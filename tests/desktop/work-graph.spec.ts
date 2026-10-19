/** 工作流到任务图的真实桌面编辑与恢复。 Exercise task graphs in real Electron. */
import { mkdir, mkdtemp, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './runtime'
import { artifacts, choose, launch } from './helpers'

/** 首会话接入不新增会话，骨架编辑不改变模板。 Reuse the first session and preserve templates. */
test('task work graph edits, binds and restores without model calls', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-work-graph-'))
  const data = path.join(root, 'data')
  const project = path.join(root, 'counter')
  await mkdir(project)
  let app = await launch(data, project)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('计数器工作图')
    await page.getByLabel('阶段目标', { exact: true }).fill('实现计数器，检查后按反馈修改')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await expect(page.getByRole('heading', { name: '计数器工作图', exact: true })).toBeVisible()
    const panel = page.getByRole('region', { name: '合作空间', exact: true })
    await panel.getByRole('button', { name: '用首会话建立工作空间', exact: true }).click()
    const graph = page.getByRole('region', { name: '任务工作图', exact: true })
    await expect(graph).toBeVisible()
    await graph.getByRole('button', { name: '从流程补充骨架', exact: true }).click()
    await expect(graph.locator('.react-flow__node')).toHaveCount(7)
    const start = graph.locator('.react-flow__node').filter({ hasText: /^讨论/ })
    const end = graph.locator('.react-flow__node').filter({ hasText: /^审查/ })
    const edgeId = `dependency:${await start.getAttribute('data-id')}:${await end.getAttribute('data-id')}`
    await graph.getByLabel('拖动连线类型').selectOption('depends_on')
    await start.locator('[data-handleid="source-right"]').click()
    await end.locator('[data-handleid="target-left"]').click()
    const directEdge = graph.locator(`.react-flow__edge[data-id="${edgeId}"]`)
    await expect(directEdge).toHaveCount(1)
    await directEdge.focus()
    await page.keyboard.press('Enter')
    await expect(directEdge).toHaveClass(/selected/)
    await page.keyboard.press('Delete')
    await expect(directEdge).toHaveCount(0)
    await graph.getByRole('button', { name: '保存工作图', exact: true }).click()
    await graph.locator('.react-flow__node').filter({ hasText: /^实现/ }).click()
    await graph.getByLabel('标题', { exact: true }).fill('实现计数器页面')
    await graph.getByLabel('工作范围', { exact: true }).fill('只编辑 index.html，保留已有内容')
    await graph.getByRole('button', { name: '保存工作图', exact: true }).click()
    await expect(graph.getByRole('status')).toHaveText('工作图已保存到当前任务。')
    await graph.getByLabel('负责人', { exact: true }).selectOption({ label: '任务执行者' })
    await graph.getByRole('button', { name: '保存工作图', exact: true }).click()
    await expect(graph.getByRole('status')).toHaveText('工作图已保存到当前任务。')
    await expect(
      graph.locator('.react-flow__node').filter({ hasText: '实现计数器页面' })
    ).toContainText('任务执行者')
    await graph
      .locator('.work-graph-selection')
      .getByLabel('实现计数器页面', { exact: true })
      .check()
    await expect(graph.getByRole('button', { name: '执行一次', exact: true })).toBeEnabled()
    await graph.getByText('结果与反馈', { exact: true }).click()
    await graph.getByLabel('工作结果与反馈', { exact: true }).fill('等待后续页面实现')
    await graph.getByLabel('工作状态', { exact: true }).selectOption('waiting')
    await graph.getByRole('button', { name: '保存结果与状态', exact: true }).click()
    await expect(
      graph.locator('.react-flow__node').filter({ hasText: '实现计数器页面' })
    ).toContainText('等待')
    await graph.getByText('结果与反馈', { exact: true }).click()
    await expect(graph.getByLabel('工作结果与反馈', { exact: true })).toBeHidden()
    // 实际拖动并保存位置；新增节点可删除，其他节点与已有结果保留。
    // Persist an actual drag, then remove a new node without losing existing results.
    const node = graph.locator('.react-flow__node').filter({ hasText: '实现计数器页面' })
    await node.scrollIntoViewIfNeeded()
    const bounds = await node.boundingBox()
    if (!bounds) throw new Error('Node bounds must be available')
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + 20)
    await page.mouse.down()
    await page.mouse.move(bounds.x + bounds.width / 2 + 45, bounds.y + 48, { steps: 8 })
    await page.mouse.up()
    await graph.getByRole('button', { name: '保存工作图', exact: true }).click()
    await expect(graph.getByRole('status')).toHaveText('工作图已保存到当前任务。')
    await graph.getByRole('button', { name: '添加工作', exact: true }).click()
    await expect(graph.locator('.react-flow__node')).toHaveCount(8)
    await graph.getByRole('button', { name: '删除节点', exact: true }).click()
    await graph.getByRole('button', { name: '保存工作图', exact: true }).click()
    await expect(graph.locator('.react-flow__node')).toHaveCount(7)
    await graph.locator('.react-flow__node').filter({ hasText: '实现计数器页面' }).click()
    await graph.locator('.work-graph-canvas').scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(root, 'work-graph-wide.png') })
    await page.setViewportSize({ width: 1000, height: 850 })
    await page.screenshot({ path: path.join(root, 'work-graph-narrow.png') })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    ).toBe(true)
    await panel.getByRole('button', { name: '团队视角', exact: true }).click()
    await expect(graph).toBeHidden()
    await panel.getByRole('button', { name: '工作视角', exact: true }).click()
    await expect(graph.locator('.react-flow__node')).toHaveCount(7)
    expect(await readdir(path.join(data, 'sessions'))).toHaveLength(1)
    expect(await readdir(project)).toEqual([])
    const taskId = (await readdir(path.join(data, 'tasks')))[0]
    await app.close()
    app = await launch(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    const restored = await page.evaluate(async (id) => {
      const graph = await window.agent.getWorkGraph({ task_id: id })
      if (!graph.ok) throw new Error(graph.error.message)
      return graph.data
    }, taskId)
    expect(restored.items).toHaveLength(7)
    const item = restored.items.find((work) => work.title === '实现计数器页面')
    expect(item?.status).toBe('waiting')
    expect(item?.position).toEqual({ x: expect.any(Number), y: expect.any(Number) })
    expect(restored.items.every((work) => work.position)).toBe(true)
    expect(item?.owner_member_id).toBeTruthy()
    expect(item?.result).toBe('等待后续页面实现')
    expect(
      restored.task.workflow?.template.stages?.find((stage) => stage.stage_id === 'implement')?.name
    ).toBe('实现')
    await writeFile(
      path.join(root, 'report.json'),
      JSON.stringify(
        { task_id: taskId, restored_items: restored.items.length, sessions: 1, model_requests: 0 },
        null,
        2
      )
    )
  } catch (error) {
    const failedPage = await app.firstWindow()
    await failedPage.screenshot({ path: path.join(root, 'failure.png') })
    await writeFile(path.join(root, 'failure.html'), await failedPage.content())
    throw error
  } finally {
    await app.close()
  }
})
