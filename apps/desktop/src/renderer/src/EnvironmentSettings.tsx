/** 已有环境登记与项目默认设置。 Existing environment registration and project defaults. */
import { useEffect, useRef, useState } from 'react'
import type {
  EnvironmentCatalog,
  EnvironmentProbe,
  EnvironmentRecord,
  ExecutionSettings
} from '../../generated/protocol'
import type { Result } from '../../shared/api'

type EnvironmentDefinition = EnvironmentRecord['definition']

const budgetLabels: Record<keyof ExecutionSettings, string> = {
  command_timeout_seconds: '普通命令时限（秒）',
  service_ready_timeout_seconds: '服务就绪时限（秒）',
  cleanup_timeout_seconds: '进程清理宽限（秒）',
  probe_timeout_seconds: '环境探测时限（秒）',
  max_output_bytes: '每个程序保留输出（字节）'
}

/** 保存后端事实，输入只在用户操作时落盘。 Persist inputs only through explicit user actions. */
export function EnvironmentSettings({
  projectId,
  projectName,
  connected
}: {
  projectId: string | null
  projectName: string
  connected: boolean
}): React.JSX.Element {
  const [catalog, setCatalog] = useState<EnvironmentCatalog | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [kind, setKind] = useState<EnvironmentDefinition['kind']>('python')
  const [name, setName] = useState('')
  const [scope, setScope] = useState<'absolute' | 'project'>('absolute')
  const [interpreter, setInterpreter] = useState('')
  const [launcher, setLauncher] = useState('')
  const [prefix, setPrefix] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [environmentId, setEnvironmentId] = useState('')
  const [limits, setLimits] = useState<ExecutionSettings | null>(null)
  const [pythonProbe, setPythonProbe] = useState<EnvironmentProbe | null>(null)
  const [pythonBusy, setPythonBusy] = useState(false)
  const [pythonError, setPythonError] = useState('')
  const generation = useRef(0)

  /** 接受同一项目的最新保存结果。 Accept saved facts belonging to the current project. */
  function accept(data: EnvironmentCatalog): void {
    setCatalog(data)
    setEnvironmentId(data.binding?.environment_id ?? '')
    setLimits(data.settings)
    setPythonProbe(null)
  }

  useEffect(() => {
    const current = ++generation.current
    setCatalog(null)
    setError('')
    setEditing(null)
    setBusy(false)
    setPythonProbe(null)
    setPythonBusy(false)
    setPythonError('')
    if (connected)
      void window.agent
        .listEnvironments({ project_id: projectId })
        .then((result) => {
          if (current !== generation.current) return
          if (result.ok) accept(result.data)
          else setError(result.error.message)
        })
        .catch(() => {
          if (current === generation.current) setError('无法读取执行环境。')
        })
    return () => {
      generation.current++
    }
  }, [projectId, connected])

  /** 操作期间保存当前身份，迟到结果不能覆盖新项目。 Guard delayed mutations by view generation. */
  async function save(action: () => Promise<Result<EnvironmentCatalog>>): Promise<void> {
    const current = generation.current
    setBusy(true)
    setError('')
    try {
      const result = await action()
      if (current !== generation.current) return
      if (result.ok) accept(result.data)
      else setError(result.error.message)
    } catch {
      if (current === generation.current) setError('环境操作未完成，请刷新查看实际保存状态。')
    } finally {
      if (current === generation.current) setBusy(false)
    }
  }

  /** 原生选择只更新输入，不自动导入或绑定。 Picking changes inputs without registration or binding. */
  async function pick(target: 'interpreter' | 'launcher' | 'prefix'): Promise<void> {
    const current = generation.current
    setBusy(true)
    try {
      const result = await window.agent.chooseEnvironmentPath({
        kind: target === 'prefix' ? 'directory' : 'executable'
      })
      if (current !== generation.current) return
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      if (!result.data.path) return
      if (target === 'launcher') setLauncher(result.data.path)
      else {
        setScope('absolute')
        if (target === 'interpreter') setInterpreter(result.data.path)
        else setPrefix(result.data.path)
      }
    } catch {
      if (current === generation.current) setError('路径选择未完成。')
    } finally {
      if (current === generation.current) setBusy(false)
    }
  }

  /** 将当前表单转为判别契约，不补造缺失路径。 Build a discriminated reference without invented paths. */
  function definition(): EnvironmentDefinition {
    if (kind === 'system') return { kind }
    if (kind === 'python') return { kind, scope, interpreter }
    if (kind === 'conda') return { kind, scope, launcher, prefix }
    return { kind, scope, launcher, interpreter }
  }

  /** 只在用户点击时检查已保存项目环境，结果不自动绑定或安装。 Inspect the saved project environment only on request. */
  async function inspectPython(): Promise<void> {
    if (!projectId || pythonBusy) return
    const current = generation.current
    setPythonBusy(true)
    setPythonError('')
    setPythonProbe(null)
    try {
      const result = await window.agent.inspectPython({ project_id: projectId })
      if (current !== generation.current) return
      if (result.ok) setPythonProbe(result.data)
      else setPythonError(result.error.message)
    } catch {
      if (current === generation.current) setPythonError('本机 Python 检查未完成。')
    } finally {
      if (current === generation.current) setPythonBusy(false)
    }
  }

  return (
    <section className="detail-card settings-card environment-settings" aria-label="项目执行环境">
      <h2>项目执行环境</h2>
      <p className="settings-hint">
        统一登记已有环境，按项目选择默认。导入不会安装或更新依赖；环境失效时不会改用全局 Python。
      </p>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {!connected ? (
        <p>等待后端连接。</p>
      ) : !catalog ? (
        <p>正在读取环境登记…</p>
      ) : (
        <>
          <div className="environment-binding">
            <h3>{projectId ? `当前项目：${projectName}` : '先选择项目，再绑定默认环境'}</h3>
            <label>
              项目默认环境
              <select
                aria-label="项目默认环境"
                value={environmentId}
                disabled={busy || !projectId}
                onChange={(event) => setEnvironmentId(event.target.value)}
              >
                <option value="">本机工具（默认，无需导入）</option>
                {catalog.environments.map((view) => (
                  <option key={view.record.environment_id} value={view.record.environment_id}>
                    {view.record.name}
                    {view.available ? '' : ' · 路径不可用'}
                  </option>
                ))}
              </select>
            </label>
            <p className="settings-hint">
              本机直接运行 · 未隔离。程序具有当前 Windows 账户的访问能力。可选沙箱尚未提供；Docker /
              WSL 管理后置。
            </p>
            <button
              disabled={busy || !projectId}
              onClick={() =>
                projectId &&
                void save(() =>
                  window.agent.bindEnvironment({
                    project_id: projectId,
                    environment_id: environmentId || null,
                    mode: 'direct',
                    expected_revision: catalog.revision
                  })
                )
              }
            >
              保存项目环境
            </button>
            <div>
              <button disabled={pythonBusy || !projectId} onClick={() => void inspectPython()}>
                {pythonBusy ? '正在检查 Python…' : '查看当前项目实际 Python'}
              </button>
              <p className="settings-hint">
                按需检查已保存的项目环境；更改选择后先保存，普通执行无需检查。
              </p>
              {pythonError && <p role="alert">{pythonError}</p>}
              {pythonProbe && (
                <p role={pythonProbe.code === 'PYTHON_READY' ? 'status' : 'alert'}>
                  {pythonProbe.code === 'PYTHON_READY' ? (
                    <>
                      Python {pythonProbe.version} · <code>{pythonProbe.interpreter}</code>
                    </>
                  ) : (
                    pythonProbe.message
                  )}
                </p>
              )}
            </div>
          </div>
          <div className="environment-list">
            {!catalog.environments.length && (
              <p>默认使用本机工具。需要特定解释器时再导入并选择。</p>
            )}
            {catalog.environments.map((view) => (
              <details key={view.record.environment_id} className="environment-item">
                <summary>
                  {view.record.name} · {view.record.definition.kind} ·{' '}
                  {view.available ? '路径可用' : '不可用'}
                </summary>
                <p>{view.issue ?? (view.record.probe?.message || '尚未执行环境检查。')}</p>
                <code>{view.interpreter ?? view.prefix ?? '使用本机 PATH 中已有工具'}</code>
                {view.launcher && (
                  <p>
                    <code>{view.launcher}</code>
                  </p>
                )}
                {view.record.probe && (
                  <p>
                    检查：
                    {view.record.probe.version ??
                      view.record.probe.launcher_version ??
                      view.record.probe.code}{' '}
                    · {view.record.probe.checked_at}
                  </p>
                )}
                <div className="settings-actions">
                  <button
                    disabled={busy}
                    onClick={() =>
                      void save(() =>
                        window.agent.probeEnvironment({
                          project_id: projectId,
                          environment_id: view.record.environment_id
                        })
                      )
                    }
                  >
                    检查此环境
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => {
                      const def = view.record.definition
                      setEditing(view.record.environment_id)
                      setName(view.record.name)
                      setKind(def.kind)
                      if (def.kind !== 'system') setScope(def.scope)
                      setInterpreter('interpreter' in def ? def.interpreter : '')
                      setLauncher('launcher' in def ? def.launcher : '')
                      setPrefix('prefix' in def ? def.prefix : '')
                    }}
                  >
                    编辑引用
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      void save(() =>
                        window.agent.removeEnvironment({
                          project_id: projectId,
                          environment_id: view.record.environment_id,
                          expected_revision: catalog.revision
                        })
                      )
                    }
                  >
                    移除登记
                  </button>
                </div>
              </details>
            ))}
          </div>
          <details className="environment-import" open>
            <summary>{editing ? '编辑环境引用' : '导入已有环境'}</summary>
            <label>
              环境名称
              <input
                aria-label="环境名称"
                value={name}
                disabled={busy}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label>
              类型
              <select
                aria-label="环境类型"
                value={kind}
                disabled={busy}
                onChange={(event) => {
                  const value = event.target.value
                  if (
                    value === 'python' ||
                    value === 'conda' ||
                    value === 'uv' ||
                    value === 'system'
                  )
                    setKind(value)
                }}
              >
                <option value="python">Python / venv</option>
                <option value="conda">Conda prefix</option>
                <option value="uv">uv + 已有 Python</option>
                <option value="system">本机工具（已有 PATH）</option>
              </select>
            </label>
            {kind !== 'system' && (
              <label>
                环境路径相对于
                <select
                  aria-label="环境路径基准"
                  value={scope}
                  disabled={busy}
                  onChange={(event) =>
                    setScope(event.target.value === 'project' ? 'project' : 'absolute')
                  }
                >
                  <option value="absolute">本机绝对位置</option>
                  <option value="project">所选项目（可移植相对路径）</option>
                </select>
              </label>
            )}
            {(kind === 'python' || kind === 'uv') && (
              <label>
                Python 解释器
                <div className="path-input">
                  <input
                    aria-label="Python 解释器"
                    value={interpreter}
                    disabled={busy}
                    onChange={(event) => setInterpreter(event.target.value)}
                    placeholder={
                      scope === 'project' ? '.venv/Scripts/python.exe' : '选择已有 python.exe'
                    }
                  />
                  <button disabled={busy} onClick={() => void pick('interpreter')}>
                    选择文件
                  </button>
                </div>
              </label>
            )}
            {(kind === 'conda' || kind === 'uv') && (
              <label>
                {kind} 入口（绝对路径）
                <div className="path-input">
                  <input
                    aria-label="环境管理器入口"
                    value={launcher}
                    disabled={busy}
                    onChange={(event) => setLauncher(event.target.value)}
                  />
                  <button disabled={busy} onClick={() => void pick('launcher')}>
                    选择入口
                  </button>
                </div>
              </label>
            )}
            {kind === 'conda' && (
              <label>
                Conda prefix
                <div className="path-input">
                  <input
                    aria-label="Conda prefix"
                    value={prefix}
                    disabled={busy}
                    onChange={(event) => setPrefix(event.target.value)}
                  />
                  <button disabled={busy} onClick={() => void pick('prefix')}>
                    选择目录
                  </button>
                </div>
              </label>
            )}
            <div className="settings-actions">
              <button
                disabled={busy || !name.trim()}
                onClick={() =>
                  void save(() =>
                    window.agent.saveEnvironment({
                      project_id: projectId,
                      expected_revision: catalog.revision,
                      environment_id: editing,
                      name: name.trim(),
                      definition: definition()
                    })
                  )
                }
              >
                {editing ? '保存环境引用' : '导入环境'}
              </button>
              {editing && (
                <button
                  disabled={busy}
                  onClick={() => {
                    setEditing(null)
                    setName('')
                  }}
                >
                  改为新登记
                </button>
              )}
            </div>
          </details>
          {limits && (
            <details>
              <summary>程序执行预算</summary>
              <p className="settings-hint">仅影响后续启动；已交付服务没有命令寿命时限。</p>
              {Object.entries(budgetLabels).map(([key, label]) => {
                const field = key as keyof ExecutionSettings
                return (
                  <label key={key}>
                    {label}
                    <input
                      aria-label={label}
                      type="number"
                      min={field === 'max_output_bytes' ? 1024 : 1}
                      step="1"
                      value={limits[field]}
                      disabled={busy}
                      onChange={(event) =>
                        setLimits({ ...limits, [field]: Number(event.target.value) })
                      }
                    />
                  </label>
                )
              })}
              <button
                disabled={
                  busy ||
                  Object.values(limits).some(
                    (value) => !Number.isSafeInteger(value) || value < 1
                  ) ||
                  limits.max_output_bytes < 1024
                }
                onClick={() =>
                  void save(() =>
                    window.agent.saveExecutionSettings({
                      project_id: projectId,
                      expected_revision: catalog.revision,
                      settings: limits
                    })
                  )
                }
              >
                保存执行预算
              </button>
            </details>
          )}
          <button
            className="text-button"
            disabled={busy}
            onClick={() =>
              void save(() => window.agent.listEnvironments({ project_id: projectId }))
            }
          >
            刷新环境状态
          </button>
          {busy && <p role="status">正在处理环境设置…</p>}
        </>
      )}
    </section>
  )
}
