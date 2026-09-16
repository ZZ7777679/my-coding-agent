/**
 * 仅向 renderer 暴露逐项定义的能力，且对返回数据再次运行时校验。
 * Expose only explicit renderer capabilities and validate returned data at runtime.
 */

import { contextBridge, ipcRenderer } from 'electron'
import type { DesktopAPI, Result } from '../shared/api'
import type { ProtocolV2 } from '../generated/protocol'
import { validate } from '../shared/validation'

/**
 * 校验 IPC 结果封装与方法契约，拒绝混合成功和失败字段。
 * Validate the IPC envelope and method contract, rejecting mixed success/error fields.
 */
async function invoke<K extends keyof ProtocolV2>(
  channel: string,
  contract: K,
  args: unknown[] = []
): Promise<Result<ProtocolV2[K]>> {
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
  createSession: (params) => invoke('agent:session-create', 'SessionSummary', [params]),
  listSessions: (params) => invoke('agent:sessions-list', 'SessionPage', [params]),
  getSession: (params) => invoke('agent:session-get', 'SessionView', [params]),
  attachSession: (params) => invoke('agent:session-attach', 'SessionView', [params]),
  detachSession: (sessionId) =>
    invoke('agent:session-detach', 'EmptyParams', [{ session_id: sessionId }]),
  startRun: (params) => invoke('agent:run-start', 'SessionSummary', [params]),
  cancelRun: (runId) => invoke('agent:run-cancel', 'SessionSummary', [{ run_id: runId }]),
  getActiveRun: () => invoke('agent:run-active', 'ActiveRunResult'),
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
