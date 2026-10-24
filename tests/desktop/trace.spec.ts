/** 用隔离模型样本检查摘要、请求全文与导航；不调用模型服务。
 * Inspect summaries, request bodies and navigation with isolated model fixtures.
 */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import path from 'node:path'

test('Trace shows request input/output, chronology and concise tool targets', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-trace-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n')
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
    await page.getByLabel('阶段目标', { exact: true }).fill('Trace fixture')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByLabel('输入问题').fill('finish with source')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(page.locator('.tool-summary').first()).toContainText('读取 · main.py')
    await expect(page.locator('.tool-summary').first()).not.toContainText('Trace')
    await page.getByLabel('输入问题').fill('保留这条未发送草稿')
    await page.locator('.tool-summary button').first().click()
    const trace = page.getByRole('complementary', { name: '执行轨迹', exact: true })
    await expect(trace).toBeVisible()
    await expect(trace).toContainText('从上到下：较早 → 最新')
    await trace.getByRole('button', { name: '展开到工作区', exact: true }).click()
    const requests = trace.locator('.trace-timeline button').filter({ hasText: '模型请求' })
    await expect(requests).toHaveCount(2)
    await requests.first().click()
    const row = trace.locator('.trace-row:visible')
    await expect(row.getByRole('button', { name: '请求 JSON', exact: true })).toBeDisabled()
    await expect(row).toContainText('这是本次请求携带的上下文')
    await expect(row.locator('.trace-json-content')).not.toBeVisible()
    await row.getByRole('button', { name: /^展开.*请求 JSON/ }).click()
    await expect(row.locator('pre')).toContainText('"messages"')
    if (await row.getByRole('button', { name: '加载全部正文', exact: true }).isVisible()) {
      await row.getByRole('button', { name: '加载全部正文', exact: true }).click()
      await expect(row.getByRole('button', { name: '正在读取全文…' })).toHaveCount(0)
    }
    const input = JSON.parse(await row.locator('pre').innerText())
    expect(input.messages[0].role).toBe('system')
    expect(
      input.messages.some(
        (m: { role: string; content: string }) =>
          m.role === 'user' && m.content === 'finish with source'
      )
    ).toBe(true)
    expect(input.tools.length).toBeGreaterThan(0)
    expect(JSON.stringify(input)).not.toContain(sentinel)
    await expect(row.locator('.trace-input-counts')).toContainText(
      `本次输入：${input.messages.length} 条消息`
    )
    const reader = row.locator('.trace-json-content')
    await reader.evaluate((element) => {
      element.scrollTop = 240
    })
    await expect.poll(() => reader.evaluate((element) => element.scrollTop)).toBe(240)
    await row.getByRole('button', { name: '收起完整请求 JSON', exact: true }).click()
    await expect(reader).not.toBeVisible()
    await row.getByRole('button', { name: '展开完整请求 JSON', exact: true }).click()
    await expect(reader).toBeVisible()
    await expect.poll(() => reader.evaluate((element) => element.scrollTop)).toBe(240)
    expect(JSON.parse(await reader.locator('pre').innerText())).toEqual(input)
    await row.getByRole('button', { name: '按消息查看', exact: true }).click()
    const systemMessage = row
      .locator('.trace-request-body > details')
      .filter({ has: page.locator('summary').filter({ hasText: '系统提示' }) })
    await systemMessage.locator('summary').click()
    await expect(systemMessage.locator('pre')).toContainText('You are a coding agent')
    await systemMessage.locator('summary').click()
    await expect(systemMessage.locator('pre')).toHaveCount(0)
    await page.screenshot({ path: path.join(root, 'messages-inspector.png') })
    await row.getByRole('button', { name: '模型响应', exact: true }).click()
    await expect(row.locator('.trace-json-content')).not.toBeVisible()
    await row.getByRole('button', { name: '展开模型响应 JSON', exact: true }).click()
    await expect(row.locator('pre')).toContainText('"tool_calls"')
    await expect(row.locator('pre')).toContainText('read_file')
    await row.getByRole('button', { name: '收起模型响应 JSON', exact: true }).click()
    await expect(row.locator('.trace-json-content')).not.toBeVisible()
    await requests.last().click()
    await row.getByRole('button', { name: /^展开.*请求 JSON/ }).click()
    await expect(row.locator('pre')).toContainText('"role": "tool"')
    await page.screenshot({ path: path.join(root, 'request-inspector.png') })
    await row.getByRole('button', { name: '按消息查看', exact: true }).click()
    await expect(row.getByText('#3 · AI 消息', { exact: true })).toBeVisible()
    await expect(row.getByText('#4 · 工具结果', { exact: true })).toBeVisible()
    await row.getByText('#4 · 工具结果', { exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(root, 'messages-inspector.png') })
    await trace.getByRole('button', { name: '跳到最新记录', exact: true }).click()
    await expect(trace.locator('[data-trace-nav]').last().locator('button')).toHaveAttribute(
      'aria-current',
      'true'
    )
    await trace.getByLabel('筛选工具').fill('read_file')
    await expect(trace.locator('.trace-timeline button[aria-current="true"]')).toContainText(
      'read_file'
    )
    await expect(trace.getByRole('button', { name: '跳到最新匹配记录' })).toBeEnabled()
    await trace.getByRole('button', { name: '关闭 Trace', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toHaveValue('保留这条未发送草稿')
  } finally {
    await app.close()
  }
})
