/** 首次使用者与资源接入的探索记录；只替换模型，不修复产品。
 * Exploratory onboarding and resource journeys; substitute the model without changing the product.
 */
import { electron, expect, test, type ElectronApplication } from './runtime'
import { artifacts, choose, python, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { once } from 'node:events'
import path from 'node:path'

type WindowPage = Awaited<ReturnType<ElectronApplication['firstWindow']>>

/** 每个检查点保存真实界面与可读文字，方便评估引用。
 * Save the real UI and readable text at each checkpoint for review evidence.
 */
async function capture(page: WindowPage, root: string, name: string): Promise<void> {
  await page.screenshot({ path: path.join(root, `${name}.png`) })
  await writeFile(path.join(root, `${name}.txt`), await page.locator('body').innerText(), 'utf8')
}

/** 使用独立数据根、项目和哨兵凭据启动真实桌面。
 * Launch the real desktop with isolated data, project and sentinel credentials.
 */
async function start(data: string, project: string): Promise<ElectronApplication> {
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  const pathName = Object.keys(env).find((name) => name.toLowerCase() === 'path') ?? 'PATH'
  env[pathName] = path.dirname(python) + path.delimiter + (env[pathName] ?? '')
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  return electron.launch({
    args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', data],
    env
  })
}

test('new user opens a project, creates a task, uses a skill and restores the session', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'persona-onboarding-first-'))
  console.log(`ONBOARDING_ARTIFACTS ${root}`)
  const project = path.join(root, 'first-project')
  const data = path.join(root, 'data')
  const source = path.join(root, 'local-skill')
  await mkdir(project)
  await mkdir(source)
  await writeFile(path.join(project, 'main.py'), 'def answer():\n    return 42\n', 'utf8')
  await writeFile(
    path.join(source, 'SKILL.md'),
    '---\nname: first-steps\ndescription: Read a small project before changing it.\n---\nRead main.py and explain the result.\n',
    'utf8'
  )
  let app = await start(data, project)
  let page = await app.firstWindow()
  try {
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await capture(page, root, '01-first-launch')
    await choose(app, null)
    await expect(page.getByRole('heading', { name: '还没有打开项目', exact: true })).toBeVisible()
    await choose(app, project)
    await expect(page.getByTestId('active-project-path')).toHaveText(project)
    await capture(page, root, '02-project-opened')
    await choose(app, path.join(root, 'missing-project'))
    await expect(page.getByTestId('active-project-path')).toHaveText(project)
    await capture(page, root, '03-invalid-project-keeps-selection')
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await page.getByRole('heading', { name: '项目执行环境', exact: true }).scrollIntoViewIfNeeded()
    await capture(page, root, '04a-default-execution-environment')
    const environment = page.getByRole('region', { name: '项目执行环境', exact: true })
    await environment.getByRole('button', { name: '查看当前项目实际 Python' }).click()
    await expect(environment).toContainText('Python 3.')
    await expect(environment).toContainText(path.basename(python))
    await page.getByLabel('默认模型', { exact: true }).scrollIntoViewIfNeeded()
    await capture(page, root, '04-model-settings')
    await page.getByLabel('默认模型', { exact: true }).selectOption('deepseek-v4.1-flash')
    await page.getByRole('button', { name: '保存默认模型', exact: true }).click()
    await expect(page.getByRole('status').filter({ hasText: '默认模型已保存' })).toBeVisible()
    await page.getByRole('button', { name: '项目工作台', exact: true }).click()
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await capture(page, root, '05-new-task-form')
    await expect(page.getByLabel('新会话模型', { exact: true })).toHaveValue('deepseek-v4.1-flash')
    await page.getByLabel('阶段目标', { exact: true }).fill('Read my first project')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await expect(page.getByRole('heading', { name: '任务流程', exact: true })).toBeVisible()
    await capture(page, root, '06-after-create-task')
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toBeVisible()
    await capture(page, root, '07-first-session')
    await page.getByRole('button', { name: 'Skill 管理', exact: true }).click()
    const library = page.getByRole('region', { name: 'Skill 资源库', exact: true })
    await library.getByText('从本地文件夹导入', { exact: true }).click()
    await library.getByLabel('导入 Skill 文件夹', { exact: true }).fill(source)
    await library.getByLabel('目录名', { exact: true }).fill('first-steps')
    await library.getByRole('combobox', { name: '保存位置', exact: true }).selectOption('project')
    await library.getByRole('button', { name: '导入目录与附属资源', exact: true }).click()
    await expect(
      library.getByRole('button', { name: 'first-steps · project', exact: true })
    ).toBeVisible()
    // 勾选由后端保存后返回，等待已持久化状态而非浏览器瞬时状态。
    // Selection reflects the backend save, so await persistence rather than an immediate DOM toggle.
    await library.getByLabel('本会话持续使用 first-steps project', { exact: true }).click()
    await expect(
      library.getByLabel('本会话持续使用 first-steps project', { exact: true })
    ).toBeChecked()
    await library.getByRole('button', { name: 'first-steps · project', exact: true }).click()
    await expect(library.getByLabel('Skill 正文')).toHaveValue(/Read main.py/)
    await capture(page, root, '08-skill-imported-selected')
    expect(
      await readFile(path.join(project, '.agents/skills/first-steps/SKILL.md'), 'utf8')
    ).toContain('Read main.py')
    await library.getByRole('button', { name: '关闭正文', exact: true }).click()
    await library
      .getByLabel('本会话持续使用 first-steps project', { exact: true })
      .scrollIntoViewIfNeeded()
    await capture(page, root, '09-skill-selection-controls')
    await page.locator('.tree-session').first().click()
    await page.getByLabel('输入问题').fill('finish with source')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await capture(page, root, '10-first-answer-no-environment-setup')
    await app.close()
    app = await start(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await expect(page.getByTestId('active-project-path')).toHaveText(project)
    await capture(page, root, '11-project-restored')
    const expand = page.getByRole('button', { name: '展开项目 first-project', exact: true })
    if (await expand.count()) await expand.click()
    await page.getByRole('button', { name: '展开任务 Read my first project', exact: true }).click()
    await page.locator('.tree-session').filter({ hasText: 'finish with source' }).first().click()
    await expect(page.getByLabel('会话模型')).toHaveValue('deepseek-v4.1-flash')
    await page.getByRole('button', { name: 'Skill 管理', exact: true }).click()
    await expect(
      page.getByLabel('本会话持续使用 first-steps project', { exact: true })
    ).toBeChecked()
    await page
      .getByLabel('本会话持续使用 first-steps project', { exact: true })
      .scrollIntoViewIfNeeded()
    await capture(page, root, '12-skill-selection-restored')
  } catch (error) {
    // 保留原始失败，即使窗口已关闭也不让截图错误覆盖它。
    // Preserve the original failure if a closed window prevents evidence capture.
    await capture(page, root, 'failure').catch((captureError: unknown) => {
      console.error('Failure screenshot unavailable', captureError)
    })
    throw error
  } finally {
    await app.close()
  }
})

test('resource user recovers from MCP authentication failure using the form', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'persona-onboarding-mcp-'))
  console.log(`ONBOARDING_ARTIFACTS ${root}`)
  const project = path.join(root, 'resource-project')
  const data = path.join(root, 'data')
  await mkdir(project)
  const peer = spawn(python, ['-X', 'utf8', '-m', 'tests.support.mcp_http_fixture'], {
    cwd: path.resolve(__dirname, '../..'),
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  })
  const exited = once(peer, 'exit')
  peer.stderr?.resume()
  const lines = createInterface({ input: peer.stdout! })
  const line = await Promise.race([
    once(lines, 'line').then(([value]) => String(value)),
    exited.then(() => {
      throw new Error('Local MCP fixture did not report its port')
    })
  ])
  const url = `http://127.0.0.1:${Number(line)}/mcp`
  let app: ElectronApplication | null = null
  let page: WindowPage | null = null
  try {
    app = await start(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    let mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    await capture(page, root, '01-mcp-first-entry')
    await mcp.getByRole('button', { name: '配置 GitHub', exact: true }).click()
    await capture(page, root, '02-github-preset-form')
    await mcp.getByLabel('名称', { exact: true }).fill('Local service for onboarding')
    await mcp.getByLabel('服务地址', { exact: true }).fill(url)
    await mcp.getByLabel('服务令牌', { exact: true }).fill('wrong-fixture-token')
    await mcp.getByRole('button', { name: '保存并测试连接', exact: true }).click()
    let card = mcp.locator('.mcp-server').filter({ hasText: 'Local service for onboarding' })
    await expect(card.locator('.mcp-status')).toHaveText('连接失败')
    await capture(page, root, '03-auth-failure-collapsed')
    await card.locator(':scope > summary').click()
    await expect(card).toContainText('401')
    await card.scrollIntoViewIfNeeded()
    await capture(page, root, '04-auth-failure-detail')
    await card.getByRole('button', { name: '编辑 / 启停', exact: true }).click()
    await expect(mcp.getByLabel('服务令牌', { exact: true })).toHaveValue('')
    await mcp.getByLabel('服务令牌', { exact: true }).fill('desktop-fixture-token')
    await mcp.getByRole('button', { name: '保存并测试连接', exact: true }).click()
    await expect(card.locator('.mcp-status')).toHaveText('已连接')
    await expect(card.locator('.mcp-tool')).toHaveCount(2)
    await card.scrollIntoViewIfNeeded()
    await capture(page, root, '05-recovered-connected')
    await card.getByRole('button', { name: '在当前项目停用', exact: true }).click()
    await expect(card).toContainText('仅资源库')
    await capture(page, root, '06-project-disabled')
    await card.getByRole('button', { name: '在当前项目启用', exact: true }).click()
    await expect(card).toContainText('当前项目已启用')
    await app.close()
    app = await start(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    mcp = page.getByRole('region', { name: 'MCP 资源库', exact: true })
    card = mcp.locator('.mcp-server').filter({ hasText: 'Local service for onboarding' })
    await card.locator(':scope > summary').click()
    await expect(card).toContainText('已加密保存令牌')
    await card.getByRole('button', { name: '连接 / 重连', exact: true }).click()
    await expect(card.locator('.mcp-status')).toHaveText('已连接')
    await card.scrollIntoViewIfNeeded()
    await capture(page, root, '07-restored-and-reconnected')
  } catch (error) {
    if (page)
      await capture(page, root, 'failure').catch((captureError: unknown) => {
        console.error('Failure screenshot unavailable', captureError)
      })
    throw error
  } finally {
    await app?.close()
    lines.close()
    if (peer.exitCode === null) peer.kill()
    await exited
  }
})
