/** 显式真实模型桌面体验，空目录单页计数器。 Opt-in real-model desktop workflow for an empty-project counter. */
import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import { randomUUID } from 'node:crypto'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { requireDesktop, root, artifacts } from '../support/runtime.mjs'

assert(process.argv.includes('--enable-real-models'), 'Explicit --enable-real-models is required')
const { _electron: electron, expect } = requireDesktop('@playwright/test')
await mkdir(artifacts, { recursive: true })
const resumeIndex = process.argv.indexOf('--resume-report')
const resumePath = resumeIndex < 0 ? null : path.resolve(process.argv[resumeIndex + 1])
if (resumePath) {
  const relative = path.relative(artifacts, resumePath)
  assert(!relative.startsWith('..') && !path.isAbsolute(relative), 'Resume only test artifacts')
}
const previous = resumePath ? JSON.parse(await readFile(resumePath, 'utf8')) : null
const directory = resumePath
  ? path.dirname(resumePath)
  : await mkdtemp(path.join(artifacts, 'desktop-counter-live-'))
const project = path.join(directory, 'project')
const data = path.join(directory, 'data')
await mkdir(project, { recursive: true })
const report = previous
  ? { ...previous, result: 'running', resumed_from: resumePath }
  : { directory, project, result: 'running', stages: [], sessions: {} }
const reportPath = path.join(
  directory,
  resumePath ? `report-resume-${randomUUID()}.json` : 'report.json'
)
const env = { ...process.env, MY_AGENT_PROJECT_DIR: project }
delete env.ELECTRON_RUN_AS_NODE
delete env.ELECTRON_RENDERER_URL
let app
let page
let projectId = previous?.project_id
let source = previous?.source_session
let target = previous?.handoff_session
let preview

/** 用系统分配的端口，不修改产品默认。 Ask the OS for a port without changing product defaults. */
async function availablePort() {
  const server = createServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const port = server.address().port
  await new Promise((resolve) => server.close(resolve))
  return port
}
const port = previous ? Number(new URL(previous.url).port) : await availablePort()
const url = `http://127.0.0.1:${port}/`
report.url = url

/** 每步立即保留结果，异常不重试真实调用。 Persist each step immediately and never retry live faults. */
async function stage(name, action) {
  if (previous?.stages.some((item) => item.name === name && item.result === 'passed')) {
    console.log(JSON.stringify({ stage: name, reused_from: resumePath }))
    return
  }
  const value = { name, started_at: new Date().toISOString(), result: 'running' }
  report.stages.push(value)
  await save()
  console.log(JSON.stringify({ stage: name, directory }))
  try {
    value.evidence = await action()
    value.result = 'passed'
  } catch (error) {
    value.result = 'failed'
    value.error = error instanceof Error ? error.message : 'Unknown runner failure'
    throw error
  } finally {
    value.ended_at = new Date().toISOString()
    await save()
  }
}

/** 报告不包含环境、凭据或 provider 原始状态。 Exclude environment, credentials and native provider state. */
async function save() {
  await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n')
}

/** 只调用已有有限 preload，读取公开事实。 Use the existing finite preload and public facts. */
async function api(name, params) {
  const result = await page.evaluate(([method, args]) => window.agent[method](args), [name, params])
  assert(result.ok, `${name}: ${result.error?.code} ${result.error?.message}`)
  return result.data
}

/** 启动真实产品入口和隔离数据根。 Launch the production entry with an isolated data root. */
async function launch() {
  app = await electron.launch({ args: [path.join(root, 'apps/desktop'), '--data-dir', data], env })
  page = await app.firstWindow()
  page.setDefaultTimeout(15000)
  await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接', {
    timeout: 20000
  })
}

/** 等待持久终态，故障立即报告而不重发。 Await durable termination; report faults without resending. */
async function waitRun(id, previousId) {
  const deadline = Date.now() + 620000
  while (Date.now() < deadline) {
    const view = await api('getSession', { session_id: id, before_seq: null })
    const run = view.summary.run
    if (run && run.run_id !== previousId && !['running', 'stopping'].includes(run.status)) {
      report.sessions[id] = view.summary
      await save()
      assert.equal(run.status, 'completed', JSON.stringify(run))
      return run
    }
    await delay(700)
  }
  throw new Error('The bounded run did not terminate within the observation window')
}

/** 从真实输入框发送一次，不用测试模型。 Send once from the actual composer with no model substitute. */
async function chat(id, mode, prompt) {
  const old = await api('getSession', { session_id: id, before_seq: null })
  await page.getByLabel('本次模式').selectOption(mode)
  await page.getByLabel('输入问题').fill(prompt)
  await page.getByRole('button', { name: '发送', exact: true }).click()
  return waitRun(id, old.summary.run?.run_id)
}

/** 使用左侧真实会话按钮，保留选择和订阅链路。 Select the real tree button and retain subscription behavior. */
async function selectSession(id) {
  const view = await api('getSession', { session_id: id, before_seq: null })
  await page.locator('.tree-session').getByText(view.summary.title, { exact: true }).click()
  await expect(page.getByLabel('输入问题')).toBeVisible()
}

/** 用户从任务面板明确创建协作会话。 Explicitly create a peer through the task panel as the user. */
async function createPeer(role, scope, model) {
  await page.locator('.tree-task').first().click()
  await page.getByText('创建新的工作会话', { exact: true }).click()
  await page.getByLabel('新会话模型', { exact: true }).selectOption(model)
  await page.getByLabel('会话角色', { exact: true }).fill(role)
  await page.getByLabel('工作范围', { exact: true }).fill(scope)
  await page.getByRole('button', { name: '新建会话', exact: true }).click()
  await expect(page.getByLabel('输入问题')).toBeVisible()
  const sessions = await api('listSessions', { project_id: projectId, cursor: null, limit: 20 })
  const peer = sessions.sessions.find((item) => item.role === role)
  assert(peer, 'Created peer must have its chosen role')
  return peer.session_id
}

/** 用户通过新入口发起交接或审查并查看来源简报。 Arrange handoff/review through the UI and inspect its brief. */
async function arrange(from, to, kind, objective) {
  await selectSession(from)
  await page.getByLabel('会话选项', { exact: true }).click()
  await page.locator('.collaboration-panel > summary').click()
  await page.getByLabel('协作会话', { exact: true }).selectOption(to)
  await page.getByLabel('工作安排', { exact: true }).selectOption(kind)
  await page
    .getByLabel(kind === 'handoff' ? '接手目标' : '审查范围', { exact: true })
    .fill(objective)
  await page
    .getByRole('button', { name: kind === 'handoff' ? '开始交接' : '发起独立 Review', exact: true })
    .click()
  let request
  const deadline = Date.now() + 620000
  while (Date.now() < deadline) {
    const result = await api('listCollaboration', { session_id: from })
    request = result.requests.find(
      (item) => item.params.target_session_id === to && item.arrangement?.kind === kind
    )
    if (request && !['preparing', 'queued', 'running'].includes(request.status)) break
    await delay(800)
  }
  assert.equal(
    request?.status,
    'completed',
    JSON.stringify({ status: request?.status, reason: request?.reason })
  )
  const card = page.locator(`[data-request-id="${request.request_id}"]`)
  await expect(card).toContainText('已返回结果')
  await card.getByText(/查看来源简报/).click()
  await expect(card).toContainText('index.html')
  await page.screenshot({ path: path.join(directory, `${kind}.png`) })
  return request
}

/** 测试浏览器只操作生成页面，不是新增产品浏览器工具。 Exercise the generated page, not a new product browser tool. */
async function openPreview() {
  const opened = app.waitForEvent('window')
  await app.evaluate(async ({ BrowserWindow }, address) => {
    const window = new BrowserWindow({
      width: 900,
      height: 650,
      webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true }
    })
    await window.loadURL(address)
  }, url)
  preview = await opened
  await preview.waitForLoadState()
}

/** 使用产品退出清理，确认当前测试程序可以停止。 Quit through product cleanup with explicit test confirmation. */
async function closeApp() {
  if (!app) return
  await app
    .evaluate(({ dialog }) => {
      dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
    })
    .catch(() => {})
  await app.close()
  app = null
}

try {
  await launch()
  if (previous) {
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').click()
    await selectSession(source)
  }
  await stage('empty-project-and-environment', async () => {
    assert.deepEqual(await readdir(project), [])
    await app.evaluate(({ dialog }, folder) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [folder] })
    }, project)
    await page.getByRole('button', { name: '选择项目文件夹', exact: false }).click()
    const projects = await api('listProjects')
    projectId = projects.active_project.project_id
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    const settings = page.getByRole('region', { name: '项目执行环境' })
    await settings.getByLabel('环境名称', { exact: true }).fill('Counter Python')
    await settings
      .getByLabel('Python 解释器', { exact: true })
      .fill(path.join(root, '.venv/Scripts/python.exe'))
    await settings.getByRole('button', { name: '导入环境', exact: true }).click()
    await settings.getByLabel('项目默认环境').selectOption({ label: 'Counter Python' })
    await settings.getByRole('button', { name: '保存项目环境', exact: true }).click()
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page
      .getByLabel('阶段目标', { exact: true })
      .fill('单页计数器：点击加一，刷新保留数字；使用已有 Python 预览。')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    const sessions = await api('listSessions', { project_id: projectId, cursor: null, limit: 20 })
    source = sessions.sessions[0].session_id
    report.source_session = source
    report.project_id = projectId
    assert.deepEqual(await readdir(project), [])
    return { projectId, source, initially_empty: true }
  })
  await stage('plan', async () => {
    const run = await chat(
      source,
      'plan',
      '查看空项目，简短规划单页计数器（点击加一、localStorage 保存），只需 index.html 和 README.md。使用已选 Python 的 http.server，不安装依赖，不创建文件，不联网；资料检索已单独验证。保存简短规划结果即可。'
    )
    assert.deepEqual(await readdir(project), [])
    return run
  })
  await stage('goal-build-and-serve', async () => {
    if (previous) {
      await expect(page.getByTestId('goal-state')).toBeVisible()
      const status = await page.getByTestId('goal-state').innerText()
      if (status !== 'completed') {
        await page.locator('.goal-panel > summary').click()
        await page.getByRole('button', { name: '接续 Goal', exact: true }).click()
        await expect(page.getByTestId('goal-state')).toHaveText(/^(active|completed)$/)
      }
    } else {
      await page.getByLabel('本次模式').selectOption('goal')
      await page
        .getByLabel('输入问题')
        .fill(
          `从空目录实现上述单页计数器。只创建 index.html 与简短 README.md。页面标题和 h1 是“计数器”，计数 output 的 id=count，加一按钮 id=increment；数字用 localStorage 保存。使用已选环境，短命令检查文件后启动 python -m http.server ${port} --bind 127.0.0.1，ready_url=${url}，用 read_program 查看实际运行。不要安装依赖、初始化 Git、联网或添加测试框架。本目标包含修复本次实现的问题；实际工具故障则停止。报告成果和真实服务地址；按钮交互由用户随后检查，不声称已经点过。`
        )
      await page.getByText('Goal 完成条件与预算（可选）', { exact: true }).click()
      await page
        .getByLabel('Goal 完成条件')
        .fill('创建计数器页面和运行说明\n使用已选 Python 成功启动静态预览并读取状态')
      await page.getByLabel('Goal 累计请求').fill('20')
      await page.getByLabel('Goal 累计工具').fill('40')
      await page.getByLabel('Goal 活跃秒数').fill('540')
      await page.getByRole('button', { name: '启动 Goal', exact: true }).click()
    }
    await expect(page.getByTestId('goal-state')).toBeVisible()
    await expect
      .poll(() => page.getByTestId('goal-state').innerText(), { timeout: 560000, intervals: [800] })
      .not.toBe('active')
    assert.equal(
      await page.getByTestId('goal-state').innerText(),
      'completed',
      await page.getByTestId('goal-panel').innerText()
    )
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    assert.deepEqual((await readdir(project)).sort(), ['README.md', 'index.html'])
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.getByRole('button', { name: '查看修改成果', exact: true }).click()
    await page
      .getByRole('complementary', { name: '修改成果' })
      .getByRole('button', { name: /index.html/ })
      .click()
    await expect(page.getByTestId('change-diff')).toContainText('localStorage')
    await page.screenshot({ path: path.join(directory, 'goal-and-diff.png') })
    return {
      goals: await api('listGoals', { session_id: source, limit: 1, before_seq: null }),
      files: await readdir(project)
    }
  })
  await stage('browser-click-refresh-and-service-restart', async () => {
    if (previous) {
      // 上次检查退出后，服务按产品规则停止；明确新请求后再验证预览。
      // Product shutdown stopped the service; make an explicit new request before previewing.
      await chat(
        source,
        'normal',
        `上次应用已退出，预览服务已停止。请用 read_program 核对上次服务，并使用原环境与命令在 ${url} 重新启动；再读取状态。不要重写文件、修改 Goal 或联网。`
      )
    }
    await openPreview()
    await expect(preview.locator('#count')).toHaveText('0')
    await preview.locator('#increment').click()
    await preview.locator('#increment').click()
    await expect(preview.locator('#count')).toHaveText('2')
    await preview.reload()
    await expect(preview.locator('#count')).toHaveText('2')
    await preview.screenshot({ path: path.join(directory, 'counter.png') })
    const run = await chat(
      source,
      'normal',
      `用户已实际点击两次并刷新，数字仍为 2。请读取页面，用 search 定位 localStorage，再用 stop_program 停止本会话当前服务，确认停止；随后 start_service 使用相同 ${url} 及原 Python 命令重新启动，用 read_program 查看状态。只执行这次短检查，不改文件、不联网。`
    )
    await preview.reload()
    await expect(preview.locator('#count')).toHaveText('2')
    return { count_after_reload_and_service_restart: 2, run }
  })
  await stage('deepseek-handoff-title', async () => {
    target = await createPeer(
      '接手改标题',
      '只将 index.html 的标题和 h1 改为“我的计数器”，保留计数行为。',
      'deepseek-v4.1-flash'
    )
    report.handoff_session = target
    const request = await arrange(
      source,
      target,
      'handoff',
      '接手 index.html：按需读来源会话与历史差异，读取当前文件基线，仅将页面 title 和 h1 从“计数器”改为“我的计数器”。不要改变其他代码、不重启服务、不联网、不添加测试。简短报告实际修改。'
    )
    await preview.reload()
    await expect(preview.locator('h1')).toHaveText('我的计数器')
    await expect(preview).toHaveTitle('我的计数器')
    await expect(preview.locator('#count')).toHaveText('2')
    await preview.locator('#increment').click()
    await expect(preview.locator('#count')).toHaveText('3')
    await preview.reload()
    await expect(preview.locator('#count')).toHaveText('3')
    return request
  })
  await stage('glm-independent-review', async () => {
    await selectSession(target)
    const reviewer =
      previous?.review_session ??
      (await createPeer(
        '独立 Review',
        '只读审查标题改动和计数逻辑，不执行或修改文件。',
        'glm-5.3-flash'
      ))
    report.review_session = reviewer
    const before = await readFile(path.join(project, 'index.html'), 'utf8')
    const request = await arrange(
      target,
      reviewer,
      'review',
      '独立检查刚才的标题改动。读取来源历史差异与当前 index.html，检查是否误改计数和 localStorage。用户已实际确认改标题后加一和刷新保存仍正常。只报告可定位问题与未检查范围；没有发现就明确写无发现，不改文件、不运行命令、不联网。'
    )
    assert.equal(await readFile(path.join(project, 'index.html'), 'utf8'), before)
    return request
  })
  await stage('exit-and-restart-persistence', async () => {
    const serviceWasRunning = await fetch(url)
      .then(() => true)
      .catch(() => false)
    const before = await api('getSession', { session_id: source, before_seq: null })
    await closeApp()
    await expect
      .poll(
        () =>
          fetch(url)
            .then(() => false)
            .catch(() => true),
        { timeout: 15000 }
      )
      .toBe(true)
    await launch()
    const after = await api('getSession', { session_id: source, before_seq: null })
    assert.equal(after.summary.run.run_id, before.summary.run.run_id)
    assert.equal(after.watermark, before.watermark)
    assert.deepEqual((await api('getActiveRuns')).sessions, [])
    assert.equal(
      await fetch(url)
        .then(() => true)
        .catch(() => false),
      false
    )
    const goals = await api('listGoals', { session_id: source, limit: 1, before_seq: null })
    assert.equal(goals.goals[0].status, 'completed')
    await page.screenshot({ path: path.join(directory, 'restarted.png') })
    return {
      same_run: true,
      same_watermark: true,
      service_running_before_exit: serviceWasRunning,
      service_stopped: true,
      no_automatic_runs: true
    }
  })
  report.result = 'passed'
} catch (error) {
  report.result = 'failed'
  if (page && !page.isClosed())
    await page.screenshot({ path: path.join(directory, 'failure.png') }).catch(() => {})
  console.error(error instanceof Error ? error.message : 'Workflow failed')
  process.exitCode = 1
} finally {
  await closeApp()
  await save()
  console.log(JSON.stringify({ result: report.result, report: reportPath }))
}
