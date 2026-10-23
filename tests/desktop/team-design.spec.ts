/** 专用团队设计切走／重启可回，一键启动真实成员会话。 Dedicated design survives navigation/restart and launches real member sessions. */
import { electron, expect, test, type ElectronApplication } from './runtime'
import { artifacts, choose, launch, sentinel } from './helpers'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import path from 'node:path'

test('team design is resumable and confirms the editable graph in one action', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'team-design-desktop-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  const env: Record<string, string> = { OPENCODE_API_KEY: sentinel, MY_AGENT_PROJECT_DIR: project }
  for (const [key, value] of Object.entries(process.env))
    if (value !== undefined && !(key in env)) env[key] = value
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const options = {
    args: [
      path.resolve(__dirname, '../support/desktop_peer.cjs'),
      '--data-dir',
      path.join(root, 'data')
    ],
    env
  }
  let app: ElectronApplication | null = await electron.launch(options)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('创建一个简单计数器页面')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开团队设计', exact: true }).click()
    let discussion = page.getByRole('region', { name: '团队设计讨论', exact: true })
    await expect(discussion.getByLabel('团队设计输入')).toBeEnabled()
    await discussion.getByLabel('团队设计输入').fill('创建实现和审查成员，画出协作图')
    await discussion.getByRole('button', { name: '发送设计要求', exact: true }).click()
    await expect(discussion).toContainText('正在设计团队')
    // 生成期间离开，运行继续，固定入口恢复同一讨论与图。
    // Leave during generation; the fixed entry resumes the same conversation and graph.
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await page.locator('.tree-team-design').click()
    discussion = page.getByRole('region', { name: '团队设计讨论', exact: true })
    await expect(discussion).toContainText('创建实现和审查成员')
    await expect(page.locator('.space-graph .react-flow__node')).toHaveCount(2)
    await expect(
      discussion.getByRole('button', { name: '确认并开始工作', exact: true })
    ).toBeEnabled()
    await discussion.getByLabel('团队设计输入').fill('把实现协调者改名为页面实现负责人')
    await discussion.getByRole('button', { name: '发送设计要求', exact: true }).click()
    await expect(page.locator('.space-graph')).toContainText('页面实现负责人')
    await expect(
      discussion.getByRole('button', { name: '确认并开始工作', exact: true })
    ).toBeEnabled()
    await discussion.getByLabel('团队设计输入').fill('下一次想调整审查职责')
    await page.getByRole('button', { name: '返回任务（保留讨论）', exact: true }).click()
    await page.locator('.tree-team-design').click()
    await expect(page.getByLabel('团队设计输入')).toHaveValue('下一次想调整审查职责')
    await expect(page.getByLabel('团队设计模型')).toHaveValue('glm-5.3-flash')
    await expect(page.getByLabel('团队设计模型')).toBeEnabled()
    await expect(
      discussion.getByRole('button', { name: '发送设计要求', exact: true })
    ).toBeEnabled()
    await page.screenshot({ path: path.join(root, 'design-and-graph.png') })
    await app.close()
    app = await electron.launch(options)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    // 展开任务树，固定入口不依赖上一次页面仍挂载。
    // The fixed task entry does not depend on the previous page remaining mounted.
    await choose(app, project)
    await page
      .getByRole('button', { name: /^展开项目 / })
      .first()
      .click()
    await expect(page.locator('.tree-task')).toHaveCount(1)
    if (!(await page.locator('.tree-team-design').isVisible()))
      await page
        .getByRole('button', { name: /^展开任务 / })
        .first()
        .click()
    await page.locator('.tree-team-design').click()
    discussion = page.getByRole('region', { name: '团队设计讨论', exact: true })
    await expect(discussion.getByLabel('团队设计输入')).toHaveValue('下一次想调整审查职责')
    await expect(page.locator('.space-graph')).toContainText('页面实现负责人')
    await discussion.getByRole('button', { name: '确认并开始工作', exact: true }).click()
    await expect(discussion).toContainText('团队已开始工作')
    await page.screenshot({ path: path.join(root, 'team-started.png') })
    const first = await page.evaluate(async () => {
      const projects = await window.agent.listProjects()
      if (!projects.ok || !projects.data.active_project) throw new Error('Missing isolated project')
      const tasks = await window.agent.listTasks({
        project_id: projects.data.active_project.project_id,
        cursor: null,
        limit: 20
      })
      if (!tasks.ok) throw new Error(tasks.error.message)
      const taskId = tasks.data.tasks[0].task_id
      const space = await window.agent.getSpace(taskId)
      const chat = await window.agent.getSpaceChat({ task_id: taskId })
      if (!space.ok || !chat.ok) throw new Error('Space facts unavailable')
      return {
        ids: space.data.space?.bindings?.map((b) => b.session_id),
        rounds: chat.data.rounds?.length,
        taskId
      }
    })
    expect(first.ids).toHaveLength(2)
    expect(first.rounds).toBe(1)
    await discussion.getByRole('button', { name: '确认并开始工作', exact: true }).click()
    const repeated = await page.evaluate(
      (task_id) => window.agent.getSpaceChat({ task_id }),
      first.taskId
    )
    expect(repeated.ok && repeated.data.rounds?.length).toBe(1)
  } finally {
    if (app) {
      // 本用例已明确启动 Goal，退出时通过原确认入口停止隔离运行。
      // Stop this test's explicitly started Goal through the original quit confirmation.
      await app.evaluate(({ dialog }) => {
        dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
      })
      await app.close()
    }
  }
})

/** 恢复部分重叠图，验证真实图几何和就地编辑，不用自动排布按钮掩盖初始问题。 Restore overlapping data and check actual graph geometry and local editing without manual layout. */
test('team graph repairs restored overlaps and keeps editing controls in view', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'team-graph-desktop-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  const app = await launch(path.join(root, 'data'), project)
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('图编辑体验')
    await page.getByLabel('阶段目标', { exact: true }).fill('设计四成员团队')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    const fixture = await page.evaluate(async () => {
      const projects = await window.agent.listProjects()
      if (!projects.ok || !projects.data.active_project) throw new Error('Missing project')
      const tasks = await window.agent.listTasks({
        project_id: projects.data.active_project.project_id,
        limit: 20,
        cursor: null
      })
      if (!tasks.ok) throw new Error(tasks.error.message)
      const taskId = tasks.data.tasks[0].task_id
      const opened = await window.agent.openTeamDesign({
        task_id: taskId,
        model_id: 'glm-5.3-flash'
      })
      if (!opened.ok) throw new Error(opened.error.message)
      const ids: string[] = Array.from({ length: 4 }, () => crypto.randomUUID())
      const saved = await window.agent.saveTeamDesign({
        task_id: taskId,
        config: {
          receiver_member_id: ids[0],
          organisation: 'central',
          members: ids.map((member_id, i) => ({
            member_id,
            name: ['协调实现', '独立审查', '资料调研', '验证成员'][i],
            role: '独立负责本项工作',
            model_id: 'glm-5.3-flash',
            position: { x: i * 30, y: i * 25 }
          })),
          edges: [
            {
              edge_id: crypto.randomUUID(),
              source_member_id: ids[0],
              target_member_id: ids[1],
              kind: 'delegate'
            },
            {
              edge_id: crypto.randomUUID(),
              source_member_id: ids[1],
              target_member_id: ids[0],
              kind: 'feedback'
            },
            {
              edge_id: crypto.randomUUID(),
              source_member_id: ids[0],
              target_member_id: ids[2],
              kind: 'delegate'
            },
            {
              edge_id: crypto.randomUUID(),
              source_member_id: ids[2],
              target_member_id: ids[3],
              kind: 'result'
            }
          ]
        }
      })
      if (!saved.ok) throw new Error(saved.error.message)
      return { taskId, ids }
    })
    await page.getByRole('button', { name: '打开团队设计', exact: true }).click()
    const panel = page.getByRole('region', { name: '合作空间', exact: true })
    const nodes = panel.locator('.space-graph .react-flow__node')
    await expect(nodes).toHaveCount(4)
    await expect(panel).toContainText('所属任务：图编辑体验')
    await expect
      .poll(async () =>
        nodes.evaluateAll((elements) => {
          const bounds = elements.map((node) => node.getBoundingClientRect())
          const area = elements[0].closest('.space-graph')!.getBoundingClientRect()
          return bounds.every(
            (a, i) =>
              a.left >= area.left &&
              a.right <= area.right &&
              a.top >= area.top &&
              a.bottom <= area.bottom &&
              bounds
                .slice(i + 1)
                .every(
                  (b) =>
                    a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top
                )
          )
        })
      )
      .toBe(true)
    // 图已显示不等于防抖保存已落盘，等到修复坐标保存后再比较后续编辑。
    // Visible layout can precede debounced persistence; compare edits after repaired coordinates are saved.
    await expect
      .poll(async () => {
        const design = await page.evaluate(
          (task_id) => window.agent.getTeamDesign({ task_id }),
          fixture.taskId
        )
        return design.ok && design.data.config?.members?.[1].position
      })
      .not.toEqual({ x: 30, y: 25 })
    const before = await page.evaluate(async (task_id) => {
      const design = await window.agent.getTeamDesign({ task_id })
      if (!design.ok) throw new Error(design.error.message)
      return design.data.config?.members
    }, fixture.taskId)
    await panel.getByRole('button', { name: '添加成员', exact: true }).click()
    await panel.getByLabel('成员名称', { exact: true }).fill('临时成员')
    await panel.getByRole('button', { name: '关闭成员编辑', exact: true }).click()
    await expect(nodes).toHaveCount(5)
    await expect
      .poll(async () => {
        const design = await page.evaluate(
          (task_id) => window.agent.getTeamDesign({ task_id }),
          fixture.taskId
        )
        return (
          design.ok && design.data.config?.members?.filter((m) => fixture.ids.includes(m.member_id))
        )
      })
      .toEqual(before)
    await panel.getByRole('button', { name: '添加关系', exact: true }).click()
    await expect(panel.getByLabel('关系目标', { exact: true })).toHaveValue('')
    await expect(panel.getByRole('button', { name: '创建关系', exact: true })).toBeDisabled()
    await expect(panel.locator('.react-flow__edge')).toHaveCount(4)
    await panel.getByLabel('关系目标', { exact: true }).selectOption({ label: '临时成员' })
    await panel.getByRole('button', { name: '创建关系', exact: true }).click()
    await expect(panel.locator('.react-flow__edge')).toHaveCount(5)
    await panel.getByRole('button', { name: '移除关系', exact: true }).click()
    await expect(panel.locator('.react-flow__edge')).toHaveCount(4)
    await panel
      .locator('.space-member-list')
      .getByRole('button', { name: /临时成员/ })
      .click()
    await panel.getByRole('button', { name: '移除成员配置（保留旧会话）', exact: true }).click()
    await expect(nodes).toHaveCount(4)
    for (const width of [1440, 1000]) {
      await page.setViewportSize({ width, height: 900 })
      await panel
        .locator('.space-member-list')
        .getByRole('button', { name: /协调实现/ })
        .click()
      const inspector = panel.locator('.space-inspector')
      await expect(
        inspector.getByRole('button', { name: '移除成员配置（保留旧会话）', exact: true })
      ).toBeInViewport()
      await expect(inspector).toContainText('协调实现 → 独立审查 · 委派')
      await expect(inspector).toContainText('独立审查 → 协调实现 · 反馈')
      await page.screenshot({ path: path.join(root, `inspector-${width}.png`) })
      await page.keyboard.press('Escape')
      await expect(inspector).toHaveCount(0)
    }
    await page.setViewportSize({ width: 1440, height: 900 })
    await panel.locator('.space-graph').scrollIntoViewIfNeeded()
    await panel.getByRole('button', { name: '展开大图', exact: true }).click()
    try {
      await expect
        .poll(async () => (await nodes.first().boundingBox())?.width ?? 0)
        .toBeGreaterThan(180)
    } finally {
      await page.screenshot({ path: path.join(root, 'graph.png') })
      const geometry = await panel.locator('.space-graph').evaluate((element) => {
        const ancestors = []
        for (let current: Element | null = element; current; current = current.parentElement) {
          const css = getComputedStyle(current)
          ancestors.push({
            name: current.className,
            rect: current.getBoundingClientRect().toJSON(),
            height: css.height,
            maxHeight: css.maxHeight,
            position: css.position,
            contain: css.contain,
            transform: css.transform
          })
        }
        return {
          ancestors,
          flow: element.querySelector('.react-flow')?.getBoundingClientRect().toJSON(),
          transform: element.querySelector('.react-flow__viewport')?.getAttribute('style')
        }
      })
      await writeFile(
        path.join(root, 'graph-geometry.json'),
        JSON.stringify(geometry, null, 2),
        'utf8'
      )
    }
    await panel.getByRole('button', { name: '收起大图', exact: true }).click()
    await expect(panel.locator('.space-graph.is-expanded')).toHaveCount(0)
  } finally {
    await app.close()
  }
})
