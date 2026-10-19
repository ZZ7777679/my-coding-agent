/** 可选代码理解服务的项目配置与实际查询。 Project settings and actual queries for optional language intelligence. */
import { useEffect, useRef, useState } from 'react'
import type { LanguageServerCatalog, LanguageResult, LanguageQuery } from '../../generated/protocol'
import { EditorIntelligenceView } from './EditorIntelligenceView'

/** LSP 独立入口，缺失不影响聊天、文件或程序运行。 An independent LSP entry; absence never gates chat, files or programs. */
export function CodeIntelligence({
  projectId,
  onOpen
}: {
  projectId: string
  onOpen?: (path: string, line: number, column: number) => void
}) {
  const [catalog, setCatalog] = useState<LanguageServerCatalog | null>(null)
  const [path, setPath] = useState('')
  const [language, setLanguage] = useState('python')
  const [action, setAction] = useState<LanguageQuery['action']>('definition')
  const [line, setLine] = useState(1)
  const [column, setColumn] = useState(1)
  const [newName, setNewName] = useState('')
  const [result, setResult] = useState<LanguageResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [projectRoot, setProjectRoot] = useState('')
  const generation = useRef(0)
  const identity = useRef(projectId)
  identity.current = projectId
  useEffect(() => {
    ++generation.current
    setResult(null)
    setBusy(false)
  }, [path, language, action, line, column, newName])
  useEffect(() => {
    let disposed = false
    ++generation.current
    setResult(null)
    setBusy(false)
    void window.agent
      .listProjects()
      .then((r) => {
        if (!disposed && r.ok)
          setProjectRoot(
            (
              r.data.recent_projects.find((item) => item.project_id === projectId) ??
              (r.data.active_project?.project_id === projectId ? r.data.active_project : null)
            )?.canonical_path ?? ''
          )
      })
      .catch(() => {
        if (!disposed) setError('项目资料读取失败。')
      })
    void window.agent.getLanguageServers({ project_id: projectId }).then((r) => {
      if (!disposed) {
        if (r.ok) setCatalog(r.data)
        else setError(r.error.message)
      }
    })
    return () => {
      disposed = true
      ++generation.current
    }
  }, [projectId])
  /** 服务命令由用户明确保存，不自动安装依赖。 Explicitly save server commands without installing dependencies. */
  const save = async () => {
    if (!catalog) return
    const r = await window.agent.saveLanguageServers({
      project_id: projectId,
      servers: catalog.servers,
      timeout_seconds: catalog.timeout_seconds
    })
    if (identity.current !== projectId) return
    if (r.ok) {
      setCatalog(r.data)
      setError('')
    } else setError(r.error.message)
  }
  /** 以零基 UTF-16 位置查询磁盘，公开显示准确来源。 Query disk using zero-based UTF-16 positions and display provenance. */
  const query = async () => {
    const ticket = ++generation.current
    setBusy(true)
    setError('')
    try {
      const r = await window.agent.queryLanguage({
        project_id: projectId,
        path,
        language,
        action,
        line: Math.max(0, line - 1),
        character: Math.max(0, column - 1),
        new_name: action === 'rename' ? newName : null,
        content: null
      })
      if (identity.current !== projectId || ticket !== generation.current) return
      if (r.ok) setResult(r.data)
      else setError(r.error.message)
    } catch {
      if (identity.current === projectId && ticket === generation.current)
        setError('代码理解请求未完成。')
    } finally {
      if (identity.current === projectId && ticket === generation.current) setBusy(false)
    }
  }
  return (
    <section className="code-intelligence">
      <h2>代码理解</h2>
      <p className="muted">
        语言服务按需启动；缺失或失败不阻断普通编码。返回的重命名建议可在编辑器审阅并保存。
      </p>
      <details>
        <summary>项目语言服务设置</summary>
        {catalog?.servers.map((s, index) => (
          <fieldset key={s.server_id}>
            <legend>
              {s.server_id} ·{' '}
              {catalog.states?.find((i) => i.server_id === s.server_id)?.status ?? 'not_started'}
            </legend>
            <label>
              <input
                type="checkbox"
                checked={s.enabled ?? true}
                onChange={(e) =>
                  setCatalog({
                    ...catalog,
                    servers: catalog.servers.map((old, i) =>
                      i === index ? { ...old, enabled: e.target.checked } : old
                    )
                  })
                }
              />
              启用
            </label>
            <label>
              程序
              <input
                value={s.program}
                onChange={(e) =>
                  setCatalog({
                    ...catalog,
                    servers: catalog.servers.map((old, i) =>
                      i === index ? { ...old, program: e.target.value } : old
                    )
                  })
                }
              />
            </label>
            <label>
              参数（每行一项）
              <textarea
                value={(s.arguments ?? []).join('\n')}
                onChange={(e) =>
                  setCatalog({
                    ...catalog,
                    servers: catalog.servers.map((old, i) =>
                      i === index
                        ? { ...old, arguments: e.target.value.split('\n').filter(Boolean) }
                        : old
                    )
                  })
                }
              />
            </label>
            <label>
              语言（逗号分隔）
              <input
                value={s.languages.join(',')}
                onChange={(e) =>
                  setCatalog({
                    ...catalog,
                    servers: catalog.servers.map((old, i) =>
                      i === index
                        ? {
                            ...old,
                            languages: e.target.value
                              .split(',')
                              .map((v) => v.trim())
                              .filter(Boolean)
                          }
                        : old
                    )
                  })
                }
              />
            </label>
          </fieldset>
        ))}
        <button
          onClick={() => {
            if (catalog)
              setCatalog({
                ...catalog,
                servers: [
                  ...catalog.servers,
                  {
                    server_id: crypto.randomUUID(),
                    program: '',
                    languages: ['python'],
                    arguments: [],
                    enabled: true
                  }
                ]
              })
          }}
        >
          登记其他标准服务
        </button>
        <button disabled={busy || !catalog} onClick={() => void save()}>
          保存设置
        </button>
      </details>
      <label>
        项目文件
        <input aria-label="LSP文件路径" value={path} onChange={(e) => setPath(e.target.value)} />
      </label>
      <select aria-label="查询语言" value={language} onChange={(e) => setLanguage(e.target.value)}>
        {['python', 'typescript', 'javascript', 'typescriptreact', 'javascriptreact'].map((v) => (
          <option key={v}>{v}</option>
        ))}
      </select>
      <select
        aria-label="代码查询"
        value={action}
        onChange={(e) => {
          const v = e.target.value
          if (
            v === 'definition' ||
            v === 'references' ||
            v === 'symbols' ||
            v === 'hover' ||
            v === 'diagnostics' ||
            v === 'completion' ||
            v === 'rename'
          )
            setAction(v)
        }}
      >
        {[
          ['definition', '定义'],
          ['references', '引用'],
          ['symbols', '符号'],
          ['hover', '说明'],
          ['diagnostics', '诊断'],
          ['completion', '补全'],
          ['rename', '重命名建议']
        ].map(([v, name]) => (
          <option key={v} value={v}>
            {name}
          </option>
        ))}
      </select>
      <label>
        行
        <input
          type="number"
          min={1}
          value={line}
          onChange={(e) => setLine(Number(e.target.value))}
        />
      </label>
      <label>
        列
        <input
          type="number"
          min={1}
          value={column}
          onChange={(e) => setColumn(Number(e.target.value))}
        />
      </label>
      {action === 'rename' && (
        <input
          aria-label="新符号名称"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
      )}
      <button disabled={busy || !path} onClick={() => void query()}>
        {busy ? '查询中…' : '查询'}
      </button>
      {error && <p role="alert">{error}</p>}
      {result && (
        <details open>
          <summary>
            {result.server_id} · {result.source === 'draft' ? '未保存草稿' : '磁盘'} · 版本{' '}
            {result.version}
            <button
              onClick={() => {
                ++generation.current
                setResult(null)
                setBusy(false)
              }}
            >
              关闭结果
            </button>
          </summary>
          <EditorIntelligenceView result={result} projectRoot={projectRoot} onNavigate={onOpen} />
        </details>
      )}
    </section>
  )
}
