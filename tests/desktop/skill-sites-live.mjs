/** 显式联网验收原站搜索、继续加载和导入；不登录、不调用模型。
 * Check original-site search, pagination and import without login or model calls.
 */
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { artifacts, requireDesktop, root } from '../support/runtime.mjs'

if (!process.argv.includes('--enable-network'))
  throw new Error('Use --enable-network for public websites')
const { _electron: electron } = requireDesktop('playwright')
const { expect } = requireDesktop('@playwright/test')
await mkdir(artifacts, { recursive: true })
const directory = await mkdtemp(path.join(artifacts, 'skill-sites-live-'))
const project = path.join(directory, 'project')
await mkdir(project)
const env = { ...process.env }
env.MY_AGENT_PROJECT_DIR = project
delete env.ELECTRON_RUN_AS_NODE
delete env.ELECTRON_RENDERER_URL
const app = await electron.launch({
  args: [path.join(root, 'apps/desktop'), '--data-dir', path.join(directory, 'data')],
  env
})
const reports = []
const network = []
app.context().on('response', (response) => {
  const url = new URL(response.url())
  if (
    (url.hostname === 'api.skillhub.cn' && url.pathname === '/api/skills') ||
    (url.hostname.endsWith('skills.sh') && /^\/api\/(skills|search)/.test(url.pathname))
  )
    network.push({ url: response.url(), status: response.status() })
})

/** 捕获可操作控件和有限页面文字，保留失败定位依据。 Keep controls and bounded text for failure diagnosis. */
async function snapshot(remote, name) {
  const result = {
    url: remote.url(),
    title: await remote.title(),
    body: (await remote.locator('body').innerText()).slice(0, 1600),
    controls: await remote.locator('input,button,select').evaluateAll((elements) =>
      elements.map((e) => ({
        tag: e.tagName,
        text: e.textContent?.trim().slice(0, 100),
        label: e.getAttribute('aria-label'),
        placeholder: e.getAttribute('placeholder')
      }))
    )
  }
  await remote.screenshot({ path: path.join(directory, name + '.png') })
  return result
}

try {
  const page = await app.firstWindow()
  await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接', {
    timeout: 20000
  })
  await app.evaluate(({ dialog }, folder) => {
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [folder] })
  }, project)
  await page.getByRole('button', { name: '选择项目文件夹', exact: false }).click()
  await page.getByRole('button', { name: 'Skill 管理', exact: true }).click()
  await page.getByRole('tab', { name: '逛网站', exact: true }).click()
  for (const [name, url] of [
    ['tencent', 'https://skillhub.cn/skills?sortBy=score'],
    ['skills-sh', 'https://skills.sh/']
  ]) {
    const result = { name, requested_url: url, steps: [] }
    reports.push(result)
    let remote
    try {
      await page.getByLabel('网站地址', { exact: true }).fill(url)
      await page.getByRole('button', { name: '访问', exact: true }).click()
      await expect
        .poll(
          () => {
            remote = app
              .context()
              .pages()
              .find(
                (p) =>
                  p !== page && p.url().includes(name === 'tencent' ? 'skillhub.cn' : 'skills.sh')
              )
            return !!remote
          },
          { timeout: 30000 }
        )
        .toBe(true)
      if (name === 'tencent') {
        await remote.getByPlaceholder('搜索技能', { exact: true }).fill('react')
        await remote.getByPlaceholder('搜索技能', { exact: true }).press('Enter')
        const rows = remote.locator('a').filter({ hasText: 'React Native Maps' })
        await expect(rows.first()).toBeVisible({ timeout: 20000 })
        result.steps.push('原站 react 搜索返回结果')
        result.search = await snapshot(remote, name + '-search')
        await remote.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
        await expect
          .poll(
            () =>
              network.some(
                (r) =>
                  r.status === 200 &&
                  new URL(r.url).hostname === 'api.skillhub.cn' &&
                  Number(new URL(r.url).searchParams.get('page')) > 1
              ),
            { timeout: 20000 }
          )
          .toBe(true)
        result.steps.push('原站继续加载收到下一页')
        await remote.evaluate(() => window.scrollTo(0, 0))
        await rows.first().click()
        await expect(remote).toHaveURL(/\/skills\/[^/]+\/[^/]+/)
        result.detail = await snapshot(remote, name + '-detail')
        result.sources = await page.evaluate(() => window.agent.skillSiteSources())
        await page.getByRole('button', { name: '导入本页 Skill' }).click()
        await expect(page.getByRole('tab', { name: '链接导入 / 快捷搜索' })).toHaveAttribute(
          'aria-selected',
          'true'
        )
        const online = page.getByRole('region', { name: 'Skill 在线发现' })
        await expect(online.locator('pre')).toContainText('React Native Maps', {
          timeout: 90000
        })
        await online.getByRole('button', { name: '导入当前项目' }).click()
        await expect(online.getByRole('status')).toContainText('已导入项目', {
          timeout: 90000
        })
        const installed = await readFile(
          path.join(project, '.agents/skills/react-native-maps/SKILL.md'),
          'utf8'
        )
        expect(installed).toContain('React Native mapping components and utilities')
        result.steps.push('原站用户上传条目经原生下载预览并导入隔离项目')
        await page.getByRole('tab', { name: '逛网站', exact: true }).click()
      } else {
        await remote.getByText('Search skills...', { exact: true }).click()
        await remote.getByPlaceholder('Search skills...', { exact: true }).fill('react')
        const detail = remote
          .getByRole('link')
          .filter({ hasText: 'vercel-react-best-practices' })
          .first()
        await expect(detail).toBeVisible({ timeout: 20000 })
        result.steps.push('原站 react 搜索返回结果')
        result.search = await snapshot(remote, name + '-search')
        await detail.click()
        await expect(remote).toHaveURL(/\/vercel-labs\/agent-skills\/vercel-react-best-practices/)
        result.detail = await snapshot(remote, name + '-detail')
        result.sources = await page.evaluate(() => window.agent.skillSiteSources())
        await page.getByRole('button', { name: '导入本页 Skill' }).click()
        const candidates = page
          .locator('.site-sources button')
          .filter({ hasText: 'vercel-react-best-practices' })
        if (await candidates.count()) await candidates.first().click()
        await expect(page.getByRole('tab', { name: '链接导入 / 快捷搜索' })).toHaveAttribute(
          'aria-selected',
          'true'
        )
        await expect(
          page.getByRole('region', { name: 'Skill 在线发现' }).locator('pre')
        ).toContainText('vercel-react-best-practices', { timeout: 90000 })
        const online = page.getByRole('region', { name: 'Skill 在线发现' })
        await online.getByRole('button', { name: '安装到资源库' }).click()
        await expect(online.getByRole('status')).toContainText('已安装到资源库', {
          timeout: 90000
        })
        await page.getByRole('tab', { name: '已安装', exact: true }).click()
        await expect(
          page.getByRole('region', { name: 'Skill 资源库' }).getByRole('button', {
            name: 'vercel-react-best-practices · user',
            exact: true
          })
        ).toBeVisible()
        result.steps.push('详情来源进入真实下载预览并安装到隔离资源库')
        await page.getByRole('tab', { name: '逛网站', exact: true }).click()
        await page.getByRole('button', { name: '网页后退' }).click()
        await expect(remote.getByPlaceholder('Search skills...')).toHaveValue('react')
        await remote.getByPlaceholder('Search skills...').fill('')
        await expect(remote.getByText('find-skills', { exact: true })).toBeVisible()
        await remote.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
        // 原站虚拟列表会移除旧行，分页以真实下一页响应判定，不以 DOM 数量递增判定。
        // Virtualization removes old rows; observe real page responses rather than DOM growth.
        await expect
          .poll(
            () =>
              network.some(
                (r) =>
                  r.status === 200 && /\/api\/skills\/all-time\/\d+/.test(new URL(r.url).pathname)
              ),
            { timeout: 20000 }
          )
          .toBe(true)
        result.steps.push('后退恢复搜索；原站继续加载收到下一页')
      }
      result.status = 'passed'
    } catch (error) {
      result.status = 'failed'
      result.error = String(error)
      result.online = await page.evaluate(() => window.agent.onlineSkillStatus())
      result.host_body = (await page.locator('body').innerText()).slice(-7000)
      if (remote)
        result.failure = await snapshot(remote, name + '-failure').catch((e) => ({
          error: String(e)
        }))
    }
    result.toolbar = await page.evaluate(() => window.agent.skillSiteControl({ action: 'status' }))
    console.log(
      JSON.stringify({ name, status: result.status, steps: result.steps, error: result.error })
    )
    await writeFile(path.join(directory, name + '.json'), JSON.stringify(result, null, 2))
  }
} finally {
  await writeFile(
    path.join(directory, 'report.json'),
    JSON.stringify({ sites: reports, network, model_requests: 0 }, null, 2)
  )
  await app.close()
  console.log(directory)
}
if (reports.some((r) => r.status !== 'passed')) process.exitCode = 1
