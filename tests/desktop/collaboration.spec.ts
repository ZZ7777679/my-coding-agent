/** 实际桌面协作入口，模型复用既有替身。 Exercise real collaboration UI with the existing model substitute. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import path from 'node:path'

/** 用户保存约定、读取历史、请求并查看真实关联结果，重载不重发。 Save an agreement, read history and request a result without resending on reload. */
test('M2 user-arranged collaboration returns attributed results', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-collaboration-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n', 'utf8')
  const env: Record<string, string> = {}
  for (const [key, value] of Object.entries(process.env)) if (value !== undefined) env[key] = value
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
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('共同读取 main.py')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByLabel('输入问题').fill('Read main.py')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await page.locator('.tree-task').first().click()
    await page.getByText('创建新的工作会话', { exact: true }).click()
    await page.getByLabel('会话角色', { exact: true }).fill('实现')
    await page.getByRole('button', { name: '新建会话', exact: true }).click()
    const source = await page.locator('.tree-session.selected').getAttribute('data-session-id')
    if (!source) throw new Error('The source session must be selected')
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.locator('.collaboration-panel > summary').click()
    const select = page.getByLabel('协作会话', { exact: true })
    await expect(select.locator('option')).toHaveCount(2)
    const target = await select.locator('option').nth(1).getAttribute('value')
    if (!target) throw new Error('An existing peer must be selectable')
    await select.selectOption(target)
    await expect(page.getByRole('button', { name: '读取对方历史', exact: true })).toBeDisabled()
    await page
      .getByLabel('协作分工', { exact: true })
      .fill('本会话负责实现；对方负责只读核对 main.py 并返回结果。')
    await page.getByRole('button', { name: '保存协作约定', exact: true }).click()
    await expect(page.getByRole('button', { name: '读取对方历史', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '读取对方历史', exact: true }).click()
    await expect(page.locator('.collaboration-panel')).toContainText('公开历史')
    await expect(page.locator('.collaboration-panel')).toContainText('返回 42')
    await expect(page.locator('.collaboration-panel')).not.toContainText('private-native-sentinel')
    await page.getByLabel('协作请求', { exact: true }).fill('Confirm the value returned by main.py')
    await page.getByRole('button', { name: '发送协作请求', exact: true }).click()
    const card = page.locator('.collaboration-requests article')
    await expect(card).toHaveCount(1)
    await expect(card).toContainText('已返回结果')
    await expect(card).toContainText('返回 42')
    const identity = await card.getAttribute('data-request-id')
    const before = await page.evaluate(
      (id) => window.agent.getSession({ session_id: id, before_seq: null }),
      target
    )
    if (!before.ok) throw new Error(before.error.code)
    expect(before.data.entries.some((entry) => entry.kind === 'collaboration.request')).toBe(true)
    await page.screenshot({ path: path.join(root, 'result.png') })
    await page.reload()
    // 重载按现有左侧树重新打开来源会话，不假设应用自动恢复当前页面。
    // Reopen the existing source through the tree instead of assuming automatic page restoration.
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').click()
    await page.locator(`.tree-session[data-session-id="${source}"]`).click()
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.locator('.collaboration-panel > summary').click()
    await expect(card).toHaveCount(1)
    await expect(card).toHaveAttribute('data-request-id', identity ?? '')
    await expect(card).toContainText('已返回结果')
    const after = await page.evaluate(
      (id) => window.agent.getSession({ session_id: id, before_seq: null }),
      target
    )
    expect(after.ok && after.data.summary.run?.run_id).toBe(before.data.summary.run?.run_id)
    expect(after.ok && after.data.watermark).toBe(before.data.watermark)
  } finally {
    await app.close()
  }
})
