/**
 * 在主进程管理 Python 生命周期与有界 RPC；原始凭据不进入公开消息。
 * Manage Python lifecycle and bounded RPC in main; keep raw credentials out of public messages.
 */

import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import path from 'node:path'
import { existsSync } from 'node:fs'
import defaults from '../../../../src/my_agent/defaults.json'
import type {
  DiagnosticReport,
  DiagnosticsParams,
  InitializeResult,
  OperationError,
  ProtocolV1
} from '../generated/protocol'
import { validate } from '../shared/validation'
import { terminateProcessTree } from './processes'

/**
 * 携带可安全跨 IPC 传递的业务错误。
 * Carry a public application error suitable for IPC.
 */
export class BackendError extends Error {
  /**
   * 保留公开错误结构，并使用其中的说明作为异常消息。
   * Keep the public error structure and use its message for the exception.
   */
  constructor(public readonly detail: OperationError) {
    super(detail.message)
  }
}

/**
 * 构造无额外修复说明的公开后端错误。
 * Create a public backend error without additional remediation.
 */
function error(code: string, message: string): BackendError {
  return new BackendError({ code, message, remediation: '' })
}

/**
 * 关联请求的完成回调与超时句柄；结束时必须一起清理。
 * Track completion callbacks and the timeout handle, cleaning them up together.
 */
type Pending = {
  resolve(value: unknown): void
  reject(reason: Error): void
  timer: ReturnType<typeof setTimeout>
}

/**
 * 维护一个 Python 连接、待响应请求和终止状态，业务初始化错误可保留诊断通道。
 * Own one Python connection and its requests; retain diagnostics after business init errors.
 */
export class Backend {
  private child: ChildProcessWithoutNullStreams | undefined
  private buffer: Buffer = Buffer.alloc(0)
  private pending = new Map<string, Pending>()
  private nextId = 0
  private failed: BackendError | undefined
  private ready: Promise<InitializeResult> | undefined
  private exited: Promise<void> | undefined
  private stopping = false
  private termination: Promise<void> | undefined
  private diagnostic: Promise<DiagnosticReport> | undefined

  /**
   * 只保存连接参数；实际进程在 start 时创建。
   * Store connection parameters; defer process creation until start.
   */
  constructor(
    private readonly root: string,
    private readonly dataDir: string,
    private readonly version: string,
    private readonly log: (message: string) => void
  ) {}

  /**
   * 复用同一个初始化承诺，避免多个界面请求重复启动后端。
   * Share one initialization promise to avoid duplicate backend processes.
   */
  start(): Promise<InitializeResult> {
    if (this.ready) return this.ready
    this.ready = this.connect()
    return this.ready
  }

  /**
   * 启动仓库虚拟环境，私下传递凭据后进行版本握手。
   * Start the repository venv, send the private bootstrap, then negotiate compatibility.
   */
  private async connect(): Promise<InitializeResult> {
    const python = path.join(
      this.root,
      '.venv',
      process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
    )
    if (!existsSync(python))
      throw error('PYTHON_MISSING', '项目 Python 环境尚未安装，请先运行 uv sync --locked。')
    const allowed = new Set([
      'PATH',
      'SYSTEMROOT',
      'WINDIR',
      'COMSPEC',
      'TEMP',
      'TMP',
      'USERPROFILE',
      'APPDATA',
      'LOCALAPPDATA',
      'PROGRAMFILES',
      'SYSTEMDRIVE',
      'UV_CACHE_DIR',
      'UV_PYTHON_INSTALL_DIR',
      'HTTP_PROXY',
      'HTTPS_PROXY',
      'ALL_PROXY',
      'NO_PROXY',
      'SSL_CERT_FILE'
    ])
    const env: NodeJS.ProcessEnv = {}
    for (const [key, value] of Object.entries(process.env)) {
      if (allowed.has(key.toUpperCase())) env[key] = value
    }
    env.PYTHONIOENCODING = 'utf-8'
    env.PYTHONUTF8 = '1'
    const child = spawn(
      python,
      [
        '-u',
        '-X',
        'utf8',
        '-m',
        'my_agent',
        '--data-dir',
        this.dataDir,
        'serve',
        '--parent-credential'
      ],
      { cwd: this.root, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, env }
    )
    this.child = child
    this.exited = new Promise((resolve) => {
      child.once('exit', () => resolve())
      child.once('error', () => resolve())
    })
    child.on('error', () => this.fail(error('BACKEND_START_FAILED', 'Python 后端启动失败。')))
    child.on('exit', () =>
      this.fail(error('BACKEND_EXITED', 'Python 后端已退出，请重新打开应用。'))
    )
    child.stdout.on('data', (chunk: Buffer) => this.receive(chunk))
    child.stderr.on('data', () => {
      // 持续消费私有诊断，避免堵塞，但不把原始内容送到 renderer 或公开日志。
      // Drain private diagnostics without forwarding raw text to the renderer or public logs.
    })
    child.stdin.on('error', () => this.fail(error('BACKEND_PIPE_CLOSED', '后端连接已关闭。')))
    const key = process.env[defaults.model.api_key_env]
    const bootstrap = JSON.stringify(key?.trim() ? { key } : {}) + '\n'
    if (Buffer.byteLength(bootstrap) > 16384) {
      this.fail(error('CREDENTIAL_TOO_LARGE', '凭据内容超过允许大小。'))
      throw this.failed
    }
    child.stdin.write(bootstrap)
    try {
      return await this.call(
        'initialize',
        {
          app_version: this.version,
          protocol_version: defaults.protocol_version,
          data_schema_version: defaults.data_schema_version
        },
        'InitializeResult'
      )
    } catch (cause) {
      // 配置需要修复不等于传输损坏，保留活跃服务供诊断使用。
      // Invalid stored configuration is not transport failure; keep the server for diagnostics.
      if (
        cause instanceof BackendError &&
        [
          'CONFIG_INVALID',
          'CONFIG_UNAVAILABLE',
          'DATA_INVALID',
          'DATA_UNAVAILABLE',
          'DATA_VERSION_UNSUPPORTED',
          'DATA_DIR_BUSY',
          'DATA_DIR_NOT_WRITABLE',
          'DISK_FULL',
          'ENVIRONMENT_RESTRICTED'
        ].includes(cause.detail.code)
      )
        throw cause
      this.fail(
        cause instanceof BackendError ? cause : error('BACKEND_START_FAILED', '后端初始化失败。')
      )
      throw this.failed
    }
  }

  /**
   * 读取最新项目与模型配置，避免将初始化快照当作当前状态。
   * Read fresh projects and model settings instead of reusing stale initialization state.
   */
  async info(): Promise<InitializeResult> {
    const initial = await this.start()
    this.assertHealthy()
    const projects = await this.call('projects.list', {}, 'ProjectsView')
    const config = await this.call('config.get', {}, 'PublicConfig')
    return { ...initial, projects, config }
  }

  /**
   * 允许存储初始化失败后的诊断，并串行化耗时探测。
   * Allow diagnostics after storage initialization failure and serialize long probes.
   */
  async diagnostics(params: DiagnosticsParams): Promise<DiagnosticReport> {
    try {
      await this.start()
    } catch {
      // 初始化被拒绝后仍可诊断；真正断管或退出仍由健康检查拒绝。
      // A live server can diagnose rejected configuration; transport failures still fail here.
      this.assertHealthy()
    }
    if (this.diagnostic) throw error('DIAGNOSTICS_BUSY', '已有诊断正在运行，请等待完成。')
    this.diagnostic = this.call('diagnostics.get', params, 'DiagnosticReport', 60000)
    try {
      return await this.diagnostic
    } finally {
      this.diagnostic = undefined
    }
  }

  /**
   * 按方法校验结果；排队等待诊断完成后再开始普通请求计时。
   * Validate the method result and start ordinary timeouts only after diagnostics finish.
   */
  async call<K extends keyof ProtocolV1>(
    method: string,
    params: object,
    resultType: K,
    timeoutMs = 8000
  ): Promise<ProtocolV1[K]> {
    // M0 顺序处理请求，长诊断排队时间不能占用普通请求的响应预算。
    // M0 serializes requests; diagnostic queue time must not consume an ordinary response budget.
    if (method !== 'diagnostics.get' && this.diagnostic) await this.diagnostic
    const value = await this.request(method, params, timeoutMs)
    try {
      return validate(resultType, value)
    } catch {
      this.fail(error('PROTOCOL_INVALID', '后端返回的数据格式不正确。'))
      throw this.failed
    }
  }

  /**
   * 拒绝已失败、关闭中或已退出连接上的新请求。
   * Reject new requests on failed, stopping or exited connections.
   */
  private assertHealthy(): void {
    if (this.failed) throw this.failed
    if (this.stopping || !this.child || this.child.exitCode !== null || this.child.killed) {
      throw error('BACKEND_EXITED', 'Python 后端未连接，请重新打开应用。')
    }
  }

  /**
   * 注册请求关联与超时，在写入前限制队列和帧大小。
   * Register correlation and timeout, checking queue and frame limits before writing.
   */
  private request(method: string, params: object, timeoutMs: number): Promise<unknown> {
    this.assertHealthy()
    if (this.pending.size >= 32)
      return Promise.reject(error('BACKEND_BUSY', '正在处理其他请求，请稍后重试。'))
    const id = 'request-' + ++this.nextId
    const frame = JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n'
    if (Buffer.byteLength(frame) > defaults.max_frame_bytes) {
      return Promise.reject(error('FRAME_TOO_LARGE', '请求超过大小限制。'))
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.fail(error('BACKEND_TIMEOUT', '后端响应超时，请重新打开应用。'))
      }, timeoutMs)
      this.pending.set(id, { resolve, reject, timer })
      this.child?.stdin.write(frame)
    })
  }

  /**
   * 先按字节组帧再严格解码 UTF-8；响应必须匹配仍在等待的请求。
   * Frame bytes before strict UTF-8 decoding and require a matching pending request.
   */
  private receive(chunk: Buffer): void {
    if (this.failed) return
    this.buffer = Buffer.concat([this.buffer, chunk])
    while (true) {
      const newline = this.buffer.indexOf(10)
      if (newline < 0) {
        if (this.buffer.length > defaults.max_frame_bytes)
          this.fail(error('FRAME_TOO_LARGE', '后端响应超过大小限制。'))
        return
      }
      const line = this.buffer.subarray(0, newline)
      this.buffer = this.buffer.subarray(newline + 1)
      if (line.length > defaults.max_frame_bytes) {
        this.fail(error('FRAME_TOO_LARGE', '后端响应超过大小限制。'))
        return
      }
      try {
        const data: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(line))
        const response = validate('RpcResponse', data)
        const pending = response.id === null ? undefined : this.pending.get(response.id)
        if (!pending || response.id === null) throw new Error('Unmatched RPC response')
        this.pending.delete(response.id)
        clearTimeout(pending.timer)
        if ('error' in response) {
          pending.reject(
            new BackendError({ ...response.error.data, message: response.error.message })
          )
        } else {
          pending.resolve(response.result)
        }
      } catch {
        this.fail(error('PROTOCOL_INVALID', '后端通信格式不正确。'))
        return
      }
    }
  }

  /**
   * 只记录首次失败的公开码，结束全部待响应请求并清理自有后端。
   * Record the first public failure code, reject pending requests and stop the owned backend.
   */
  private fail(cause: BackendError): void {
    if (this.failed) return
    this.failed = cause
    if (!this.stopping) this.log(cause.detail.code)
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer)
      pending.reject(cause)
    }
    this.pending.clear()
    this.buffer = Buffer.alloc(0)
    this.child?.stdin.end()
    this.terminate()
  }

  /**
   * 复用终止任务，防止多个失败分支重复处理进程树。
   * Share the termination task so failure paths do not stop the process tree repeatedly.
   */
  private terminate(): void {
    if (this.child && !this.termination)
      this.termination = terminateProcessTree(this.child, this.log)
  }

  /**
   * 先发送 EOF，超出清理宽限再终止，并等待实际退出事件。
   * Send EOF, terminate after the cleanup grace period and await the actual exit event.
   */
  async stop(): Promise<void> {
    const child = this.child
    this.stopping = true
    if (!child) return
    if (child.exitCode !== null || child.signalCode !== null) {
      await this.termination
      return
    }
    child.stdin.end()
    const timer = setTimeout(() => this.terminate(), 2000)
    try {
      // 发出终止请求不代表已退出，需等待实际事件以释放管道和写入锁。
      // A kill request alone does not prove exit; wait for the process event and lock release.
      await this.exited
      await this.termination
    } finally {
      clearTimeout(timer)
    }
  }
}
