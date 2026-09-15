/**
 * 桌面验收共用夹具；数据、项目与本机启动文件均可放入隔离工作区。
 * Shared desktop fixtures supporting isolated data, projects and local startup settings.
 */

import { electron, expect, type ElectronApplication } from './runtime'
import path from 'node:path'
import { cp, copyFile, mkdir, symlink, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'

export const desktop = path.resolve(__dirname, '../../apps/desktop')
export const artifacts = path.resolve(desktop, '../../.artifacts/tests')
export const sentinel = 'desktop-test-credential-never-persist'
export const python = path.join(desktop, '../../.venv/Scripts/python.exe')

/**
 * 用哨兵凭据启动真实 Electron，可复制构建资源并复用 venv 来隔离启动文件。
 * Launch real Electron with a sentinel key, optionally isolating built resources and startup files.
 */
export async function launch(
  dataDir: string,
  projectDir = path.dirname(dataDir),
  workspace?: string
): Promise<ElectronApplication> {
  const env: Record<string, string> = {}
  for (const [name, value] of Object.entries(process.env)) {
    if (value !== undefined) env[name] = value
  }
  env.OPENCODE_API_KEY = sentinel
  env.MY_AGENT_PROJECT_DIR = projectDir
  delete env.ELECTRON_RUN_AS_NODE
  delete env.ELECTRON_RENDERER_URL
  let entry = desktop
  if (workspace) {
    // 使用隔离工作区的真实构建与启动文件，不修改活动 Electron 的应用路径。
    // Use real builds and startup files in isolation instead of changing a live app's path.
    entry = path.join(workspace, 'apps/desktop')
    await mkdir(entry, { recursive: true })
    await copyFile(path.join(desktop, 'package.json'), path.join(entry, 'package.json'))
    await cp(path.join(desktop, 'out'), path.join(entry, 'out'), { recursive: true })
    const environment = path.join(workspace, '.venv')
    if (!existsSync(environment))
      await symlink(path.resolve(desktop, '../../.venv'), environment, 'junction')
  }
  return electron.launch({ args: [entry, '--data-dir', dataDir], env })
}

/**
 * 只在测试根创建本机路径文件，不改仓库真实启动设置。
 * Create a local path file under the test root without changing real repository settings.
 */
export async function workspaceFixture(
  root: string,
  dataDir: string,
  projectDir: string
): Promise<string> {
  const workspace = path.join(root, 'workspace')
  await mkdir(workspace, { recursive: true })
  await writeFile(
    path.join(workspace, 'agent.paths.local.json'),
    JSON.stringify({
      data_dir: dataDir,
      project_dir: projectDir
    }),
    'utf8'
  )
  return workspace
}

/**
 * 替换原生选择结果后点击真实按钮，保留 IPC、RPC 和存储链路。
 * Stub the native selection, then click the real button through IPC, RPC and storage.
 */
export async function choose(app: ElectronApplication, selected: string | null): Promise<void> {
  await app.evaluate(({ dialog }, folder) => {
    dialog.showOpenDialog = async (
      first: Electron.BaseWindow | Electron.OpenDialogOptions,
      second?: Electron.OpenDialogOptions
    ) => {
      const options = second ?? first
      process.env.MY_AGENT_TEST_DIALOG_START = 'defaultPath' in options ? options.defaultPath : ''
      return { canceled: folder === null, filePaths: folder ? [folder] : [] }
    }
  }, selected)
  const page = await app.firstWindow()
  await page.getByRole('button', { name: '选择项目文件夹', exact: false }).click()
  await expect(page.getByRole('button', { name: '选择项目文件夹', exact: false })).toBeEnabled()
}

/**
 * 只替换保存对话框结果，导出内容与写文件仍走真实主进程。
 * Stub only the save-dialog result; main still supplies and writes the real export.
 */
export async function exportTarget(app: ElectronApplication, target: string | null): Promise<void> {
  await app.evaluate(({ dialog }, location) => {
    dialog.showSaveDialog = async () => ({ canceled: location === null, filePath: location ?? '' })
  }, target)
}
