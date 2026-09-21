/* Generated from Python DTOs. Do not edit by hand. */

export type CanContinue = boolean;
export type CreatedAt = string;
export type Issue = string | null;
export type Mode = "normal" | "plan";
export type ModelId = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type ProjectId = string;
export type Role = string;
export type Code = string | null;
export type GoalId = string | null;
export type GoalRole = ("work" | "question") | null;
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
export type Method = ("discuss" | "plan" | "implement" | "diagnose" | "review" | "handoff") | null;
export type MethodVersion = string | null;
export type Mode1 = "normal" | "plan";
export type OutputTokens = number | null;
export type PlanDocument = string | null;
export type ProgressSync = "none" | "pending" | "synced";
export type Requests = number;
export type RunId = string;
export type Status = "running" | "stopping" | "completed" | "failed" | "cancelled" | "budget_exceeded" | "interrupted";
export type Tools = number;
export type WaitedSeconds = number;
export type WaitingFor = string | null;
export type WorkId = string | null;
export type Scope = string;
export type SessionId = string;
export type TaskId = string | null;
export type Title = string;
export type UpdatedAt = string;
export type Sessions = SessionSummary[];
export type AppVersion = string;
export type Name = string;
export type ProtocolVersion = 4;
export type Stage = "M3";
export type ContextMode = "isolated" | "inherit";
export type Kind = "handoff" | "review";
export type Notes = string;
export type Objective = string;
export type OperationId = string;
export type SourceSessionId = string;
export type TargetSessionId = string;
export type TransferGoalId = string | null;
export type TransferRunId = string | null;
export type OperationId1 = string;
export type Role1 = string;
export type Scope1 = string;
export type SessionId1 = string;
export type TaskId1 = string;
export type EnvironmentId = string | null;
export type ExpectedRevision = number;
export type Mode2 = "direct" | "sandbox";
export type ProjectId1 = string;
/**
 * Legacy compatibility field; not an execution gate. Use the selected mode.
 */
export type Trusted = boolean;
export type RunId1 = string;
export type AfterSha256 = string;
export type BeforeSha256 = string | null;
export type ChangeId = string;
export type CreatedAt1 = string;
export type Error = string | null;
export type Operation = "create" | "edit";
export type Path = string;
export type ProjectId2 = string;
export type RunId2 = string;
export type SessionId2 = string;
export type Status1 = "prepared" | "applied" | "failed";
export type ToolCallId = string;
export type Changes = ChangeSummary[];
export type NextCursor = string | null;
export type UnavailableCount = number;
export type Diff = string;
export type NextOffset = number | null;
export type Kind1 = "data" | "project";
export type Kind2 = "executable" | "directory";
export type BeforeSeq = number | null;
export type Limit = number;
export type SourceSessionId1 = string;
export type TargetSessionId1 = string;
export type Enabled = boolean;
export type Mode3 = "normal" | "plan";
export type Scope2 = string;
export type SourceSessionId2 = string;
export type TargetSessionId2 = string;
export type TaskId2 = string;
export type UpdatedAt1 = string;
export type Error1 = string | null;
export type Links = CollaborationLink[];
export type NextCursor1 = string | null;
export type CapturedAt = string;
export type InheritedContext = string;
export type MaxActiveSeconds = number | null;
export type MaxRequests1 = number | null;
export type MaxTools1 = number | null;
export type Code1 = string | null;
export type CriterionId = string;
export type Description = string;
export type Criteria = GoalCriterion[];
export type GoalId1 = string;
export type CriterionId1 = string;
export type Expectation = "observed" | "succeeded";
export type Kind3 = "tool_result" | "assistant" | "user";
export type RunId3 = string;
export type Seq = number;
export type SessionId3 = string;
export type Evidence = EvidenceRef[];
export type Explanation = string;
export type Status2 = "met" | "unmet" | "not_checked" | "needs_user";
export type Criteria1 = CriterionResult[];
export type Status3 = "user_confirmed" | "proposal";
export type Text = string;
export type Decisions = SharedDecision[];
export type NextAction = string;
export type NextWorkId = string | null;
export type Outcome = "continue" | "complete" | "wait" | "return";
export type Impact = string;
export type Options = string[];
export type Question = string;
export type QuestionId = string;
export type Summary = string;
export type DependsOn = string[];
export type Evidence1 = EvidenceRef[];
export type FeedbackFrom = EvidenceRef[];
export type Method1 = "discuss" | "plan" | "implement" | "diagnose" | "review" | "handoff";
export type Scope3 = string;
export type Status4 = "planned" | "in_progress" | "completed" | "waiting";
export type Title1 = string;
export type WorkId1 = string;
export type WorkItems = WorkItem[];
export type LastResultSeq = number | null;
export type Objective1 = string;
export type OperationId2 = string;
export type Prompt = string;
export type PendingInputs = GoalInputView[];
export type Revision = number;
export type SessionId4 = string;
export type Status5 =
  "active" | "paused" | "waiting" | "failed" | "budget_exceeded" | "interrupted" | "completed" | "cancelled";
export type ActiveSeconds = number;
export type InputTokens1 = number | null;
export type OutputTokens1 = number | null;
export type Requests2 = number;
export type ReservedSeconds = number;
export type Tools1 = number;
export type UncertainRunIds = string[];
export type SourceSessionId3 = string;
export type SourceWatermark = number;
export type CreatedAt2 = string;
export type Artifacts = string;
export type Constraints = string;
export type Decisions1 = string;
export type Goal = string;
export type Progress = string;
export type Status6 = "active" | "completed" | "archived";
export type Title2 = string;
export type Unresolved = string;
export type InitialModelId = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type InitialSessionId = string;
export type ProjectId3 = string;
export type Revision1 = number;
export type Source = "user" | "run_report";
export type TaskId3 = string;
export type UpdatedAt2 = string;
export type RunId4 = string;
export type Seq1 = number;
export type SessionId5 = string;
export type Decisions2 = SourcedDecision[];
export type Items = SourcedWorkItem[];
export type UpdatedAt3 = string;
export type Members = MemberProgress[];
export type CreatedAt3 = string;
export type ExpectedResult = string;
export type Inputs = string;
export type Mode4 = "normal" | "plan";
export type Objective2 = string;
export type OperationId3 = string;
export type SourceSessionId4 = string;
export type TargetSessionId3 = string;
export type ParentRequestId = string | null;
export type Reason = string | null;
export type RequestId = string;
export type Result = string;
export type ResultSeq = number | null;
export type SchemaVersion = 1;
export type Scope4 = string;
export type SourceRunId = string | null;
export type Status7 = "preparing" | "queued" | "running" | "completed" | "failed" | "cancelled" | "held";
export type TargetRunId = string | null;
export type TaskId4 = string;
export type UpdatedAt4 = string;
export type Requests1 = CollaborationRequest[];
export type Cursor = string | null;
export type Limit1 = number;
export type SessionId6 = string;
export type SessionId7 = string;
export type AutoTriggerTokens = number;
export type Automatic = boolean;
export type KeepRecentTokens = number;
export type SummaryOutputTokens = number | null;
export type SummaryTargetTokens = number;
export type ToolResultPreviewTokens = number;
export type SessionId8 = string;
export type Associations = boolean;
export type AutoPages = boolean;
export type Automatic1 = boolean;
export type Contribute = boolean;
export type MaintenanceInputBytes = number;
export type MaintenanceRequests = number;
export type RecallChars = number;
export type RecallLimit = number;
export type Use = boolean;
export type SessionId9 = string;
export type Concurrency = number;
export type Enabled1 = boolean;
export type Enabled2 = boolean;
export type Mode5 = "normal" | "plan";
export type Scope5 = string;
export type SourceSessionId5 = string;
export type TargetSessionId4 = string;
export type TimeoutSeconds = number;
export type ProbeTimeoutSeconds = number;
export type ReuseEnabled = boolean;
export type ActiveRequests = number;
export type ClientCreated = boolean;
export type Code2 = string;
export type FinishedAt = string;
export type HttpStatus = number | null;
export type ModelId1 = ("glm-5.3-flash" | "deepseek-v4.1-flash") | null;
export type ModelsConfirmed = boolean | null;
export type ConnectMs = number | null;
export type ElapsedMs = number;
export type FirstEventMs = number | null;
export type FirstTextMs = number | null;
export type LastDataMs = number | null;
export type Phase =
  "preparing" | "connecting" | "tls" | "waiting" | "receiving" | "reasoning" | "text" | "tool_arguments" | "completed";
export type ReceivedBytes = number | null;
export type ResponseComplete = boolean | null;
export type ResponseHeadersMs = number | null;
export type TlsMs = number | null;
export type Code3 = string;
export type FinishedAt1 = string;
export type Message1 = string;
export type Remediation = string;
export type InputTokens2 = number | null;
export type OutputTokens2 = number | null;
export type ModelId2 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Testing = boolean;
export type Models = ModelConnectionState[];
export type PendingRelease = boolean;
export type ReuseEnabled1 = boolean;
export type SessionId10 = string;
export type CheckpointId = string;
export type CreatedAt4 = string;
export type ModelId3 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type ParentId = string | null;
export type Text1 = string;
export type ThroughSeq = number;
export type EstimateBasis = string;
export type EstimatedHistoryTokens = number;
export type EstimatedInputTokens = number | null;
export type HistoryThroughSeq = number;
export type CompressionApplied = boolean | null;
export type FinishReason = string | null;
export type FinishedAt2 = string | null;
export type HistoryAfterBytes = number | null;
export type HistoryAfterTokens = number | null;
export type HistoryBeforeBytes = number | null;
export type HistoryBeforeTokens = number | null;
export type JobId = string;
export type Message2 = string;
export type Mode6 = "manual" | "automatic";
export type ModelId4 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Outcome1 = ("summary" | "trimmed" | "nothing" | "not_smaller") | null;
export type OutputTokenLimit = number | null;
export type Requests3 = number;
export type RetainedTokens = number | null;
export type RunId5 = string | null;
export type StartedAt = string;
export type Status8 = "preparing" | "receiving" | "ready" | "adopted" | "failed" | "cancelled" | "interrupted";
export type ThroughSeq1 = number;
export type At = string;
export type EstimatedFixedTokens = number | null;
export type EstimatedInputTokens1 = number | null;
export type Form = string;
export type Kind4 = string;
export type Preview = string;
export type PreviewComplete = boolean;
/**
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "JsonValue".
 */
export type JsonValue = unknown;
export type ReadTool = string | null;
export type Reason1 = string;
export type Revision2 = number | null;
export type SourceId = string | null;
export type Title3 = string;
export type Materials = ContextMaterial[];
export type MessageCount = number;
export type RequestBytes = number;
export type ToolNames = string[];
export type MessageId = string;
export type ModelId5 = ("glm-5.3-flash" | "deepseek-v4.1-flash") | null;
export type LimitBytes = number;
export type Measurement = "history_bytes";
export type MigratedFromBytes = boolean;
export type RawBytes = number;
export type SessionId11 = string;
export type InputTokens3 = number | null;
export type ModelId6 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Status9 = "reported" | "not_measured" | "not_reported" | "model_changed" | "compacted";
export type WindowSource = string;
export type WindowTokens = number | null;
export type ReportedInputTokens = number;
export type ReportedOutputTokens = number;
export type Requests4 = number;
export type UnavailableJobs = number;
export type UnknownJobs = number;
export type TriggerTokens = number;
export type WindowBytes = number;
export type Action = "cancel" | "resume";
export type RequestId1 = string;
/**
 * 三个互斥分支使 Python 与桌面校验器都拒绝错误字段组合。
 *
 * Three disjoint branches let both Python and desktop reject invalid field combinations.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ControlGoalParams".
 */
export type ControlGoalParams = GoalStateControl | GoalBudgetControl | GoalAnswerControl;
export type Action1 = "resume" | "pause" | "cancel";
export type ExpectedRevision1 = number;
export type GoalId2 = string;
export type OperationId4 = string;
export type SessionId12 = string;
export type Action2 = "budget";
export type ExpectedRevision2 = number;
export type GoalId3 = string;
export type OperationId5 = string;
export type SessionId13 = string;
export type Action3 = "answer";
export type Answer = string;
export type ExpectedRevision3 = number;
export type GoalId4 = string;
export type OperationId6 = string;
export type QuestionId1 = string;
export type SessionId14 = string;
/**
 * @minItems 1
 */
export type Criteria2 = [GoalCriterion, ...GoalCriterion[]];
export type GoalId5 = string;
export type Method2 = "discuss" | "plan" | "implement" | "diagnose" | "review" | "handoff";
export type Objective3 = string;
export type SessionId15 = string;
export type ModelId7 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type OperationId7 = string | null;
export type ProjectId4 = string;
export type Role2 = string;
export type Scope6 = string;
export type TaskId5 = string | null;
export type ModelId8 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type OperationId8 = string;
export type ProjectId5 = string;
export type SessionError = string | null;
export type EnvVar = "OPENCODE_API_KEY";
export type Present = boolean | null;
export type Source1 = "process" | "windows_user" | "none" | "restricted";
export type Blocking = boolean;
export type CheckId = string;
export type Code4 = string;
export type Remediation1 = string;
export type Status10 = "ok" | "warning" | "error" | "not_checked";
export type Summary1 = string;
export type AppVersion1 = string;
export type AuthenticationVerified = "not_checked";
export type CatalogReachable = "ok" | "error" | "not_checked";
export type CheckedAt = string;
export type Checks = DiagnosticCheck[];
export type CredentialPresent = boolean | null;
export type Mode7 = ("local" | "dev" | "network" | "write_probe")[];
export type ReportSchemaVersion = 1;
export type ToolRoundtripVerified = "not_checked";
export type Dev = boolean;
export type Network = boolean;
export type NetworkTimeoutSeconds = number | null;
export type WriteProbe = boolean;
export type Path1 = string | null;
export type EnvironmentId1 = string | null;
export type Mode8 = "direct" | "sandbox";
export type ProjectId6 = string;
/**
 * Legacy compatibility field; not an execution gate. Use the selected mode.
 */
export type Trusted1 = boolean;
export type Available = boolean;
export type Interpreter = string | null;
export type Issue1 = string | null;
export type Launcher = string | null;
export type Prefix = string | null;
export type Definition = SystemEnvironment | PythonEnvironment | CondaEnvironment | UvEnvironment;
export type Kind5 = "system";
export type Interpreter1 = string;
export type Kind6 = "python";
export type Scope7 = "absolute" | "project";
export type Kind7 = "conda";
export type Launcher1 = string;
export type Prefix1 = string;
export type Scope8 = "absolute" | "project";
export type Interpreter2 = string;
export type Kind8 = "uv";
export type Launcher2 = string;
export type Scope9 = "absolute" | "project";
export type EnvironmentId2 = string;
export type Name1 = string;
export type CheckedAt1 = string;
export type Code5 = string;
export type Interpreter3 = string | null;
export type LauncherVersion = string | null;
export type Message3 = string;
export type ProjectId7 = string | null;
export type Version = string | null;
export type Environments = EnvironmentView[];
export type Revision3 = number;
export type CleanupTimeoutSeconds = number;
export type CommandTimeoutSeconds = number;
export type MaxOutputBytes = number;
export type ProbeTimeoutSeconds1 = number;
export type ServiceReadyTimeoutSeconds = number;
export type EnvironmentId3 = string;
export type ProjectId8 = string | null;
export type ProjectId9 = string | null;
export type Code6 = string;
export type Remediation2 = string;
export type ProbeCount = number;
export type Code7 = string | null;
export type Command = ProgramCommand | ShellCommand;
export type Arguments = string[];
export type Kind9 = "program";
export type Program = string;
export type Kind10 = "powershell";
export type Script = string;
export type CreatedAt5 = string;
export type Cwd = string;
export type DroppedBytes = number;
export type EnvironmentId4 = string;
export type EnvironmentName = string;
export type EnvironmentRevision = number;
export type ExitCode = number | null;
export type FinishedAt3 = string | null;
export type HttpStatus1 = number | null;
export type Kind11 = "command" | "service";
export type Message4 = string | null;
export type Mode9 = "direct";
export type Pid = number | null;
export type ProgramId = string;
export type ProjectId10 = string;
export type ResolvedCommand = string[];
export type Retained = boolean;
export type RunId6 = string;
export type SessionId16 = string;
export type Status11 = "starting" | "running" | "ready" | "stopping" | "exited" | "stopped" | "failed" | "interrupted";
export type ToolCallId1 = string | null;
export type Url = string | null;
export type Programs = ProgramSummary[];
export type Kind12 = "config" | "projects" | "diagnostics";
export type Path2 = string | null;
export type MemoryId = string;
export type SessionId17 = string;
export type ChangeId1 = string;
export type Offset = number;
export type SessionId18 = string;
export type AfterSeq = number;
export type ProgramId1 = string;
export type BeforeSeq1 = number | null;
export type SessionId19 = string;
export type BeforeSeq2 = number | null;
export type Goals = GoalView[];
export type Complete = boolean;
export type CallSeq = number | null;
export type Kind13 = string;
export type NextOffset1 = number | null;
export type Offset1 = number;
export type ResultSeq1 = number | null;
export type Seq2 = number;
export type Text2 = string;
export type ToolCallId2 = string | null;
export type ToolName = string | null;
export type TotalChars = number;
export type Items1 = HistoryItem[];
export type MatchUnit = "records" | "occurrences";
export type Matches = number;
export type NextAfterSeq = number | null;
export type ThroughSeq2 = number;
export type AfterSeq1 = number;
export type ArtifactId = string | null;
export type EntrySeq = number | null;
export type IncludeLookupResults = boolean;
export type Limit2 = number;
export type MaxChars = number;
export type Offset2 = number;
export type Query = string;
export type SessionId20 = string;
export type ThroughSeq3 = number | null;
export type AppVersion2 = string;
export type DataSchemaVersion = 1;
export type ProtocolVersion1 = 4;
export type Capabilities = (
  | "context.get"
  | "context.configure"
  | "context.compact"
  | "context.cancel"
  | "context.history"
  | "memory.list"
  | "memory.save"
  | "memory.forget"
  | "memory.configure"
  | "memory.maintain"
  | "memory.cancel"
  | "initialize"
  | "workers.list"
  | "workers.configure"
  | "workers.control"
  | "collaboration.message"
  | "collaboration.messages"
  | "projects.open"
  | "projects.relocate"
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
  | "sessions.select_model"
  | "tasks.create"
  | "tasks.list"
  | "tasks.get"
  | "tasks.update"
  | "tasks.ensure_session"
  | "sessions.assign"
  | "collaboration.list"
  | "collaboration.connect"
  | "collaboration.history"
  | "collaboration.request"
  | "collaboration.control"
  | "collaboration.arrange"
  | "sessions.list"
  | "sessions.get"
  | "sessions.attach"
  | "sessions.detach"
  | "runs.start"
  | "runs.cancel"
  | "runs.active"
  | "goals.create"
  | "goals.list"
  | "goals.control"
  | "changes.list"
  | "changes.get"
  | "environments.list"
  | "environments.save"
  | "environments.remove"
  | "environments.probe"
  | "environments.bind"
  | "execution.configure"
  | "programs.list"
  | "programs.get"
  | "programs.stop"
  | "execution.status"
)[];
export type AllowedModels = ("glm-5.3-flash" | "deepseek-v4.1-flash")[];
export type Api = "chat_completions";
export type BaseUrl = "https://opencode.ai/zen/go/v1";
export type ConfigPath = string;
export type ModelId9 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type ModelSource = "default" | "user" | "cli";
export type Provider = "opencode-go";
export type Available1 = boolean;
export type CanonicalPath = string;
export type LastOpenedAt = string;
export type Name2 = string;
export type Path3 = string;
export type ProjectId11 = string;
export type UnavailableCode = string | null;
export type RecentProjects = ProjectSummary[];
export type DataDir = string;
export type DataSchemaVersion1 = 1;
export type Source2 = "cli" | "environment" | "default";
export type Status12 = "ready" | "not_initialized" | "unavailable" | "busy";
export type Cursor1 = string | null;
export type Limit3 = number;
export type SessionId21 = string;
export type BeforeSeq3 = number | null;
export type Limit4 = number;
export type SessionId22 = string;
export type Category = string | null;
export type Cursor2 = string | null;
export type IncludeDisabled = boolean;
export type Limit5 = number;
export type Query1 = string;
export type SessionId23 = string;
export type Subject = string | null;
export type Cursor3 = string | null;
export type Limit6 = number;
export type ProjectId12 = string;
export type SessionId24 = string | null;
export type Cursor4 = string | null;
export type Limit7 = number;
export type ProjectId13 = string;
export type AfterSeq2 = number | null;
export type SessionId25 = string;
export type SourceIds = string[];
export type Title4 = string;
export type Category1 = string;
export type Content = string;
export type CreatedAt6 = string;
export type Enabled3 = boolean;
export type MemoryId1 = string;
export type Pinned = boolean;
export type ProjectId14 = string | null;
export type RelatedIds = string[];
export type Revision4 = number;
export type Scope10 = "project" | "user";
export type SessionId26 = string | null;
export type Source3 = "user" | "agent" | "maintenance";
export type SourceIds1 = string[];
export type SourceSeq = number | null;
export type Stale = boolean;
export type Subjects = string[];
export type Supersedes = string[];
export type Tags = string[];
export type Title5 = string;
export type UpdatedAt5 = string;
export type ValidFrom = string | null;
export type ValidUntil = string | null;
export type Entries = MemoryEntry[];
export type NextCursor2 = string | null;
export type FinishedAt4 = string | null;
export type JobId1 = string;
export type Message5 = string;
export type ModelId10 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Requests5 = number;
export type StartedAt1 = string;
export type Status13 = "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type ThroughSeq4 = number;
export type PendingOffset = number;
export type PendingSeq = number | null;
export type ProcessedSeq = number;
export type UsedIds = string[];
export type UnavailableCount1 = number;
export type SessionId27 = string;
export type ModelId11 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type TimeoutSeconds1 = number;
/**
 * 路径与已有标识二选一，禁止同时提交两种定位方式。
 *
 * Require either a path or an existing ID, never both.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "OpenProjectParams".
 */
export type OpenProjectParams = OpenProjectByPath | OpenProjectById;
export type Path4 = string;
export type ProjectId15 = string;
export type Url1 = string;
export type Code8 = string;
export type Message6 = string;
export type Remediation3 = string;
export type CreatedAt7 = string;
export type DeliveredRunId = string | null;
export type MessageId1 = string;
export type Content1 = string;
export type OperationId9 = string;
export type SourceSessionId6 = string;
export type TargetSessionId5 = string;
export type TaskId6 = string;
export type Messages = PeerMessage[];
export type NextCursor3 = string | null;
export type ActiveCount = number;
export type NextCursor4 = string | null;
export type Programs1 = ProgramSummary[];
export type UnavailableCount2 = number;
export type ProgramId2 = string;
export type ArchiveId = string | null;
export type ArchiveRead = string | null;
export type NextSeq = number;
export type Seq3 = number;
export type Stream = "stdout" | "stderr";
export type Text3 = string;
export type Output = OutputChunk[];
export type Truncated = boolean;
export type Path5 = string;
export type ProjectId16 = string;
export type EnvironmentId5 = string;
export type ExpectedRevision4 = number;
export type ProjectId17 = string | null;
export type Jsonrpc = "2.0";
export type Method3 = string;
export type Id = string;
export type Jsonrpc1 = "2.0";
export type Method4 = string;
/**
 * 成功与失败响应的严格联合，不接受混合结构。
 *
 * Strict union of success and failure responses, rejecting mixed envelopes.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "RpcResponse".
 */
export type RpcResponse = RpcSuccess | RpcFailure;
export type Id1 = string;
export type Jsonrpc2 = "2.0";
export type Code9 = number;
export type Message7 = string;
export type Id2 = string | null;
export type Jsonrpc3 = "2.0";
export type Definition1 = SystemEnvironment | PythonEnvironment | CondaEnvironment | UvEnvironment;
export type EnvironmentId6 = string | null;
export type ExpectedRevision5 = number;
export type Name3 = string;
export type ProjectId18 = string | null;
export type ExpectedRevision6 = number;
export type ProjectId19 = string | null;
export type Category2 = string;
export type Content2 = string;
export type Enabled4 = boolean;
export type Pinned1 = boolean;
export type RelatedIds1 = string[];
export type Scope11 = "project" | "user";
export type SourceIds2 = string[];
export type Stale1 = boolean;
export type Subjects1 = string[];
export type Supersedes1 = string[];
export type Tags1 = string[];
export type Title6 = string;
export type ValidFrom1 = string | null;
export type ValidUntil1 = string | null;
export type MemoryId2 = string | null;
export type SessionId28 = string;
export type ModelId12 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type OperationId10 = string;
export type SessionId29 = string;
export type Jsonrpc4 = "2.0";
export type Method5 = "session.event";
export type DeltaIndex = number;
export type Kind14 = "changed" | "text.delta" | "reasoning.delta" | "model.progress" | "resync";
export type MessageId2 = string | null;
export type ProcessEpoch = string;
export type RunId7 = string | null;
export type Seq4 = number;
export type SessionId30 = string;
export type Text4 = string;
export type ActiveSessionIds = string[];
export type NextCursor5 = string | null;
export type Sessions1 = SessionSummary[];
export type UnavailableCount3 = number;
export type SessionId31 = string;
export type BeforeSeq4 = number | null;
export type DeltaIndex1 = number;
export type Name4 = string;
export type ToolCallId3 = string;
export type Kind15 =
  | "user"
  | "assistant"
  | "tool.started"
  | "tool.completed"
  | "tool.skipped"
  | "run.finished"
  | "goal.event"
  | "collaboration.request"
  | "session.recovered";
export type MessageId3 = string | null;
export type ModelId13 = ("glm-5.3-flash" | "deepseek-v4.1-flash") | null;
export type Reasoning = string;
export type Content3 = string;
export type IsError = boolean;
export type ToolCallId4 = string;
export type RunId8 = string | null;
export type Seq5 = number;
export type Text5 = string;
export type WebResult = WebSearchResult | WebPageResult | null;
export type ActualQueries = string[];
export type ArchiveId1 = string | null;
export type Kind16 = "web.search";
export type ModelId14 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Query2 = string;
export type RetrievedAt = string;
export type SearchUses = number;
export type Excerpt = string;
export type PageAge = string | null;
export type Title7 = string;
export type Url2 = string;
export type Sources = WebSource[];
export type Summary2 = string;
export type Truncated1 = boolean;
export type ArchiveId2 = string | null;
export type Content4 = string;
export type ContentType = string;
export type DownloadTruncated = boolean;
export type Kind17 = "web.page";
export type NextOffset2 = number | null;
export type Offset3 = number;
export type Redirects = string[];
export type RequestedUrl = string;
export type RetrievedAt1 = string;
export type StatusCode = number | null;
export type Title8 = string;
export type Truncated2 = boolean;
export type Url3 = string;
export type Entries1 = ChatEntry[];
export type ProcessEpoch1 = string;
export type StreamMessageId = string | null;
export type StreamModelId = ("glm-5.3-flash" | "deepseek-v4.1-flash") | null;
export type StreamReasoning = string;
export type StreamText = string;
export type Watermark = number;
export type Mode10 = "normal" | "plan";
export type OperationId11 = string;
export type PlanDocument1 = string | null;
export type Prompt1 = string;
export type SessionId32 = string;
export type ConfigPath1 = string;
export type CurrentDataDir = string;
export type DataDir1 = string;
export type ProjectDir = string;
export type DataDir2 = string;
export type ProjectDir1 = string;
export type NextCursor6 = string | null;
export type ProjectId20 = string;
export type Revision5 = number;
export type Status14 = "active" | "completed" | "archived";
export type TaskId7 = string;
export type Title9 = string;
export type Tasks = TaskSummary[];
export type UnavailableCount4 = number;
export type TaskId8 = string;
export type ModelId15 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type ExpectedRevision7 = number;
export type OperationId12 = string;
export type TaskId9 = string;
export type Action4 = "stop" | "continue";
export type Prompt2 = string;
export type SessionId33 = string;
export type WorkerId = string;
export type ActiveSeconds1 = number;
export type ContextMode1 = "isolated" | "inherit";
export type Mode11 = "normal" | "plan";
export type Objective4 = string;
export type Role3 = "implement" | "research";
export type Scope12 = string;
export type Code10 = string | null;
export type CreatedAt8 = string;
export type GoalId6 = string | null;
export type ModelId16 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type OwnerRunId = string;
export type OwnerSessionId = string;
export type PendingMessages = string[];
export type Requests6 = number;
export type Result1 = string;
export type RunId9 = string | null;
export type SessionId34 = string;
export type Status15 = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Tools2 = number;
export type UpdatedAt6 = string;
export type WorkerId1 = string;
export type Workers = WorkerRecord[];
export type SessionId35 = string;

export interface ProtocolV4 {
  ActiveRunResult: ActiveRunResult;
  AppInfo: AppInfo;
  ArrangeSessionWorkParams: ArrangeSessionWorkParams;
  AssignSessionParams: AssignSessionParams;
  BindEnvironmentParams: BindEnvironmentParams;
  CancelRunParams: CancelRunParams;
  ChangePage: ChangePage;
  ChangeView: ChangeView;
  ChooseDirectoryParams: ChooseDirectoryParams;
  ChooseEnvironmentPathParams: ChooseEnvironmentPathParams;
  CollaborationHistoryParams: CollaborationHistoryParams;
  CollaborationLink: CollaborationLink;
  CollaborationPage: CollaborationPage;
  CollaborationPageParams: CollaborationPageParams;
  CollaborationRequest: CollaborationRequest;
  CollaborationRequestParams: CollaborationRequestParams;
  ConfigureContextParams: ConfigureContextParams;
  ConfigureMemoryParams: ConfigureMemoryParams;
  ConfigureWorkersParams: ConfigureWorkersParams;
  ConnectSessionsParams: ConnectSessionsParams;
  ConnectionProbeParams: ConnectionProbeParams;
  ConnectionSettings: ConnectionSettings;
  ConnectionStatus: ConnectionStatus;
  ContextParams: ContextParams;
  ContextView: ContextView;
  ControlCollaborationParams: ControlCollaborationParams;
  ControlGoalParams: ControlGoalParams;
  CreateGoalParams: CreateGoalParams;
  CreateSessionParams: CreateSessionParams;
  CreateTaskParams: CreateTaskParams;
  CreateTaskResult: CreateTaskResult;
  CredentialInfo: CredentialInfo;
  DiagnosticCheck: DiagnosticCheck;
  DiagnosticReport: DiagnosticReport;
  DiagnosticsParams: DiagnosticsParams;
  DirectorySelection: DirectorySelection;
  EmptyParams: EmptyParams;
  EnvironmentCatalog: EnvironmentCatalog;
  EnvironmentParams: EnvironmentParams;
  EnvironmentProjectParams: EnvironmentProjectParams;
  ErrorData: ErrorData;
  ExecutionSettings: ExecutionSettings;
  ExecutionStatus: ExecutionStatus;
  ExportParams: ExportParams;
  ExportResult: ExportResult;
  ForgetMemoryParams: ForgetMemoryParams;
  GetChangeParams: GetChangeParams;
  GetProgramParams: GetProgramParams;
  GetSessionParams: GetSessionParams;
  GoalPage: GoalPage;
  GoalView: GoalView;
  HistoryPage: HistoryPage;
  HistoryParams: HistoryParams;
  InitializeParams: InitializeParams;
  InitializeResult: InitializeResult;
  ListChangesParams: ListChangesParams;
  ListGoalsParams: ListGoalsParams;
  ListMemoryParams: ListMemoryParams;
  ListProgramsParams: ListProgramsParams;
  ListSessionsParams: ListSessionsParams;
  MaintainMemoryParams: MaintainMemoryParams;
  MemoryPage: MemoryPage;
  MemoryParams: MemoryParams;
  ModelConnectionProbeParams: ModelConnectionProbeParams;
  OpenProjectParams: OpenProjectParams;
  OpenWebUrlParams: OpenWebUrlParams;
  OperationError: OperationError;
  PeerMessage: PeerMessage;
  PeerMessagePage: PeerMessagePage;
  ProgramPage: ProgramPage;
  ProgramParams: ProgramParams;
  ProgramView: ProgramView;
  ProjectSummary: ProjectSummary;
  ProjectsView: ProjectsView;
  PublicConfig: PublicConfig;
  RelocateProjectParams: RelocateProjectParams;
  RemoveEnvironmentParams: RemoveEnvironmentParams;
  RpcNotification: RpcNotification;
  RpcRequest: RpcRequest;
  RpcResponse: RpcResponse;
  RunLimits: RunLimits;
  SaveEnvironmentParams: SaveEnvironmentParams;
  SaveExecutionSettings: SaveExecutionSettings;
  SaveMemoryParams: SaveMemoryParams;
  SelectSessionModelParams: SelectSessionModelParams;
  SendMessageParams: SendMessageParams;
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
  TaskFields: TaskFields;
  TaskPage: TaskPage;
  TaskParams: TaskParams;
  TaskView: TaskView;
  UpdateConfigParams: UpdateConfigParams;
  UpdateTaskParams: UpdateTaskParams;
  WebPageResult: WebPageResult;
  WebSearchResult: WebSearchResult;
  WorkerControlParams: WorkerControlParams;
  WorkerPage: WorkerPage;
  WorkerSessionParams: WorkerSessionParams;
}
/**
 * 各会话的活动运行列表，切换视图仍可逐项停止。
 *
 * Active runs per session remain independently stoppable across views.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ActiveRunResult".
 */
export interface ActiveRunResult {
  sessions: Sessions;
}
/**
 * 会话列表条目，不泄露原生模型状态。
 *
 * Session list entry without native provider state.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SessionSummary".
 */
export interface SessionSummary {
  can_continue: CanContinue;
  created_at: CreatedAt;
  issue: Issue;
  mode?: Mode;
  model_id: ModelId;
  project_id: ProjectId;
  role?: Role;
  run: RunView | null;
  scope?: Scope;
  session_id: SessionId;
  task_id?: TaskId;
  title: Title;
  updated_at: UpdatedAt;
}
/**
 * 公开运行计数；未知用量与未结束清理明确呈现。
 *
 * Public counts and explicit unknown usage.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "RunView".
 */
export interface RunView {
  code: Code;
  goal_id?: GoalId;
  goal_role?: GoalRole;
  input_tokens: InputTokens;
  limits: RunLimits;
  message: Message;
  method?: Method;
  method_version?: MethodVersion;
  mode?: Mode1;
  output_tokens: OutputTokens;
  plan_document?: PlanDocument;
  progress_sync?: ProgressSync;
  requests: Requests;
  run_id: RunId;
  status: Status;
  tools: Tools;
  waited_seconds?: WaitedSeconds;
  waiting_for?: WaitingFor;
  work_id?: WorkId;
}
/**
 * 受信设置中的可调整限额，不代表模型能力。 Adjustable limits, not model capabilities.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "AppInfo".
 */
export interface AppInfo {
  app_version: AppVersion;
  name: Name;
  protocol_version: ProtocolVersion;
  stage: Stage;
}
/**
 * 用户主动交接 / 审查，停止身份只用于明确移交的工作。
 *
 * User-initiated handoff or review, with stop identities limited to transferred work.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ArrangeSessionWorkParams".
 */
export interface ArrangeSessionWorkParams {
  context_mode?: ContextMode;
  kind: Kind;
  notes?: Notes;
  objective: Objective;
  operation_id: OperationId;
  source_session_id: SourceSessionId;
  target_session_id: TargetSessionId;
  transfer_goal_id?: TransferGoalId;
  transfer_run_id?: TransferRunId;
}
/**
 * 用户设置会话归属与分工；不授予跨会话访问权限。
 *
 * User-defined membership, not history access grants.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "AssignSessionParams".
 */
export interface AssignSessionParams {
  operation_id: OperationId1;
  role?: Role1;
  scope?: Scope1;
  session_id: SessionId1;
  task_id: TaskId1;
}
/**
 * 用户保存项目默认环境与执行方式。
 *
 * Persist the user's default environment and execution mode.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "BindEnvironmentParams".
 */
export interface BindEnvironmentParams {
  environment_id: EnvironmentId;
  expected_revision: ExpectedRevision;
  mode: Mode2;
  project_id: ProjectId1;
  trusted?: Trusted;
}
/**
 * 只停止指定运行，不隐式停止其他任务。
 *
 * Cancel the specified run only.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CancelRunParams".
 */
export interface CancelRunParams {
  run_id: RunId1;
}
/**
 * 差异元数据页，损坏记录明确计数。 Metadata page with explicit unreadable-record count.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ChangePage".
 */
export interface ChangePage {
  changes: Changes;
  next_cursor: NextCursor;
  unavailable_count: UnavailableCount;
}
/**
 * 一次写入的来源与结果，准备状态不等于成功。
 *
 * Provenance and outcome; prepared is not success.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ChangeSummary".
 */
export interface ChangeSummary {
  after_sha256: AfterSha256;
  before_sha256: BeforeSha256;
  change_id: ChangeId;
  created_at: CreatedAt1;
  error?: Error;
  operation: Operation;
  path: Path;
  project_id: ProjectId2;
  run_id: RunId2;
  session_id: SessionId2;
  status: Status1;
  tool_call_id: ToolCallId;
}
/**
 * 历史修改的有界 diff；不代表当前磁盘内容。 Bounded historical diff, not live disk contents.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ChangeView".
 */
export interface ChangeView {
  diff: Diff;
  next_offset: NextOffset;
  summary: ChangeSummary;
}
/**
 * 限定受信目录选择器的用途，不接受任意系统操作。
 *
 * Limit the trusted directory picker to its declared purpose.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ChooseDirectoryParams".
 */
export interface ChooseDirectoryParams {
  kind: Kind1;
}
/**
 * 选择已有环境入口。
 *
 * Select existing environment paths through a trusted picker.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ChooseEnvironmentPathParams".
 */
export interface ChooseEnvironmentPathParams {
  kind: Kind2;
}
/**
 * 按约定读取对方公开历史，保留分页与来源。
 *
 * Read permitted public history with pagination and provenance.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CollaborationHistoryParams".
 */
export interface CollaborationHistoryParams {
  before_seq?: BeforeSeq;
  limit?: Limit;
  source_session_id: SourceSessionId1;
  target_session_id: TargetSessionId1;
}
/**
 * 会话访问约定，保存任务归属与修改时间。
 *
 * A session access agreement with task ownership and modification time.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CollaborationLink".
 */
export interface CollaborationLink {
  enabled?: Enabled;
  mode?: Mode3;
  scope: Scope2;
  source_session_id: SourceSessionId2;
  target_session_id: TargetSessionId2;
  task_id: TaskId2;
  updated_at: UpdatedAt1;
}
/**
 * 双方可见状态；约定方向不因展示而反转。
 *
 * Status visible to both parties without reversing access grants.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CollaborationPage".
 */
export interface CollaborationPage {
  error?: Error1;
  links: Links;
  next_cursor: NextCursor1;
  requests: Requests1;
}
/**
 * 请求生命周期与精确运行来源，完成结果从运行事实读取。
 *
 * Request lifecycle and exact run provenance; results come from durable run facts.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CollaborationRequest".
 */
export interface CollaborationRequest {
  arrangement?: ArrangeSessionWorkParams | null;
  brief?: SessionWorkBrief | null;
  created_at: CreatedAt3;
  params: CollaborationRequestParams;
  parent_request_id?: ParentRequestId;
  reason?: Reason;
  request_id: RequestId;
  result?: Result;
  result_seq?: ResultSeq;
  schema_version?: SchemaVersion;
  scope: Scope4;
  source_run_id?: SourceRunId;
  status: Status7;
  target_run_id?: TargetRunId;
  task_id: TaskId4;
  updated_at: UpdatedAt4;
}
/**
 * 从已保存事实生成简报；成果快照不是当前磁盘内容。
 *
 * A brief from durable facts; artifact snapshots are not current disk contents.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SessionWorkBrief".
 */
export interface SessionWorkBrief {
  captured_at: CapturedAt;
  changes: ChangePage;
  inherited_context?: InheritedContext;
  source_goal: GoalView | null;
  source_run: RunView | null;
  source_session_id: SourceSessionId3;
  source_watermark: SourceWatermark;
  task: TaskView;
}
/**
 * 目标状态和累计用量，不以完成 Goal 自动完成 Task。
 *
 * Goal state and cumulative usage, independent of task completion.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GoalView".
 */
export interface GoalView {
  budget: GoalBudget;
  code: Code1;
  criteria: Criteria;
  goal_id: GoalId1;
  last_report?: WorkReport | null;
  last_result_seq?: LastResultSeq;
  objective: Objective1;
  pending_inputs?: PendingInputs;
  question?: HumanQuestion | null;
  revision: Revision;
  session_id: SessionId4;
  status: Status5;
  usage: GoalUsage;
}
/**
 * 累计预算可留空，Run 仍使用自身限额，不引入固定续跑次数。
 *
 * Optional cumulative budgets coexist with run limits without a fixed continuation count.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GoalBudget".
 */
export interface GoalBudget {
  max_active_seconds?: MaxActiveSeconds;
  max_requests?: MaxRequests1;
  max_tools?: MaxTools1;
}
/**
 * 用户确定的完成条件；报告可按需引用，不能改写条件。
 *
 * A user-defined criterion optionally referenced, never rewritten, by model results.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GoalCriterion".
 */
export interface GoalCriterion {
  criterion_id: CriterionId;
  description: Description;
}
/**
 * 一次完整工作运行的结构化结果；不会自行改变用户目标或任务状态。
 *
 * A structured work-run result that never changes the user's objective or task status.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WorkReport".
 */
export interface WorkReport {
  criteria?: Criteria1;
  decisions?: Decisions;
  next_action?: NextAction;
  next_work_id?: NextWorkId;
  outcome: Outcome;
  question?: HumanQuestion | null;
  summary: Summary;
  work_items?: WorkItems;
}
/**
 * 模型逐项判断，明确未满足、未验证与等待用户验收。
 *
 * Per-criterion model judgments distinguish unmet, unchecked and user acceptance.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CriterionResult".
 */
export interface CriterionResult {
  criterion_id: CriterionId1;
  evidence?: Evidence;
  explanation: Explanation;
  status: Status2;
}
/**
 * 模型声明的来源类别与用途，不等同于宿主验证通过。
 *
 * Model-declared source kinds and uses are not host-verified success.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "EvidenceRef".
 */
export interface EvidenceRef {
  expectation?: Expectation;
  kind: Kind3;
  run_id: RunId3;
  seq: Seq;
  session_id: SessionId3;
}
/**
 * 本任务内需共享的决定，明确区分用户要求和建议。
 *
 * Task-local decisions distinguish user direction from proposals.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SharedDecision".
 */
export interface SharedDecision {
  status?: Status3;
  text: Text;
}
/**
 * 需用户答复的具体问题及影响，不把闲聊或超时当作回答。
 *
 * A specific question and its impact, never answered by chatter or elapsed time.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "HumanQuestion".
 */
export interface HumanQuestion {
  impact: Impact;
  options?: Options;
  question: Question;
  question_id: QuestionId;
}
/**
 * 一个有意义的工作单元；依赖和反馈不等同于单个工具调用。
 *
 * A meaningful work unit with dependencies and feedback, not an individual tool call.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WorkItem".
 */
export interface WorkItem {
  depends_on?: DependsOn;
  evidence?: Evidence1;
  feedback_from?: FeedbackFrom;
  method?: Method1;
  scope: Scope3;
  status: Status4;
  title: Title1;
  work_id: WorkId1;
}
/**
 * 尚未开始回答的输入，不把排队显示成已执行。
 *
 * Input still waiting for an answer, never displayed as already executed.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GoalInputView".
 */
export interface GoalInputView {
  operation_id: OperationId2;
  prompt: Prompt;
}
/**
 * 从真实开始事实累计；未知耗时单独预留，不计离线时长。
 *
 * Count durable starts; reserve unknown durations separately without charging offline time.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GoalUsage".
 */
export interface GoalUsage {
  active_seconds?: ActiveSeconds;
  input_tokens?: InputTokens1;
  output_tokens?: OutputTokens1;
  requests?: Requests2;
  reserved_seconds?: ReservedSeconds;
  tools?: Tools1;
  uncertain_run_ids?: UncertainRunIds;
}
/**
 * 任务当前版本与可追溯来源。 Current task revision with traceable provenance.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "TaskView".
 */
export interface TaskView {
  created_at: CreatedAt2;
  fields: TaskFields;
  initial_model_id: InitialModelId;
  initial_session_id: InitialSessionId;
  project_id: ProjectId3;
  revision: Revision1;
  source: Source;
  task_id: TaskId3;
  updated_at: UpdatedAt2;
  work?: TaskWork;
}
/**
 * 用户维护的共同信息；成果字段仅表示用户记录。
 *
 * User-maintained shared facts and artifact notes.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "TaskFields".
 */
export interface TaskFields {
  artifacts?: Artifacts;
  constraints?: Constraints;
  decisions?: Decisions1;
  goal: Goal;
  progress?: Progress;
  status?: Status6;
  title: Title2;
  unresolved?: Unresolved;
}
/**
 * 任务当前工作图与最近一次报告，历史在任务版本日志保留。
 *
 * Current task work graph and latest report; task revisions preserve history.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "TaskWork".
 */
export interface TaskWork {
  decisions?: Decisions2;
  items?: Items;
  last_report?: WorkReport | null;
  members?: Members;
  source?: EventRef | null;
}
/**
 * 共同决定保留聊天来源，不覆盖用户手写字段。
 *
 * Shared decisions retain sources without replacing user fields.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SourcedDecision".
 */
export interface SourcedDecision {
  decision: SharedDecision;
  source: EventRef;
}
/**
 * 模型提供的可选会话引用；报告自身的来源由宿主另行记录。
 *
 * Optional model-supplied references; the host records the report's own provenance separately.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "EventRef".
 */
export interface EventRef {
  run_id: RunId4;
  seq: Seq1;
  session_id: SessionId5;
}
/**
 * 宿主附加来源，保留模型判断与事实出处的区别。
 *
 * Host-attached provenance distinguishes a model judgment from its source facts.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SourcedWorkItem".
 */
export interface SourcedWorkItem {
  item: WorkItem;
  source: EventRef;
}
/**
 * 各成员最新报告与宿主来源。
 *
 * Each member's latest report and host provenance.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "MemberProgress".
 */
export interface MemberProgress {
  report: WorkReport;
  source: EventRef;
  updated_at: UpdatedAt3;
}
/**
 * 明确的协作工作和返回要求，操作 ID 用于幂等投递。
 *
 * A bounded assignment and return requirements with an idempotent operation ID.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CollaborationRequestParams".
 */
export interface CollaborationRequestParams {
  expected_result?: ExpectedResult;
  inputs?: Inputs;
  mode?: Mode4;
  objective: Objective2;
  operation_id: OperationId3;
  source_session_id: SourceSessionId4;
  target_session_id: TargetSessionId3;
}
/**
 * 本会话的约定和请求分页。
 *
 * Page this session's agreements and requests.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CollaborationPageParams".
 */
export interface CollaborationPageParams {
  cursor?: Cursor;
  limit?: Limit1;
  session_id: SessionId6;
}
/**
 * 保存后续请求采用的整理设置。
 *
 * Save compaction settings for subsequent requests.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ConfigureContextParams".
 */
export interface ConfigureContextParams {
  session_id: SessionId7;
  settings: ContextSettings;
}
/**
 * 绝对 token 整理预算；与模型容量及生成额度分别管理。
 *
 * Absolute token policy, separate from model capacity and generation allowance.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ContextSettings".
 */
export interface ContextSettings {
  auto_trigger_tokens?: AutoTriggerTokens;
  automatic?: Automatic;
  keep_recent_tokens?: KeepRecentTokens;
  summary_output_tokens?: SummaryOutputTokens;
  summary_target_tokens?: SummaryTargetTokens;
  tool_result_preview_tokens?: ToolResultPreviewTokens;
}
/**
 * 保存会话的使用、贡献和实验选项。
 *
 * Save session use, contribution and experiment settings.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ConfigureMemoryParams".
 */
export interface ConfigureMemoryParams {
  session_id: SessionId8;
  settings: MemorySettings;
}
/**
 * 使用和贡献分别控制，实验默认关闭。
 *
 * Independent use/contribution controls; experiments start disabled.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "MemorySettings".
 */
export interface MemorySettings {
  associations?: Associations;
  auto_pages?: AutoPages;
  automatic?: Automatic1;
  contribute?: Contribute;
  maintenance_input_bytes?: MaintenanceInputBytes;
  maintenance_requests?: MaintenanceRequests;
  recall_chars?: RecallChars;
  recall_limit?: RecallLimit;
  use?: Use;
}
/**
 * 保存下一次委派的能力开关。
 *
 * Save delegation settings for subsequent assignments.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ConfigureWorkersParams".
 */
export interface ConfigureWorkersParams {
  session_id: SessionId9;
  settings: WorkerSettings;
}
/**
 * 默认关闭；并发是可调资源配置。
 *
 * Disabled by default; concurrency is an adjustable resource setting.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WorkerSettings".
 */
export interface WorkerSettings {
  concurrency?: Concurrency;
  enabled?: Enabled1;
}
/**
 * 用户指定定向协作范围；禁用只影响后续访问。
 *
 * A user-defined directional agreement; disabling affects subsequent access.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ConnectSessionsParams".
 */
export interface ConnectSessionsParams {
  enabled?: Enabled2;
  mode?: Mode5;
  scope: Scope5;
  source_session_id: SourceSessionId5;
  target_session_id: TargetSessionId4;
}
/**
 * 每次手动探测明确指定总等待时间。 Specify the total timeout for one manual probe.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ConnectionProbeParams".
 */
export interface ConnectionProbeParams {
  timeout_seconds: TimeoutSeconds;
}
/**
 * 持久化复用偏好与手动探测等待时间。 Persist reuse preference and manual probe timeout.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ConnectionObservation".
 */
export interface ConnectionObservation {
  code: Code2;
  finished_at: FinishedAt;
  http_status: HttpStatus;
  model_id?: ModelId1;
  models_confirmed: ModelsConfirmed;
  progress: ModelProgress;
}
/**
 * 请求阶段与单调时钟耗时，不包含网络原文。 Request phases and timings without raw payloads.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ModelProgress".
 */
export interface ModelProgress {
  connect_ms?: ConnectMs;
  elapsed_ms: ElapsedMs;
  first_event_ms?: FirstEventMs;
  first_text_ms?: FirstTextMs;
  last_data_ms?: LastDataMs;
  phase: Phase;
  received_bytes?: ReceivedBytes;
  response_complete?: ResponseComplete;
  response_headers_ms?: ResponseHeadersMs;
  tls_ms?: TlsMs;
}
/**
 * 按模型保存正在测试的进度和最近结果；不代表独立套接字。
 *
 * Per-model test progress and last result, not a separate physical connection.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ModelConnectionResult".
 */
export interface ModelConnectionResult {
  code: Code3;
  finished_at: FinishedAt1;
  message: Message1;
  progress: ModelProgress;
  remediation: Remediation;
  usage: TokenUsage | null;
}
/**
 * 服务实际返回的用量；未知保留 null。 Reported usage; unknown remains null.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "TokenUsage".
 */
export interface TokenUsage {
  input_tokens: InputTokens2;
  output_tokens: OutputTokens2;
}
/**
 * 定位本会话的窗口。
 *
 * Identify a session window.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ContextParams".
 */
export interface ContextParams {
  session_id: SessionId10;
}
/**
 * 输入区的 token 观察、字节处理量与整理事实。
 *
 * Token observations, byte processing sizes and compaction facts for the composer.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ContextView".
 */
export interface ContextView {
  checkpoint: Checkpoint | null;
  estimate_basis?: EstimateBasis;
  estimated_history_tokens?: EstimatedHistoryTokens;
  estimated_input_tokens?: EstimatedInputTokens;
  history_through_seq: HistoryThroughSeq;
  job: ContextJob | null;
  last_request?: ContextRequest | null;
  limit_bytes: LimitBytes;
  measurement?: Measurement;
  migrated_from_bytes?: MigratedFromBytes;
  raw_bytes: RawBytes;
  session_id: SessionId11;
  settings: ContextSettings;
  tokens: ContextTokens;
  totals?: UsageSummary;
  trigger_tokens?: TriggerTokens;
  window_bytes: WindowBytes;
}
/**
 * 完整保存的派生摘要，原始事件保持原样。
 *
 * Durable derived summary; raw events stay intact.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "Checkpoint".
 */
export interface Checkpoint {
  checkpoint_id: CheckpointId;
  created_at: CreatedAt4;
  model_id: ModelId3;
  parent_id: ParentId;
  text: Text1;
  through_seq: ThroughSeq;
  usage: TokenUsage;
}
/**
 * 辅助整理的真实状态和累计用量。
 *
 * Actual maintenance state and cumulative usage.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ContextJob".
 */
export interface ContextJob {
  compression_applied?: CompressionApplied;
  finish_reason?: FinishReason;
  finished_at?: FinishedAt2;
  history_after_bytes?: HistoryAfterBytes;
  history_after_tokens?: HistoryAfterTokens;
  history_before_bytes?: HistoryBeforeBytes;
  history_before_tokens?: HistoryBeforeTokens;
  job_id: JobId;
  message?: Message2;
  mode?: Mode6;
  model_id: ModelId4;
  outcome?: Outcome1;
  output_token_limit?: OutputTokenLimit;
  policy?: ContextSettings | null;
  requests?: Requests3;
  retained_tokens?: RetainedTokens;
  run_id: RunId5;
  started_at: StartedAt;
  status: Status8;
  through_seq?: ThroughSeq1;
  usage?: TokenUsage;
}
/**
 * 最近请求的固定材料事实，后续设置不会改写。
 *
 * Fixed facts for the latest request, unaffected by later settings.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ContextRequest".
 */
export interface ContextRequest {
  at: At;
  manifest: ContextManifest;
  message_id: MessageId;
  model_id: ModelId5;
}
/**
 * 请求边界保存实际材料与单独标注的 token 估计。
 *
 * Persist actual materials and separately labelled token estimates at the request boundary.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ContextManifest".
 */
export interface ContextManifest {
  estimated_fixed_tokens?: EstimatedFixedTokens;
  estimated_input_tokens?: EstimatedInputTokens1;
  materials?: Materials;
  message_count: MessageCount;
  request_bytes: RequestBytes;
  tool_names: ToolNames;
}
/**
 * 实际采用的材料来源与有界预览，不复制原生对话。
 *
 * Adopted source references and bounded previews, never native conversation state.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ContextMaterial".
 */
export interface ContextMaterial {
  form: Form;
  kind: Kind4;
  preview?: Preview;
  preview_complete?: PreviewComplete;
  read_arguments?: JsonObject;
  read_tool?: ReadTool;
  reason: Reason1;
  revision?: Revision2;
  source_id?: SourceId;
  title: Title3;
}
/**
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "JsonObject".
 */
export interface JsonObject {
  [k: string]: JsonValue;
}
/**
 * 单次主请求的实际输入用量与独立的模型目录窗口。
 *
 * Reported input for one main request, alongside the separate catalog window.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ContextTokens".
 */
export interface ContextTokens {
  input_tokens?: InputTokens3;
  model_id: ModelId6;
  status?: Status9;
  window_source: WindowSource;
  window_tokens: WindowTokens;
}
/**
 * 已报告 token 与未知用量分别计数。
 *
 * Separate reported tokens from unknown usage.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "UsageSummary".
 */
export interface UsageSummary {
  reported_input_tokens?: ReportedInputTokens;
  reported_output_tokens?: ReportedOutputTokens;
  requests?: Requests4;
  unavailable_jobs?: UnavailableJobs;
  unknown_jobs?: UnknownJobs;
}
/**
 * 用户取消请求或明确恢复尚未启动的队列项。
 *
 * Cancel a request or explicitly release an unstarted held item.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ControlCollaborationParams".
 */
export interface ControlCollaborationParams {
  action: Action;
  request_id: RequestId1;
}
/**
 * 无附带预算或答复的状态控制。 State controls without hidden budgets or answers.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GoalStateControl".
 */
export interface GoalStateControl {
  action: Action1;
  expected_revision: ExpectedRevision1;
  goal_id: GoalId2;
  operation_id: OperationId4;
  session_id: SessionId12;
}
/**
 * 明确替换累计预算，不自动接续。 Explicitly replace cumulative budgets without resuming.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GoalBudgetControl".
 */
export interface GoalBudgetControl {
  action: Action2;
  budget: GoalBudget;
  expected_revision: ExpectedRevision2;
  goal_id: GoalId3;
  operation_id: OperationId5;
  session_id: SessionId13;
}
/**
 * 只回答指定 HITL 问题，不把普通问题当成答复。
 *
 * Answer only the named HITL question, never interpreting ordinary chatter as an answer.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GoalAnswerControl".
 */
export interface GoalAnswerControl {
  action: Action3;
  answer: Answer;
  expected_revision: ExpectedRevision3;
  goal_id: GoalId4;
  operation_id: OperationId6;
  question_id: QuestionId1;
  session_id: SessionId14;
}
/**
 * 由用户在既有会话创建目标，不创建正式会话。
 *
 * Create a user goal in an existing session without creating a formal session.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CreateGoalParams".
 */
export interface CreateGoalParams {
  budget: GoalBudget;
  criteria: Criteria2;
  goal_id: GoalId5;
  limits?: RunLimits | null;
  method?: Method2;
  objective: Objective3;
  session_id: SessionId15;
}
/**
 * 选择项目与模型，不发起运行。
 *
 * Select project and model without starting a run.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CreateSessionParams".
 */
export interface CreateSessionParams {
  model_id: ModelId7;
  operation_id?: OperationId7;
  project_id: ProjectId4;
  role?: Role2;
  scope?: Scope6;
  task_id?: TaskId5;
}
/**
 * 一次创建操作同时预留首会话身份，重试不重复创建。
 *
 * Reserve the first session for idempotent creation.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CreateTaskParams".
 */
export interface CreateTaskParams {
  fields: TaskFields;
  model_id: ModelId8;
  operation_id: OperationId8;
  project_id: ProjectId5;
}
/**
 * 分开表达任务保存与首会话创建，失败可显式接续。
 *
 * Distinguish task saving from session creation.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CreateTaskResult".
 */
export interface CreateTaskResult {
  session: SessionSummary | null;
  session_error: SessionError;
  task: TaskView;
}
/**
 * 仅公开凭据来源与存在状态；null 表示读取受限。
 *
 * Expose only credential source and presence; null means access was restricted.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CredentialInfo".
 */
export interface CredentialInfo {
  env_var: EnvVar;
  present: Present;
  source: Source1;
}
/**
 * 单项诊断的公开结论、影响与脱敏证据。
 *
 * Public outcome, impact and sanitized evidence for one diagnostic check.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "DiagnosticCheck".
 */
export interface DiagnosticCheck {
  blocking: Blocking;
  check_id: CheckId;
  code: Code4;
  evidence: Evidence2;
  remediation: Remediation1;
  status: Status10;
  summary: Summary1;
}
export interface Evidence2 {
  [k: string]: string | boolean | number | null;
}
/**
 * 区分凭据存在与目录可达；M0 尚未验证认证或真实工具回合。
 *
 * Separate key presence and catalog access from auth and tool calls, unverified in M0.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
  mode: Mode7;
  report_schema_version: ReportSchemaVersion;
  tool_roundtrip_verified: ToolRoundtripVerified;
}
/**
 * 显式声明额外诊断选项，避免隐式联网或写入。
 *
 * Declare optional probes explicitly to prevent implicit networking or writes.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "DirectorySelection".
 */
export interface DirectorySelection {
  path: Path1;
}
/**
 * 表示不接受参数的方法，拒绝任何额外字段。
 *
 * Represent parameterless methods and reject every extra field.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "EmptyParams".
 */
export interface EmptyParams {}
/**
 * 设置页的可公开环境与当前项目绑定。
 *
 * Public environment settings and current project binding.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "EnvironmentCatalog".
 */
export interface EnvironmentCatalog {
  binding: ProjectExecution | null;
  environments: Environments;
  revision: Revision3;
  settings: ExecutionSettings;
}
/**
 * 项目唯一默认环境和后续执行方式。
 *
 * A project's default environment and future execution policy.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ProjectExecution".
 */
export interface ProjectExecution {
  environment_id: EnvironmentId1;
  mode: Mode8;
  project_id: ProjectId6;
  trusted?: Trusted1;
}
/**
 * 登记事实与当前路径可用性，未经探测不冒充版本已验证。
 *
 * Registration and live path availability, without claiming unperformed probes.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "EnvironmentView".
 */
export interface EnvironmentView {
  available: Available;
  interpreter: Interpreter;
  issue: Issue1;
  launcher: Launcher;
  prefix: Prefix;
  record: EnvironmentRecord;
}
/**
 * 仅保存用户环境引用，不保存进程变量或凭据。
 *
 * Persist environment references, not env secrets.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "EnvironmentRecord".
 */
export interface EnvironmentRecord {
  definition: Definition;
  environment_id: EnvironmentId2;
  name: Name1;
  probe?: EnvironmentProbe | null;
}
/**
 * 用户显式选择已有本机工具，不虚构 Python 绑定。
 *
 * Explicit existing system-tool selection.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SystemEnvironment".
 */
export interface SystemEnvironment {
  kind: Kind5;
}
/**
 * 已有解释器，项目相对路径在启动时解析。
 *
 * Existing interpreter with launch-time project paths.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "PythonEnvironment".
 */
export interface PythonEnvironment {
  interpreter: Interpreter1;
  kind: Kind6;
  scope: Scope7;
}
/**
 * Conda 安装入口和明确 prefix，不默认使用 base。
 *
 * Explicit Conda launcher and environment prefix.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "CondaEnvironment".
 */
export interface CondaEnvironment {
  kind: Kind7;
  launcher: Launcher1;
  prefix: Prefix1;
  scope: Scope8;
}
/**
 * 登记 uv 与已有解释器，普通运行不自动同步依赖。
 *
 * Register uv and an existing interpreter.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "UvEnvironment".
 */
export interface UvEnvironment {
  interpreter: Interpreter2;
  kind: Kind8;
  launcher: Launcher2;
  scope: Scope9;
}
/**
 * 显式探测结果及其实际路径来源。
 *
 * Explicit probe evidence with its actual path context.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "EnvironmentProbe".
 */
export interface EnvironmentProbe {
  checked_at: CheckedAt1;
  code: Code5;
  interpreter: Interpreter3;
  launcher_version: LauncherVersion;
  message: Message3;
  project_id: ProjectId7;
  version: Version;
}
/**
 * 新启动程序采用的可调预算；持续服务不套用命令寿命。
 *
 * Adjustable launch budgets; retained services have no command-lifetime timeout.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ExecutionSettings".
 */
export interface ExecutionSettings {
  cleanup_timeout_seconds: CleanupTimeoutSeconds;
  command_timeout_seconds: CommandTimeoutSeconds;
  max_output_bytes: MaxOutputBytes;
  probe_timeout_seconds: ProbeTimeoutSeconds1;
  service_ready_timeout_seconds: ServiceReadyTimeoutSeconds;
}
/**
 * 指定已登记环境，不接受任意待执行命令。
 *
 * Identify a registered environment, not a command.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "EnvironmentParams".
 */
export interface EnvironmentParams {
  environment_id: EnvironmentId3;
  project_id: ProjectId8;
}
/**
 * 可选项目用于解析相对环境。
 *
 * Optional project context for relative environments.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "EnvironmentProjectParams".
 */
export interface EnvironmentProjectParams {
  project_id: ProjectId9;
}
/**
 * RPC 错误的稳定业务码与修复说明。
 *
 * Stable application error code and remediation inside an RPC error.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ErrorData".
 */
export interface ErrorData {
  code: Code6;
  remediation: Remediation2;
}
/**
 * 退出前展示实际持有的工作。
 *
 * Show owned work before application shutdown.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ExecutionStatus".
 */
export interface ExecutionStatus {
  probe_count: ProbeCount;
  programs: Programs;
}
/**
 * 实际程序身份、来源与结果，PID 仅展示而非恢复授权。
 *
 * Program identity and outcome; a saved PID is not authority to reclaim a process.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ProgramSummary".
 */
export interface ProgramSummary {
  code: Code7;
  command: Command;
  created_at: CreatedAt5;
  cwd: Cwd;
  dropped_bytes?: DroppedBytes;
  environment_id: EnvironmentId4;
  environment_name: EnvironmentName;
  environment_revision: EnvironmentRevision;
  exit_code: ExitCode;
  finished_at: FinishedAt3;
  http_status: HttpStatus1;
  kind: Kind11;
  message: Message4;
  mode?: Mode9;
  pid: Pid;
  program_id: ProgramId;
  project_id: ProjectId10;
  resolved_command: ResolvedCommand;
  retained: Retained;
  run_id: RunId6;
  session_id: SessionId16;
  status: Status11;
  tool_call_id?: ToolCallId1;
  url: Url;
}
/**
 * 程序和参数数组直接执行，不猜测 shell 转义。
 *
 * Execute an explicit program and argument array.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ProgramCommand".
 */
export interface ProgramCommand {
  arguments?: Arguments;
  kind: Kind9;
  program: Program;
}
/**
 * 用户任务中的显式 PowerShell 脚本，与普通 argv 区分。
 *
 * Explicit PowerShell, distinct from argv.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ShellCommand".
 */
export interface ShellCommand {
  kind: Kind10;
  script: Script;
}
/**
 * 限定导出的公开文档类型，内容由后端提供。
 *
 * Select a public export category whose content comes from the backend.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ExportParams".
 */
export interface ExportParams {
  kind: Kind12;
}
/**
 * 返回成功导出的文件位置；null 表示用户取消。
 *
 * Return the exported file location, or null when the user cancels.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ExportResult".
 */
export interface ExportResult {
  path: Path2;
}
/**
 * 删除条目正文而不删除聊天。
 *
 * Delete entry content, not conversation history.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ForgetMemoryParams".
 */
export interface ForgetMemoryParams {
  memory_id: MemoryId;
  session_id: SessionId17;
}
/**
 * 按成果身份与字符游标读取差异。 Read a change by identity and character cursor.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GetChangeParams".
 */
export interface GetChangeParams {
  change_id: ChangeId1;
  offset?: Offset;
  session_id: SessionId18;
}
/**
 * 从已看到的输出序号继续读取。
 *
 * Continue reading after the last observed output sequence.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GetProgramParams".
 */
export interface GetProgramParams {
  after_seq?: AfterSeq;
  program_id: ProgramId1;
}
/**
 * 显式历史页游标，null 取最近一页。
 *
 * Explicit history cursor; null loads the latest page.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GetSessionParams".
 */
export interface GetSessionParams {
  before_seq: BeforeSeq1;
  session_id: SessionId19;
}
/**
 * 按创建事实倒序分页，旧目标不被新目标覆盖。
 *
 * Page goals by descending creation sequence without overwriting older objectives.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "GoalPage".
 */
export interface GoalPage {
  before_seq: BeforeSeq2;
  goals: Goals;
}
/**
 * 可直接展开的材料索引及匹配数。
 *
 * Expandable material index and match count.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "HistoryPage".
 */
export interface HistoryPage {
  complete: Complete;
  items: Items1;
  match_unit?: MatchUnit;
  matches: Matches;
  next_after_seq: NextAfterSeq;
  through_seq: ThroughSeq2;
}
/**
 * 公开材料片段，保留原序号和续读位置。
 *
 * Public fragment with original sequence and continuation.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "HistoryItem".
 */
export interface HistoryItem {
  call_seq?: CallSeq;
  kind: Kind13;
  next_offset: NextOffset1;
  offset: Offset1;
  result_seq?: ResultSeq1;
  seq: Seq2;
  text: Text2;
  tool_call_id?: ToolCallId2;
  tool_name?: ToolName;
  total_chars: TotalChars;
}
/**
 * 桌面读取指定会话的历史。
 *
 * Read a selected session's history from the desktop.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "HistoryParams".
 */
export interface HistoryParams {
  after_seq?: AfterSeq1;
  artifact_id?: ArtifactId;
  entry_seq?: EntrySeq;
  include_lookup_results?: IncludeLookupResults;
  limit?: Limit2;
  max_chars?: MaxChars;
  offset?: Offset2;
  query?: Query;
  session_id: SessionId20;
  through_seq?: ThroughSeq3;
}
/**
 * 前端声明的兼容性信息；应用版本与协议版本分别处理。
 *
 * Client compatibility information, keeping app and protocol versions distinct.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "PublicConfig".
 */
export interface PublicConfig {
  allowed_models: AllowedModels;
  api: Api;
  base_url: BaseUrl;
  config_path: ConfigPath;
  credential: CredentialInfo;
  http: ConnectionSettings;
  model_id: ModelId9;
  model_source: ModelSource;
  provider: Provider;
  run: RunLimits;
}
/**
 * 同时返回当前项目与最近记录，允许初次启动为空。
 *
 * Return active and recent projects, allowing an empty first-launch state.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ProjectSummary".
 */
export interface ProjectSummary {
  available: Available1;
  canonical_path: CanonicalPath;
  last_opened_at: LastOpenedAt;
  name: Name2;
  path: Path3;
  project_id: ProjectId11;
  unavailable_code: UnavailableCode;
}
/**
 * 展示实际数据根、配置来源和存储可用状态。
 *
 * Expose the effective data root, its source and storage availability.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "StorageInfo".
 */
export interface StorageInfo {
  data_dir: DataDir;
  data_schema_version: DataSchemaVersion1;
  source: Source2;
  status: Status12;
}
/**
 * 会话内分页，不接受文件系统路径。 Page by session without filesystem path input.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ListChangesParams".
 */
export interface ListChangesParams {
  cursor: Cursor1;
  limit?: Limit3;
  session_id: SessionId21;
}
/**
 * 按事实游标读取有界目标列表。 Read bounded goals by fact cursor.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ListGoalsParams".
 */
export interface ListGoalsParams {
  before_seq?: BeforeSeq3;
  limit?: Limit4;
  session_id: SessionId22;
}
/**
 * 桌面记忆检索。
 *
 * Desktop memory lookup.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ListMemoryParams".
 */
export interface ListMemoryParams {
  category?: Category;
  cursor?: Cursor2;
  include_disabled?: IncludeDisabled;
  limit?: Limit5;
  query?: Query1;
  session_id: SessionId23;
  subject?: Subject;
}
/**
 * 用户查询卡片范围；工具另校验会话权限。
 *
 * User query scope; tools also check session ownership.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ListProgramsParams".
 */
export interface ListProgramsParams {
  cursor?: Cursor3;
  limit?: Limit6;
  project_id: ProjectId12;
  session_id?: SessionId24;
}
/**
 * 按项目分页会话列表。
 *
 * Page sessions by project.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ListSessionsParams".
 */
export interface ListSessionsParams {
  cursor: Cursor4;
  limit: Limit7;
  project_id: ProjectId13;
}
/**
 * 手动整理可显式选择旧范围，默认仅处理增量。
 *
 * Manual maintenance can explicitly select old history.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "MaintainMemoryParams".
 */
export interface MaintainMemoryParams {
  after_seq?: AfterSeq2;
  session_id: SessionId25;
  source_ids?: SourceIds;
  title?: Title4;
}
/**
 * 管理页与检索结果，不隐藏局部读取失败。
 *
 * Management/retrieval results with local read failures.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "MemoryPage".
 */
export interface MemoryPage {
  entries: Entries;
  next_cursor: NextCursor2;
  state: MemoryState;
  totals?: UsageSummary;
  unavailable_count?: UnavailableCount1;
}
/**
 * 带作用域和修订来源的独立记忆。
 *
 * Independent memory with scope and revision provenance.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "MemoryEntry".
 */
export interface MemoryEntry {
  category?: Category1;
  content: Content;
  created_at: CreatedAt6;
  enabled?: Enabled3;
  memory_id: MemoryId1;
  pinned?: Pinned;
  project_id: ProjectId14;
  related_ids?: RelatedIds;
  revision: Revision4;
  scope?: Scope10;
  session_id: SessionId26;
  source: Source3;
  source_ids?: SourceIds1;
  source_seq: SourceSeq;
  stale?: Stale;
  subjects?: Subjects;
  supersedes?: Supersedes;
  tags?: Tags;
  title: Title5;
  updated_at: UpdatedAt5;
  valid_from?: ValidFrom;
  valid_until?: ValidUntil;
}
/**
 * 会话贡献起点与最近维护事实。
 *
 * Session contribution boundary and latest maintenance facts.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "MemoryState".
 */
export interface MemoryState {
  job?: MemoryJob | null;
  pending_offset?: PendingOffset;
  pending_seq?: PendingSeq;
  processed_seq: ProcessedSeq;
  settings?: MemorySettings;
  used_ids?: UsedIds;
}
/**
 * 独立维护费用与状态，不改已结束 Run 的账本。
 *
 * Maintenance cost/state separate from finished runs.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "MemoryJob".
 */
export interface MemoryJob {
  finished_at?: FinishedAt4;
  job_id: JobId1;
  message?: Message5;
  model_id: ModelId10;
  requests?: Requests5;
  started_at: StartedAt1;
  status: Status13;
  through_seq: ThroughSeq4;
  usage?: TokenUsage;
}
/**
 * 当前项目内管理记忆。
 *
 * Manage memory within the current project.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "MemoryParams".
 */
export interface MemoryParams {
  session_id: SessionId27;
}
/**
 * 显式选择被测模型，不沿用当前会话选择。 Select the tested model explicitly.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ModelConnectionProbeParams".
 */
export interface ModelConnectionProbeParams {
  model_id: ModelId11;
  timeout_seconds: TimeoutSeconds1;
}
/**
 * 通过用户选择的目录路径打开项目。
 *
 * Open a project using a user-selected directory path.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "OpenProjectByPath".
 */
export interface OpenProjectByPath {
  path: Path4;
}
/**
 * 通过已有项目标识恢复选择，并由服务重新验证目录。
 *
 * Restore a recorded project by ID and let the service revalidate its directory.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "OpenProjectById".
 */
export interface OpenProjectById {
  project_id: ProjectId15;
}
/**
 * 用户点击来源时打开 HTTP(S) 地址；宿主仍校验 URL。
 *
 * Open an HTTP(S) source on a user click; the host also validates the URL.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "OpenWebUrlParams".
 */
export interface OpenWebUrlParams {
  url: Url1;
}
/**
 * 桌面操作使用的公开错误，不包含原始异常堆栈。
 *
 * Public desktop-operation error without a raw exception traceback.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "OperationError".
 */
export interface OperationError {
  code: Code8;
  message: Message6;
  remediation: Remediation3;
}
/**
 * 宿主填写来源和请求边界送达状态。
 *
 * The host records provenance and request-boundary delivery state.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "PeerMessage".
 */
export interface PeerMessage {
  created_at: CreatedAt7;
  delivered_run_id?: DeliveredRunId;
  message_id: MessageId1;
  params: SendMessageParams;
  task_id: TaskId6;
}
/**
 * 普通交流不等同工作请求，不唤醒空闲会话。
 *
 * Ordinary messages are not work requests and never wake idle sessions.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SendMessageParams".
 */
export interface SendMessageParams {
  content: Content1;
  operation_id: OperationId9;
  source_session_id: SourceSessionId6;
  target_session_id: TargetSessionId5;
}
/**
 * 普通消息的可追溯收发记录。
 *
 * Traceable incoming and outgoing ordinary messages.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "PeerMessagePage".
 */
export interface PeerMessagePage {
  messages: Messages;
  next_cursor?: NextCursor3;
}
/**
 * 按项目或会话查询卡片，损坏记录明确计数。
 *
 * Query project/session cards with damage counts.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ProgramPage".
 */
export interface ProgramPage {
  active_count: ActiveCount;
  next_cursor: NextCursor4;
  programs: Programs1;
  unavailable_count: UnavailableCount2;
}
/**
 * 只使用受管程序身份。
 *
 * Address a managed program by identity only.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ProgramParams".
 */
export interface ProgramParams {
  program_id: ProgramId2;
}
/**
 * 有界输出页与实际状态。
 *
 * Bounded output page and actual process state.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ProgramView".
 */
export interface ProgramView {
  archive_id?: ArchiveId;
  archive_read?: ArchiveRead;
  next_seq: NextSeq;
  output: Output;
  summary: ProgramSummary;
  truncated: Truncated;
}
/**
 * 按消费顺序编号的输出块，始终作为纯文本处理。
 *
 * Numbered output chunks rendered as plain text.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "OutputChunk".
 */
export interface OutputChunk {
  seq: Seq3;
  stream: Stream;
  text: Text3;
}
/**
 * 明确把已有项目身份绑定到新目录，保留会话与记忆。
 *
 * Explicitly rebind an existing project identity, retaining sessions and memory.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "RelocateProjectParams".
 */
export interface RelocateProjectParams {
  path: Path5;
  project_id: ProjectId16;
}
/**
 * 删除登记而不卸载环境。
 *
 * Remove a reference without uninstalling its environment.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "RemoveEnvironmentParams".
 */
export interface RemoveEnvironmentParams {
  environment_id: EnvironmentId5;
  expected_revision: ExpectedRevision4;
  project_id: ProjectId17;
}
/**
 * 不要求回复的 JSON-RPC 通知，不能与带标识请求混淆。
 *
 * JSON-RPC notification requiring no reply, distinct from an identified request.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "RpcNotification".
 */
export interface RpcNotification {
  jsonrpc: Jsonrpc;
  method: Method3;
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "RpcRequest".
 */
export interface RpcRequest {
  id: Id;
  jsonrpc: Jsonrpc1;
  method: Method4;
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "RpcError".
 */
export interface RpcError {
  code: Code9;
  data: ErrorData;
  message: Message7;
}
/**
 * 显式导入或修改引用，以版本防止覆盖较新设置。
 *
 * Import references with revision checks.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SaveEnvironmentParams".
 */
export interface SaveEnvironmentParams {
  definition: Definition1;
  environment_id: EnvironmentId6;
  expected_revision: ExpectedRevision5;
  name: Name3;
  project_id: ProjectId18;
}
/**
 * 仅影响后续启动，不重新执行或热切换程序。
 *
 * Affect future launches without restarting programs.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SaveExecutionSettings".
 */
export interface SaveExecutionSettings {
  expected_revision: ExpectedRevision6;
  project_id: ProjectId19;
  settings: ExecutionSettings;
}
/**
 * 显式保存知识，可更新已知条目。
 *
 * Explicit knowledge save or update.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SaveMemoryParams".
 */
export interface SaveMemoryParams {
  fields: MemoryFields;
  memory_id?: MemoryId2;
  session_id: SessionId28;
}
/**
 * 用户可维护的知识正文；其余来源由宿主填写。
 *
 * Editable knowledge; the host supplies provenance.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "MemoryFields".
 */
export interface MemoryFields {
  category?: Category2;
  content: Content2;
  enabled?: Enabled4;
  pinned?: Pinned1;
  related_ids?: RelatedIds1;
  scope?: Scope11;
  source_ids?: SourceIds2;
  stale?: Stale1;
  subjects?: Subjects1;
  supersedes?: Supersedes1;
  tags?: Tags1;
  title: Title6;
  valid_from?: ValidFrom1;
  valid_until?: ValidUntil1;
}
/**
 * 选择既有会话的后续模型，不创建会话或发请求。
 *
 * Select a session's next model without creating sessions or sending requests.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SelectSessionModelParams".
 */
export interface SelectSessionModelParams {
  model_id: ModelId12;
  operation_id: OperationId10;
  session_id: SessionId29;
}
/**
 * 唯一支持的后端事件通知形状。
 *
 * The sole supported backend notification envelope.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SessionEventNotification".
 */
export interface SessionEventNotification {
  jsonrpc: Jsonrpc4;
  method: Method5;
  params: SessionSignal;
}
/**
 * 轻量通知：持久变更需要重取快照，文本按增量顺序接收。
 *
 * Lightweight notifications: resync durable changes and order transient text deltas.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SessionSignal".
 */
export interface SessionSignal {
  delta_index: DeltaIndex;
  kind: Kind14;
  message_id: MessageId2;
  model_progress?: ModelProgress | null;
  process_epoch: ProcessEpoch;
  run_id: RunId7;
  seq: Seq4;
  session_id: SessionId30;
  text: Text4;
}
/**
 * 项目会话的游标页。
 *
 * Cursor page of project sessions.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SessionPage".
 */
export interface SessionPage {
  active_session_ids: ActiveSessionIds;
  next_cursor: NextCursor5;
  sessions: Sessions1;
  unavailable_count: UnavailableCount3;
}
/**
 * 限定会话身份。
 *
 * Constrain session identity.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SessionParams".
 */
export interface SessionParams {
  session_id: SessionId31;
}
/**
 * 有界快照含历史水位与实时预览。
 *
 * Bounded snapshot with history watermark and live preview.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SessionView".
 */
export interface SessionView {
  before_seq: BeforeSeq4;
  delta_index: DeltaIndex1;
  entries: Entries1;
  model_progress?: ModelProgress | null;
  process_epoch: ProcessEpoch1;
  stream_message_id: StreamMessageId;
  stream_model_id?: StreamModelId;
  stream_reasoning?: StreamReasoning;
  stream_text: StreamText;
  summary: SessionSummary;
  watermark: Watermark;
}
/**
 * 显式投影的可公开历史记录。
 *
 * Explicitly projected public history record.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ChatEntry".
 */
export interface ChatEntry {
  call: ToolCall | null;
  goal_result?: GoalView | null;
  kind: Kind15;
  message_id: MessageId3;
  model_id?: ModelId13;
  program_result?: ProgramView | null;
  reasoning?: Reasoning;
  result: ToolResult | null;
  run_id: RunId8;
  seq: Seq5;
  text: Text5;
  web_result?: WebResult;
}
/**
 * 完整参数对象，仍需工具权限校验。 Complete arguments still requiring tool policy checks.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ToolCall".
 */
export interface ToolCall {
  arguments: JsonObject;
  name: Name4;
  tool_call_id: ToolCallId3;
}
/**
 * 按调用标识关联可公开工具结果。 Associate public tool output with its call ID.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "ToolResult".
 */
export interface ToolResult {
  content: Content3;
  is_error: IsError;
  tool_call_id: ToolCallId4;
}
/**
 * 原生搜索结果；模型总结和实际来源分别呈现。
 *
 * Native search results distinguish model summaries from actual sources.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WebSearchResult".
 */
export interface WebSearchResult {
  actual_queries: ActualQueries;
  archive_id?: ArchiveId1;
  kind: Kind16;
  model_id: ModelId14;
  query: Query2;
  retrieved_at: RetrievedAt;
  search_uses: SearchUses;
  sources: Sources;
  summary: Summary2;
  truncated?: Truncated1;
  usage: TokenUsage;
}
/**
 * 只保存实际来源及可用摘录，不公开供应商不透明字段。
 *
 * Retain actual sources and available excerpts, excluding opaque provider fields.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WebSource".
 */
export interface WebSource {
  excerpt?: Excerpt;
  page_age?: PageAge;
  title: Title7;
  url: Url2;
}
/**
 * 公开正文片段及读取状态，不宣称执行了网页脚本。
 *
 * A public text excerpt and retrieval status, without claiming script execution.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WebPageResult".
 */
export interface WebPageResult {
  archive_id?: ArchiveId2;
  content: Content4;
  content_type: ContentType;
  download_truncated: DownloadTruncated;
  kind: Kind17;
  next_offset: NextOffset2;
  offset: Offset3;
  redirects: Redirects;
  requested_url: RequestedUrl;
  retrieved_at: RetrievedAt1;
  status_code?: StatusCode;
  title: Title8;
  truncated: Truncated2;
  url: Url3;
}
/**
 * 幂等操作 ID 独立于 RPC ID。
 *
 * Idempotent operation identity is separate from RPC identity.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "StartRunParams".
 */
export interface StartRunParams {
  limits: RunLimits | null;
  mode?: Mode10;
  operation_id: OperationId11;
  plan_document?: PlanDocument1;
  prompt: Prompt1;
  session_id: SessionId32;
}
/**
 * 区分已保存的下次启动设置与本次实际数据根。
 *
 * Distinguish saved next-launch paths from the current effective data root.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "StartupPathsParams".
 */
export interface StartupPathsParams {
  data_dir: DataDir2;
  project_dir: ProjectDir1;
}
/**
 * 按项目分页；损坏任务单独计数，不冒充空任务。
 *
 * Project page with explicit unreadable records.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "TaskPage".
 */
export interface TaskPage {
  next_cursor: NextCursor6;
  tasks: Tasks;
  unavailable_count: UnavailableCount4;
}
/**
 * 树列表仅包含显示所需字段，详细共同信息按需读取。
 *
 * Navigation metadata; shared details load on demand.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "TaskSummary".
 */
export interface TaskSummary {
  project_id: ProjectId20;
  revision: Revision5;
  status: Status14;
  task_id: TaskId7;
  title: Title9;
}
/**
 * 任务查询身份。 Task lookup identity.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "TaskParams".
 */
export interface TaskParams {
  task_id: TaskId8;
}
/**
 * 仅允许保存一个受支持的默认模型标识。
 *
 * Allow saving only one supported default model ID.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "UpdateConfigParams".
 */
export interface UpdateConfigParams {
  model_id: ModelId15;
  run?: RunLimits | null;
}
/**
 * 以版本和操作 ID 防止旧页面覆盖新结论。 Guard edits with a revision and operation identity.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "UpdateTaskParams".
 */
export interface UpdateTaskParams {
  expected_revision: ExpectedRevision7;
  fields: TaskFields;
  operation_id: OperationId12;
  task_id: TaskId9;
}
/**
 * 按已知身份停止或继续内部工作。
 *
 * Stop or continue identified internal work.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WorkerControlParams".
 */
export interface WorkerControlParams {
  action: Action4;
  prompt?: Prompt2;
  session_id: SessionId33;
  worker_id: WorkerId;
}
/**
 * 子卡片列表，不进入左侧正式会话树。
 *
 * Worker cards, excluded from the formal session tree.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WorkerPage".
 */
export interface WorkerPage {
  settings: WorkerSettings;
  workers: Workers;
}
/**
 * 完整内部身份、原安排与结果入口。
 *
 * Internal identity, original assignment and result references.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WorkerRecord".
 */
export interface WorkerRecord {
  active_seconds?: ActiveSeconds1;
  assignment: SpawnWorkerArgs;
  code?: Code10;
  created_at: CreatedAt8;
  goal_id: GoalId6;
  model_id: ModelId16;
  owner_run_id: OwnerRunId;
  owner_session_id: OwnerSessionId;
  pending_messages?: PendingMessages;
  requests?: Requests6;
  result?: Result1;
  run_id?: RunId9;
  session_id: SessionId34;
  status: Status15;
  tools?: Tools2;
  updated_at: UpdatedAt6;
  worker_id: WorkerId1;
}
/**
 * 一个独立、有边界的子任务；不要求收益评分。
 *
 * One bounded independent assignment, without benefit scores.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "SpawnWorkerArgs".
 */
export interface SpawnWorkerArgs {
  context_mode?: ContextMode1;
  mode?: Mode11;
  objective: Objective4;
  role?: Role3;
  scope?: Scope12;
}
/**
 * 用户会话中的子工作入口。
 *
 * Worker access within an owning user session.
 *
 * This interface was referenced by `ProtocolV4`'s JSON-Schema
 * via the `definition` "WorkerSessionParams".
 */
export interface WorkerSessionParams {
  session_id: SessionId35;
}
