import { useEffect, useRef, useState } from 'react'
import type { McpCatalog, ProjectSummary } from '../../generated/protocol'
import { mcpImportUrl, parseMcpImport, type McpImportEntry } from './mcpImportDraft'

/** 预览并逐项导入本地与远程配置，仍由原 RPC 保存与加密。 Preview local and remote imports using the existing RPC writer and encryption. */
export function McpImport({
  projectId,
  sessionId,
  projects,
  catalog,
  onSaved,
  onBusy,
  onClose
}: {
  projectId: string | null
  sessionId: string | null
  projects: ProjectSummary[]
  catalog: McpCatalog
  onSaved: (catalog: McpCatalog) => void
  onBusy: (busy: boolean) => void
  onClose: () => void
}) {
  const [text, setText] = useState('')
  const [entries, setEntries] = useState<McpImportEntry[]>([])
  const [scope, setScope] = useState(projectId ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  /** 识别完成后清空含秘密的原始文本，令牌仅留在密码草稿中。 Clear raw pasted secrets after preview; keep only password drafts. */
  function preview() {
    try {
      const result = parseMcpImport(text)
      setEntries(result)
      if (result.every((entry) => !entry.error)) setText('')
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法识别输入。')
    }
  }

  /** 更新指定草稿而不改已保存服务。 Update one draft without changing saved services. */
  function change(id: string, update: Partial<McpImportEntry>) {
    setEntries((rows) =>
      rows.map((row) => (row.server.server_id === id ? { ...row, ...update } : row))
    )
  }

  /** 保留逐项结果；失败后只重试未保存项，离页不再发起余下保存。 Retain per-item outcomes; retry unsaved items and stop dispatch on unmount. */
  async function save() {
    if (busy) return
    setBusy(true)
    onBusy(true)
    setError('')
    try {
      for (const entry of entries.filter((row) => row.selected && !row.saved)) {
        if (!alive.current) break
        let url: string
        try {
          url = entry.server.transport === 'stdio' ? '' : mcpImportUrl(entry.server.url)
        } catch (cause) {
          change(entry.server.server_id, {
            error: cause instanceof Error ? cause.message : '地址格式无效。'
          })
          continue
        }
        try {
          const server = {
            ...entry.server,
            url,
            all_projects: scope === '*',
            project_ids: scope && scope !== '*' ? [scope] : []
          }
          const result = await window.agent.saveMcp({
            project_id: projectId,
            session_id: sessionId,
            server,
            connection_values: entry.connectionValues,
            credential_value: server.auth?.source === 'saved' ? entry.credential : null
          })
          if (!alive.current) break
          if (result.ok) {
            change(server.server_id, {
              saved: true,
              credential: '',
              connectionValues: {},
              error: ''
            })
            onSaved(result.data)
          } else
            change(server.server_id, { error: `${result.error.code}：${result.error.message}` })
        } catch {
          if (!alive.current) break
          // 通信中断可能发生在写入之后；不要声称没有保存或自动重放。
          // A transport failure may follow a write; do not claim rollback or auto-replay.
          change(entry.server.server_id, {
            error: '保存未完成或结果未知，请刷新列表核对后再试。'
          })
          break
        }
      }
    } finally {
      if (alive.current) {
        setBusy(false)
        onBusy(false)
      }
    }
  }

  const remaining = entries.filter((entry) => entry.selected && !entry.saved)
  return (
    <section className="mcp-setup mcp-import" aria-label="导入 MCP">
      <h3>从 URL / JSON 导入</h3>
      <p className="settings-hint">
        粘贴服务 URL 或 mcpServers／servers JSON，支持本地 stdio、Streamable HTTP 和
        SSE。先预览，保存后可测试连接。
      </p>
      {(!entries.length || text) && (
        <>
          <label>
            URL 或 JSON
            <textarea
              rows={6}
              spellCheck={false}
              value={text}
              disabled={busy}
              onChange={(event) => setText(event.target.value)}
              placeholder={'https://example.com/mcp 或 { "mcpServers": { … } }'}
            />
          </label>
          <button disabled={busy || !text.trim()} onClick={preview}>
            识别并预览
          </button>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!!entries.length && (
        <>
          <label>
            启用范围
            <select
              aria-label="启用范围"
              value={scope}
              disabled={busy || entries.some((entry) => entry.saved)}
              onChange={(event) => setScope(event.target.value)}
            >
              <option value="">仅加入资源库</option>
              {projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.name}
                </option>
              ))}
              <option value="*">所有项目</option>
            </select>
          </label>
          {entries.map((entry) => (
            <article
              key={entry.server.server_id}
              className="mcp-import-entry"
              aria-label={`导入 ${entry.server.name}`}
            >
              <label className="mcp-checkbox">
                <input
                  type="checkbox"
                  checked={entry.selected}
                  disabled={busy || entry.saved || !entry.parsed}
                  onChange={(event) =>
                    change(entry.server.server_id, { selected: event.target.checked })
                  }
                />
                <strong>{entry.server.name}</strong> ·{' '}
                {entry.saved
                  ? '已导入'
                  : !entry.parsed
                    ? '未识别'
                    : entry.server.transport === 'stdio'
                      ? '本地 stdio'
                      : entry.server.transport === 'sse'
                        ? '远程 SSE'
                        : '远程 Streamable HTTP'}
              </label>
              {entry.error && (
                <p className="error" role="alert">
                  {entry.error}
                </p>
              )}
              {entry.selected && !entry.saved && (
                <>
                  <div className="mcp-form-row">
                    <label>
                      服务名称
                      <input
                        value={entry.server.name}
                        disabled={busy}
                        onChange={(event) =>
                          change(entry.server.server_id, {
                            server: { ...entry.server, name: event.target.value }
                          })
                        }
                      />
                    </label>
                    {entry.server.transport !== 'stdio' && (
                      <label>
                        服务地址
                        <input
                          value={entry.server.url ?? ''}
                          disabled={busy}
                          onChange={(event) =>
                            change(entry.server.server_id, {
                              server: { ...entry.server, url: event.target.value }
                            })
                          }
                        />
                      </label>
                    )}
                    {entry.server.transport !== 'stdio' && (
                      <label>
                        连接方式
                        <select
                          aria-label="导入连接方式"
                          value={entry.server.transport}
                          disabled={busy}
                          onChange={(event) => {
                            if (event.target.value === 'http' || event.target.value === 'sse')
                              change(entry.server.server_id, {
                                server: { ...entry.server, transport: event.target.value }
                              })
                          }}
                        >
                          <option value="http">Streamable HTTP</option>
                          <option value="sse">旧式 HTTP + SSE</option>
                        </select>
                      </label>
                    )}
                  </div>
                  {entry.server.transport === 'stdio' && (
                    <>
                      <label>
                        程序路径
                        <input
                          value={entry.server.command ?? ''}
                          disabled={busy}
                          onChange={(event) =>
                            change(entry.server.server_id, {
                              server: { ...entry.server, command: event.target.value }
                            })
                          }
                        />
                      </label>
                      <p className="settings-hint">
                        启动参数：<code>{JSON.stringify(entry.server.arguments ?? [])}</code>
                      </p>
                      <p className="settings-hint">
                        工作目录：{entry.server.cwd || '所选项目目录；未选项目时为应用数据根'}
                      </p>
                    </>
                  )}
                  {entry.server.transport !== 'stdio' &&
                    (entry.server.auth?.source === 'saved' ||
                      entry.server.auth?.source === 'none') && (
                      <label>
                        {entry.server.auth?.source === 'saved'
                          ? `服务令牌（${entry.server.auth.header} ${entry.server.auth.prefix ?? ''}）`
                          : '服务令牌（可选，Bearer）'}
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={entry.credential}
                          disabled={busy}
                          onChange={(event) =>
                            change(entry.server.server_id, {
                              credential: event.target.value,
                              server: {
                                ...entry.server,
                                auth: {
                                  source: event.target.value ? 'saved' : 'none',
                                  header: entry.server.auth?.header ?? 'Authorization',
                                  prefix: entry.server.auth?.prefix ?? 'Bearer'
                                }
                              }
                            })
                          }
                        />
                      </label>
                    )}
                  {(['env', 'headers'] as const).map((kind) =>
                    Object.entries(entry.connectionValues[kind] ?? {}).map(([name, value]) => (
                      <label key={`${kind}:${name}`}>
                        {kind === 'env' ? '环境变量' : '请求头'} {name}（加密保存）
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={value}
                          disabled={busy}
                          onChange={(event) =>
                            change(entry.server.server_id, {
                              connectionValues: {
                                ...entry.connectionValues,
                                [kind]: {
                                  ...entry.connectionValues[kind],
                                  [name]: event.target.value
                                }
                              }
                            })
                          }
                        />
                      </label>
                    ))
                  )}
                  {Object.keys(entry.server.env_refs ?? {}).length > 0 && (
                    <p className="settings-hint">
                      环境变量引用：{Object.keys(entry.server.env_refs ?? {}).join('、')}
                      （启动时读取）
                    </p>
                  )}
                  <p className="settings-hint">
                    协议默认自动兼容新旧服务；需要时可在导入后的高级连接选项中选择旧版握手。
                  </p>
                  <p className="settings-hint">
                    {entry.server.enabled === false ? '导入后停用' : '导入后启用'}
                    {entry.server.timeout_seconds !== undefined
                      ? ` · 调用超时 ${entry.server.timeout_seconds} 秒`
                      : ''}
                  </p>
                  <p className="settings-hint">
                    {entry.server.auth?.source === 'environment'
                      ? `认证使用环境变量 ${entry.server.auth.env_var}。`
                      : '令牌通过 Windows 加密保存，不写入普通配置或项目；示例 xxx 需换成服务商令牌。'}
                  </p>
                  {Object.keys(entry.server.header_refs ?? {}).length > 0 && (
                    <p className="settings-hint">
                      请求头环境引用：{Object.keys(entry.server.header_refs ?? {}).join('、')}
                      （连接时读取）
                    </p>
                  )}
                  {Object.keys(entry.server.headers ?? {}).length > 0 && (
                    <p className="settings-hint">
                      附加配置头：{Object.keys(entry.server.headers ?? {}).join('、')}
                    </p>
                  )}
                  {catalog.servers.some((view) => view.server.name === entry.server.name) && (
                    <p className="settings-hint">已有同名服务；本次新建独立登记，不覆盖原服务。</p>
                  )}
                </>
              )}
            </article>
          ))}
          <p className="settings-hint" role="status">
            已导入 {entries.filter((entry) => entry.saved).length}{' '}
            项。保存不自动连接；在下方服务卡片点“连接 / 重连”。
          </p>
        </>
      )}
      <div className="mcp-actions">
        {!!entries.length && (
          <button disabled={busy || !remaining.length} onClick={() => void save()}>
            {busy ? '正在导入…' : `导入所选 ${remaining.length} 项`}
          </button>
        )}
        {!!entries.length && (
          <button
            disabled={busy}
            onClick={() => {
              setEntries([])
              setError('')
            }}
          >
            重新粘贴
          </button>
        )}
        <button disabled={busy} onClick={onClose}>
          关闭导入
        </button>
      </div>
    </section>
  )
}
