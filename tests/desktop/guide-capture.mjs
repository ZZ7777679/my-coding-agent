/** 采集隔离示例的真实桌面截图，不运行网络模型。 Capture real desktop guides with isolated offline examples. */
import {
  _electron as electron,
  expect
} from '../../apps/desktop/node_modules/@playwright/test/index.mjs'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const part = process.argv[2] ?? 'core'
const artifacts = path.join(repo, '.artifacts/tests')
await mkdir(artifacts, { recursive: true })
const root = await mkdtemp(path.join(artifacts, `guide-${part}-`))
const project = path.join(root, 'counter-demo')
const data = path.join(root, 'data')
await mkdir(project)
await mkdir(data)
await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n')
await writeFile(path.join(project, 'answer.py'), 'value = 1\n')
await writeFile(
  path.join(project, 'AGENTS.md'),
  '# 示例项目\n\n页面使用本地资源，避免不必要的依赖。\n'
)
await writeFile(
  path.join(project, 'index.html'),
  '<!doctype html>\n<html lang="zh-CN">\n<meta charset="utf-8">\n<title>计数器</title>\n<h1>我的计数器</h1>\n<button id="add">+1</button>\n<output id="count">0</output>\n<script>\nlet count = 0;\ndocument.querySelector("#add").onclick = () => {\n  document.querySelector("#count").value = ++count;\n};\n</script>\n</html>\n'
)
if (part === 'workbench') {
  execFileSync('git', ['init', '--quiet', project])
  execFileSync('git', ['-C', project, 'add', '--', 'main.py', 'index.html', 'AGENTS.md'])
  execFileSync('git', [
    '-C',
    project,
    '-c',
    'user.name=Guide Example',
    '-c',
    'user.email=guide@example.invalid',
    'commit',
    '-qm',
    'Initial counter example'
  ])
  await writeFile(
    path.join(project, 'main.py'),
    'def answer():\n    # 示例修改 / Example change\n    return 43\n'
  )
}
if (part === 'resources') {
  await writeFile(
    path.join(data, 'mcp.json'),
    JSON.stringify({
      servers: [
        {
          server_id: 'guide-local',
          name: '指南示例：本地工具服务',
          transport: 'stdio',
          command: path.join(repo, '.venv/Scripts/python.exe'),
          arguments: ['-X', 'utf8', path.join(repo, 'tests/support/mcp_catalog_fixture.py')]
        }
      ]
    })
  )
}
const env = {
  ...process.env,
  OPENCODE_API_KEY: 'desktop-test-credential-never-persist',
  MY_AGENT_PROJECT_DIR: project
}
delete env.ELECTRON_RUN_AS_NODE
delete env.ELECTRON_RENDERER_URL
const app = await electron.launch({
  args: [path.join(repo, 'tests/support/desktop_peer.cjs'), '--data-dir', data],
  env
})
const shots = []
const page = await app.firstWindow()
page.setDefaultTimeout(15000)

/** 保存截图和来源清单，不修改页面外观或伪造状态。 Save pixels and provenance without altering the UI. */
async function shot(name, target = page) {
  if (target !== page) await target.scrollIntoViewIfNeeded()
  await target.screenshot({ path: path.join(root, `${name}.png`) })
  shots.push(name)
  await writeFile(
    path.join(root, 'capture.json'),
    JSON.stringify(
      { part, root, project, model: 'offline DesktopModel fixture', screenshots: shots },
      null,
      2
    )
  )
  console.log(`Captured ${name}`)
}

/** 进入真实功能页。 Navigate via the visible sidebar. */
async function nav(name) {
  await page.getByRole('button', { name, exact: true }).click()
}

/** 用真实创建入口初始化示例任务。 Create the example task through the UI. */
async function task() {
  await nav('新建任务 →')
  await page.getByLabel('任务名称', { exact: true }).fill('单页计数器')
  await page
    .getByLabel('阶段目标', { exact: true })
    .fill('完成按钮加一、保存数字，并由审查会话检查结果。')
  if (part === 'core') await shot('task-create')
  await nav('创建任务与首会话')
  await expect(page.getByRole('heading', { name: '单页计数器', exact: true })).toBeVisible()
}

/** 发送离线样例，等待真实运行终态。 Send a fixture prompt and await the real run state. */
async function send(prompt) {
  await page.getByLabel('输入问题', { exact: true }).fill(prompt)
  await nav('发送')
  await expect(page.getByLabel('输入问题', { exact: true })).toHaveValue('')
  await expect(page.getByTestId('run-status')).toContainText('回答结束', { timeout: 20000 })
  await expect(page.getByRole('button', { name: '停止运行', exact: true })).toBeHidden()
}

try {
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1440, 1000))
  await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
  await app.evaluate(({ dialog }, folder) => {
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [folder] })
  }, project)
  await page.getByRole('button', { name: '选择项目文件夹', exact: false }).click()
  await expect(page.getByTestId('active-project-name')).toHaveText('counter-demo')
  if (part === 'core') await shot('project-home')
  await task()

  if (part === 'core') {
    await shot('task-overview')
    await nav('打开 / 补齐首会话')
    await send('请读取 main.py 并解释它的作用。')
    await shot('chat')
    await page.locator('.tree-session').first().click({ button: 'right' })
    await shot('session-menu')
    await page.keyboard.press('Escape')
    await nav('Trace')
    const trace = page.getByRole('complementary', { name: '执行轨迹', exact: true })
    await expect(trace.locator('.trace-row').first()).toBeVisible()
    await shot('trace')
    await trace.getByRole('button', { name: '关闭 Trace', exact: true }).click()
    await page.getByTestId('open-context').click()
    await shot('context')
    await page.getByTestId('request-materials').locator(':scope > button').click()
    await shot('context-materials')
    await page.getByTestId('open-memory').click()
    await nav('新增记忆')
    await page.getByLabel('记忆标题', { exact: true }).fill('页面资源保持本地')
    await page
      .getByLabel('记忆正文', { exact: true })
      .fill('计数器页面不依赖 CDN；优先使用浏览器和项目已有能力。')
    await nav('保存记忆')
    await expect(page.getByTestId('context-memory')).toContainText('页面资源保持本地')
    await nav('收起新记忆草稿')
    await page.getByRole('button', { name: /已保存记忆/ }).click()
    await shot('memory')
    await nav('关闭面板')
    await page.getByLabel('本次模式', { exact: true }).selectOption('goal')
    await page.locator('.goal-setup > summary').click()
    await page
      .getByLabel('输入问题', { exact: true })
      .fill('完成单页计数器，确认按钮加一并保留数字。')
    await shot('goal')
    await page.getByLabel('输入问题', { exact: true }).fill('')
    await page.getByLabel('本次模式', { exact: true }).selectOption('normal')
    await send('files: create')
    await send('files: edit')
    await nav('回退')
    const rollback = page.getByRole('complementary', { name: '请求回退' })
    await rollback.getByRole('button', { name: /files: edit/ }).click()
    await expect(rollback.getByRole('button', { name: '只恢复代码', exact: true })).toBeEnabled()
    await shot('rollback')
    await rollback.getByRole('button', { name: '关闭', exact: true }).click()
  } else if (part === 'resources') {
    await nav('Skill 管理')
    await expect(page.getByRole('region', { name: 'Skill 资源库' })).toBeVisible()
    await expect(page.locator('.skill-item').first()).toBeVisible()
    await shot('skills')
    await nav('MCP 管理')
    const server = page.locator('.mcp-server').filter({ hasText: '指南示例：本地工具服务' })
    await server.locator(':scope > summary').click()
    await server.getByRole('button', { name: '连接 / 重连', exact: true }).click()
    await expect(server.locator('.mcp-status')).toHaveText('已连接')
    await shot('mcp')
    await nav('工作流管理')
    await expect(page.getByRole('region', { name: '工作流管理', exact: true })).toBeVisible()
    await shot('workflows')
    await nav('设置与诊断')
    const environments = page.getByRole('region', { name: '项目执行环境' })
    await environments.getByText('导入已有环境', { exact: true }).click()
    await shot('execution-settings', environments)
    await environments.getByLabel('执行方式', { exact: true }).selectOption('sandbox')
    await shot('sandbox-settings', environments)
    await environments.getByLabel('执行方式', { exact: true }).selectOption('direct')
    await shot('diagnostics', page.locator('.diagnostics-card').first())
  } else if (part === 'workbench') {
    await nav('打开 / 补齐首会话')
    await nav('项目文件')
    await page.getByRole('button', { name: 'index.html', exact: true }).click()
    await expect(page.locator('.monaco-editor').first()).toBeVisible()
    await shot('editor')
    const tabs = page.getByRole('navigation', { name: '编码工作台', exact: true })
    await tabs.getByRole('button', { name: '本地 Git', exact: true }).click()
    await expect(page.locator('.local-git-panel')).toContainText('main.py')
    await shot('git')
    await tabs.getByRole('button', { name: '交互终端', exact: true }).click()
    const terminal = page.locator('.terminal-panel')
    await terminal.locator('.terminal-launch > summary').click()
    await terminal.getByRole('button', { name: '启动终端', exact: true }).click()
    await expect(terminal.locator('.terminal-toolbar')).toContainText('运行中')
    await terminal.getByLabel('交互终端输出与输入', { exact: true }).click()
    await page.keyboard.type('Get-Location')
    await page.keyboard.press('Enter')
    // 等终端输出绘制完成，仅影响截图；不作为产品执行条件。
    // Allow the terminal canvas to paint; this is only a capture delay.
    await page.waitForTimeout(1000)
    await shot('terminal')
  } else if (part === 'team') {
    const space = page.getByRole('region', { name: '合作空间', exact: true })
    await space.getByRole('button', { name: '创建合作空间草稿', exact: true }).click()
    for (const [name, role, scope] of [
      ['实现成员', '实现计数器并汇报结果', 'index.html'],
      ['审查成员', '只读检查页面与说明，返回建议', 'index.html、README.md']
    ]) {
      await space.getByRole('button', { name: '添加成员', exact: true }).click()
      await space.getByLabel('成员名称', { exact: true }).fill(name)
      await space.getByLabel('成员职责', { exact: true }).fill(role)
      await space.getByLabel('成员工作范围', { exact: true }).fill(scope)
    }
    await space.getByRole('button', { name: '添加关系', exact: true }).click()
    const source = await space.getByLabel('关系来源', { exact: true }).inputValue()
    const target = await space.getByLabel('关系目标', { exact: true }).inputValue()
    await space.getByLabel('关系来源', { exact: true }).selectOption(target)
    await space.getByLabel('关系目标', { exact: true }).selectOption(source)
    await space.getByLabel('关系类型', { exact: true }).selectOption('feedback')
    await space.getByLabel('关系说明', { exact: true }).fill('审查结果交回实现成员，按授权修复')
    await space.getByRole('button', { name: '自动排布', exact: true }).click()
    await space.getByRole('button', { name: '保存空间配置', exact: true }).click()
    await expect(space.getByRole('status')).toContainText('空间配置已保存')
    await space.getByRole('button', { name: '组建团队会话', exact: true }).click()
    await expect(space.getByRole('status')).toContainText('团队会话已组建')
    await expect(space.locator('.react-flow__node')).toHaveCount(2)
    await space.locator('.space-graph').scrollIntoViewIfNeeded()
    await space.locator('.react-flow__controls-fitview').click()
    await expect(space.locator('.react-flow__node').first()).toBeInViewport()
    await page.waitForTimeout(350)
    await shot('team-graph', space.locator('.space-graph'))
    await shot('team-settings')
    await space.getByRole('button', { name: '工作视角', exact: true }).click()
    const graph = page.getByRole('region', { name: '任务工作图', exact: true })
    await graph.getByRole('button', { name: '从流程补充骨架', exact: true }).click()
    await expect(graph.locator('.react-flow__node')).toHaveCount(7)
    await graph.getByRole('button', { name: '保存工作图', exact: true }).click()
    await shot('work-graph', graph.locator('.work-graph-canvas'))
  } else if (part === 'learning') {
    await nav('打开 / 补齐首会话')
    await send('读取 main.py，看看是否需要改进文件读取方式。')
    await page.getByText('复盘此会话', { exact: true }).click()
    await page.getByRole('textbox', { name: '关注点（可选）', exact: true }).fill('read_file')
    await nav('开始复盘')
    await expect(page.locator('.evolution-quick [role=status]')).toContainText('调查完成', {
      timeout: 20000
    })
    await shot('review-quick')
    await nav('查看本次改进')
    await shot('review-findings')
    await page.getByRole('button', { name: '查看实际参考材料', exact: true }).first().click()
    await shot('review-evidence')
    await page.keyboard.press('Escape')
    await page.locator('.evolution-budget > summary').click()
    await shot('review-budget', page.locator('.evolution-budget'))
  } else throw new Error(`Unknown capture part: ${part}`)
  console.log(`Guide screenshots: ${root}`)
} catch (error) {
  await page.screenshot({ path: path.join(root, 'failure.png') })
  await writeFile(
    path.join(root, 'failure.txt'),
    String(error) + '\n' + (await page.locator('body').innerText())
  )
  console.error(`Capture failed: ${root}\n${String(error)}`)
  process.exitCode = 1
} finally {
  await app.close()
}
