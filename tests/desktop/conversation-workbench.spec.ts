/** 会话追加、折叠卡片与真实文件／终端联合验收；模型为离线样本。
 * Exercise conversation supplements, worker cards and real files/terminals with an offline model. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

test('conversation keeps supplements, readable workers, editor drafts and both shells', async () => {
  test.setTimeout(120000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'conversation-workbench-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(path.join(project, 'src'), { recursive: true })
  const file = path.join(project, 'src', 'hello world.py')
  await writeFile(file, 'print("original")\n')
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const app = await electron.launch({
    args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', data],
    env
  })
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('会话中编辑与运行')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    const sid = await page.locator('.tree-session.selected').getAttribute('data-session-id')
    if (!sid) throw new Error('Session missing')
    await page.getByLabel('本次模式').selectOption('normal')
    await page.getByLabel('输入问题').fill('supplement: wait')
    await page.getByTestId('send-message').click()
    await expect(page.getByTestId('send-message')).toHaveText('追加要求')
    await page.getByLabel('输入问题').fill('supplement: appended')
    await page.getByTestId('send-message').click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(page.locator('.chat-history')).toContainText(
      'Supplement delivered in the same run.'
    )
    await expect(page.locator('.input-delivery')).toContainText('已纳入后续上下文')
    const facts = (await readFile(path.join(data, 'sessions', sid, 'events.jsonl'), 'utf8'))
      .trim()
      .split('\n')
      .map((line) => JSON.parse(line))
    expect(facts.filter((fact) => fact.data.kind === 'run.accepted')).toHaveLength(1)

    await page.getByRole('button', { name: '开启子 Agent', exact: true }).click()
    await page.getByTestId('workers').locator(':scope > button[aria-expanded]').click()
    await expect(page.getByLabel('允许拆分子 agent')).toBeChecked()
    await page.getByRole('button', { name: '返回对话', exact: true }).click()
    for (let i = 0; i < 2; i++) {
      await page.getByLabel('输入问题').fill('m3: failing worker')
      await page.getByTestId('send-message').click()
      await expect(page.getByTestId('run-status')).toContainText('运行失败')
    }
    await page.getByTestId('workers').locator(':scope > button[aria-expanded]').click()
    const cards = page.locator('.worker-card')
    await expect(cards).toHaveCount(2)
    await cards.nth(0).locator(':scope > summary').click()
    await cards.nth(1).locator(':scope > summary').click()
    await expect(cards.nth(0)).not.toHaveAttribute('open')
    await expect(cards.nth(0).locator(':scope > summary')).toHaveText('文档与进度审查')
    await expect(cards.nth(1).locator('.worker-card-body')).toContainText('只读已存在的阶段记录')
    await expect(cards.nth(1).locator('.worker-card-body')).toContainText(
      'I will inspect the progress directory'
    )
    await page.screenshot({ path: path.join(root, 'worker-cards.png') })
    await page.getByRole('button', { name: '返回对话', exact: true }).click()
    await page.getByTestId('workers').locator(':scope > button[aria-expanded]').click()
    await expect(cards.nth(0)).not.toHaveAttribute('open')
    await expect(cards.nth(1)).toHaveAttribute('open')
    await page.getByRole('button', { name: '返回对话', exact: true }).click()

    await page.getByLabel('输入问题').fill('保留已有草稿')
    await page.getByRole('button', { name: '项目文件', exact: true }).click()
    await page
      .getByRole('navigation', { name: '项目文件树', exact: true })
      .getByRole('button', { name: 'src/hello world.py', exact: true })
      .click()
    const editor = page.locator('.workspace-code .monaco-editor').first()
    await editor.locator('.view-lines').click()
    await page.keyboard.press('Control+A')
    await page.keyboard.insertText('print("saved")\n')
    await page
      .locator('.workspace-code-toolbar')
      .getByRole('button', { name: '保存', exact: true })
      .click()
    await expect(page.locator('.workspace-notice')).toContainText('已保存到原项目')
    await expect.poll(() => readFile(file, 'utf8')).toBe('print("saved")\n')
    await editor.locator('.view-lines').click()
    await page.keyboard.press('Control+End')
    await page.keyboard.insertText('# unsaved\n')
    await page.getByRole('button', { name: '关闭工作台', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toHaveValue('保留已有草稿')
    await page.getByRole('button', { name: '项目文件', exact: true }).click()
    await expect(page.locator('.workspace-code > footer')).toContainText('未保存到项目')
    await page.getByRole('button', { name: '让 Agent 运行', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toHaveValue(/保留已有草稿[\s\S]*src\/hello world.py/)
    expect(await readFile(file, 'utf8')).not.toContain('unsaved')
    await page.getByRole('button', { name: '项目文件', exact: true }).click()
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1780, 980))
    await page.screenshot({ path: path.join(root, 'conversation-editor-wide.png') })
    const nav = page.getByRole('navigation', { name: '编码工作台', exact: true })
    for (const shell of ['PowerShell', 'CMD']) {
      await nav.getByRole('button', { name: '文件 / 编辑器', exact: true }).click()
      if (
        !(await page
          .locator('.file-execution-menu')
          .evaluate((node) => (node as HTMLDetailsElement).open))
      )
        await page.locator('.file-execution-menu > summary').click()
      await page
        .locator('.file-execution-menu')
        .getByRole('button', { name: shell, exact: true })
        .click()
      await expect(page.locator('.terminal-toolbar')).toContainText('运行中')
      await page.getByLabel('交互终端输出与输入', { exact: true }).click()
      const command =
        shell === 'CMD' ? 'echo actual> cmd.txt' : 'Set-Content -LiteralPath ps.txt -Value actual'
      await page.keyboard.type(command)
      await page.keyboard.press('Enter')
      await expect
        .poll(() =>
          readFile(path.join(project, 'src', shell === 'CMD' ? 'cmd.txt' : 'ps.txt'), 'utf8').catch(
            () => ''
          )
        )
        .toContain('actual')
      await page.getByRole('button', { name: '关闭终端进程', exact: true }).click()
      await expect(page.locator('.terminal-toolbar')).toContainText('已关闭')
    }
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1000, 740))
    await nav.getByRole('button', { name: '文件 / 编辑器', exact: true }).click()
    await page.screenshot({ path: path.join(root, 'conversation-editor-narrow.png') })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    await page.getByRole('button', { name: '关闭工作台', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toHaveValue(/保留已有草稿/)
  } catch (error) {
    const page = await app.firstWindow()
    await page.screenshot({ path: path.join(root, 'failure.png') })
    await writeFile(path.join(root, 'failure.txt'), await page.locator('body').innerText())
    throw error
  } finally {
    await app.close()
  }
})
