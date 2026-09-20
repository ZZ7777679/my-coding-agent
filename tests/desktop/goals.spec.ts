/** 离线模型驱动实际 Goal 桌面、文件与持久化。 Offline model with real desktop goals, files and storage. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, readdir } from 'node:fs/promises'
import path from 'node:path'

test('M2 Goal handles interruptions, HITL, budgets and explicit restart', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-goal-'))
  const dataDir = path.join(root, 'data')
  const project = path.join(root, 'empty')
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
    expect(await readdir(project)).toEqual([])
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('Goal 空项目流程')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await page.getByLabel('本次模式').selectOption('goal')
    await page.getByLabel('输入问题').fill('goal-test:page 从空目录保存页面并采用用户选择的标题')
    await page.getByText('Goal 完成条件与预算（可选）', { exact: true }).click()
    await page.getByLabel('Goal 完成条件').fill('Create index.html\nUse the selected title')
    await page.getByLabel('Goal 累计请求').fill('20')
    await page.getByRole('button', { name: '启动 Goal', exact: true }).click()
    await expect(page.getByTestId('goal-state')).toHaveText('active')
    await page.getByLabel('输入问题').fill('What is currently saved?')
    await page.getByRole('button', { name: '发送插话', exact: true }).click()
    await expect(page.getByTestId('chat-history')).toContainText('已收到插话；原始目标不变')
    await expect(page.getByTestId('goal-state')).toHaveText('waiting')
    await expect(page.getByTestId('goal-question')).toHaveText('页面标题用什么？')
    expect(await readFile(path.join(project, 'index.html'), 'utf8')).toBe('<h1>Draft</h1>')
    await page.screenshot({ path: path.join(root, 'goal-hitl.png') })
    await page.getByLabel('输入问题').fill('goal-chat:普通问答不是 HITL 答复')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('chat-history')).toContainText('普通问题已回答')
    await expect(page.getByTestId('goal-state')).toHaveText('waiting')
    await page.getByLabel('Goal 答复').fill('Notes')
    await page.getByRole('button', { name: '提交答复并接续', exact: true }).click()
    const completed = page.locator('[data-testid="goal-history"][data-status="completed"]')
    await expect(completed).toBeVisible()
    await expect(page.getByTestId('goal-panel')).toHaveCount(0)
    expect(await readFile(path.join(project, 'index.html'), 'utf8')).toBe('<h1>Notes</h1>')
    await completed.locator('summary').click()
    await expect(completed).toContainText('Create index.html · 已满足')
    await expect(completed).toContainText('Use the selected title · 已满足')
    await completed.locator('summary').click()
    await page.screenshot({ path: path.join(root, 'goal-completed.png') })

    await page.getByLabel('本次模式').selectOption('goal')
    await page.getByLabel('输入问题').fill('goal-test:hold 等待显式暂停')
    await page.getByRole('button', { name: '启动 Goal', exact: true }).click()
    await expect(page.getByTestId('goal-state')).toHaveText('active')
    const geometry = await page.evaluate(() => {
      const goal = document.querySelector('.goal-card')!.getBoundingClientRect()
      const history = document.querySelector('.chat-history')!.getBoundingClientRect()
      const input = document.querySelector('.chat-composer')!.getBoundingClientRect()
      return {
        height: goal.height,
        afterHistory: goal.top >= history.bottom,
        beforeInput: goal.bottom <= input.top
      }
    })
    expect(geometry.height).toBeLessThan(60)
    expect(geometry.afterHistory && geometry.beforeInput).toBe(true)
    await page.locator('.goal-heading').click()
    await expect(page.getByTestId('goal-request-usage')).toContainText('累计请求 1 / 20')
    await page.getByRole('button', { name: '暂停 Goal', exact: true }).click()
    await expect(page.getByTestId('goal-state')).toHaveText('paused')
    await page.getByRole('button', { name: '调整 Goal 预算', exact: true }).click()
    await page.getByLabel('Goal 累计请求').fill('4')
    await page.getByRole('button', { name: '保存预算', exact: true }).click()
    await expect
      .poll(async () => ({
        usage: await page.getByTestId('goal-request-usage').innerText(),
        errors: await page.locator('.goal-card [role="alert"]').allTextContents()
      }))
      .toEqual({ usage: '累计请求 1 / 4', errors: [] })
    await expect(page.getByTestId('goal-state')).toHaveText('paused')
    await page.getByRole('button', { name: '接续 Goal', exact: true }).click()
    await expect(page.getByTestId('goal-request-usage')).toContainText('累计请求 2 / 4')
    await app.evaluate(({ dialog }) => {
      dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
    })
    await app.close()
    app = await launch()
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').click()
    await expect(page.locator('.task-work')).toContainText('修改标题')
    await expect(page.locator('.task-work')).toContainText('页面及用户指定标题已保存')
    await page.locator('.tree-session').last().click()
    await expect(page.getByTestId('goal-state')).toHaveText('interrupted')
    await page.locator('.goal-heading').click()
    await expect(page.getByTestId('goal-request-usage')).toContainText('累计请求 2 / 4')
    expect(await readdir(project)).toEqual(['index.html'])
    await page.screenshot({ path: path.join(root, 'goal-restarted.png') })
    await page.getByRole('button', { name: '取消 Goal', exact: true }).click()
    await expect(
      page.locator('[data-testid="goal-history"][data-status="cancelled"]')
    ).toBeVisible()
    await expect(page.getByTestId('goal-panel')).toHaveCount(0)
    await page.getByLabel('输入问题').fill('recovery:create')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect
      .poll(() => readFile(path.join(project, 'recovery.txt'), 'utf8').catch(() => null))
      .toBe('saved once')
    await page.getByRole('button', { name: '停止运行', exact: true }).click()
    await page.screenshot({ path: path.join(root, 'interruption-review.png') })
    await page.getByLabel('输入问题').fill('recovery:check')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('chat-history')).toContainText('已核对中断结果')
    await expect(page.getByTestId('chat-history')).toContainText('matches_after')
    await expect(page.getByTestId('chat-history')).toContainText('未重跑旧工具')
    expect(await readFile(path.join(project, 'recovery.txt'), 'utf8')).toBe('saved once')
    const sessions = await readdir(path.join(dataDir, 'sessions'))
    expect(sessions).toHaveLength(1)
    const history = await readFile(
      path.join(dataDir, 'sessions', sessions[0], 'events.jsonl'),
      'utf8'
    )
    expect(history).not.toContain(sentinel)
    expect(history).toContain('goal.input')
    expect(history).toContain('session.recovered')
  } finally {
    await app
      .evaluate(({ dialog }) => {
        dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false })
      })
      .catch(() => {})
    await app.close()
  }
})
