/** 在线资源使用真实 RPC / 文件，仅 HTTP 为样本。 Real RPC/files with a website HTTP fixture. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile } from 'node:fs/promises'
import path from 'node:path'

test('online skills can be searched, previewed, installed and imported into a project', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-online-skills-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
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
    await choose(app, project)
    await page.getByRole('button', { name: 'Skill 管理', exact: true }).click()
    await page.getByRole('tab', { name: '链接导入 / 快捷搜索' }).click()
    const online = page.getByRole('region', { name: 'Skill 在线发现' })
    await online.getByLabel('搜索 Skill', { exact: true }).fill('sample')
    await online.getByRole('button', { name: '搜索', exact: true }).click()
    await online.getByRole('button', { name: 'sample-skill', exact: true }).click()
    await expect(online.locator('pre')).toContainText('Read references/note.md.')
    await online.getByRole('button', { name: '关闭预览' }).click()
    await expect(online.locator('pre')).toHaveCount(0)
    await online.getByRole('button', { name: '显示预览' }).click()
    await online.getByRole('button', { name: '安装到资源库' }).click()
    await expect(online.getByRole('status')).toContainText('已安装到资源库')
    await page.screenshot({ path: path.join(root, 'online-installed.png') })
    await page.getByRole('tab', { name: '已安装', exact: true }).click()
    const installed = page.getByRole('region', { name: 'Skill 资源库' })
    const skill = installed
      .locator('.skill-item')
      .filter({ has: page.getByRole('button', { name: 'sample-skill · user', exact: true }) })
    await expect(skill).toContainText('fixture/repo')
    await skill.getByRole('button', { name: '导入当前项目', exact: true }).click()
    await expect(
      installed.getByRole('button', { name: 'sample-skill · project', exact: true })
    ).toBeVisible()
    expect(
      await readFile(path.join(project, '.agents/skills/sample-skill/references/note.md'), 'utf8')
    ).toContain('Keep this reference')
    await page.getByRole('tab', { name: '链接导入 / 快捷搜索' }).click()
    await online.getByLabel('搜索 Skill', { exact: true }).fill('slow')
    await online.getByRole('button', { name: '搜索', exact: true }).click()
    await online.getByRole('button', { name: '取消', exact: true }).click()
    await expect(online.getByRole('status')).toContainText('已取消')
  } finally {
    await app.close()
  }
})
