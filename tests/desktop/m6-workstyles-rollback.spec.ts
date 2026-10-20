/** M6 组合复用和请求回退的真实桌面入口，模型使用既有替身。 M6 desktop flows with the existing model fixture. */
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'

test('workstyle reuse and code/conversation restore retain the original history', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-m6-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  const env: Record<string, string> = { OPENCODE_API_KEY: sentinel, MY_AGENT_PROJECT_DIR: project }
  for (const [name, value] of Object.entries(process.env)) {
    if (value !== undefined && !(name in env)) env[name] = value
  }
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
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    const environments = page.getByRole('region', { name: '项目执行环境' })
    await environments.getByLabel('执行方式', { exact: true }).selectOption('sandbox')
    await environments.getByLabel('允许沙箱网络', { exact: true }).uncheck()
    await environments.getByLabel('沙箱只读目录', { exact: true }).fill('.')
    await environments.getByRole('button', { name: '保存项目环境', exact: true }).click()
    await expect(
      environments.getByRole('button', { name: '保存项目环境', exact: true })
    ).toBeEnabled()
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await expect(environments.getByLabel('执行方式', { exact: true })).toHaveValue('sandbox')
    await expect(environments.getByLabel('允许沙箱网络', { exact: true })).not.toBeChecked()
    await expect(environments.getByLabel('沙箱只读目录', { exact: true })).toHaveValue('.')
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('M6 sample')
    await page.getByLabel('阶段目标', { exact: true }).fill('Reuse and restore')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'M6 sample', exact: true })).toBeVisible()
    const firstTaskId = (await readdir(path.join(root, 'data/tasks')))[0]
    const styles = page.locator('.workstyles')
    await styles.locator(':scope > summary').click()
    await styles.getByRole('button', { name: '从当前任务保存为工作方式', exact: true }).click()
    await styles.getByLabel('名称', { exact: true }).fill('M6 reusable')
    await styles.getByRole('button', { name: '保存组合工作方式', exact: true }).click()
    await expect(styles.getByRole('status')).toContainText('已保存')
    await styles.getByLabel('项目默认工作方式').selectOption({ label: 'M6 reusable' })
    await expect(styles.getByLabel('项目默认工作方式')).toBeEnabled()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByLabel('输入问题').fill('files: create')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await page.getByLabel('输入问题').fill('files: edit')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toHaveValue('')
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    expect(await readFile(path.join(project, 'src/main.py'), 'utf8')).toBe('print(2)\n')
    await page.getByRole('button', { name: '回退', exact: true }).click()
    const restore = page.getByRole('complementary', { name: '请求回退' })
    await restore.getByRole('button', { name: /files: edit/ }).click()
    await restore.getByRole('button', { name: '恢复并重新提问', exact: true }).click()
    await expect(restore.getByRole('status')).toContainText('重新开始')
    expect(await readFile(path.join(project, 'src/main.py'), 'utf8')).toBe('print(1)\n')
    await expect(page.getByLabel('输入问题')).toHaveValue('files: edit')
    await restore.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(restore).toBeHidden()
    await expect(page.locator('.abandoned-entry').first()).toBeVisible()
    await page.getByRole('button', { name: '＋ 新建任务', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('Second task')
    await page.getByLabel('阶段目标', { exact: true }).fill('Use project default')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Second task', exact: true })).toBeVisible()
    const secondTaskId = (await readdir(path.join(root, 'data/tasks'))).find(
      (id) => id !== firstTaskId
    )
    if (!secondTaskId) throw new Error('Second task must be persisted')
    await page.evaluate(async (taskId) => {
      const task = await window.agent.getTask(taskId)
      const current = await window.agent.getSpace(taskId)
      if (!task.ok || !current.ok) throw new Error('Task/space read failed')
      const memberId = crypto.randomUUID()
      const saved = await window.agent.saveSpace({
        task_id: taskId,
        expected_revision: current.data.space?.revision ?? null,
        config: {
          receiver_member_id: memberId,
          members: [{ member_id: memberId, name: 'M6 member', model_id: 'glm-5.3-flash' }]
        }
      })
      if (!saved.ok) throw new Error(saved.error.message)
      const bound = await window.agent.bindSpaceMember({
        task_id: taskId,
        member_id: memberId,
        session_id: task.data.initial_session_id,
        operation_id: crypto.randomUUID()
      })
      if (!bound.ok) throw new Error(bound.error.message)
    }, secondTaskId)
    // 重新进入任务加载真实配置；Trace 必须只含所选 Run，关闭后保留任务位置。
    // Reload real configuration; trace stays scoped to its run and closes back to the task.
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.locator('.tree-task').filter({ hasText: 'Second task' }).click()
    const group = page.getByRole('region', { name: '合作群聊', exact: true })
    await group.getByLabel('群聊消息或合作目标').fill('m3: trace sample')
    await group.getByRole('button', { name: '发送问题', exact: true }).click()
    await expect(group.locator('.space-output').first()).toContainText('本次运行已结束')
    await group.getByRole('button', { name: '本次运行 / Trace', exact: true }).first().click()
    const trace = page.getByRole('complementary', { name: '执行轨迹', exact: true })
    await expect(trace).toBeVisible()
    await expect(trace.locator('.trace-row')).not.toHaveCount(0)
    await trace.getByRole('button', { name: '关闭 Trace', exact: true }).click()
    await expect(trace).toBeHidden()
    await expect(page.getByRole('heading', { name: 'Second task', exact: true })).toBeVisible()
    // 接纳失败没有 Run；不可把该卡片的 Trace 扩大成整个会话。
    // Failed admission has no Run and must not open unrelated session-wide trace records.
    await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n', 'utf8')
    const busyRunId = await page.evaluate(async (taskId) => {
      const task = await window.agent.getTask(taskId)
      if (!task.ok) throw new Error(task.error.message)
      const result = await window.agent.startRun({
        session_id: task.data.initial_session_id,
        operation_id: crypto.randomUUID(),
        prompt: 'Read main.py and wait',
        limits: null,
        mode: 'plan'
      })
      if (!result.ok) throw new Error(result.error.message)
      if (!result.data.run) throw new Error('Expected admitted run')
      return result.data.run.run_id
    }, secondTaskId)
    try {
      await group.getByLabel('群聊消息或合作目标').fill('Another question while busy')
      await group.getByRole('button', { name: '发送问题', exact: true }).click()
      const rejected = group.locator('.space-output').filter({ hasText: 'RUN_BUSY' })
      await expect(rejected).toContainText('无运行记录')
      await expect(rejected.getByRole('button', { name: '本次运行 / Trace' })).toHaveCount(0)
      await expect(rejected.getByRole('button', { name: '进入会话', exact: true })).toBeVisible()
      await expect(trace).toBeHidden()
    } finally {
      const stopped = await page.evaluate((runId) => window.agent.cancelRun(runId), busyRunId)
      expect(stopped.ok).toBe(true)
    }
    await page.screenshot({ path: path.join(root, 'workstyle-reused.png') })
  } catch (error) {
    await (await app.firstWindow()).screenshot({ path: path.join(root, 'failure.png') })
    throw error
  } finally {
    await app.close()
  }
})
