/** 搜索与可恢复 Git 开关的真实桌面验收。 Real desktop search and recoverable Git switch acceptance. */
import { expect, test } from './runtime'
import { artifacts, choose, launch } from './helpers'
import { mkdir, mkdtemp, readFile, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'

/** 只使用隔离项目，验证 UI、RPC、移动、重启和恢复。 Isolated UI/RPC relocation, restart and restoration. */
test('M5 search options and reversible project Git switch', async () => {
  test.setTimeout(90000)
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-search-git-'))
  const project = path.join(root, 'project')
  const data = path.join(root, 'data')
  await mkdir(project)
  await writeFile(path.join(project, 'main.py'), '# context\ndef hello():\n    return 1\n', 'utf8')
  for (let index = 0; index < 200; index++) {
    await writeFile(
      path.join(project, `sample-${index}.py`),
      '# context\ndef hello():\n    return 1\n',
      'utf8'
    )
  }
  let app = await launch(data, project)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await choose(app, project)
    await page.getByRole('button', { name: '新建任务 →', exact: true }).click()
    await page.getByLabel('任务名称', { exact: true }).fill('搜索与 Git')
    await page.getByLabel('阶段目标', { exact: true }).fill('隔离目录验证搜索和仓库恢复')
    await page.getByRole('button', { name: '创建任务与首会话', exact: true }).click()
    await page.getByRole('button', { name: '打开 / 补齐首会话', exact: true }).click()
    // 等待异步会话导航完成后再切页，避免迟到导航覆盖测试的下一步。
    // Wait for session navigation before switching pages, rather than racing its response.
    await expect(page.getByLabel('输入问题')).toBeEnabled()
    await page.getByRole('button', { name: '编码工作台', exact: true }).click()
    await page.getByLabel('快速打开文件').fill('^def\\s+')
    await page.locator('.workspace-search-options > summary').click()
    await page.getByLabel('正则表达式（rg）').check()
    await page.getByLabel('包含路径', { exact: true }).fill('**/*.py')
    await page.getByLabel('前后文行数', { exact: true }).fill('1')
    await page.getByRole('button', { name: '搜索文件内容', exact: true }).click()
    const files = page.getByRole('navigation', { name: '项目文件树', exact: true })
    await expect(files).toContainText('main.py:2')
    await expect(files).toContainText('1: # context')
    await expect(files).toContainText('3:     return 1')
    // 扩大到真实出现过超时的规模，并确认普通 RPC 仍正常。
    // Exercise the previously failing scale and confirm ordinary RPC remains healthy.
    const searchStarted = Date.now()
    const searchResult = await page.evaluate(async () => {
      const projects = await window.agent.listProjects()
      if (!projects.ok || !projects.data.active_project) throw new Error('Project unavailable')
      const sessions = await window.agent.listSessions({
        project_id: projects.data.active_project.project_id,
        cursor: null,
        limit: 1
      })
      if (!sessions.ok || !sessions.data.sessions[0]) throw new Error('Session unavailable')
      const result = await window.agent.documentsSearch({
        session_id: sessions.data.sessions[0].session_id,
        query: '^def\\s+',
        regex: true,
        limit: 100
      })
      return { result, projects: await window.agent.listProjects() }
    })
    expect(searchResult.result.ok).toBe(true)
    if (searchResult.result.ok) expect(searchResult.result.data.matches).toHaveLength(100)
    expect(searchResult.projects.ok).toBe(true)
    await writeFile(
      path.join(root, 'search-report.json'),
      JSON.stringify({ seconds: (Date.now() - searchStarted) / 1000, ...searchResult }, null, 2)
    )
    const nav = page.getByRole('navigation', { name: '编码工作台', exact: true })
    await nav.getByRole('button', { name: '本地 Git', exact: true }).click()
    let git = page.locator('.local-git-panel')
    // 隔离项目位于开发仓库内，显式初始化本项目，避免操作上层仓库。
    // Explicitly initialize the fixture project, never the development parent repository.
    await git.getByRole('button', { name: /初始化.*仓库|初始化本地 Git/ }).click()
    await expect(git.getByRole('button', { name: /初始化.*仓库|初始化本地 Git/ })).toHaveCount(0)
    const head = await readFile(path.join(project, '.git/HEAD'), 'utf8')
    await git.getByRole('button', { name: '关闭 Git 并保留备份', exact: true }).click()
    await expect(git).toContainText('项目 Git · 已关闭')
    await expect(git).toContainText('可恢复备份：')
    await expect(git.getByRole('button', { name: '提交该仓库整个暂存区' })).toHaveCount(0)
    await expect
      .poll(() =>
        stat(path.join(project, '.git')).then(
          () => true,
          () => false
        )
      )
      .toBe(false)
    await page.screenshot({ path: path.join(root, 'git-disabled.png') })
    await app.close()
    app = await launch(data, project)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await page.getByRole('button', { name: '编码工作台', exact: true }).click()
    await page
      .getByRole('navigation', { name: '编码工作台', exact: true })
      .getByRole('button', { name: '本地 Git', exact: true })
      .click()
    git = page.locator('.local-git-panel')
    await expect(git).toContainText('项目 Git · 已关闭')
    await git.getByRole('button', { name: '开启 Git（有备份时恢复）', exact: true }).click()
    await expect(git).toContainText('项目 Git · 已开启')
    await expect(
      git.getByRole('button', { name: '关闭 Git 并保留备份', exact: true })
    ).toBeEnabled()
    await expect(git).not.toContainText('本项目 Git 已关闭；')
    expect(await readFile(path.join(project, '.git/HEAD'), 'utf8')).toBe(head)
    expect(await readFile(path.join(project, 'main.py'), 'utf8')).toContain('def hello():')
    await page.screenshot({ path: path.join(root, 'git-restored.png') })
  } catch (error) {
    const page = app.windows()[0]
    if (page && !page.isClosed()) {
      await page.screenshot({ path: path.join(root, 'failure.png') })
      await writeFile(path.join(root, 'failure.html'), await page.content(), 'utf8')
    }
    throw error
  } finally {
    await app.close()
  }
})
