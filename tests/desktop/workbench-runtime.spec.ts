/** M5 实际终端与本地索引的原生验收，不调用模型。 Native M5 terminal and local-index acceptance without model calls. */
import { expect, test } from './runtime'
import { artifacts, choose, launch } from './helpers'
import { mkdir, mkdtemp, readFile, stat, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import path from 'node:path'
import type { Page } from '../../apps/desktop/node_modules/@playwright/test'

/** 只读取真实后端输出作证据，输入始终经过 xterm 键盘事件。 Read actual backend evidence while sending input through xterm keyboard events. */
async function output(page: Page, terminalId: string): Promise<string> {
  let afterSeq = 0
  let text = ''
  // PSReadLine 重绘能超过单帧上限，证据也按公开游标分页读取。
  // PSReadLine redraws can exceed one frame, so evidence follows the public cursor.
  while (true) {
    const result = await page.evaluate((params) => window.agent.readTerminal(params), {
      terminal_id: terminalId,
      after_seq: afterSeq
    })
    if (!result.ok) throw new Error(result.error.message)
    text += result.data.output.map((chunk) => chunk.text).join('')
    if (!result.data.output.length || result.data.next_seq <= afterSeq) return text
    afterSeq = result.data.next_seq
  }
}

/** 单窗口串行验证实际 PowerShell、尺寸同步、中断与 Git 暂存。 Verify PowerShell, resizing, interruption and Git staging sequentially in one window. */
test('M5 native workbench controls real PowerShell and explicit local Git index', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-runtime-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  await writeFile(path.join(project, 'alpha.txt'), 'alpha index evidence\n', 'utf8')
  await writeFile(path.join(project, 'beta.txt'), 'beta stays selected independently\n', 'utf8')
  const unique = randomUUID().replaceAll('-', '')
  const app = await launch(data, project)
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('终端与本地Git原生验收')
    await page.getByLabel('阶段目标', { exact: true }).fill('通过实际工作台操作终端与索引')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByRole('button', { name: '项目文件', exact: true }).click()
    const nav = page.getByRole('navigation', { name: '编码工作台', exact: true })
    await nav.getByRole('button', { name: '交互终端', exact: true }).click()
    const terminal = page.locator('.terminal-panel')
    await terminal.locator('.terminal-launch > summary').click()
    await expect(terminal.getByLabel('程序', { exact: true })).toHaveValue('powershell.exe')
    await terminal.getByRole('button', { name: '启动终端', exact: true }).click()
    await expect(terminal.locator('.terminal-toolbar')).toContainText('运行中')
    const terminalId = (await terminal.locator('.terminal-assignment').innerText()).match(
      /终端 ID ([a-zA-Z0-9_-]+)/
    )?.[1]
    if (!terminalId) throw new Error('Terminal ID was not rendered')
    const screen = terminal.getByLabel('交互终端输出与输入', { exact: true })
    await screen.click()
    // 拼接标记避免命令回显本身被误认作命令执行成功。
    // Concatenate the marker so command echo cannot masquerade as execution output.
    await page.keyboard.type(`echo ('M5_PTY_' + '${unique}')`)
    await page.keyboard.press('Enter')
    await expect.poll(() => output(page, terminalId)).toContain(`M5_PTY_${unique}`)
    const before = await page.evaluate(
      (id) => window.agent.readTerminal({ terminal_id: id, after_seq: 0 }),
      terminalId
    )
    if (!before.ok) throw new Error(before.error.message)
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1300, 900))
    await expect
      .poll(async () => {
        const result = await page.evaluate(
          (id) => window.agent.readTerminal({ terminal_id: id, after_seq: 0 }),
          terminalId
        )
        return (
          result.ok &&
          (result.data.summary.cols !== before.data.summary.cols ||
            result.data.summary.rows !== before.data.summary.rows)
        )
      })
      .toBe(true)
    await screen.click()
    await page.keyboard.type(
      `echo ('READY_' + '${unique}'); Start-Sleep -Seconds 60; echo ('UNEXPECTED_' + '${unique}')`
    )
    const readyStarted = Date.now()
    await page.keyboard.press('Enter')
    try {
      await expect
        .poll(() => output(page, terminalId), { timeout: 15000 })
        .toContain(`READY_${unique}`)
    } catch (error) {
      await page.screenshot({ path: path.join(root, 'terminal-long-line-failure.png') })
      await writeFile(
        path.join(root, 'terminal-long-line-failure.txt'),
        await terminal.innerText(),
        'utf8'
      )
      throw error
    }
    const readyMilliseconds = Date.now() - readyStarted
    await terminal.getByRole('button', { name: '中断 Ctrl+C', exact: true }).click()
    await screen.click()
    await page.keyboard.type(`echo ('AFTER_CTRL_C_' + '${unique}')`)
    await page.keyboard.press('Enter')
    await expect.poll(() => output(page, terminalId)).toContain(`AFTER_CTRL_C_${unique}`)
    expect(await output(page, terminalId)).not.toContain(`UNEXPECTED_${unique}`)
    await terminal.getByRole('button', { name: '关闭终端进程', exact: true }).click()
    await expect(terminal.locator('.terminal-toolbar')).toContainText('已关闭')
    const closed = await page.evaluate(
      (id) => window.agent.readTerminal({ terminal_id: id, after_seq: 0 }),
      terminalId
    )
    if (!closed.ok) throw new Error(closed.error.message)
    expect(closed.data.summary.status).toBe('stopped')
    expect(closed.data.summary.finished_at).not.toBeNull()
    await page.screenshot({ path: path.join(root, 'terminal-resized-interrupted.png') })
    await expect(stat(path.join(project, '.git'))).rejects.toThrow()
    await nav.getByRole('button', { name: '本地 Git', exact: true }).click()
    const git = page.locator('.local-git-panel')
    const gitStatus = await page.evaluate(
      (projectId) => window.agent.getGitStatus({ project_id: projectId }),
      closed.data.summary.project_id
    )
    await writeFile(path.join(root, 'git-status.json'), JSON.stringify(gitStatus, null, 2), 'utf8')
    await page.screenshot({ path: path.join(root, 'git-before-init.png') })
    await git.getByRole('button', { name: /^(初始化本地 Git|在本项目初始化独立仓库)$/ }).click()
    await expect(git.getByLabel('选择 alpha.txt', { exact: true })).toBeVisible()
    await git.getByLabel('选择 alpha.txt', { exact: true }).check()
    await git.getByLabel('选择 beta.txt', { exact: true }).check()
    await git.getByRole('button', { name: '暂存所选文件（2）', exact: true }).click()
    await git.getByRole('tab', { name: '暂存区', exact: true }).click()
    await expect(git.locator('.local-git-files > li')).toHaveCount(2)
    await git.getByRole('button', { name: 'alpha.txt', exact: true }).click()
    await expect(git.locator('.local-git-diff')).toContainText('暂存区差异 · alpha.txt')
    await expect(git.locator('.local-git-diff')).toContainText('+alpha index evidence')
    await page.screenshot({ path: path.join(root, 'git-index-diff.png') })
    await git.getByLabel('选择 alpha.txt', { exact: true }).check()
    await git.getByRole('button', { name: '取消所选暂存（1）', exact: true }).click()
    await expect(git.locator('.local-git-files > li')).toHaveCount(1)
    await expect(git.locator('.local-git-files')).toContainText('beta.txt')
    await page.screenshot({ path: path.join(root, 'git-index-unstaged.png') })
    await git.getByRole('tab', { name: '工作区', exact: true }).click()
    await expect(git.locator('.local-git-files')).toContainText('alpha.txt')
    const config = await readFile(path.join(project, '.git/config'), 'utf8')
    expect(config).not.toContain('[remote ')
    expect(config).not.toContain('[user]')
    await writeFile(
      path.join(root, 'report.json'),
      JSON.stringify(
        {
          terminal_id: terminalId,
          shell: 'powershell.exe',
          real_xterm_input: true,
          output_marker: true,
          long_line_ready_milliseconds: readyMilliseconds,
          resized: true,
          foreground_interrupted: true,
          process_stopped: true,
          git_explicit_init: true,
          staged_two_files: true,
          index_diff: true,
          unstaged_only_selected: true,
          remote: false,
          identity_configuration: false,
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
