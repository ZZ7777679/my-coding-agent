/**
 * 仅向 renderer 暴露逐项定义的能力，且对返回数据再次运行时校验。
 * Expose only explicit renderer capabilities and validate returned data at runtime.
 */

import { contextBridge, ipcRenderer } from 'electron'
import { m5Api } from './m5'
import type { DesktopAPI, Result } from '../shared/api'
import type { ProtocolV10 } from '../generated/protocol'
import { validate } from '../shared/validation'

/**
 * 校验 IPC 结果封装与方法契约，拒绝混合成功和失败字段。
 * Validate the IPC envelope and method contract, rejecting mixed success/error fields.
 */
async function invoke<K extends keyof ProtocolV10>(
  channel: string,
  contract: K,
  args: unknown[] = []
): Promise<Result<ProtocolV10[K]>> {
  const raw: unknown = await ipcRenderer.invoke(channel, ...args)
  if (typeof raw !== 'object' || raw === null || !('ok' in raw)) throw new Error('IPC_INVALID')
  if (raw.ok === false && 'error' in raw && !('data' in raw)) {
    return { ok: false, error: validate('OperationError', raw.error) }
  }
  if (raw.ok !== true || !('data' in raw) || 'error' in raw) throw new Error('IPC_INVALID')
  return { ok: true, data: validate(contract, raw.data) }
}

/**
 * 处理项目选择的取消结果；取消保留 null，不伪造空项目列表。
 * Preserve null on picker cancellation instead of fabricating an empty project list.
 */
async function nullableProjects(): ReturnType<DesktopAPI['chooseProject']> {
  const raw: unknown = await ipcRenderer.invoke('agent:choose')
  if (typeof raw !== 'object' || raw === null || !('ok' in raw)) throw new Error('IPC_INVALID')
  if (raw.ok === false && 'error' in raw && !('data' in raw)) {
    return { ok: false, error: validate('OperationError', raw.error) }
  }
  if (raw.ok !== true || !('data' in raw) || 'error' in raw) throw new Error('IPC_INVALID')
  return { ok: true, data: raw.data === null ? null : validate('ProjectsView', raw.data) }
}

const api: DesktopAPI = {
  ...m5Api(invoke),
  getSpace: (taskId) => invoke('agent:space-get', 'SpaceResult', [{ task_id: taskId }]),
  saveSpace: (params) => invoke('agent:space-save', 'SpaceResult', [params]),
  startSpace: (params) => invoke('agent:space-start', 'SpaceResult', [params]),
  bindSpaceMember: (params) => invoke('agent:space-bind', 'SpaceResult', [params]),
  saveSpaceLayout: (params) => invoke('agent:space-layout', 'SpaceResult', [params]),
  parseWorkflow: (params) => invoke('agent:workflow-parse', 'WorkflowTemplate', [params]),
  listWorkflows: (params) => invoke('agent:workflows-list', 'WorkflowCatalog', [params]),
  saveWorkflow: (params) => invoke('agent:workflow-save', 'WorkflowCatalog', [params]),
  removeWorkflow: (params) => invoke('agent:workflow-remove', 'WorkflowCatalog', [params]),
  updateTaskWorkflow: (params) => invoke('agent:task-workflow', 'TaskView', [params]),
  listMcp: (params) => invoke('agent:mcp-list', 'McpCatalog', [params]),
  saveMcp: (params) => invoke('agent:mcp-save', 'McpCatalog', [params]),
  controlMcp: (params) => invoke('agent:mcp-control', 'McpCatalog', [params]),
  readMcpArtifact: (params) => invoke('agent:mcp-artifact', 'McpArtifact', [params]),
  listSkills: (params) => invoke('agent:skills-list', 'SkillCatalog', [params]),
  searchOnlineSkills: (params) =>
    invoke('agent:skills-online-search', 'OnlineSkillStatus', [params]),
  inspectOnlineSkill: (params) =>
    invoke('agent:skills-online-inspect', 'OnlineSkillStatus', [params]),
  onlineSkillStatus: () => invoke('agent:skills-online-status', 'OnlineSkillStatus'),
  skillSiteControl: (params) => invoke('agent:skill-site-control', 'SkillSiteState', [params]),
  skillSiteLayout: (params) => invoke('agent:skill-site-layout', 'SkillSiteState', [params]),
  skillSiteSources: () => invoke('agent:skill-site-sources', 'SkillSiteSources'),
  readOnlineSkill: (params) => invoke('agent:skills-online-read', 'OnlineSkillDocument', [params]),
  installOnlineSkill: (params) =>
    invoke('agent:skills-online-install', 'OnlineSkillStatus', [params]),
  cancelOnlineSkill: (params) =>
    invoke('agent:skills-online-cancel', 'OnlineSkillStatus', [params]),
  readSkill: (params) => invoke('agent:skill-read', 'SkillDocument', [params]),
  saveSkill: (params) => invoke('agent:skill-save', 'SkillCatalog', [params]),
  selectSkills: (params) => invoke('agent:skills-select', 'SkillCatalog', [params]),
  enableSkill: (params) => invoke('agent:skill-enable', 'SkillCatalog', [params]),

  listTrace: (params) => invoke('agent:trace-list', 'TracePage', [params]),
  getTraceDetail: (params) => invoke('agent:trace-detail', 'TraceDetail', [params]),
  createGoal: (params) => invoke('agent:goal-create', 'GoalView', [params]),
  listGoals: (params) => invoke('agent:goals-list', 'GoalPage', [params]),
  controlGoal: (params) => invoke('agent:goal-control', 'GoalView', [params]),
  listEnvironments: (params) => invoke('agent:environments', 'EnvironmentCatalog', [params]),
  inspectPython: (params) =>
    invoke('agent:environment-inspect-python', 'EnvironmentProbe', [params]),
  saveEnvironment: (params) => invoke('agent:environment-save', 'EnvironmentCatalog', [params]),
  removeEnvironment: (params) => invoke('agent:environment-remove', 'EnvironmentCatalog', [params]),
  probeEnvironment: (params) => invoke('agent:environment-probe', 'EnvironmentCatalog', [params]),
  bindEnvironment: (params) => invoke('agent:environment-bind', 'EnvironmentCatalog', [params]),
  saveExecutionSettings: (params) =>
    invoke('agent:execution-settings', 'EnvironmentCatalog', [params]),
  chooseEnvironmentPath: (params) =>
    invoke('agent:environment-path', 'DirectorySelection', [params]),
  listWorkers: (params) => invoke('agent:workers-list', 'WorkerPage', [params]),
  configureWorkers: (params) => invoke('agent:workers-configure', 'WorkerPage', [params]),
  controlWorker: (params) => invoke('agent:workers-control', 'WorkerPage', [params]),
  getContext: (params) => invoke('agent:context-get', 'ContextView', [params]),
  configureContext: (params) => invoke('agent:context-configure', 'ContextView', [params]),
  compactContext: (params) => invoke('agent:context-compact', 'ContextView', [params]),
  cancelCompaction: (params) => invoke('agent:context-cancel', 'ContextView', [params]),
  readHistory: (params) => invoke('agent:context-history', 'HistoryPage', [params]),
  listMemory: (params) => invoke('agent:memory-list', 'MemoryPage', [params]),
  saveMemory: (params) => invoke('agent:memory-save', 'MemoryPage', [params]),
  forgetMemory: (params) => invoke('agent:memory-forget', 'MemoryPage', [params]),
  configureMemory: (params) => invoke('agent:memory-configure', 'MemoryPage', [params]),
  maintainMemory: (params) => invoke('agent:memory-maintain', 'MemoryPage', [params]),
  cancelMemory: (params) => invoke('agent:memory-cancel', 'MemoryPage', [params]),
  sendPeerMessage: (params) => invoke('agent:peer-message', 'PeerMessage', [params]),
  listPeerMessages: (params) => invoke('agent:peer-messages', 'PeerMessagePage', [params]),
  relocateProject: (params) => invoke('agent:project-relocate', 'ProjectsView', [params]),
  listPrograms: (params) => invoke('agent:programs', 'ProgramPage', [params]),
  getProgram: (params) => invoke('agent:program-get', 'ProgramView', [params]),
  stopProgram: (programId) =>
    invoke('agent:program-stop', 'ProgramView', [{ program_id: programId }]),
  openProgram: (programId) =>
    invoke('agent:program-open', 'EmptyParams', [{ program_id: programId }]),
  openWebUrl: (url) => invoke('agent:web-open', 'EmptyParams', [{ url }]),
  listChanges: (params) => invoke('agent:changes-list', 'ChangePage', [params]),
  getChange: (params) => invoke('agent:change-get', 'ChangeView', [params]),
  createTask: (params) => invoke('agent:task-create', 'CreateTaskResult', [params]),
  listTasks: (params) => invoke('agent:tasks-list', 'TaskPage', [params]),
  getTask: (taskId) => invoke('agent:task-get', 'TaskView', [{ task_id: taskId }]),
  updateTask: (params) => invoke('agent:task-update', 'TaskView', [params]),
  ensureTaskSession: (taskId) =>
    invoke('agent:task-session', 'CreateTaskResult', [{ task_id: taskId }]),
  assignSession: (params) => invoke('agent:session-assign', 'SessionSummary', [params]),
  listCollaboration: (params) => invoke('agent:collaboration-list', 'CollaborationPage', [params]),
  connectSessions: (params) => invoke('agent:collaboration-connect', 'CollaborationLink', [params]),
  readPeerHistory: (params) => invoke('agent:collaboration-history', 'SessionView', [params]),
  requestCollaboration: (params) =>
    invoke('agent:collaboration-request', 'CollaborationRequest', [params]),
  controlCollaboration: (params) =>
    invoke('agent:collaboration-control', 'CollaborationRequest', [params]),
  arrangeSessionWork: (params) =>
    invoke('agent:collaboration-arrange', 'CollaborationRequest', [params]),
  createSession: (params) => invoke('agent:session-create', 'SessionSummary', [params]),
  selectSessionModel: (params) => invoke('agent:session-model', 'SessionSummary', [params]),
  listSessions: (params) => invoke('agent:sessions-list', 'SessionPage', [params]),
  getSession: (params) => invoke('agent:session-get', 'SessionView', [params]),
  attachSession: (params) => invoke('agent:session-attach', 'SessionView', [params]),
  detachSession: (sessionId) =>
    invoke('agent:session-detach', 'EmptyParams', [{ session_id: sessionId }]),
  startRun: (params) => invoke('agent:run-start', 'SessionSummary', [params]),
  cancelRun: (runId) => invoke('agent:run-cancel', 'SessionSummary', [{ run_id: runId }]),
  getActiveRuns: () => invoke('agent:run-active', 'ActiveRunResult'),
  /** 校验每条事件，并提供可注销监听。 Validate each event and return a removable listener. */
  onSessionEvent: (listener) => {
    const receive = (_event: Electron.IpcRendererEvent, raw: unknown) => {
      listener(validate('SessionSignal', raw))
    }
    ipcRenderer.on('agent:session-event', receive)
    return () => {
      ipcRenderer.removeListener('agent:session-event', receive)
    }
  },
  getAppInfo: () => invoke('agent:info', 'InitializeResult'),
  chooseProject: nullableProjects,
  listProjects: () => invoke('agent:projects', 'ProjectsView'),
  openRecentProject: (projectId) => invoke('agent:open-recent', 'ProjectsView', [projectId]),
  getStorageInfo: () => invoke('agent:storage', 'StorageInfo'),
  getConfig: () => invoke('agent:config', 'PublicConfig'),
  saveConfig: (params) => invoke('agent:save-config', 'PublicConfig', [params]),
  runDiagnostics: (params) => invoke('agent:diagnostics', 'DiagnosticReport', [params]),
  getConnections: () => invoke('agent:connections', 'ConnectionStatus'),
  saveConnections: (params) => invoke('agent:save-connections', 'PublicConfig', [params]),
  releaseConnections: () => invoke('agent:release-connections', 'ConnectionStatus'),
  testConnection: (params) => invoke('agent:test-connection', 'ConnectionStatus', [params]),
  testModelConnection: (params) =>
    invoke('agent:test-model-connection', 'ConnectionStatus', [params]),
  getStartupPaths: () => invoke('agent:startup-paths', 'StartupPaths'),
  saveStartupPaths: (params) => invoke('agent:save-startup-paths', 'StartupPaths', [params]),
  chooseStartupDirectory: (params) =>
    invoke('agent:choose-startup-directory', 'DirectorySelection', [params]),
  exportJson: (params) => invoke('agent:export-json', 'ExportResult', [params]),
  /**
   * 请求主进程打开当前数据根，并校验仅返回 null 的成功结果。
   * Ask main to open the active data root and validate the null-only success result.
   */
  openDataDirectory: async () => {
    const raw: unknown = await ipcRenderer.invoke('agent:open-data')
    if (typeof raw !== 'object' || raw === null || !('ok' in raw)) throw new Error('IPC_INVALID')
    if (raw.ok === false && 'error' in raw && !('data' in raw)) {
      return { ok: false, error: validate('OperationError', raw.error) }
    }
    if (raw.ok !== true || !('data' in raw) || raw.data !== null || 'error' in raw)
      throw new Error('IPC_INVALID')
    return { ok: true, data: null }
  }
}
contextBridge.exposeInMainWorld('agent', api)
