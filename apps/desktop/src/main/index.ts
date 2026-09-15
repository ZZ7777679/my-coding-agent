/**
 * 装配窗口、受限 IPC 与 Python 后端；所有受信系统操作都留在主进程。
 * Wire the window, restricted IPC and Python backend; keep trusted system actions in main.
 */

import { app, BrowserWindow, dialog, ipcMain, shell, type IpcMainInvokeEvent } from 'electron'
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  realpathSync,
  statSync,
  writeFileSync
} from 'node:fs'
import path from 'node:path'
import defaults from '../../../../src/my_agent/defaults.json'
import { Backend, BackendError } from './backend'
import type { Result } from '../shared/api'
import { validate } from '../shared/validation'
import { startupPaths, saveStartupPaths, canonicalDirectory, workspaceRoot } from './startup-paths'
import { exportJson } from './json-export'
import type { DiagnosticReport } from '../generated/protocol'

let backend: Backend | undefined
let window: BrowserWindow | undefined
let quitting = false
let choosing = false
let dataDir = ''
let lastDiagnostic: DiagnosticReport | undefined
let exporting = false

/**
 * 拒绝 Windows 根相对路径，避免按当前盘符解释目录。
 * Reject Windows root-relative paths so the current drive cannot change their meaning.
 */
function isFullyAbsolute(value: string): boolean {
  return (
    path.isAbsolute(value) && (process.platform !== 'win32' || path.parse(value).root.length > 1)
  )
}

/**
 * 解析并创建实际数据根；磁盘不可用时明确失败，不回退其他位置。
 * Resolve and create the effective data root; fail on unavailable storage without fallback.
 */
function startupDirectory(): string {
  const args = process.argv
  const index = args.indexOf('--data-dir')
  const value =
    index >= 0 ? args[index + 1] : (process.env[defaults.data_dir_env] ?? defaults.data_dir)
  if (!value?.trim() || !isFullyAbsolute(value))
    throw new Error('应用数据目录必须是完整的绝对路径。')
  const resolved = path.resolve(value)
  if (!existsSync(path.parse(resolved).root)) throw new Error('应用数据所在磁盘不可用。')
  if (existsSync(resolved) && !statSync(resolved).isDirectory())
    throw new Error('应用数据路径不是文件夹。')
  mkdirSync(resolved, { recursive: true })
  return realpathSync.native(resolved)
}

/**
 * 验证项目选择器起始目录；失效时显示修复入口而不是使用系统默认目录。
 * Validate the picker start and offer repair instead of falling back to a system folder.
 */
function projectDialogDirectory(): string | undefined {
  const value =
    process.env[defaults.project_dir_env] ??
    (app.isPackaged ? undefined : defaults.development_project_dir)
  if (value === undefined) return undefined
  try {
    if (!value.trim() || !isFullyAbsolute(value) || !statSync(value).isDirectory()) {
      throw new Error('Invalid project dialog directory')
    }
    return realpathSync.native(value)
  } catch {
    throw new BackendError({
      code: 'PROJECT_PICKER_DIR_INVALID',
      message: '项目选择器的起始目录不可用。',
      remediation:
        '请创建该目录，或修改 agent.paths.local.json 的 project_dir / MY_AGENT_PROJECT_DIR 后重新打开应用。'
    })
  }
}

/**
 * 写入有界、仅包含公开错误码的日志，记录失败不得中断资源清理。
 * Write bounded public-code logs; logging failure must not interrupt cleanup.
 */
function log(code: string): void {
  try {
    const target = path.join(dataDir, 'logs/electron.log')
    if (existsSync(target) && statSync(target).size >= 1024 * 1024) {
      writeFileSync(target, 'LOG_ROTATED\n')
    }
    appendFileSync(target, new Date().toISOString() + ' ' + code + '\n')
  } catch {
    // 存储问题由界面报告，日志故障不能中断关闭清理。
    // Storage failures appear in the window; logging must not interrupt cleanup.
  }
}

/**
 * 仅接受本窗口主 frame 发出的 IPC。
 * Accept IPC only from this window's main frame.
 */
function authorized(event: IpcMainInvokeEvent): boolean {
  return (
    !!window &&
    event.sender === window.webContents &&
    event.senderFrame === window.webContents.mainFrame
  )
}

/**
 * 统一校验 IPC 来源与参数数量，包装公开成功结果或脱敏错误。
 * Check IPC source and arity, wrapping public results or sanitized failures.
 */
function handle<T>(
  channel: string,
  count: number,
  action: (...args: unknown[]) => Promise<T>
): void {
  ipcMain.handle(channel, async (event, ...args: unknown[]): Promise<Result<T>> => {
    if (!authorized(event) || args.length !== count) {
      return {
        ok: false,
        error: { code: 'IPC_REJECTED', message: '请求来源或参数无效。', remediation: '' }
      }
    }
    try {
      return { ok: true, data: await action(...args) }
    } catch (cause) {
      const detail =
        cause instanceof BackendError
          ? cause.detail
          : {
              code: 'OPERATION_FAILED',
              message: '操作未完成，请检查目录或重新打开应用。',
              remediation: ''
            }
      log(detail.code)
      return { ok: false, error: validate('OperationError', detail) }
    }
  })
}

/**
 * 等待业务初始化后返回后端；诊断恢复入口使用独立路径。
 * Return the backend after business initialization; diagnostics use a separate recovery path.
 */
async function readyBackend(): Promise<Backend> {
  if (!backend) throw new Error('Backend unavailable')
  await backend.start()
  return backend
}

try {
  dataDir = startupDirectory()
  // 在 Electron 就绪前设置所有自有路径，避免 Chromium 提前落入系统默认目录。
  // Set owned paths before Electron is ready so Chromium cannot initialize default locations.
  for (const name of ['electron', 'cache/electron', 'logs', 'logs/crashes']) {
    mkdirSync(path.join(dataDir, name), { recursive: true })
  }
  app.setPath('userData', path.join(dataDir, 'electron'))
  app.setPath('sessionData', path.join(dataDir, 'cache/electron'))
  app.setPath('crashDumps', path.join(dataDir, 'logs/crashes'))
  app.setAppLogsPath(path.join(dataDir, 'logs'))
} catch {
  dialog.showErrorBox(
    '无法打开应用数据目录',
    '请检查 E 盘或通过 --data-dir 指定可写的绝对路径。应用未切换保存位置。'
  )
  app.exit(1)
}

if (!app.requestSingleInstanceLock()) app.exit(0)

app
  .whenReady()
  .then(async () => {
    backend = new Backend(path.resolve(app.getAppPath(), '../..'), dataDir, app.getVersion(), log)
    void backend.start().catch(() => log('BACKEND_START_FAILED'))
    window = new BrowserWindow({
      width: 1220,
      height: 820,
      minWidth: 960,
      minHeight: 650,
      backgroundColor: '#111315',
      title: 'My Coding Agent',
      autoHideMenuBar: true,
      webPreferences: {
        preload: path.join(__dirname, '../preload/index.js'),
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true
      }
    })
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    window.webContents.on('will-navigate', (event) => event.preventDefault())
    window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) =>
      callback(false)
    )
    window.webContents.on('did-fail-load', () => {
      log('RENDERER_LOAD_FAILED')
      dialog.showErrorBox('界面加载失败', '请重新构建桌面资源后再打开应用。')
    })
    handle('agent:info', 0, async () => (await readyBackend()).info())
    handle('agent:projects', 0, async () =>
      (await readyBackend()).call('projects.list', {}, 'ProjectsView')
    )
    handle('agent:storage', 0, async () => (await (await readyBackend()).info()).storage)
    handle('agent:config', 0, async () =>
      (await readyBackend()).call('config.get', {}, 'PublicConfig')
    )
    handle('agent:save-config', 1, async (value) => {
      const params = validate('UpdateConfigParams', value)
      const result = await (await readyBackend()).call('config.update', params, 'PublicConfig')
      lastDiagnostic = undefined
      return result
    })
    handle('agent:diagnostics', 1, async (value) => {
      const params = validate('DiagnosticsParams', value)
      if (!backend) throw new Error('Backend unavailable')
      const report = await backend.diagnostics(params)
      lastDiagnostic = report
      return report
    })
    handle('agent:startup-paths', 0, async () => validate('StartupPaths', startupPaths(dataDir)))
    handle('agent:save-startup-paths', 1, async (value) => {
      const params = validate('StartupPathsParams', value)
      return validate('StartupPaths', saveStartupPaths(params, dataDir))
    })
    handle('agent:choose-startup-directory', 1, async (value) => {
      const params = validate('ChooseDirectoryParams', value)
      if (!window || choosing) throw new Error('Dialog busy')
      choosing = true
      try {
        const configured = startupPaths(dataDir)
        let start = params.kind === 'data' ? configured.data_dir : configured.project_dir
        // 设置页需要可修复失效路径；使用最近的存在父级，只改变选择器起点。
        // Repair invalid settings from the nearest existing parent, changing only the picker start.
        while (!existsSync(start) && path.dirname(start) !== start) start = path.dirname(start)
        if (!existsSync(start)) start = dataDir
        const selected = await dialog.showOpenDialog(window, {
          title: params.kind === 'data' ? '选择应用数据目录' : '选择项目选择器起始目录',
          defaultPath: start,
          properties: ['openDirectory']
        })
        return validate('DirectorySelection', {
          path:
            selected.canceled || !selected.filePaths[0]
              ? null
              : canonicalDirectory(selected.filePaths[0], true)
        })
      } finally {
        choosing = false
      }
    })
    handle('agent:export-json', 1, async (value) => {
      const params = validate('ExportParams', value)
      if (!window || exporting) throw new Error('Export busy')
      exporting = true
      try {
        let document: object
        if (params.kind === 'diagnostics') {
          if (!lastDiagnostic)
            throw new BackendError({
              code: 'DIAGNOSTICS_MISSING',
              message: '请先运行诊断，再导出报告。',
              remediation: ''
            })
          document = lastDiagnostic
        } else {
          const service = await readyBackend()
          document =
            params.kind === 'config'
              ? await service.call('config.get', {}, 'PublicConfig')
              : await service.call('projects.list', {}, 'ProjectsView')
        }
        return await exportJson(window, params.kind, document, dataDir, [
          path.join(dataDir, 'projects.json'),
          path.join(dataDir, 'storage.json'),
          path.join(dataDir, 'config.toml'),
          path.join(dataDir, '.runtime.lock'),
          path.join(workspaceRoot(), 'agent.paths.local.json')
        ])
      } finally {
        exporting = false
      }
    })
    handle('agent:open-recent', 1, async (projectId) => {
      const params = validate('OpenProjectParams', { project_id: projectId })
      return (await readyBackend()).call('projects.open', params, 'ProjectsView')
    })
    handle('agent:choose', 0, async () => {
      const service = await readyBackend()
      if (!window || choosing) throw new Error('Dialog busy')
      choosing = true
      try {
        const selection = await dialog.showOpenDialog(window, {
          title: '选择项目文件夹',
          defaultPath: projectDialogDirectory(),
          properties: ['openDirectory']
        })
        if (selection.canceled || !selection.filePaths[0]) return null
        const params = validate('OpenProjectParams', { path: selection.filePaths[0] })
        return await service.call('projects.open', params, 'ProjectsView')
      } finally {
        choosing = false
      }
    })
    handle('agent:open-data', 0, async () => {
      const info = await (await readyBackend()).info()
      if (realpathSync.native(info.storage.data_dir) !== dataDir)
        throw new Error('Storage mismatch')
      if (await shell.openPath(dataDir)) throw new Error('Open folder failed')
      return null
    })
    const devURL = process.env.ELECTRON_RENDERER_URL
    if (devURL) {
      const parsed = new URL(devURL)
      if (parsed.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(parsed.hostname)) {
        throw new Error('Invalid development URL')
      }
      await window.loadURL(devURL)
    } else {
      await window.loadFile(path.join(__dirname, '../renderer/index.html'))
    }
  })
  .catch(() => {
    log('APP_START_FAILED')
    dialog.showErrorBox('应用启动失败', '请检查项目依赖、Python 环境与数据目录。')
    app.quit()
  })

app.on('window-all-closed', () => app.quit())
app.on('before-quit', (event) => {
  if (quitting) return
  event.preventDefault()
  quitting = true
  void (backend?.stop() ?? Promise.resolve()).finally(() => app.exit(0))
})
