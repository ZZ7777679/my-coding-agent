/** 空项目的环境选择、实际程序与退出清理。 Empty-project environment, real execution and shutdown. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, python, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, readdir } from 'node:fs/promises'
import { createServer } from 'node:net'
import path from 'node:path'

/** 由系统分配临时端口，产品命令不依赖固定端口。 Allocate a temporary port without product constants. */
async function availablePort(): Promise<number> {
  const server = createServer()
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('No TCP endpoint')
  const port = address.port
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve()))
  )
  return port
}

/** 模型离线替身，环境 / 文件 / 进程 / HTTP / 桌面均走真实实现。 Offline model, real application stack. */
test('M2 environment and empty-project app persist while services stop on app exit', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-execution-'))
  const dataDir = path.join(root, 'data')
  const project = path.join(root, 'project')
  await mkdir(project)
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const launch = () =>
    electron.launch({
      args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', dataDir],
      env
    })
  let app = await launch()
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('从空目录创建并运行 Notes 小应用')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    expect(await readdir(dataDir)).not.toContain('environments.json')
    await page.getByLabel('输入问题').fill('program:location')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('chat-history')).toContainText(
      '已使用默认本机环境执行 Get-Location'
    )
    const location = page.locator('.chat-history > .program-card').first()
    await expect(location.locator('summary')).toContainText('run_command')
    await expect(location.locator('summary')).toContainText('Get-Location')
    await expect(location.locator('summary')).toContainText('已退出')
    await expect(location.locator('summary')).toContainText('退出码 0')
    await expect(location).not.toHaveAttribute('open', '')
    await location.locator('summary').click()
    await expect(location.getByLabel('程序输出')).toContainText(project)
    await expect(page.locator('.chat-panel .program-panel')).toHaveCount(0)
    await location.locator('summary').click()
    expect(await readdir(dataDir)).not.toContain('environments.json')
    expect(await readdir(project)).toEqual([])
    await page.screenshot({ path: path.join(root, 'default-execution.png') })
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    const settings = page.getByRole('region', { name: '项目执行环境' })
    await expect(settings.getByLabel('信任此项目的本机执行')).toHaveCount(0)
    await settings.getByLabel('环境名称', { exact: true }).fill('Isolated test Python')
    await settings.getByLabel('Python 解释器', { exact: true }).fill(python)
    await settings.getByRole('button', { name: '导入环境', exact: true }).click()
    await expect(settings.getByLabel('项目默认环境')).toContainText('Isolated test Python')
    await settings.getByLabel('项目默认环境').selectOption({ label: 'Isolated test Python' })
    await settings.getByRole('button', { name: '保存项目环境', exact: true }).click()
    await expect(settings.getByRole('status')).toHaveCount(0)
    await settings.locator('.environment-item summary').click()
    await settings.getByRole('button', { name: '检查此环境', exact: true }).click()
    await expect(settings).toContainText('已有环境检查完成')
    await page.locator('.tree-session.selected').click()
    const port = await availablePort()
    const url = `http://127.0.0.1:${port}/`
    await page.getByLabel('输入问题').fill(`program:create:${port}`)
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(page.getByTestId('chat-history')).toContainText('已创建并运行 Notes 小应用')
    const cards = page.locator('.chat-history > .program-card').filter({ hasText: 'start_service' })
    await expect(cards).toHaveCount(1)
    await expect(page.locator('.chat-history > .program-card')).toHaveCount(3)
    await expect(page.getByText('工具 · run_command', { exact: true })).toHaveCount(0)
    await expect(page.getByText('工具 · start_service', { exact: true })).toHaveCount(0)
    const command = page.locator('.chat-history > .program-card').filter({ hasText: '--describe' })
    await expect(command.locator('summary')).toContainText('已退出')
    await expect(command.locator('summary')).toContainText('退出码 0')
    await expect(command).not.toHaveAttribute('open', '')
    await expect(cards.locator('summary')).toContainText('HTTP 已响应')
    await cards.locator('summary').click()
    await expect(cards.getByRole('button', { name: '打开预览', exact: true })).toBeVisible()
    const response = await fetch(url)
    expect(response.status).toBe(200)
    expect(await response.text()).toContain('Save note')
    expect(await readdir(project)).toEqual(['app.py'])
    const order = await page.locator('.chat-history').evaluate((history) => {
      const children = [...history.children]
      const program = children.findIndex(
        (node) => node.matches('.program-card') && node.textContent?.includes('start_service')
      )
      const reply = children.findIndex(
        (node) =>
          node.matches('.assistant') && node.textContent?.includes('已创建并运行 Notes 小应用')
      )
      return program >= 0 && program < reply
    })
    expect(order).toBe(true)
    await cards.getByRole('button', { name: '打开预览', exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(root, 'program-cards.png') })
    // 切换视图不能停止已交付程序；退出使用真实应用退出流程。
    // Navigation keeps services; shutdown follows the real application quit path.
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await expect(
      page.locator('.program-panel:visible').getByText('HTTP 已响应', { exact: true })
    ).toBeVisible()
    expect((await fetch(url)).status).toBe(200)
    await app.evaluate(({ dialog, app: nativeApp }) => {
      dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
      nativeApp.quit()
    })
    await expect
      .poll(() =>
        fetch(url)
          .then(() => false)
          .catch(() => true)
      )
      .toBe(true)
    for (const record of await readdir(path.join(dataDir, 'programs'))) {
      const text = await readFile(path.join(dataDir, 'programs', record), 'utf8')
      expect(text).not.toContain(sentinel)
      expect(JSON.parse(text).summary.status).toMatch(/^(exited|stopped)$/)
    }
    await app.close()
    app = await launch()
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await expect(page.getByLabel('项目默认环境')).toContainText('Isolated test Python')
    await expect(page.getByLabel('信任此项目的本机执行')).toHaveCount(0)
    expect(
      await fetch(url)
        .then(() => true)
        .catch(() => false)
    ).toBe(false)
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await expect(page.locator('.program-panel:visible')).toContainText('已停止')
    // 重启后展开项目 / 任务，再进入已有会话；折叠状态不等于历史丢失。
    // Expand the navigation after restart; collapsed branches do not mean lost history.
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').click()
    await page.locator('.tree-session').click()
    const restored = page
      .locator('.chat-history > .program-card')
      .filter({ hasText: 'start_service' })
    await expect(restored.locator('summary')).toContainText('已停止')
    await expect(page.locator('.chat-panel .program-panel')).toHaveCount(0)
  } finally {
    await app
      .evaluate(({ dialog }) => {
        dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
      })
      .catch(() => {})
    await app.close()
  }
})
