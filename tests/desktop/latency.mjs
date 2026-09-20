/** 独立桌面传输计时，不调用模型，不属于默认回归。 Standalone offline desktop latency measurement. */
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
import path from 'node:path'
import { requireDesktop, root, artifacts } from '../support/runtime.mjs'

const { _electron: electron, expect } = requireDesktop('@playwright/test')
const streaming = process.argv.includes('--streaming')
await mkdir(artifacts, { recursive: true })
const directory = await mkdtemp(path.join(artifacts, 'desktop-latency-'))
const project = path.join(directory, 'project')
await mkdir(project)
const env = { ...process.env, OPENCODE_API_KEY: 'latency-sentinel', MY_AGENT_PROJECT_DIR: project }
delete env.ELECTRON_RUN_AS_NODE
delete env.ELECTRON_RENDERER_URL
const app = await electron.launch({
  args: [
    path.join(root, 'tests/support/latency_desktop_peer.cjs'),
    '--data-dir',
    path.join(directory, 'data')
  ],
  env
})
try {
  const page = await app.firstWindow()
  await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
  await app.evaluate(({ dialog }, folder) => {
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [folder] })
  }, project)
  await page.getByRole('button', { name: '选择项目文件夹', exact: false }).click()
  await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
  await page.getByLabel('阶段目标', { exact: true }).fill('latency probe')
  await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
  await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
  if (streaming) await page.getByLabel('运行详情', { exact: true }).click()
  const reports = []
  for (let index = 0; index < (streaming ? 1 : 3); index++) {
    await expect(page.getByLabel('输入问题')).toBeEnabled()
    await page.getByLabel('输入问题').fill(streaming ? 'streaming probe' : 'latency probe')
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeEnabled()
    await page.evaluate(() => {
      const now = () => performance.timeOrigin + performance.now()
      const timing = { click: null, event: null, dom: null, paint: null, updates: [] }
      window.__latencyProbe = timing
      const unsubscribe = window.agent.onSessionEvent((signal) => {
        if (signal.kind === 'text.delta' && timing.event === null) timing.event = now()
      })
      const observer = new MutationObserver(() => {
        const text = document.querySelector('.chat-message.stream pre')?.textContent
        if (text && timing.updates.at(-1)?.chars !== text.length)
          timing.updates.push({ chars: text.length, at: now() })
        if (text && timing.dom === null) {
          timing.dom = now()
          requestAnimationFrame(() => {
            timing.paint = now()
          })
        }
      })
      observer.observe(document.querySelector('.chat-history'), {
        childList: true,
        subtree: true,
        characterData: true
      })
      window.__latencyCleanup = () => {
        observer.disconnect()
        unsubscribe()
      }
      document.querySelector('[data-testid=send-message]').addEventListener(
        'click',
        () => {
          timing.click = now()
        },
        { once: true }
      )
    })
    await page.getByRole('button', { name: '发送', exact: true }).click()
    if (streaming) {
      await expect(page.getByTestId('model-progress')).toContainText('尚未收到回答正文')
      await expect(page.getByTestId('model-progress')).toContainText('思考与正文分开展示')
    }
    await page.waitForFunction(() => window.__latencyProbe.paint !== null)
    await expect(page.getByTestId('run-status')).toContainText('回答结束')
    const timing = await page.evaluate(() => {
      window.__latencyCleanup()
      return window.__latencyProbe
    })
    const backend = (await readFile(path.join(directory, 'backend.jsonl'), 'utf8'))
      .trim()
      .split('\n')
      .map(JSON.parse)[index]
    const rounded = (value) => Math.round(value * 1000) / 1000
    let streamReport = {}
    if (streaming) {
      // 只验证中途确实多次更新；实测延迟写报告，不把固定帧率当作业务门槛。
      // Require real intermediate updates; report latency without imposing a fixed frame-rate gate.
      assert.ok(timing.updates.length > 1, 'The DOM must update before the complete answer')
      assert.equal(timing.updates.at(-1).chars, backend.emissions.at(-1).chars)
      assert.ok(timing.updates[0].at < backend.emissions.at(-1).before_text_ms)
      const delivery = backend.emissions.map((emission) => {
        const update = timing.updates.find((value) => value.chars >= emission.chars)
        assert.ok(update, 'Every emitted fragment must reach the DOM')
        return {
          chars: emission.chars,
          backend_to_dom_ms: rounded(update.at - emission.before_text_ms)
        }
      })
      streamReport = {
        emitted_fragments: backend.emissions.length,
        distinct_dom_updates: timing.updates.length,
        stream_duration_ms: rounded(
          backend.emissions.at(-1).before_text_ms - backend.before_text_ms
        ),
        delivery
      }
    }
    reports.push({
      source: 'offline_model_real_electron_rpc_storage',
      click_to_backend_text_ms: rounded(backend.before_text_ms - timing.click),
      backend_to_renderer_event_ms: rounded(timing.event - backend.before_text_ms),
      renderer_event_to_dom_ms: rounded(timing.dom - timing.event),
      click_to_dom_ms: rounded(timing.dom - timing.click),
      click_to_animation_frame_ms: rounded(timing.paint - timing.click),
      ...streamReport
    })
  }
  await writeFile(
    path.join(directory, 'report.json'),
    JSON.stringify(reports, null, 2) + '\n',
    'utf8'
  )
  console.log(JSON.stringify(reports))
  console.log(path.join(directory, 'report.json'))
} finally {
  await app.close()
}
