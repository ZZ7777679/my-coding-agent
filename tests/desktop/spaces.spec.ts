/** M5 手动合作空间的真实桌面验证，不发送模型请求。 Verify manual M5 spaces in real Electron without model requests. */
import { expect, test } from './runtime'
import { artifacts, choose, launch } from './helpers'
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

/** 从手动草稿到成员会话，编辑图并重启恢复。 Edit a manual team and graph, assemble sessions, and restore after restart. */
test('M5 manual space assembles sessions and restores graph configuration and collapse', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-spaces-'))
  const project = path.join(root, 'empty-project')
  const data = path.join(root, 'data')
  await mkdir(project)
  let app = await launch(data, project)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('手动合作空间')
    await page.getByLabel('阶段目标', { exact: true }).fill('制作本地页面并 Review')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await expect(page.getByRole('heading', { name: '手动合作空间', exact: true })).toBeVisible()
    const taskIds = await readdir(path.join(data, 'tasks'))
    expect(taskIds).toHaveLength(1)
    const taskId = taskIds[0]
    const initialSessions = await readdir(path.join(data, 'sessions'))
    expect(initialSessions).toHaveLength(1)
    let panel = page.getByRole('region', { name: '合作空间', exact: true })
    await panel.getByRole('button', { name: '创建合作空间草稿', exact: true }).click()
    await panel.getByRole('button', { name: '添加成员', exact: true }).click()
    await panel.getByLabel('成员名称', { exact: true }).fill('实现成员')
    await panel.getByLabel('成员职责', { exact: true }).fill('实现页面')
    await panel.getByLabel('成员工作范围', { exact: true }).fill('单页 HTML')
    await panel.getByRole('button', { name: '关闭成员编辑', exact: true }).click()
    await panel.getByRole('button', { name: '添加成员', exact: true }).click()
    await panel.getByLabel('成员名称', { exact: true }).fill('审查成员')
    await panel.getByLabel('成员职责', { exact: true }).fill('Review')
    await panel.getByLabel('成员工作范围', { exact: true }).fill('只读检查页面')
    await panel.getByLabel('成员模型', { exact: true }).selectOption('deepseek-v4.1-flash')
    await panel.getByRole('button', { name: '关闭成员编辑', exact: true }).click()
    await panel.getByRole('button', { name: '添加关系', exact: true }).click()
    await panel.getByLabel('关系目标', { exact: true }).selectOption({ label: '审查成员' })
    await panel.getByLabel('关系类型', { exact: true }).selectOption('feedback')
    await panel.getByLabel('关系说明', { exact: true }).fill('带来源返回审查结果')
    const source = await panel.getByLabel('关系来源', { exact: true }).inputValue()
    const target = await panel.getByLabel('关系目标', { exact: true }).inputValue()
    await panel.getByLabel('关系来源', { exact: true }).selectOption(target)
    await panel.getByLabel('关系目标', { exact: true }).selectOption(source)
    await panel.getByRole('button', { name: '创建关系', exact: true }).click()
    await panel.getByRole('button', { name: '关闭关系编辑', exact: true }).click()
    await panel.getByRole('button', { name: '自动排布', exact: true }).click()
    await panel.locator('.react-flow__controls-fitview').click()
    const node = panel.locator(`.react-flow__node[data-id="${source}"]`)
    await node.scrollIntoViewIfNeeded()
    const box = await node.boundingBox()
    if (!box) throw new Error('The actual graph node must be visible for dragging')
    await page.mouse.move(box.x + box.width / 2, box.y + 20)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width / 2 + 70, box.y + 60, { steps: 6 })
    await page.mouse.up()
    await panel.getByRole('button', { name: '保存空间配置', exact: true }).click()
    await expect(panel.getByRole('status')).toContainText('空间配置已保存')
    expect(await readdir(path.join(data, 'sessions'))).toEqual(initialSessions)
    const draft = await page.evaluate(async (id) => {
      const result = await window.agent.getSpace(id)
      if (!result.ok || !result.data.space) throw new Error('The saved space must exist')
      return result.data.space
    }, taskId)
    expect(draft.config.members).toHaveLength(2)
    expect(draft.config.members?.[0].position).not.toEqual({ x: 0, y: 0 })
    expect(draft.config.edges?.[0]).toMatchObject({
      source_member_id: target,
      target_member_id: source,
      kind: 'feedback',
      label: '带来源返回审查结果'
    })
    await panel.getByRole('button', { name: '组建团队会话', exact: true }).click()
    await expect(panel.getByRole('status')).toContainText('团队会话已组建')
    expect(await readdir(path.join(data, 'sessions'))).toHaveLength(3)
    await panel.getByRole('button', { name: '收起关系图', exact: true }).click()
    await expect(panel.locator('.space-graph')).toHaveCount(0)
    await panel
      .locator('.space-member-list')
      .getByRole('button', { name: /审查成员/ })
      .click()
    await panel.getByText('当前会话与历史', { exact: true }).click()
    await panel.getByRole('button', { name: '打开成员会话', exact: true }).click()
    await expect(page.getByLabel('输入问题', { exact: true })).toBeEnabled()
    await expect(page.getByLabel('会话模型', { exact: true })).toHaveValue('deepseek-v4.1-flash')
    await expect(page.locator('.session-membership')).toContainText('Review')
    await page.locator('.tree-task').filter({ hasText: '手动合作空间' }).click()
    panel = page.getByRole('region', { name: '合作空间', exact: true })
    await expect(panel.getByRole('button', { name: '展开关系图', exact: true })).toBeVisible()
    await page.screenshot({ path: path.join(root, 'space-assembled-collapsed.png') })
    const spacePath = path.join(data, 'spaces', `${taskId}.json`)
    await expect
      .poll(async () => {
        const result = await page.evaluate((id) => window.agent.getSpace(id), taskId)
        return result.ok && result.data.space?.layout?.graph_open
      })
      .toBe(false)
    const saved = await readFile(spacePath, 'utf8')
    await app.close()
    app = await launch(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').filter({ hasText: '手动合作空间' }).click()
    panel = page.getByRole('region', { name: '合作空间', exact: true })
    await expect(panel.getByRole('button', { name: '展开关系图', exact: true })).toBeVisible()
    await expect(panel.locator('.space-graph')).toHaveCount(0)
    expect(await readFile(spacePath, 'utf8')).toBe(saved)
    await panel.getByRole('button', { name: '展开关系图', exact: true }).click()
    await expect(panel.locator('.react-flow__node')).toHaveCount(2)
    await expect(panel.locator('.react-flow__edge')).toHaveCount(1)
    const restored = await page.evaluate(async (id) => {
      const result = await window.agent.getSpace(id)
      if (!result.ok || !result.data.space) throw new Error('The restored space must exist')
      return result.data.space
    }, taskId)
    expect(restored.config).toEqual(draft.config)
    expect(
      restored.bindings?.every((item) => item.session_id && item.session_ids?.length === 1)
    ).toBe(true)
    const active = await page.evaluate(() => window.agent.getActiveRuns())
    expect(active.ok && active.data.sessions.length === 0).toBe(true)
    const sessions = await readdir(path.join(data, 'sessions'))
    for (const id of sessions) {
      const log = await readFile(path.join(data, 'sessions', id, 'events.jsonl'), 'utf8')
      expect(log).not.toContain('request.started')
    }
    expect(await readdir(project)).toEqual([])
    // 真实窗口中反复折叠多个区域，关闭后只保留标题，不覆盖相邻区域。
    // Toggle real disclosures at both widths; closed regions retain only their summaries.
    for (const width of [1440, 1000]) {
      await page.setViewportSize({ width, height: 900 })
      for (const selector of [
        '.space-team-tools',
        '.space-chat-disclosure',
        '.space-organisation',
        '.space-relation-list',
        '.task-shared'
      ]) {
        const disclosure = page.locator(selector)
        const summary = disclosure.locator(':scope > summary')
        if (
          await disclosure.evaluate(
            (element) => element instanceof HTMLDetailsElement && element.open
          )
        )
          await summary.click()
        await summary.click()
        await expect(disclosure).toHaveAttribute('open', '')
        await summary.click()
        await expect(disclosure).not.toHaveAttribute('open')
        const outer = await disclosure.boundingBox()
        const heading = await summary.boundingBox()
        if (!outer || !heading) throw new Error('Disclosure geometry must be available')
        expect(outer.height).toBeLessThanOrEqual(heading.height + 4)
      }
      await panel.locator('.space-graph').scrollIntoViewIfNeeded()
      await panel.locator('.react-flow__controls-fitview').click()
      await panel
        .locator('.space-graph')
        .screenshot({ path: path.join(root, `space-graph-${width}.png`) })
      const overflow = await page
        .locator('.task-panel')
        .evaluate((element) => element.scrollWidth > element.clientWidth)
      expect(overflow).toBe(false)
      await page.screenshot({ path: path.join(root, `space-layout-${width}.png`) })
    }
    await page.screenshot({ path: path.join(root, 'space-restored.png') })
    await writeFile(
      path.join(root, 'report.json'),
      JSON.stringify(
        {
          task_id: taskId,
          member_ids: restored.config.members?.map((item) => item.member_id),
          sessions,
          draft_created_sessions: false,
          model_requests: 0,
          network_requests: 0,
          graph_layout_restored: true,
          graph_collapse_restored: true,
          task_disclosures_checked_widths: [1440, 1000]
        },
        null,
        2
      ),
      'utf8'
    )
  } finally {
    await app.close()
  }
})
