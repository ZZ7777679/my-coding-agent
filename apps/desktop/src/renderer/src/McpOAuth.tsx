/** OAuth 登记表单与作业状态，不接收授权码或令牌。 OAuth setup/status never receive codes or tokens. */
import type { McpOAuthConfig, McpOAuthView, McpPreset } from '../../generated/protocol'
import { useState } from 'react'

/** 常用服务无需填写高级登记；按服务需要展开。 Reveal optional registration settings when needed. */
export function McpOAuthSetup({
  value,
  preset,
  onChange
}: {
  value: McpOAuthConfig
  preset?: McpPreset
  onChange: (value: McpOAuthConfig) => void
}) {
  const [error, setError] = useState('')
  /** 只打开服务官方登记入口，失败时保留配置。 Open official registration help without losing edits. */
  async function openSetup() {
    if (!preset?.oauth_setup_url) return
    setError('')
    try {
      const result = await window.agent.openWebUrl(preset.oauth_setup_url)
      if (!result.ok) setError(result.error.message)
    } catch {
      setError('无法打开登记说明，请稍后重试。')
    }
  }
  return (
    <section className="mcp-oauth-setup" aria-label="OAuth 配置">
      <p className="settings-hint">
        {preset?.oauth_help ||
          '由服务商网页完成登录与授权。支持自动登记的服务可直接登录；其余服务填写自己的应用身份。'}
      </p>
      {preset?.oauth_setup_url && (
        <button type="button" onClick={() => void openSetup()}>
          打开应用登记说明
        </button>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <details open={preset?.preset_id === 'github'}>
        <summary>OAuth 应用登记与权限（按需填写）</summary>
        <label>
          Client ID
          <input
            value={value.client_id ?? ''}
            placeholder="支持自动登记时留空"
            onChange={(e) => onChange({ ...value, client_id: e.target.value.trim() })}
          />
        </label>
        <label>
          Client Secret 环境变量
          <input
            value={value.client_secret_env ?? ''}
            placeholder="仅填写变量名称，例如 GITHUB_OAUTH_CLIENT_SECRET"
            onChange={(e) =>
              onChange({
                ...value,
                client_secret_env: e.target.value.trim(),
                token_auth_method: e.target.value.trim()
                  ? value.token_auth_method === 'client_secret_basic'
                    ? 'client_secret_basic'
                    : 'client_secret_post'
                  : 'none'
              })
            }
          />
        </label>
        <label>
          令牌端点认证
          <select
            value={value.token_auth_method ?? 'none'}
            onChange={(e) => {
              const method = e.target.value
              if (
                method === 'none' ||
                method === 'client_secret_post' ||
                method === 'client_secret_basic'
              )
                onChange({ ...value, token_auth_method: method })
            }}
          >
            <option value="none">公共客户端 / 无 Secret</option>
            <option value="client_secret_post">Client Secret · 表单</option>
            <option value="client_secret_basic">Client Secret · Basic</option>
          </select>
        </label>
        <label>
          授权权限 scope
          <input
            value={value.scope ?? ''}
            placeholder="留空使用服务要求的权限；多项用空格分隔"
            onChange={(e) => onChange({ ...value, scope: e.target.value })}
          />
        </label>
        <label>
          客户端元数据 URL
          <input
            value={value.client_metadata_url ?? ''}
            placeholder="可选，自己已托管的 HTTPS 元数据文档"
            onChange={(e) => onChange({ ...value, client_metadata_url: e.target.value.trim() })}
          />
        </label>
        <div className="mcp-form-row">
          <label>
            回调端口
            <input
              type="number"
              min="0"
              max="65535"
              value={value.callback_port ?? 0}
              onChange={(e) => onChange({ ...value, callback_port: Number(e.target.value) })}
            />
          </label>
          <label>
            登录等待（秒）
            <input
              type="number"
              min="1"
              value={value.login_timeout_seconds ?? 600}
              onChange={(e) =>
                onChange({ ...value, login_timeout_seconds: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <p className="settings-hint">
          回调为 http://127.0.0.1:{value.callback_port || '系统分配端口'}/oauth/callback。默认端口 0
          由系统分配；需要固定回调的服务请先登记该地址。
        </p>
      </details>
    </section>
  )
}

const labels: Record<NonNullable<McpOAuthView['status']>, string> = {
  not_logged_in: '尚未登录',
  stored: '已有本地登录',
  discovering: '正在获取授权配置',
  awaiting_user: '等待浏览器授权',
  exchanging: '正在换取令牌',
  authorized: '已登录',
  failed: '登录失败',
  cancelled: '登录已取消'
}

/** 显示真实授权阶段和控制，退出仅影响本机登录。 Show actual auth stages; logout is local only. */
export function McpOAuthStatus({
  view,
  busy,
  onLogin,
  onCancel,
  onLogout,
  onOpen
}: {
  view: McpOAuthView
  busy: boolean
  onLogin: () => void
  onCancel: () => void
  onLogout: () => void
  onOpen: (url: string) => void
}) {
  const pending = ['discovering', 'awaiting_user', 'exchanging'].includes(view.status ?? '')
  return (
    <section className="mcp-oauth-state" aria-label="OAuth 登录">
      <p role="status">OAuth · {labels[view.status ?? 'not_logged_in']}</p>
      {view.error && (
        <p className="error" role="alert">
          {view.error}
        </p>
      )}
      {view.scope && (
        <p className="settings-hint">
          {view.status === 'authorized' ? '已授权权限' : '请求权限'}：{view.scope}
        </p>
      )}
      {pending && view.redirect_uri && (
        <p className="settings-hint">本次回调：{view.redirect_uri}</p>
      )}
      <div className="mcp-actions">
        <button disabled={busy || pending} onClick={onLogin}>
          登录授权
        </button>
        {view.authorization_url && (
          <button disabled={busy} onClick={() => onOpen(view.authorization_url!)}>
            打开授权网页
          </button>
        )}
        {pending && (
          <button disabled={busy} onClick={onCancel}>
            取消登录
          </button>
        )}
        <button disabled={busy} onClick={onLogout}>
          退出本机登录
        </button>
      </div>
      <p className="settings-hint">
        密码只在服务商网页输入。退出会清除此服务的本机 OAuth
        凭据并关闭连接；服务商账户中的应用授权需在其网站撤销。
      </p>
    </section>
  )
}
