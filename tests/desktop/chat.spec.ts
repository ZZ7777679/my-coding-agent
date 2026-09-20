/** 在真实 Electron / IPC / RPC / 存储中验收，只替换模型。 Real desktop stack with an injected model. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

/** 长任务、停止、错误、纯文本渲染、预算与重启共用一个隔离场景。 One scenario for core desktop behavior. */
test('M1 chat persists evidence, survives long waits and stops without blocking controls', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-chat-'))
  const dataDir = path.join(root, 'data')
  const project = path.join(root, 'project')
  await mkdir(project)
  const source = 'def answer():\n    return 42\n'
  await writeFile(path.join(project, 'main.py'), source, 'utf8')
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
    await page.getByLabel('阶段目标', { exact: true }).fill('阅读 main.py')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toBeEnabled()
    await page.getByLabel('输入问题').fill('read and wait')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await page.getByLabel('运行详情', { exact: true }).click()
    await expect(page.getByTestId('model-progress')).toContainText('已收到思考片段')
    await expect(page.getByTestId('reasoning-content')).toContainText('先定位 main.py 的入口。')
    await expect(page.getByTestId('reasoning-content')).toContainText('再核对第 2 行的返回值。')
    await expect(page.locator('.reasoning-block')).toHaveAttribute('open', '')
    await page.locator('.reasoning-block > summary').click()
    await expect(page.getByTestId('reasoning-content')).not.toBeVisible()
    await page.getByLabel('会话模型', { exact: true }).selectOption('deepseek-v4.1-flash')
    await expect(page.getByLabel('会话模型', { exact: true })).toHaveValue('deepseek-v4.1-flash')
    await expect(page.getByTestId('chat-history')).toContainText('未提交预览')
    await expect(page.getByTestId('model-progress')).toContainText('本次请求首字')
    // 必须跨过原来的 8 秒控制等待，确认长任务不会断开后端。
    // Cross the original 8-second boundary to prove long runs keep control alive.
    await page.waitForTimeout(8500)
    const waiting = await page.getByTestId('model-progress').innerText()
    expect(waiting).toContain('最后观测：已收到正文')
    expect(Number(waiting.match(/距上次数据 ([\d.]+) 秒/)?.[1])).toBeGreaterThan(7)
    expect(waiting).not.toContain('模型正在思考')
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    expect((await page.evaluate(() => window.agent.getConfig())).ok).toBe(true)
    await page.reload()
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').first().click()
    await page.locator('.tree-session').first().click()
    await expect(page.getByTestId('chat-history')).toContainText('第 2 行返回 42')
    await expect(page.getByTestId('reasoning-content')).toContainText('再核对第 2 行的返回值。')
    await page.getByLabel('运行详情', { exact: true }).click()
    const restoredWaiting = await page.getByTestId('model-progress').innerText()
    expect(Number(restoredWaiting.match(/距上次数据 ([\d.]+) 秒/)?.[1])).toBeGreaterThan(7)
    const active = await page.evaluate(() => window.agent.getActiveRuns())
    expect(active.ok && active.data.sessions[0]?.run?.requests).toBe(2)
    await page.getByRole('button', { name: '停止运行', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('已停止')
    await page.getByLabel('输入问题').fill('finish with source')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.locator('.stream .reasoning-block')).toBeVisible()
    await page.locator('.stream .reasoning-block > summary').click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(page.locator('.reasoning-block')).not.toHaveAttribute('open', '')
    await page.locator('.reasoning-block > summary').click()
    await expect(page.getByTestId('reasoning-content')).toContainText('再核对第 2 行的返回值。')
    await expect(page.locator('.chat-message.assistant > strong').last()).toHaveText(
      'DeepSeek V4.1 Flash'
    )
    await expect(page.getByTestId('model-progress')).toContainText('本次请求首字')
    await expect(page.getByTestId('chat-history')).toContainText('main.py:2 返回 42')
    expect(await page.locator('.chat-history script').count()).toBe(0)
    await page.getByText('工具结果', { exact: false }).first().click()
    await expect(page.getByTestId('chat-history')).toContainText('read_at')
    await expect(page.getByTestId('chat-history')).not.toContainText('sha256')
    await page.getByText('工具结果', { exact: false }).first().click()
    await page.getByLabel('运行详情', { exact: true }).click()
    const layout = await page.evaluate(() => {
      const history = document.querySelector('.chat-history')!.getBoundingClientRect()
      const input = document.querySelector('.chat-composer')!.getBoundingClientRect()
      return {
        historyRatio: history.height / innerHeight,
        inputBottom: input.bottom,
        height: innerHeight,
        overflow:
          document.querySelector('.workspace')!.scrollHeight -
          document.querySelector('.workspace')!.clientHeight
      }
    })
    expect(layout.historyRatio).toBeGreaterThan(0.6)
    expect(layout.inputBottom).toBeLessThanOrEqual(layout.height)
    expect(layout.overflow).toBeLessThanOrEqual(1)
    await page.screenshot({ path: path.join(root, 'chat.png') })
    await page.getByLabel('输入问题').fill('fail now')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('MODEL_TIMEOUT')
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await page.getByText('高级运行预算与读取规则', { exact: true }).click()
    await page.getByLabel('模型请求次数', { exact: true }).fill('7')
    await page.getByRole('button', { name: '保存运行设置', exact: true }).click()
    await expect(page.getByText('已保存，对下一次运行生效。', { exact: true })).toBeVisible()
    const files = await readdir(path.join(dataDir, 'sessions'))
    const sessionId = files[0]
    const facts = await readFile(path.join(dataDir, 'sessions', sessionId, 'events.jsonl'), 'utf8')
    expect(facts).toContain('private-native-sentinel')
    expect(facts).not.toContain(sentinel)
    expect(await readFile(path.join(project, 'main.py'), 'utf8')).toBe(source)
    await app.close()
    app = await launch()
    page = await app.firstWindow()
    await expect(page.getByTestId('active-project-path')).toHaveText(project)
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').first().click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    await expect(page.getByTestId('chat-history')).toContainText('main.py:2 返回 42')
    await expect(page.getByTestId('reasoning-content')).toContainText('再核对第 2 行的返回值。')
    await expect(page.getByLabel('会话模型', { exact: true })).toHaveValue('deepseek-v4.1-flash')
    expect((await page.evaluate(() => window.agent.getActiveRuns())).ok).toBe(true)
    const config = await page.evaluate(() => window.agent.getConfig())
    expect(config.ok && config.data.run.max_requests).toBe(7)
    expect(await page.locator('body').innerText()).not.toContain('private-native-sentinel')
    expect(await readFile(path.join(dataDir, 'sessions', sessionId, 'events.jsonl'), 'utf8')).toBe(
      facts
    )
    await page.screenshot({ path: path.join(root, 'chat-restarted.png') })
  } finally {
    await app.close()
  }
})
