/** 日常编码用户的隔离体验记录；模型决策为替身，界面与执行使用真实实现。
 * Record an isolated coding persona journey with model decisions substituted and real UI/execution.
 */
import { electron, expect, test, type ElectronApplication } from './runtime'
import { artifacts, choose, python, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import path from 'node:path'

/** 为真实本地服务选择空闲端口。 Allocate an available port for the real local service. */
async function availablePort(): Promise<number> {
  const server = createServer()
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('No TCP endpoint')
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve()))
  )
  return address.port
}

/** 记录真实用户入口、结果和界面几何，不更改产品实现。 Observe real entry points and layout. */
test('coding persona creates, inspects, stops and resumes work', async () => {
  test.setTimeout(120000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'persona-coding-'))
  const project = path.join(root, 'coding project')
  const data = path.join(root, 'data')
  await mkdir(project)
  await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n', 'utf8')
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  const pathName = Object.keys(env).find((name) => name.toLowerCase() === 'path') ?? 'PATH'
  env[pathName] = path.dirname(python) + path.delimiter + (env[pathName] ?? '')
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const observations: Record<string, unknown> = { root, project, simulatedModel: true }
  const errors: string[] = []
  let stage = 'launch'
  /** 保持同一隔离数据根，重启不改应用文件。 Relaunch with the same isolated application data. */
  const launch = (): Promise<ElectronApplication> =>
    electron.launch({
      args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', data],
      env
    })
  let app = await launch()
  let page = await app.firstWindow()
  page.on('pageerror', (error) => errors.push(error.message))
  /** 留存阶段界面及可见文字，方便复核用户实际看到什么。 Save screenshots and visible text. */
  const capture = async (name: string): Promise<void> => {
    await page.screenshot({ path: path.join(root, `${name}.png`) })
    await writeFile(path.join(root, `${name}.txt`), await page.locator('body').innerText(), 'utf8')
  }
  try {
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    stage = 'create-task'
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('日常编码体验')
    await page
      .getByLabel('阶段目标', { exact: true })
      .fill('修改 Python 文件并运行一个本地 Notes 页面')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await capture('01-task-created')
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    observations.navigation = await page
      .getByRole('navigation', { name: '项目任务会话' })
      .innerText()

    stage = 'stream-stop-switch-model'
    await page.getByLabel('输入问题').fill('read and wait')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('reasoning-content')).toContainText('再核对第 2 行的返回值。')
    await page.getByLabel('会话模型', { exact: true }).selectOption('deepseek-v4.1-flash')
    await expect(page.getByLabel('会话模型', { exact: true })).toHaveValue('deepseek-v4.1-flash')
    await expect(page.getByTestId('chat-history')).toContainText('第 2 行返回 42')
    observations.activeModel = await page.locator('.stream > strong').innerText()
    await capture('02-stream-and-model-switch')
    await page.locator('.stream .reasoning-block > summary').click()
    await expect(page.getByTestId('reasoning-content')).not.toBeVisible()
    await page.getByRole('button', { name: '停止运行', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('已停止')
    observations.stopStatus = await page.getByTestId('run-status').innerText()
    await page.getByLabel('输入问题').fill('finish with source')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(page.locator('.chat-message.assistant > strong').last()).toHaveText(
      'DeepSeek V4.1 Flash'
    )
    observations.resume = await page.locator('.chat-message.assistant').last().innerText()

    stage = 'failure-and-trace'
    await page.getByLabel('输入问题').fill('fail now')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('MODEL_TIMEOUT')
    await capture('03-model-failure')
    await page.getByRole('button', { name: 'Trace', exact: true }).click()
    const trace = page.getByRole('complementary', { name: '执行轨迹', exact: true })
    await trace.getByLabel('仅失败').check()
    await expect(trace.locator('.trace-row')).not.toHaveCount(0)
    observations.failedTrace = await trace.innerText()
    await trace.locator('.trace-row > summary').last().click()
    await expect(trace.locator('.trace-row[open] pre')).toContainText('MODEL_TIMEOUT')
    await capture('04-failed-trace')
    await trace.getByRole('button', { name: '关闭 Trace', exact: true }).click()

    stage = 'edit-and-diff'
    await page.getByLabel('输入问题').fill('files:create')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await page.getByLabel('输入问题').fill('files:edit')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect.poll(() => readFile(path.join(project, 'src/main.py'), 'utf8')).toBe('print(2)\n')
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.getByRole('button', { name: '查看修改成果', exact: true }).click()
    const changes = page.getByRole('complementary', { name: '修改成果' })
    await changes
      .getByRole('button', { name: 'src/main.py · 编辑 · 已保存到项目', exact: true })
      .click()
    await expect(page.getByTestId('change-diff')).toContainText('-print(1)')
    await expect(page.getByTestId('change-diff')).toContainText('+print(2)')
    await capture('05-file-diff')
    observations.diff = await page.getByTestId('change-diff').innerText()
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.getByRole('button', { name: '收起修改成果', exact: true }).click()
    const editAction = page
      .locator('.tool-summary > button')
      .filter({ hasText: 'edit_file' })
      .last()
    await editAction.click()
    await expect(trace.locator('.trace-row[open]')).toContainText('edit_file')
    await trace
      .locator('.trace-row[open]')
      .getByRole('button', { name: '参数', exact: true })
      .click()
    await trace.locator('.trace-row[open]').getByText('原始参数', { exact: true }).click()
    await expect(trace.locator('.trace-row[open] pre').first()).toContainText('print(1)')
    await trace.getByLabel('筛选工具').fill('edit_file')
    await expect(trace.locator('.trace-row')).toHaveCount(1)
    observations.filteredTrace = await trace.innerText()
    await capture('06-filtered-trace')
    await trace.getByRole('button', { name: '关闭 Trace', exact: true }).click()
    const fold = page
      .getByRole('button', { name: '折叠本轮过程 · 2 次工具调用', exact: true })
      .last()
    await fold.click()
    await expect(
      page.getByRole('button', { name: '展开本轮过程 · 2 次工具调用', exact: true })
    ).toBeVisible()
    await page.getByRole('button', { name: '展开本轮过程 · 2 次工具调用', exact: true }).click()

    stage = 'real-program'
    const port = await availablePort()
    const url = `http://127.0.0.1:${port}/`
    await page.getByLabel('输入问题').fill(`program:create:${port}`)
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(page.getByTestId('chat-history')).toContainText('已创建并运行 Notes 小应用')
    await expect(page.getByRole('button', { name: '停止运行', exact: true })).toHaveCount(0)
    expect((await fetch(url)).status).toBe(200)
    observations.programSource = await readFile(path.join(project, 'app.py'), 'utf8')
    observations.quickControls = await page.locator('.program-quick-controls').allInnerTexts()
    await capture('07-running-program-chat')
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    const card = page.locator('.program-card').filter({ hasText: 'HTTP 已响应' })
    await expect(card).toHaveCount(1)
    await expect(card).not.toHaveAttribute('open', '')
    await card.locator(':scope > summary').click()
    await expect(card.getByLabel('程序输出')).toContainText('Starting Notes app')
    await card.getByLabel('程序输出').scrollIntoViewIfNeeded()
    await capture('08-program-expanded')
    await card.locator(':scope > summary').click()
    await expect(card).not.toHaveAttribute('open', '')

    stage = 'new-session-and-return'
    await page.locator('.tree-task').first().click()
    await page.getByText('创建新的工作会话', { exact: true }).click()
    await page.getByLabel('会话角色', { exact: true }).fill('复查')
    await page.getByLabel('工作范围', { exact: true }).fill('只读查看运行结果')
    await page.getByRole('button', { name: '新建会话', exact: true }).click()
    await expect(page.locator('.session-membership')).toContainText('复查')
    observations.secondSessionInitiallyEmpty = (await page.locator('.tool-summary').count()) === 0
    expect((await fetch(url)).status).toBe(200)
    await page.locator('.tree-session').filter({ hasText: 'read and wait' }).click()
    await expect(page.getByLabel('会话模型', { exact: true })).toHaveValue('deepseek-v4.1-flash')
    await expect(page.getByTestId('chat-history')).toContainText('已创建并运行 Notes 小应用')
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.getByRole('button', { name: '查看修改成果', exact: true }).click()
    const orderedChanges = page.getByRole('complementary', { name: '修改成果' })
    await expect(orderedChanges.locator('details > button')).toHaveCount(3)
    expect(await orderedChanges.locator('details > button').allTextContents()).toEqual([
      'src/main.py · 新建 · 已保存到项目',
      'src/main.py · 编辑 · 已保存到项目',
      'app.py · 新建 · 已保存到项目'
    ])
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.getByRole('button', { name: '收起修改成果', exact: true }).click()

    stage = 'narrow-layout'
    const geometry = []
    for (const size of [
      [1080, 700],
      [960, 650]
    ]) {
      await app.evaluate(({ BrowserWindow }, dimensions) => {
        BrowserWindow.getAllWindows()[0].setSize(dimensions[0], dimensions[1])
      }, size)
      await expect(page.getByLabel('输入问题')).toBeInViewport({ ratio: 1 })
      await page.getByRole('button', { name: 'Trace', exact: true }).click()
      await expect(trace).toBeVisible()
      await expect(trace).toBeInViewport({ ratio: 1 })
      geometry.push(
        await page.evaluate(() => {
          const history = document.querySelector('.chat-history')!.getBoundingClientRect()
          const input = document.querySelector('.chat-composer')!.getBoundingClientRect()
          const tracePanel = document.querySelector('.trace-panel')!.getBoundingClientRect()
          return {
            width: innerWidth,
            height: innerHeight,
            documentWidth: document.documentElement.scrollWidth,
            documentHeight: document.documentElement.scrollHeight,
            history: { width: history.width, height: history.height },
            input: { left: input.left, right: input.right, top: input.top, bottom: input.bottom },
            trace: {
              left: tracePanel.left,
              right: tracePanel.right,
              top: tracePanel.top,
              bottom: tracePanel.bottom
            }
          }
        })
      )
      await capture(`09-narrow-trace-${size[0]}`)
      await trace.getByRole('button', { name: '关闭 Trace', exact: true }).click()
    }
    observations.geometry = geometry
    await page.getByRole('button', { name: '停止程序', exact: true }).click()
    await expect(page.locator('.program-quick-controls').last()).toContainText('已停止')
    await expect
      .poll(() =>
        fetch(url)
          .then(() => false)
          .catch(() => true)
      )
      .toBe(true)
    observations.stoppedPreviewButtonCount = await page
      .getByRole('button', { name: '打开预览', exact: true })
      .count()
    expect(observations.stoppedPreviewButtonCount).toBe(0)
    const stoppedSessionId = await page
      .locator('.tree-session.selected')
      .getAttribute('data-session-id')
    if (!stoppedSessionId) throw new Error('Missing stopped session')
    const stoppedOpen = await page.evaluate(async (sessionId) => {
      const session = await window.agent.getSession({ session_id: sessionId, before_seq: null })
      if (!session.ok) throw new Error(session.error.code)
      const programs = await window.agent.listPrograms({
        project_id: session.data.summary.project_id,
        session_id: sessionId,
        cursor: null,
        limit: 20
      })
      if (!programs.ok) throw new Error(programs.error.code)
      const service = programs.data.programs.find((program) => program.kind === 'service')
      if (!service) throw new Error('Missing stopped service')
      return window.agent.openProgram(service.program_id)
    }, stoppedSessionId)
    expect(stoppedOpen.ok).toBe(false)
    if (!stoppedOpen.ok) {
      expect(stoppedOpen.error.code).toBe('PROGRAM_NOT_READY')
      expect(stoppedOpen.error.message).toContain('重新启动服务')
    }
    await capture('10-service-stopped')

    stage = 'restart'
    await app.close()
    app = await launch()
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: '展开项目 coding project', exact: true }).click()
    await page.getByRole('button', { name: '展开任务 日常编码体验', exact: true }).click()
    await page.locator('.tree-session').filter({ hasText: 'read and wait' }).click()
    await expect(page.getByLabel('会话模型', { exact: true })).toHaveValue('deepseek-v4.1-flash')
    await expect(page.locator('.program-quick-controls').last()).toContainText('已停止')
    await page.getByRole('button', { name: 'Trace', exact: true }).click()
    await expect(page.getByRole('complementary', { name: '执行轨迹', exact: true })).toContainText(
      'start_service'
    )
    await capture('11-restarted')
    observations.completed = true
  } finally {
    observations.lastStage = stage
    observations.pageErrors = errors
    await capture('last-state').catch((error: unknown) => {
      observations.captureError = error instanceof Error ? error.message : String(error)
    })
    await writeFile(
      path.join(root, 'observations.json'),
      JSON.stringify(observations, null, 2),
      'utf8'
    )
    console.log(`PERSONA_CODING_ARTIFACTS=${root}`)
    await app
      .evaluate(({ dialog }) => {
        dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
      })
      .catch(() => {})
    await app.close()
  }
})

/** 在已有隔离样本上只读核对窄窗与停止状态，不重复调用模型。
 * Inspect narrow layouts and stopped controls on an existing isolated fixture without model calls.
 */
test('coding persona inspects saved artifacts at narrow width', async () => {
  const supplied = process.env.MY_AGENT_PERSONA_REVIEW_ROOT
  test.skip(!supplied, 'Opt-in review of a previously saved isolated fixture')
  const root = path.resolve(supplied!)
  const relative = path.relative(artifacts, root)
  if (
    relative.startsWith('..') ||
    path.isAbsolute(relative) ||
    !relative.startsWith('persona-coding-')
  )
    throw new Error('Review root must be this persona fixture under the test artifacts')
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = path.join(root, 'coding project')
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
    await page.getByRole('button', { name: '展开项目 coding project', exact: true }).click()
    await page.getByRole('button', { name: '展开任务 日常编码体验', exact: true }).click()
    await page.locator('.tree-session').filter({ hasText: 'read and wait' }).click()
    const service = page.locator('.program-quick-controls').last()
    await expect(service).toContainText('已停止')
    await expect(service.getByRole('button', { name: '打开预览', exact: true })).toHaveCount(0)
    await service.scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(root, '12-stopped-preview-confirmed.png') })
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(960, 650))
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.getByRole('button', { name: '查看修改成果', exact: true }).click()
    const changes = page.getByRole('complementary', { name: '修改成果' })
    await changes
      .getByRole('button', { name: 'src/main.py · 编辑 · 已保存到项目', exact: true })
      .click()
    await expect(page.getByTestId('change-diff')).toContainText('+print(2)')
    await page.screenshot({ path: path.join(root, '13-narrow-changes.png') })
    const layout = await page.evaluate(() => {
      const composer = document.querySelector('.composer-dock')!.getBoundingClientRect()
      const changesPanel = document.querySelector('.changes-panel')!.getBoundingClientRect()
      return {
        width: innerWidth,
        height: innerHeight,
        documentWidth: document.documentElement.scrollWidth,
        documentHeight: document.documentElement.scrollHeight,
        composerBottom: composer.bottom,
        changes: { left: changesPanel.left, right: changesPanel.right, bottom: changesPanel.bottom }
      }
    })
    await writeFile(path.join(root, 'saved-review.json'), JSON.stringify(layout, null, 2), 'utf8')
    expect(layout.documentWidth).toBeLessThanOrEqual(layout.width + 1)
    expect(layout.documentHeight).toBeLessThanOrEqual(layout.height + 1)
    expect(layout.composerBottom).toBeLessThanOrEqual(layout.height + 1)
  } finally {
    await app.close()
  }
})
