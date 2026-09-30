/**
 * 模型、目录与诊断设置页；显示后端事实，额外探测由用户触发。
 * Model, path and diagnostic settings; show backend facts and run probes only on request.
 */

import { useEffect, useRef, useState } from 'react'
import type {
  DiagnosticReport,
  InitializeResult,
  ModelId,
  PublicConfig,
  StartupPaths
} from '../../generated/protocol'
import type { Result } from '../../shared/api'
import { RunSettings } from './RunSettings'
import { Connections } from './Connections'
import { EnvironmentSettings } from './EnvironmentSettings'
import { Workflows } from './Workflows'

/**
 * 从工作台接收连接与互斥状态，并上报已保存配置。
 * Receive connection and busy state from the workspace and report saved settings.
 */
type Props = {
  info: InitializeResult | null
  connected: boolean
  busy: boolean
  onBusy: (value: boolean) => void
  onConfig: (value: PublicConfig) => void
}

const modelNames: Record<ModelId, string> = {
  'glm-5.3-flash': 'GLM-5.3-Flash',
  'deepseek-v4.1-flash': 'DeepSeek V4.1 Flash'
}
const statuses = { ok: '正常', warning: '注意', error: '异常', not_checked: '未检查' }
const sources = { default: '内置默认', user: '已保存配置', cli: '启动参数' }
const credentialSources = {
  process: '当前进程',
  windows_user: 'Windows 用户环境',
  none: '未检测到',
  restricted: '读取受限'
}
const checkNames: Record<string, string> = {
  python: 'Python 解释器',
  config: '模型配置',
  storage: '数据目录',
  writer: '写入锁',
  disk: '磁盘空间',
  write_probe: '实际写入探测',
  credential: '模型凭据',
  catalog: '服务目录连通性',
  catalog_models: '模型目录',
  execution_backend: '容器环境',
  configuration_storage: '配置与存储',
  storage_access: '目录访问'
}

/**
 * 管理待保存输入与操作反馈，区分当前生效数据根和下次启动配置。
 * Manage pending edits and feedback, separating active storage from next-launch settings.
 */
export function Settings({ info, connected, busy, onBusy, onConfig }: Props) {
  const [paths, setPaths] = useState<StartupPaths | null>(null)
  const [dataDir, setDataDir] = useState('')
  const [projectDir, setProjectDir] = useState('')
  const [model, setModel] = useState<ModelId | null>(null)
  const [dev, setDev] = useState(false)
  const [network, setNetwork] = useState(false)
  const [writeProbe, setWriteProbe] = useState(false)
  const [report, setReport] = useState<DiagnosticReport | null>(null)
  const [operation, setOperation] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const mounted = useRef(true)
  const running = useRef(false)

  /**
   * 以主进程确认的目录设置刷新表单。
   * Refresh form fields from main-confirmed directory settings.
   */
  const applyPaths = (value: StartupPaths) => {
    setPaths(value)
    setDataDir(value.data_dir)
    setProjectDir(value.project_dir)
  }

  useEffect(() => {
    mounted.current = true
    let active = true
    void window.agent
      .getStartupPaths()
      .then((result) => {
        if (!active) return
        if (result.ok) applyPaths(result.data)
        else setError(result.error.message + ' ' + result.error.remediation)
      })
      .catch(() => {
        if (active) setError('启动目录配置读取失败，请重新打开应用。')
      })
    return () => {
      active = false
      mounted.current = false
    }
  }, [])

  /**
   * 统一设置操作的互斥、加载和错误状态；卸载后不再更新页面。
   * Coordinate settings actions, loading and errors; stop updating state after unmount.
   */
  async function perform<T>(
    name: string,
    action: () => Promise<Result<T>>,
    success: (value: T) => void
  ): Promise<void> {
    if (running.current || busy) return
    running.current = true
    onBusy(true)
    setOperation(name)
    setMessage('')
    setError('')
    try {
      const result = await action()
      if (!mounted.current) return
      if (result.ok) success(result.data)
      else setError(result.error.message + ' ' + result.error.remediation)
    } catch {
      if (mounted.current) setError('操作未完成，请检查连接状态后重试。')
    } finally {
      running.current = false
      if (mounted.current) {
        setOperation('')
        onBusy(false)
      }
    }
  }

  const config = info?.config
  const selectedModel = model ?? config?.model_id
  /** 连接配置保存后使旧报告失效，与主进程导出缓存保持一致。
   * Invalidate old reports after connection settings change, matching the export cache.
   */
  const acceptConnectionConfig = (value: PublicConfig) => {
    onConfig(value)
    setReport(null)
  }
  /**
   * 保存选中的模型，成功后采用后端结果并使旧诊断报告失效。
   * Save the selected model, apply backend results and invalidate the old diagnostic report.
   */
  const saveModel = () => {
    if (!selectedModel) return
    void perform(
      'model',
      () => window.agent.saveConfig({ model_id: selectedModel }),
      (value) => {
        onConfig(value)
        setModel(null)
        setReport(null)
        setMessage('默认模型已保存，重新启动后继续使用。')
      }
    )
  }
  /**
   * 触发指定公开文档的原生导出，并区分成功与取消。
   * Request a native public-document export, distinguishing success from cancellation.
   */
  const exportResult = (kind: 'config' | 'projects' | 'diagnostics') => {
    void perform(
      'export',
      () => window.agent.exportJson({ kind }),
      (value) => {
        setMessage(value.path ? '已导出到：' + value.path : '已取消导出。')
      }
    )
  }

  return (
    <div className="content settings-content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">PREFERENCES</div>
          <h1>设置与诊断</h1>
          <p>管理本地配置，检查运行环境，保存诊断结果。</p>
        </div>
      </div>
      {config && <RunSettings config={config} disabled={busy || !connected} onSaved={onConfig} />}
      {error && (
        <div className="notice" role="alert">
          <span>!</span>
          <p>{error}</p>
        </div>
      )}
      {message && (
        <div className="settings-success" role="status">
          {message}
        </div>
      )}
      <div className="settings-grid">
        <section className="detail-card settings-card" aria-labelledby="model-heading">
          <div className="settings-card-heading">
            <h2 id="model-heading">模型与凭据</h2>
            <span className="tag">OpenCode Go</span>
          </div>
          <label className="field-label" htmlFor="default-model">
            默认模型
          </label>
          <select
            id="default-model"
            value={selectedModel ?? ''}
            disabled={!connected || busy}
            onChange={(event) => {
              const value = event.target.value
              if (value === 'glm-5.3-flash' || value === 'deepseek-v4.1-flash') setModel(value)
            }}
          >
            {!config && <option value="">等待读取配置</option>}
            {config?.allowed_models.map((value) => (
              <option key={value} value={value}>
                {modelNames[value]}
              </option>
            ))}
          </select>
          <div className="settings-actions">
            <button
              className="primary"
              disabled={!connected || busy || selectedModel === config?.model_id}
              onClick={saveModel}
            >
              {operation === 'model' ? '正在保存…' : '保存默认模型'}
            </button>
            <button
              className="secondary"
              disabled={!connected || busy}
              onClick={() =>
                void perform(
                  'refresh',
                  () => window.agent.getConfig(),
                  (value) => {
                    onConfig(value)
                    setModel(null)
                    setMessage('配置已刷新。')
                  }
                )
              }
            >
              刷新配置
            </button>
          </div>
          <dl className="settings-facts">
            <dt>配置来源</dt>
            <dd>{config ? sources[config.model_source] : '尚未读取'}</dd>
            <dt>服务地址</dt>
            <dd>{config?.base_url ?? '尚未读取'}</dd>
            <dt>接口</dt>
            <dd>{config?.api ?? '尚未读取'}</dd>
            <dt>配置文件</dt>
            <dd>{config?.config_path ?? '尚未读取'}</dd>
            <dt>凭据变量</dt>
            <dd>{config?.credential.env_var ?? '尚未读取'}</dd>
            <dt>凭据来源</dt>
            <dd>{config ? credentialSources[config.credential.source] : '尚未读取'}</dd>
            <dt>凭据状态</dt>
            <dd>
              {!config
                ? '尚未读取'
                : config.credential.present === true
                  ? '已检测，尚未验证调用'
                  : config.credential.present === false
                    ? '未检测到'
                    : '读取受限'}
            </dd>
          </dl>
          <p className="settings-hint">
            配置保存由 Python 后端完成。此处不展示密钥；修改进程环境变量后需要重新启动应用。
          </p>
        </section>

        <section className="detail-card settings-card" aria-labelledby="paths-heading">
          <div className="settings-card-heading">
            <h2 id="paths-heading">启动目录</h2>
            <span className="subtle-tag">下次启动生效</span>
          </div>
          <p className="settings-hint">
            当前数据位置：
            <code>{paths?.current_data_dir ?? info?.storage.data_dir ?? '尚未读取'}</code>
          </p>
          <label className="field-label" htmlFor="startup-data-dir">
            应用数据目录
          </label>
          <div className="path-field">
            <input
              id="startup-data-dir"
              value={dataDir}
              disabled={!paths || busy}
              onChange={(event) => setDataDir(event.target.value)}
            />
            <button
              className="secondary"
              disabled={!paths || busy}
              onClick={() =>
                void perform(
                  'choose-data',
                  () => window.agent.chooseStartupDirectory({ kind: 'data' }),
                  (value) => {
                    if (value.path) setDataDir(value.path)
                  }
                )
              }
            >
              选择数据目录
            </button>
          </div>
          <label className="field-label" htmlFor="startup-project-dir">
            项目选择器起始目录
          </label>
          <div className="path-field">
            <input
              id="startup-project-dir"
              value={projectDir}
              disabled={!paths || busy}
              onChange={(event) => setProjectDir(event.target.value)}
            />
            <button
              className="secondary"
              disabled={!paths || busy}
              onClick={() =>
                void perform(
                  'choose-project',
                  () => window.agent.chooseStartupDirectory({ kind: 'project' }),
                  (value) => {
                    if (value.path) setProjectDir(value.path)
                  }
                )
              }
            >
              选择起始目录
            </button>
          </div>
          <div className="settings-actions">
            <button
              className="primary"
              disabled={
                !paths || busy || (dataDir === paths.data_dir && projectDir === paths.project_dir)
              }
              onClick={() =>
                void perform(
                  'paths',
                  () =>
                    window.agent.saveStartupPaths({ data_dir: dataDir, project_dir: projectDir }),
                  (value) => {
                    applyPaths(value)
                    setMessage('启动目录已保存。重新启动后生效，现有数据不会自动搬迁。')
                  }
                )
              }
            >
              {operation === 'paths' ? '正在保存…' : '保存启动目录'}
            </button>
          </div>
          <p className="settings-hint">
            切换数据目录不会迁移记录。需要保留历史时，先关闭应用并备份、复制原数据，再从新位置启动。
          </p>
          <p className="settings-hint">
            启动参数和环境变量仍优先于本机文件。修改选择器起始目录不会自动登记项目。
          </p>
          <details className="settings-details">
            <summary>查看本机配置位置</summary>
            <code>{paths?.config_path ?? '尚未读取'}</code>
          </details>
        </section>

        <section
          className="detail-card settings-card diagnostics-card"
          aria-labelledby="diagnostics-heading"
        >
          <div className="settings-card-heading">
            <h2 id="diagnostics-heading">环境诊断</h2>
            <span className="subtle-tag">默认仅检查本机</span>
          </div>
          <div className="diagnostic-options">
            <label>
              <input
                type="checkbox"
                checked={dev}
                disabled={busy}
                onChange={(event) => setDev(event.target.checked)}
              />
              包括开发工具与容器环境
            </label>
            <label>
              <input
                type="checkbox"
                checked={network}
                disabled={busy}
                onChange={(event) => setNetwork(event.target.checked)}
              />
              探测服务网络连通性
            </label>
            <label>
              <input
                type="checkbox"
                checked={writeProbe}
                disabled={busy}
                onChange={(event) => setWriteProbe(event.target.checked)}
              />
              实际测试数据目录写入
            </label>
          </div>
          <p className="settings-hint">
            网络探测仅请求模型目录，不发送密钥或生成请求；写入探测创建并清理独立临时文件。开发检查可能需要数十秒。
          </p>
          <div className="settings-actions">
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                void perform(
                  'diagnostics',
                  () =>
                    window.agent.runDiagnostics({
                      dev,
                      network,
                      write_probe: writeProbe,
                      network_timeout_seconds: config?.http.probe_timeout_seconds ?? null
                    }),
                  setReport
                )
              }
            >
              {operation === 'diagnostics' ? '正在检查…' : '运行诊断'}
            </button>
            <button
              className="secondary"
              disabled={busy || !report}
              onClick={() => exportResult('diagnostics')}
            >
              导出诊断 JSON
            </button>
          </div>
          {operation === 'diagnostics' && (
            <p className="loading-line" role="status">
              <i />
              正在等待诊断结果，完成后显示各项状态。
            </p>
          )}
          {report ? (
            <div data-testid="diagnostic-report">
              <div className="diagnostic-summary">
                <strong>
                  {report.checks.some((check) => check.blocking)
                    ? '发现需要处理的问题'
                    : '本次检查已完成'}
                </strong>
                <span>{new Date(report.checked_at).toLocaleString('zh-CN')}</span>
              </div>
              <div className="diagnostic-assurances">
                <span>
                  凭据：
                  {report.credential_present === true
                    ? '已检测'
                    : report.credential_present === false
                      ? '未检测到'
                      : '读取受限'}
                </span>
                <span>模型认证：未验证</span>
                <span>工具回合：未验证</span>
              </div>
              <div className="diagnostic-list">
                {report.checks.map((check) => (
                  <div
                    className="diagnostic-row"
                    key={check.check_id}
                    data-check-id={check.check_id}
                  >
                    <span className={'diagnostic-badge ' + check.status}>
                      {statuses[check.status]}
                    </span>
                    <div className="diagnostic-body">
                      <strong>
                        {checkNames[check.check_id] ?? check.check_id.replace(/^file\./, '文件：')}
                      </strong>
                      <p>{check.summary}</p>
                      {check.remediation && <p className="remediation">{check.remediation}</p>}
                      <details className="settings-details">
                        <summary>检查详情</summary>
                        <code>{check.code}</code>
                        {Object.entries(check.evidence).map(([key, value]) => (
                          <div className="evidence-row" key={key}>
                            <span>{key}</span>
                            <code>{value === null ? '不可用' : String(value)}</code>
                          </div>
                        ))}
                      </details>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="settings-hint">尚未运行诊断。打开此页不会自动联网或执行写入探测。</p>
          )}
        </section>

        <section className="detail-card settings-card diagnostics-card">
          <Connections
            connected={connected}
            busy={busy}
            config={config}
            diagnosticStatus={report?.connections}
            onBusy={onBusy}
            onConfig={acceptConnectionConfig}
          />
        </section>

        <Workflows />
        <EnvironmentSettings
          projectId={info?.projects.active_project?.project_id ?? null}
          projectName={info?.projects.active_project?.name ?? ''}
          connected={connected}
        />
        <section className="detail-card settings-card export-card" aria-labelledby="export-heading">
          <div>
            <h2 id="export-heading">导出公开配置与项目列表</h2>
            <p className="settings-hint">导出当前后端返回的 JSON，包含目录信息，不包含 API Key。</p>
          </div>
          <div className="settings-actions">
            <button
              className="secondary"
              disabled={!connected || busy}
              onClick={() => exportResult('config')}
            >
              导出配置 JSON
            </button>
            <button
              className="secondary"
              disabled={!connected || busy}
              onClick={() => exportResult('projects')}
            >
              导出项目 JSON
            </button>
          </div>
        </section>
      </div>
    </div>
  )
}
