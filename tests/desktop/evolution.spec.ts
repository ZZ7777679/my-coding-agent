/** M7 真实桌面资源采用和恢复，不调用模型。 Real M7 resource adoption/restoration without model calls. */
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import path from 'node:path'
import { electron, expect, test } from './runtime'
import { artifacts, choose, launch, python, sentinel } from './helpers'

test('evolution contextual entry shares screening and jobs with the independent page', async () => {
  test.setTimeout(60000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-m7-contextual-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n')
  await writeFile(path.join(project, 'answer.py'), 'value = 1\n')
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
    await page.getByLabel('阶段目标', { exact: true }).fill('Contextual review sample')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await expect(page.getByText('复盘此任务', { exact: true })).toBeVisible()
    await page.getByText('复盘此任务', { exact: true }).click()
    await page.getByRole('button', { name: '自定义范围与预算', exact: true }).click()
    await expect(page.locator('.evolution-inherited')).toContainText('已带入任务范围')
    await page.locator('.tree-task').first().click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByLabel('输入问题').fill('Read main.py for the review sample')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByText('main.py:2 返回 42。不执行脚本', { exact: true })).toBeVisible()
    await expect(page.getByText('复盘此会话', { exact: true })).toBeVisible()
    await page.getByText('复盘此会话', { exact: true }).click()
    await page.getByRole('textbox', { name: '关注点（可选）', exact: true }).fill('read_file')
    await page.getByRole('button', { name: '开始复盘', exact: true }).click()
    await expect(page.locator('.evolution-quick [role=status]')).toContainText('调查完成', {
      timeout: 15000
    })
    await page.screenshot({ path: path.join(root, 'quick-review.png') })
    const before = await page.evaluate(async () => {
      const projects = await window.agent.listProjects()
      if (!projects.ok || !projects.data.active_project) throw new Error('Missing project')
      const jobs = await window.agent.evolutionList({
        project_id: projects.data.active_project.project_id
      })
      if (!jobs.ok) throw new Error(jobs.error.message)
      return { pid: projects.data.active_project.project_id, jobs: jobs.data.jobs ?? [] }
    })
    expect(before.jobs).toHaveLength(1)
    expect(before.jobs[0].origin?.kind).toBe('session')
    await page.getByRole('button', { name: '查看本次改进', exact: true }).click()
    const job = page.locator(`#evolution-job-${before.jobs[0].job_id}`)
    await expect(job).toHaveAttribute('open', '')
    await job.getByRole('button', { name: '查看实际参考材料', exact: true }).click()
    const panel = page.getByRole('dialog', { name: '改进证据', exact: true })
    await expect(panel).toBeInViewport({ ratio: 1 })
    await expect(panel.locator('.evolution-screening')).toBeVisible()
    await expect(panel.getByLabel('调查阅读覆盖')).toContainText('已读 1 项')
    await page.screenshot({ path: path.join(root, 'screening.png') })
    await page.keyboard.press('Escape')
    const after = await page.evaluate(
      (pid) => window.agent.evolutionList({ project_id: pid }),
      before.pid
    )
    expect(after.ok && after.data.jobs?.length).toBe(1)
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await expect(page.locator('.evolution-quick')).toHaveCount(1)
    await page.screenshot({ path: path.join(root, 'project-entry.png') })
    await page.getByText('复盘此项目', { exact: true }).click()
    await page.getByRole('button', { name: '自定义范围与预算', exact: true }).click()
    await expect(page.locator('.evolution-inherited')).toContainText('已带入项目范围')
    await page.getByRole('button', { name: '清除继承范围，手动选材', exact: true }).click()
    await expect(page.locator('.evolution-inherited')).toHaveCount(0)
  } finally {
    await app.close()
  }
})

test('evolution saves independent budgets in the module and restores them after restart', async () => {
  test.setTimeout(60000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-m7-budget-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  let app = await launch(data, project)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    const original = await page.evaluate(() => window.agent.getConfig())
    expect(original.ok).toBe(true)
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    const start = page.getByRole('button', { name: '开始改进', exact: true })
    await expect(start).toBeInViewport()
    const summary = page.locator('.evolution-budget > summary')
    await expect(summary).toBeInViewport()
    await summary.click()
    const budget = page.locator('.evolution-budget')
    const values: Array<[string, string]> = [
      ['模型请求次数', '40'],
      ['工具调用次数', '90'],
      ['总运行时间（秒）', '1200'],
      ['单请求总时限（秒）', '240'],
      ['每次输出 token 上限', '12000'],
      ['参考材料正文预算（字符）', '64000']
    ]
    for (const [label, value] of values) await budget.getByLabel(label, { exact: true }).fill(value)
    await budget.getByRole('button', { name: '保存改进预算', exact: true }).click()
    await expect(budget.getByRole('status')).toHaveText('改进预算已保存，对下一次调查或生成生效。')
    await expect(summary).toContainText('请求 40 次 · 工具 90 次 · 总时限 1200 秒')
    expect(await page.evaluate(() => window.agent.getConfig())).toEqual(original)
    await page.screenshot({ path: path.join(root, 'budget.png') })
    await summary.click()
    await expect(start).toBeInViewport()
    await app.close()
    app = await launch(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await page.locator('.evolution-budget > summary').click()
    for (const [label, value] of values)
      await expect(
        page.locator('.evolution-budget').getByLabel(label, { exact: true })
      ).toHaveValue(value)
    expect(await page.evaluate(() => window.agent.getConfig())).toEqual(original)
    await page.getByText('高级容量设置', { exact: true }).click()
    const labels = [
      ...values.map(([label]) => label),
      '累计调查上下文容量（字节）',
      '单次模型响应容量（字节）'
    ]
    for (const label of labels) {
      await page.getByRole('checkbox', { name: `${label}不限`, exact: true }).check()
      await expect(
        page.locator('.evolution-budget').getByLabel(label, { exact: true })
      ).toBeDisabled()
    }
    // 来回切换保留本页原数值；保存后持久化的是 null 而非巨大数字。
    // Toggling restores local numbers; persisted unlimited values are null, not huge numbers.
    await page.getByRole('checkbox', { name: '模型请求次数不限', exact: true }).uncheck()
    await expect(
      page.locator('.evolution-budget').getByLabel('模型请求次数', { exact: true })
    ).toHaveValue('40')
    await page.getByRole('checkbox', { name: '模型请求次数不限', exact: true }).check()
    await page.getByRole('button', { name: '保存改进预算', exact: true }).click()
    await expect(page.locator('.evolution-budget > summary')).toContainText(
      '请求 不限 · 工具 不限 · 总时限 不限'
    )
    await page.screenshot({ path: path.join(root, 'unlimited.png') })
    await app.close()
    app = await launch(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await page.locator('.evolution-budget > summary').click()
    await page.getByText('高级容量设置', { exact: true }).click()
    for (const label of labels) {
      await expect(page.getByRole('checkbox', { name: `${label}不限`, exact: true })).toBeChecked()
      await expect(
        page.locator('.evolution-budget').getByLabel(label, { exact: true })
      ).toBeDisabled()
    }
    await page.getByRole('checkbox', { name: '模型请求次数不限', exact: true }).uncheck()
    await page.locator('.evolution-budget').getByLabel('模型请求次数', { exact: true }).fill('8')
    await page.getByRole('button', { name: '保存改进预算', exact: true }).click()
    await expect(page.locator('.evolution-budget > summary')).toContainText(
      '请求 8 次 · 工具 不限 · 总时限 不限'
    )
    expect(await page.evaluate(() => window.agent.getConfig())).toEqual(original)
  } finally {
    await app.close()
  }
})

test('evolution resource edits restore and persist through restart', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-m7-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  await writeFile(path.join(project, 'AGENTS.md'), 'Keep changes focused.\n')
  await writeFile(path.join(project, 'answer.py'), 'value = 1\n')
  let app = await launch(data, project)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await expect(page.getByRole('heading', { name: '经验与改进', exact: true })).toBeVisible()
    await page.getByText('指定资源快捷入口', { exact: true }).click()
    await page.getByRole('checkbox', { name: '我已确定要修改的资源', exact: true }).check()
    await page.getByRole('button', { name: '读取当前内容', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('已读取当前版本')
    await page.getByText('手动编写候选', { exact: true }).click()
    await page.getByLabel('建议完整内容').fill('Keep changes focused. Explain results briefly.\n')
    await page.getByRole('button', { name: '保存候选', exact: true }).click()
    await expect(page.getByRole('button', { name: '采用候选', exact: true })).toBeVisible()
    // 页面与候选切换保留草稿；已保存资源保持原样。
    // Navigation and candidate switches retain drafts without changing the resource.
    await page.getByLabel('建议完整内容').fill('Unsaved focused draft.\n')
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await expect(page.getByLabel('建议完整内容')).toHaveValue('Unsaved focused draft.\n')
    await page.getByRole('button', { name: '关闭详情', exact: true }).click()
    await page.getByRole('button', { name: '项目规范改进', exact: true }).click()
    await expect(page.getByLabel('建议完整内容')).toHaveValue('Unsaved focused draft.\n')
    await page.getByLabel('建议完整内容').fill('Keep changes focused. Explain results briefly.\n')
    await page.getByRole('button', { name: '采用候选', exact: true }).click()
    await expect(page.getByRole('button', { name: '恢复修改前版本', exact: true })).toBeVisible()
    expect(await readFile(path.join(project, 'AGENTS.md'), 'utf8')).toBe(
      'Keep changes focused. Explain results briefly.\n'
    )
    await page.getByRole('button', { name: '恢复修改前版本', exact: true }).click()
    await expect(page.getByRole('button', { name: '采用候选', exact: true })).toBeVisible()
    expect(await readFile(path.join(project, 'AGENTS.md'), 'utf8')).toBe('Keep changes focused.\n')
    await page.getByRole('button', { name: '关闭详情', exact: true }).click()
    await page.getByText('指定资源快捷入口', { exact: true }).click()
    await page.getByLabel('改进对象类型', { exact: true }).selectOption('code')
    await page.getByLabel('目标 项目相对文件路径').fill('answer.py')
    await page.getByRole('button', { name: '读取当前内容', exact: true }).click()
    await page.getByText('手动编写候选', { exact: true }).click()
    await page.getByLabel('建议完整内容').fill('value = 2\n')
    await page.getByRole('button', { name: '保存候选', exact: true }).click()
    await page.getByText('独立代码实验', { exact: true }).click()
    await page
      .getByLabel('PowerShell 检查命令')
      .fill(`& '${python.replaceAll("'", "''")}' -c "import answer; assert answer.value == 2"`)
    await page.getByRole('button', { name: '比较原版与候选', exact: true }).click()
    const experiment = page
      .locator('details')
      .filter({
        has: page.locator('summary').filter({ hasText: '原版 exit=1，候选 exit=0' })
      })
      .first()
    await expect(experiment).toBeVisible()
    await experiment.locator('summary').first().click()
    await page.getByRole('button', { name: '读取实验详情', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '改进证据' })).toBeInViewport()
    await page.getByRole('button', { name: '关闭证据', exact: true }).click()
    await page.getByLabel('建议完整内容').fill('value = 3\n')
    await page.getByRole('button', { name: '保存候选', exact: true }).click()
    await expect(page.getByText(/旧版本结果，已过期/).first()).toBeVisible()
    expect(await readFile(path.join(project, 'answer.py'), 'utf8')).toBe('value = 1\n')
    await page.getByRole('button', { name: '关闭详情', exact: true }).click()
    await page.getByLabel('改进对象类型', { exact: true }).selectOption('preference')
    await page.getByText('手动编写候选', { exact: true }).click()
    await page.getByLabel('记忆标题', { exact: true }).fill('短总结')
    await page.getByLabel('记忆正文', { exact: true }).fill('优先简短说明实际结果。')
    await page.getByRole('button', { name: '保存候选', exact: true }).click()
    await page.getByRole('button', { name: '采用候选', exact: true }).click()
    await expect(page.getByRole('button', { name: '恢复修改前版本', exact: true })).toBeVisible()
    await page.getByLabel('反馈或改进要求').fill('保留明确来源，不把猜测记成事实。')
    await page.getByText('补充说明与保存反馈（可选）', { exact: true }).click()
    await page.getByRole('button', { name: '保存反馈', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('反馈已保存')
    await page.screenshot({ path: path.join(root, 'evolution.png'), fullPage: true })
    await app.close()
    app = await launch(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await page.getByText('指定资源快捷入口', { exact: true }).click()
    await page.getByRole('checkbox', { name: '我已确定要修改的资源', exact: true }).check()
    await expect(page.getByText('个人偏好改进', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '个人偏好改进', exact: true }).click()
    await expect(page.getByLabel('记忆正文', { exact: true })).toHaveValue('优先简短说明实际结果。')
    await page.getByRole('button', { name: '关闭详情', exact: true }).click()
    await expect(page.getByRole('button', { name: '恢复修改前版本', exact: true })).toHaveCount(0)
  } finally {
    await app.close()
  }
})

test('evolution selects a named run and exposes the actual review materials', async () => {
  test.setTimeout(60000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-m7-evidence-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n')
  await writeFile(path.join(project, 'AGENTS.md'), 'Keep changes focused.\n')
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
    await page.getByLabel('阶段目标', { exact: true }).fill('Review evidence sample')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByLabel('输入问题').fill('Read main.py for the review sample')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByText('main.py:2 返回 42。不执行脚本', { exact: true })).toBeVisible()
    // 超过目录一页，确保旧轮不会被最近 Trace 的数量遮住。
    // Exceed one run page so older turns cannot disappear behind recent Trace events.
    await page.evaluate(async () => {
      const projects = await window.agent.listProjects()
      if (!projects.ok || !projects.data.active_project) throw new Error('Missing project')
      const sessions = await window.agent.listSessions({
        project_id: projects.data.active_project.project_id,
        cursor: null,
        limit: 30
      })
      if (!sessions.ok) throw new Error(sessions.error.message)
      const sid = sessions.data.sessions[0].session_id
      for (let i = 0; i < 21; i++) {
        const started = await window.agent.startRun({
          session_id: sid,
          operation_id: crypto.randomUUID(),
          prompt: `m3: evidence run ${i}`,
          limits: null,
          mode: 'plan'
        })
        if (!started.ok) throw new Error(started.error.message)
        for (;;) {
          const view = await window.agent.getSession({ session_id: sid, before_seq: null })
          if (!view.ok) throw new Error(view.error.message)
          if (view.data.summary.run?.status === 'completed') break
          if (view.data.summary.run?.status === 'failed') throw new Error('Fixture run failed')
          await new Promise((resolve) => setTimeout(resolve, 20))
        }
      }
    })
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await page.getByText('从会话 / Trace 选择', { exact: true }).click()
    await page.getByText('指定资源快捷入口', { exact: true }).click()
    await page.getByRole('checkbox', { name: '我已确定要修改的资源', exact: true }).check()
    await page.getByRole('button', { name: '读取项目会话', exact: true }).click()
    await expect(page.getByLabel('参考会话')).toBeVisible()
    await page.getByLabel('参考会话').selectOption({ index: 1 })
    await expect(page.getByText(/已加载 20 \/ 22 轮/)).toBeVisible()
    await expect(page.getByRole('checkbox', { name: /指定运行 · Read main.py/ })).toHaveCount(0)
    await page.getByRole('button', { name: '加载更早运行（保留当前列表）', exact: true }).click()
    await expect(page.getByText(/已加载 22 \/ 22 轮/)).toBeVisible()
    await page.getByRole('checkbox', { name: /指定运行 · Read main.py/ }).check()
    await page.getByRole('checkbox', { name: /指定运行 · m3: evidence run 0 ·/ }).check()
    await page
      .getByLabel('反馈或改进要求')
      .fill('Use this read trace to improve our project guidance.')
    await page.getByRole('button', { name: '预览本次参考材料', exact: true }).click()
    await expect(page.getByText('本次待参考材料', { exact: true })).toBeVisible()
    await expect(page.getByLabel('实际选材范围')).toContainText('指定运行')
    await page.getByRole('button', { name: '关闭证据', exact: true }).click()
    await page.getByLabel('选材范围', { exact: true }).selectOption('session')
    await page.getByRole('checkbox', { name: /参考整个会话 · 22 轮/ }).check()
    await page.getByRole('button', { name: '预览本次参考材料', exact: true }).click()
    await expect(page.getByLabel('实际选材范围')).toContainText('整个会话')
    await page.getByRole('button', { name: '关闭证据', exact: true }).click()
    await page.getByLabel('选材范围', { exact: true }).selectOption('event')
    await page
      .locator('.evolution-run-list .evolution-entry')
      .filter({ hasText: 'Read main.py for the review sample' })
      .getByRole('button', { name: '选择本轮事件', exact: true })
      .click()
    await page.getByRole('checkbox', { name: /单条事件.*read_file/ }).check()
    const previewButton = page.getByRole('button', { name: '预览本次参考材料', exact: true })
    await previewButton.scrollIntoViewIfNeeded()
    const pagePosition = await page
      .locator('main.workspace')
      .evaluate((element) => element.scrollTop)
    await previewButton.click()
    const evidencePanel = page.getByRole('dialog', { name: '改进证据', exact: true })
    await expect(evidencePanel).toBeInViewport({ ratio: 1 })
    await expect(
      evidencePanel.getByRole('button', { name: '关闭证据', exact: true })
    ).toBeInViewport()
    await expect(page.getByLabel('实际选材范围')).toContainText('去重后 1 条 Trace')
    const input = page.locator('.evolution-input').first()
    await input
      .locator('summary')
      .filter({ hasText: /read_file/ })
      .first()
      .click()
    await expect(input.locator('pre').filter({ hasText: 'return 42' }).first()).toContainText(
      'return 42'
    )
    await input
      .getByRole('button', { name: '查看代表记录', exact: true })
      .filter({ visible: true })
      .first()
      .click()
    const trace = page.getByRole('complementary', { name: '执行轨迹', exact: true })
    await expect(trace).toBeInViewport()
    await expect(
      evidencePanel.getByRole('button', { name: '返回参考材料', exact: true })
    ).toBeInViewport()
    await expect(trace.getByRole('button', { name: '关闭 Trace', exact: true })).toHaveCount(0)
    await page.screenshot({ path: path.join(root, 'trace-panel.png') })
    await evidencePanel.getByRole('button', { name: '返回参考材料', exact: true }).click()
    await expect(evidencePanel).toBeVisible()
    await expect(input.locator('pre').filter({ hasText: 'return 42' }).first()).toBeVisible()
    await evidencePanel.getByRole('button', { name: '关闭证据', exact: true }).click()
    await expect(previewButton).toBeFocused()
    expect(await page.locator('main.workspace').evaluate((element) => element.scrollTop)).toBe(
      pagePosition
    )
    await expect(evidencePanel).toHaveCount(0)

    // 从页面中部直接打开 Trace；窄窗口也不依赖聊天布局，Esc 返回原入口。
    // Open Trace directly mid-page; narrow windows need no chat layout and Escape restores the trigger.
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1000, 740))
    const origin = page
      .getByLabel('已选参考材料')
      .getByRole('button', { name: '定位原始记录' })
      .first()
    await origin.scrollIntoViewIfNeeded()
    const sourcePosition = await page
      .locator('main.workspace')
      .evaluate((element) => element.scrollTop)
    await origin.click()
    await expect(evidencePanel).toBeInViewport({ ratio: 1 })
    await expect(trace).toBeInViewport()
    await page.keyboard.press('Escape')
    await expect(evidencePanel).toHaveCount(0)
    await expect(origin).toBeFocused()
    expect(await page.locator('main.workspace').evaluate((element) => element.scrollTop)).toBe(
      sourcePosition
    )
    await page.getByRole('heading', { name: '参考哪些记录', exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(root, 'selection.png') })
    await expect(page.getByText('本次待参考材料', { exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: '开始改进', exact: true }).click()
    const job = page
      .locator('details.detail-card')
      .filter({
        has: page.locator('summary').filter({ hasText: '调查完成' })
      })
      .first()
    await expect(job).toBeVisible()
    await job.locator('summary').first().click()
    await job.getByRole('button', { name: '查看候选', exact: true }).click()
    await page.getByRole('button', { name: '查看所属调查的全部材料', exact: true }).click()
    await expect(page.locator('.evolution-input')).toHaveCount(1)
    const actual = page.locator('.evolution-input').last()
    await actual.getByText('你的本次要求', { exact: true }).click()
    await expect(actual.locator('pre').filter({ hasText: 'Use this read trace' })).toBeVisible()
    await expect(evidencePanel).toBeInViewport({ ratio: 1 })
    await page.getByRole('button', { name: '关闭证据', exact: true }).click()
    await page.screenshot({ path: path.join(root, 'evidence.png'), fullPage: true })
  } finally {
    await app.close()
  }
})

test('evolution investigates cross-project evidence and keeps independent candidate drafts', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-m7-investigation-'))
  const sourceProject = path.join(root, 'business-project')
  const targetProject = path.join(root, 'harness-project')
  await mkdir(sourceProject)
  await mkdir(targetProject)
  await writeFile(path.join(sourceProject, 'main.py'), 'def answer():\n    return 42\n')
  await writeFile(path.join(targetProject, 'answer.py'), 'value = 1\n')
  const env: Record<string, string> = {}
  for (const [key, value] of Object.entries(process.env)) if (value !== undefined) env[key] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = sourceProject
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
    await choose(app, sourceProject)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('Source execution')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByLabel('输入问题').fill('Read main.py for the review sample')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByText('main.py:2 返回 42。不执行脚本', { exact: true })).toBeVisible()
    const sourceId = await page.evaluate(async () => {
      const result = await window.agent.listProjects()
      if (!result.ok || !result.data.active_project) throw new Error('Source project missing')
      return result.data.active_project.project_id
    })
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await choose(app, targetProject)
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    // 检查首屏可发现性；toBeVisible 和点击的自动滚动无法证明入口不用找。
    // Verify first-screen discoverability; visibility and auto-scrolling clicks cannot prove it.
    await expect(page.getByRole('button', { name: '开始改进', exact: true })).toBeInViewport()
    await expect(page.getByLabel('反馈或改进要求')).toBeInViewport()
    await expect(page.getByRole('button', { name: '开始改进', exact: true })).toBeEnabled()
    await expect(page.getByRole('button', { name: '保存反馈', exact: true })).toBeHidden()
    await page.screenshot({ path: path.join(root, 'start.png') })
    await expect(page.getByLabel('改进对象类型')).toBeHidden()
    await page.getByLabel('参考记录所在项目').selectOption(sourceId)
    await page.getByText('从会话 / Trace 选择', { exact: true }).click()
    await page.getByRole('button', { name: '读取项目会话', exact: true }).click()
    await page.getByLabel('参考会话').selectOption({ index: 1 })
    await page.getByRole('checkbox', { name: /指定运行 · Read main.py/ }).check()
    await page
      .getByLabel('反馈或改进要求')
      .fill('Investigate the usage and implementation separately.')
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await expect(page.getByLabel('反馈或改进要求')).toHaveValue(
      'Investigate the usage and implementation separately.'
    )
    await expect(page.getByLabel('已选参考材料')).toContainText('business-project')
    await page.getByRole('button', { name: '开始改进', exact: true }).click()
    await expect(page.getByRole('button', { name: '查看本次改进进度', exact: true })).toBeVisible()
    const investigation = page
      .locator('details.detail-card')
      .filter({
        has: page.locator('summary').filter({ hasText: '调查完成 · 2 项发现 · 0 个候选' })
      })
      .first()
    await expect(investigation).toBeVisible()
    await expect(investigation.locator('summary').first()).toContainText('请求 6')
    await page.getByRole('button', { name: '查看本次改进进度', exact: true }).click()
    await expect(investigation).toHaveAttribute('open', '')
    await expect(
      investigation.getByRole('checkbox', { name: 'Clarify reading usage', exact: true })
    ).toBeChecked()
    await expect(
      investigation.getByRole('checkbox', { name: 'Correct answer implementation', exact: true })
    ).toBeChecked()
    await investigation
      .getByRole('checkbox', { name: 'Correct answer implementation', exact: true })
      .uncheck()
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await page.getByRole('button', { name: '查看本次改进进度', exact: true }).click()
    await expect(
      investigation.getByRole('checkbox', { name: 'Correct answer implementation', exact: true })
    ).not.toBeChecked()
    await investigation
      .getByRole('checkbox', { name: 'Correct answer implementation', exact: true })
      .check()
    await investigation.getByRole('button', { name: '查看实际参考材料', exact: true }).click()
    const evidencePanel = page.getByRole('dialog', { name: '改进证据', exact: true })
    await expect(evidencePanel).toBeInViewport({ ratio: 1 })
    await expect(evidencePanel.getByLabel('调查阅读覆盖')).toContainText('已读 1 项')
    await expect(evidencePanel.getByText('模型最终返回（排查格式）', { exact: true })).toBeVisible()
    await evidencePanel.getByRole('button', { name: '关闭证据', exact: true }).click()
    await investigation
      .getByRole('heading', { name: '调查发现与建议', exact: true })
      .scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(root, 'findings.png') })
    await investigation.getByRole('button', { name: '生成所选问题的关联候选', exact: true }).click()
    const proposals = page
      .locator('details.detail-card')
      .filter({
        has: page.locator('summary').filter({ hasText: '调查完成 · 2 项发现 · 2 个候选' })
      })
      .first()
    await expect(proposals).toBeVisible()
    await proposals.locator('summary').first().click()
    await proposals.getByRole('button', { name: '查看候选 1', exact: true }).click()
    await expect(page.getByLabel('建议完整内容')).toHaveValue(
      'Read relevant files before proposing changes.\n'
    )
    await page.getByLabel('建议完整内容').fill('Keep this unsaved candidate draft.\n')
    await proposals.getByRole('button', { name: '查看候选 2', exact: true }).click()
    await expect(page.getByLabel('建议完整内容')).toHaveValue('value = 2\n')
    await page.getByRole('button', { name: '采用候选', exact: true }).click()
    await expect(page.getByRole('button', { name: '恢复修改前版本', exact: true })).toBeVisible()
    expect(await readFile(path.join(targetProject, 'answer.py'), 'utf8')).toBe('value = 2\n')
    expect(await readFile(path.join(sourceProject, 'main.py'), 'utf8')).toContain('return 42')
    await page.getByRole('button', { name: '恢复修改前版本', exact: true }).click()
    await expect(page.getByRole('button', { name: '采用候选', exact: true })).toBeVisible()
    expect(await readFile(path.join(targetProject, 'answer.py'), 'utf8')).toBe('value = 1\n')
    await proposals.getByRole('button', { name: '查看候选 1', exact: true }).click()
    await expect(page.getByLabel('建议完整内容')).toHaveValue(
      'Keep this unsaved candidate draft.\n'
    )
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await expect(page.getByLabel('建议完整内容')).toHaveValue(
      'Keep this unsaved candidate draft.\n'
    )
    await page.getByLabel('反馈或改进要求').fill('Record another focused investigation.')
    await page.evaluate(async () => {
      const result = await window.agent.listProjects()
      if (!result.ok || !result.data.active_project) throw new Error('Target missing')
      const project_id = result.data.active_project.project_id
      const settings = await window.agent.evolutionConfigure({ project_id, automatic_review: true })
      if (!settings.ok) throw new Error(settings.error.message)
    })
    await page.getByText('补充说明与保存反馈（可选）', { exact: true }).click()
    await page.getByRole('button', { name: '保存反馈', exact: true }).click()
    await expect(
      page.getByRole('status').filter({ hasText: '反馈已保存并已启动复盘' })
    ).toBeVisible()
    const count = async () =>
      page.evaluate(async () => {
        const projects = await window.agent.listProjects()
        if (!projects.ok || !projects.data.active_project) throw new Error('Target missing')
        const result = await window.agent.evolutionList({
          project_id: projects.data.active_project.project_id
        })
        if (!result.ok) throw new Error(result.error.message)
        return result.data.jobs?.length ?? 0
      })
    const before = await count()
    await page.getByRole('button', { name: '查看本次改进进度', exact: true }).click()
    expect(await count()).toBe(before)
    // 原调查可以再次生成，导航不会把候选入口永久锁在旧作业。
    // Regenerate from the original investigation instead of trapping the entry on its old job.
    await investigation.locator('summary').first().click()
    await investigation.getByRole('button', { name: '沿原调查重新生成候选', exact: true }).click()
    await expect.poll(count).toBe(before + 1)
    await expect(
      page.getByRole('button', { name: '提炼为经验候选', exact: true }).first()
    ).toBeVisible()
    const history = await page.evaluate(async () => {
      const projects = await window.agent.listProjects()
      if (!projects.ok || !projects.data.active_project) throw new Error('Target missing')
      const pid = projects.data.active_project.project_id
      const result = await window.agent.evolutionList({ project_id: pid })
      if (!result.ok) throw new Error(result.error.message)
      return { pid, job: result.data.jobs!.find((job) => job.status === 'completed')! }
    })
    const originalId = await investigation.getAttribute('id')
    for (let index = 0; index < 33; index++) {
      const id = randomUUID()
      await writeFile(
        path.join(root, 'data', 'evolution', history.pid, 'jobs', `${id}.json`),
        JSON.stringify({
          ...history.job,
          job_id: id,
          updated_at: '2099-01-01T00:00:00Z',
          message: `History fixture ${index}`,
          findings: [],
          candidate_ids: [],
          candidate_id: null,
          review_input: null,
          request: null
        })
      )
    }
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await page.getByRole('button', { name: '经验与改进', exact: true }).click()
    await page.getByRole('button', { name: '查看本次改进进度', exact: true }).click()
    await expect(page.locator('details[id^="evolution-job-"][open]')).toHaveCount(1)
    await page.getByRole('button', { name: '更早的调查与候选生成', exact: true }).click()
    await expect(page.locator(`#${originalId}`)).toBeVisible()
    await expect(
      page.getByRole('button', { name: '更早的调查与候选生成', exact: true })
    ).toHaveCount(0)
    await page.screenshot({ path: path.join(root, 'investigation.png'), fullPage: true })
  } finally {
    await app.close()
  }
})
