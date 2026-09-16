/** 独立桌面传输计时，不调用模型，不属于默认回归。 Standalone offline desktop latency measurement. */
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { requireDesktop, root, artifacts } from '../support/runtime.mjs'

const { _electron: electron, expect } = requireDesktop('@playwright/test')
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
  await page.getByRole('button', { name: '只读对话', exact: true }).click()
  await page.getByRole('button', { name: '新建会话', exact: true }).click()
  const reports = []
  for (let index = 0; index < 3; index++) {
    await expect(page.getByLabel('输入问题')).toBeEnabled()
    await page.getByLabel('输入问题').fill('latency probe')
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeEnabled()
    await page.evaluate(() => {
      const now = () => performance.timeOrigin + performance.now()
      const timing = { click: null, event: null, dom: null, paint: null }
      window.__latencyProbe = timing
      const unsubscribe = window.agent.onSessionEvent((signal) => {
        if (signal.kind === 'text.delta' && timing.event === null) timing.event = now()
      })
      const observer = new MutationObserver(() => {
        if (
          document.querySelector('.chat-message.stream pre')?.textContent &&
          timing.dom === null
        ) {
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
      document.querySelector('.chat-composer button[type=submit]').addEventListener(
        'click',
        () => {
          timing.click = now()
        },
        { once: true }
      )
    })
    await page.getByRole('button', { name: '发送', exact: true }).click()
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
    reports.push({
      source: 'offline_model_real_electron_rpc_storage',
      click_to_backend_text_ms: rounded(backend.before_text_ms - timing.click),
      backend_to_renderer_event_ms: rounded(timing.event - backend.before_text_ms),
      renderer_event_to_dom_ms: rounded(timing.dom - timing.event),
      click_to_dom_ms: rounded(timing.dom - timing.click),
      click_to_animation_frame_ms: rounded(timing.paint - timing.click)
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
