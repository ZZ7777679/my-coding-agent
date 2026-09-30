/** 本地 MCP 工具目录和窗口滚动边界。 Local MCP catalog and viewport scroll boundaries. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, python, sentinel } from './helpers'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import path from 'node:path'

test('MCP tools are readable and chat input stays inside the window', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-mcp-layout-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  await mkdir(data)
  await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n')
  await writeFile(
    path.join(data, 'mcp.json'),
    JSON.stringify({
      servers: [
        {
          server_id: 'catalog-fixture',
          name: '本地工具样本',
          transport: 'stdio',
          command: python,
          arguments: ['-X', 'utf8', path.resolve(__dirname, '../support/mcp_catalog_fixture.py')]
        }
      ]
    })
  )
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const app = await electron.launch({
    args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', data],
    env
  })
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('目录与布局检查')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    const mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    const server = mcp.locator('.mcp-server')
    await expect(server).toContainText('未连接')
    await server.locator(':scope > summary').click()
    await expect(server).toContainText('连接服务后可查看')
    await server.getByRole('button', { name: '连接 / 重连', exact: true }).click()
    await expect(server.locator('.mcp-status')).toHaveText('已连接')
    await expect(server.locator('.mcp-tool')).toHaveCount(2)
    await expect(server.locator('pre')).toHaveCount(0)
    const search = server.getByRole('searchbox', { name: '搜索工具' })
    await search.fill('nothing-matches')
    await expect(server).toContainText('没有匹配的工具')
    await search.fill('样本状态')
    await expect(server.locator('.mcp-tool:visible')).toHaveCount(1)
    await expect(server.locator('.mcp-tool:visible')).toContainText('读取状态')
    await search.fill('format_note')
    const tool = server.locator('.mcp-tool:visible')
    await tool.locator(':scope > summary').click()
    await expect(tool.locator('.mcp-parameters')).toContainText('要整理的文本')
    await expect(tool.locator('.mcp-parameters')).toContainText('必填')
    await expect(tool.locator('.mcp-parameters')).toContainText('可选')
    await expect(tool.locator('.mcp-parameters')).toContainText('默认值："brief"')
    await tool.locator('.mcp-raw > summary').click()
    await expect(tool.locator('pre')).toContainText('inputSchema')
    await tool.locator('.mcp-raw > summary').click()
    await expect(tool.locator('pre')).toHaveCount(0)
    await server.getByRole('button', { name: '刷新工具', exact: true }).click()
    await expect(server.locator('.mcp-status')).toHaveText('已连接')
    await expect(tool).toHaveAttribute('open', '')
    await search.fill('')
    await page.screenshot({ path: path.join(root, 'mcp-tools.png') })
    await server.getByRole('button', { name: '关闭此连接', exact: true }).click()
    await expect(server.locator('.mcp-status')).toHaveText('未连接')
    await page.locator('.tree-session').first().click()
    await page
      .getByLabel('输入问题')
      .fill('finish with source\n' + 'A long conversation line.\n'.repeat(70))
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')

    // 使用真实窗口尺寸；每个滚动区域在自己的边界内，不能靠裁掉输入框通过。
    // Resize the native window and verify containment, not just hidden overflow.
    const measurements = []
    for (const [width, height] of [
      [1220, 820],
      [1080, 700],
      [960, 650]
    ]) {
      await app.evaluate(
        ({ BrowserWindow }, size) => {
          BrowserWindow.getAllWindows()[0].setSize(size[0], size[1])
        },
        [width, height]
      )
      await expect(page.getByRole('button', { name: '发送', exact: true })).toBeInViewport({
        ratio: 1
      })
      await expect(page.getByLabel('输入问题')).toBeInViewport({ ratio: 1 })
      const geometry = await page.evaluate(() => {
        const history = document.querySelector<HTMLElement>('.chat-history')!
        const workspace = document.querySelector<HTMLElement>('.workspace')!
        const composer = document.querySelector<HTMLElement>('.composer-dock')!
        return {
          width: innerWidth,
          height: innerHeight,
          documentHeight: document.documentElement.scrollHeight,
          workspaceHeight: workspace.clientHeight,
          workspaceScroll: workspace.scrollHeight,
          historyHeight: history.clientHeight,
          historyScroll: history.scrollHeight,
          inputBottom: composer.getBoundingClientRect().bottom
        }
      })
      measurements.push(geometry)
      expect(geometry.documentHeight).toBeLessThanOrEqual(geometry.height + 1)
      expect(geometry.workspaceScroll).toBeLessThanOrEqual(geometry.workspaceHeight + 1)
      expect(geometry.historyHeight).toBeGreaterThan(180)
      expect(geometry.historyScroll).toBeGreaterThan(geometry.historyHeight)
      expect(geometry.inputBottom).toBeLessThanOrEqual(geometry.height + 1)
      await page.getByRole('button', { name: 'Trace', exact: true }).click()
      const trace = page.getByRole('complementary', { name: '执行轨迹', exact: true })
      await expect(trace).toBeInViewport({ ratio: 1 })
      await trace.getByRole('button', { name: '关闭 Trace', exact: true }).click()
      const workers = page.getByTestId('workers')
      await workers.locator(':scope > summary').click()
      await expect(workers.getByRole('button', { name: '保存并发数' })).toBeInViewport({ ratio: 1 })
      await expect(page.getByLabel('输入问题')).toBeInViewport({ ratio: 1 })
      await workers.locator(':scope > summary').click()
      await page.screenshot({ path: path.join(root, `chat-${width}-${height}.png`) })
    }
    await writeFile(path.join(root, 'layout.json'), JSON.stringify(measurements, null, 2))
  } finally {
    await app.close()
  }
})
