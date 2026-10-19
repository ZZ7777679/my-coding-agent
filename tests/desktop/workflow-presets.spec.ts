/** 三个适配工作流的实际桌面入口与快照。 Exercise adapted workflows and snapshots in real Electron. */
import { mkdir, mkdtemp, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './runtime'
import { artifacts, choose, launch } from './helpers'

/** 从资源库查看、复制，逐个创建任务并重启恢复；零模型请求。 Browse, copy, create and restore without model calls. */
test('adapted workflow presets can be selected, copied and restored', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-workflows-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  let app = await launch(data, project)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '工作流管理', exact: true }).click()
    const library = page.getByRole('region', { name: '工作流管理', exact: true })
    const option = library.locator('.workflow-option').filter({ hasText: 'OpenSpec' })
    await option.locator('summary').click()
    await expect(option).toContainText('c794978')
    await option.getByRole('button', { name: '查看阶段', exact: true }).click()
    await expect(library.getByRole('button', { name: '保存模板', exact: true })).toBeDisabled()
    await library.getByRole('button', { name: '复制后编辑', exact: true }).click()
    await library.getByLabel('流程名称', { exact: true }).fill('我的变更流程')
    await library.getByRole('button', { name: '保存模板', exact: true }).click()
    await expect(
      library.locator('.workflow-option').filter({ hasText: '我的变更流程' })
    ).toBeVisible()

    for (const method of ['openspec', 'superpowers', 'spec-kit']) {
      await page.getByRole('button', { name: '项目工作台', exact: true }).click()
      await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
      await page.getByLabel('任务名称', { exact: true }).fill(`流程体验 ${method}`)
      await page.getByLabel('阶段目标', { exact: true }).fill('实现一个计数器')
      await page.locator('.task-panel .workflow-catalog > summary').click()
      await page.getByLabel('选择流程', { exact: true }).selectOption(`builtin:${method}`)
      await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
      await expect(
        page.getByRole('heading', { name: `流程体验 ${method}`, exact: true })
      ).toBeVisible()
      const editor = page
        .locator('section')
        .filter({ has: page.getByRole('heading', { name: '任务流程', exact: true }) })
        .last()
      await page.getByLabel('当前阶段', { exact: true }).selectOption('implement')
      await editor.getByRole('button', { name: '保存任务流程', exact: true }).click()
      await expect(page.getByLabel('当前阶段', { exact: true })).toHaveValue('implement')
      await page.screenshot({ path: path.join(root, `${method}.png`) })
    }
    expect(await readdir(project)).toEqual([])
    await app.close()
    app = await launch(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: '工作流管理', exact: true }).click()
    await expect(
      page
        .getByRole('region', { name: '工作流管理', exact: true })
        .locator('.workflow-option')
        .filter({ hasText: '我的变更流程' })
    ).toBeVisible()
    const tasks = await page.evaluate(async () => {
      const projects = await window.agent.listProjects()
      if (!projects.ok || !projects.data.active_project) throw new Error('No active project')
      const result = await window.agent.listTasks({
        project_id: projects.data.active_project.project_id,
        cursor: null,
        limit: 100
      })
      if (!result.ok) throw new Error(result.error.message)
      return Promise.all(
        (result.data.tasks ?? []).map(async (task) => {
          const view = await window.agent.getTask(task.task_id)
          if (!view.ok) throw new Error(view.error.message)
          return {
            template: view.data.workflow?.template.template_id,
            stage: view.data.workflow?.current_stage_id
          }
        })
      )
    })
    expect(tasks.map((task) => task.template).sort()).toEqual([
      'builtin:openspec',
      'builtin:spec-kit',
      'builtin:superpowers'
    ])
    expect(tasks.every((task) => task.stage === 'implement')).toBe(true)
    await writeFile(
      path.join(root, 'report.json'),
      JSON.stringify({ tasks, model_requests: 0 }, null, 2)
    )
  } finally {
    await app.close()
  }
})
