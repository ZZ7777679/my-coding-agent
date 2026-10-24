/** 开发模式首屏接纳与重挂载验证；不联网调用模型。
 * Verify development startup acceptance across effect remounts without model requests. */
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './runtime'
import { artifacts, desktop, launch } from './helpers'

test('development startup accepts the first workspace response without waiting for a poll', async () => {
  test.setTimeout(60000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'startup-development-'))
  const { createServer } = await import('../../apps/desktop/node_modules/vite/dist/node/index.js')
  const server = await createServer({
    configFile: false,
    root: path.join(desktop, 'src/renderer'),
    cacheDir: path.join(root, 'vite-cache'),
    esbuild: { jsx: 'automatic' },
    server: { host: '127.0.0.1', port: 0, fs: { allow: [path.resolve(desktop, '../..')] } }
  })
  server.middlewares.use('/__startup_fixture', (_request, response) => {
    response.setHeader('Content-Type', 'text/html')
    response.end('<!doctype html><title>Startup fixture</title>')
  })
  await server.listen()
  const url = server.resolvedUrls?.local[0]
  if (!url) throw new Error('Missing development server URL')
  const app = await launch(path.join(root, 'data'), root, undefined, url + '__startup_fixture')
  try {
    const page = await app.firstWindow()
    await page.waitForURL(url + '__startup_fixture')
    await page.waitForLoadState('load')
    // 先在空白夹具页装记录器，再进入真实界面，覆盖完整开发 Effect 生命周期。
    // Attach the recorder on an empty fixture page before entering the real dev UI.
    await app.evaluate(({ ipcMain }) => {
      const handlers: unknown = Reflect.get(ipcMain, '_invokeHandlers')
      if (!(handlers instanceof Map)) throw new Error('Missing IPC handler map')
      const original: unknown = handlers.get('agent:info')
      if (typeof original !== 'function') throw new Error('Missing app info handler')
      const metrics = { calls: 0, firstReplyAt: 0, failNext: false }
      Reflect.set(globalThis, 'startupMetrics', metrics)
      ipcMain.removeHandler('agent:info')
      ipcMain.handle('agent:info', async (event, ...args: unknown[]) => {
        metrics.calls++
        if (metrics.failNext) {
          metrics.failNext = false
          return {
            ok: false,
            error: { code: 'BACKEND_BUSY', message: 'Startup retry sample', remediation: '' }
          }
        }
        const result: unknown = await original(event, ...args)
        if (typeof result === 'object' && result !== null && 'ok' in result && result.ok)
          metrics.firstReplyAt ||= Date.now()
        return result
      })
    })
    await page.goto(url)
    await expect
      .poll(() => app.evaluate(() => Reflect.get(globalThis, 'startupMetrics').firstReplyAt))
      .toBeGreaterThan(0)
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    const metrics = await app.evaluate(() => Reflect.get(globalThis, 'startupMetrics'))
    const result = { ...metrics, uiObservedAt: Date.now(), modelRequests: 0 }
    await writeFile(path.join(root, 'report.json'), JSON.stringify(result, null, 2))
    expect(result.uiObservedAt - metrics.firstReplyAt).toBeLessThan(3000)
    expect(metrics.calls).toBe(1)
    await expect(page.getByRole('button', { name: '选择项目文件夹', exact: false })).toBeEnabled()
    // 首次错误同样要及时显示，用户主动重新读取仍走真实后端。
    // Surface an initial failure promptly too; manual rereading still uses the real backend.
    await app.evaluate(() => {
      Reflect.get(globalThis, 'startupMetrics').failNext = true
    })
    await page.reload()
    await expect(page.getByText('Startup retry sample', { exact: true })).toBeVisible({
      timeout: 3000
    })
    await page.getByRole('button', { name: '立即重新读取', exact: true }).click()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接', {
      timeout: 3000
    })
    await page.screenshot({ path: path.join(root, 'ready.png') })
  } finally {
    await app.close()
    await server.close()
  }
})
