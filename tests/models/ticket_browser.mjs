/** 独立核验离线 HTML 的真实筛选和文本安全。 Independently verify real offline filtering and text safety. */
import { chromium } from '../../apps/desktop/node_modules/playwright/index.mjs'
import { writeFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import assert from 'node:assert/strict'

const [html, phase, reportPath] = process.argv.slice(2)
const report = { phase, checks: [], externalRequests: [] }
let browser
try {
  // 复用已确认安装的 Edge，不下载浏览器或改变用户设置。
  // Reuse the verified installed Edge without downloading a browser or changing user settings.
  browser = await chromium.launch({ headless: true, channel: 'msedge' })
  const page = await browser.newPage()
  await page.route(/^https?:/, (route) => {
    report.externalRequests.push(route.request().url())
    return route.abort()
  })
  await page.goto(pathToFileURL(html).href)
  const rows = page.locator('#tickets tbody tr:visible')
  assert.equal(await rows.count(), 3)
  const titles = await rows.locator('td:nth-child(2)').allTextContents()
  assert.equal(titles[0], '登录失败')
  assert.ok(titles[2].includes('<script>'))
  assert.equal(await page.evaluate(() => globalThis.__ticket_injected), undefined)
  assert.equal(await page.locator('img').count(), 0)
  report.checks.push('rows and input rendered as plain text')
  await page.locator('#status-filter').selectOption('closed')
  assert.equal(await rows.count(), 1)
  assert.equal(await rows.locator('td:first-child').innerText(), 'T002')
  await page.locator('#priority-filter').selectOption('high')
  assert.equal(await rows.count(), 0)
  await page.locator('#status-filter').selectOption('')
  assert.equal(await rows.count(), 1)
  assert.equal(await rows.locator('td:first-child').innerText(), 'T001')
  await page.locator('#priority-filter').selectOption('')
  assert.equal(await rows.count(), 3)
  report.checks.push('combined status and priority filters')
  if (phase === 'followup') {
    await page.locator('#search').fill('EXPORT')
    assert.equal(await rows.count(), 1)
    assert.equal(await rows.locator('td:first-child').innerText(), 'T002')
    await page.locator('#status-filter').selectOption('open')
    assert.equal(await rows.count(), 0)
    await page.locator('#search').fill('')
    assert.equal(await rows.count(), 1)
    report.checks.push('case-insensitive search combines with existing filters')
  }
  assert.deepEqual(report.externalRequests, [])
  await page.screenshot({ path: reportPath.replace(/\.json$/, '.png') })
  report.passed = true
} catch (error) {
  report.passed = false
  report.error = String(error)
  process.exitCode = 1
} finally {
  await browser?.close()
  await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n', 'utf8')
}
