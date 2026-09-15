/**
 * 仅向 renderer 暴露逐项定义的能力，且对返回数据再次运行时校验。
 * Expose only explicit renderer capabilities and validate returned data at runtime.
 */

import { contextBridge, ipcRenderer } from 'electron'
import type { DesktopAPI, Result } from '../shared/api'
import type { ProtocolV1 } from '../generated/protocol'
import { validate } from '../shared/validation'

/**
 * 校验 IPC 结果封装与方法契约，拒绝混合成功和失败字段。
 * Validate the IPC envelope and method contract, rejecting mixed success/error fields.
 */
async function invoke<K extends keyof ProtocolV1>(
  channel: string,
  contract: K,
  args: unknown[] = []
): Promise<Result<ProtocolV1[K]>> {
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
  getAppInfo: () => invoke('agent:info', 'InitializeResult'),
  chooseProject: nullableProjects,
  listProjects: () => invoke('agent:projects', 'ProjectsView'),
  openRecentProject: (projectId) => invoke('agent:open-recent', 'ProjectsView', [projectId]),
  getStorageInfo: () => invoke('agent:storage', 'StorageInfo'),
  getConfig: () => invoke('agent:config', 'PublicConfig'),
  saveConfig: (params) => invoke('agent:save-config', 'PublicConfig', [params]),
  runDiagnostics: (params) => invoke('agent:diagnostics', 'DiagnosticReport', [params]),
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
