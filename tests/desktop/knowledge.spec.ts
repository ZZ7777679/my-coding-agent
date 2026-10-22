/** 验证真实桌面知识入口；只替换模型。 Exercise knowledge UI with only the model replaced. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp } from 'node:fs/promises'
import path from 'node:path'

test('M3 context, memory and worker controls persist across reload', async () => {
  // 该场景含重载、压缩、历史分页及新增子任务故障读取，保留单动作超时。
  // Allow the expanded reload/compaction/history/worker scenario while retaining action timeouts.
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-knowledge-'))
  const project = path.join(root, 'project')
  await mkdir(project)
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
    const page = await app.firstWindow()
    page.on('pageerror', (error) => console.error('Knowledge renderer:', error.message))
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('M3 简单离线页面')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    const sid = await page.locator('.tree-session.selected').getAttribute('data-session-id')
    if (!sid) throw new Error('Expected selected session')
    const panel = page.getByTestId('context-memory')
    const contextButton = panel.getByTestId('open-context')
    const closePanel = panel.getByRole('button', { name: '关闭面板', exact: true })
    await expect(contextButton).toContainText('尚未计量 / 1M token')
    await contextButton.click()
    await page.keyboard.press('Escape')
    await expect(contextButton).toBeFocused()
    await expect(panel.getByRole('region')).toBeHidden()
    await contextButton.click()
    await panel.getByTestId('context-advanced').locator(':scope > button').click()
    const outputLimit = page.getByLabel('摘要请求输出上限', { exact: true })
    await expect(outputLimit).toHaveValue('')
    await expect(outputLimit).toHaveAttribute('placeholder', '跟随运行预算')
    await outputLimit.fill('4096')
    await page.getByLabel('工具定义加载', { exact: true }).selectOption('all')
    await page.getByLabel('窗口允许时在后台压缩，下一请求采用', { exact: true }).check()
    await page.getByRole('button', { name: '保存材料与压缩参数', exact: true }).click()
    await expect(
      page.getByRole('button', { name: '保存材料与压缩参数', exact: true })
    ).toBeEnabled()
    const savedPolicy = await page.evaluate(async (sessionId) => {
      const response = await window.agent.getContext({ session_id: sessionId })
      if (!response.ok) throw new Error(response.error.message)
      return response.data.settings
    }, sid)
    expect(savedPolicy.tool_loading).toBe('all')
    expect(savedPolicy.background_compaction).toBe(true)
    await page.getByLabel('工具定义加载', { exact: true }).selectOption('on_demand')
    await page.getByLabel('窗口允许时在后台压缩，下一请求采用', { exact: true }).uncheck()
    await outputLimit.fill('')
    await page.getByRole('button', { name: '保存材料与压缩参数', exact: true }).click()
    await expect(
      page.getByRole('button', { name: '保存材料与压缩参数', exact: true })
    ).toBeEnabled()
    // M8 使用独立阅读面板，先关闭再切换入口；不穿透覆盖层。
    // Close the M8 reading surface before switching entry points.
    await closePanel.click()
    await panel.getByTestId('open-memory').click()
    await page.getByRole('button', { name: '新增记忆', exact: true }).click()
    await page.getByLabel('记忆标题').fill('Offline requirement')
    await page.getByLabel('记忆正文').fill('Use bundled assets and no CDN')
    await closePanel.click()
    await expect(panel.getByRole('region')).toBeHidden()
    await panel.getByTestId('open-memory').click()
    await expect(page.getByLabel('记忆正文')).toHaveValue('Use bundled assets and no CDN')
    await page.getByRole('button', { name: '保存记忆', exact: true }).click()
    await expect(panel).toContainText('Offline requirement')
    await closePanel.click()
    for (let index = 0; index < 3; index++) {
      await page
        .getByLabel('输入问题')
        .fill('m3: desktop history ' + index + (index === 0 ? ' x'.repeat(4600) : ''))
      await page.getByRole('button', { name: '发送', exact: true }).click()
      await expect(page.getByLabel('输入问题')).toHaveValue('')
      await expect(page.getByTestId('run-status')).toContainText('回答结束')
    }
    await expect(contextButton).toContainText('上次输入 123.5K / 1M token（12.3%）')
    await panel.getByTestId('open-history').click()
    await panel.getByTestId('history-query').locator(':scope > button').click()
    await page.getByLabel('历史搜索').fill('desktop history')
    await page.getByRole('button', { name: '查询历史', exact: true }).click()
    const results = panel.getByTestId('history-results')
    await expect(results).toContainText('3 项匹配')
    const firstEntry = results.locator('[data-testid^="history-entry-"]').first()
    await firstEntry.locator(':scope > button').click()
    await expect(firstEntry.locator('pre')).toContainText('desktop history 0')
    await expect(firstEntry.locator('pre')).not.toContainText('m3:')
    await firstEntry.getByRole('button', { name: '从头查看', exact: true }).click()
    await expect(firstEntry.locator('pre')).toContainText('m3: desktop history 0')
    await firstEntry.getByRole('button', { name: '继续展开原文', exact: true }).click()
    await expect(firstEntry.getByRole('button', { name: '继续展开原文', exact: true })).toHaveCount(
      0
    )
    await expect(firstEntry.locator('pre')).toHaveText('m3: desktop history 0' + ' x'.repeat(4600))
    await page.getByRole('button', { name: '更多历史结果', exact: true }).click()
    await expect(results.locator('[data-testid^="history-entry-"]')).toHaveCount(3)
    await firstEntry.getByRole('button', { name: '加入这次提问', exact: true }).click()
    await firstEntry.locator('.knowledge-collapse').click()
    await expect(firstEntry.locator('pre')).toBeHidden()
    await results.locator(':scope > button').click()
    await panel.getByTestId('history-query').locator(':scope > button').click()
    await closePanel.click()
    await expect(page.getByTestId('question-materials')).toContainText('历史 #')
    // 切到任务再回来会卸载 Chat；查看状态与所选材料仍按会话保留。
    // Switching through the task unmounts Chat; session viewer state and materials must survive.
    await page.locator('.tree-task').click()
    await page.locator(`.tree-session[data-session-id="${sid}"]`).click()
    await expect(page.getByTestId('question-materials')).toContainText('历史 #')
    await page.getByLabel('输入问题').fill('m3: use selected material')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toHaveValue('')
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(panel.getByRole('region')).toBeHidden()
    await expect(page.getByTestId('question-materials')).toHaveCount(0)
    await panel.getByTestId('open-history').click()
    await expect(results.locator(':scope > button')).toHaveAttribute('aria-expanded', 'false')
    await expect(panel.getByTestId('history-query').locator(':scope > button')).toHaveAttribute(
      'aria-expanded',
      'false'
    )
    await panel.getByTestId('history-query').locator(':scope > button').click()
    await expect(page.getByLabel('历史搜索')).toHaveValue('desktop history')
    await results.locator(':scope > button').click()
    await expect(results).toContainText('3 项匹配')
    await page.screenshot({ path: path.join(root, 'history-panel.png') })
    await closePanel.click()
    await contextButton.click()
    await panel.getByTestId('request-materials').locator(':scope > button').click()
    await expect(panel.getByTestId('request-materials')).toContainText('任务目标')
    await page.getByRole('button', { name: '压缩当前会话', exact: true }).click()
    await expect(panel).toContainText('查看摘要')
    await expect(contextButton).toContainText('压缩后待计量 / 1M token')
    await expect(panel).toContainText('本次输出上限 8192 token')
    await panel.getByTestId('summary').locator(':scope > button').click()
    await expect(panel).toContainText('Earlier task:')
    await page.screenshot({ path: path.join(root, 'context-panel.png') })
    await panel
      .getByTestId('summary')
      .getByRole('button', { name: '收起查看摘要', exact: true })
      .click()
    await closePanel.focus()
    await page.keyboard.press('Escape')
    await expect(contextButton).toBeFocused()
    await expect(panel.getByRole('region')).toBeHidden()
    const workers = page.getByTestId('workers')
    await page.getByLabel('输入问题').fill('m3: lookup')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toHaveValue('')
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await panel.getByTestId('open-history').click()
    await page.getByLabel('历史搜索').fill('read_history')
    await page.getByLabel('关键词检索也包含先前查找历史 / 状态工具的调用和结果').check()
    await page.getByRole('button', { name: '查询历史', exact: true }).click()
    await expect(results).toContainText('1 项匹配')
    const callEntry = results.locator('[data-testid^="history-entry-"]').first()
    await callEntry.locator(':scope > button').click()
    await callEntry.getByRole('button', { name: /^查看对应结果/ }).click()
    const linkedResult = callEntry.locator('[data-testid^="history-related-"]')
    await expect(linkedResult.locator('pre')).toContainText('desktop history')
    await linkedResult.locator(':scope > button').click()
    await expect(linkedResult.locator('pre')).toBeHidden()
    await expect(callEntry.locator(':scope > button')).toHaveAttribute('aria-expanded', 'true')
    await closePanel.click()
    await workers.locator(':scope > button').click()
    await page.locator('.worker-options > summary').click()
    await page.getByLabel('允许拆分子 agent').click()
    await expect(page.getByLabel('允许拆分子 agent')).toBeChecked()
    await expect(workers.locator(':scope > button')).toContainText('已开启')
    await page.screenshot({ path: path.join(root, 'knowledge.png') })
    await page.reload()
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').click()
    await page.locator(`.tree-session[data-session-id="${sid}"]`).click()
    await expect(page.getByTestId('workers').locator(':scope > button')).toContainText('已开启')
    await expect(page.getByTestId('open-context')).toContainText('已压缩')
    const state = await page.evaluate(
      (sessionId) => window.agent.listMemory({ session_id: sessionId }),
      sid
    )
    expect(
      state.ok && state.data.entries.some((entry) => entry.title === 'Offline requirement')
    ).toBe(true)
    const contextState = await page.evaluate(
      (sessionId) => window.agent.getContext({ session_id: sessionId }),
      sid
    )
    expect(contextState.ok && contextState.data.settings.summary_output_tokens).toBe(null)
    await page.getByLabel('输入问题').fill('m3: failing worker')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('运行失败')
    await workers.locator(':scope > button').click()
    const failed = page.locator('.reading-detail')
    await expect(failed).toContainText('Model request rejected (HTTP 400)')
    await failed.locator('.failure-notice summary').click()
    await expect(failed).toContainText('response_headers')
    await expect(failed).toContainText('诊断编号')
    await expect(failed).toContainText('已保存的部分输出')
    await expect(failed.locator('.markdown-content')).toHaveText(
      'I will inspect the progress directory'
    )
    await page.screenshot({ path: path.join(root, 'worker-failure.png') })
    await page.getByRole('button', { name: '返回对话', exact: true }).click()
    await page.getByLabel('输入问题').fill('m3: inspect failed worker')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(page.locator('.chat-panel')).toContainText(
      'Saved failure inspected without restarting the child.'
    )
  } finally {
    await app.close()
  }
})
