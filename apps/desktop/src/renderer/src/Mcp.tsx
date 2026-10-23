/** MCP 设置、会话连接和图片产物。 MCP settings, session connections and image artifacts. */
import { useEffect, useRef, useState } from 'react'
import type {
  McpCatalog,
  McpServer,
  McpControlParams,
  SaveMcpParams,
  McpPreset,
  ProjectSummary
} from '../../generated/protocol'
import { McpSetup } from './McpSetup'
import { McpImport } from './McpImport'
import { McpOAuthStatus } from './McpOAuth'

type McpTool = NonNullable<McpCatalog['servers'][number]['tools']>[number]

const connectionLabels: Record<string, string> = {
  not_connected: '未连接',
  connecting: '连接中',
  connected: '已连接',
  refreshing: '刷新中',
  closing: '关闭中',
  closed: '已关闭',
  failed: '连接失败',
  unsupported_execution_mode: '当前沙箱暂不支持',
  authenticating: '正在授权'
}
const transportLabels: Record<NonNullable<McpServer['transport']>, string> = {
  stdio: '本地服务',
  http: '远程 HTTP',
  sse: '远程 SSE',
  browser: '临时浏览器'
}

/** 只为展示读取对象字段，不改变服务的原始定义。 Read display fields without altering server schemas. */
function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/** 显示常见参数类型，复杂定义仍可查看原文。 Label common types while retaining complex raw schemas. */
function parameterType(value: unknown): string {
  if (!isObject(value)) return '未声明类型'
  const labels: Record<string, string> = {
    string: '文本',
    number: '数值',
    integer: '整数',
    boolean: '是 / 否',
    object: '对象',
    array: '列表',
    null: '空值'
  }
  if (typeof value.type === 'string') return labels[value.type] ?? value.type
  if (Array.isArray(value.type))
    return value.type
      .filter((t): t is string => typeof t === 'string')
      .map((t) => labels[t] ?? t)
      .join(' / ')
  const variants = value.anyOf ?? value.oneOf
  if (Array.isArray(variants)) return variants.map(parameterType).join(' / ')
  if (typeof value.$ref === 'string') return value.$ref.split('/').at(-1) || '引用类型'
  return '未声明类型'
}

/** 参数按服务定义展示；原始 JSON 只在用户展开后渲染。 Show parameter help and lazily reveal raw JSON. */
function McpToolItem({ tool }: { tool: McpTool }) {
  const [showRaw, setShowRaw] = useState(false)
  const name = typeof tool.name === 'string' ? tool.name : '未命名工具'
  const annotations = isObject(tool.annotations) ? tool.annotations : {}
  const title =
    typeof tool.title === 'string'
      ? tool.title
      : typeof annotations.title === 'string'
        ? annotations.title
        : name
  const description =
    typeof tool.description === 'string' ? tool.description : '服务未提供用途说明。'
  const schema = isObject(tool.inputSchema) ? tool.inputSchema : {}
  const properties = isObject(schema.properties) ? Object.entries(schema.properties) : []
  const required = Array.isArray(schema.required) ? schema.required : []
  return (
    <details className="mcp-tool">
      <summary>
        <span className="mcp-tool-name">
          <strong>{title}</strong>
          {title !== name && <code>{name}</code>}
        </span>
        <span className="mcp-tool-description">{description}</span>
      </summary>
      <div className="mcp-tool-body">
        <p>{description}</p>
        <h4>调用参数</h4>
        {properties.length ? (
          <dl className="mcp-parameters">
            {properties.map(([key, value]) => {
              const parameter = isObject(value) ? value : {}
              return (
                <div key={key}>
                  <dt>
                    <code>{key}</code>
                    <span className="subtle-tag">{required.includes(key) ? '必填' : '可选'}</span>
                    <span className="muted">{parameterType(value)}</span>
                  </dt>
                  <dd>
                    {typeof parameter.description === 'string' && <p>{parameter.description}</p>}
                    {Array.isArray(parameter.enum) && (
                      <p>
                        可选值：{parameter.enum.map((entry) => JSON.stringify(entry)).join('、')}
                      </p>
                    )}
                    {parameter.default !== undefined && (
                      <p>默认值：{JSON.stringify(parameter.default)}</p>
                    )}
                  </dd>
                </div>
              )
            })}
          </dl>
        ) : (
          <p className="muted">
            {schema.type === 'object' && !schema.anyOf && !schema.oneOf && !schema.$ref
              ? '没有列出的固定参数。'
              : '此工具使用复合参数定义，可展开原始定义查看。'}
          </p>
        )}
        <details className="mcp-raw" onToggle={(event) => setShowRaw(event.currentTarget.open)}>
          <summary>高级 · 原始工具定义（JSON）</summary>
          {showRaw && <pre>{JSON.stringify(tool, null, 2)}</pre>}
        </details>
      </div>
    </details>
  )
}

/** 可搜索的工具目录仅作展示，不触发调用或将全部定义送入模型。 Browse tools without invoking or injecting them. */
function McpToolCatalog({ tools, connected }: { tools: McpTool[]; connected: boolean }) {
  const [query, setQuery] = useState('')
  const search = query.trim().toLocaleLowerCase()
  const matching = tools.filter((tool) =>
    [
      tool.name,
      tool.title,
      tool.description,
      isObject(tool.annotations) ? tool.annotations.title : ''
    ].some((value) => typeof value === 'string' && value.toLocaleLowerCase().includes(search))
  )
  return (
    <section className="mcp-tools" aria-label="工具目录">
      <div className="mcp-tools-heading">
        <h3>工具目录 · {tools.length} 项</h3>
        {!!tools.length && (
          <input
            type="search"
            aria-label="搜索工具"
            placeholder="搜索名称或用途"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        )}
      </div>
      {!tools.length ? (
        <p className="muted">
          {connected
            ? '此服务当前没有提供工具；仍可能提供资源，可让 Agent 列出该服务的资源。'
            : '连接服务后可查看它提供的工具；已有连接可点击“刷新工具”。'}
        </p>
      ) : (
        <>
          <p className="settings-hint">
            展开查看参数。这里是能力说明，Agent 会按任务需要发现并使用工具。
          </p>
          {search && (
            <p className="muted">
              找到 {matching.length} / {tools.length} 项
            </p>
          )}
          {!matching.length && <p className="muted">没有匹配的工具，换个名称或用途试试。</p>}
          {tools.map((tool, index) => (
            <div
              key={typeof tool.name === 'string' ? tool.name : index}
              hidden={!matching.includes(tool)}
            >
              <McpToolItem tool={tool} />
            </div>
          ))}
        </>
      )}
    </section>
  )
}

/** 所有操作走后端；界面不启动进程或读取本地文件。 Delegate processes and files to the backend. */
export function Mcp({
  projectId,
  sessionId = null,
  projects
}: {
  projectId: string | null
  sessionId?: string | null
  projects: ProjectSummary[]
}) {
  const [catalog, setCatalog] = useState<McpCatalog | null>(null)
  const [draft, setDraft] = useState<McpServer | null>(null)
  const [importing, setImporting] = useState(false)
  const [image, setImage] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const loginToOpen = useRef<string | null>(null)
  const pending =
    !!catalog?.installing_browser ||
    !!catalog?.servers.some(
      (s) =>
        ['connecting', 'refreshing', 'closing', 'authenticating'].includes(s.status) ||
        ['discovering', 'awaiting_user', 'exchanging'].includes(s.oauth?.status ?? '')
    )
  /** 仅本页主动发起的登录自动开网页，回到页面不重复弹窗。 Open only logins initiated here, not on page revisit. */
  useEffect(() => {
    const url = catalog?.servers.find((s) => s.server.server_id === loginToOpen.current)?.oauth
      ?.authorization_url
    if (!url) return
    loginToOpen.current = null
    void openAuthorization(url)
  }, [catalog])
  /** 网页打开失败仍保留登录入口，可以再次打开。 Keep a manual link if browser opening fails. */
  async function openAuthorization(url: string) {
    try {
      const result = await window.agent.openWebUrl(url)
      if (!result.ok) setError(result.error.message)
    } catch {
      setError('未能打开系统浏览器，请使用“打开授权网页”重试。')
    }
  }
  useEffect(() => {
    let disposed = false
    void window.agent
      .listMcp({ project_id: projectId, session_id: sessionId })
      .then((r) => {
        if (!disposed) {
          if (r.ok) setCatalog(r.data)
          else setError(r.error.message)
        }
      })
      .catch(() => {
        if (!disposed) setError('MCP 目录读取失败。')
      })
    return () => {
      disposed = true
    }
  }, [projectId, sessionId])
  useEffect(() => {
    if (!pending) return
    let disposed = false
    const timer = setInterval(() => {
      void window.agent
        .listMcp({ project_id: projectId, session_id: sessionId })
        .then((r) => {
          if (!disposed && r.ok) setCatalog(r.data)
        })
        .catch(() => {
          if (!disposed) setError('服务状态读取失败，可手动刷新。')
        })
    }, 1000)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [projectId, sessionId, pending])
  /** 编辑已有身份，项目范围保持原义。 Edit an existing identity with its original project scope. */
  function edit(server: McpServer) {
    setImporting(false)
    setDraft(server)
    setError('')
    setNotice('')
    if (server.project_ids?.length) setDraft({ ...server, all_projects: false })
  }
  /** 预设只是表单初值，选择本身不保存或连接。 Presets only fill a draft without saving or connecting. */
  function addPreset(preset: McpPreset) {
    edit({
      ...preset.server,
      server_id: crypto.randomUUID(),
      project_ids: projectId ? [projectId] : [],
      all_projects: false
    })
  }
  /** 写入凭据只发送一次；保存成功后可显式连接。 Send write-only credentials once, then optionally connect. */
  async function saveDraft(
    value: Pick<
      SaveMcpParams,
      'server' | 'credential_value' | 'clear_credential' | 'connection_values'
    >,
    connect: boolean
  ) {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    const params = { project_id: projectId, session_id: sessionId }
    try {
      const saved = await window.agent.saveMcp({ ...params, ...value })
      if (!saved.ok) {
        setError(saved.error.message)
        return
      }
      setCatalog(saved.data)
      setDraft(null)
      setNotice(
        `已保存 ${value.server.name}${connect ? '，后续结果见下方服务状态。' : '。可展开服务查看配置和连接状态。'}`
      )
      if (connect) {
        const oauth =
          (value.server.transport === 'http' || value.server.transport === 'sse') &&
          value.server.auth?.source === 'oauth'
        if (oauth) loginToOpen.current = value.server.server_id
        const result = await window.agent.controlMcp({
          ...params,
          server_id: value.server.server_id,
          action: oauth ? 'oauth_login' : 'connect'
        })
        if (result.ok) setCatalog(result.data)
        else setError(result.error.message)
      }
    } catch {
      setError('服务保存或连接操作失败，请刷新状态后检查；未自动重试。')
    } finally {
      setBusy(false)
    }
  }
  /** 用户操作更新事实；失败保留编辑输入。 Explicit actions refresh facts, preserving failed drafts. */
  async function act(action: McpControlParams['action'] | 'refresh_list', serverId = '') {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      if (action === 'oauth_login') loginToOpen.current = serverId
      if (action === 'oauth_cancel' || action === 'oauth_logout') loginToOpen.current = null
      const params = { project_id: projectId, session_id: sessionId }
      const result =
        action === 'refresh_list'
          ? await window.agent.listMcp(params)
          : await window.agent.controlMcp({ ...params, server_id: serverId, action })
      if (result.ok) {
        setCatalog(result.data)
      } else setError(result.error.message)
    } catch {
      setError('操作失败；请检查 JSON 格式、服务配置或连接状态。')
    } finally {
      setBusy(false)
    }
  }
  /** 登记项目启用关系，不复制机器路径或凭据到项目。 Bind a project without writing machine settings into it. */
  async function enableForProject(server: McpServer, enable = true) {
    if (!projectId || busy) return
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.saveMcp({
        project_id: projectId,
        session_id: sessionId,
        server: {
          ...server,
          enabled: enable ? true : server.enabled,
          all_projects: false,
          project_ids: enable
            ? [...new Set([...(server.project_ids ?? []), projectId])]
            : (server.all_projects !== false && !server.project_ids?.length
                ? projects.map((project) => project.project_id)
                : (server.project_ids ?? [])
              ).filter((id) => id !== projectId)
        }
      })
      if (result.ok) setCatalog(result.data)
      else setError(result.error.message)
    } catch {
      setError('项目启用关系保存失败。')
    } finally {
      setBusy(false)
    }
  }
  /** 图片按块读取并由前端显示，不将截图视为模型视觉检查。 Load image chunks for human inspection. */
  async function viewImage(id: string) {
    if (busy) return
    setBusy(true)
    setError('')
    setImage('')
    try {
      let offset: number | null = 0
      const chunks: string[] = []
      let mime = ''
      while (offset !== null) {
        const r = await window.agent.readMcpArtifact({
          project_id: projectId,
          session_id: sessionId,
          artifact_id: id,
          offset
        })
        if (!r.ok) {
          setError(r.error.message)
          return
        }
        chunks.push(r.data.data)
        mime = r.data.mime_type
        offset = r.data.next_offset
      }
      setImage(`data:${mime};base64,${chunks.join('')}`)
    } catch {
      setError('图片读取失败。')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="detail-card settings-card mcp-manager" aria-label="MCP 资源库">
      <p className="muted">
        {sessionId ? '此会话独立连接；切换会话不会关闭浏览器。' : '这里的测试连接独立于会话连接。'}{' '}
        临时浏览器不保存登录状态，退出应用时关闭。 项目启用表示可供 Agent
        发现；连接成功表示服务可用，实际调用见会话 Trace。
      </p>
      <div className="mcp-actions">
        <button
          disabled={busy || !catalog}
          onClick={() => {
            setDraft(null)
            setImporting(true)
            setNotice('')
            setError('')
          }}
        >
          从 URL / JSON 导入
        </button>
        <span className="settings-hint">已有服务地址或 mcpServers 配置？直接粘贴即可。</span>
      </div>
      {importing && catalog && (
        <McpImport
          projectId={projectId}
          sessionId={sessionId}
          projects={projects}
          catalog={catalog}
          onSaved={setCatalog}
          onBusy={setBusy}
          onClose={() => setImporting(false)}
        />
      )}
      {!!catalog?.presets?.length && (
        <section aria-label="常用 MCP 服务">
          <h3>添加常用服务</h3>
          <div className="mcp-presets">
            {catalog.presets.map((preset) => (
              <article className="mcp-preset" key={preset.preset_id}>
                <strong>{preset.server.name}</strong>
                <p>{preset.server.description}</p>
                <p className="settings-hint">{preset.auth_help}</p>
                <button disabled={busy} onClick={() => addPreset(preset)}>
                  配置 {preset.server.name}
                </button>
              </article>
            ))}
          </div>
          <p className="settings-hint">
            选择后填写连接配置；仅添加到资源库或启用到所选项目。打开此页不会连接外部服务。
          </p>
        </section>
      )}
      <div className="mcp-actions">
        <button disabled={busy} onClick={() => void act('refresh_list')}>
          刷新状态
        </button>
        <button
          disabled={busy}
          onClick={() =>
            edit({
              server_id: crypto.randomUUID(),
              name: '新服务',
              transport: 'stdio',
              all_projects: false
            })
          }
        >
          新增服务
        </button>
      </div>
      {draft && (
        <McpSetup
          key={draft.server_id}
          server={draft}
          preset={catalog?.presets?.find((preset) => preset.preset_id === draft.preset_id)}
          projects={projects}
          busy={busy}
          credentialMessage={
            catalog?.servers.find((view) => view.server.server_id === draft.server_id)
              ?.credential_message
          }
          onSave={saveDraft}
          onCancel={() => setDraft(null)}
        />
      )}
      {notice && (
        <p className="settings-hint" role="status">
          {notice}
        </p>
      )}
      {!catalog && !error && <p className="muted">正在读取服务列表…</p>}
      {catalog?.servers.length === 0 && (
        <p className="muted">还没有登记服务，点击“新增服务”接入本地或远程 MCP。</p>
      )}
      {catalog?.installing_browser && <p>正在安装浏览器运行包…</p>}
      {catalog?.install_error && <p className="error">{catalog.install_error}</p>}
      {catalog?.issues?.map((issue) => (
        <p className="error" key={issue}>
          {issue}
        </p>
      ))}
      {catalog?.servers.map(
        ({
          server,
          status,
          error: issue,
          tools,
          credential_status,
          credential_message,
          needs_reconnect,
          oauth
        }) => (
          <details key={server.server_id} className="mcp-server">
            <summary>
              <strong>{server.name}</strong>
              <span className="subtle-tag">{transportLabels[server.transport ?? 'stdio']}</span>
              <span
                className="mcp-status"
                data-status={server.enabled === false ? 'disabled' : status}
              >
                {server.enabled === false
                  ? '已停用'
                  : (connectionLabels[status] ?? `未识别状态（${status}）`)}
              </span>
              <span className="muted">
                {tools?.length
                  ? `${tools.length} 个工具`
                  : status === 'connected'
                    ? '未提供工具'
                    : '工具待发现'}
              </span>
            </summary>
            <div className="mcp-server-body">
              {oauth && (
                <McpOAuthStatus
                  view={oauth}
                  busy={busy}
                  onLogin={() => void act('oauth_login', server.server_id)}
                  onCancel={() => void act('oauth_cancel', server.server_id)}
                  onLogout={() => void act('oauth_logout', server.server_id)}
                  onOpen={(url) => void openAuthorization(url)}
                />
              )}
              {issue && <p className="error">{issue}</p>}
              {server.description && <p className="muted">{server.description}</p>}
              {(server.transport === 'http' || server.transport === 'sse') && (
                <p className="settings-hint">{server.url}</p>
              )}
              {(server.transport === 'http' ||
                server.transport === 'sse' ||
                credential_status !== 'not_required') && (
                <p
                  className={
                    credential_status === 'missing' || credential_status === 'unavailable'
                      ? 'error'
                      : 'settings-hint'
                  }
                >
                  {status === 'connected' && credential_status === 'configured'
                    ? '此连接已通过服务握手。'
                    : credential_message}
                </p>
              )}
              {needs_reconnect && (
                <p className="settings-hint">
                  连接仍使用旧配置 / 凭据，点击“连接 / 重连”应用更新。
                </p>
              )}
              <div className="mcp-actions">
                <button
                  disabled={busy || status === 'unsupported_execution_mode'}
                  onClick={() => void act('connect', server.server_id)}
                >
                  连接 / 重连
                </button>
                <button
                  disabled={busy || status === 'unsupported_execution_mode'}
                  onClick={() => void act('refresh', server.server_id)}
                >
                  刷新工具
                </button>
                <button disabled={busy} onClick={() => void act('close', server.server_id)}>
                  关闭此连接
                </button>
              </div>
              <p className="settings-hint">
                启用范围：
                {server.project_ids?.length
                  ? server.project_ids
                      .map((id) => projects.find((p) => p.project_id === id)?.name ?? id)
                      .join('、')
                  : server.all_projects !== false
                    ? '全部项目'
                    : '仅资源库，尚未启用到项目'}
              </p>
              {projectId &&
                (server.enabled !== false &&
                (server.project_ids?.includes(projectId) ||
                  (!server.project_ids?.length && server.all_projects !== false)) ? (
                  <span>
                    <span className="subtle-tag">当前项目已启用</span>
                    <button disabled={busy} onClick={() => void enableForProject(server, false)}>
                      在当前项目停用
                    </button>
                  </span>
                ) : (
                  <button disabled={busy} onClick={() => void enableForProject(server)}>
                    在当前项目启用
                  </button>
                ))}
              <div className="mcp-actions">
                <button disabled={busy} onClick={() => edit(server)}>
                  编辑 / 启停
                </button>
                <button disabled={busy} onClick={() => void act('remove', server.server_id)}>
                  移除登记
                </button>
                {server.transport === 'browser' && (
                  <button
                    disabled={busy}
                    onClick={() => void act('install_browser', server.server_id)}
                  >
                    安装浏览器运行包
                  </button>
                )}
              </div>
              <McpToolCatalog tools={tools ?? []} connected={status === 'connected'} />
            </div>
          </details>
        )
      )}
      {!!catalog?.artifacts?.length && (
        <details>
          <summary>截图产物</summary>
          {catalog.artifacts.map((id) => (
            <button key={id} disabled={busy} onClick={() => void viewImage(id)}>
              {id}
            </button>
          ))}
        </details>
      )}
      {image && (
        <div>
          <button onClick={() => setImage('')}>关闭图片</button>
          <img className="mcp-image" src={image} alt="浏览器截图产物" />
        </div>
      )}
      {busy && <p>正在处理服务操作…</p>}
      {error && <p className="error">{error}</p>}
    </section>
  )
}
