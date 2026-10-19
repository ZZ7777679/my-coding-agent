/** M5 真实文件工作台：保存、Agent 冲突、选区引用和重启草稿。 Real file workbench saves, Agent conflicts, references and restart drafts. */
import { electron, expect, test, type ElectronApplication } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import type { Page } from '../../apps/desktop/node_modules/@playwright/test'

/** 只有模型替换为离线夹具，保留 Electron/IPC/Python/Monaco 链路。 Substitute only the model while retaining Electron, IPC, Python and Monaco. */
async function launchWorkbench(dataDir: string, project: string): Promise<ElectronApplication> {
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  return electron.launch({
    args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', dataDir],
    env
  })
}

/** 真正使用键盘编辑 Monaco，不从 renderer 写文件或伪造 editor 状态。 Edit Monaco through real keystrokes without renderer filesystem access or fake state. */
async function replaceBuffer(page: Page, text: string, merge = false): Promise<void> {
  const host = merge
    ? page.locator('.monaco-diff-editor .editor.modified')
    : page.locator('.workspace-code .monaco-editor').first()
  await expect(host).toBeVisible()
  await host.locator('.view-lines').click()
  await page.keyboard.press('Control+A')
  await page.keyboard.insertText(text)
}

/** 真实桌面联合场景不调用真实模型，不使用个人项目或数据根。 Exercise real desktop integration without real models or personal directories. */
test('M5 workbench preserves dirty edits across Agent writes and restart, with selected references', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-workbench-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(path.join(project, 'src'), { recursive: true })
  const file = path.join(project, 'src/main.py')
  await writeFile(file, Buffer.from('\ufeffprint(1)\r\n', 'utf8'))
  let app = await launchWorkbench(data, project)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('文件工作台验收')
    await page.getByLabel('阶段目标', { exact: true }).fill('核对原项目保存、草稿与并排冲突')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    const sessions = await readdir(path.join(data, 'sessions'))
    expect(sessions).toHaveLength(1)
    const sessionId = sessions[0]
    await page.getByRole('button', { name: '编码工作台', exact: true }).click()
    await page
      .getByRole('navigation', { name: '项目文件树', exact: true })
      .getByRole('button', { name: 'src/main.py', exact: true })
      .click()
    const saved = 'print(1)\n# saved by user\n'
    await replaceBuffer(page, saved)
    await page
      .locator('.workspace-code-toolbar')
      .getByRole('button', { name: '保存', exact: true })
      .click()
    await expect.poll(() => readFile(file, 'utf8')).toBe('\ufeff' + saved.replaceAll('\n', '\r\n'))
    await expect(page.locator('.workspace-code > footer')).toContainText('已与保存基线一致')
    const dirty = saved + '# unsaved draft\n'
    await replaceBuffer(page, dirty)
    await expect
      .poll(async () => {
        const result = await page.evaluate(
          (id) => window.agent.documentsDrafts({ session_id: id }),
          sessionId
        )
        return result.ok ? result.data.drafts[0]?.content : ''
      })
      .toBe(dirty)
    await page.getByRole('button', { name: '返回对话', exact: true }).click()
    const prompt =
      'files:edit\n\n| 项目 | 状态 |\n| --- | --- |\n| 文件 | 核对 |\n\n```python\nprint(2)\n```'
    await page.getByLabel('输入问题', { exact: true }).fill(prompt)
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect.poll(() => readFile(file, 'utf8')).toBe('\ufeffprint(2)\r\n# saved by user\r\n')
    await expect(page.getByTestId('chat-history').locator('.markdown-content table')).toBeVisible()
    await expect(
      page.getByTestId('chat-history').getByRole('button', { name: '复制代码', exact: true })
    ).toBeVisible()
    await page.getByRole('button', { name: '编码工作台', exact: true }).click()
    await page
      .locator('.workspace-code-toolbar')
      .getByRole('button', { name: '保存', exact: true })
      .click()
    await expect(
      page.getByText('左：当前磁盘；右：未保存缓冲（可编辑）。', { exact: true })
    ).toBeVisible()
    expect(await readFile(file, 'utf8')).not.toContain('unsaved draft')
    const merged = 'print(2)\n# saved by user\n# unsaved draft\n'
    await replaceBuffer(page, merged, true)
    await page.getByRole('button', { name: '采用此磁盘基线并保留合并内容', exact: true }).click()
    await page
      .locator('.workspace-code-toolbar')
      .getByRole('button', { name: '保存', exact: true })
      .click()
    await expect.poll(() => readFile(file, 'utf8')).toBe('\ufeff' + merged.replaceAll('\n', '\r\n'))
    const restored = merged + '# restored after restart\n'
    await replaceBuffer(page, restored)
    await expect
      .poll(async () => {
        const result = await page.evaluate(
          (id) => window.agent.documentsDrafts({ session_id: id }),
          sessionId
        )
        return result.ok ? result.data.drafts[0]?.content : ''
      })
      .toBe(restored)
    await page.keyboard.press('Control+A')
    await page.getByRole('button', { name: '引用选区 / 文件', exact: true }).click()
    const chip = page.locator('.attachment-chip').first()
    await expect(chip).toContainText('草稿')
    await chip.getByRole('button').first().click()
    await expect(page.locator('.input-attachments pre')).toContainText('# restored after restart')
    expect(await readFile(file, 'utf8')).not.toContain('restored after restart')
    await page.getByRole('button', { name: '编码工作台', exact: true }).click()
    const nav = page.getByRole('navigation', { name: '编码工作台', exact: true })
    await nav.getByRole('button', { name: '交互终端', exact: true }).click()
    await expect(page.locator('.code-workbench .workbench-pane:not([hidden])')).toHaveCount(1)
    await expect(page.locator('.workspace-editor')).toBeHidden()
    await nav.getByRole('button', { name: '本地 Git', exact: true }).click()
    await expect(page.locator('.code-workbench .workbench-pane:not([hidden])')).toHaveCount(1)
    await expect(page.locator('.terminal-panel')).toBeHidden()
    await nav.getByRole('button', { name: '文件 / 编辑器', exact: true }).click()
    await expect(page.locator('.workspace-code > footer')).toContainText('未保存到项目')
    await page.screenshot({ path: path.join(root, 'dirty-buffer.png') })
    await app.close()
    app = await launchWorkbench(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').filter({ hasText: '文件工作台验收' }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByRole('button', { name: '编码工作台', exact: true }).click()
    await expect(page.locator('.workspace-tabs')).toContainText('main.py ●')
    await expect(page.locator('.workspace-code .view-lines')).toContainText(
      '# restored after restart'
    )
    expect(await readFile(file, 'utf8')).not.toContain('restored after restart')
    await page.screenshot({ path: path.join(root, 'restored-buffer.png') })
    await writeFile(
      path.join(root, 'report.json'),
      JSON.stringify(
        {
          session_id: sessionId,
          manual_saved: true,
          bom_crlf_preserved: true,
          agent_conflict_preserved_both: true,
          selected_draft_reference: true,
          restarted_draft_restored: true,
          real_model_requests: 0
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

/** 真实 Pyright 查询与 UTF-16 重命名经 Monaco 和共享写入器闭环。 Verify real Pyright and UTF-16 rename through Monaco and the shared writer. */
test('M5 editor uses real LSP and preserves rename drafts until explicit save', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-language-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  const file = path.join(project, 'main.py')
  const original = 'label = "😀"; value = 1\nprint(value)\nnumber: int = "bad"\n'
  await writeFile(file, original, 'utf8')
  const app = await launchWorkbench(data, project)
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('真实语言服务验收')
    await page.getByLabel('阶段目标', { exact: true }).fill('验证代码导航与重命名草稿')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByRole('button', { name: '编码工作台', exact: true }).click()
    await page
      .getByRole('navigation', { name: '项目文件树', exact: true })
      .getByRole('button', { name: 'main.py', exact: true })
      .click()
    const operations = page.getByLabel('代码理解操作', { exact: true })
    await operations.getByRole('button', { name: '诊断', exact: true }).click()
    await expect(page.locator('.workspace-language-panel')).toContainText('bad')
    await expect(page.locator('.workspace-code .squiggly-error').first()).toBeVisible()
    await page.getByLabel('跳转行号', { exact: true }).fill('2')
    await page.getByRole('button', { name: '跳转', exact: true }).click()
    await page.keyboard.press('Home')
    for (let i = 0; i < 7; ++i) await page.keyboard.press('ArrowRight')
    await operations.getByRole('button', { name: '引用', exact: true }).click()
    await expect(page.locator('.workspace-language-panel')).toContainText('main.py:1:')
    await operations.getByLabel('新符号名称', { exact: true }).fill('renamed')
    await operations.getByRole('button', { name: '预览重命名', exact: true }).click()
    const panel = page.locator('.workspace-language-panel')
    await expect(panel).toContainText('main.py · 2 处 · 草稿')
    await panel.getByRole('button', { name: '比较建议', exact: true }).click()
    await expect(panel.locator('.workspace-rename-diff')).toContainText('renamed')
    expect(await readFile(file, 'utf8')).toBe(original)
    await panel.getByRole('checkbox').check()
    await expect(
      panel.getByRole('button', { name: '保存选中的磁盘建议', exact: true })
    ).toBeDisabled()
    await panel.getByRole('button', { name: '应用选中建议到缓冲', exact: true }).click()
    await expect(page.locator('.workspace-code > footer')).toContainText('未保存到项目')
    expect(await readFile(file, 'utf8')).toBe(original)
    await page
      .locator('.workspace-code-toolbar')
      .getByRole('button', { name: '保存', exact: true })
      .click()
    await expect.poll(() => readFile(file, 'utf8')).toBe(original.replaceAll('value', 'renamed'))
    await page.screenshot({ path: path.join(root, 'language-rename.png') })
    await writeFile(
      path.join(root, 'report.json'),
      JSON.stringify(
        {
          real_server: 'pyright',
          diagnostics_nonblocking: true,
          references: true,
          utf16_rename: true,
          preview_no_write: true,
          draft_no_write: true,
          explicit_save: true,
          real_model_requests: 0
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
