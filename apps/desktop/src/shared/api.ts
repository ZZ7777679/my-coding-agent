/**
 * 定义受限 preload 的类型接口；具体数据对象来自生成协议。
 * Define the restricted preload interface, using generated protocol data types.
 */

import type {
  InitializeResult,
  OperationError,
  ProjectsView,
  StorageInfo,
  PublicConfig,
  UpdateConfigParams,
  DiagnosticsParams,
  DiagnosticReport,
  StartupPaths,
  StartupPathsParams,
  ChooseDirectoryParams,
  DirectorySelection,
  ExportParams,
  ExportResult
} from '../generated/protocol'

/**
 * 用互斥成功与失败结构传递公开操作结果。
 * Represent public operation outcomes as mutually exclusive success or failure.
 */
export type Result<T> = { ok: true; data: T } | { ok: false; error: OperationError }

/**
 * renderer 唯一受信入口；不暴露文件系统、密钥或任意命令。
 * The renderer's trusted entry point, without filesystem, secret or arbitrary-command access.
 */
export interface DesktopAPI {
  /**
   * 读取应用、存储、当前配置与项目状态。
   * Read application, storage, configuration and project state.
   */
  getAppInfo(): Promise<Result<InitializeResult>>
  /**
   * 打开原生目录选择器；用户取消时返回 null。
   * Open the native directory picker, returning null on cancellation.
   */
  chooseProject(): Promise<Result<ProjectsView | null>>
  /**
   * 重新验证并读取最近项目与当前选择。
   * Revalidate and read recent projects and the active selection.
   */
  listProjects(): Promise<Result<ProjectsView>>
  /**
   * 按已有标识恢复项目，仍由后端检查目录是否可用。
   * Restore by ID while the backend rechecks directory availability.
   */
  openRecentProject(projectId: string): Promise<Result<ProjectsView>>
  /**
   * 读取当前实际数据根及其状态。
   * Read the effective data root and its status.
   */
  getStorageInfo(): Promise<Result<StorageInfo>>
  /**
   * 通过受信主进程打开实际数据文件夹。
   * Open the effective data folder through the trusted main process.
   */
  openDataDirectory(): Promise<Result<null>>
  /**
   * 刷新公开配置与凭据元信息，不读取密钥值。
   * Refresh public settings and credential metadata without exposing secret values.
   */
  getConfig(): Promise<Result<PublicConfig>>
  /**
   * 通过 Python 单写者保存默认模型。
   * Save the default model through the Python single writer.
   */
  saveConfig(params: UpdateConfigParams): Promise<Result<PublicConfig>>
  /**
   * 显式选择开发、网络与写入探测，返回脱敏报告。
   * Explicitly choose developer, network and write probes and return a sanitized report.
   */
  runDiagnostics(params: DiagnosticsParams): Promise<Result<DiagnosticReport>>
  /**
   * 读取下次启动配置与当前实际数据位置。
   * Read next-launch settings and the current effective data location.
   */
  getStartupPaths(): Promise<Result<StartupPaths>>
  /**
   * 保存下次启动目录，不自动迁移数据或登记项目。
   * Save next-launch directories without moving data or registering projects.
   */
  saveStartupPaths(params: StartupPathsParams): Promise<Result<StartupPaths>>
  /**
   * 选择启动设置使用的目录，不改变当前项目。
   * Pick a directory for startup settings without changing the active project.
   */
  chooseStartupDirectory(params: ChooseDirectoryParams): Promise<Result<DirectorySelection>>
  /**
   * 导出主进程获取的公开文档；renderer 不提供文件内容或目标路径。
   * Export main-fetched public documents; the renderer supplies neither content nor paths.
   */
  exportJson(params: ExportParams): Promise<Result<ExportResult>>
}

declare global {
  /**
   * 声明 preload 注入的受限对象，便于 renderer 获得静态类型。
   * Type the restricted object injected by preload for renderer code.
   */
  interface Window {
    agent: DesktopAPI
  }
}
