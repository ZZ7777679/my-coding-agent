/** MCP 连接表单；秘密仅作为写入参数发送，不从后端读回。
 * MCP setup sends tokens as write-only inputs and never reads them back.
 */
import { useState } from 'react'
import type { McpPreset, McpServer, ProjectSummary, SaveMcpParams } from '../../generated/protocol'
import { McpOAuthSetup } from './McpOAuth'

type SetupValue = Pick<
  SaveMcpParams,
  'server' | 'credential_value' | 'clear_credential' | 'connection_values'
>

/** 解析旧配置的引用字段，错误只显示说明。 Parse legacy reference fields with a fixed error message. */
function stringMap(text: string): Record<string, string> {
  const value: unknown = JSON.parse(text)
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Expected object')
  const result: Record<string, string> = {}
  for (const [name, entry] of Object.entries(value)) {
    if (typeof entry !== 'string') throw new Error('Expected string')
    result[name] = entry
  }
  return result
}

/** 编辑当前服务快照，提交成功后由父组件关闭。 Edit a server snapshot and close after confirmed saving. */
export function McpSetup({
  server,
  preset,
  projects,
  busy,
  credentialMessage,
  onSave,
  onCancel
}: {
  server: McpServer
  preset?: McpPreset
  projects: ProjectSummary[]
  busy: boolean
  credentialMessage?: string
  onSave: (value: SetupValue, connect: boolean) => Promise<void>
  onCancel: () => void
}) {
  const [draft, setDraft] = useState(server)
  const [argumentsText, setArgumentsText] = useState((server.arguments ?? []).join('\n'))
  const [envRefs, setEnvRefs] = useState(JSON.stringify(server.env_refs ?? {}, null, 2))
  const [headerRefs, setHeaderRefs] = useState(JSON.stringify(server.header_refs ?? {}, null, 2))
  const [headers, setHeaders] = useState(JSON.stringify(server.headers ?? {}, null, 2))
  const [token, setToken] = useState('')
  const [clearToken, setClearToken] = useState(false)
  const [error, setError] = useState('')
  const [connectionValues, setConnectionValues] = useState<
    NonNullable<SaveMcpParams['connection_values']>
  >({})
  const remote = draft.transport === 'http' || draft.transport === 'sse'
  const auth = draft.auth
  let selectedToolsets: string[] = []
  try {
    selectedToolsets = (stringMap(headers)['X-MCP-Toolsets'] ?? '').split(',')
  } catch {
    // 高级文本可能正在编辑，保存时再说明错误。 In-progress advanced text is checked on save.
  }

  /** 工具组只是请求头配置，保留用户输入的其他组。 Toolset selection preserves other configured groups. */
  function toggleToolset(name: string, checked: boolean) {
    try {
      const values = stringMap(headers)
      const names = selectedToolsets.filter((value) => value && value !== name)
      if (checked) names.push(name)
      if (names.length) values['X-MCP-Toolsets'] = names.join(',')
      else delete values['X-MCP-Toolsets']
      setHeaders(JSON.stringify(values, null, 2))
      setError('')
    } catch {
      setError('请先修正高级选项中的 HTTP 配置头 JSON。')
    }
  }

  /** 只保存显式表单；空令牌保留已保存值。 Save explicit fields; a blank token keeps the stored value. */
  async function submit(connect: boolean) {
    setError('')
    let values: SetupValue
    try {
      values = {
        server: {
          ...draft,
          arguments:
            argumentsText === (server.arguments ?? []).join('\n')
              ? (server.arguments ?? [])
              : argumentsText
                ? argumentsText.split(/\r?\n/)
                : [],
          env_refs: stringMap(envRefs),
          header_refs: stringMap(headerRefs),
          headers: stringMap(headers),
          project_ids: draft.all_projects ? [] : (draft.project_ids ?? [])
        },
        credential_value: auth?.source === 'saved' && token.trim() ? token.trim() : null,
        clear_credential: clearToken && !token.trim(),
        connection_values: connectionValues
      }
    } catch {
      setError('高级引用和配置头应为 JSON 对象，键和值均为文本。')
      return
    }
    await onSave(values, connect)
  }

  /** 打开官方说明，不把网页访问当作认证成功。 Open official help without claiming authentication. */
  async function openHelp(url: string) {
    try {
      const result = await window.agent.openWebUrl(url)
      if (!result.ok) setError(result.error.message)
    } catch {
      setError('无法打开官方页面，请稍后重试。')
    }
  }

  return (
    <fieldset className="mcp-setup" disabled={busy}>
      <legend>服务配置 · {server.name}</legend>
      {preset && <p className="muted">{preset.auth_help}</p>}
      <label>
        名称
        <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </label>
      <label>
        用途说明
        <input
          value={draft.description ?? ''}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        />
      </label>
      <div className="mcp-form-row">
        <label>
          连接方式
          <select
            value={draft.transport ?? 'stdio'}
            onChange={(e) => {
              const transport = e.target.value
              if (
                transport === 'http' ||
                transport === 'sse' ||
                transport === 'stdio' ||
                transport === 'browser'
              )
                setDraft({ ...draft, transport })
            }}
          >
            <option value="http">远程 HTTP</option>
            <option value="sse">远程 SSE（旧式服务）</option>
            <option value="stdio">本地 stdio</option>
            <option value="browser">临时浏览器</option>
          </select>
        </label>
        <label>
          调用超时（秒）
          <input
            type="number"
            value={draft.timeout_seconds ?? 120}
            onChange={(e) => setDraft({ ...draft, timeout_seconds: Number(e.target.value) })}
          />
        </label>
      </div>
      {remote ? (
        <>
          <label>
            服务地址
            <input
              value={draft.url ?? ''}
              onChange={(e) => setDraft({ ...draft, url: e.target.value })}
            />
          </label>
          <label>
            认证方式
            <select
              value={auth?.source ?? 'none'}
              onChange={(e) => {
                const source = e.target.value
                if (
                  source === 'none' ||
                  source === 'environment' ||
                  source === 'saved' ||
                  source === 'oauth'
                ) {
                  const presetAddress = source === 'oauth' ? preset?.oauth_url : preset?.server.url
                  const usesPresetAddress =
                    draft.url === preset?.server.url || draft.url === preset?.oauth_url
                  setDraft({
                    ...draft,
                    url: usesPresetAddress && presetAddress ? presetAddress : draft.url,
                    auth: { ...auth, source, env_var: auth?.env_var || preset?.suggested_env || '' }
                  })
                  setToken('')
                }
              }}
            >
              <option value="none">无需认证 / 匿名访问</option>
              <option value="saved">在本机加密保存令牌</option>
              <option value="environment">引用环境变量</option>
              <option value="oauth">OAuth · 浏览器登录</option>
            </select>
          </label>
          {auth?.source === 'oauth' && (
            <McpOAuthSetup
              value={auth.oauth ?? {}}
              preset={preset}
              onChange={(oauth) => setDraft({ ...draft, auth: { ...auth, oauth } })}
            />
          )}
          {auth?.source === 'environment' && (
            <label>
              凭据环境变量
              <input
                value={auth.env_var ?? ''}
                placeholder={preset?.suggested_env ?? 'MY_MCP_TOKEN'}
                onChange={(e) => setDraft({ ...draft, auth: { ...auth, env_var: e.target.value } })}
              />
            </label>
          )}
          {auth?.source === 'saved' && (
            <>
              <label>
                服务令牌
                <input
                  type="password"
                  autoComplete="new-password"
                  value={token}
                  placeholder="输入新令牌；留空保留已有值"
                  onChange={(e) => {
                    setToken(e.target.value)
                    setClearToken(false)
                  }}
                />
              </label>
              <p className="settings-hint">
                使用当前 Windows 用户加密，保存在应用数据目录；不会复制到项目或发给模型。
              </p>
              <label className="mcp-checkbox">
                <input
                  type="checkbox"
                  checked={clearToken}
                  onChange={(e) => {
                    setClearToken(e.target.checked)
                    if (e.target.checked) setToken('')
                  }}
                />
                清除已保存令牌
              </label>
            </>
          )}
          {credentialMessage && <p className="settings-hint">{credentialMessage}</p>}
          {preset && (
            <div className="mcp-actions">
              <button type="button" onClick={() => void openHelp(preset.credential_url)}>
                获取服务凭据
              </button>
              <button type="button" onClick={() => void openHelp(preset.docs_url)}>
                官方接入说明
              </button>
            </div>
          )}
          {!!preset?.toolsets?.length && (
            <fieldset>
              <legend>GitHub 工具组</legend>
              <div className="mcp-toolsets">
                {preset.toolsets.map((group) => (
                  <label className="mcp-checkbox" key={group.name}>
                    <input
                      type="checkbox"
                      checked={selectedToolsets.includes(group.name)}
                      onChange={(e) => toggleToolset(group.name, e.target.checked)}
                    />
                    {group.title}
                  </label>
                ))}
              </div>
              <p className="settings-hint">
                未指定时使用服务默认组；实际可用能力由账户权限和工具发现结果决定。
              </p>
            </fieldset>
          )}
        </>
      ) : (
        <>
          <label>
            {draft.transport === 'browser' ? 'Node 路径（留空自动定位）' : '程序路径'}
            <input
              value={draft.command ?? ''}
              onChange={(e) => setDraft({ ...draft, command: e.target.value })}
            />
          </label>
          {draft.transport === 'browser' ? (
            <label>
              浏览器程序（留空使用已安装的运行包）
              <input
                value={draft.browser_executable ?? ''}
                onChange={(e) => setDraft({ ...draft, browser_executable: e.target.value })}
              />
            </label>
          ) : (
            <label>
              启动参数（每行一项）
              <textarea value={argumentsText} onChange={(e) => setArgumentsText(e.target.value)} />
            </label>
          )}
        </>
      )}
      <fieldset>
        <legend>项目启用范围</legend>
        <label className="mcp-checkbox">
          <input
            type="checkbox"
            checked={draft.all_projects !== false}
            onChange={(e) => setDraft({ ...draft, all_projects: e.target.checked })}
          />
          全部项目
        </label>
        {draft.all_projects === false &&
          projects.map((project) => (
            <label className="mcp-checkbox" key={project.project_id}>
              <input
                type="checkbox"
                checked={draft.project_ids?.includes(project.project_id) ?? false}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    project_ids: e.target.checked
                      ? [...(draft.project_ids ?? []), project.project_id]
                      : (draft.project_ids ?? []).filter((id) => id !== project.project_id)
                  })
                }
              />
              {project.name}
            </label>
          ))}
        <p className="settings-hint">未选择时仅保留在资源库，可以先测试，再启用到项目。</p>
      </fieldset>
      <label className="mcp-checkbox">
        <input
          type="checkbox"
          checked={draft.enabled !== false}
          onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
        />
        启用服务
      </label>
      <details className="mcp-advanced">
        <summary>高级连接选项</summary>
        <label>
          协议兼容方式
          <select
            aria-label="协议兼容方式"
            value={draft.protocol_mode ?? 'auto'}
            onChange={(event) => {
              if (event.target.value === 'auto' || event.target.value === 'legacy')
                setDraft({ ...draft, protocol_mode: event.target.value })
            }}
          >
            <option value="auto">自动协商（推荐）</option>
            <option value="legacy">旧版 initialize 握手</option>
          </select>
        </label>
        {!remote && (
          <label>
            工作目录（留空跟随项目）
            <input
              value={draft.cwd ?? ''}
              onChange={(event) => setDraft({ ...draft, cwd: event.target.value })}
            />
          </label>
        )}
        {(['env', 'headers'] as const).map((kind) =>
          (kind === 'env' ? draft.stored_env : draft.stored_headers)?.map((name) => (
            <div className="mcp-form-row" key={`${kind}:${name}`}>
              <label>
                {kind === 'env' ? '已保存环境变量' : '已保存请求头'} {name}
                <input
                  type="password"
                  autoComplete="new-password"
                  placeholder="留空保留原值"
                  value={connectionValues[kind]?.[name] ?? ''}
                  onChange={(event) => {
                    const values: Record<string, string> = { ...connectionValues[kind] }
                    if (event.target.value) values[name] = event.target.value
                    else delete values[name]
                    setConnectionValues({ ...connectionValues, [kind]: values })
                  }}
                />
              </label>
              <button
                type="button"
                onClick={() =>
                  setDraft({
                    ...draft,
                    [kind === 'env' ? 'stored_env' : 'stored_headers']: (kind === 'env'
                      ? draft.stored_env
                      : draft.stored_headers
                    )?.filter((key) => key !== name)
                  })
                }
              >
                移除 {name}
              </button>
            </div>
          ))
        )}
        <p className="muted">
          服务身份：<code>{draft.server_id}</code>
        </p>
        {remote && (
          <>
            {auth?.source !== 'oauth' && (
              <div className="mcp-form-row">
                <label>
                  认证头名称
                  <input
                    value={auth?.header ?? 'Authorization'}
                    onChange={(e) =>
                      setDraft({ ...draft, auth: { ...auth, header: e.target.value } })
                    }
                  />
                </label>
                <label>
                  认证前缀（留空直接使用令牌）
                  <input
                    value={auth?.prefix ?? 'Bearer'}
                    onChange={(e) =>
                      setDraft({ ...draft, auth: { ...auth, prefix: e.target.value } })
                    }
                  />
                </label>
              </div>
            )}
            <label>
              HTTP 配置头 JSON（非秘密）
              <textarea value={headers} onChange={(e) => setHeaders(e.target.value)} />
            </label>
            <label>
              HTTP 头引用 JSON（头名 → 本机变量名）
              <textarea value={headerRefs} onChange={(e) => setHeaderRefs(e.target.value)} />
            </label>
            <p className="settings-hint">
              旧引用按环境变量原值发送；OAuth 模式由专用认证管理 Authorization 头。
            </p>
          </>
        )}
        {!remote && (
          <label>
            环境变量引用 JSON（变量名 → 本机变量名）
            <textarea value={envRefs} onChange={(e) => setEnvRefs(e.target.value)} />
          </label>
        )}
      </details>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="mcp-actions">
        <button type="button" onClick={() => void submit(true)}>
          {auth?.source === 'oauth' && remote ? '保存并登录' : '保存并测试连接'}
        </button>
        <button type="button" onClick={() => void submit(false)}>
          保存配置
        </button>
        <button type="button" onClick={onCancel}>
          取消编辑
        </button>
      </div>
      <p className="settings-hint">测试仅连接服务并查询工具目录；配置更新后已有连接可手动重连。</p>
    </fieldset>
  )
}
