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
import { registerM5Ipc } from './m5'
import type { Result } from '../shared/api'
import { validate } from '../shared/validation'
import { startupPaths, saveStartupPaths, canonicalDirectory, workspaceRoot } from './startup-paths'
import { exportJson } from './json-export'
import { SkillSites } from './skill-sites'
import type { DiagnosticReport } from '../generated/protocol'

let backend: Backend | undefined
let window: BrowserWindow | undefined
let quitting = false
let quitPending = false
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
    const skillSites = new SkillSites(window, dataDir)
    handle('agent:skill-site-control', 1, async (value) =>
      skillSites.control(validate('SkillSiteControl', value))
    )
    handle('agent:skill-site-layout', 1, async (value) =>
      skillSites.layout(validate('SkillSiteLayout', value))
    )
    handle('agent:skill-site-sources', 0, async () => skillSites.sources())
    window.on('close', (event) => {
      if (!quitting) {
        event.preventDefault()
        app.quit()
      }
    })
    backend.subscribe((signal) => {
      if (window && !window.isDestroyed()) window.webContents.send('agent:session-event', signal)
    })
    window.webContents.on('will-navigate', (event) => event.preventDefault())
    // 允许界面主动复制文字；无需读取用户已有剪贴板。
    // Allow UI text copying without granting clipboard reads.
    window.webContents.session.setPermissionRequestHandler((_contents, permission, callback) =>
      callback(permission === 'clipboard-sanitized-write')
    )
    window.webContents.on('did-fail-load', () => {
      log('RENDERER_LOAD_FAILED')
      dialog.showErrorBox('界面加载失败', '请重新构建桌面资源后再打开应用。')
    })
    handle('agent:info', 0, async () => (await readyBackend()).info())
    registerM5Ipc(handle, readyBackend)
    handle('agent:m6-project-directory', 1, async (value) => {
      const params = validate('EnvironmentProjectParams', value)
      const projects = await (await readyBackend()).call('projects.list', {}, 'ProjectsView')
      const project = projects.recent_projects.find(
        (item) => item.project_id === params.project_id
      )
      if (!project || !project.available)
        throw new BackendError({
          code: 'PROJECT_UNAVAILABLE',
          message: '项目目录不可用，请在项目工作台重新定位。',
          remediation: ''
        })
      if (await shell.openPath(project.path))
        throw new BackendError({
          code: 'FOLDER_OPEN_FAILED',
          message: '无法打开项目目录，请复制路径后手动打开。',
          remediation: ''
        })
      return validate('EmptyParams', {})
    })
    handle('agent:m5-pick-attachments', 1, async (value) => {
      const params = validate('DocumentSessionParams', value)
      const service = await readyBackend()
      const session = await service.call('sessions.get', { session_id: params.session_id }, 'SessionView')
      const projects = await service.call('projects.list', {}, 'ProjectsView')
      const project = projects.recent_projects.find(item => item.project_id === session.summary.project_id)
      if (!project) throw new BackendError({ code: 'PROJECT_UNAVAILABLE', message: '项目记录不可用，请重新打开项目。', remediation: '' })
      const selected = await dialog.showOpenDialog({ title: '选择本次输入材料', defaultPath: project?.path, properties: ['openFile', 'multiSelections'] })
      const attachments = []
      if (!selected.canceled) {
        for (const file of selected.filePaths) attachments.push(await service.call('attachments.import', { session_id: params.session_id, path: file, purpose: 'User selected input file' }, 'Attachment'))
      }
      return validate('AttachmentPage', { attachments })
    })
    handle('agent:m5-editor-open', 1, async (value) => {
      const params = validate('DocumentParams', value)
      const service = await readyBackend()
      await service.call('documents.read', params, 'DocumentView')
      const snapshot = await service.call('sessions.get', { session_id: params.session_id, before_seq: null }, 'SessionView')
      const info = await service.info()
      const project = info.projects.recent_projects.find((item) => item.project_id === snapshot.summary.project_id)
      if (!project) throw new BackendError({ code: 'PROJECT_NOT_FOUND', message: '项目登记不存在。', remediation: '' })
      const result = await shell.openPath(path.resolve(project.path, params.path))
      if (result) throw new BackendError({ code: 'EDITOR_OPEN_FAILED', message: '系统没有可用的外部编辑器关联。', remediation: '' })
      return validate('EmptyParams', {})
    })
    handle('agent:environments', 1, async (value) =>
      (await readyBackend()).call(
        'environments.list',
        validate('EnvironmentProjectParams', value),
        'EnvironmentCatalog'
      )
    )
    handle('agent:environment-inspect-python', 1, async (value) => {
      const service = await readyBackend()
      const params = validate('EnvironmentProjectParams', value)
      const catalog = await service.call('environments.list', params, 'EnvironmentCatalog')
      return service.call(
        'environments.inspect_python',
        params,
        'EnvironmentProbe',
        (catalog.settings.probe_timeout_seconds +
          2 * catalog.settings.cleanup_timeout_seconds +
          5) *
          1000
      )
    })
    handle('agent:environment-save', 1, async (value) =>
      (await readyBackend()).call(
        'environments.save',
        validate('SaveEnvironmentParams', value),
        'EnvironmentCatalog'
      )
    )
    handle('agent:environment-remove', 1, async (value) =>
      (await readyBackend()).call(
        'environments.remove',
        validate('RemoveEnvironmentParams', value),
        'EnvironmentCatalog'
      )
    )
    handle('agent:environment-bind', 1, async (value) =>
      (await readyBackend()).call(
        'environments.bind',
        validate('BindEnvironmentParams', value),
        'EnvironmentCatalog'
      )
    )
    handle('agent:execution-settings', 1, async (value) =>
      (await readyBackend()).call(
        'execution.configure',
        validate('SaveExecutionSettings', value),
        'EnvironmentCatalog'
      )
    )
    handle('agent:environment-probe', 1, async (value) => {
      const service = await readyBackend()
      const params = validate('EnvironmentParams', value)
      const catalog = await service.call(
        'environments.list',
        { project_id: params.project_id },
        'EnvironmentCatalog'
      )
      return service.call(
        'environments.probe',
        params,
        'EnvironmentCatalog',
        (2 * catalog.settings.probe_timeout_seconds +
          2 * catalog.settings.cleanup_timeout_seconds +
          5) *
          1000
      )
    })
    handle('agent:environment-path', 1, async (value) => {
      const params = validate('ChooseEnvironmentPathParams', value)
      if (!window) throw new Error('Window unavailable')
      const selection = await dialog.showOpenDialog(window, {
        title: params.kind === 'directory' ? '选择已有环境目录' : '选择已有环境的 .exe 入口',
        defaultPath: projectDialogDirectory(),
        properties: params.kind === 'directory' ? ['openDirectory'] : ['openFile'],
        ...(params.kind === 'executable'
          ? { filters: [{ name: '可执行程序', extensions: ['exe'] }] }
          : {})
      })
      return validate('DirectorySelection', {
        path: selection.canceled ? null : (selection.filePaths[0] ?? null)
      })
    })
    handle('agent:workflow-parse', 1, async (value) =>
      (await readyBackend()).call(
        'workflows.parse',
        validate('ParseWorkflowParams', value),
        'WorkflowTemplate'
      )
    )
    handle('agent:workflows-list', 1, async (value) =>
      (await readyBackend()).call(
        'workflows.list',
        validate('EmptyParams', value),
        'WorkflowCatalog'
      )
    )
    handle('agent:workflow-save', 1, async (value) =>
      (await readyBackend()).call(
        'workflows.save',
        validate('SaveWorkflowParams', value),
        'WorkflowCatalog'
      )
    )
    handle('agent:workflow-remove', 1, async (value) =>
      (await readyBackend()).call(
        'workflows.remove',
        validate('RemoveWorkflowParams', value),
        'WorkflowCatalog'
      )
    )
    handle('agent:task-workflow', 1, async (value) =>
      (await readyBackend()).call(
        'tasks.workflow',
        validate('UpdateTaskWorkflowParams', value),
        'TaskView'
      )
    )
    handle('agent:mcp-list', 1, async (value) =>
      (await readyBackend()).call('mcp.list', validate('McpParams', value), 'McpCatalog')
    )
    handle('agent:mcp-save', 1, async (value) =>
      (await readyBackend()).call('mcp.save', validate('SaveMcpParams', value), 'McpCatalog')
    )
    handle('agent:mcp-control', 1, async (value) =>
      (await readyBackend()).call('mcp.control', validate('McpControlParams', value), 'McpCatalog')
    )
    handle('agent:mcp-artifact', 1, async (value) =>
      (await readyBackend()).call(
        'mcp.artifact',
        validate('McpArtifactParams', value),
        'McpArtifact'
      )
    )
    handle('agent:skills-list', 1, async (value) =>
      (await readyBackend()).call('skills.list', validate('SkillParams', value), 'SkillCatalog')
    )
    handle('agent:skills-online-search', 1, async (value) =>
      (await readyBackend()).call(
        'skills.online.search',
        validate('OnlineSkillSearch', value),
        'OnlineSkillStatus'
      )
    )
    handle('agent:skills-online-inspect', 1, async (value) =>
      (await readyBackend()).call(
        'skills.online.inspect',
        validate('OnlineSkillInspect', value),
        'OnlineSkillStatus'
      )
    )
    handle('agent:skills-online-status', 0, async () =>
      (await readyBackend()).call('skills.online.status', {}, 'OnlineSkillStatus')
    )
    handle('agent:skills-online-read', 1, async (value) =>
      (await readyBackend()).call(
        'skills.online.read',
        validate('OnlineSkillRead', value),
        'OnlineSkillDocument'
      )
    )
    handle('agent:skills-online-install', 1, async (value) =>
      (await readyBackend()).call(
        'skills.online.install',
        validate('OnlineSkillInstall', value),
        'OnlineSkillStatus'
      )
    )
    handle('agent:skills-online-cancel', 1, async (value) =>
      (await readyBackend()).call(
        'skills.online.cancel',
        validate('OnlineSkillCancel', value),
        'OnlineSkillStatus'
      )
    )
    handle('agent:skill-read', 1, async (value) =>
      (await readyBackend()).call(
        'skills.read',
        validate('SkillReadParams', value),
        'SkillDocument'
      )
    )
    handle('agent:skill-save', 1, async (value) =>
      (await readyBackend()).call('skills.save', validate('SaveSkillParams', value), 'SkillCatalog')
    )
    handle('agent:skills-select', 1, async (value) =>
      (await readyBackend()).call(
        'skills.select',
        validate('SelectSkillsParams', value),
        'SkillCatalog'
      )
    )
    handle('agent:skill-enable', 1, async (value) =>
      (await readyBackend()).call(
        'skills.enable',
        validate('EnableSkillParams', value),
        'SkillCatalog'
      )
    )
    handle('agent:trace-list', 1, async (value) =>
      (await readyBackend()).call('trace.list', validate('TraceParams', value), 'TracePage')
    )
    handle('agent:trace-detail', 1, async (value) =>
      (await readyBackend()).call(
        'trace.detail',
        validate('TraceDetailParams', value),
        'TraceDetail'
      )
    )
    handle('agent:context-get', 1, async (value) =>
      (await readyBackend()).call('context.get', validate('ContextParams', value), 'ContextView')
    )
    handle('agent:context-configure', 1, async (value) =>
      (await readyBackend()).call(
        'context.configure',
        validate('ConfigureContextParams', value),
        'ContextView'
      )
    )
    handle('agent:context-compact', 1, async (value) =>
      (await readyBackend()).call(
        'context.compact',
        validate('ContextParams', value),
        'ContextView'
      )
    )
    handle('agent:context-cancel', 1, async (value) =>
      (await readyBackend()).call('context.cancel', validate('ContextParams', value), 'ContextView')
    )
    handle('agent:context-history', 1, async (value) =>
      (await readyBackend()).call(
        'context.history',
        validate('HistoryParams', value),
        'HistoryPage'
      )
    )
    handle('agent:memory-list', 1, async (value) =>
      (await readyBackend()).call('memory.list', validate('ListMemoryParams', value), 'MemoryPage')
    )
    handle('agent:memory-save', 1, async (value) =>
      (await readyBackend()).call('memory.save', validate('SaveMemoryParams', value), 'MemoryPage')
    )
    handle('agent:memory-forget', 1, async (value) =>
      (await readyBackend()).call(
        'memory.forget',
        validate('ForgetMemoryParams', value),
        'MemoryPage'
      )
    )
    handle('agent:memory-configure', 1, async (value) =>
      (await readyBackend()).call(
        'memory.configure',
        validate('ConfigureMemoryParams', value),
        'MemoryPage'
      )
    )
    handle('agent:memory-maintain', 1, async (value) =>
      (await readyBackend()).call(
        'memory.maintain',
        validate('MaintainMemoryParams', value),
        'MemoryPage'
      )
    )
    handle('agent:memory-cancel', 1, async (value) =>
      (await readyBackend()).call('memory.cancel', validate('MemoryParams', value), 'MemoryPage')
    )
    handle('agent:peer-message', 1, async (value) =>
      (await readyBackend()).call(
        'collaboration.message',
        validate('SendMessageParams', value),
        'PeerMessage'
      )
    )
    handle('agent:peer-messages', 1, async (value) =>
      (await readyBackend()).call(
        'collaboration.messages',
        validate('CollaborationPageParams', value),
        'PeerMessagePage'
      )
    )
    handle('agent:project-relocate', 1, async (value) =>
      (await readyBackend()).call(
        'projects.relocate',
        validate('RelocateProjectParams', value),
        'ProjectsView'
      )
    )
    handle('agent:programs', 1, async (value) =>
      (await readyBackend()).call(
        'programs.list',
        validate('ListProgramsParams', value),
        'ProgramPage'
      )
    )
    handle('agent:program-get', 1, async (value) =>
      (await readyBackend()).call(
        'programs.get',
        validate('GetProgramParams', value),
        'ProgramView'
      )
    )
    handle('agent:program-stop', 1, async (value) => {
      const service = await readyBackend()
      const settings = await service.call(
        'environments.list',
        { project_id: null },
        'EnvironmentCatalog'
      )
      return service.call(
        'programs.stop',
        validate('ProgramParams', value),
        'ProgramView',
        (settings.settings.cleanup_timeout_seconds + 5) * 1000
      )
    })
    handle('agent:web-open', 1, async (value) => {
      const params = validate('OpenWebUrlParams', value)
      const url = new URL(params.url)
      if (
        !['http:', 'https:'].includes(url.protocol) ||
        !url.hostname ||
        url.username ||
        url.password
      )
        throw new Error('Invalid web URL')
      await shell.openExternal(url.toString())
      return {}
    })
    handle('agent:program-open', 1, async (value) => {
      const view = await (
        await readyBackend()
      ).call('programs.get', validate('ProgramParams', value), 'ProgramView')
      if (view.summary.status !== 'ready' || !view.summary.url)
        throw new BackendError({
          code: 'PROGRAM_NOT_READY',
          message: '预览服务已停止或尚未就绪，请先重新启动服务。',
          remediation: ''
        })
      const url = new URL(view.summary.url)
      const local =
        url.hostname === 'localhost' ||
        url.hostname === '[::1]' ||
        /^127\.\d+\.\d+\.\d+$/.test(url.hostname)
      if (!local || !['http:', 'https:'].includes(url.protocol) || url.username || url.password)
        throw new Error('Invalid service URL')
      await shell.openExternal(url.toString())
      return {}
    })
    handle('agent:space-get', 1, async (value) =>
      (await readyBackend()).call('spaces.get', validate('SpaceParams', value), 'SpaceResult')
    )
    handle('agent:space-save', 1, async (value) =>
      (await readyBackend()).call('spaces.save', validate('SaveSpaceParams', value), 'SpaceResult')
    )
    handle('agent:space-start', 1, async (value) =>
      (await readyBackend()).call(
        'spaces.start',
        validate('SpaceStartParams', value),
        'SpaceResult'
      )
    )
    handle('agent:space-bind', 1, async (value) =>
      (await readyBackend()).call(
        'spaces.bind',
        validate('BindSpaceMemberParams', value),
        'SpaceResult'
      )
    )
    handle('agent:space-layout', 1, async (value) =>
      (await readyBackend()).call(
        'spaces.layout',
        validate('SaveSpaceLayoutParams', value),
        'SpaceResult'
      )
    )
    handle('agent:task-create', 1, async (value) =>
      (await readyBackend()).call(
        'tasks.create',
        validate('CreateTaskParams', value),
        'CreateTaskResult'
      )
    )
    handle('agent:tasks-list', 1, async (value) =>
      (await readyBackend()).call('tasks.list', validate('ListSessionsParams', value), 'TaskPage')
    )
    handle('agent:task-get', 1, async (value) =>
      (await readyBackend()).call('tasks.get', validate('TaskParams', value), 'TaskView')
    )
    handle('agent:task-update', 1, async (value) =>
      (await readyBackend()).call('tasks.update', validate('UpdateTaskParams', value), 'TaskView')
    )
    handle('agent:task-session', 1, async (value) =>
      (await readyBackend()).call(
        'tasks.ensure_session',
        validate('TaskParams', value),
        'CreateTaskResult'
      )
    )
    handle('agent:session-assign', 1, async (value) =>
      (await readyBackend()).call(
        'sessions.assign',
        validate('AssignSessionParams', value),
        'SessionSummary'
      )
    )
    handle('agent:workers-list', 1, async (value) =>
      (await readyBackend()).call(
        'workers.list',
        validate('WorkerSessionParams', value),
        'WorkerPage'
      )
    )
    handle('agent:workers-configure', 1, async (value) =>
      (await readyBackend()).call(
        'workers.configure',
        validate('ConfigureWorkersParams', value),
        'WorkerPage'
      )
    )
    handle('agent:workers-control', 1, async (value) =>
      (await readyBackend()).call(
        'workers.control',
        validate('WorkerControlParams', value),
        'WorkerPage'
      )
    )
    handle('agent:collaboration-list', 1, async (value) =>
      (await readyBackend()).call(
        'collaboration.list',
        validate('CollaborationPageParams', value),
        'CollaborationPage'
      )
    )
    handle('agent:collaboration-arrange', 1, async (value) =>
      (await readyBackend()).call(
        'collaboration.arrange',
        validate('ArrangeSessionWorkParams', value),
        'CollaborationRequest'
      )
    )
    handle('agent:collaboration-connect', 1, async (value) =>
      (await readyBackend()).call(
        'collaboration.connect',
        validate('ConnectSessionsParams', value),
        'CollaborationLink'
      )
    )
    handle('agent:collaboration-history', 1, async (value) =>
      (await readyBackend()).call(
        'collaboration.history',
        validate('CollaborationHistoryParams', value),
        'SessionView'
      )
    )
    handle('agent:collaboration-request', 1, async (value) =>
      (await readyBackend()).call(
        'collaboration.request',
        validate('CollaborationRequestParams', value),
        'CollaborationRequest'
      )
    )
    handle('agent:collaboration-control', 1, async (value) =>
      (await readyBackend()).call(
        'collaboration.control',
        validate('ControlCollaborationParams', value),
        'CollaborationRequest'
      )
    )
    handle('agent:session-create', 1, async (value) =>
      (await readyBackend()).call(
        'sessions.create',
        validate('CreateSessionParams', value),
        'SessionSummary'
      )
    )
    handle('agent:session-model', 1, async (value) =>
      (await readyBackend()).call(
        'sessions.select_model',
        validate('SelectSessionModelParams', value),
        'SessionSummary'
      )
    )
    handle('agent:sessions-list', 1, async (value) =>
      (await readyBackend()).call(
        'sessions.list',
        validate('ListSessionsParams', value),
        'SessionPage'
      )
    )
    handle('agent:session-get', 1, async (value) =>
      (await readyBackend()).call(
        'sessions.get',
        validate('GetSessionParams', value),
        'SessionView'
      )
    )
    handle('agent:session-attach', 1, async (value) =>
      (await readyBackend()).call(
        'sessions.attach',
        validate('GetSessionParams', value),
        'SessionView'
      )
    )
    handle('agent:session-detach', 1, async (value) =>
      (await readyBackend()).call(
        'sessions.detach',
        validate('SessionParams', value),
        'EmptyParams'
      )
    )
    handle('agent:run-start', 1, async (value) => {
      const params = validate('StartRunParams', value)
      const core = await readyBackend()
      // Plan 切换可能等待前一 Goal 的实际进程清理，不能沿用短控制超时。
      // A Plan switch may await actual process cleanup, rather than a short control acknowledgement.
      if (params.mode === 'plan') {
        const catalog = await core.call(
          'environments.list',
          { project_id: null },
          'EnvironmentCatalog'
        )
        return core.call(
          'runs.start',
          params,
          'SessionSummary',
          Math.max(8000, (catalog.settings.cleanup_timeout_seconds * 2 + 5) * 1000)
        )
      }
      return core.call('runs.start', params, 'SessionSummary')
    })
    handle('agent:goal-create', 1, async (value) =>
      (await readyBackend()).call('goals.create', validate('CreateGoalParams', value), 'GoalView')
    )
    handle('agent:goals-list', 1, async (value) =>
      (await readyBackend()).call('goals.list', validate('ListGoalsParams', value), 'GoalPage')
    )
    handle('agent:goal-control', 1, async (value) =>
      (await readyBackend()).call('goals.control', validate('ControlGoalParams', value), 'GoalView')
    )
    handle('agent:changes-list', 1, async (value) =>
      (await readyBackend()).call(
        'changes.list',
        validate('ListChangesParams', value),
        'ChangePage'
      )
    )
    handle('agent:change-get', 1, async (value) =>
      (await readyBackend()).call('changes.get', validate('GetChangeParams', value), 'ChangeView')
    )
    handle('agent:run-cancel', 1, async (value) =>
      (await readyBackend()).call(
        'runs.cancel',
        validate('CancelRunParams', value),
        'SessionSummary'
      )
    )
    handle('agent:run-active', 0, async () =>
      (await readyBackend()).call('runs.active', {}, 'ActiveRunResult')
    )
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
    handle('agent:connections', 0, async () =>
      (await readyBackend()).call('connections.get', {}, 'ConnectionStatus')
    )
    handle('agent:save-connections', 1, async (value) => {
      const params = validate('ConnectionSettings', value)
      const result = await (
        await readyBackend()
      ).call('connections.configure', params, 'PublicConfig')
      lastDiagnostic = undefined
      return result
    })
    handle('agent:release-connections', 0, async () =>
      (await readyBackend()).call('connections.release', {}, 'ConnectionStatus')
    )
    handle('agent:test-connection', 1, async (value) => {
      const params = validate('ConnectionProbeParams', value)
      // 传输等待覆盖用户选择的探测期限；上限来自 JS 定时器范围。
      // Cover the chosen probe deadline within JavaScript's timer range.
      const timeout = Math.min(
        2 ** 31 - 1,
        params.timeout_seconds * 1000 + defaults.http.rpc_timeout_grace_ms
      )
      return (await readyBackend()).call('connections.test', params, 'ConnectionStatus', timeout)
    })
    handle('agent:test-model-connection', 1, async (value) => {
      const params = validate('ModelConnectionProbeParams', value)
      const timeout = Math.min(
        2 ** 31 - 1,
        params.timeout_seconds * 1000 + defaults.http.rpc_timeout_grace_ms
      )
      return (await readyBackend()).call(
        'connections.test_model',
        params,
        'ConnectionStatus',
        timeout
      )
    })
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
  if (quitPending) return
  quitPending = true
  void (async () => {
    try {
      if (backend) {
        try {
          const [execution, active] = await Promise.all([
            backend.call('execution.status', {}, 'ExecutionStatus'),
            backend.call('runs.active', {}, 'ActiveRunResult')
          ])
          if (execution.programs.length || execution.probe_count || active.sessions.length) {
            const choice = await dialog.showMessageBox({
              type: 'question',
              title: '停止并退出',
              buttons: ['返回应用', '停止并退出'],
              defaultId: 0,
              cancelId: 0,
              message: `退出将停止 ${execution.programs.length} 个程序及 ${active.sessions.length} 个 Agent 运行。`,
              detail: '已保存的任务、会话和文件会保留；下次启动不会自动重跑程序。'
            })
            if (choice.response !== 1) return
          }
        } catch {
          log('SHUTDOWN_STATUS_UNAVAILABLE')
        }
      }
      quitting = true
      await backend?.stop()
      app.exit(0)
    } finally {
      quitPending = false
    }
  })()
})
