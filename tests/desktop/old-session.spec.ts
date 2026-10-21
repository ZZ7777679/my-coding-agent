/** 真实旧历史与慢读取回包的隔离验收。 Isolated real history and delayed read-response acceptance. */
import { execFileSync } from 'node:child_process'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './runtime'
import { artifacts, launch, python } from './helpers'

test('old sessions coalesce slow refreshes and keep one composer per selection', async () => {
  test.setTimeout(60000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-old-session-'))
  const data = path.join(root, 'data')
  const project = path.join(root, 'project')
  const ids: string[] = JSON.parse(
    execFileSync(python, [path.resolve(__dirname, '../support/long_session.py'), data, project], {
      encoding: 'utf8'
    })
  )
  const before = await readFile(path.join(data, 'sessions', ids[0], 'events.jsonl'))
  const app = await launch(data, project)
  try {
    const page = await app.firstWindow()
    const errors: string[] = []
    page.on('console', (event) => {
      if (event.type() === 'error') errors.push(event.text())
    })
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: '展开项目 project', exact: true }).click()
    const old = page.locator(`[data-session-id="${ids[0]}"]`)
    const started = Date.now()
    await old.click()
    await expect(page.locator('.chat-history')).toContainText('History answer 179')
    await expect(page.getByTestId('workers')).toHaveCount(1)
    const openMs = Date.now() - started
    const signal = await page.evaluate(async (sessionId) => {
      const view = await window.agent.getSession({ session_id: sessionId, before_seq: null })
      if (!view.ok) throw new Error(view.error.message)
      return {
        session_id: sessionId,
        run_id: view.data.summary.run?.run_id ?? null,
        process_epoch: view.data.process_epoch,
        kind: 'changed',
        seq: view.data.watermark,
        message_id: null,
        delta_index: 0,
        text: ''
      }
    }, ids[0])

    // 保留真实 IPC／RPC；仅延迟只读回包，观测界面是否重复派发。
    // Keep real IPC/RPC and delay only read replies to observe duplicate dispatch.
    await app.evaluate(({ ipcMain }) => {
      const handlers: unknown = Reflect.get(ipcMain, '_invokeHandlers')
      if (!(handlers instanceof Map)) throw new Error('Missing IPC handler map')
      const stats: Record<string, { active: number; max: number; calls: number }> = {}
      for (const channel of [
        'agent:info',
        'agent:run-active',
        'agent:context-get',
        'agent:workers-list',
        'agent:goals-list',
        'agent:memory-list'
      ]) {
        const original: unknown = handlers.get(channel)
        if (typeof original !== 'function') throw new Error(`Missing ${channel}`)
        stats[channel] = { active: 0, max: 0, calls: 0 }
        ipcMain.removeHandler(channel)
        ipcMain.handle(channel, async (event, ...args: unknown[]) => {
          const stat = stats[channel]
          stat.calls++
          stat.active++
          stat.max = Math.max(stat.max, stat.active)
          try {
            const result: unknown = await original(event, ...args)
            await new Promise((resolve) => setTimeout(resolve, 3500))
            return result
          } finally {
            stat.active--
          }
        })
      }
      Reflect.set(globalThis, 'oldSessionReadStats', stats)
    })
    await app.evaluate(async ({ BrowserWindow }, event) => {
      for (let index = 0; index < 35; index++) {
        BrowserWindow.getAllWindows()[0].webContents.send('agent:session-event', event)
        await new Promise((resolve) => setTimeout(resolve, 80))
      }
    }, signal)
    await expect
      .poll(async () =>
        app.evaluate(() => {
          const value = Reflect.get(globalThis, 'oldSessionReadStats')
          return value['agent:context-get'].calls
        })
      )
      .toBeGreaterThanOrEqual(2)
    await page.waitForTimeout(4000)
    const stats = await app.evaluate(() => Reflect.get(globalThis, 'oldSessionReadStats'))
    for (const channel of [
      'agent:info',
      'agent:run-active',
      'agent:context-get',
      'agent:workers-list',
      'agent:goals-list'
    ])
      expect(stats[channel].max).toBeLessThanOrEqual(1)
    expect(stats['agent:context-get'].calls).toBe(2)
    expect(stats['agent:memory-list'].calls).toBe(0)
    await expect(page.getByText('正在处理其他请求，请稍后重试。', { exact: true })).toHaveCount(0)
    for (let index = 0; index < 2; index++) {
      await page.locator(`[data-session-id="${ids[1]}"]`).click()
      await expect(page.locator('.chat-history')).toContainText('History answer 1')
      await old.click()
      await expect(page.locator('.chat-history')).toContainText('History answer 179')
      await expect(page.getByTestId('workers')).toHaveCount(1)
    }
    expect(errors.filter((text) => /same key|unique.*key/.test(text))).toEqual([])
    // 一次历史读取失败不能永久留下“忙碌”；下一次只读刷新恢复提示。
    // A transient history error must clear after a successful read-only refresh.
    await app.evaluate(({ ipcMain }) => {
      const handlers: unknown = Reflect.get(ipcMain, '_invokeHandlers')
      if (!(handlers instanceof Map)) throw new Error('Missing IPC handler map')
      const original: unknown = handlers.get('agent:session-get')
      if (typeof original !== 'function') throw new Error('Missing session reader')
      let first = true
      ipcMain.removeHandler('agent:session-get')
      ipcMain.handle('agent:session-get', async (event, ...args: unknown[]) => {
        if (first) {
          first = false
          return {
            ok: false,
            error: {
              code: 'BACKEND_BUSY',
              message: '正在处理其他请求，请稍后重试。',
              remediation: ''
            }
          }
        }
        return original(event, ...args)
      })
    })
    await expect(page.locator('.chat-panel > [role=alert]')).toContainText('正在处理其他请求')
    await expect(page.locator('.chat-panel > [role=alert]')).toHaveCount(0)
    await page.screenshot({ path: path.join(root, 'old-session.png') })
    await writeFile(
      path.join(root, 'report.json'),
      JSON.stringify({ openMs, stats, errors }, null, 2)
    )
    expect(await readFile(path.join(data, 'sessions', ids[0], 'events.jsonl'))).toEqual(before)
  } finally {
    await app.close()
  }
})
