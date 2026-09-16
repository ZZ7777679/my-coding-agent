/* Generated from Python DTOs. Do not edit by hand. */

export type CanContinue = boolean;
export type CreatedAt = string;
export type Issue = string | null;
export type ModelId = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type ProjectId = string;
export type Code = string | null;
export type InputTokens = number | null;
export type ExcludeGlobs = string[];
export type IncludeIgnored = boolean;
export type MaxContextBytes = number;
export type MaxDepth = number;
export type MaxFileBytes = number;
export type MaxOutputTokens = number;
export type MaxRequests = number;
export type MaxResponseBytes = number;
export type MaxScanFiles = number;
export type MaxSeconds = number;
export type MaxToolBytes = number;
export type MaxTools = number;
export type RequestTimeoutSeconds = number;
export type Message = string | null;
export type OutputTokens = number | null;
export type Requests = number;
export type RunId = string;
export type Status = "running" | "stopping" | "completed" | "failed" | "cancelled" | "budget_exceeded" | "interrupted";
export type Tools = number;
export type SessionId = string;
export type Title = string;
export type UpdatedAt = string;
export type AppVersion = string;
export type Name = string;
export type ProtocolVersion = 2;
export type Stage = "M1";
export type RunId1 = string;
export type Kind = "data" | "project";
export type TimeoutSeconds = number;
export type ProbeTimeoutSeconds = number;
export type ReuseEnabled = boolean;
export type ActiveRequests = number;
export type ClientCreated = boolean;
export type Code1 = string;
export type FinishedAt = string;
export type HttpStatus = number | null;
export type ModelId1 = ("glm-5.3-flash" | "deepseek-v4.1-flash") | null;
export type ModelsConfirmed = boolean | null;
export type ConnectMs = number | null;
export type ElapsedMs = number;
export type FirstEventMs = number | null;
export type FirstTextMs = number | null;
export type Phase = "preparing" | "connecting" | "tls" | "waiting" | "receiving" | "reasoning" | "text" | "completed";
export type ResponseComplete = boolean | null;
export type ResponseHeadersMs = number | null;
export type TlsMs = number | null;
export type Code2 = string;
export type FinishedAt1 = string;
export type Message1 = string;
export type Remediation = string;
export type InputTokens1 = number | null;
export type OutputTokens1 = number | null;
export type ModelId2 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Testing = boolean;
export type Models = ModelConnectionState[];
export type PendingRelease = boolean;
export type ReuseEnabled1 = boolean;
export type ModelId3 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type ProjectId1 = string;
export type EnvVar = "OPENCODE_API_KEY";
export type Present = boolean | null;
export type Source = "process" | "windows_user" | "none" | "restricted";
export type Blocking = boolean;
export type CheckId = string;
export type Code3 = string;
export type Remediation1 = string;
export type Status1 = "ok" | "warning" | "error" | "not_checked";
export type Summary = string;
export type AppVersion1 = string;
export type AuthenticationVerified = "not_checked";
export type CatalogReachable = "ok" | "error" | "not_checked";
export type CheckedAt = string;
export type Checks = DiagnosticCheck[];
export type CredentialPresent = boolean | null;
export type Mode = ("local" | "dev" | "network" | "write_probe")[];
export type ReportSchemaVersion = 1;
export type ToolRoundtripVerified = "not_checked";
export type Dev = boolean;
export type Network = boolean;
export type NetworkTimeoutSeconds = number | null;
export type WriteProbe = boolean;
export type Path = string | null;
export type Code4 = string;
export type Remediation2 = string;
export type Kind1 = "config" | "projects" | "diagnostics";
export type Path1 = string | null;
export type BeforeSeq = number | null;
export type SessionId1 = string;
export type AppVersion2 = string;
export type DataSchemaVersion = 1;
export type ProtocolVersion1 = 2;
export type Capabilities = (
  | "initialize"
  | "projects.open"
  | "projects.list"
  | "config.get"
  | "config.update"
  | "diagnostics.get"
  | "connections.get"
  | "connections.configure"
  | "connections.release"
  | "connections.test"
  | "connections.test_model"
  | "shutdown"
  | "sessions.create"
  | "sessions.list"
  | "sessions.get"
  | "sessions.attach"
  | "sessions.detach"
  | "runs.start"
  | "runs.cancel"
  | "runs.active"
)[];
export type AllowedModels = ("glm-5.3-flash" | "deepseek-v4.1-flash")[];
export type Api = "chat_completions";
export type BaseUrl = "https://opencode.ai/zen/go/v1";
export type ConfigPath = string;
export type ModelId4 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type ModelSource = "default" | "user" | "cli";
export type Provider = "opencode-go";
export type Available = boolean;
export type CanonicalPath = string;
export type LastOpenedAt = string;
export type Name1 = string;
export type Path2 = string;
export type ProjectId2 = string;
export type UnavailableCode = string | null;
export type RecentProjects = ProjectSummary[];
export type DataDir = string;
export type DataSchemaVersion1 = 1;
export type Source1 = "cli" | "environment" | "default";
export type Status2 = "ready" | "not_initialized" | "unavailable" | "busy";
export type Cursor = string | null;
export type Limit = number;
export type ProjectId3 = string;
export type ModelId5 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type TimeoutSeconds1 = number;
/**
 * 路径与已有标识二选一，禁止同时提交两种定位方式。
 *
 * Require either a path or an existing ID, never both.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "OpenProjectParams".
 */
export type OpenProjectParams = OpenProjectByPath | OpenProjectById;
export type Path3 = string;
export type ProjectId4 = string;
export type Code5 = string;
export type Message2 = string;
export type Remediation3 = string;
export type Jsonrpc = "2.0";
export type Method = string;
/**
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "JsonValue".
 */
export type JsonValue = unknown;
export type Id = string;
export type Jsonrpc1 = "2.0";
export type Method1 = string;
/**
 * 成功与失败响应的严格联合，不接受混合结构。
 *
 * Strict union of success and failure responses, rejecting mixed envelopes.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "RpcResponse".
 */
export type RpcResponse = RpcSuccess | RpcFailure;
export type Id1 = string;
export type Jsonrpc2 = "2.0";
export type Code6 = number;
export type Message3 = string;
export type Id2 = string | null;
export type Jsonrpc3 = "2.0";
export type Jsonrpc4 = "2.0";
export type Method2 = "session.event";
export type DeltaIndex = number;
export type Kind2 = "changed" | "text.delta" | "model.progress" | "resync";
export type MessageId = string | null;
export type ProcessEpoch = string;
export type RunId2 = string | null;
export type Seq = number;
export type SessionId2 = string;
export type Text = string;
export type ActiveSessionId = string | null;
export type NextCursor = string | null;
export type Sessions = SessionSummary[];
export type UnavailableCount = number;
export type SessionId3 = string;
export type BeforeSeq1 = number | null;
export type DeltaIndex1 = number;
export type Name2 = string;
export type ToolCallId = string;
export type Kind3 = "user" | "assistant" | "tool.started" | "tool.completed" | "run.finished";
export type MessageId1 = string | null;
export type Content = string;
export type IsError = boolean;
export type ToolCallId1 = string;
export type RunId3 = string | null;
export type Seq1 = number;
export type Text1 = string;
export type Entries = ChatEntry[];
export type ProcessEpoch1 = string;
export type StreamMessageId = string | null;
export type StreamText = string;
export type Watermark = number;
export type OperationId = string;
export type Prompt = string;
export type SessionId4 = string;
export type ConfigPath1 = string;
export type CurrentDataDir = string;
export type DataDir1 = string;
export type ProjectDir = string;
export type DataDir2 = string;
export type ProjectDir1 = string;
export type ModelId6 = "glm-5.3-flash" | "deepseek-v4.1-flash";

export interface ProtocolV2 {
  ActiveRunResult: ActiveRunResult;
  AppInfo: AppInfo;
  CancelRunParams: CancelRunParams;
  ChooseDirectoryParams: ChooseDirectoryParams;
  ConnectionProbeParams: ConnectionProbeParams;
  ConnectionSettings: ConnectionSettings;
  ConnectionStatus: ConnectionStatus;
  CreateSessionParams: CreateSessionParams;
  CredentialInfo: CredentialInfo;
  DiagnosticCheck: DiagnosticCheck;
  DiagnosticReport: DiagnosticReport;
  DiagnosticsParams: DiagnosticsParams;
  DirectorySelection: DirectorySelection;
  EmptyParams: EmptyParams;
  ErrorData: ErrorData;
  ExportParams: ExportParams;
  ExportResult: ExportResult;
  GetSessionParams: GetSessionParams;
  InitializeParams: InitializeParams;
  InitializeResult: InitializeResult;
  ListSessionsParams: ListSessionsParams;
  ModelConnectionProbeParams: ModelConnectionProbeParams;
  OpenProjectParams: OpenProjectParams;
  OperationError: OperationError;
  ProjectSummary: ProjectSummary;
  ProjectsView: ProjectsView;
  PublicConfig: PublicConfig;
  RpcNotification: RpcNotification;
  RpcRequest: RpcRequest;
  RpcResponse: RpcResponse;
  RunLimits: RunLimits;
  SessionEventNotification: SessionEventNotification;
  SessionPage: SessionPage;
  SessionParams: SessionParams;
  SessionSignal: SessionSignal;
  SessionSummary: SessionSummary;
  SessionView: SessionView;
  StartRunParams: StartRunParams;
  StartupPaths: StartupPaths;
  StartupPathsParams: StartupPathsParams;
  StorageInfo: StorageInfo;
  UpdateConfigParams: UpdateConfigParams;
}
/**
 * 公开全局运行状态，切换视图仍能停止。 Global run state remains stoppable across views.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ActiveRunResult".
 */
export interface ActiveRunResult {
  session: SessionSummary | null;
}
/**
 * 会话列表条目，不泄露原生模型状态。 Session list entry without native provider state.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "SessionSummary".
 */
export interface SessionSummary {
  can_continue: CanContinue;
  created_at: CreatedAt;
  issue: Issue;
  model_id: ModelId;
  project_id: ProjectId;
  run: RunView | null;
  session_id: SessionId;
  title: Title;
  updated_at: UpdatedAt;
}
/**
 * 公开运行计数；未知用量与未结束清理明确呈现。 Public counts and explicit unknown usage.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "RunView".
 */
export interface RunView {
  code: Code;
  input_tokens: InputTokens;
  limits: RunLimits;
  message: Message;
  output_tokens: OutputTokens;
  requests: Requests;
  run_id: RunId;
  status: Status;
  tools: Tools;
}
/**
 * 受信设置中的可调整限额，不代表模型能力。 Adjustable limits, not model capabilities.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "RunLimits".
 */
export interface RunLimits {
  exclude_globs: ExcludeGlobs;
  include_ignored: IncludeIgnored;
  max_context_bytes: MaxContextBytes;
  max_depth: MaxDepth;
  max_file_bytes: MaxFileBytes;
  max_output_tokens: MaxOutputTokens;
  max_requests: MaxRequests;
  max_response_bytes: MaxResponseBytes;
  max_scan_files: MaxScanFiles;
  max_seconds: MaxSeconds;
  max_tool_bytes: MaxToolBytes;
  max_tools: MaxTools;
  request_timeout_seconds: RequestTimeoutSeconds;
}
/**
 * 展示应用版本、协议版本与当前实现阶段。
 *
 * Expose the application version, protocol version and implemented stage.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "AppInfo".
 */
export interface AppInfo {
  app_version: AppVersion;
  name: Name;
  protocol_version: ProtocolVersion;
  stage: Stage;
}
/**
 * 只停止指定运行，不隐式停止其他任务。 Cancel the specified run only.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "CancelRunParams".
 */
export interface CancelRunParams {
  run_id: RunId1;
}
/**
 * 限定受信目录选择器的用途，不接受任意系统操作。
 *
 * Limit the trusted directory picker to its declared purpose.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ChooseDirectoryParams".
 */
export interface ChooseDirectoryParams {
  kind: Kind;
}
/**
 * 每次手动探测明确指定总等待时间。 Specify the total timeout for one manual probe.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ConnectionProbeParams".
 */
export interface ConnectionProbeParams {
  timeout_seconds: TimeoutSeconds;
}
/**
 * 持久化复用偏好与手动探测等待时间。 Persist reuse preference and manual probe timeout.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ConnectionSettings".
 */
export interface ConnectionSettings {
  probe_timeout_seconds: ProbeTimeoutSeconds;
  reuse_enabled: ReuseEnabled;
}
/**
 * 后端自身管理状态，不把客户端个数冒充在线套接字数。
 *
 * Backend-owned lifecycle state, without claiming a count of live sockets.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ConnectionStatus".
 */
export interface ConnectionStatus {
  active_requests: ActiveRequests;
  client_created: ClientCreated;
  last_probe: ConnectionObservation | null;
  last_request: ConnectionObservation | null;
  models?: Models;
  pending_release: PendingRelease;
  reuse_enabled: ReuseEnabled1;
}
/**
 * 最近一次操作的脱敏结果；历史成功不保证当前在线。
 *
 * A sanitized observation of one operation, never a guarantee of current connectivity.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ConnectionObservation".
 */
export interface ConnectionObservation {
  code: Code1;
  finished_at: FinishedAt;
  http_status: HttpStatus;
  model_id?: ModelId1;
  models_confirmed: ModelsConfirmed;
  progress: ModelProgress;
}
/**
 * 请求阶段与单调时钟耗时，不包含网络原文。 Request phases and timings without raw payloads.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ModelProgress".
 */
export interface ModelProgress {
  connect_ms?: ConnectMs;
  elapsed_ms: ElapsedMs;
  first_event_ms?: FirstEventMs;
  first_text_ms?: FirstTextMs;
  phase: Phase;
  response_complete?: ResponseComplete;
  response_headers_ms?: ResponseHeadersMs;
  tls_ms?: TlsMs;
}
/**
 * 按模型保存正在测试的进度和最近结果；不代表独立套接字。
 *
 * Per-model test progress and last result, not a separate physical connection.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ModelConnectionState".
 */
export interface ModelConnectionState {
  last_test: ModelConnectionResult | null;
  model_id: ModelId2;
  progress: ModelProgress | null;
  testing: Testing;
}
/**
 * 单次真实模型测试的公开结果，不包含提示或回答。
 *
 * Public facts from one real model test, excluding prompts and responses.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ModelConnectionResult".
 */
export interface ModelConnectionResult {
  code: Code2;
  finished_at: FinishedAt1;
  message: Message1;
  progress: ModelProgress;
  remediation: Remediation;
  usage: TokenUsage | null;
}
/**
 * 服务实际返回的用量；未知保留 null。 Reported usage; unknown remains null.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "TokenUsage".
 */
export interface TokenUsage {
  input_tokens: InputTokens1;
  output_tokens: OutputTokens1;
}
/**
 * 选择项目与模型，不发起运行。 Select project and model without starting a run.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "CreateSessionParams".
 */
export interface CreateSessionParams {
  model_id: ModelId3;
  project_id: ProjectId1;
}
/**
 * 仅公开凭据来源与存在状态；null 表示读取受限。
 *
 * Expose only credential source and presence; null means access was restricted.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "CredentialInfo".
 */
export interface CredentialInfo {
  env_var: EnvVar;
  present: Present;
  source: Source;
}
/**
 * 单项诊断的公开结论、影响与脱敏证据。
 *
 * Public outcome, impact and sanitized evidence for one diagnostic check.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "DiagnosticCheck".
 */
export interface DiagnosticCheck {
  blocking: Blocking;
  check_id: CheckId;
  code: Code3;
  evidence: Evidence;
  remediation: Remediation1;
  status: Status1;
  summary: Summary;
}
export interface Evidence {
  [k: string]: string | boolean | number | null;
}
/**
 * 区分凭据存在与目录可达；M0 尚未验证认证或真实工具回合。
 *
 * Separate key presence and catalog access from auth and tool calls, unverified in M0.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "DiagnosticReport".
 */
export interface DiagnosticReport {
  app_version: AppVersion1;
  authentication_verified: AuthenticationVerified;
  catalog_reachable: CatalogReachable;
  checked_at: CheckedAt;
  checks: Checks;
  connections?: ConnectionStatus | null;
  credential_present: CredentialPresent;
  mode: Mode;
  report_schema_version: ReportSchemaVersion;
  tool_roundtrip_verified: ToolRoundtripVerified;
}
/**
 * 显式声明额外诊断选项，避免隐式联网或写入。
 *
 * Declare optional probes explicitly to prevent implicit networking or writes.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "DiagnosticsParams".
 */
export interface DiagnosticsParams {
  dev: Dev;
  network: Network;
  network_timeout_seconds?: NetworkTimeoutSeconds;
  write_probe: WriteProbe;
}
/**
 * 返回已选择目录；null 明确表示取消选择。
 *
 * Return the selected directory, with null explicitly representing cancellation.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "DirectorySelection".
 */
export interface DirectorySelection {
  path: Path;
}
/**
 * 表示不接受参数的方法，拒绝任何额外字段。
 *
 * Represent parameterless methods and reject every extra field.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "EmptyParams".
 */
export interface EmptyParams {}
/**
 * RPC 错误的稳定业务码与修复说明。
 *
 * Stable application error code and remediation inside an RPC error.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ErrorData".
 */
export interface ErrorData {
  code: Code4;
  remediation: Remediation2;
}
/**
 * 限定导出的公开文档类型，内容由后端提供。
 *
 * Select a public export category whose content comes from the backend.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ExportParams".
 */
export interface ExportParams {
  kind: Kind1;
}
/**
 * 返回成功导出的文件位置；null 表示用户取消。
 *
 * Return the exported file location, or null when the user cancels.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ExportResult".
 */
export interface ExportResult {
  path: Path1;
}
/**
 * 显式历史页游标，null 取最近一页。 Explicit history cursor; null loads the latest page.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "GetSessionParams".
 */
export interface GetSessionParams {
  before_seq: BeforeSeq;
  session_id: SessionId1;
}
/**
 * 前端声明的兼容性信息；应用版本与协议版本分别处理。
 *
 * Client compatibility information, keeping app and protocol versions distinct.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "InitializeParams".
 */
export interface InitializeParams {
  app_version: AppVersion2;
  data_schema_version: DataSchemaVersion;
  protocol_version: ProtocolVersion1;
}
/**
 * 返回初始化后的公开状态与当前实际支持的方法。
 *
 * Return initialized public state and the methods currently supported.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "InitializeResult".
 */
export interface InitializeResult {
  app: AppInfo;
  capabilities: Capabilities;
  config: PublicConfig;
  projects: ProjectsView;
  storage: StorageInfo;
}
/**
 * 前端可见的模型配置，不携带凭据原值。
 *
 * Renderer-visible model configuration without credential values.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "PublicConfig".
 */
export interface PublicConfig {
  allowed_models: AllowedModels;
  api: Api;
  base_url: BaseUrl;
  config_path: ConfigPath;
  credential: CredentialInfo;
  http: ConnectionSettings;
  model_id: ModelId4;
  model_source: ModelSource;
  provider: Provider;
  run: RunLimits;
}
/**
 * 同时返回当前项目与最近记录，允许初次启动为空。
 *
 * Return active and recent projects, allowing an empty first-launch state.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ProjectsView".
 */
export interface ProjectsView {
  active_project: ProjectSummary | null;
  recent_projects: RecentProjects;
}
/**
 * 公开项目记录及当前可用性，隐藏内部文件系统身份字段。
 *
 * Expose project metadata and availability without internal filesystem identity fields.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ProjectSummary".
 */
export interface ProjectSummary {
  available: Available;
  canonical_path: CanonicalPath;
  last_opened_at: LastOpenedAt;
  name: Name1;
  path: Path2;
  project_id: ProjectId2;
  unavailable_code: UnavailableCode;
}
/**
 * 展示实际数据根、配置来源和存储可用状态。
 *
 * Expose the effective data root, its source and storage availability.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "StorageInfo".
 */
export interface StorageInfo {
  data_dir: DataDir;
  data_schema_version: DataSchemaVersion1;
  source: Source1;
  status: Status2;
}
/**
 * 按项目分页会话列表。 Page sessions by project.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ListSessionsParams".
 */
export interface ListSessionsParams {
  cursor: Cursor;
  limit: Limit;
  project_id: ProjectId3;
}
/**
 * 显式选择被测模型，不沿用当前会话选择。 Select the tested model explicitly.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ModelConnectionProbeParams".
 */
export interface ModelConnectionProbeParams {
  model_id: ModelId5;
  timeout_seconds: TimeoutSeconds1;
}
/**
 * 通过用户选择的目录路径打开项目。
 *
 * Open a project using a user-selected directory path.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "OpenProjectByPath".
 */
export interface OpenProjectByPath {
  path: Path3;
}
/**
 * 通过已有项目标识恢复选择，并由服务重新验证目录。
 *
 * Restore a recorded project by ID and let the service revalidate its directory.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "OpenProjectById".
 */
export interface OpenProjectById {
  project_id: ProjectId4;
}
/**
 * 桌面操作使用的公开错误，不包含原始异常堆栈。
 *
 * Public desktop-operation error without a raw exception traceback.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "OperationError".
 */
export interface OperationError {
  code: Code5;
  message: Message2;
  remediation: Remediation3;
}
/**
 * 不要求回复的 JSON-RPC 通知，不能与带标识请求混淆。
 *
 * JSON-RPC notification requiring no reply, distinct from an identified request.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "RpcNotification".
 */
export interface RpcNotification {
  jsonrpc: Jsonrpc;
  method: Method;
  params: Params;
}
export interface Params {
  [k: string]: JsonValue;
}
/**
 * 带关联标识的 JSON-RPC 请求；参数在方法分发时继续校验。
 *
 * JSON-RPC request with a correlation ID; method dispatch validates parameters further.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "RpcRequest".
 */
export interface RpcRequest {
  id: Id;
  jsonrpc: Jsonrpc1;
  method: Method1;
  params: Params1;
}
export interface Params1 {
  [k: string]: JsonValue;
}
/**
 * 关联请求标识与成功结果；具体结果仍需按方法校验。
 *
 * Associate a request ID with its result, which still needs method-specific validation.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "RpcSuccess".
 */
export interface RpcSuccess {
  id: Id1;
  jsonrpc: Jsonrpc2;
  result: JsonValue;
}
/**
 * 关联请求与公开错误；无法确定请求标识时允许 null。
 *
 * Associate a request with a public error, allowing null when its ID is unknown.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "RpcFailure".
 */
export interface RpcFailure {
  error: RpcError;
  id: Id2;
  jsonrpc: Jsonrpc3;
}
/**
 * 将 JSON-RPC 数字错误码与应用错误信息分开表达。
 *
 * Keep JSON-RPC numeric codes distinct from application error information.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "RpcError".
 */
export interface RpcError {
  code: Code6;
  data: ErrorData;
  message: Message3;
}
/**
 * 唯一支持的后端事件通知形状。 The sole supported backend notification envelope.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "SessionEventNotification".
 */
export interface SessionEventNotification {
  jsonrpc: Jsonrpc4;
  method: Method2;
  params: SessionSignal;
}
/**
 * 轻量通知：持久变更需要重取快照，文本按增量顺序接收。
 *
 * Lightweight notifications: resync durable changes and order transient text deltas.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "SessionSignal".
 */
export interface SessionSignal {
  delta_index: DeltaIndex;
  kind: Kind2;
  message_id: MessageId;
  model_progress?: ModelProgress | null;
  process_epoch: ProcessEpoch;
  run_id: RunId2;
  seq: Seq;
  session_id: SessionId2;
  text: Text;
}
/**
 * 项目会话的游标页。 Cursor page of project sessions.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "SessionPage".
 */
export interface SessionPage {
  active_session_id: ActiveSessionId;
  next_cursor: NextCursor;
  sessions: Sessions;
  unavailable_count: UnavailableCount;
}
/**
 * 限定会话身份。 Constrain session identity.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "SessionParams".
 */
export interface SessionParams {
  session_id: SessionId3;
}
/**
 * 有界快照含历史水位与实时预览。 Bounded snapshot with history watermark and live preview.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "SessionView".
 */
export interface SessionView {
  before_seq: BeforeSeq1;
  delta_index: DeltaIndex1;
  entries: Entries;
  model_progress?: ModelProgress | null;
  process_epoch: ProcessEpoch1;
  stream_message_id: StreamMessageId;
  stream_text: StreamText;
  summary: SessionSummary;
  watermark: Watermark;
}
/**
 * 显式投影的可公开历史记录。 Explicitly projected public history record.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ChatEntry".
 */
export interface ChatEntry {
  call: ToolCall | null;
  kind: Kind3;
  message_id: MessageId1;
  result: ToolResult | null;
  run_id: RunId3;
  seq: Seq1;
  text: Text1;
}
/**
 * 完整参数对象，仍需工具权限校验。 Complete arguments still requiring tool policy checks.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ToolCall".
 */
export interface ToolCall {
  arguments: JsonObject;
  name: Name2;
  tool_call_id: ToolCallId;
}
/**
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "JsonObject".
 */
export interface JsonObject {
  [k: string]: JsonValue;
}
/**
 * 按调用标识关联可公开工具结果。 Associate public tool output with its call ID.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "ToolResult".
 */
export interface ToolResult {
  content: Content;
  is_error: IsError;
  tool_call_id: ToolCallId1;
}
/**
 * 幂等操作 ID 独立于 RPC ID。 Idempotent operation identity is separate from RPC identity.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "StartRunParams".
 */
export interface StartRunParams {
  limits: RunLimits | null;
  operation_id: OperationId;
  prompt: Prompt;
  session_id: SessionId4;
}
/**
 * 区分已保存的下次启动设置与本次实际数据根。
 *
 * Distinguish saved next-launch paths from the current effective data root.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "StartupPaths".
 */
export interface StartupPaths {
  config_path: ConfigPath1;
  current_data_dir: CurrentDataDir;
  data_dir: DataDir1;
  project_dir: ProjectDir;
}
/**
 * 描述下次启动的目录设置，不触发数据迁移或项目登记。
 *
 * Describe next-launch directories without migrating data or registering projects.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "StartupPathsParams".
 */
export interface StartupPathsParams {
  data_dir: DataDir2;
  project_dir: ProjectDir1;
}
/**
 * 仅允许保存一个受支持的默认模型标识。
 *
 * Allow saving only one supported default model ID.
 *
 * This interface was referenced by `ProtocolV2`'s JSON-Schema
 * via the `definition` "UpdateConfigParams".
 */
export interface UpdateConfigParams {
  model_id: ModelId6;
  run?: RunLimits | null;
}
