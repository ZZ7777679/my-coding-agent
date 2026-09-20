/** M2 真实桌面任务与旧会话接续，不调用模型。 Real desktop task and legacy-session flow without model calls. */
import { expect, test } from './runtime'
import { artifacts, choose, launch } from './helpers'
import { mkdir, mkdtemp, readFile, readdir } from 'node:fs/promises'
import path from 'node:path'

/** 从空目录创建任务、编辑共同信息、归入旧会话并重启。 Create, update, assign legacy sessions and restart from an empty project. */
test('M2 tasks persist shared facts and organize legacy sessions in the left tree', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-tasks-'))
  const project = path.join(root, 'empty-project')
  const data = path.join(root, 'data')
  await mkdir(project)
  let app = await launch(data, project)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    const legacy = await page.evaluate(async () => {
      const info = await window.agent.getAppInfo()
      if (!info.ok || !info.data.projects.active_project) throw new Error('No project')
      const result = await window.agent.createSession({
        project_id: info.data.projects.active_project.project_id,
        model_id: 'deepseek-v4.1-flash'
      })
      if (!result.ok) throw new Error(result.error.code)
      return result.data
    })
    const legacyPath = path.join(data, 'sessions', legacy.session_id, 'events.jsonl')
    const before = await readFile(legacyPath, 'utf8')
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('空目录任务')
    await page.getByLabel('阶段目标', { exact: true }).fill('制作一个本地待办清单')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await expect(page.getByRole('heading', { name: '空目录任务', exact: true })).toBeVisible()
    await page.getByLabel('已确认结论', { exact: true }).fill('使用 SQLite 保存数据')
    await page.getByLabel('当前进度', { exact: true }).fill('先讨论需求，尚未编写代码')
    await page.getByRole('button', { name: '保存共享信息', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('共享信息已保存')
    await expect(page.getByRole('navigation', { name: '项目任务会话' })).toContainText('空目录任务')
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await expect(page.getByLabel('输入问题', { exact: true })).toBeEnabled()
    await expect(page.locator('.session-sidebar')).toHaveCount(0)
    await page.locator('.tree-task').first().click()
    await expect(page.getByLabel('已确认结论', { exact: true })).toHaveValue('使用 SQLite 保存数据')
    await page.getByText('创建新的工作会话', { exact: true }).click()
    await page.getByLabel('新会话模型', { exact: true }).selectOption('deepseek-v4.1-flash')
    await page.getByLabel('会话角色', { exact: true }).fill('实现界面')
    await page.getByLabel('工作范围', { exact: true }).fill('前端页面')
    await page.getByRole('button', { name: '新建会话', exact: true }).click()
    await expect(page.getByLabel('会话模型', { exact: true })).toHaveValue('deepseek-v4.1-flash')
    await expect(page.locator('.session-membership')).toContainText('实现界面')
    const tree = page.getByRole('navigation', { name: '项目任务会话' })
    await tree.locator('details').filter({ hasText: '未归属会话' }).getByRole('button').click()
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.getByText('归属与分工', { exact: true }).click()
    await page.getByLabel('所属任务', { exact: true }).selectOption({ label: '空目录任务' })
    await page.getByLabel('会话角色', { exact: true }).fill('历史参考')
    await page.getByRole('button', { name: '保存归属与分工', exact: true }).click()
    await expect(page.locator('.session-membership')).toContainText('历史参考')
    expect((await readFile(legacyPath, 'utf8')).startsWith(before)).toBe(true)
    expect(await readdir(project)).toEqual([])
    const taskFiles = await readdir(path.join(data, 'tasks'))
    expect(taskFiles).toHaveLength(1)
    const saved = await readFile(path.join(data, 'tasks', taskFiles[0], 'events.jsonl'), 'utf8')
    await page.screenshot({ path: path.join(root, 'tasks.png') })
    await app.close()
    app = await launch(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').filter({ hasText: '空目录任务' }).click()
    await expect(page.getByLabel('已确认结论', { exact: true })).toHaveValue('使用 SQLite 保存数据')
    await expect(page.getByLabel('当前进度', { exact: true })).toHaveValue(
      '先讨论需求，尚未编写代码'
    )
    expect(await readFile(path.join(data, 'tasks', taskFiles[0], 'events.jsonl'), 'utf8')).toBe(
      saved
    )
    const active = await page.evaluate(() => window.agent.getActiveRuns())
    expect(active.ok && active.data.sessions.length === 0).toBe(true)
    await page.screenshot({ path: path.join(root, 'tasks-restarted.png') })
  } finally {
    await app.close()
  }
})
