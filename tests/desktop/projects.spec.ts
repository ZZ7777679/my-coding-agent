/**
 * 真实桌面项目流程验收；原生对话框与 Explorer 返回值使用受控替身。
 * Real desktop project-flow checks with controlled native-dialog and Explorer results.
 */

import { expect, test } from './runtime'
import { artifacts, sentinel, python, launch, choose } from './helpers'
import { mkdir, mkdtemp, readFile, rename, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import path from 'node:path'

/**
 * 验证项目选择、取消、重启恢复与目录失效，同时检查 renderer 权限边界。
 * Verify selection, cancellation, recovery and invalidation alongside renderer boundaries.
 */
test('project selection, cancellation, persistence, unavailable paths and data boundary', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-'))
  const dataDir = path.join(root, '应用数据')
  const project = path.join(root, '中文 项目')
  await mkdir(project)
  let app = await launch(dataDir, project)
  try {
    let page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await expect(page.getByText('还没有打开项目')).toBeVisible()
    await expect(page.getByTestId('data-dir')).toHaveText(dataDir)
    await page.screenshot({ path: path.join(root, 'empty.png') })
    expect(await page.evaluate(() => Object.keys(window.agent).sort())).toEqual([
      'chooseProject',
      'chooseStartupDirectory',
      'exportJson',
      'getAppInfo',
      'getConfig',
      'getStartupPaths',
      'getStorageInfo',
      'listProjects',
      'openDataDirectory',
      'openRecentProject',
      'runDiagnostics',
      'saveConfig',
      'saveStartupPaths'
    ])
    expect(await page.evaluate(() => 'require' in window || 'process' in window)).toBe(false)

    await choose(app, project)
    expect(await app.evaluate(() => process.env.MY_AGENT_TEST_DIALOG_START)).toBe(project)
    await expect(page.getByTestId('active-project-path')).toHaveText(project)
    const firstSave = await readFile(path.join(dataDir, 'projects.json'), 'utf8')
    expect(firstSave).not.toContain(sentinel)
    await choose(app, null)
    expect(await readFile(path.join(dataDir, 'projects.json'), 'utf8')).toBe(firstSave)
    await choose(app, dataDir)
    await expect(page.getByRole('alert')).toBeVisible()
    expect(await readFile(path.join(dataDir, 'projects.json'), 'utf8')).toBe(firstSave)
    await choose(app, project)
    await expect(page.locator('.recent-project')).toHaveCount(1)

    await app.evaluate(({ shell }) => {
      shell.openPath = async (target) => {
        process.env.MY_AGENT_TEST_OPENED_PATH = target
        return ''
      }
    })
    await page.getByRole('button', { name: '打开数据文件夹', exact: false }).click()
    await expect.poll(() => app.evaluate(() => process.env.MY_AGENT_TEST_OPENED_PATH)).toBe(dataDir)
    const paths = await app.evaluate(({ app: native }) => ({
      userData: native.getPath('userData'),
      cache: native.getPath('sessionData'),
      logs: native.getPath('logs')
    }))
    for (const selected of Object.values(paths))
      expect(path.relative(dataDir, selected)).not.toMatch(/^\.\./)
    await page.screenshot({ path: path.join(root, 'project.png') })
    await app.close()

    app = await launch(dataDir)
    page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    await expect(page.getByTestId('active-project-path')).toHaveText(project)
    await rename(project, project + '-moved')
    await expect(page.locator('.project-title .tag')).toHaveText('目录不可用')
    await expect(page.getByTestId('active-project-path')).toHaveText(project)
  } finally {
    await app.close()
  }
})

/**
 * 验证无效起始目录不会回退，目录恢复后可正常选择。
 * Verify invalid picker starts do not fall back and become usable once restored.
 */
test('an unavailable picker start directory is reported without a system-folder fallback', async () => {
  await mkdir(artifacts, { recursive: true })
  const root = await mkdtemp(path.join(artifacts, 'desktop-picker-'))
  const dataDir = path.join(root, 'data')
  const missing = path.join(root, 'missing-project')
  const app = await launch(dataDir, missing)
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('本地后端已连接')
    const before = await readFile(path.join(dataDir, 'projects.json'), 'utf8')
    await choose(app, null)
    await expect(page.getByRole('alert')).toContainText('项目选择器的起始目录不可用')
    await expect(page.getByRole('alert')).toContainText('MY_AGENT_PROJECT_DIR')
    expect(await app.evaluate(() => process.env.MY_AGENT_TEST_DIALOG_START)).toBeUndefined()
    expect(await readFile(path.join(dataDir, 'projects.json'), 'utf8')).toBe(before)
    await expect(page.getByText('还没有打开项目')).toBeVisible()
    await mkdir(missing)
    await choose(app, missing)
    await expect(page.getByTestId('active-project-path')).toHaveText(missing)
  } finally {
    await app.close()
  }
})

/**
 * 验证损坏配置在界面可见、仍可诊断且原文件保留。
 * Verify corrupted config is visible, remains diagnosable and is preserved.
 */
test('corrupt configuration is visible and preserved', async () => {
  await mkdir(artifacts, { recursive: true })
  const dataDir = await mkdtemp(path.join(artifacts, 'desktop-corrupt-'))
  const file = path.join(dataDir, 'config.toml')
  await writeFile(file, 'invalid=', 'utf8')
  const app = await launch(dataDir)
  try {
    const page = await app.firstWindow()
    await expect(page.getByTestId('connection-status')).toHaveText('后端不可用')
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByRole('button', { name: '选择项目文件夹', exact: false })).toBeDisabled()
    await page.getByRole('button', { name: '设置与诊断', exact: true }).click()
    await page.getByRole('button', { name: '运行诊断', exact: true }).click()
    await expect(page.getByTestId('diagnostic-report')).toContainText('配置')
    await expect(page.getByTestId('diagnostic-report')).toContainText('发现需要处理的问题')
    await expect(page.getByRole('button', { name: '保存默认模型', exact: true })).toBeDisabled()
    expect(await readFile(file, 'utf8')).toBe('invalid=')
  } finally {
    await app.close()
  }
})

/**
 * 用独立持锁进程验证第二实例失败，不终止原写入者。
 * Use an independent lock holder to verify a rejected second writer leaves it alive.
 */
test('a second writer is rejected without terminating the existing writer', async () => {
  await mkdir(artifacts, { recursive: true })
  const dataDir = await mkdtemp(path.join(artifacts, 'desktop-busy-'))
  const holder = spawn(
    python,
    [
      '-u',
      '-c',
      [
        'import sys',
        'from my_agent.config import resolve_data_dir',
        'from my_agent.storage import Storage',
        'with Storage(resolve_data_dir(sys.argv[1])).writer():',
        ' print("READY", flush=True)',
        ' sys.stdin.read()'
      ].join('\n'),
      dataDir
    ],
    { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true }
  )
  holder.stderr.resume()
  const closed = once(holder, 'exit')
  try {
    await once(holder.stdout, 'data', { signal: AbortSignal.timeout(5000) })
    const app = await launch(dataDir)
    try {
      const page = await app.firstWindow()
      await expect(page.getByTestId('connection-status')).toHaveText('后端不可用')
      await expect(page.getByRole('alert')).toContainText('数据目录已被另一个实例使用')
    } finally {
      await app.close()
    }
    expect(holder.exitCode).toBeNull()
  } finally {
    holder.stdin.end()
    await closed
  }
})
