/** MCP 预设、认证表单与连接恢复的真实桌面场景。 Real desktop preset, authentication and reconnect flow. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, python, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { once } from 'node:events'
import path from 'node:path'

test('MCP presets configure credentials and connect without raw JSON', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-mcp-services-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  const peer = spawn(python, ['-X', 'utf8', '-m', 'tests.support.mcp_http_fixture'], {
    cwd: path.resolve(__dirname, '../..'),
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  })
  const exited = once(peer, 'exit')
  peer.stderr?.resume()
  const lines = createInterface({ input: peer.stdout! })
  const line = await Promise.race([
    once(lines, 'line').then(([value]) => String(value)),
    exited.then(() => {
      throw new Error('HTTP fixture exited before reporting its port')
    })
  ])
  const url = `http://127.0.0.1:${Number(line)}/mcp`
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
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    let mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    await expect(mcp.getByRole('button', { name: '配置 GitHub', exact: true })).toBeVisible()
    await expect(mcp.locator('.mcp-server')).toHaveCount(1)
    await mcp.getByRole('button', { name: '配置 Context7 文档', exact: true }).click()
    await expect(mcp.getByRole('combobox', { name: '认证方式', exact: true })).toHaveValue('none')
    await mcp.getByRole('button', { name: '取消编辑', exact: true }).click()
    await expect(mcp.locator('.mcp-server')).toHaveCount(1)
    await mcp.getByRole('button', { name: '配置 GitHub', exact: true }).click()
    await mcp.getByLabel('名称', { exact: true }).fill('GitHub 本地样本')
    await mcp.getByLabel('服务地址', { exact: true }).fill(url)
    await mcp.getByLabel('服务令牌', { exact: true }).fill('wrong-fixture-token')
    await mcp.getByRole('button', { name: '保存并测试连接', exact: true }).click()
    let card = mcp.locator('.mcp-server').filter({ hasText: 'GitHub 本地样本' })
    await card.locator(':scope > summary').click()
    await expect(card.locator('.mcp-status')).toHaveText('连接失败')
    await expect(card).toContainText('401')
    await card.getByRole('button', { name: '编辑 / 启停', exact: true }).click()
    await expect(mcp.getByLabel('服务令牌', { exact: true })).toHaveValue('')
    await mcp.getByLabel('服务令牌', { exact: true }).fill('desktop-fixture-token')
    await mcp.getByRole('button', { name: '保存并测试连接', exact: true }).click()
    await expect(card.locator('.mcp-status')).toHaveText('已连接')
    await expect(card.locator('.mcp-tool')).toHaveCount(2)
    await expect(card).toContainText('当前项目已启用')
    await card.getByRole('button', { name: '编辑 / 启停', exact: true }).click()
    await mcp.getByLabel('调用超时（秒）', { exact: true }).fill('45')
    await mcp.getByRole('button', { name: '保存配置', exact: true }).click()
    await expect(card).toContainText('旧配置')
    await card.getByRole('button', { name: '连接 / 重连', exact: true }).click()
    await expect(card.locator('.mcp-status')).toHaveText('已连接')
    await expect(card).not.toContainText('旧配置')
    await page.screenshot({ path: path.join(root, 'connected.png') })
    await card.getByRole('button', { name: '在当前项目停用', exact: true }).click()
    await expect(card).toContainText('仅资源库')
    await card.getByRole('button', { name: '在当前项目启用', exact: true }).click()
    const config = await readFile(path.join(data, 'mcp.json'), 'utf8')
    expect(config).not.toContain('desktop-fixture-token')
    expect(config).not.toContain('wrong-fixture-token')
    await app.close()
    app = await electron.launch({
      args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', data],
      env
    })
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    card = mcp.locator('.mcp-server').filter({ hasText: 'GitHub 本地样本' })
    await card.locator(':scope > summary').click()
    await expect(card).toContainText('已加密保存令牌')
    await card.getByRole('button', { name: '连接 / 重连', exact: true }).click()
    await expect(card.locator('.mcp-status')).toHaveText('已连接')
    await card.getByRole('button', { name: '编辑 / 启停', exact: true }).click()
    await mcp.getByLabel('清除已保存令牌', { exact: true }).check()
    await mcp.getByRole('button', { name: '保存配置', exact: true }).click()
    await expect(card).toContainText('尚未保存令牌')
    await card.getByRole('button', { name: '移除登记', exact: true }).click()
    await expect(card).toHaveCount(0)
  } finally {
    await app?.close()
    lines.close()
    if (peer.exitCode === null) peer.kill()
    await exited
  }
})
