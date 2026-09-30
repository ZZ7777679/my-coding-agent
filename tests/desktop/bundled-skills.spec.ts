/** 预装资源复制保留正文与附件。 Bundled resource copies preserve bodies and attachments. */
import { electron, expect, test } from './runtime'
import { artifacts, choose, sentinel } from './helpers'
import { mkdir, mkdtemp, readFile } from 'node:fs/promises'
import path from 'node:path'

test('bundled skills show provenance and copy editable resources without losing references', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-bundled-skills-'))
  const project = path.join(root, 'project')
  await mkdir(project)
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env))
    if (value !== undefined) env[name] = value
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = project
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
    const library = page.getByRole('region', { name: 'Skill 资源库' })
    const name = 'vercel-react-best-practices'
    const builtin = library.locator('.skill-item').filter({
      has: page.getByRole('button', { name: `${name} · builtin`, exact: true })
    })
    await expect(builtin).toContainText('vercel-labs/agent-skills')
    await builtin.getByRole('button', { name: `${name} · builtin`, exact: true }).click()
    const body = library.getByLabel('Skill 正文')
    await expect(body).not.toBeEditable()
    await library.getByRole('button', { name: '复制为可编辑版本', exact: true }).click()
    await expect(body).toBeEditable()
    const original = await body.inputValue()
    await body.fill(`${original}\nLocal desktop edit.\n`)
    await library.getByRole('button', { name: '保存 Skill', exact: true }).click()
    await expect(library.getByRole('button', { name: '保存 Skill', exact: true })).toBeEnabled()
    const user = library.locator('.skill-item').filter({
      has: page.getByRole('button', { name: `${name} · user`, exact: true })
    })
    await user.getByRole('button', { name: '导入当前项目', exact: true }).click()
    await expect(
      library.getByRole('button', { name: `${name} · project`, exact: true })
    ).toBeVisible()
    const installed = path.join(project, '.agents/skills', name)
    expect(await readFile(path.join(installed, 'SKILL.md'), 'utf8')).toContain(
      'Local desktop edit.'
    )
    expect(await readFile(path.join(installed, 'rules/async-parallel.md'), 'utf8')).toContain(
      'Promise.all'
    )
    expect(await readFile(path.join(installed, 'SOURCE.md'), 'utf8')).toContain(
      'vercel-labs/agent-skills'
    )
    expect(await readFile(path.join(installed, 'LICENSE.txt'), 'utf8')).toContain('MIT License')
    // 原始内置仍是原文，复制 / 编辑不修改随包发布的资源。
    // Editing the copy leaves the packaged original unchanged.
    await builtin.getByRole('button', { name: `${name} · builtin`, exact: true }).click()
    await expect(body).toHaveValue(original)
    await library.getByRole('button', { name: '关闭正文', exact: true }).click()
    await expect(body).toHaveCount(0)
    await page.screenshot({ path: path.join(root, 'bundled-skills.png') })
  } finally {
    await app.close()
  }
})
