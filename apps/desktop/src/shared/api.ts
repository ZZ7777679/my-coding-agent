/**
 * 定义受限 preload 的类型接口；具体数据对象来自生成协议。
 * Define the restricted preload interface, using generated protocol data types.
 */

import type { M5DesktopAPI } from './m5-api'
import type { M7DesktopAPI } from './m7-api'
import type {
  BindSpaceMemberParams,
  SaveSpaceParams,
  SaveSpaceLayoutParams,
  SpaceResult,
  SpaceStartParams,
  ParseWorkflowParams,
  WorkflowTemplate,
  WorkflowCatalog,
  SaveWorkflowParams,
  RemoveWorkflowParams,
  UpdateTaskWorkflowParams,
  EmptyParams,
  McpParams,
  SaveMcpParams,
  McpControlParams,
  McpCatalog,
  McpArtifactParams,
  McpArtifact,
  SkillParams,
  SkillReadParams,
  SaveSkillParams,
  SelectSkillsParams,
  EnableSkillParams,
  SkillCatalog,
  SkillDocument,
  OnlineSkillCancel,
  OnlineSkillDocument,
  OnlineSkillInspect,
  OnlineSkillInstall,
  OnlineSkillRead,
  OnlineSkillSearch,
  OnlineSkillStatus,
  SkillSiteControl,
  SkillSiteLayout,
  SkillSiteState,
  SkillSiteSources,
  TraceParams,
  TraceDetailParams,
  TracePage,
  TraceDetail,
  WorkerSessionParams,
  ConfigureWorkersParams,
  WorkerControlParams,
  WorkerPage,
  SendMessageParams,
  PeerMessage,
  PeerMessagePage,
  RelocateProjectParams,
  ConfigureContextParams,
  ConfigureMemoryParams,
  ContextParams,
  ContextView,
  ForgetMemoryParams,
  HistoryPage,
  HistoryParams,
  ListMemoryParams,
  MaintainMemoryParams,
  MemoryPage,
  MemoryParams,
  SaveMemoryParams,
  ArrangeSessionWorkParams,
  CollaborationPage,
  CollaborationPageParams,
  CollaborationLink,
  ConnectSessionsParams,
  CollaborationHistoryParams,
  CollaborationRequest,
  CollaborationRequestParams,
  ControlCollaborationParams,
  InitializeResult,
  OperationError,
  ProjectsView,
  StorageInfo,
  PublicConfig,
  UpdateConfigParams,
  DiagnosticsParams,
  DiagnosticReport,
  ConnectionSettings,
  ConnectionProbeParams,
  ModelConnectionProbeParams,
  ConnectionStatus,
  StartupPaths,
  StartupPathsParams,
  ChooseDirectoryParams,
  DirectorySelection,
  ExportParams,
  ExportResult,
  CreateSessionParams,
  ListSessionsParams,
  GetSessionParams,
  StartRunParams,
  SessionSummary,
  SessionPage,
  SessionView,
  SessionSignal,
  ActiveRunResult,
  CreateTaskParams,
  CreateTaskResult,
  UpdateTaskParams,
  TaskView,
  TaskPage,
  AssignSessionParams,
  SelectSessionModelParams,
  ListChangesParams,
  GetChangeParams,
  ChangePage,
  ChangeView,
  EnvironmentCatalog,
  EnvironmentProbe,
  EnvironmentProjectParams,
  SaveEnvironmentParams,
  RemoveEnvironmentParams,
  EnvironmentParams,
  BindEnvironmentParams,
  SaveExecutionSettings,
  ListProgramsParams,
  GetProgramParams,
  ProgramPage,
  ProgramView,
  ChooseEnvironmentPathParams,
  CreateGoalParams,
  ListGoalsParams,
  ControlGoalParams,
  GoalView,
  GoalPage
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
export interface DesktopAPI extends M5DesktopAPI, M7DesktopAPI {
  /** 读取任务空间，旧任务返回未创建状态。 Read a task space, absent for legacy tasks. */
  getSpace(taskId: string): Promise<Result<SpaceResult>>
  /** 保存团队与图草稿，不开始执行。 Save a team and graph draft without execution. */
  saveSpace(params: SaveSpaceParams): Promise<Result<SpaceResult>>
  /** 显式组建草稿内的成员会话。 Explicitly assemble the draft's member sessions. */
  startSpace(params: SpaceStartParams): Promise<Result<SpaceResult>>
  /** 给稳定成员绑定已有或新会话。 Bind an existing or new session to a stable member. */
  bindSpaceMember(params: BindSpaceMemberParams): Promise<Result<SpaceResult>>
  /** 独立保存图展示状态，不保存团队编辑草稿。 Save graph presentation without committing team drafts. */
  saveSpaceLayout(params: SaveSpaceLayoutParams): Promise<Result<SpaceResult>>
  parseWorkflow: (params: ParseWorkflowParams) => Promise<Result<WorkflowTemplate>>
  listWorkflows: (params: EmptyParams) => Promise<Result<WorkflowCatalog>>
  saveWorkflow: (params: SaveWorkflowParams) => Promise<Result<WorkflowCatalog>>
  removeWorkflow: (params: RemoveWorkflowParams) => Promise<Result<WorkflowCatalog>>
  updateTaskWorkflow: (params: UpdateTaskWorkflowParams) => Promise<Result<TaskView>>
  listMcp: (params: McpParams) => Promise<Result<McpCatalog>>
  saveMcp: (params: SaveMcpParams) => Promise<Result<McpCatalog>>
  controlMcp: (params: McpControlParams) => Promise<Result<McpCatalog>>
  readMcpArtifact: (params: McpArtifactParams) => Promise<Result<McpArtifact>>
  listSkills: (params: SkillParams) => Promise<Result<SkillCatalog>>
  searchOnlineSkills: (params: OnlineSkillSearch) => Promise<Result<OnlineSkillStatus>>
  inspectOnlineSkill: (params: OnlineSkillInspect) => Promise<Result<OnlineSkillStatus>>
  onlineSkillStatus: () => Promise<Result<OnlineSkillStatus>>
  skillSiteControl: (params: SkillSiteControl) => Promise<Result<SkillSiteState>>
  skillSiteLayout: (params: SkillSiteLayout) => Promise<Result<SkillSiteState>>
  skillSiteSources: () => Promise<Result<SkillSiteSources>>
  readOnlineSkill: (params: OnlineSkillRead) => Promise<Result<OnlineSkillDocument>>
  installOnlineSkill: (params: OnlineSkillInstall) => Promise<Result<OnlineSkillStatus>>
  cancelOnlineSkill: (params: OnlineSkillCancel) => Promise<Result<OnlineSkillStatus>>
  readSkill: (params: SkillReadParams) => Promise<Result<SkillDocument>>
  saveSkill: (params: SaveSkillParams) => Promise<Result<SkillCatalog>>
  selectSkills: (params: SelectSkillsParams) => Promise<Result<SkillCatalog>>
  enableSkill: (params: EnableSkillParams) => Promise<Result<SkillCatalog>>

  listTrace: (params: TraceParams) => Promise<Result<TracePage>>
  getTraceDetail: (params: TraceDetailParams) => Promise<Result<TraceDetail>>
  /** Read internal workers. */
  listWorkers(params: WorkerSessionParams): Promise<Result<WorkerPage>>
  /** Configure optional delegation. */
  configureWorkers(params: ConfigureWorkersParams): Promise<Result<WorkerPage>>
  /** Control one internal worker. */
  controlWorker(params: WorkerControlParams): Promise<Result<WorkerPage>>
  /** 按已选身份调用本地服务。 Call the local service for selected identities. */
  sendPeerMessage(params: SendMessageParams): Promise<Result<PeerMessage>>
  /** 按已选身份调用本地服务。 Call the local service for selected identities. */
  listPeerMessages(params: CollaborationPageParams): Promise<Result<PeerMessagePage>>
  /** 按已选身份调用本地服务。 Call the local service for selected identities. */
  relocateProject(params: RelocateProjectParams): Promise<Result<ProjectsView>>

  /** context.get: 读取或更新本地知识状态。 Read or update local knowledge state. */
  getContext(params: ContextParams): Promise<Result<ContextView>>
  /** context.configure: 读取或更新本地知识状态。 Read or update local knowledge state. */
  configureContext(params: ConfigureContextParams): Promise<Result<ContextView>>
  /** context.compact: 读取或更新本地知识状态。 Read or update local knowledge state. */
  compactContext(params: ContextParams): Promise<Result<ContextView>>
  /** context.cancel: 读取或更新本地知识状态。 Read or update local knowledge state. */
  cancelCompaction(params: ContextParams): Promise<Result<ContextView>>
  /** context.history: 读取或更新本地知识状态。 Read or update local knowledge state. */
  readHistory(params: HistoryParams): Promise<Result<HistoryPage>>
  /** memory.list: 读取或更新本地知识状态。 Read or update local knowledge state. */
  listMemory(params: ListMemoryParams): Promise<Result<MemoryPage>>
  /** memory.save: 读取或更新本地知识状态。 Read or update local knowledge state. */
  saveMemory(params: SaveMemoryParams): Promise<Result<MemoryPage>>
  /** memory.forget: 读取或更新本地知识状态。 Read or update local knowledge state. */
  forgetMemory(params: ForgetMemoryParams): Promise<Result<MemoryPage>>
  /** memory.configure: 读取或更新本地知识状态。 Read or update local knowledge state. */
  configureMemory(params: ConfigureMemoryParams): Promise<Result<MemoryPage>>
  /** memory.maintain: 读取或更新本地知识状态。 Read or update local knowledge state. */
  maintainMemory(params: MaintainMemoryParams): Promise<Result<MemoryPage>>
  /** memory.cancel: 读取或更新本地知识状态。 Read or update local knowledge state. */
  cancelMemory(params: MemoryParams): Promise<Result<MemoryPage>>

  /** 读取双方协作状态。 Read collaboration status for both parties. */
  listCollaboration(params: CollaborationPageParams): Promise<Result<CollaborationPage>>
  /** 保存用户协作约定。 Save a user-defined agreement. */
  connectSessions(params: ConnectSessionsParams): Promise<Result<CollaborationLink>>
  /** 按约定读取公开历史，不唤醒模型。 Read permitted history without waking a model. */
  readPeerHistory(params: CollaborationHistoryParams): Promise<Result<SessionView>>
  /** 向已有会话投递明确请求。 Deliver scoped work to an existing session. */
  requestCollaboration(params: CollaborationRequestParams): Promise<Result<CollaborationRequest>>
  /** 停止或明确接续尚未开始的请求。 Stop or release an unstarted request. */
  controlCollaboration(params: ControlCollaborationParams): Promise<Result<CollaborationRequest>>
  /** 用户主动交接或独立审查已有会话成果。 Arrange a user-initiated handoff or independent review. */
  arrangeSessionWork(params: ArrangeSessionWorkParams): Promise<Result<CollaborationRequest>>
  /** 在当前会话启动用户 Goal。 Start a user goal in the current session. */
  createGoal(params: CreateGoalParams): Promise<Result<GoalView>>
  /** 读取真实目标状态及累计用量。 Read goal state and cumulative usage. */
  listGoals(params: ListGoalsParams): Promise<Result<GoalPage>>
  /** 明确暂停、接续、取消、答复或改预算。 Explicitly control, answer or budget a goal. */
  controlGoal(params: ControlGoalParams): Promise<Result<GoalView>>
  /** 查看登记和项目默认。 Read registrations and project defaults. */
  listEnvironments(params: EnvironmentProjectParams): Promise<Result<EnvironmentCatalog>>
  /** 按需检查当前项目实际 Python。 Inspect the effective Python on demand. */
  inspectPython(params: EnvironmentProjectParams): Promise<Result<EnvironmentProbe>>
  /** 导入已有环境引用。 Register an existing environment reference. */
  saveEnvironment(params: SaveEnvironmentParams): Promise<Result<EnvironmentCatalog>>
  /** 移除登记，不删除环境。 Remove a reference without deleting the environment. */
  removeEnvironment(params: RemoveEnvironmentParams): Promise<Result<EnvironmentCatalog>>
  /** 显式检查登记入口。 Explicitly probe registered tools. */
  probeEnvironment(params: EnvironmentParams): Promise<Result<EnvironmentCatalog>>
  /** 保存项目默认与信任。 Save project environment and trust. */
  bindEnvironment(params: BindEnvironmentParams): Promise<Result<EnvironmentCatalog>>
  /** 保存后续执行预算。 Save budgets for future launches. */
  saveExecutionSettings(params: SaveExecutionSettings): Promise<Result<EnvironmentCatalog>>
  /** 原生选择已存在路径。 Select an existing path natively. */
  chooseEnvironmentPath(params: ChooseEnvironmentPathParams): Promise<Result<DirectorySelection>>
  /** 项目 / 会话程序卡片。 Query project/session program cards. */
  listPrograms(params: ListProgramsParams): Promise<Result<ProgramPage>>
  /** 实际状态与有界输出。 Read real state and bounded output. */
  getProgram(params: GetProgramParams): Promise<Result<ProgramView>>
  /** 停止自有程序。 Stop an owned process. */
  stopProgram(programId: string): Promise<Result<ProgramView>>
  /** 用户点击后打开已确认服务地址。 Open a confirmed service on user click. */
  openProgram(programId: string): Promise<Result<object>>
  /** 用户点击后打开 HTTP(S) 资料，不自动打开模型链接。 Open web references only on user clicks. */
  openWebUrl(url: string): Promise<Result<object>>
  /** 按会话分页修改成果。 Page saved changes within a session. */
  listChanges(params: ListChangesParams): Promise<Result<ChangePage>>
  /** 读取保存的基线差异，不直接读取项目文件。 Read a saved baseline diff, not live project files. */
  getChange(params: GetChangeParams): Promise<Result<ChangeView>>
  /** 保存任务并创建首会话，不调用模型。 Save a task and its first session without model calls. */
  createTask(params: CreateTaskParams): Promise<Result<CreateTaskResult>>
  /** 读取任务分页。 Read a project task page. */
  listTasks(params: ListSessionsParams): Promise<Result<TaskPage>>
  /** 读取最新共享信息。 Read current shared task facts. */
  getTask(taskId: string): Promise<Result<TaskView>>
  /** 以版本校验保存用户结论。 Save user facts with revision checks. */
  updateTask(params: UpdateTaskParams): Promise<Result<TaskView>>
  /** 显式补齐或打开首会话。 Explicitly recover or open the first session. */
  ensureTaskSession(taskId: string): Promise<Result<CreateTaskResult>>
  /** 保存用户指定的会话归属与分工。 Save user-selected session ownership and scope. */
  assignSession(params: AssignSessionParams): Promise<Result<SessionSummary>>
  /** 创建项目会话，不调用模型。 Create a project session without a model request. */
  createSession(params: CreateSessionParams): Promise<Result<SessionSummary>>
  /** 切换后续请求的模型，保留会话。 Select the next model without replacing the session. */
  selectSessionModel(params: SelectSessionModelParams): Promise<Result<SessionSummary>>
  /** 分页读取会话。 Page project sessions. */
  listSessions(params: ListSessionsParams): Promise<Result<SessionPage>>
  /** 分页读取历史。 Page session history. */
  getSession(params: GetSessionParams): Promise<Result<SessionView>>
  /** 订阅并获取一致快照。 Subscribe and obtain a consistent snapshot. */
  attachSession(params: GetSessionParams): Promise<Result<SessionView>>
  /** 清理会话订阅。 Release a session subscription. */
  detachSession(sessionId: string): Promise<Result<object>>
  /** 持久接纳一次运行。 Durably accept a run. */
  startRun(params: StartRunParams): Promise<Result<SessionSummary>>
  /** 接纳停止，终态通过通知确认。 Accept cancellation; notifications confirm cleanup. */
  cancelRun(runId: string): Promise<Result<SessionSummary>>
  /** 查询跨视图活动运行。 Read the active run across views. */
  getActiveRuns(): Promise<Result<ActiveRunResult>>
  /** 监听已校验通知，卸载时注销。 Listen to validated notifications and unsubscribe on unmount. */
  onSessionEvent(listener: (signal: SessionSignal) => void): () => void
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
  /** 只读当前后端连接池状态。 Read current backend pool state without networking. */
  getConnections(): Promise<Result<ConnectionStatus>>
  /** 持久保存复用偏好，不中断活动回答。 Persist reuse policy without interrupting answers. */
  saveConnections(params: ConnectionSettings): Promise<Result<PublicConfig>>
  /** 释放现有连接，活动借用结束后关闭。 Retire connections after active borrowers finish. */
  releaseConnections(): Promise<Result<ConnectionStatus>>
  /** 显式测试目录连接，不携带密钥或生成内容。 Explicitly probe without keys or generation. */
  testConnection(params: ConnectionProbeParams): Promise<Result<ConnectionStatus>>
  /** 显式测试指定模型的一次真实响应，会使用额度。 Test one real model response using quota. */
  testModelConnection(params: ModelConnectionProbeParams): Promise<Result<ConnectionStatus>>
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
