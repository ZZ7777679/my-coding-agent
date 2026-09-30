/** 长任务负责人通过真实桌面体验接续，只替换模型。 Long-task owner journeys using the real desktop and a model substitute. */
import { electron, expect, test, type ElectronApplication } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import type { Page } from '../../apps/desktop/node_modules/@playwright/test'

/** 创建独立项目与数据根，不访问个人项目。 Create an isolated project and data root without personal data. */
async function fixture(label: string) {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, `persona-long-tasks-${label}-`))
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
  /** 复用已有模型装配；主进程和后端仍为产品实现。 Reuse the model fixture with production main and backend. */
  const launch = () =>
    electron.launch({
      args: [
        path.resolve(__dirname, '../support/desktop_peer.cjs'),
        '--data-dir',
        path.join(root, 'data')
      ],
      env
    })
  console.info(`PERSONA_ARTIFACTS ${root}`)
  return { root, project, launch }
}

/** 保存视觉与可检索的界面证据。 Save visual and searchable UI evidence. */
async function capture(page: Page, root: string, name: string) {
  await page.screenshot({ path: path.join(root, `${name}.png`) })
  await writeFile(path.join(root, `${name}.txt`), await page.locator('body').innerText(), 'utf8')
}

/** 明确创建一个任务及首会话，不开始模型运行。 Explicitly create one task and its first session without model work. */
async function createTask(app: ElectronApplication, project: string, title: string) {
  const page = await app.firstWindow()
  await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
  await choose(app, project)
  await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
  await page.getByLabel('任务名称', { exact: true }).fill(title)
  await page
    .getByLabel('阶段目标', { exact: true })
    .fill('长期维护离线清单；实现与文档由不同会话协作。')
  await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  await page.getByLabel('已确认结论', { exact: true }).fill('只使用本地资源，启动端口 8123。')
  await page
    .getByLabel('当前进度', { exact: true })
    .fill('main.py 已存在，下一步由文档会话核对说明。')
  await page.getByRole('button', { name: '保存共享信息', exact: true }).click()
  await expect(page.locator('.task-panel').getByRole('status')).toContainText('共享信息已保存')
  return page
}

/** 从真实左树恢复指定会话。 Reopen a saved session through the actual navigation tree. */
async function reopen(page: Page, session: string) {
  await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
  await page.locator('.tree-project').click()
  await page.locator('.tree-task').click()
  await page.locator(`.tree-session[data-session-id="${session}"]`).click()
}

/** 发送替身可识别的文本，真实记录请求与材料。 Send fixture-recognized text through real request and material storage. */
async function send(page: Page, prompt: string) {
  await page.getByLabel('输入问题').fill(prompt)
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByLabel('输入问题')).toHaveValue('')
  await expect(page.getByTestId('run-status')).toContainText('回答结束')
}

/** 完成任务分工、阶段覆盖与手动交接，并检查重启未重发。 Exercise task roles, stage overrides and explicit handoff without replay after restart. */
test('Long-task owner associates stages, hands off work and resumes after restart', async () => {
  test.setTimeout(120000)
  const f = await fixture('workflow')
  let app = await f.launch()
  let page: Page | undefined
  try {
    page = await createTask(app, f.project, '离线清单长期维护')
    const stages = await page
      .getByLabel('当前阶段', { exact: true })
      .locator('option')
      .allTextContents()
    expect(stages).toEqual(['未选择', '讨论', '规划', '实现', '验证', '审查', '交接', '收尾'])
    await page.getByLabel('当前阶段', { exact: true }).selectOption('implement')
    await page.getByRole('button', { name: '保存任务流程', exact: true }).click()
    await expect(page.getByRole('button', { name: '保存任务流程', exact: true })).toBeEnabled()
    await capture(page, f.root, '01-task-workflow')
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    const source = await page.locator('.tree-session.selected').getAttribute('data-session-id')
    if (!source) throw new Error('Missing source session')
    await send(page, 'Read main.py and confirm the value for the documentation handoff.')
    const sourceView = await page.evaluate(
      (id) => window.agent.getSession({ session_id: id, before_seq: null }),
      source
    )
    if (!sourceView.ok || !sourceView.data.summary.task_id) throw new Error('Missing task')
    expect(sourceView.data.summary.run?.status).toBe('completed')
    const sourceRun = sourceView.data.summary.run
    if (!sourceRun) throw new Error('Missing completed source run')
    const taskId = sourceView.data.summary.task_id
    await page.locator('.tree-task').click()
    await page.getByText('创建新的工作会话', { exact: true }).click()
    await page.getByLabel('会话角色', { exact: true }).fill('文档接续')
    await page.getByLabel('工作范围', { exact: true }).fill('只读核对 main.py 并返回文档建议')
    await page.getByRole('button', { name: '新建会话', exact: true }).click()
    const target = await page.locator('.tree-session.selected').getAttribute('data-session-id')
    if (!target) throw new Error('Missing target session')
    // 接收方先留一轮不同答案，确认交接结果来自新 Run 而非已有历史。
    // Keep a distinct prior answer in the recipient to verify provenance from the new run.
    await send(page, 'm3: documentation prepares to check offline requirement')
    const targetView = await page.evaluate(
      (id) => window.agent.getSession({ session_id: id, before_seq: null }),
      target
    )
    if (!targetView.ok) throw new Error(targetView.error.code)
    await expect(
      page.locator(`.tree-session[data-session-id="${target}"] .session-role`)
    ).toHaveText('文档接续')
    await page.locator('.tree-task').click()
    await page
      .getByLabel(`${targetView.data.summary.title} 的阶段`, { exact: true })
      .selectOption('handoff')
    await page.getByRole('button', { name: '保存任务流程', exact: true }).click()
    await expect(page.getByRole('button', { name: '保存任务流程', exact: true })).toBeEnabled()
    await expect(
      page.getByRole('button', {
        name: `${targetView.data.summary.title} · 文档接续`,
        exact: true
      })
    ).toBeVisible()
    const task = await page.evaluate((id) => window.agent.getTask(id), taskId)
    expect(task.ok && task.data.workflow?.session_stages?.[target]).toBe('handoff')
    await capture(page, f.root, '02-role-stage')
    await page.locator(`.tree-session[data-session-id="${source}"]`).click()
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.locator('.collaboration-panel > summary').click()
    await page.getByLabel('协作会话', { exact: true }).selectOption(target)
    await page.getByText('普通协作消息（空闲时只收件）', { exact: true }).click()
    await expect(page.locator('.collaboration-panel [role="status"]')).toContainText(
      '尚未为所选会话保存协作约定'
    )
    await page
      .getByLabel('协作消息', { exact: true })
      .fill('已确认启动端口 8123，请接手时保留本地资源约束。')
    await page.getByRole('button', { name: '发送给所选会话', exact: true }).click()
    await expect(page.locator('.collaboration-panel [role="alert"]')).toContainText(
      '尚未设置这两个会话的协作约定'
    )
    await capture(page, f.root, '03-message-needs-agreement')
    await page
      .getByLabel('协作分工', { exact: true })
      .fill('主会话维护共同结论，文档会话核对 main.py 并返回说明。')
    await page.getByRole('button', { name: '保存协作约定', exact: true }).click()
    await expect(page.getByRole('button', { name: '读取对方历史', exact: true })).toBeEnabled()
    await expect(page.locator('.collaboration-panel [role="status"]')).toHaveCount(0)
    await page.getByRole('button', { name: '发送给所选会话', exact: true }).click()
    await expect(page.locator('.collaboration-panel')).toContainText('已保存待接收')
    const idle = await page.evaluate(() => window.agent.getActiveRuns())
    expect(idle.ok && idle.data.sessions.length).toBe(0)
    await page.getByLabel('工作安排', { exact: true }).selectOption('handoff')
    await page
      .getByLabel('接手目标', { exact: true })
      .fill('Read main.py and confirm the value; preserve the offline requirement.')
    await page
      .getByLabel('交接补充说明', { exact: true })
      .fill('文档会话独立核对代码，保留任务共享结论。')
    await page.getByRole('button', { name: '开始交接', exact: true }).click()
    const card = page.locator('.collaboration-requests article')
    await expect(card).toHaveCount(1)
    await expect(card).toContainText('已返回结果')
    await expect(card).toContainText('返回 42')
    await card.getByText(/查看来源简报/).click()
    await expect(card).toContainText('启动端口 8123')
    const requests = await page.evaluate(
      (id) => window.agent.listCollaboration({ session_id: id }),
      source
    )
    if (!requests.ok) throw new Error(requests.error.code)
    expect(requests.data.requests).toHaveLength(1)
    const request = requests.data.requests[0]
    expect(request.status).toBe('completed')
    expect(request.brief?.source_session_id).toBe(source)
    expect(request.brief?.source_watermark).toBe(sourceView.data.watermark)
    expect(request.brief?.source_run).toEqual(sourceRun)
    expect(request.target_run_id).not.toBe(targetView.data.summary.run?.run_id)
    expect(request.params.target_session_id).toBe(target)
    await capture(page, f.root, '03-handoff-result')
    await card.getByRole('button', { name: '查看接收会话', exact: true }).click()
    await expect(page.getByTestId('chat-history')).toContainText('返回 42')
    const before = await page.evaluate(
      (id) => window.agent.getSession({ session_id: id, before_seq: null }),
      target
    )
    const materials = await page.evaluate(
      (id) => window.agent.getContext({ session_id: id }),
      target
    )
    if (!before.ok) throw new Error(before.error.code)
    expect(before.data.summary.run?.status).toBe('completed')
    expect(before.data.summary.run?.run_id).toBe(request.target_run_id)
    const resultFact = before.data.entries.find((entry) => entry.seq === request.result_seq)
    expect(resultFact?.kind).toBe('run.finished')
    expect(resultFact?.run_id).toBe(request.target_run_id)
    const answer = [...before.data.entries]
      .reverse()
      .find((entry) => entry.kind === 'assistant' && entry.run_id === request.target_run_id)
    expect(answer?.text).toBe(request.result)
    expect(request.result).toContain('main.py:2 返回 42')
    await page.getByTestId('open-context').click()
    await page.getByTestId('request-materials').locator(':scope > button').click()
    await capture(page, f.root, '04-handoff-materials')
    await writeFile(
      path.join(f.root, 'facts-before-restart.json'),
      JSON.stringify({ source, target, sourceView, task, requests, before, materials }, null, 2),
      'utf8'
    )
    const sourceFactsPath = path.join(f.root, 'data', 'sessions', source, 'events.jsonl')
    const targetFactsPath = path.join(f.root, 'data', 'sessions', target, 'events.jsonl')
    const sourceFacts = await readFile(sourceFactsPath, 'utf8')
    const targetFacts = await readFile(targetFactsPath, 'utf8')
    await app.close()
    app = await f.launch()
    page = await app.firstWindow()
    await reopen(page, target)
    const after = await page.evaluate(
      (id) => window.agent.getSession({ session_id: id, before_seq: null }),
      target
    )
    expect(after.ok && after.data.watermark).toBe(before.ok && before.data.watermark)
    expect(after.ok && after.data.summary.run?.run_id).toBe(
      before.ok && before.data.summary.run?.run_id
    )
    const afterSource = await page.evaluate(
      (id) => window.agent.getSession({ session_id: id, before_seq: null }),
      source
    )
    expect(afterSource.ok && afterSource.data.watermark).toBe(sourceView.data.watermark)
    expect(afterSource.ok && afterSource.data.summary.run).toEqual(sourceRun)
    const afterRequests = await page.evaluate(
      (id) => window.agent.listCollaboration({ session_id: id }),
      source
    )
    expect(afterRequests.ok && afterRequests.data.requests).toEqual(requests.data.requests)
    const afterIdle = await page.evaluate(() => window.agent.getActiveRuns())
    expect(afterIdle.ok && afterIdle.data.sessions).toEqual([])
    // 重启不创建新 Run、不追加请求或工具事实，来源与接收方日志均保持原样。
    // Restart creates no run or request/tool facts; both source and recipient logs stay intact.
    expect(await readFile(sourceFactsPath, 'utf8')).toBe(sourceFacts)
    expect(await readFile(targetFactsPath, 'utf8')).toBe(targetFacts)
    await page.locator('.tree-task').click()
    await expect(page.getByLabel('当前阶段', { exact: true })).toHaveValue('implement')
    await expect(page.getByLabel('已确认结论', { exact: true })).toHaveValue(
      '只使用本地资源，启动端口 8123。'
    )
    const restored = await page.evaluate((id) => window.agent.getTask(id), taskId)
    expect(restored.ok && restored.data.workflow?.session_stages?.[target]).toBe('handoff')
    await capture(page, f.root, '05-restarted-task')
    await writeFile(
      path.join(f.root, 'result.json'),
      JSON.stringify(
        { status: 'completed', restored, after, afterSource, afterRequests, afterIdle },
        null,
        2
      ),
      'utf8'
    )
  } catch (error) {
    if (page) await capture(page, f.root, 'failure').catch(() => undefined)
    throw error
  } finally {
    await app
      .evaluate(({ dialog }) => {
        dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
      })
      .catch(() => undefined)
    await app.close()
  }
})

/** 检查手动纠错的记忆、实际材料与历史面板，主动停止局部 Goal。 Inspect corrected memory, actual materials and history, then explicitly stop a local Goal. */
test('Long-task owner corrects memory, checks context and stops a local Goal', async () => {
  test.setTimeout(120000)
  const f = await fixture('memory')
  let app = await f.launch()
  let page: Page | undefined
  try {
    page = await createTask(app, f.project, '记忆纠错与局部目标')
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    const source = await page.locator('.tree-session.selected').getAttribute('data-session-id')
    if (!source) throw new Error('Missing source session')
    await page.getByTestId('open-memory').click()
    await page.getByRole('button', { name: '新增记忆', exact: true }).click()
    await page.getByLabel('记忆标题').fill('清单启动约定')
    await page.getByLabel('记忆正文').fill('清单端口 8000；资源必须离线。')
    await page.getByLabel('优先召回（仍受容量限制）').check()
    await page.getByRole('button', { name: '保存记忆', exact: true }).click()
    const results = page.getByTestId('memory-results')
    await expect(results).toContainText('清单启动约定')
    await results.locator(':scope > button').click()
    await results.getByRole('button', { name: /清单启动约定 · 本项目/ }).click()
    await results.getByRole('button', { name: '编辑', exact: true }).click()
    await page.getByLabel('记忆正文').fill('清单端口已改为 8123；资源必须离线。')
    await page.getByRole('button', { name: '保存记忆', exact: true }).click()
    await expect(results).toContainText('清单端口已改为 8123')
    await capture(page, f.root, '01-corrected-memory')
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()
    for (let index = 0; index < 3; index++)
      await send(
        page,
        'm3: 清单端口 context history ' + index + (index === 0 ? ' detail'.repeat(1400) : '')
      )
    await page.getByTestId('open-history').click()
    await page.getByTestId('history-query').locator(':scope > button').click()
    await page.getByLabel('历史搜索').fill('context history')
    await page.getByRole('button', { name: '查询历史', exact: true }).click()
    await expect(page.getByTestId('history-results')).toContainText('3 项匹配')
    const entry = page
      .getByTestId('history-results')
      .locator('[data-testid^="history-entry-"]')
      .first()
    await entry.locator(':scope > button').click()
    await expect(entry.locator('pre')).toContainText('context history 0')
    await entry.getByRole('button', { name: '加入这次提问', exact: true }).click()
    await capture(page, f.root, '02-history-fragment')
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()
    await expect(page.getByTestId('question-materials')).toContainText('历史 #')
    await page.locator('.tree-task').click()
    await page.locator(`.tree-session[data-session-id="${source}"]`).click()
    await expect(page.getByTestId('question-materials')).toContainText('历史 #')
    await send(page, 'm3: use attached context history with corrected 清单端口')
    await page.getByTestId('open-context').click()
    await page.getByTestId('request-materials').locator(':scope > button').click()
    await expect(page.getByTestId('request-materials')).toContainText('清单启动约定')
    const beforeCompact = await page.evaluate(
      (id) => window.agent.getContext({ session_id: id }),
      source
    )
    expect(beforeCompact.ok && JSON.stringify(beforeCompact.data.last_request)).toContain('8123')
    await page.getByRole('button', { name: '压缩当前会话', exact: true }).click()
    await expect(page.getByTestId('open-context')).toContainText('压缩后待计量')
    await page.getByTestId('summary').locator(':scope > button').click()
    await capture(page, f.root, '03-context-compacted')
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()
    await page.locator('.tree-task').click()
    await page.getByText('创建新的工作会话', { exact: true }).click()
    await page.getByLabel('会话角色', { exact: true }).fill('新接续会话')
    await page.getByRole('button', { name: '新建会话', exact: true }).click()
    const fresh = await page.locator('.tree-session.selected').getAttribute('data-session-id')
    if (!fresh) throw new Error('Missing fresh session')
    await send(page, 'm3: confirm 清单端口 and offline requirement')
    const recalled = await page.evaluate((id) => window.agent.getContext({ session_id: id }), fresh)
    expect(recalled.ok && JSON.stringify(recalled.data.last_request)).toContain('8123')
    expect(recalled.ok && JSON.stringify(recalled.data.last_request)).not.toContain('端口 8000')
    await page.getByTestId('open-context').click()
    await page.getByTestId('request-materials').locator(':scope > button').click()
    await capture(page, f.root, '04-new-session-materials')
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()
    await page.getByLabel('本次模式').selectOption('goal')
    await page.getByLabel('输入问题').fill('goal-test:hold 局部核对启动端口，等待显式停止')
    await page.getByRole('button', { name: '启动 Goal', exact: true }).click()
    await expect(page.getByTestId('goal-state')).toHaveText('active')
    await page.getByRole('button', { name: '停止运行', exact: true }).click()
    await expect(page.getByTestId('goal-state')).toHaveText('paused')
    await page.locator('.goal-heading').click()
    await capture(page, f.root, '05-goal-stopped')
    const stopped = await page.evaluate(
      (id) => window.agent.listGoals({ session_id: id, limit: 1 }),
      fresh
    )
    await app.close()
    app = await f.launch()
    page = await app.firstWindow()
    await reopen(page, fresh)
    await expect(page.getByTestId('goal-state')).toHaveText('paused')
    const active = await page.evaluate(() => window.agent.getActiveRuns())
    expect(active.ok && active.data.sessions.length).toBe(0)
    await page.locator('.goal-heading').click()
    await page.getByRole('button', { name: '取消 Goal', exact: true }).click()
    await expect(
      page.locator('[data-testid="goal-history"][data-status="cancelled"]')
    ).toBeVisible()
    await send(page, 'm3: ordinary continuation after cancelled goal')
    await expect(page.getByTestId('goal-panel')).toHaveCount(0)
    await capture(page, f.root, '06-cancelled-goal-history')
    const memory = await page.evaluate((id) => window.agent.listMemory({ session_id: id }), fresh)
    await writeFile(
      path.join(f.root, 'result.json'),
      JSON.stringify(
        { status: 'completed', source, fresh, beforeCompact, recalled, stopped, memory },
        null,
        2
      ),
      'utf8'
    )
    expect(await readFile(path.join(f.project, 'main.py'), 'utf8')).toBe(
      'def answer():\n    return 42\n'
    )
  } catch (error) {
    if (page) await capture(page, f.root, 'failure').catch(() => undefined)
    throw error
  } finally {
    await app
      .evaluate(({ dialog }) => {
        dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
      })
      .catch(() => undefined)
    await app.close()
  }
})
