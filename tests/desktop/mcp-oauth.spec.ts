/** 本地服务走完整桌面 OAuth，系统浏览器入口仅替换为样本同意页。 Test desktop OAuth with fixture consent. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, python, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { once } from 'node:events'
import path from 'node:path'

test('MCP OAuth login, reconnect, cancellation and local logout', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-mcp-oauth-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  const peer = spawn(python, ['-X', 'utf8', '-m', 'tests.support.mcp_oauth_fixture'], {
    cwd: path.resolve(__dirname, '../..'),
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  })
  const exited = once(peer, 'exit')
  peer.stderr?.resume()
  const lines = createInterface({ input: peer.stdout! })
  const url = await Promise.race([
    once(lines, 'line').then(([value]) => String(value)),
    exited.then(() => {
      throw new Error('OAuth fixture did not start')
    })
  ])
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  let app: Awaited<ReturnType<typeof electron.launch>> | null = null
  try {
    app = await electron.launch({
      args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', data],
      env
    })
    await app.evaluate(({ shell }) => {
      shell.openExternal = async (address) => {
        const target = new URL(address)
        if (target.hostname !== '127.0.0.1') throw new Error('Expected isolated OAuth fixture')
        target.pathname = '/approve'
        const result = await fetch(target)
        if (!result.ok) throw new Error('Fixture consent failed')
      }
    })
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    let mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    await mcp.getByRole('button', { name: '配置 Context7 文档', exact: true }).click()
    await mcp.getByRole('combobox', { name: '认证方式', exact: true }).selectOption('oauth')
    await expect(mcp.getByLabel('服务地址', { exact: true })).toHaveValue(
      'https://mcp.context7.com/mcp/oauth'
    )
    await mcp.getByLabel('服务地址', { exact: true }).fill(url + '/mcp')
    await mcp.getByLabel('名称', { exact: true }).fill('OAuth 本地样本')
    await mcp.getByRole('button', { name: '保存并登录', exact: true }).click()
    let card = mcp.locator('.mcp-server').filter({ hasText: 'OAuth 本地样本' })
    await card.locator(':scope > summary').click()
    await expect(card.locator('.mcp-status')).toHaveText('已连接')
    await expect(card.getByRole('status')).toHaveText('OAuth · 已登录')
    await expect(card.locator('.mcp-tool')).toHaveCount(1)
    await page.screenshot({ path: path.join(root, 'authorized.png') })
    const config = await readFile(path.join(data, 'mcp.json'), 'utf8')
    expect(config).not.toContain('fixture-access-')
    expect(config).not.toContain('fixture-refresh-')
    await app.close()
    app = await electron.launch({
      args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', data],
      env
    })
    // 不打开真实浏览器，留下待授权状态供取消检查。 Leave authorization pending for cancellation.
    await app.evaluate(({ shell }) => {
      shell.openExternal = async () => {}
    })
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    card = mcp.locator('.mcp-server').filter({ hasText: 'OAuth 本地样本' })
    await card.locator(':scope > summary').click()
    await expect(card).toContainText('已有本地登录')
    await card.getByRole('button', { name: '连接 / 重连', exact: true }).click()
    await expect(card.locator('.mcp-status')).toHaveText('已连接')
    await card.getByRole('button', { name: '登录授权', exact: true }).click()
    await expect(card.getByRole('button', { name: '打开授权网页', exact: true })).toBeVisible()
    await card.getByRole('button', { name: '取消登录', exact: true }).click()
    await expect(card).toContainText('登录已取消')
    await card.getByRole('button', { name: '退出本机登录', exact: true }).click()
    await expect(card.getByRole('status')).toHaveText('OAuth · 尚未登录')
    await expect(card.getByRole('button', { name: '打开授权网页', exact: true })).toHaveCount(0)
  } finally {
    await app?.close()
    lines.close()
    if (peer.exitCode === null) peer.kill()
    await exited
  }
})
