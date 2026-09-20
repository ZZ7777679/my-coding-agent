/** 多会话桌面归属与独立停止；复用既有模型替身。 Desktop ownership and isolated stop with the existing model substitute. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import path from 'node:path'

/** 第一会话运行时从界面创建并执行第二会话，停止前者不覆盖后者。 Start a second session in the UI and stop the first without replacing the second. */
test('M2 independent sessions stay runnable and stoppable across navigation', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-concurrency-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n', 'utf8')
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const app = await electron.launch({
    args: [
      path.resolve(__dirname, '../support/desktop_peer.cjs'),
      '--data-dir',
      path.join(root, 'data')
    ],
    env
  })
  try {
    await app.evaluate(({ dialog }) => {
      dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
    })
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('会话分工并行读取 main.py')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByLabel('输入问题').fill('first read and wait')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('chat-history')).toContainText('第 2 行返回 42')
    await page.locator('.tree-task').first().click()
    await page.getByText('创建新的工作会话', { exact: true }).click()
    await page.getByLabel('会话角色', { exact: true }).fill('并行阅读')
    await page.getByRole('button', { name: '新建会话', exact: true }).click()
    await page.getByLabel('输入问题').fill('second read and wait')
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.locator('.tree-session .session-state.running')).toHaveCount(2)
    await expect(page.getByTestId('chat-history')).toContainText('second read and wait')
    await expect(page.getByTestId('chat-history')).not.toContainText('first read and wait')
    const running = await page.evaluate(() => window.agent.getActiveRuns())
    expect(running.ok && running.data.sessions.length).toBe(2)
    if (!running.ok) throw new Error(running.error.code)
    const first = running.data.sessions.find((item) => item.title.includes('first'))
    const second = running.data.sessions.find((item) => item.title.includes('second'))
    if (!first || !second) throw new Error('Both distinct runs must be listed')
    expect(first.session_id).not.toBe(second.session_id)
    await page.screenshot({ path: path.join(root, 'parallel.png') })
    await page.locator(`.tree-session[data-session-id="${first.session_id}"]`).click()
    await page.getByRole('button', { name: '停止运行', exact: true }).click()
    await expect(page.locator('.tree-session .session-state.running')).toHaveCount(1)
    const secondEntry = page.locator(`.tree-session[data-session-id="${second.session_id}"]`)
    await expect(secondEntry.locator('.session-state')).toHaveClass('session-state running')
    await secondEntry.click()
    await expect(page.getByTestId('run-status')).toContainText('正在运行')
    await page.reload()
    page = await app.firstWindow()
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').first().click()
    await page.locator(`.tree-session[data-session-id="${second.session_id}"]`).click()
    await expect(page.getByTestId('chat-history')).toContainText('second read and wait')
    const unchanged = await page.evaluate(() => window.agent.getActiveRuns())
    expect(unchanged.ok && unchanged.data.sessions[0]?.run?.run_id).toBe(second.run?.run_id)
    await page.getByRole('button', { name: '停止运行', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('已停止')
    await expect(page.locator('.tree-session .session-state.running')).toHaveCount(0)
    await app.evaluate(({ BrowserWindow }) => {
      BrowserWindow.getAllWindows()[0].setContentSize(960, 650)
    })
    await expect(page.getByLabel('会话模型', { exact: true })).toBeVisible()
    await expect(page.getByLabel('输入问题')).toBeInViewport()
    await expect(page.getByTestId('send-message')).toBeInViewport()
    const layout = await page.evaluate(() => ({
      historyRatio: document.querySelector('.chat-history')!.clientHeight / innerHeight,
      horizontalOverflow: document.documentElement.scrollWidth - innerWidth
    }))
    expect(layout.historyRatio).toBeGreaterThan(0.6)
    expect(layout.horizontalOverflow).toBeLessThanOrEqual(1)
    await page.screenshot({ path: path.join(root, 'compact-window.png') })
  } finally {
    await app.close()
  }
})
