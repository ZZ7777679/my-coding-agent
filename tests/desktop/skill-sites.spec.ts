/** 原站交互与宿主隔离；网站用本地样本。 Original-site interaction and host separation with a local site. */
import { electron, expect, test } from './runtime'
import { artifacts, sentinel } from './helpers'
import { mkdir, mkdtemp } from 'node:fs/promises'
import { createServer } from 'node:http'
import path from 'node:path'

test('site browsing preserves search and pagination, hands off sources and hides on leave', async () => {
  const server = createServer((request, response) => {
    const url = new URL(request.url ?? '/', 'http://localhost')
    response.setHeader('Content-Type', 'text/html; charset=utf-8')
    response.end(
      `<h1>Skill catalog ${url.searchParams.get('page') === '2' ? 'page 2' : 'page 1'}</h1><form><input name="q" aria-label="Site search"><button>Search site</button></form><p>Query: ${url.searchParams.get('q') ?? ''}</p><a href="?page=2">Next page</a><a href="https://github.com/fixture/repo/tree/main/skills/demo">View source</a>`
    )
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('No test server')
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-skill-sites-'))
  const env: Record<string, string> = {}
  for (const [key, value] of Object.entries(process.env)) if (value !== undefined) env[key] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_TEST_SKILL_CATALOG = '1'
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  const app = await electron.launch({
    args: [
      path.resolve(__dirname, '../support/desktop_peer.cjs'),
      '--data-dir',
      path.join(root, 'data')
    ],
    env
  })
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    const url = `http://127.0.0.1:${address.port}/`
    await page.getByRole('button', { name: 'Skill 管理', exact: true }).click()
    await page.getByRole('tab', { name: '逛网站', exact: true }).click()
    await expect(page.getByText('请先选择聚合网站，或输入网址后点击“访问”。')).toBeVisible()
    await expect(page.getByRole('button', { name: '刷新网页', exact: true })).toBeDisabled()
    await expect(page.getByLabel('Skill 聚合网站', { exact: true })).toHaveValue('')
    // 未选择时不创建原生网页；进入及返回管理页都不触发默认导航。
    // Entering or revisiting the empty manager must not create a native site or navigate.
    expect(
      await app.evaluate(
        ({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].contentView.children.length
      )
    ).toBe(0)
    expect(app.context().pages()).toHaveLength(1)
    await page.getByRole('tab', { name: '已安装', exact: true }).click()
    await page.getByRole('tab', { name: '逛网站', exact: true }).click()
    await expect(page.getByLabel('网站地址', { exact: true })).toHaveValue('')
    expect(
      await app.evaluate(
        ({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].contentView.children.length
      )
    ).toBe(0)
    await page.getByLabel('网站地址', { exact: true }).fill(url)
    await page.getByRole('button', { name: '访问', exact: true }).click()
    await expect
      .poll(
        () =>
          app
            .context()
            .pages()
            .filter((p) => p.url().startsWith(url)).length
      )
      .toBe(1)
    const remote = app
      .context()
      .pages()
      .find((p) => p.url().startsWith(url))!
    await remote.getByLabel('Site search').fill('review')
    await remote.getByRole('button', { name: 'Search site' }).click()
    await expect(remote.locator('p')).toHaveText('Query: review')
    await remote.getByRole('link', { name: 'Next page' }).click()
    await expect(remote.getByRole('heading')).toHaveText('Skill catalog page 2')
    await page.getByRole('button', { name: '网页后退' }).click()
    await expect(remote.locator('p')).toHaveText('Query: review')
    expect(
      await remote.evaluate(() => ({
        appBridge: typeof window.agent,
        node: typeof Reflect.get(globalThis, 'require')
      }))
    ).toEqual({ appBridge: 'undefined', node: 'undefined' })
    expect(
      await app.evaluate(
        ({ BrowserWindow }) =>
          BrowserWindow.getAllWindows()[0].contentView.children.filter((v) => v.getVisible()).length
      )
    ).toBe(1)
    await page.getByRole('button', { name: '导入本页 Skill' }).click()
    await expect(page.getByRole('tab', { name: '链接导入 / 快捷搜索' })).toHaveAttribute(
      'aria-selected',
      'true'
    )
    await expect(page.getByRole('region', { name: 'Skill 在线发现' }).locator('pre')).toContainText(
      'Read references/note.md.'
    )
    await expect
      .poll(() =>
        app.evaluate(
          ({ BrowserWindow }) =>
            BrowserWindow.getAllWindows()[0].contentView.children.filter((v) => v.getVisible())
              .length
        )
      )
      .toBe(0)
    await page.getByRole('tab', { name: '逛网站', exact: true }).click()
    await expect(remote.locator('p')).toHaveText('Query: review')
    await page.getByRole('button', { name: 'MCP 管理', exact: true }).click()
    await expect
      .poll(() =>
        app.evaluate(
          ({ BrowserWindow }) =>
            BrowserWindow.getAllWindows()[0].contentView.children.filter((v) => v.getVisible())
              .length
        )
      )
      .toBe(0)
  } finally {
    await app.close()
    await new Promise<void>((resolve) => server.close(() => resolve()))
  }
})
