/** 用真实联网记录验证桌面来源，不重复模型调用。 Inspect real web results in the desktop without new model calls. */
import assert from 'node:assert/strict'
import { cp, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { requireDesktop, root, artifacts } from '../support/runtime.mjs'

const reportPath = path.resolve(process.argv[2] ?? '')
const relative = path.relative(artifacts, reportPath)
if (relative.startsWith('..') || path.isAbsolute(relative))
  throw new Error('Use a real web report under .artifacts/tests')
const report = JSON.parse(await readFile(reportPath, 'utf8'))
assert.equal(report.result, 'passed', 'The source must be a successful real web run')
await mkdir(artifacts, { recursive: true })
const directory = await mkdtemp(path.join(artifacts, 'desktop-web-live-'))
const data = path.join(directory, 'data')
await cp(path.join(path.dirname(reportPath), 'data'), data, { recursive: true })
const { _electron: electron, expect } = requireDesktop('@playwright/test')
const env = { ...process.env, OPENCODE_API_KEY: 'desktop-web-sentinel' }
delete env.ELECTRON_RUN_AS_NODE
delete env.ELECTRON_RENDERER_URL
const app = await electron.launch({
  args: [path.join(root, 'apps/desktop'), '--data-dir', data],
  env
})
try {
  const page = await app.firstWindow()
  await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
  await page.locator('.tree-project').click()
  await page.locator('.tree-task').click()
  await page.locator('.tree-session').first().click()
  const cards = page.getByTestId('web-reference-card')
  await expect(cards).toHaveCount(2)
  await expect(cards.first()).toContainText('deepseek-v4.1-flash')
  await cards.first().locator('summary').click()
  await cards.last().locator('summary').click()
  await expect(cards.first().locator('li')).toHaveCount(10)
  await expect(cards.last()).toContainText('json.dumps')
  await expect(cards.last()).toContainText('继续读取')
  await expect(page.getByTestId('run-status')).toContainText('回答结束')
  await app.evaluate(({ shell }) => {
    globalThis.webTestOpened = null
    shell.openExternal = async (url) => {
      globalThis.webTestOpened = url
    }
  })
  await cards.first().locator('button').first().click()
  await expect
    .poll(() => app.evaluate(() => globalThis.webTestOpened))
    .toBe(report.sources.find((source) => source.kind === 'web.search').sources[0].url)
  await expect(cards.first().getByRole('alert')).toHaveCount(0)
  await page.screenshot({ path: path.join(directory, 'sources.png') })
  await writeFile(
    path.join(directory, 'report.json'),
    JSON.stringify(
      {
        result: 'passed',
        source_report: reportPath,
        model_calls: 0,
        evidence:
          'Production desktop reads actual search/page history, source links use real IPC with browser opening suppressed.'
      },
      null,
      2
    )
  )
  console.log(JSON.stringify({ result: 'passed', directory }))
} finally {
  await app.close()
}
