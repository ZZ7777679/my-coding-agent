/** 空项目读写、Plan 授权与历史 diff。 Empty-project writes, Plan grants and historical diffs. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, readdir } from 'node:fs/promises'
import path from 'node:path'

/** 模型替身驱动真实桌面 / 文件，重启后结果仍可查看。 Fake model with real desktop/files and restart. */
test('M2 files persist edits and diffs while Plan blocks unauthorized writes', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-files-'))
  const dataDir = path.join(root, 'data')
  const project = path.join(root, 'project')
  await mkdir(project)
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const launch = () =>
    electron.launch({
      args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', dataDir],
      env
    })
  let app = await launch()
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('从空目录创建简单 Python 文件')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await expect(page.getByLabel('本次模式', { exact: true })).toHaveValue('normal')
    await page.getByLabel('本次模式', { exact: true }).selectOption('plan')
    await page.getByLabel('输入问题').fill('files:create')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('工具调用失败')
    expect(await readdir(project)).toEqual([])
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeDisabled()
    await page.getByLabel('输入问题').fill('files:document')
    await page.getByLabel('允许保存的计划文档').fill('docs/plan.md')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    expect(await readFile(path.join(project, 'docs/plan.md'), 'utf8')).toBe('# Plan\n')
    await page.getByLabel('本次模式', { exact: true }).selectOption('normal')
    await page.getByLabel('输入问题').fill('files:create')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('chat-history')).toContainText('files:create')
    await expect
      .poll(async () => readFile(path.join(project, 'src/main.py'), 'utf8').catch(() => ''))
      .toBe('print(1)\n')
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await page.getByLabel('输入问题').fill('files:edit')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect
      .poll(async () => readFile(path.join(project, 'src/main.py'), 'utf8'))
      .toBe('print(2)\n')
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    const changes = page.getByRole('complementary', { name: '修改成果' })
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.getByRole('button', { name: '查看修改成果', exact: true }).click()
    await changes
      .getByRole('button', { name: 'src/main.py · 编辑 · 已保存到项目', exact: true })
      .click()
    await expect(page.getByTestId('change-diff')).toContainText('-print(1)')
    await expect(page.getByTestId('change-diff')).toContainText('+print(2)')
    expect(await readdir(project)).not.toContain('.git')
    const sessions = await readdir(path.join(dataDir, 'sessions'))
    const records = await readdir(path.join(dataDir, 'changes', sessions[0]))
    expect(records).toHaveLength(3)
    for (const file of records)
      expect(
        await readFile(path.join(dataDir, 'changes', sessions[0], file), 'utf8')
      ).not.toContain(sentinel)
    await expect(page.getByRole('button', { name: '停止运行', exact: true })).toHaveCount(0)
    await page.screenshot({ path: path.join(root, 'files-diff.png') })
    await app.close()
    app = await launch()
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').first().click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await expect(page.getByLabel('本次模式', { exact: true })).toHaveValue('normal')
    const restored = page.getByRole('complementary', { name: '修改成果' })
    await page.getByLabel('会话选项', { exact: true }).click()
    await page.getByRole('button', { name: '查看修改成果', exact: true }).click()
    await expect(
      restored.getByRole('button', { name: 'src/main.py · 编辑 · 已保存到项目', exact: true })
    ).toBeVisible()
    expect(await readFile(path.join(project, 'src/main.py'), 'utf8')).toBe('print(2)\n')
  } finally {
    await app.close()
  }
})
