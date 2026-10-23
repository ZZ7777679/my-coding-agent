/** MCP 粘贴导入的格式与真实桌面验证。 Format and real desktop checks for pasted MCP imports. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, python, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { once } from 'node:events'
import path from 'node:path'
import { parseMcpImport } from '../../apps/desktop/src/renderer/src/mcpImportDraft'

test('remote import preserves endpoints and separates credentials from public config', () => {
  for (const type of ['streamableHttp', 'streamable-http', 'streamable_http', 'http']) {
    const [entry] = parseMcpImport(
      JSON.stringify({
        mcpServers: {
          cmapi00074637: {
            type,
            url: 'http://localhost:8123/mcp?region=cn',
            headers: { Authorization: 'Bearer fixture-secret', 'X-Tenant': 'demo' }
          }
        }
      })
    )
    expect(entry.parsed).toBe(true)
    expect(entry.server.url).toBe('http://localhost:8123/mcp?region=cn')
    expect(entry.server.auth).toEqual({
      source: 'saved',
      header: 'Authorization',
      prefix: 'Bearer'
    })
    expect(entry.server.headers).toEqual({})
    expect(entry.server.stored_headers).toEqual(['X-Tenant'])
    expect(entry.connectionValues.headers).toEqual({ 'X-Tenant': 'demo' })
    expect(entry.credential).toBe('fixture-secret')
    expect(JSON.stringify(entry.server)).not.toContain('fixture-secret')
  }
  const [env] = parseMcpImport(
    JSON.stringify({
      url: 'https://example.com/mcp',
      headers: {
        Authorization: 'Bearer ${env:MCP_TOKEN}',
        'X-Tenant': '${TENANT}'
      }
    })
  )
  expect(env.server.auth).toEqual({
    source: 'environment',
    header: 'Authorization',
    prefix: 'Bearer',
    env_var: 'MCP_TOKEN'
  })
  expect(env.server.header_refs).toEqual({ 'X-Tenant': 'TENANT' })
  expect(env.credential).toBe('')
  expect(parseMcpImport('https://example.com/mcp')[0].server.auth?.source).toBe('none')
})

test('unsupported entries stay explicit without blocking compatible siblings or echoing raw secrets', () => {
  const rows = parseMcpImport(
    JSON.stringify({
      mcpServers: {
        valid: { url: 'https://example.com/mcp' },
        legacy: { type: 'sse', url: 'https://example.com/sse' },
        local: { command: 'node', args: ['server.js'], env: { API_KEY: 'isolated-local-key' } },
        unsupported: { type: 'websocket', url: 'https://example.com/ws' },
        headers: { url: 'https://example.com/mcp', headers: { Authorization: 123 } }
      }
    })
  )
  expect(rows.map((row) => row.parsed)).toEqual([true, true, true, false, false])
  expect(rows[1].server.transport).toBe('sse')
  expect(rows[2].server.transport).toBe('stdio')
  expect(rows[2].connectionValues.env).toEqual({ API_KEY: 'isolated-local-key' })
  expect(JSON.stringify(rows[2].server)).not.toContain('isolated-local-key')
  expect(rows[3].error).toContain('暂不支持')
  expect(() => parseMcpImport('{ "secret": "fixture-secret"')).toThrow('有效 JSON')
  expect(
    parseMcpImport(JSON.stringify({ url: 'https://example.com/mcp', ignored: 'fixture-secret' }))[0]
      .error
  ).not.toContain('fixture-secret')
})

test('desktop imports JSON and URL, keeps partial saves, credentials and duplicate identities across restart', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-mcp-import-'))
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
  let app: Awaited<ReturnType<typeof electron.launch>> | null = null
  try {
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
    const launch = {
      args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', data],
      env
    }
    app = await electron.launch(launch)
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    let mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    await mcp.getByRole('button', { name: '从 URL / JSON 导入', exact: true }).click()
    let panel = mcp.getByRole('region', { name: '导入 MCP', exact: true })
    await panel.getByLabel('URL 或 JSON', { exact: true }).fill(
      JSON.stringify({
        mcpServers: {
          cmapi00074637: {
            url,
            type: 'streamableHttp',
            headers: { Authorization: 'Bearer desktop-fixture-token' }
          },
          second: { url }
        }
      })
    )
    await panel.getByRole('button', { name: '识别并预览', exact: true }).click()
    const first = panel.getByRole('article', { name: '导入 cmapi00074637', exact: true })
    const second = panel.getByRole('article', { name: '导入 second', exact: true })
    await expect(
      first.getByLabel('服务令牌（Authorization Bearer）', { exact: true })
    ).toHaveAttribute('type', 'password')
    await expect(mcp.locator('.mcp-server')).toHaveCount(1)
    // 第一项成功后第二项本地参数失败；重试不得重复新建第一项。
    // Fail the second draft after saving the first; retry must not recreate the first.
    await second.getByLabel('服务地址', { exact: true }).fill('')
    await panel.getByRole('button', { name: '导入所选 2 项', exact: true }).click()
    await expect(panel.getByRole('status')).toContainText('已导入 1 项')
    await expect(second.getByRole('alert')).toContainText('请填写远程服务 URL')
    await second.getByLabel('服务地址', { exact: true }).fill(url)
    await panel.getByRole('button', { name: '导入所选 1 项', exact: true }).click()
    await expect(panel.getByRole('status')).toContainText('已导入 2 项')
    await expect(mcp.locator('.mcp-server')).toHaveCount(3)
    let card = mcp.locator('.mcp-server').filter({ hasText: 'cmapi00074637' })
    await expect(card.locator('.mcp-status')).toHaveText('未连接')
    await panel.getByRole('button', { name: '关闭导入', exact: true }).click()
    await card.locator(':scope > summary').click()
    await expect(card).toContainText('当前项目已启用')
    await card.getByRole('button', { name: '连接 / 重连', exact: true }).click()
    await expect(card.locator('.mcp-status')).toHaveText('已连接')
    await expect(card.locator('.mcp-tool')).toHaveCount(2)
    const config = await readFile(path.join(data, 'mcp.json'), 'utf8')
    expect(config).not.toContain('desktop-fixture-token')
    const catalog = await page.evaluate(() => window.agent.listMcp({}))
    expect(JSON.stringify(catalog)).not.toContain('desktop-fixture-token')
    await app.close()
    app = await electron.launch(launch)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    card = mcp.locator('.mcp-server').filter({ hasText: 'cmapi00074637' })
    await card.locator(':scope > summary').click()
    await expect(card).toContainText('已加密保存令牌')
    await expect(card).toContainText('当前项目已启用')
    await card.getByRole('button', { name: '连接 / 重连', exact: true }).click()
    await expect(card.locator('.mcp-status')).toHaveText('已连接')
    await mcp.getByRole('button', { name: '从 URL / JSON 导入', exact: true }).click()
    panel = mcp.getByRole('region', { name: '导入 MCP', exact: true })
    await panel.getByLabel('URL 或 JSON', { exact: true }).fill(url)
    await panel.getByRole('button', { name: '识别并预览', exact: true }).click()
    await panel.getByLabel('服务名称', { exact: true }).fill('cmapi00074637')
    await expect(panel.getByLabel('启用范围', { exact: true })).toBeVisible()
    await panel.getByLabel('启用范围', { exact: true }).selectOption('')
    await expect(panel).toContainText('已有同名服务')
    await page.screenshot({ path: path.join(root, 'import-preview.png') })
    await panel.getByRole('button', { name: '导入所选 1 项', exact: true }).click()
    await expect(panel.getByRole('status')).toContainText('已导入 1 项')
    await panel.getByRole('button', { name: '关闭导入', exact: true }).click()
    await expect(card).toHaveCount(2)
    await expect(card.first().locator('.mcp-status')).toHaveText('已连接')
    await card.last().locator(':scope > summary').click()
    await expect(card.last()).toContainText('仅资源库')
    await expect(card.last().locator('.mcp-status')).toHaveText('未连接')
    await mcp.getByRole('button', { name: '从 URL / JSON 导入', exact: true }).click()
    panel = mcp.getByRole('region', { name: '导入 MCP', exact: true })
    await panel.getByLabel('URL 或 JSON', { exact: true }).fill(
      JSON.stringify({
        servers: {
          local: {
            type: 'stdio',
            command: python,
            args: [path.resolve(__dirname, '../support/mcp_import_fixture.py')],
            cwd: '${workspaceFolder}',
            env: { MCP_IMPORT_TOKEN: 'isolated-local-token' }
          }
        }
      })
    )
    await panel.getByRole('button', { name: '识别并预览', exact: true }).click()
    await expect(panel).toContainText('本地 stdio')
    await expect(panel.getByLabel('环境变量 MCP_IMPORT_TOKEN（加密保存）')).toHaveAttribute(
      'type',
      'password'
    )
    await panel.getByRole('button', { name: '导入所选 1 项', exact: true }).click()
    await expect(panel.getByRole('status')).toContainText('已导入 1 项')
    await panel.getByRole('button', { name: '关闭导入', exact: true }).click()
    const local = mcp
      .locator('.mcp-server')
      .filter({ has: page.locator('summary strong', { hasText: /^local$/ }) })
    await local.locator(':scope > summary').click()
    await local.getByRole('button', { name: '连接 / 重连', exact: true }).click()
    await expect(local.locator('.mcp-status')).toHaveText('已连接')
    await expect(local.locator('.mcp-tool')).toHaveCount(1)
    await local.getByRole('button', { name: '编辑 / 启停', exact: true }).click()
    await mcp.getByText('高级连接选项', { exact: true }).click()
    await expect(mcp.getByLabel('已保存环境变量 MCP_IMPORT_TOKEN')).toHaveValue('')
    await mcp.getByRole('button', { name: '保存配置', exact: true }).click()
    expect(await readFile(path.join(data, 'mcp.json'), 'utf8')).not.toContain(
      'isolated-local-token'
    )
  } finally {
    await app?.close()
    lines.close()
    if (peer.exitCode === null) peer.kill()
    await exited
  }
})
