/** 诊断页管理后端连接生命周期，只展示可观测事实。
 * Manage backend connections in diagnostics using observable facts only.
 */
import { useEffect, useRef, useState } from 'react'
import type {
  ConnectionObservation,
  ConnectionStatus,
  ModelConnectionState,
  ModelId,
  PublicConfig
} from '../../generated/protocol'
import type { Result } from '../../shared/api'

type Props = {
  connected: boolean
  busy: boolean
  config: PublicConfig | undefined
  diagnosticStatus: ConnectionStatus | null | undefined
  onBusy: (value: boolean) => void
  onConfig: (config: PublicConfig) => void
}

const phases = {
  preparing: '准备请求',
  connecting: '建立连接',
  tls: 'TLS 握手',
  waiting: '等待服务',
  receiving: '接收响应',
  reasoning: '模型处理中',
  text: '输出正文',
  completed: '响应结束'
}

const modelNames: Record<ModelId, string> = {
  'glm-5.3-flash': 'GLM 5.3 Flash',
  'deepseek-v4.1-flash': 'DeepSeek V4.1 Flash'
}
const modelShortNames: Record<ModelId, string> = {
  'glm-5.3-flash': 'GLM',
  'deepseek-v4.1-flash': 'DeepSeek'
}

/** 将缺失指标保留为未观测，不当作零耗时。 Keep absent measurements distinct from zero. */
function elapsed(value: number | null | undefined): string {
  return value == null ? '未观测' : `${(value / 1000).toFixed(3)} 秒`
}

/** 独立显示指定模型的测试目标、阶段和结果，不将共享池冒充模型在线状态。
 * Show one model's explicit target, phase and result without claiming ongoing connectivity.
 */
function ModelConnectionRow({
  model,
  state,
  testing,
  disabled,
  onTest
}: {
  model: ModelId
  state: ModelConnectionState | undefined
  testing: boolean
  disabled: boolean
  onTest: () => void
}) {
  const running = testing || state?.testing === true
  const result = state?.last_test
  const progress = running ? (state?.testing ? state.progress : null) : result?.progress
  const outcome = running ? 'running' : !result ? 'unknown' : result.code === 'OK' ? 'ok' : 'error'
  return (
    <article className="model-connection-row" data-testid={`model-connection-${model}`}>
      <div className="model-connection-name">
        <strong>{modelNames[model]}</strong>
        <code>{model}</code>
        <span className={`model-test-status ${outcome}`} aria-live="polite">
          {running
            ? `正在测试 · ${progress ? phases[progress.phase] : '准备请求'}`
            : !state
              ? '状态尚未读取'
              : !result
                ? '尚未测试'
                : result.code === 'OK'
                  ? '最近测试成功'
                  : `最近测试失败 · ${result.code}`}
        </span>
      </div>
      <div className="model-connection-result">
        <div>
          模型首字 <strong>{elapsed(progress?.first_text_ms)}</strong>
        </div>
        <small>
          {running
            ? '正在请求该模型…'
            : result
              ? `测试时间：${new Date(result.finished_at).toLocaleString('zh-CN')}`
              : '点击右侧按钮，测试该模型的实际响应'}
        </small>
        {progress && (
          <details>
            <summary>分段耗时</summary>
            <div className="connection-metrics">
              <span>阶段：{phases[progress.phase]}</span>
              <span>总耗时：{elapsed(progress.elapsed_ms)}</span>
              <span>建立连接：{elapsed(progress.connect_ms)}</span>
              <span>TLS：{elapsed(progress.tls_ms)}</span>
              <span>响应头：{elapsed(progress.response_headers_ms)}</span>
            </div>
          </details>
        )}
        {!running && result && result.code !== 'OK' && (
          <p className="model-test-error">
            {result.message} {result.remediation}
          </p>
        )}
      </div>
      <button className="secondary" disabled={disabled || running} onClick={onTest}>
        {running ? `正在测试 ${modelShortNames[model]}…` : `测试 ${modelShortNames[model]}`}
      </button>
    </article>
  )
}

/** 显示单次历史结果与阶段耗时，不表示持续健康。 Show one past result, not ongoing health. */
function Observation({ title, value }: { title: string; value: ConnectionObservation | null }) {
  return (
    <div className="connection-observation">
      <strong>{title}</strong>
      {value ? (
        <>
          <p>
            {value.model_id && `${modelNames[value.model_id]} · `}
            {value.code === 'OK' ? '成功' : `未通过（${value.code}）`} ·{' '}
            {new Date(value.finished_at).toLocaleString('zh-CN')}
            {value.http_status !== null && ` · HTTP ${value.http_status}`}
          </p>
          <div className="connection-metrics">
            <span>结束于：{phases[value.progress.phase]}</span>
            <span>总耗时：{elapsed(value.progress.elapsed_ms)}</span>
            <span>建立连接：{elapsed(value.progress.connect_ms)}</span>
            <span>TLS：{elapsed(value.progress.tls_ms)}</span>
            <span>响应头：{elapsed(value.progress.response_headers_ms)}</span>
            {value.progress.first_text_ms != null && (
              <span>模型首字：{elapsed(value.progress.first_text_ms)}</span>
            )}
          </div>
          {value.models_confirmed === false && (
            <p className="settings-hint">目录返回成功，但尚未确认全部默认模型。</p>
          )}
          {value.code === 'CATALOG_AUTH_REQUIRED' && (
            <p className="settings-hint">
              服务已返回响应，但目录要求认证；本次未发送密钥，不能据此判断密钥是否有效。
            </p>
          )}
        </>
      ) : (
        <p className="settings-hint">本次应用运行期间尚无记录。</p>
      )}
    </div>
  )
}

/** 读取共享池快照，保存开关并显式探测；页面加载不联网。
 * Read pool snapshots, persist policy and explicitly probe; mounting does not use the network.
 */
export function Connections({
  connected,
  busy,
  config,
  diagnosticStatus,
  onBusy,
  onConfig
}: Props) {
  const [status, setStatus] = useState<ConnectionStatus | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [timeout, setTimeout] = useState('')
  const [operation, setOperation] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const generation = useRef(0)
  const working = useRef(false)

  useEffect(() => {
    if (diagnosticStatus) {
      ++generation.current
      setStatus(diagnosticStatus)
    }
  }, [diagnosticStatus])

  useEffect(() => {
    if (config) {
      setEnabled(config.http.reuse_enabled)
      setTimeout(String(config.http.probe_timeout_seconds))
    }
  }, [config])

  useEffect(() => {
    const ticket = ++generation.current
    setStatus(null)
    if (connected) {
      void window.agent.getConnections().then(
        (result) => {
          if (ticket !== generation.current) return
          if (result.ok) setStatus(result.data)
          else setError(result.error.message)
        },
        () => {
          if (ticket === generation.current) setError('连接状态读取失败，请刷新重试。')
        }
      )
    }
    return () => {
      ++generation.current
    }
  }, [connected])

  useEffect(() => {
    if (!operation.startsWith('model:')) return
    let stopped = false
    const ticket = generation.current
    let timer: number
    /** 仅在显式测试期间读取本地进度；顺序轮询并丢弃迟到结果。
     * Poll local state only during explicit testing; serialize reads and discard stale results.
     */
    async function poll(): Promise<void> {
      try {
        const result = await window.agent.getConnections()
        if (!stopped && working.current && ticket === generation.current) {
          if (result.ok) {
            setStatus(result.data)
            setMessage('')
          } else {
            setMessage(`进度读取失败：${result.error.message} 正在等待本次测试结果。`)
          }
        }
      } catch {
        if (!stopped && working.current && ticket === generation.current) {
          setMessage('测试进度暂时无法读取，正在等待本次测试结果。')
        }
      }
      if (!stopped && working.current) timer = window.setTimeout(() => void poll(), 400)
    }
    timer = window.setTimeout(() => void poll(), 400)
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [operation])

  /** 互斥本面板操作并拒绝过期结果，错误仅显示公开说明。
   * Serialize panel actions and reject stale results, showing public errors only.
   */
  async function perform<T>(
    name: string,
    action: () => Promise<Result<T>>,
    accept: (value: T) => void
  ): Promise<void> {
    if (working.current || busy || !connected) return
    working.current = true
    const ticket = ++generation.current
    onBusy(true)
    setOperation(name)
    setError('')
    setMessage('')
    try {
      const result = await action()
      if (ticket !== generation.current) return
      if (result.ok) {
        if (name.startsWith('model:')) setMessage('')
        accept(result.data)
      } else setError(result.error.message + ' ' + result.error.remediation)
    } catch {
      if (ticket === generation.current) setError('连接管理操作未完成，请刷新状态后重试。')
    } finally {
      working.current = false
      setOperation('')
      onBusy(false)
    }
  }

  /** 保存偏好后刷新运行状态，保存失败时不改已生效配置。
   * Refresh lifecycle state after saving; failed saves preserve the effective configuration.
   */
  async function save(): Promise<Result<PublicConfig>> {
    const ticket = generation.current
    const result = await window.agent.saveConnections({
      reuse_enabled: enabled,
      probe_timeout_seconds: Number(timeout)
    })
    if (result.ok) {
      try {
        const refreshed = await window.agent.getConnections()
        if (ticket === generation.current) {
          setStatus(refreshed.ok ? refreshed.data : null)
          if (!refreshed.ok) setError('设置已保存，但状态刷新失败，请稍后刷新连接状态。')
        }
      } catch {
        if (ticket === generation.current) {
          setStatus(null)
          setError('设置已保存，但状态刷新失败，请稍后刷新连接状态。')
        }
      }
    }
    return result
  }

  const timeoutValid = Number.isFinite(Number(timeout)) && Number(timeout) > 0
  const disabled = busy || !connected || !config
  return (
    <section className="connection-panel" aria-labelledby="connections-heading">
      <div className="settings-card-heading">
        <h3 id="connections-heading">模型连接池</h3>
        <span className="subtle-tag">当前后端 · 跨会话共享</span>
      </div>
      <p className="settings-hint">
        分别测试 GLM 和 DeepSeek 的实际响应；每次只向所选模型发送一条短消息，会使用模型额度。
        测试不发送项目内容或会话历史，结果按模型独立保留。
      </p>
      <div className="model-connection-list">
        {config?.allowed_models.map((model) => (
          <ModelConnectionRow
            key={model}
            model={model}
            state={status?.models?.find((item) => item.model_id === model)}
            testing={operation === `model:${model}`}
            disabled={disabled || !timeoutValid}
            onTest={() =>
              void perform(
                `model:${model}`,
                () =>
                  window.agent.testModelConnection({
                    model_id: model,
                    timeout_seconds: Number(timeout)
                  }),
                setStatus
              )
            }
          />
        ))}
      </div>
      <p className="settings-hint">
        两个模型共用下面的 HTTP
        连接池。测试结果仅表示当次响应，重启后清空；打开页面与刷新状态不联网。
      </p>
      <div className="connection-metrics" data-testid="connection-pool-status">
        <span>当前复用：{status ? (status.reuse_enabled ? '开启' : '关闭') : '尚未读取'}</span>
        <span>
          共享客户端：{status ? (status.client_created ? '已创建' : '未创建') : '尚未读取'}
        </span>
        <span>活动请求：{status?.active_requests ?? '尚未读取'}</span>
        <span>
          {!status
            ? '释放状态：尚未读取'
            : status.pending_release
              ? '已有请求结束后释放旧连接'
              : '无待释放的活动连接'}
        </span>
      </div>
      <div className="diagnostic-options">
        <label>
          <input
            type="checkbox"
            checked={enabled}
            disabled={disabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          跨会话复用连接
        </label>
        <label>
          连接测试超时（秒）
          <input
            className="connection-timeout"
            type="number"
            min="0"
            step="any"
            value={timeout}
            disabled={disabled}
            onChange={(event) => setTimeout(event.target.value)}
          />
        </label>
      </div>
      <div className="settings-actions">
        <button
          className="primary"
          disabled={disabled || !timeoutValid}
          onClick={() =>
            void perform('save', save, (value) => {
              onConfig(value)
              setMessage('连接设置已保存，重启后保留；正在进行的回答会继续完成。')
            })
          }
        >
          保存连接设置
        </button>
        <button
          className="secondary"
          disabled={disabled}
          onClick={() => void perform('refresh', () => window.agent.getConnections(), setStatus)}
        >
          刷新连接状态
        </button>
        <button
          className="secondary"
          disabled={disabled || !status}
          onClick={() =>
            void perform(
              'release',
              () => window.agent.releaseConnections(),
              (value) => {
                setStatus(value)
                setMessage(
                  value.pending_release
                    ? '已安排释放，当前回答结束后关闭旧连接。'
                    : '已有连接已释放，下次请求按需建立。'
                )
              }
            )
          }
        >
          释放已有连接
        </button>
      </div>
      {message && (
        <p className="settings-hint" aria-live="polite">
          {message}
        </p>
      )}
      {error && (
        <p className="notice" role="alert">
          {error}
        </p>
      )}
      <p className="settings-hint">
        开启后保留可复用连接；关闭后仍可聊天，每次请求结束即释放。客户端已创建不代表连接仍在线。
        没有后台保活；释放和切换开关均不打断当前回答。
      </p>
      <details className="connection-details">
        <summary>网关目录探测与最近请求</summary>
        <p className="settings-hint">
          目录探测仅发送一次无密钥 GET 请求，不调用任何模型、不验证认证或生成速度。
        </p>
        <button
          className="secondary"
          disabled={disabled || !timeoutValid}
          onClick={() =>
            void perform(
              'gateway',
              () => window.agent.testConnection({ timeout_seconds: Number(timeout) }),
              setStatus
            )
          }
        >
          {operation === 'gateway' ? '正在探测网关目录…' : '网关目录探测'}
        </button>
        <Observation title="最近模型请求" value={status?.last_request ?? null} />
        <Observation title="最近网关目录探测" value={status?.last_probe ?? null} />
      </details>
    </section>
  )
}
