/** M4 桌面入口使用真实 RPC，只替换模型。 M4 desktop journey with real RPC and a model substitute. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

test('M4 workflow, skill picker, MCP catalog and Trace remain usable', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-m4-'))
  const project = path.join(root, 'project')
  await mkdir(path.join(project, '.agents/skills/local-method'), { recursive: true })
  await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n')
  await writeFile(
    path.join(project, '.agents/skills/local-method/SKILL.md'),
    '---\nname: local-method\ndescription: Local method\n---\nUse small changes.\n'
  )
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const launch = () =>
    electron.launch({
      args: [
        path.resolve(__dirname, '../support/desktop_peer.cjs'),
        '--data-dir',
        path.join(root, 'data')
      ],
      env
    })
  let app = await launch()
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('M4 read main.py')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await expect(page.getByRole('heading', { name: '任务流程', exact: true })).toBeVisible()
    await page.getByLabel('当前阶段', { exact: true }).selectOption('implement')
    await page.getByRole('button', { name: '保存任务流程', exact: true }).click()
    await expect(page.getByRole('button', { name: '保存任务流程', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await expect(page.locator('.skills-picker')).toHaveCount(0)
    await page.getByRole('button', { name: 'Skill 管理', exact: true }).click()
    const skill = page.getByRole('region', { name: 'Skill 资源库', exact: true })
    // 状态在后端保存后更新；等待实际持久化结果。 Await the persisted backend selection.
    await skill.getByLabel('选择 local-method project', { exact: true }).click()
    await expect(skill.getByLabel('选择 local-method project', { exact: true })).toBeChecked()
    await skill.getByRole('button', { name: 'local-method · project', exact: true }).click()
    await expect(skill.getByLabel('Skill 正文')).toHaveValue(/Use small changes\./)
    await skill.getByRole('button', { name: '关闭正文', exact: true }).click()
    await expect(skill.getByLabel('Skill 正文')).toHaveCount(0)
    const plan = skill
      .locator('.skill-item')
      .filter({ has: page.getByRole('button', { name: 'plan · builtin', exact: true }) })
    await plan.getByRole('button', { name: '导入当前项目', exact: true }).click()
    await expect(skill.getByRole('button', { name: 'plan · project', exact: true })).toBeVisible()
    expect(await readFile(path.join(project, '.agents/skills/plan/SKILL.md'), 'utf8')).toContain(
      'name: plan'
    )
    await page.screenshot({ path: path.join(root, 'm4-skills.png') })
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    const mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    await expect(mcp).toContainText('未连接')
    await mcp.getByRole('button', { name: '新增服务', exact: true }).click()
    await mcp.getByLabel('名称', { exact: true }).fill('Library server')
    await mcp.getByLabel('程序路径', { exact: true }).fill('fixture-only-not-run')
    await mcp.getByRole('button', { name: '保存配置', exact: true }).click()
    const server = mcp
      .locator('details')
      .filter({ has: page.locator(':scope > summary', { hasText: /^Library server/ }) })
      .first()
    await server.locator(':scope > summary').click()
    await expect(server).toContainText('仅资源库')
    await server.getByRole('button', { name: '在当前项目启用', exact: true }).click()
    await expect(server).toContainText('当前项目已启用')
    await page.screenshot({ path: path.join(root, 'm4-mcp.png') })
    await page
      .locator('.tree-session.selected, .tree-session.active, .tree-session')
      .first()
      .click()
    await page.getByLabel('输入问题').fill('finish with source')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(page.locator('.tool-summary').first()).toContainText('read_file')
    await expect(page.locator('.tool-summary pre')).toHaveCount(0)
    await page.locator('.tool-summary button').first().click()
    const trace = page.getByRole('complementary', { name: '执行轨迹', exact: true })
    await expect(trace).toBeVisible()
    await trace.locator('.trace-row[open]').getByText('原始结果', { exact: true }).click()
    await expect(trace.locator('.trace-row[open] pre').first()).toContainText('main.py')
    await trace.getByRole('button', { name: '关闭 Trace', exact: true }).click()
    await expect(trace).toHaveCount(0)
    await page.getByRole('button', { name: /折叠本轮过程/ }).click()
    await expect(page.locator('.tool-summary')).toHaveCount(0)
    await page.getByRole('button', { name: /展开本轮过程/ }).click()
    await app.close()
    app = await launch()
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    const expandProject = page.getByRole('button', { name: '展开项目 project', exact: true })
    if (await expandProject.count()) await expandProject.click()
    await page.getByRole('button', { name: '展开任务 M4 read main.py', exact: true }).click()
    const session = page.locator('.tree-session').filter({ hasText: 'finish with source' }).first()
    await session.click()
    await page.getByRole('button', { name: 'Trace', exact: true }).click()
    await expect(page.getByRole('complementary', { name: '执行轨迹' })).toContainText('read_file')
    await page.screenshot({ path: path.join(root, 'm4-trace.png') })
  } finally {
    await app.close()
  }
})
