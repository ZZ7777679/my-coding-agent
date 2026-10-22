/** M8 实际 Electron 体验；后端、存储和界面真实，模型使用隔离样本。
 * M8 Electron experience using real services/storage/UI with a fixture model. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

test('M8 themes, reading workspaces, partial worker result and idle reads', async () => {
  test.setTimeout(180000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'm8-experience-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  const env: Record<string, string> = { OPENCODE_API_KEY: sentinel, MY_AGENT_PROJECT_DIR: project }
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined && !(name in env)) env[name] = value
  env.MY_AGENT_TEST_RPC_METRICS = path.join(root, 'rpc-methods.jsonl')
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const started = Date.now()
  const app = await electron.launch({
    args: [path.resolve(__dirname, '../support/desktop_peer.cjs'), '--data-dir', data],
    env
  })
  const metrics: Record<string, unknown> = {}
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    metrics.startup_ms = Date.now() - started
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('阶段目标', { exact: true }).fill('M8 简单计数器 · 隔离体验')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await expect(page.getByRole('button', { name: '打开 / 补齐首会话', exact: true })).toBeVisible()
    await page.screenshot({ path: path.join(root, 'task-graphite.png') })
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    const sid = await page.locator('.tree-session.selected').getAttribute('data-session-id')
    if (!sid) throw new Error('Session missing')
    const config = await page.evaluate(() => window.agent.getConfig())
    expect(config.ok && config.data.run.max_tools).toBe(null)
    await page.getByLabel('输入问题').fill('m3: lookup')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await page.getByLabel('输入问题').fill('尚未发送的草稿：保留这里')
    await page.getByRole('button', { name: 'Trace', exact: true }).click()
    await page.getByRole('button', { name: '展开到工作区', exact: true }).click()
    await expect(page.getByLabel('轨迹时间线')).toBeVisible()
    await page.getByLabel('筛选工具').fill('read_history')
    await expect(page.locator('.trace-timeline')).toContainText('read_history')
    await page.screenshot({ path: path.join(root, 'trace-graphite.png') })
    await page.getByRole('button', { name: '关闭 Trace', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toHaveValue('尚未发送的草稿：保留这里')
    await page.getByRole('button', { name: 'Trace', exact: true }).click()
    await expect(page.getByLabel('筛选工具')).toHaveValue('read_history')
    await page.getByRole('button', { name: '关闭 Trace', exact: true }).click()
    await page.evaluate(async (sessionId) => {
      const result = await window.agent.configureWorkers({
        session_id: sessionId,
        settings: { enabled: true, concurrency: 4 }
      })
      if (!result.ok) throw new Error(result.error.message)
      for (let i = 0; i < 4; i++) {
        const saved = await window.agent.saveMemory({
          session_id: sessionId,
          memory_id: null,
          fields: {
            title: `项目约定 ${i + 1}`,
            content:
              '## 保持简单\n\n这个隔离样本使用 Python 标准库，不新增运行门槛。\n\n优先保持数据来源可追溯。',
            scope: 'project',
            category: 'preference',
            pinned: true
          }
        })
        if (!saved.ok) throw new Error(saved.error.message)
      }
    }, sid)
    await page.getByLabel('输入问题').fill('m3: failing worker')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('运行失败')
    await page.getByLabel('输入问题').fill('Worker 返回后继续编辑的草稿')
    const readingStarted = Date.now()
    await page.getByTestId('workers').locator(':scope > button').click()
    await expect(page.getByRole('dialog', { name: '子 Agent 工作空间' })).toBeVisible()
    await expect(page.locator('.reading-detail')).toContainText(
      'I will inspect the progress directory'
    )
    metrics.worker_open_ms = Date.now() - readingStarted
    await page.screenshot({ path: path.join(root, 'workers-graphite.png') })
    await page.getByRole('button', { name: '返回对话', exact: true }).click()
    await expect(page.getByLabel('输入问题')).toHaveValue('Worker 返回后继续编辑的草稿')
    await page.getByTestId('open-memory').click()
    await page.getByRole('button', { name: '展开到工作区', exact: true }).click()
    await page.getByRole('button', { name: '查找 / 刷新记忆', exact: true }).click()
    await expect(page.getByLabel('已保存记忆列表').getByRole('button')).toHaveCount(4)
    await page.getByRole('button', { name: '已过时', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('已标为来源待更新')
    await page.getByRole('button', { name: '编辑', exact: true }).click()
    await page.getByLabel('记忆正文', { exact: true }).fill('尚未保存的记忆修改')
    await page.screenshot({ path: path.join(root, 'memory-graphite.png') })
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()
    await page.getByTestId('open-memory').click()
    await expect(page.getByLabel('记忆正文', { exact: true })).toHaveValue('尚未保存的记忆修改')
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()

    const presets = ['石墨蓝', '经典浅色', '北欧灰蓝', '暖纸米色', '深灰薄荷']
    for (const name of presets) {
      await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
      await page.getByRole('button', { name, exact: true }).click()
      await page.getByRole('button', { name: '保存外观', exact: true }).click()
      await expect(page.getByText('外观已保存', { exact: true })).toBeVisible()
      await page.locator(`.tree-session[data-session-id="${sid}"]`).click()
      await expect(page.locator('.workspace')).toHaveClass(/workspace-chat/)
      await expect(page.getByLabel('输入问题')).toBeVisible()
      await page.screenshot({ path: path.join(root, `chat-${name}.png`) })
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth
      )
      expect(overflow).toBe(false)
    }
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await page.getByLabel('主色 HEX', { exact: true }).fill('#aa77cc')
    await page.getByRole('button', { name: '保存外观', exact: true }).click()
    await expect(page.getByText('外观已保存', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '收起侧栏', exact: true }).click()
    await expect(page.locator('.app')).toHaveClass(/sidebar-collapsed/)
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'mint')
    await expect(page.locator('.app')).toHaveClass(/sidebar-collapsed/)
    await page.getByRole('button', { name: '展开侧栏', exact: true }).click()
    const stored = JSON.parse(
      await readFile(path.join(data, 'electron', 'appearance.json'), 'utf8')
    )
    expect(stored.accent).toBe('#aa77cc')
    await page.locator('.tree-project').click()
    await page.locator('.tree-task').click()
    const cold = Date.now()
    await page.locator(`.tree-session[data-session-id="${sid}"]`).click()
    await expect(page.getByTestId('run-status')).toContainText('运行失败')
    metrics.cold_session_ms = Date.now() - cold
    const elapsed = await page.evaluate(async (sessionId) => {
      const values: number[] = []
      for (let i = 0; i < 3; i++) {
        const t = performance.now()
        await window.agent.getSession({ session_id: sessionId, before_seq: null })
        values.push(performance.now() - t)
      }
      return values
    }, sid)
    metrics.warm_read_ms = elapsed
    await page.getByLabel('输入问题').fill('m3: m8 long reading')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    await expect(page.locator('.chat-history')).toContainText('Local reading sample')
    const typing = Date.now()
    await page.getByLabel('输入问题').pressSequentially('Reading performance sample', { delay: 0 })
    metrics.long_answer_typing_ms = Date.now() - typing
    const idleStart = Date.now()
    await page.waitForTimeout(8000)
    const rpc = (await readFile(path.join(root, 'rpc-methods.jsonl'), 'utf8'))
      .trim()
      .split('\n')
      .map((line) => JSON.parse(line))
    metrics.idle_8s_reads = rpc.filter((row) => row.at >= idleStart).map((row) => row.method)
    await app.evaluate(({ BrowserWindow }) => {
      BrowserWindow.getAllWindows()[0].setSize(1000, 740)
      BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1.25)
    })
    await page.getByTestId('workers').locator(':scope > button').click()
    await expect
      .poll(async () =>
        page.getByRole('dialog').evaluate((node) => {
          const rect = node.getBoundingClientRect()
          return rect.right <= innerWidth && rect.bottom <= innerHeight
        })
      )
      .toBe(true)
    await page.waitForTimeout(300)
    metrics.zoom_geometry = await page.evaluate(() => ({
      width: innerWidth,
      height: innerHeight,
      dpr: devicePixelRatio,
      dialog: document.querySelector('dialog')?.getBoundingClientRect().toJSON()
    }))
    // 原生截图遵循 Electron 缩放，避免 CDP 截图视口被裁切。
    // Native capture respects Electron zoom without CDP viewport clipping.
    const nativeImage = await app.evaluate(async ({ BrowserWindow }) =>
      (await BrowserWindow.getAllWindows()[0].webContents.capturePage()).toPNG().toString('base64')
    )
    await writeFile(path.join(root, 'workers-125.png'), Buffer.from(nativeImage, 'base64'))
    await page.getByRole('button', { name: '返回对话', exact: true }).click()
    await writeFile(path.join(root, 'metrics.json'), JSON.stringify(metrics, null, 2))
    console.log('M8 evidence:', root, JSON.stringify(metrics))
  } finally {
    await app.close()
  }
})
