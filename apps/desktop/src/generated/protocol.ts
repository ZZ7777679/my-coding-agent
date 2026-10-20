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
export type ProtocolVersion = 11;
export type Stage = "M6";
export type ExpectedRevision = number;
export type ExpectedSpaceRevision = number | null;
export type OperationId = string;
export type StyleId = string;
export type TaskId1 = string;
export type ContextMode = "isolated" | "inherit";
export type Kind = "handoff" | "review";
export type Notes = string;
export type Objective = string;
export type OperationId1 = string;
export type SourceSessionId = string;
export type TargetSessionId = string;
export type TransferGoalId = string | null;
export type TransferRunId = string | null;
export type OperationId2 = string;
export type Role1 = string;
export type Scope1 = string;
export type SessionId1 = string;
export type TaskId2 = string;
export type AttachmentId = string;
export type CreatedAt1 = string;
export type Draft = boolean;
export type EndLine = number | null;
export type Kind1 = "image" | "text";
export type Mime = string;
export type Name1 = string;
export type Origin = "file" | "selection" | "upload";
export type Purpose = string;
export type SessionId2 = string;
export type SizeBytes = number;
export type SourcePath = string | null;
export type StartLine = number | null;
export type Attachments = Attachment[];
export type AttachmentId1 = string;
export type Offset = number;
export type SessionId3 = string;
export type AttachmentId2 = string;
export type Complete = boolean;
export type ImageData = string | null;
export type ImageUrl = string | null;
export type NextOffset = number | null;
export type Text = string | null;
export type EnvironmentId = string | null;
export type EnvironmentPassthrough = string[];
export type ExpectedRevision1 = number;
export type Mode2 = "direct" | "sandbox";
export type ProjectId1 = string;
export type AuthorizationTimeoutSeconds = number;
export type Network = "blocked" | "enabled";
export type ReadPaths = string[];
export type WritePaths = string[];
/**
 * Legacy compatibility field; not an execution gate. Use the selected mode.
 */
export type Trusted = boolean;
export type MemberId = string;
export type OperationId3 = string;
export type SessionId4 = string | null;
export type TaskId3 = string;
export type RunId1 = string;
export type Description = string;
export type Name2 = string;
export type SkillIds = string[];
export type StyleId1 = string;
export type TaskId4 = string;
export type AfterSha256 = string;
export type BeforeSha256 = string | null;
export type ChangeId = string;
export type CreatedAt2 = string;
export type Destination = string | null;
export type Error = string | null;
export type Operation = "create" | "edit" | "delete" | "move" | "create_directory" | "delete_directory";
export type Path = string;
export type ProjectId2 = string;
export type RunId2 = string;
export type SessionId5 = string;
export type Source = "agent" | "user" | "restore";
export type Status1 = "prepared" | "applied" | "failed";
export type ToolCallId = string;
export type Changes = ChangeSummary[];
export type Coverage = string;
export type NextCursor = string | null;
export type UnavailableCount = number;
export type Diff = string;
export type NextOffset1 = number | null;
export type BeforeSeq = number;
export type ChangedFiles = number;
export type CheckpointId = string;
export type CreatedAt3 = string;
export type FinishedAt = string | null;
export type Issues = string[];
export type Kind2 = "request" | "restore";
export type ProjectId3 = string;
export type RunId3 = string | null;
export type SessionId6 = string;
export type Status2 = "capturing" | "ready" | "partial" | "failed";
export type Title1 = string;
export type Checkpoints = FileCheckpointSummary[];
export type UnavailableCount1 = number;
export type SessionId7 = string;
export type Kind3 = "data" | "project";
export type Kind4 = "executable" | "directory";
export type BeforeSeq1 = number | null;
export type Limit = number;
export type SourceSessionId1 = string;
export type TargetSessionId1 = string;
export type Enabled = boolean;
export type Mode3 = "normal" | "plan";
export type Scope2 = string;
export type SourceSessionId2 = string;
export type TargetSessionId2 = string;
export type TaskId5 = string;
export type UpdatedAt1 = string;
export type Candidates = SessionSummary[];
export type Error1 = string | null;
export type Links = CollaborationLink[];
export type NextCursor1 = string | null;
export type NextPeerCursor = string | null;
export type NextStep = string;
export type Reason = "no_task" | "no_agreements_configured" | "ready";
export type CapturedAt = string;
export type InheritedContext = string;
export type MaxActiveSeconds = number | null;
export type MaxRequests1 = number | null;
export type MaxTools1 = number | null;
export type Code1 = string | null;
export type CriterionId = string;
export type Description1 = string;
export type Criteria = GoalCriterion[];
export type GoalId1 = string;
export type CriterionId1 = string;
export type Expectation = "observed" | "succeeded";
export type Kind5 = "tool_result" | "assistant" | "user";
export type RunId4 = string;
export type Seq = number;
export type SessionId8 = string;
export type Evidence = EvidenceRef[];
export type Explanation = string;
export type Status3 = "met" | "unmet" | "not_checked" | "needs_user";
export type Criteria1 = CriterionResult[];
export type Status4 = "user_confirmed" | "proposal";
export type Text1 = string;
export type Decisions = SharedDecision[];
export type NextAction = string;
export type NextWorkId = string | null;
export type Outcome = "continue" | "complete" | "wait" | "return";
export type Impact = string;
export type Options = string[];
export type Question = string;
export type QuestionId = string;
export type Summary = string;
export type ClaimStatus = ("unclaimed" | "assigned" | "claimed" | "released") | null;
export type DependsOn = string[];
export type Evidence1 = EvidenceRef[];
export type FeedbackFrom = EvidenceRef[];
export type FeedbackTo = string[];
export type Method1 = "discuss" | "plan" | "implement" | "diagnose" | "review" | "handoff";
export type OwnerMemberId = string | null;
export type X = number;
export type Y = number;
export type Result = string | null;
export type RunId5 = string | null;
export type Scope3 = string;
export type StageId = string | null;
export type Status5 = "planned" | "in_progress" | "completed" | "waiting";
export type Title2 = string;
export type WorkId1 = string;
export type WorkItems = WorkItem[];
export type LastResultSeq = number | null;
export type Objective1 = string;
export type OperationId4 = string;
export type Prompt = string;
export type PendingInputs = GoalInputView[];
export type Revision = number;
export type SessionId9 = string;
export type Status6 =
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
export type CreatedAt4 = string;
export type Artifacts = string;
export type Constraints = string;
export type Decisions1 = string;
export type Goal = string;
export type Progress = string;
export type Status7 = "active" | "completed" | "archived";
export type Title3 = string;
export type Unresolved = string;
export type InitialModelId = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type InitialSessionId = string;
export type ProjectId4 = string;
export type Revision1 = number;
export type Source1 = "user" | "run_report";
export type TaskId6 = string;
export type UpdatedAt2 = string;
export type ClaimStatus1 = "assigned" | "claimed" | "released";
export type OwnerMemberId1 = string | null;
export type ProgressUpdatedAt = string | null;
export type Result1 = string | null;
export type RunId6 = string | null;
export type Status8 = ("planned" | "in_progress" | "completed" | "waiting") | null;
export type UpdatedAt3 = string;
export type WorkId2 = string;
export type Assignments = WorkAssignment[];
export type RunId7 = string;
export type Seq1 = number;
export type SessionId10 = string;
export type Decisions2 = SourcedDecision[];
export type UpdatedAt4 = string | null;
export type Items = SourcedWorkItem[];
export type UpdatedAt5 = string;
export type Members = MemberProgress[];
export type PlannedItems = WorkItem[];
export type RemovedWorkIds = string[];
export type CurrentStageId = string | null;
export type Description2 = string;
export type Name3 = string;
export type Artifacts1 = string;
export type DependsOn1 = string[];
export type FeedbackTo1 = string[];
export type Goal1 = string;
export type Name4 = string;
export type Skills = string[];
export type StageId1 = string;
export type SuggestedRole = string;
export type Stages = WorkflowStage[];
export type TemplateId = string;
export type Description3 = string;
export type Name5 = string;
export type SkillIds1 = string[];
export type StyleId2 = string;
export type EdgeId = string;
export type Kind6 = "delegate" | "result" | "discuss" | "feedback";
export type Label = string;
export type SourceMemberId = string;
export type TargetMemberId = string;
export type Edges = SpaceEdge[];
export type InitialWorkItems = WorkItem[];
export type MemberId1 = string;
export type ModelId1 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Name6 = string;
export type X1 = number;
export type Y1 = number;
export type Role2 = string;
export type Scope4 = string;
export type SkillIds2 = string[];
export type Members1 = SpaceMember[];
export type Organisation = "central" | "hierarchical" | "peer";
export type ReceiverMemberId = string | null;
export type UpdatedAt6 = string;
export type CreatedAt5 = string;
export type NextAction1 = string;
export type Outcome1 = ("continue" | "complete" | "wait" | "return") | null;
export type ExpectedResult = string;
export type Inputs = string;
export type Mode4 = "normal" | "plan";
export type Objective2 = string;
export type OperationId5 = string;
export type SourceSessionId4 = string;
export type TargetSessionId3 = string;
export type ParentRequestId = string | null;
export type Reason1 = string | null;
export type RequestId = string;
export type Result2 = string;
export type ResultSeq = number | null;
export type SchemaVersion = 1;
export type Scope5 = string;
export type SourceRunId = string | null;
export type Status9 = "preparing" | "queued" | "running" | "completed" | "failed" | "cancelled" | "held";
export type TargetRunId = string | null;
export type TaskId7 = string;
export type UpdatedAt7 = string;
export type Requests1 = CollaborationRequest[];
export type TaskId8 = string | null;
export type UnavailablePeers = number;
export type WorkerEnabled = boolean;
export type WorkerReason = string;
export type Cursor = string | null;
export type Limit1 = number;
export type PeerCursor = string | null;
export type SessionId11 = string;
export type SessionId12 = string;
export type ActiveTools = string[];
export type AutoTriggerTokens = number;
export type Automatic = boolean;
export type BackgroundCompaction = boolean;
export type CoreTools = string[];
export type KeepRecentTokens = number;
export type Enabled1 = boolean;
export type MaxFileBytes1 = number;
export type MaxTotalBytes = number;
export type SkillCatalogTokens = number;
export type SummaryOutputTokens = number | null;
export type SummaryTargetTokens = number;
export type ToolLoading = "on_demand" | "all";
export type ToolResultPreviewTokens = number;
export type Enabled2 = boolean;
export type ProjectId5 = string;
export type SessionId13 = string;
export type Associations = boolean;
export type AutoPages = boolean;
export type Automatic1 = boolean;
export type Contribute = boolean;
export type MaintenanceInputBytes = number;
export type MaintenanceRequests = number;
export type RecallChars = number;
export type RecallLimit = number;
export type Use = boolean;
export type SessionId14 = string;
export type Concurrency = number;
export type Enabled3 = boolean;
export type Enabled4 = boolean;
export type Mode5 = "normal" | "plan";
export type Scope6 = string;
export type SourceSessionId5 = string;
export type TargetSessionId4 = string;
export type TimeoutSeconds = number;
export type ProbeTimeoutSeconds = number;
export type ReuseEnabled = boolean;
export type ActiveRequests = number;
export type ClientCreated = boolean;
export type Code2 = string;
export type FinishedAt1 = string;
export type HttpStatus = number | null;
export type ModelId2 = ("glm-5.3-flash" | "deepseek-v4.1-flash") | null;
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
export type FinishedAt2 = string;
export type Message1 = string;
export type Remediation = string;
export type CachedInputTokens = number | null;
export type InputTokens2 = number | null;
export type OutputTokens2 = number | null;
export type ModelId3 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Testing = boolean;
export type Models = ModelConnectionState[];
export type PendingRelease = boolean;
export type ReuseEnabled1 = boolean;
export type SessionId15 = string;
export type CheckpointId1 = string;
export type CreatedAt6 = string;
export type ModelId4 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type ParentId = string | null;
export type Text2 = string;
export type ThroughSeq = number;
export type EstimateBasis = string;
export type EstimatedHistoryTokens = number;
export type EstimatedInputTokens = number | null;
export type HistoryThroughSeq = number;
export type Background = boolean;
export type CompressionApplied = boolean | null;
export type FinishReason = string | null;
export type FinishedAt3 = string | null;
export type HistoryAfterBytes = number | null;
export type HistoryAfterTokens = number | null;
export type HistoryBeforeBytes = number | null;
export type HistoryBeforeTokens = number | null;
export type JobId = string;
export type Message2 = string;
export type Mode6 = "manual" | "automatic";
export type ModelId5 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Outcome2 = ("summary" | "trimmed" | "nothing" | "not_smaller") | null;
export type OutputTokenLimit = number | null;
export type Requests3 = number;
export type RetainedTokens = number | null;
export type RunId8 = string | null;
export type StartedAt = string;
export type Status10 = "preparing" | "receiving" | "ready" | "adopted" | "failed" | "cancelled" | "interrupted";
export type ThroughSeq1 = number;
export type At = string;
export type EstimatedFixedTokens = number | null;
export type EstimatedInputTokens1 = number | null;
export type Form = string;
export type Kind7 = string;
export type Preview = string;
export type PreviewComplete = boolean;
/**
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "JsonValue".
 */
export type JsonValue = unknown;
export type ReadTool = string | null;
export type Reason2 = string;
export type Revision2 = number | null;
export type SourceId = string | null;
export type Title4 = string;
export type Materials = ContextMaterial[];
export type MessageCount = number;
export type RequestBytes = number;
export type ToolNames = string[];
export type MessageId = string;
export type ModelId6 = ("glm-5.3-flash" | "deepseek-v4.1-flash") | null;
export type LimitBytes = number;
export type Measurement = "history_bytes";
export type MigratedFromBytes = boolean;
export type RawBytes = number;
export type SessionId16 = string;
export type InputTokens3 = number | null;
export type ModelId7 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Status11 = "reported" | "not_measured" | "not_reported" | "model_changed" | "compacted";
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ControlGoalParams".
 */
export type ControlGoalParams = GoalStateControl | GoalBudgetControl | GoalAnswerControl;
export type Action1 = "resume" | "pause" | "cancel";
export type ExpectedRevision2 = number;
export type GoalId2 = string;
export type OperationId6 = string;
export type SessionId17 = string;
export type Action2 = "budget";
export type ExpectedRevision3 = number;
export type GoalId3 = string;
export type OperationId7 = string;
export type SessionId18 = string;
export type Action3 = "answer";
export type Answer = string;
export type ExpectedRevision4 = number;
export type GoalId4 = string;
export type OperationId8 = string;
export type QuestionId1 = string;
export type SessionId19 = string;
export type Name7 = string;
export type NewTemplateId = string;
export type TemplateId1 = string;
export type AttachmentIds = string[];
/**
 * @minItems 1
 */
export type Criteria2 = [GoalCriterion, ...GoalCriterion[]];
export type GoalId5 = string;
export type Method2 = "discuss" | "plan" | "implement" | "diagnose" | "review" | "handoff";
export type Objective3 = string;
export type SessionId20 = string;
export type ModelId8 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type OperationId9 = string | null;
export type ProjectId6 = string;
export type Role3 = string;
export type Scope7 = string;
export type TaskId9 = string | null;
export type ModelId9 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type OperationId10 = string;
export type ProjectId7 = string;
export type UseProjectWorkstyle = boolean;
export type WorkflowTemplateId = string | null;
export type WorkstyleId = string | null;
export type SessionError = string | null;
export type EnvVar = "OPENCODE_API_KEY";
export type Present = boolean | null;
export type Source2 = "process" | "windows_user" | "none" | "restricted";
export type Blocking = boolean;
export type CheckId = string;
export type Code4 = string;
export type Remediation1 = string;
export type Status12 = "ok" | "warning" | "error" | "not_checked";
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
export type Network1 = boolean;
export type NetworkTimeoutSeconds = number | null;
export type WriteProbe = boolean;
export type Path1 = string | null;
export type ChangeId1 = string;
export type SessionId21 = string;
export type After = string;
export type Before = string;
export type Current = string;
export type CurrentExists = boolean;
export type Message3 = string | null;
export type Restorable = boolean;
export type BaseContent = string;
export type Content = string;
export type Path2 = string;
export type SessionId22 = string;
export type UpdatedAt8 = string;
export type Directory = string;
export type Limit2 = number;
export type Query = string;
export type SessionId23 = string;
export type Directories = string[];
export type Files = string[];
export type Skipped = number;
export type Truncated = boolean;
export type Content1 = string;
export type Destination1 = string | null;
export type Operation1 = "create_file" | "create_directory" | "move" | "delete";
export type Path3 = string;
export type Recursive = boolean;
export type SessionId24 = string;
export type Path4 = string;
export type SessionId25 = string;
export type After1 = number;
export type Before1 = number;
export type ExcludeGlobs1 = string[];
export type Glob = string;
export type IncludeGlobs = string[];
export type Limit3 = number;
export type Query1 = string;
export type Regex = boolean;
export type SessionId26 = string;
export type Backend = string;
export type Line = number;
export type Text3 = string;
export type ContextAfter = DocumentContextLine[];
export type ContextBefore = DocumentContextLine[];
export type Line1 = number;
export type Path5 = string;
export type Text4 = string;
export type Matches = DocumentMatch[];
export type Skipped1 = number;
export type Truncated1 = boolean;
export type SessionId27 = string;
export type ChangeId2 = string | null;
export type Content2 = string;
export type Encoding = string;
export type Newline = string;
export type Path6 = string;
export type ReadAt = string;
export type Drafts = DocumentDraft[];
export type Enabled5 = boolean;
export type ProjectId8 = string | null;
export type SessionId28 = string | null;
export type SkillId = string;
export type EnvironmentId1 = string | null;
export type EnvironmentPassthrough1 = string[];
export type Mode8 = "direct" | "sandbox";
export type ProjectId9 = string;
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
export type Kind8 = "system";
export type Interpreter1 = string;
export type Kind9 = "python";
export type Scope8 = "absolute" | "project";
export type Kind10 = "conda";
export type Launcher1 = string;
export type Prefix1 = string;
export type Scope9 = "absolute" | "project";
export type Interpreter2 = string;
export type Kind11 = "uv";
export type Launcher2 = string;
export type Scope10 = "absolute" | "project";
export type EnvironmentId2 = string;
export type Name8 = string;
export type CheckedAt1 = string;
export type Code5 = string;
export type Interpreter3 = string | null;
export type LauncherVersion = string | null;
export type Message4 = string;
export type ProjectId10 = string | null;
export type Version = string | null;
export type Environments = EnvironmentView[];
export type Revision3 = number;
export type SandboxIssue = string | null;
export type CleanupTimeoutSeconds = number;
export type CommandTimeoutSeconds = number;
export type MaxOutputBytes = number;
export type ProbeTimeoutSeconds1 = number;
export type ServiceReadyTimeoutSeconds = number;
export type EnvironmentId3 = string;
export type ProjectId11 = string | null;
export type ProjectId12 = string | null;
export type Code6 = string;
export type Remediation2 = string;
export type ProbeCount = number;
export type Code7 = string | null;
export type Command = ProgramCommand | ShellCommand;
export type Arguments = string[];
export type Kind12 = "program";
export type Program = string;
export type Kind13 = "powershell";
export type Script = string;
export type CreatedAt7 = string;
export type Cwd = string;
export type DroppedBytes = number;
export type EnvironmentId4 = string;
export type EnvironmentName = string;
export type EnvironmentRevision = number;
export type ExitCode = number | null;
export type FinishedAt4 = string | null;
export type HttpStatus1 = number | null;
export type Kind14 = "command" | "service";
export type Message5 = string | null;
export type Mode9 = "direct" | "sandbox";
export type Pid = number | null;
export type ProgramId = string;
export type ProjectId13 = string;
export type ResolvedCommand = string[];
export type Retained = boolean;
export type RunId9 = string;
export type SessionId29 = string;
export type Status13 = "starting" | "running" | "ready" | "stopping" | "exited" | "stopped" | "failed" | "interrupted";
export type ToolCallId1 = string | null;
export type Url = string | null;
export type Programs = ProgramSummary[];
export type Kind15 = "config" | "projects" | "diagnostics";
export type Path7 = string | null;
export type MemoryId = string;
export type SessionId30 = string;
export type Objective4 = string;
export type OperationId11 = string;
export type Organisation1 = "central" | "hierarchical" | "peer";
export type SessionId31 = string;
export type TaskId10 = string;
export type ChangeId3 = string;
export type Offset1 = number;
export type SessionId32 = string;
export type AfterSeq = number;
export type ProgramId1 = string;
export type BeforeSeq2 = number | null;
export type SessionId33 = string;
export type Message6 = string;
export type ProjectId14 = string;
export type CommitId = string;
export type Output = string;
export type ProjectId15 = string;
export type Area = "worktree" | "index";
export type Path8 = string;
export type ProjectId16 = string;
export type Text5 = string;
export type Truncated2 = boolean;
export type Area1 = "worktree" | "index";
export type Path9 = string;
export type ProjectId17 = string;
export type Author = string;
export type AuthoredAt = string;
export type CommitId1 = string;
export type Subject = string;
export type Commits = GitCommit[];
export type ProjectId18 = string;
export type Limit4 = number;
export type ProjectId19 = string;
/**
 * @minItems 1
 */
export type Paths = [string, ...string[]];
export type ProjectId20 = string;
export type ProjectId21 = string;
export type BackupPath = string | null;
export type Enabled6 = boolean;
export type ProjectId22 = string;
export type ProjectMetadataPresent = boolean;
export type Available1 = boolean;
export type Branch = string | null;
export type Code8 = string | null;
export type IndexStatus = string;
export type OriginalPath = string | null;
export type Path10 = string;
export type WorktreeStatus = string;
export type Files1 = GitFileStatus[];
export type Message7 = string | null;
export type ProjectId23 = string;
export type ProjectRepository = boolean;
export type Repository = boolean;
export type RepositoryRoot = string | null;
export type BeforeSeq3 = number | null;
export type Goals = GoalView[];
export type Complete1 = boolean;
export type CallSeq = number | null;
export type Kind16 = string;
export type NextOffset2 = number | null;
export type Offset2 = number;
export type ResultSeq1 = number | null;
export type Seq2 = number;
export type Text6 = string;
export type ToolCallId2 = string | null;
export type ToolName = string | null;
export type TotalChars = number;
export type Items1 = HistoryItem[];
export type MatchUnit = "records" | "occurrences";
export type Matches1 = number;
export type NextAfterSeq = number | null;
export type ThroughSeq2 = number;
export type AfterSeq1 = number;
export type ArtifactId = string | null;
export type EntrySeq = number | null;
export type IncludeLookupResults = boolean;
export type Limit5 = number;
export type MaxChars = number;
export type Offset3 = number;
export type Query2 = string;
export type SessionId34 = string;
export type ThroughSeq3 = number | null;
export type AttachmentId3 = string | null;
export type Data = string;
export type Final = boolean;
export type Mime1 = "image/png" | "image/jpeg" | "image/webp" | "image/gif";
export type Name9 = string;
export type Purpose1 = string;
export type SessionId35 = string;
export type Content3 = string | null;
export type Draft1 = boolean;
export type EndLine1 = number | null;
export type Path11 = string;
export type Purpose2 = string;
export type SessionId36 = string;
export type StartLine1 = number | null;
export type Content4 = string;
export type TemplateId2 = string;
export type AppVersion2 = string;
export type DataSchemaVersion = 1;
export type ProtocolVersion1 = 11;
export type Capabilities = (
  | "spaces.work"
  | "spaces.work_graph"
  | "spaces.work_graph_save"
  | "spaces.work_graph_start"
  | "spaces.generate"
  | "spaces.chat_view"
  | "spaces.chat"
  | "spaces.start_round"
  | "spaces.stop"
  | "spaces.templates"
  | "spaces.template_save"
  | "spaces.template_copy"
  | "spaces.template_import"
  | "spaces.template_export"
  | "documents.list"
  | "documents.read"
  | "documents.search"
  | "documents.save"
  | "documents.drafts"
  | "documents.draft"
  | "documents.operate"
  | "documents.patch"
  | "documents.diff"
  | "documents.restore"
  | "terminals.list"
  | "terminals.open"
  | "terminals.read"
  | "terminals.write"
  | "terminals.resize"
  | "terminals.control"
  | "terminals.interrupt"
  | "terminals.stop"
  | "git.status"
  | "git.settings"
  | "git.configure"
  | "git.diff"
  | "git.stage"
  | "git.unstage"
  | "git.init"
  | "git.commit"
  | "git.history"
  | "intelligence.list"
  | "intelligence.configure"
  | "intelligence.query"
  | "attachments.import"
  | "attachments.chunk"
  | "attachments.read"
  | "spaces.get"
  | "spaces.save"
  | "spaces.start"
  | "spaces.bind"
  | "spaces.layout"
  | "workflows.parse"
  | "workflows.list"
  | "workflows.save"
  | "workflows.remove"
  | "tasks.workflow"
  | "mcp.list"
  | "mcp.save"
  | "mcp.control"
  | "mcp.artifact"
  | "trace.list"
  | "trace.detail"
  | "skills.list"
  | "skills.read"
  | "skills.save"
  | "skills.select"
  | "skills.enable"
  | "skills.online.search"
  | "skills.online.inspect"
  | "skills.online.status"
  | "skills.online.read"
  | "skills.online.install"
  | "skills.online.cancel"
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
export type BaseUrl = string;
export type ConfigPath = string;
export type ModelId10 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type ModelSource = "default" | "user" | "cli";
export type Provider = "opencode-go";
export type Available2 = boolean;
export type CanonicalPath = string;
export type LastOpenedAt = string;
export type Name10 = string;
export type Path12 = string;
export type ProjectId24 = string;
export type UnavailableCode = string | null;
export type RecentProjects = ProjectSummary[];
export type DataDir = string;
export type DataSchemaVersion1 = 1;
export type Source3 = "cli" | "environment" | "default";
export type Status14 = "ready" | "not_initialized" | "unavailable" | "busy";
export type ProjectId25 = string;
export type Action4 = "definition" | "references" | "symbols" | "hover" | "diagnostics" | "completion" | "rename";
export type Character = number;
export type Content5 = string | null;
export type Language = string;
export type Line2 = number;
export type NewName = string | null;
export type Path13 = string;
export type ProjectId26 = string;
export type Version1 = number;
export type Action5 = string;
export type Content6 = string;
export type ObservedAt = string;
export type Path14 = string;
export type ProjectId27 = string;
export type Content7 = string | null;
export type Error2 = string | null;
export type Path15 = string;
export type Source4 = "disk" | "draft";
export type Version2 = number | null;
export type RenameDocuments = LanguageDocumentSnapshot[];
export type ServerId = string;
export type Source5 = "disk" | "draft";
export type Version3 = number;
export type ProjectId28 = string;
export type Arguments1 = string[];
export type Enabled7 = boolean;
export type Languages = string[];
export type Program1 = string;
export type ServerId1 = string;
export type Servers = LanguageServer[];
export type Message8 = string | null;
export type ServerId2 = string;
export type Status15 = "not_started" | "running" | "failed";
export type States = LanguageServerState[];
export type TimeoutSeconds1 = number;
export type Cursor1 = string | null;
export type Limit6 = number;
export type Path16 = string | null;
export type Scope11 = "session" | "task";
export type SessionId37 = string;
export type BeforeSeq4 = number | null;
export type Limit7 = number;
export type SessionId38 = string;
export type Category = string | null;
export type Cursor2 = string | null;
export type IncludeDisabled = boolean;
export type Limit8 = number;
export type Query3 = string;
export type SessionId39 = string;
export type Subject1 = string | null;
export type Cursor3 = string | null;
export type Limit9 = number;
export type ProjectId29 = string;
export type SessionId40 = string | null;
export type Cursor4 = string | null;
export type Limit10 = number;
export type ProjectId30 = string;
export type ProjectId31 = string;
export type AfterSeq2 = number | null;
export type SessionId41 = string;
export type SourceIds = string[];
export type Title5 = string;
export type Data1 = string;
export type MimeType = string;
export type NextOffset3 = number | null;
export type ArtifactId1 = string;
export type Offset4 = number;
export type ProjectId32 = string | null;
export type SessionId42 = string | null;
export type Artifacts2 = string[];
export type InstallError = string;
export type InstallingBrowser = boolean;
export type Issues1 = string[];
export type AuthHelp = string;
export type CredentialUrl = string;
export type DocsUrl = string;
export type OauthHelp = string;
export type OauthSetupUrl = string;
export type OauthUrl = string;
export type PresetId = string;
export type AllProjects = boolean;
export type Arguments2 = string[];
export type EnvVar1 = string;
export type Header = string;
export type CallbackPort = number;
export type ClientId = string;
export type ClientMetadataUrl = string;
export type ClientSecretEnv = string;
export type LoginTimeoutSeconds = number;
export type Scope12 = string;
export type TokenAuthMethod = "none" | "client_secret_post" | "client_secret_basic";
export type Prefix2 = string;
export type Source6 = "none" | "environment" | "saved" | "oauth";
export type BrowserExecutable = string;
export type Command1 = string;
export type Description4 = string;
export type Enabled8 = boolean;
export type Name11 = string;
export type PresetId1 = string;
export type ProjectIds = string[];
export type ServerId3 = string;
export type TimeoutSeconds2 = number;
export type Transport = "stdio" | "http" | "browser";
export type Url1 = string;
export type SuggestedEnv = string;
export type Name12 = string;
export type Title6 = string;
export type Toolsets = McpToolset[];
export type Presets = McpPreset[];
export type CredentialMessage = string;
export type CredentialStatus = "not_required" | "configured" | "missing" | "unavailable";
export type Error3 = string;
export type NeedsReconnect = boolean;
export type AuthorizationUrl = string;
export type Error4 = string;
export type ExpiresAt = number | null;
export type RedirectUri = string;
export type Scope13 = string;
export type Status16 =
  "not_logged_in" | "stored" | "discovering" | "awaiting_user" | "exchanging" | "authorized" | "failed" | "cancelled";
export type Status17 = string;
export type Tools2 = JsonObject[];
export type Servers1 = McpServerView[];
export type Action6 =
  "connect" | "refresh" | "close" | "remove" | "install_browser" | "oauth_login" | "oauth_cancel" | "oauth_logout";
export type ProjectId33 = string | null;
export type ServerId4 = string;
export type SessionId43 = string | null;
export type ProjectId34 = string | null;
export type SessionId44 = string | null;
export type Category1 = string;
export type Content8 = string;
export type CreatedAt8 = string;
export type Enabled9 = boolean;
export type MemoryId1 = string;
export type Pinned = boolean;
export type ProjectId35 = string | null;
export type RelatedIds = string[];
export type Revision4 = number;
export type Scope14 = "project" | "user";
export type SessionId45 = string | null;
export type Source7 = "user" | "agent" | "maintenance";
export type SourceIds1 = string[];
export type SourceSeq = number | null;
export type Stale = boolean;
export type Subjects = string[];
export type Supersedes = string[];
export type Tags = string[];
export type Title7 = string;
export type UpdatedAt9 = string;
export type ValidFrom = string | null;
export type ValidUntil = string | null;
export type Entries = MemoryEntry[];
export type NextCursor2 = string | null;
export type FinishedAt5 = string | null;
export type JobId1 = string;
export type Message9 = string;
export type ModelId11 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Requests5 = number;
export type StartedAt1 = string;
export type Status18 = "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type ThroughSeq4 = number;
export type PendingOffset = number;
export type PendingSeq = number | null;
export type ProcessedSeq = number;
export type UsedIds = string[];
export type UnavailableCount2 = number;
export type SessionId46 = string;
export type ModelId12 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type TimeoutSeconds3 = number;
export type Id = string;
export type Kind17 = "project" | "task" | "session";
export type Name13 = string;
export type OperationId12 = string;
export type Content9 = string;
export type FileCount = number;
export type Files2 = string[];
export type Truncated3 = boolean;
export type Directory1 = string;
export type MaxArchiveMb = number;
export type Ref = string;
export type Source8 = string;
export type TimeoutSeconds4 = number;
export type Path17 = string;
export type PreviewId = string;
export type ProjectId36 = string | null;
export type Scope15 = "user" | "project";
export type Path18 = string;
export type PreviewId1 = string;
export type Limit11 = number;
export type Query4 = string;
export type TimeoutSeconds5 = number;
export type Action7 = ("search" | "inspect" | "install") | null;
export type ErrorCode = string | null;
export type Installs = number | null;
export type Name14 = string;
export type Source9 = string;
export type Url2 = string;
export type Hits = OnlineSkillHit[];
export type Description5 = string;
export type Enabled10 = boolean;
export type Name15 = string;
export type Directory2 = string;
export type DownloadedAt = string;
export type Ref1 = string;
export type Repository1 = string;
export type Revision5 = string | null;
export type Path19 = string;
export type ResourceBase = string;
export type ShadowedBy = string | null;
export type SkillId1 = string;
export type Source10 = "builtin" | "user" | "project";
export type Version4 = string;
export type Message10 = string;
export type OperationId13 = string;
export type Issues2 = string[];
export type PreviewId2 = string;
export type Bytes = number;
export type Description6 = string;
export type FileCount1 = number;
export type Name16 = string;
export type Path20 = string;
export type Skills1 = OnlineSkillCandidate[];
export type Total = number;
export type Query5 = string;
export type Status19 = "idle" | "running" | "ready" | "installed" | "failed" | "cancelled";
/**
 * 路径与已有标识二选一，禁止同时提交两种定位方式。
 *
 * Require either a path or an existing ID, never both.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OpenProjectParams".
 */
export type OpenProjectParams = OpenProjectByPath | OpenProjectById;
export type Path21 = string;
export type ProjectId37 = string;
export type Cols = number;
export type Command2 = ProgramCommand | ShellCommand;
export type Cwd1 = string;
export type MemberId2 = string | null;
export type ProjectId38 = string;
export type Rows = number;
export type SessionId47 = string | null;
export type Url3 = string;
export type Code9 = string;
export type Message11 = string;
export type Remediation3 = string;
export type ChangeId4 = string | null;
export type Code10 = string | null;
export type Message12 = string | null;
export type Path22 = string;
export type Status20 = "applied" | "failed";
export type Items2 = OperationItem[];
export type Partial = boolean;
export type Unattempted = number;
export type Content10 = string;
export type Content11 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Edits = [EditFileArgs, ...EditFileArgs[]];
export type NewText = string;
export type OldText = string;
export type Path23 = string;
export type SessionId48 = string;
export type CreatedAt9 = string;
export type DeliveredRunId = string | null;
export type MessageId1 = string;
export type Content12 = string;
export type OperationId14 = string;
export type SourceSessionId6 = string;
export type TargetSessionId5 = string;
export type TaskId11 = string;
export type Messages = PeerMessage[];
export type NextCursor3 = string | null;
export type CheckpointId2 = string;
export type SessionId49 = string;
export type ActiveCount = number;
export type NextCursor4 = string | null;
export type Programs1 = ProgramSummary[];
export type UnavailableCount3 = number;
export type ProgramId2 = string;
export type ArchiveId = string | null;
export type ArchiveRead = string | null;
export type NextSeq = number;
export type Seq3 = number;
export type Stream = "stdout" | "stderr";
export type Text7 = string;
export type Output1 = OutputChunk[];
export type Truncated4 = boolean;
export type AfterSeq3 = number;
export type TerminalId = string;
export type Path24 = string;
export type ProjectId39 = string;
export type EnvironmentId5 = string;
export type ExpectedRevision5 = number;
export type ProjectId40 = string | null;
export type TemplateId3 = string;
export type Id1 = string;
export type Kind18 = "project" | "task" | "session";
export type Name17 = string;
export type OperationId15 = string;
export type Cols1 = number;
export type Rows1 = number;
export type TerminalId1 = string;
export type CheckpointId3 = string;
export type IncludeObserved = boolean;
export type Mode10 = "code" | "conversation";
export type OperationId16 = string;
export type Paths1 = string[] | null;
export type SessionId50 = string;
export type Diff1 = string;
export type Message13 = string;
export type Path25 = string;
export type Source11 = "agent" | "observed" | "other_session";
export type Status21 = "ready" | "unchanged" | "conflict" | "restored" | "failed" | "skipped";
export type Files3 = RestoreFile[];
export type Issues3 = string[];
export type Files4 = RestoreFile[];
export type Message14 = string;
export type Prompt1 = string;
export type Rewound = boolean;
export type UndoCheckpointId = string;
export type Jsonrpc = "2.0";
export type Method3 = string;
export type Id2 = string;
export type Jsonrpc1 = "2.0";
export type Method4 = string;
/**
 * 成功与失败响应的严格联合，不接受混合结构。
 *
 * Strict union of success and failure responses, rejecting mixed envelopes.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RpcResponse".
 */
export type RpcResponse = RpcSuccess | RpcFailure;
export type Id3 = string;
export type Jsonrpc2 = "2.0";
export type Code11 = number;
export type Message15 = string;
export type Id4 = string | null;
export type Jsonrpc3 = "2.0";
export type BaseContent1 = string;
export type Content13 = string;
export type Path26 = string;
export type SessionId51 = string;
export type Definition1 = SystemEnvironment | PythonEnvironment | CondaEnvironment | UvEnvironment;
export type EnvironmentId6 = string | null;
export type ExpectedRevision6 = number;
export type Name18 = string;
export type ProjectId41 = string | null;
export type ExpectedRevision7 = number;
export type ProjectId42 = string | null;
export type ProjectId43 = string;
export type Servers2 = LanguageServer[];
export type TimeoutSeconds6 = number;
export type ClearCredential = boolean;
export type CredentialValue = string | null;
export type ProjectId44 = string | null;
export type SessionId52 = string | null;
export type Category2 = string;
export type Content14 = string;
export type Enabled11 = boolean;
export type Pinned1 = boolean;
export type RelatedIds1 = string[];
export type Scope16 = "project" | "user";
export type SourceIds2 = string[];
export type Stale1 = boolean;
export type Subjects1 = string[];
export type Supersedes1 = string[];
export type Tags1 = string[];
export type Title8 = string;
export type ValidFrom1 = string | null;
export type ValidUntil1 = string | null;
export type MemoryId2 = string | null;
export type SessionId53 = string;
export type Content15 = string;
export type ImportDirectory = string | null;
export type Name19 = string;
export type Overwrite = boolean;
export type ProjectId45 = string | null;
export type Scope17 = "user" | "project";
export type SessionId54 = string | null;
export type GraphOpen = boolean;
export type X2 = number;
export type Y2 = number;
export type Zoom = number;
export type TaskId12 = string;
export type ExpectedRevision8 = number | null;
export type TaskId13 = string;
export type Description7 = string;
export type InitialWorkItems1 = WorkItem[];
export type Name20 = string;
export type TemplateId4 = string;
export type ExpectedRevision9 = number;
export type Items3 = WorkItem[];
export type OperationId17 = string;
export type TaskId14 = string;
export type ModelId13 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type OperationId18 = string;
export type SessionId55 = string;
export type ProjectId46 = string | null;
export type Selected = string[];
export type SessionId56 = string | null;
export type Jsonrpc4 = "2.0";
export type Method5 = "session.event";
export type DeltaIndex = number;
export type Kind19 = "changed" | "text.delta" | "reasoning.delta" | "model.progress" | "resync";
export type MessageId2 = string | null;
export type ProcessEpoch = string;
export type RunId10 = string | null;
export type Seq4 = number;
export type SessionId57 = string;
export type Text8 = string;
export type ActiveSessionIds = string[];
export type NextCursor5 = string | null;
export type Sessions1 = SessionSummary[];
export type UnavailableCount4 = number;
export type SessionId58 = string;
export type BeforeSeq5 = number | null;
export type DeltaIndex1 = number;
export type Abandoned = boolean;
export type Name21 = string;
export type ToolCallId3 = string;
export type Kind20 =
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
export type ModelId14 = ("glm-5.3-flash" | "deepseek-v4.1-flash") | null;
export type Reasoning = string;
export type Content16 = string;
export type IsError = boolean;
export type ToolCallId4 = string;
export type RunId11 = string | null;
export type Seq5 = number;
export type Text9 = string;
export type WebResult = WebSearchResult | WebPageResult | null;
export type ActualQueries = string[];
export type ArchiveId1 = string | null;
export type Kind21 = "web.search";
export type ModelId15 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Query6 = string;
export type RetrievedAt = string;
export type SearchUses = number;
export type Excerpt = string;
export type PageAge = string | null;
export type Title9 = string;
export type Url4 = string;
export type Sources = WebSource[];
export type Summary2 = string;
export type Truncated5 = boolean;
export type ArchiveId2 = string | null;
export type Content17 = string;
export type ContentType = string;
export type DownloadTruncated = boolean;
export type Kind22 = "web.page";
export type NextOffset4 = number | null;
export type Offset5 = number;
export type Redirects = string[];
export type RequestedUrl = string;
export type RetrievedAt1 = string;
export type StatusCode = number | null;
export type Title10 = string;
export type Truncated6 = boolean;
export type Url5 = string;
export type Entries1 = ChatEntry[];
export type ProcessEpoch1 = string;
export type StreamMessageId = string | null;
export type StreamModelId = ("glm-5.3-flash" | "deepseek-v4.1-flash") | null;
export type StreamReasoning = string;
export type StreamText = string;
export type Watermark = number;
export type Issues4 = string[];
export type Items4 = SkillItem[];
export type ProjectDirectory = string;
export type RulePaths = string[];
export type Selected1 = string[];
export type UserDirectory = string;
export type Content18 = string;
export type ProjectId47 = string | null;
export type SessionId59 = string | null;
export type ProjectId48 = string | null;
export type SessionId60 = string | null;
export type SkillId2 = string;
export type Action8 = "navigate" | "back" | "forward" | "reload" | "stop" | "status";
export type Url6 = string;
export type Height = number;
export type OwnerId = string;
export type Visible = boolean;
export type Width = number;
export type X3 = number;
export type Y3 = number;
export type PageUrl = string;
export type Label1 = string;
export type Url7 = string;
export type Sources1 = SkillSiteSource[];
export type CanBack = boolean;
export type CanForward = boolean;
export type Error5 = string;
export type Loading = boolean;
export type Title11 = string;
export type Url8 = string;
export type BeforeId = string | null;
export type Limit12 = number;
export type TaskId15 = string;
export type Content19 = string;
export type Mode11 = "normal" | "plan";
export type OperationId19 = string;
export type TargetMemberIds = string[];
export type TaskId16 = string;
export type WorkIds = string[];
export type CreatedAt10 = string;
export type Error6 = string | null;
export type ExpectedRevision10 = number | null;
export type RunId12 = string | null;
export type Generations = TeamGeneration[];
export type Content20 = string;
export type CreatedAt11 = string;
export type Error7 = string | null;
export type GoalId6 = string | null;
export type MemberId3 = string;
export type OperationId20 = string;
export type RequestId2 = string | null;
export type RunId13 = string | null;
export type SessionId61 = string;
export type Executions = SpaceExecution[];
export type MessageId4 = string;
export type Mode12 = "normal" | "plan";
export type TargetMemberIds1 = string[];
export type WorkIds1 = string[];
export type Messages1 = SpaceChatMessage[];
export type NextBefore = string | null;
export type DeltaIndex2 = number;
export type Error8 = string | null;
export type MemberId4 = string;
export type MessageId5 = string | null;
export type OriginId = string | null;
export type ProcessEpoch2 = string | null;
export type RunId14 = string | null;
export type Seq6 = number | null;
export type SessionId62 = string;
export type Status22 = string;
export type Streaming = boolean;
export type Text10 = string;
export type WaitingFor1 = string | null;
export type Outputs = SpacePublicOutput[];
export type CreatedAt12 = string;
export type Executions1 = SpaceExecution[];
export type Objective5 = string;
export type RoundId = string;
export type Stopped = boolean;
export type WorkIds2 = string[];
export type Rounds = SpaceRound[];
export type TaskId17 = string;
export type TaskId18 = string;
export type Error9 = string | null;
export type MemberId5 = string;
export type SessionId63 = string | null;
export type SessionIds = string[];
export type Bindings = SpaceBinding[];
export type CreatedAt13 = string;
export type Error10 = string | null;
export type ProjectId49 = string;
export type Revision6 = number;
export type TaskId19 = string;
export type UpdatedAt10 = string;
export type TaskId20 = string;
export type AttachmentIds1 = string[];
export type Mode13 = "normal" | "plan";
export type OperationId21 = string;
export type PlanDocument1 = string | null;
export type Prompt2 = string;
export type SessionId64 = string;
export type Objective6 = string;
export type OperationId22 = string;
export type TargetMemberIds2 = string[];
export type TaskId21 = string;
export type WorkIds3 = string[];
export type Continuous = boolean;
export type Instruction = string;
export type MemberId6 = string;
export type OperationId23 = string;
export type TaskId22 = string;
/**
 * @minItems 1
 */
export type WorkIds4 = [string, ...string[]];
export type ConfigPath1 = string;
export type CurrentDataDir = string;
export type DataDir1 = string;
export type ProjectDir = string;
export type DataDir2 = string;
export type ProjectDir1 = string;
export type MemberId7 = string | null;
export type RoundId1 = string | null;
export type TaskId23 = string;
export type NextCursor6 = string | null;
export type ProjectId50 = string;
export type Revision7 = number;
export type Status23 = "active" | "completed" | "archived";
export type TaskId24 = string;
export type Title12 = string;
export type Tasks = TaskSummary[];
export type UnavailableCount5 = number;
export type TaskId25 = string;
export type Description8 = string;
export type Name22 = string;
export type SchemaVersion1 = 1;
export type TemplateId5 = string;
export type UpdatedAt11 = string;
export type Content21 = string;
export type TemplateId6 = string;
export type Templates = TeamTemplate[];
export type Controller = "user" | "member";
export type MemberId8 = string | null;
export type SessionId65 = string | null;
export type TerminalId2 = string;
export type ActiveCount1 = number;
export type Available3 = boolean;
export type Message16 = string | null;
export type Code12 = string | null;
export type Cols2 = number;
export type Command3 = ProgramCommand | ShellCommand;
export type Controller1 = "user" | "member";
export type CreatedAt14 = string;
export type Cwd2 = string;
export type DroppedBytes1 = number;
export type EnvironmentName1 = string;
export type ExitCode1 = number | null;
export type FinishedAt6 = string | null;
export type MemberId9 = string | null;
export type Message17 = string | null;
export type Mode14 = "direct" | "sandbox";
export type Pid1 = number | null;
export type ProjectId51 = string;
export type Rows2 = number;
export type RunId15 = string | null;
export type SessionId66 = string | null;
export type Status24 = "starting" | "running" | "stopping" | "exited" | "stopped" | "failed" | "interrupted";
export type TerminalId3 = string;
export type ToolCallId5 = string | null;
export type Terminals = TerminalSummary[];
export type UnavailableCount6 = number;
export type TerminalId4 = string;
export type NextSeq1 = number;
export type Seq7 = number;
export type Text11 = string;
export type Output2 = TerminalChunk[];
export type Truncated7 = boolean;
export type At1 = string;
export type DurationMs = number | null;
export type GoalId7 = string | null;
export type IsError1 = boolean;
export type Kind23 = string;
export type RequestId3 = string | null;
export type RunId16 = string | null;
export type Seq8 = number;
export type Status25 = string;
export type Title13 = string;
export type ToolCallId6 = string | null;
export type ToolName1 = string | null;
export type UpdatedSeq = number;
export type Identity = string;
export type Kind24 = "change" | "archive" | "image";
export type Title14 = string;
export type Links1 = TraceLink[];
export type NextOffset5 = number | null;
export type Offset6 = number;
export type Seq9 = number;
export type Text12 = string;
export type TotalChars1 = number;
export type Offset7 = number;
export type Part = "detail" | "parameters" | "result";
export type Seq10 = number;
export type SessionId67 = string;
export type BeforeSeq6 = number | null;
export type Items5 = TraceItem[];
export type JobIssues = string[];
export type Jobs = JsonObject[];
export type NextJobOffset = number | null;
export type Updates = TraceItem[];
export type Watermark1 = number;
export type BeforeSeq7 = number | null;
export type ErrorsOnly = boolean;
export type JobOffset = number;
export type Limit13 = number;
export type RunId17 = string | null;
export type SessionId68 = string;
export type Tool = string;
export type WatchSeqs = number[];
export type ModelId16 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type Action9 = "assign" | "claim" | "release" | "result";
export type MemberId10 = string | null;
export type OperationId24 = string;
export type Result3 = string | null;
export type RunId18 = string | null;
export type Status26 = ("planned" | "in_progress" | "completed" | "waiting") | null;
export type TaskId26 = string;
export type WorkId3 = string;
export type ExpectedRevision11 = number;
export type OperationId25 = string;
export type TaskId27 = string;
export type ExpectedRevision12 = number;
export type OperationId26 = string;
export type TaskId28 = string;
export type Goals1 = GoalView[];
export type Issues5 = string[];
export type Items6 = WorkItem[];
export type SuggestedItems = WorkItem[];
export type DefaultStyleId = string | null;
export type Issues6 = string[];
export type Styles = WorkStyle[];
export type ProjectId52 = string;
export type StyleId3 = string | null;
export type ProjectId53 = string | null;
export type Action10 = "stop" | "continue";
export type Prompt3 = string;
export type SessionId69 = string;
export type WorkerId = string;
export type ActiveSeconds1 = number;
export type ContextMode1 = "isolated" | "inherit";
export type Mode15 = "normal" | "plan";
export type Objective7 = string;
export type Role4 = "implement" | "research";
export type Scope18 = string;
export type Code13 = string | null;
export type CreatedAt15 = string;
export type GoalId8 = string | null;
export type ModelId17 = "glm-5.3-flash" | "deepseek-v4.1-flash";
export type OwnerRunId = string;
export type OwnerSessionId = string;
export type PendingMessages = string[];
export type Requests6 = number;
export type Result4 = string;
export type RunId19 = string | null;
export type SessionId70 = string;
export type Status27 = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Tools3 = number;
export type UpdatedAt12 = string;
export type WorkerId1 = string;
export type Workers = WorkerRecord[];
export type SessionId71 = string;
export type Issues7 = string[];
export type Templates1 = WorkflowTemplate[];
export type TerminalId5 = string;
export type Text13 = string;

export interface ProtocolV11 {
  ActiveRunResult: ActiveRunResult;
  AppInfo: AppInfo;
  ApplyWorkStyle: ApplyWorkStyle;
  ArrangeSessionWorkParams: ArrangeSessionWorkParams;
  AssignSessionParams: AssignSessionParams;
  Attachment: Attachment;
  AttachmentPage: AttachmentPage;
  AttachmentParams: AttachmentParams;
  AttachmentUpload: AttachmentUpload;
  AttachmentView: AttachmentView;
  BindEnvironmentParams: BindEnvironmentParams;
  BindSpaceMemberParams: BindSpaceMemberParams;
  CancelRunParams: CancelRunParams;
  CaptureWorkStyle: CaptureWorkStyle;
  ChangePage: ChangePage;
  ChangeView: ChangeView;
  CheckpointPage: CheckpointPage;
  CheckpointParams: CheckpointParams;
  ChooseDirectoryParams: ChooseDirectoryParams;
  ChooseEnvironmentPathParams: ChooseEnvironmentPathParams;
  CollaborationHistoryParams: CollaborationHistoryParams;
  CollaborationLink: CollaborationLink;
  CollaborationPage: CollaborationPage;
  CollaborationPageParams: CollaborationPageParams;
  CollaborationRequest: CollaborationRequest;
  CollaborationRequestParams: CollaborationRequestParams;
  ConfigureContextParams: ConfigureContextParams;
  ConfigureGitParams: ConfigureGitParams;
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
  CopyTeamTemplateParams: CopyTeamTemplateParams;
  CreateGoalParams: CreateGoalParams;
  CreateSessionParams: CreateSessionParams;
  CreateTaskParams: CreateTaskParams;
  CreateTaskResult: CreateTaskResult;
  CredentialInfo: CredentialInfo;
  DiagnosticCheck: DiagnosticCheck;
  DiagnosticReport: DiagnosticReport;
  DiagnosticsParams: DiagnosticsParams;
  DirectorySelection: DirectorySelection;
  DocumentChangeParams: DocumentChangeParams;
  DocumentDiff: DocumentDiff;
  DocumentDraft: DocumentDraft;
  DocumentListParams: DocumentListParams;
  DocumentListing: DocumentListing;
  DocumentOperationParams: DocumentOperationParams;
  DocumentParams: DocumentParams;
  DocumentSearchParams: DocumentSearchParams;
  DocumentSearchResult: DocumentSearchResult;
  DocumentSessionParams: DocumentSessionParams;
  DocumentView: DocumentView;
  DraftPage: DraftPage;
  EmptyParams: EmptyParams;
  EnableSkillParams: EnableSkillParams;
  EnvironmentCatalog: EnvironmentCatalog;
  EnvironmentParams: EnvironmentParams;
  EnvironmentProbe: EnvironmentProbe;
  EnvironmentProjectParams: EnvironmentProjectParams;
  ErrorData: ErrorData;
  ExecutionSettings: ExecutionSettings;
  ExecutionStatus: ExecutionStatus;
  ExportParams: ExportParams;
  ExportResult: ExportResult;
  ForgetMemoryParams: ForgetMemoryParams;
  GenerateTeamParams: GenerateTeamParams;
  GetChangeParams: GetChangeParams;
  GetProgramParams: GetProgramParams;
  GetSessionParams: GetSessionParams;
  GitCommitParams: GitCommitParams;
  GitCommitResult: GitCommitResult;
  GitDiff: GitDiff;
  GitDiffParams: GitDiffParams;
  GitHistory: GitHistory;
  GitHistoryParams: GitHistoryParams;
  GitPathsParams: GitPathsParams;
  GitProjectParams: GitProjectParams;
  GitSettings: GitSettings;
  GitStatus: GitStatus;
  GoalPage: GoalPage;
  GoalView: GoalView;
  HistoryPage: HistoryPage;
  HistoryParams: HistoryParams;
  ImageChunk: ImageChunk;
  ImportAttachment: ImportAttachment;
  ImportTeamTemplateParams: ImportTeamTemplateParams;
  InitializeParams: InitializeParams;
  InitializeResult: InitializeResult;
  IntelligenceParams: IntelligenceParams;
  LanguageQuery: LanguageQuery;
  LanguageResult: LanguageResult;
  LanguageServerCatalog: LanguageServerCatalog;
  ListChangesParams: ListChangesParams;
  ListGoalsParams: ListGoalsParams;
  ListMemoryParams: ListMemoryParams;
  ListProgramsParams: ListProgramsParams;
  ListSessionsParams: ListSessionsParams;
  ListTerminalsParams: ListTerminalsParams;
  MaintainMemoryParams: MaintainMemoryParams;
  McpArtifact: McpArtifact;
  McpArtifactParams: McpArtifactParams;
  McpCatalog: McpCatalog;
  McpControlParams: McpControlParams;
  McpParams: McpParams;
  MemoryPage: MemoryPage;
  MemoryParams: MemoryParams;
  ModelConnectionProbeParams: ModelConnectionProbeParams;
  NavigationItemName: NavigationItemName;
  OnlineSkillCancel: OnlineSkillCancel;
  OnlineSkillDocument: OnlineSkillDocument;
  OnlineSkillInspect: OnlineSkillInspect;
  OnlineSkillInstall: OnlineSkillInstall;
  OnlineSkillRead: OnlineSkillRead;
  OnlineSkillSearch: OnlineSkillSearch;
  OnlineSkillStatus: OnlineSkillStatus;
  OpenProjectParams: OpenProjectParams;
  OpenTerminalParams: OpenTerminalParams;
  OpenWebUrlParams: OpenWebUrlParams;
  OperationError: OperationError;
  OperationResult: OperationResult;
  ParseWorkStyle: ParseWorkStyle;
  ParseWorkflowParams: ParseWorkflowParams;
  PatchDocumentsParams: PatchDocumentsParams;
  PeerMessage: PeerMessage;
  PeerMessagePage: PeerMessagePage;
  PreviewCheckpointParams: PreviewCheckpointParams;
  ProgramPage: ProgramPage;
  ProgramParams: ProgramParams;
  ProgramView: ProgramView;
  ProjectSummary: ProjectSummary;
  ProjectsView: ProjectsView;
  PublicConfig: PublicConfig;
  ReadTerminalParams: ReadTerminalParams;
  RelocateProjectParams: RelocateProjectParams;
  RemoveEnvironmentParams: RemoveEnvironmentParams;
  RemoveWorkflowParams: RemoveWorkflowParams;
  RenameNavigationParams: RenameNavigationParams;
  ResizeTerminalParams: ResizeTerminalParams;
  RestoreCheckpointParams: RestoreCheckpointParams;
  RestorePreview: RestorePreview;
  RestoreResult: RestoreResult;
  RpcNotification: RpcNotification;
  RpcRequest: RpcRequest;
  RpcResponse: RpcResponse;
  RunLimits: RunLimits;
  SaveDocumentParams: SaveDocumentParams;
  SaveEnvironmentParams: SaveEnvironmentParams;
  SaveExecutionSettings: SaveExecutionSettings;
  SaveLanguageServers: SaveLanguageServers;
  SaveMcpParams: SaveMcpParams;
  SaveMemoryParams: SaveMemoryParams;
  SaveSkillParams: SaveSkillParams;
  SaveSpaceLayoutParams: SaveSpaceLayoutParams;
  SaveSpaceParams: SaveSpaceParams;
  SaveTeamTemplateParams: SaveTeamTemplateParams;
  SaveWorkGraphParams: SaveWorkGraphParams;
  SaveWorkStyle: SaveWorkStyle;
  SaveWorkflowParams: SaveWorkflowParams;
  SelectSessionModelParams: SelectSessionModelParams;
  SelectSkillsParams: SelectSkillsParams;
  SendMessageParams: SendMessageParams;
  SessionEventNotification: SessionEventNotification;
  SessionPage: SessionPage;
  SessionParams: SessionParams;
  SessionSignal: SessionSignal;
  SessionSummary: SessionSummary;
  SessionView: SessionView;
  SkillCatalog: SkillCatalog;
  SkillDocument: SkillDocument;
  SkillParams: SkillParams;
  SkillReadParams: SkillReadParams;
  SkillSiteControl: SkillSiteControl;
  SkillSiteLayout: SkillSiteLayout;
  SkillSiteSources: SkillSiteSources;
  SkillSiteState: SkillSiteState;
  SpaceChatPageParams: SpaceChatPageParams;
  SpaceChatParams: SpaceChatParams;
  SpaceChatView: SpaceChatView;
  SpaceParams: SpaceParams;
  SpaceResult: SpaceResult;
  SpaceStartParams: SpaceStartParams;
  StartRunParams: StartRunParams;
  StartSpaceRoundParams: StartSpaceRoundParams;
  StartWorkGraphParams: StartWorkGraphParams;
  StartupPaths: StartupPaths;
  StartupPathsParams: StartupPathsParams;
  StopSpaceRoundParams: StopSpaceRoundParams;
  StorageInfo: StorageInfo;
  TaskFields: TaskFields;
  TaskPage: TaskPage;
  TaskParams: TaskParams;
  TaskView: TaskView;
  TeamGeneration: TeamGeneration;
  TeamTemplate: TeamTemplate;
  TeamTemplateExport: TeamTemplateExport;
  TeamTemplateParams: TeamTemplateParams;
  TeamTemplatesResult: TeamTemplatesResult;
  TerminalControlParams: TerminalControlParams;
  TerminalPage: TerminalPage;
  TerminalParams: TerminalParams;
  TerminalView: TerminalView;
  TraceDetail: TraceDetail;
  TraceDetailParams: TraceDetailParams;
  TracePage: TracePage;
  TraceParams: TraceParams;
  UpdateConfigParams: UpdateConfigParams;
  UpdateSpaceWorkParams: UpdateSpaceWorkParams;
  UpdateTaskParams: UpdateTaskParams;
  UpdateTaskWorkflowParams: UpdateTaskWorkflowParams;
  WebPageResult: WebPageResult;
  WebSearchResult: WebSearchResult;
  WorkGraphView: WorkGraphView;
  WorkStyle: WorkStyle;
  WorkStyleCatalog: WorkStyleCatalog;
  WorkStyleDefault: WorkStyleDefault;
  WorkStyleQuery: WorkStyleQuery;
  WorkerControlParams: WorkerControlParams;
  WorkerPage: WorkerPage;
  WorkerSessionParams: WorkerSessionParams;
  WorkflowCatalog: WorkflowCatalog;
  WorkflowTemplate: WorkflowTemplate;
  WriteTerminalParams: WriteTerminalParams;
}
/**
 * 各会话的活动运行列表，切换视图仍可逐项停止。
 *
 * Active runs per session remain independently stoppable across views.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "AppInfo".
 */
export interface AppInfo {
  app_version: AppVersion;
  name: Name;
  protocol_version: ProtocolVersion;
  stage: Stage;
}
/**
 * 显式采用模板定义，保留已有任务目标和运行历史。
 *
 * Adopt definitions while keeping goals and run history.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ApplyWorkStyle".
 */
export interface ApplyWorkStyle {
  expected_revision: ExpectedRevision;
  expected_space_revision?: ExpectedSpaceRevision;
  operation_id: OperationId;
  style_id: StyleId;
  task_id: TaskId1;
}
/**
 * 用户主动交接 / 审查，停止身份只用于明确移交的工作。
 *
 * User-initiated handoff or review, with stop identities limited to transferred work.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ArrangeSessionWorkParams".
 */
export interface ArrangeSessionWorkParams {
  context_mode?: ContextMode;
  kind: Kind;
  notes?: Notes;
  objective: Objective;
  operation_id: OperationId1;
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "AssignSessionParams".
 */
export interface AssignSessionParams {
  operation_id: OperationId2;
  role?: Role1;
  scope?: Scope1;
  session_id: SessionId1;
  task_id: TaskId2;
}
/**
 * 文件快照或图片元信息，字节单独保存。
 * File snapshot or image metadata with separately stored bytes.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "Attachment".
 */
export interface Attachment {
  attachment_id: AttachmentId;
  created_at: CreatedAt1;
  draft?: Draft;
  end_line?: EndLine;
  kind: Kind1;
  mime: Mime;
  name: Name1;
  origin?: Origin;
  purpose?: Purpose;
  session_id: SessionId2;
  size_bytes: SizeBytes;
  source_path?: SourcePath;
  start_line?: StartLine;
}
/**
 * 原生选择器返回的已保存材料，取消返回空集合。
 *
 * Saved materials returned by the native picker; cancellation returns an empty collection.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "AttachmentPage".
 */
export interface AttachmentPage {
  attachments: Attachments;
}
/**
 * 按所属会话读取一个附件。 Read an attachment within its owning session.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "AttachmentParams".
 */
export interface AttachmentParams {
  attachment_id: AttachmentId1;
  offset?: Offset;
  session_id: SessionId3;
}
/**
 * 上传进度不表示模型已经看图。
 * Upload progress never means the model has inspected the image.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "AttachmentUpload".
 */
export interface AttachmentUpload {
  attachment?: Attachment | null;
  attachment_id: AttachmentId2;
  complete: Complete;
}
/**
 * 查看保存的文本或图片，只有显式预览返回图片数据。
 * View saved text or images; image data is returned only for explicit
 * preview.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "AttachmentView".
 */
export interface AttachmentView {
  attachment: Attachment;
  image_data?: ImageData;
  image_url?: ImageUrl;
  next_offset?: NextOffset;
  text?: Text;
}
/**
 * 用户保存项目默认环境与执行方式。
 *
 * Persist the user's default environment and execution mode.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "BindEnvironmentParams".
 */
export interface BindEnvironmentParams {
  environment_id: EnvironmentId;
  environment_passthrough?: EnvironmentPassthrough;
  expected_revision: ExpectedRevision1;
  mode: Mode2;
  project_id: ProjectId1;
  sandbox?: SandboxSettings;
  trusted?: Trusted;
}
/**
 * 原生沙箱的明确目录授权与网络能力。 Explicit native sandbox paths and network capabilities.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SandboxSettings".
 */
export interface SandboxSettings {
  authorization_timeout_seconds?: AuthorizationTimeoutSeconds;
  network?: Network;
  read_paths?: ReadPaths;
  write_paths?: WritePaths;
}
/**
 * 用户显式绑定已有会话或幂等创建新会话。
 *
 * Explicitly bind a session or idempotently create one.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "BindSpaceMemberParams".
 */
export interface BindSpaceMemberParams {
  member_id: MemberId;
  operation_id: OperationId3;
  session_id?: SessionId4;
  task_id: TaskId3;
}
/**
 * 只停止指定运行，不隐式停止其他任务。
 *
 * Cancel the specified run only.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CancelRunParams".
 */
export interface CancelRunParams {
  run_id: RunId1;
}
/**
 * 从任务生成预览，尚不写入模板库。 Preview a task-derived blueprint before library save.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CaptureWorkStyle".
 */
export interface CaptureWorkStyle {
  description?: Description;
  name: Name2;
  skill_ids?: SkillIds;
  style_id: StyleId1;
  task_id: TaskId4;
}
/**
 * 差异元数据页，损坏记录明确计数。 Metadata page with explicit unreadable-record count.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ChangePage".
 */
export interface ChangePage {
  changes: Changes;
  coverage?: Coverage;
  next_cursor: NextCursor;
  unavailable_count: UnavailableCount;
}
/**
 * 一次写入的来源与结果，准备状态不等于成功。
 *
 * Provenance and outcome; prepared is not success.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ChangeSummary".
 */
export interface ChangeSummary {
  after_sha256: AfterSha256;
  before_sha256: BeforeSha256;
  change_id: ChangeId;
  created_at: CreatedAt2;
  destination?: Destination;
  error?: Error;
  operation: Operation;
  path: Path;
  project_id: ProjectId2;
  run_id: RunId2;
  session_id: SessionId5;
  source?: Source;
  status: Status1;
  tool_call_id: ToolCallId;
}
/**
 * 历史修改的有界 diff；不代表当前磁盘内容。 Bounded historical diff, not live disk contents.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ChangeView".
 */
export interface ChangeView {
  diff: Diff;
  next_offset: NextOffset1;
  summary: ChangeSummary;
}
/**
 * 列出可恢复点和局部不可读记录。 List restore points and unreadable entries.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CheckpointPage".
 */
export interface CheckpointPage {
  checkpoints: Checkpoints;
  unavailable_count?: UnavailableCount1;
}
/**
 * 检查点来源与覆盖事实，不向模型暴露内容摘要键。 Checkpoint provenance and actual coverage.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "FileCheckpointSummary".
 */
export interface FileCheckpointSummary {
  before_seq: BeforeSeq;
  changed_files?: ChangedFiles;
  checkpoint_id: CheckpointId;
  created_at: CreatedAt3;
  finished_at?: FinishedAt;
  issues?: Issues;
  kind?: Kind2;
  project_id: ProjectId3;
  run_id: RunId3;
  session_id: SessionId6;
  status: Status2;
  title: Title1;
}
/**
 * 读取所选会话的代码起点。 Read code starting points for a selected session.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CheckpointParams".
 */
export interface CheckpointParams {
  session_id: SessionId7;
}
/**
 * 限定受信目录选择器的用途，不接受任意系统操作。
 *
 * Limit the trusted directory picker to its declared purpose.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ChooseDirectoryParams".
 */
export interface ChooseDirectoryParams {
  kind: Kind3;
}
/**
 * 选择已有环境入口。
 *
 * Select existing environment paths through a trusted picker.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ChooseEnvironmentPathParams".
 */
export interface ChooseEnvironmentPathParams {
  kind: Kind4;
}
/**
 * 按约定读取对方公开历史，保留分页与来源。
 *
 * Read permitted public history with pagination and provenance.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CollaborationHistoryParams".
 */
export interface CollaborationHistoryParams {
  before_seq?: BeforeSeq1;
  limit?: Limit;
  source_session_id: SourceSessionId1;
  target_session_id: TargetSessionId1;
}
/**
 * 会话访问约定，保存任务归属与修改时间。
 *
 * A session access agreement with task ownership and modification time.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CollaborationLink".
 */
export interface CollaborationLink {
  enabled?: Enabled;
  mode?: Mode3;
  scope: Scope2;
  source_session_id: SourceSessionId2;
  target_session_id: TargetSessionId2;
  task_id: TaskId5;
  updated_at: UpdatedAt1;
}
/**
 * 双方可见状态；约定方向不因展示而反转。
 *
 * Status visible to both parties without reversing access grants.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CollaborationPage".
 */
export interface CollaborationPage {
  candidates?: Candidates;
  error?: Error1;
  links: Links;
  next_cursor: NextCursor1;
  next_peer_cursor?: NextPeerCursor;
  next_step?: NextStep;
  reason?: Reason;
  requests: Requests1;
  task_id?: TaskId8;
  unavailable_peers?: UnavailablePeers;
  worker_enabled?: WorkerEnabled;
  worker_reason?: WorkerReason;
}
/**
 * 请求生命周期与精确运行来源，完成结果从运行事实读取。
 *
 * Request lifecycle and exact run provenance; results come from durable run facts.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CollaborationRequest".
 */
export interface CollaborationRequest {
  arrangement?: ArrangeSessionWorkParams | null;
  brief?: SessionWorkBrief | null;
  created_at: CreatedAt5;
  next_action?: NextAction1;
  outcome?: Outcome1;
  params: CollaborationRequestParams;
  parent_request_id?: ParentRequestId;
  reason?: Reason1;
  request_id: RequestId;
  result?: Result2;
  result_seq?: ResultSeq;
  schema_version?: SchemaVersion;
  scope: Scope5;
  source_run_id?: SourceRunId;
  status: Status9;
  target_run_id?: TargetRunId;
  task_id: TaskId7;
  updated_at: UpdatedAt7;
}
/**
 * 从已保存事实生成简报；成果快照不是当前磁盘内容。
 *
 * A brief from durable facts; artifact snapshots are not current disk contents.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
  session_id: SessionId9;
  status: Status6;
  usage: GoalUsage;
}
/**
 * 累计预算可留空，Run 仍使用自身限额，不引入固定续跑次数。
 *
 * Optional cumulative budgets coexist with run limits without a fixed continuation count.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GoalCriterion".
 */
export interface GoalCriterion {
  criterion_id: CriterionId;
  description: Description1;
}
/**
 * 一次完整工作运行的结构化结果；不会自行改变用户目标或任务状态。
 *
 * A structured work-run result that never changes the user's objective or task status.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CriterionResult".
 */
export interface CriterionResult {
  criterion_id: CriterionId1;
  evidence?: Evidence;
  explanation: Explanation;
  status: Status3;
}
/**
 * 模型声明的来源类别与用途，不等同于宿主验证通过。
 *
 * Model-declared source kinds and uses are not host-verified success.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EvidenceRef".
 */
export interface EvidenceRef {
  expectation?: Expectation;
  kind: Kind5;
  run_id: RunId4;
  seq: Seq;
  session_id: SessionId8;
}
/**
 * 本任务内需共享的决定，明确区分用户要求和建议。
 *
 * Task-local decisions distinguish user direction from proposals.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SharedDecision".
 */
export interface SharedDecision {
  status?: Status4;
  text: Text1;
}
/**
 * 需用户答复的具体问题及影响，不把闲聊或超时当作回答。
 *
 * A specific question and its impact, never answered by chatter or elapsed time.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkItem".
 */
export interface WorkItem {
  claim_status?: ClaimStatus;
  depends_on?: DependsOn;
  evidence?: Evidence1;
  feedback_from?: FeedbackFrom;
  feedback_to?: FeedbackTo;
  method?: Method1;
  owner_member_id?: OwnerMemberId;
  position?: WorkPosition | null;
  result?: Result;
  run_id?: RunId5;
  scope: Scope3;
  stage_id?: StageId;
  status: Status5;
  title: Title2;
  work_id: WorkId1;
}
/**
 * 用户保存的任务图位置，不参与执行排序。
 *
 * User-saved graph position, independent of scheduling.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkPosition".
 */
export interface WorkPosition {
  x: X;
  y: Y;
}
/**
 * 尚未开始回答的输入，不把排队显示成已执行。
 *
 * Input still waiting for an answer, never displayed as already executed.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GoalInputView".
 */
export interface GoalInputView {
  operation_id: OperationId4;
  prompt: Prompt;
}
/**
 * 从真实开始事实累计；未知耗时单独预留，不计离线时长。
 *
 * Count durable starts; reserve unknown durations separately without charging offline time.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TaskView".
 */
export interface TaskView {
  created_at: CreatedAt4;
  fields: TaskFields;
  initial_model_id: InitialModelId;
  initial_session_id: InitialSessionId;
  project_id: ProjectId4;
  revision: Revision1;
  source: Source1;
  task_id: TaskId6;
  updated_at: UpdatedAt2;
  work?: TaskWork;
  workflow?: TaskWorkflow | null;
  workstyle?: WorkStyle | null;
}
/**
 * 用户维护的共同信息；成果字段仅表示用户记录。
 *
 * User-maintained shared facts and artifact notes.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TaskFields".
 */
export interface TaskFields {
  artifacts?: Artifacts;
  constraints?: Constraints;
  decisions?: Decisions1;
  goal: Goal;
  progress?: Progress;
  status?: Status7;
  title: Title3;
  unresolved?: Unresolved;
}
/**
 * 任务当前工作图与最近一次报告，历史在任务版本日志保留。
 *
 * Current task work graph and latest report; task revisions preserve history.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TaskWork".
 */
export interface TaskWork {
  assignments?: Assignments;
  decisions?: Decisions2;
  items?: Items;
  last_report?: WorkReport | null;
  members?: Members;
  planned_items?: PlannedItems;
  removed_work_ids?: RemovedWorkIds;
  source?: EventRef | null;
}
/**
 * 宿主保存的工作承接事实，独立于模型报告并保留任务版本。
 *
 * Host-saved work assignments remain separate from model reports and task-versioned.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkAssignment".
 */
export interface WorkAssignment {
  claim_status: ClaimStatus1;
  owner_member_id?: OwnerMemberId1;
  progress_updated_at?: ProgressUpdatedAt;
  result?: Result1;
  run_id?: RunId6;
  status?: Status8;
  updated_at: UpdatedAt3;
  work_id: WorkId2;
}
/**
 * 共同决定保留聊天来源，不覆盖用户手写字段。
 *
 * Shared decisions retain sources without replacing user fields.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EventRef".
 */
export interface EventRef {
  run_id: RunId7;
  seq: Seq1;
  session_id: SessionId10;
}
/**
 * 宿主附加来源，保留模型判断与事实出处的区别。
 *
 * Host-attached provenance distinguishes a model judgment from its source facts.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SourcedWorkItem".
 */
export interface SourcedWorkItem {
  item: WorkItem;
  source: EventRef;
  updated_at?: UpdatedAt4;
}
/**
 * 各成员最新报告与宿主来源。
 *
 * Each member's latest report and host provenance.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "MemberProgress".
 */
export interface MemberProgress {
  report: WorkReport;
  source: EventRef;
  updated_at: UpdatedAt5;
}
/**
 * 模板快照与当前阶段、会话分工独立保存。
 *
 * Persist snapshot, current stage and assignments.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TaskWorkflow".
 */
export interface TaskWorkflow {
  current_stage_id?: CurrentStageId;
  session_stages?: SessionStages;
  template: WorkflowTemplate;
}
export interface SessionStages {
  [k: string]: string;
}
/**
 * 可分享的流程模板不含机器路径。
 *
 * Shareable template without machine-specific paths.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkflowTemplate".
 */
export interface WorkflowTemplate {
  description?: Description2;
  name: Name3;
  stages?: Stages;
  template_id: TemplateId;
}
/**
 * 阶段说明与依赖是接续信息，不构成执行门槛。
 *
 * Stages describe work without gating execution.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkflowStage".
 */
export interface WorkflowStage {
  artifacts?: Artifacts1;
  depends_on?: DependsOn1;
  feedback_to?: FeedbackTo1;
  goal?: Goal1;
  name: Name4;
  skills?: Skills;
  stage_id: StageId1;
  suggested_role?: SuggestedRole;
}
/**
 * 只含可复用定义，没有会话、运行、结果或凭据。
 *
 * Reusable definitions without sessions, runs or results.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkStyle".
 */
export interface WorkStyle {
  description?: Description3;
  name: Name5;
  skill_ids?: SkillIds1;
  style_id: StyleId2;
  team?: SpaceConfig;
  updated_at?: UpdatedAt6;
  workflow?: WorkflowTemplate | null;
}
/**
 * 可编辑组织预设、成员和图，允许反馈环。
 *
 * Editable organisation, members and graph allowing cycles.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceConfig".
 */
export interface SpaceConfig {
  edges?: Edges;
  initial_work_items?: InitialWorkItems;
  members?: Members1;
  organisation?: Organisation;
  receiver_member_id?: ReceiverMemberId;
}
/**
 * 描述协作关系的有向连线，不是通信白名单。
 *
 * Descriptive directed links, not communication grants.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceEdge".
 */
export interface SpaceEdge {
  edge_id: EdgeId;
  kind: Kind6;
  label?: Label;
  source_member_id: SourceMemberId;
  target_member_id: TargetMemberId;
}
/**
 * 独立于会话的稳定成员身份与职责。
 *
 * Stable member identity and duties independent of sessions.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceMember".
 */
export interface SpaceMember {
  member_id: MemberId1;
  model_id: ModelId1;
  name: Name6;
  position?: SpacePosition;
  role?: Role2;
  scope?: Scope4;
  skill_ids?: SkillIds2;
}
/**
 * 用户保存的节点位置。
 *
 * User-saved node coordinates.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpacePosition".
 */
export interface SpacePosition {
  x?: X1;
  y?: Y1;
}
/**
 * 明确的协作工作和返回要求，操作 ID 用于幂等投递。
 *
 * A bounded assignment and return requirements with an idempotent operation ID.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CollaborationRequestParams".
 */
export interface CollaborationRequestParams {
  expected_result?: ExpectedResult;
  inputs?: Inputs;
  mode?: Mode4;
  objective: Objective2;
  operation_id: OperationId5;
  source_session_id: SourceSessionId4;
  target_session_id: TargetSessionId3;
}
/**
 * 本会话的约定和请求分页。
 *
 * Page this session's agreements and requests.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CollaborationPageParams".
 */
export interface CollaborationPageParams {
  cursor?: Cursor;
  limit?: Limit1;
  peer_cursor?: PeerCursor;
  session_id: SessionId11;
}
/**
 * 保存后续请求采用的整理设置。
 *
 * Save compaction settings for subsequent requests.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ConfigureContextParams".
 */
export interface ConfigureContextParams {
  session_id: SessionId12;
  settings: ContextSettings;
}
/**
 * 绝对 token 整理预算；与模型容量及生成额度分别管理。
 *
 * Absolute token policy, separate from model capacity and generation allowance.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ContextSettings".
 */
export interface ContextSettings {
  active_tools?: ActiveTools;
  auto_trigger_tokens?: AutoTriggerTokens;
  automatic?: Automatic;
  background_compaction?: BackgroundCompaction;
  core_tools?: CoreTools;
  keep_recent_tokens?: KeepRecentTokens;
  rollback?: RollbackSettings;
  skill_catalog_tokens?: SkillCatalogTokens;
  summary_output_tokens?: SummaryOutputTokens;
  summary_target_tokens?: SummaryTargetTokens;
  tool_loading?: ToolLoading;
  tool_result_preview_tokens?: ToolResultPreviewTokens;
}
/**
 * 只限制检查点覆盖范围，不限制编码任务。 Bound checkpoint coverage, never coding execution.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RollbackSettings".
 */
export interface RollbackSettings {
  enabled?: Enabled1;
  max_file_bytes?: MaxFileBytes1;
  max_total_bytes?: MaxTotalBytes;
}
/**
 * 用户切换 Git；关闭移走自身元数据，开启恢复。
 *
 * Toggle Git with recoverable metadata relocation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ConfigureGitParams".
 */
export interface ConfigureGitParams {
  enabled: Enabled2;
  project_id: ProjectId5;
}
/**
 * 保存会话的使用、贡献和实验选项。
 *
 * Save session use, contribution and experiment settings.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ConfigureMemoryParams".
 */
export interface ConfigureMemoryParams {
  session_id: SessionId13;
  settings: MemorySettings;
}
/**
 * 使用和贡献分别控制，实验默认关闭。
 *
 * Independent use/contribution controls; experiments start disabled.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ConfigureWorkersParams".
 */
export interface ConfigureWorkersParams {
  session_id: SessionId14;
  settings: WorkerSettings;
}
/**
 * 默认关闭；并发是可调资源配置。
 *
 * Disabled by default; concurrency is an adjustable resource setting.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkerSettings".
 */
export interface WorkerSettings {
  concurrency?: Concurrency;
  enabled?: Enabled3;
}
/**
 * 用户指定定向协作范围；禁用只影响后续访问。
 *
 * A user-defined directional agreement; disabling affects subsequent access.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ConnectSessionsParams".
 */
export interface ConnectSessionsParams {
  enabled?: Enabled4;
  mode?: Mode5;
  scope: Scope6;
  source_session_id: SourceSessionId5;
  target_session_id: TargetSessionId4;
}
/**
 * 每次手动探测明确指定总等待时间。 Specify the total timeout for one manual probe.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ConnectionProbeParams".
 */
export interface ConnectionProbeParams {
  timeout_seconds: TimeoutSeconds;
}
/**
 * 持久化复用偏好与手动探测等待时间。 Persist reuse preference and manual probe timeout.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ConnectionObservation".
 */
export interface ConnectionObservation {
  code: Code2;
  finished_at: FinishedAt1;
  http_status: HttpStatus;
  model_id?: ModelId2;
  models_confirmed: ModelsConfirmed;
  progress: ModelProgress;
}
/**
 * 请求阶段与单调时钟耗时，不包含网络原文。 Request phases and timings without raw payloads.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ModelConnectionState".
 */
export interface ModelConnectionState {
  last_test: ModelConnectionResult | null;
  model_id: ModelId3;
  progress: ModelProgress | null;
  testing: Testing;
}
/**
 * 单次真实模型测试的公开结果，不包含提示或回答。
 *
 * Public facts from one real model test, excluding prompts and responses.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ModelConnectionResult".
 */
export interface ModelConnectionResult {
  code: Code3;
  finished_at: FinishedAt2;
  message: Message1;
  progress: ModelProgress;
  remediation: Remediation;
  usage: TokenUsage | null;
}
/**
 * 服务实际返回的用量；未知保留 null。 Reported usage; unknown remains null.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TokenUsage".
 */
export interface TokenUsage {
  cached_input_tokens?: CachedInputTokens;
  input_tokens: InputTokens2;
  output_tokens: OutputTokens2;
}
/**
 * 定位本会话的窗口。
 *
 * Identify a session window.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ContextParams".
 */
export interface ContextParams {
  session_id: SessionId15;
}
/**
 * 输入区的 token 观察、字节处理量与整理事实。
 *
 * Token observations, byte processing sizes and compaction facts for the composer.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
  session_id: SessionId16;
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "Checkpoint".
 */
export interface Checkpoint {
  checkpoint_id: CheckpointId1;
  created_at: CreatedAt6;
  model_id: ModelId4;
  parent_id: ParentId;
  text: Text2;
  through_seq: ThroughSeq;
  usage: TokenUsage;
}
/**
 * 辅助整理的真实状态和累计用量。
 *
 * Actual maintenance state and cumulative usage.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ContextJob".
 */
export interface ContextJob {
  background?: Background;
  compression_applied?: CompressionApplied;
  finish_reason?: FinishReason;
  finished_at?: FinishedAt3;
  history_after_bytes?: HistoryAfterBytes;
  history_after_tokens?: HistoryAfterTokens;
  history_before_bytes?: HistoryBeforeBytes;
  history_before_tokens?: HistoryBeforeTokens;
  job_id: JobId;
  message?: Message2;
  mode?: Mode6;
  model_id: ModelId5;
  outcome?: Outcome2;
  output_token_limit?: OutputTokenLimit;
  policy?: ContextSettings | null;
  requests?: Requests3;
  retained_tokens?: RetainedTokens;
  run_id: RunId8;
  started_at: StartedAt;
  status: Status10;
  through_seq?: ThroughSeq1;
  usage?: TokenUsage;
}
/**
 * 最近请求的固定材料事实，后续设置不会改写。
 *
 * Fixed facts for the latest request, unaffected by later settings.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ContextRequest".
 */
export interface ContextRequest {
  at: At;
  manifest: ContextManifest;
  message_id: MessageId;
  model_id: ModelId6;
}
/**
 * 请求边界保存实际材料与单独标注的 token 估计。
 *
 * Persist actual materials and separately labelled token estimates at the request boundary.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ContextMaterial".
 */
export interface ContextMaterial {
  form: Form;
  kind: Kind7;
  preview?: Preview;
  preview_complete?: PreviewComplete;
  read_arguments?: JsonObject;
  read_tool?: ReadTool;
  reason: Reason2;
  revision?: Revision2;
  source_id?: SourceId;
  title: Title4;
}
/**
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ContextTokens".
 */
export interface ContextTokens {
  input_tokens?: InputTokens3;
  model_id: ModelId7;
  status?: Status11;
  window_source: WindowSource;
  window_tokens: WindowTokens;
}
/**
 * 已报告 token 与未知用量分别计数。
 *
 * Separate reported tokens from unknown usage.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ControlCollaborationParams".
 */
export interface ControlCollaborationParams {
  action: Action;
  request_id: RequestId1;
}
/**
 * 无附带预算或答复的状态控制。 State controls without hidden budgets or answers.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GoalStateControl".
 */
export interface GoalStateControl {
  action: Action1;
  expected_revision: ExpectedRevision2;
  goal_id: GoalId2;
  operation_id: OperationId6;
  session_id: SessionId17;
}
/**
 * 明确替换累计预算，不自动接续。 Explicitly replace cumulative budgets without resuming.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GoalBudgetControl".
 */
export interface GoalBudgetControl {
  action: Action2;
  budget: GoalBudget;
  expected_revision: ExpectedRevision3;
  goal_id: GoalId3;
  operation_id: OperationId7;
  session_id: SessionId18;
}
/**
 * 只回答指定 HITL 问题，不把普通问题当成答复。
 *
 * Answer only the named HITL question, never interpreting ordinary chatter as an answer.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GoalAnswerControl".
 */
export interface GoalAnswerControl {
  action: Action3;
  answer: Answer;
  expected_revision: ExpectedRevision4;
  goal_id: GoalId4;
  operation_id: OperationId8;
  question_id: QuestionId1;
  session_id: SessionId19;
}
/**
 * 显式复制模板为独立快照。
 *
 * Explicitly copy a template into an independent snapshot.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CopyTeamTemplateParams".
 */
export interface CopyTeamTemplateParams {
  name: Name7;
  new_template_id: NewTemplateId;
  template_id: TemplateId1;
}
/**
 * 由用户在既有会话创建目标，不创建正式会话。
 *
 * Create a user goal in an existing session without creating a formal session.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CreateGoalParams".
 */
export interface CreateGoalParams {
  attachment_ids?: AttachmentIds;
  budget: GoalBudget;
  criteria: Criteria2;
  goal_id: GoalId5;
  limits?: RunLimits | null;
  method?: Method2;
  objective: Objective3;
  session_id: SessionId20;
}
/**
 * 选择项目与模型，不发起运行。
 *
 * Select project and model without starting a run.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CreateSessionParams".
 */
export interface CreateSessionParams {
  model_id: ModelId8;
  operation_id?: OperationId9;
  project_id: ProjectId6;
  role?: Role3;
  scope?: Scope7;
  task_id?: TaskId9;
}
/**
 * 一次创建操作同时预留首会话身份，重试不重复创建。
 *
 * Reserve the first session for idempotent creation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CreateTaskParams".
 */
export interface CreateTaskParams {
  fields: TaskFields;
  model_id: ModelId9;
  operation_id: OperationId10;
  project_id: ProjectId7;
  use_project_workstyle?: UseProjectWorkstyle;
  workflow_template_id?: WorkflowTemplateId;
  workstyle_id?: WorkstyleId;
}
/**
 * 分开表达任务保存与首会话创建，失败可显式接续。
 *
 * Distinguish task saving from session creation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CredentialInfo".
 */
export interface CredentialInfo {
  env_var: EnvVar;
  present: Present;
  source: Source2;
}
/**
 * 单项诊断的公开结论、影响与脱敏证据。
 *
 * Public outcome, impact and sanitized evidence for one diagnostic check.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DiagnosticCheck".
 */
export interface DiagnosticCheck {
  blocking: Blocking;
  check_id: CheckId;
  code: Code4;
  evidence: Evidence2;
  remediation: Remediation1;
  status: Status12;
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DiagnosticsParams".
 */
export interface DiagnosticsParams {
  dev: Dev;
  network: Network1;
  network_timeout_seconds?: NetworkTimeoutSeconds;
  write_probe: WriteProbe;
}
/**
 * 返回已选择目录；null 明确表示取消选择。
 *
 * Return the selected directory, with null explicitly representing cancellation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DirectorySelection".
 */
export interface DirectorySelection {
  path: Path1;
}
/**
 * 只选择一个历史修改。
 *
 * Select one historical change.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentChangeParams".
 */
export interface DocumentChangeParams {
  change_id: ChangeId1;
  session_id: SessionId21;
}
/**
 * 历史两端与当前磁盘分别呈现。
 *
 * Present historical snapshots and current disk separately.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentDiff".
 */
export interface DocumentDiff {
  after: After;
  before: Before;
  current: Current;
  current_exists: CurrentExists;
  message?: Message3;
  restorable: Restorable;
  summary: ChangeSummary;
}
/**
 * 保存未写入项目的缓冲与恢复基线。
 *
 * Persist an unsaved buffer and its recovery baseline.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentDraft".
 */
export interface DocumentDraft {
  base_content: BaseContent;
  content: Content;
  path: Path2;
  session_id: SessionId22;
  updated_at?: UpdatedAt8;
}
/**
 * 有界文件发现与快速打开查询。
 *
 * Bounded file discovery and quick-open filtering.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentListParams".
 */
export interface DocumentListParams {
  directory?: Directory;
  limit?: Limit2;
  query?: Query;
  session_id: SessionId23;
}
/**
 * 发现得到的文件和目录，明确截断。
 *
 * Discovered files and directories with explicit truncation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentListing".
 */
export interface DocumentListing {
  directories: Directories;
  files: Files;
  skipped: Skipped;
  truncated: Truncated;
}
/**
 * 明确选定文件操作与目的地。
 *
 * An explicitly selected file operation and destination.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentOperationParams".
 */
export interface DocumentOperationParams {
  content?: Content1;
  destination?: Destination1;
  operation: Operation1;
  path: Path3;
  recursive?: Recursive;
  session_id: SessionId24;
}
/**
 * 指定文件而不自动扫描项目外内容。
 *
 * Select a file without scanning outside the project.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentParams".
 */
export interface DocumentParams {
  path: Path4;
  session_id: SessionId25;
}
/**
 * 与模型共享的项目文本搜索。
 *
 * Project text search shared with model tools.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentSearchParams".
 */
export interface DocumentSearchParams {
  after?: After1;
  before?: Before1;
  exclude_globs?: ExcludeGlobs1;
  glob?: Glob;
  include_globs?: IncludeGlobs;
  limit?: Limit3;
  query: Query1;
  regex?: Regex;
  session_id: SessionId26;
}
/**
 * 搜索命中与不可读数量。
 *
 * Search matches and unreadable counts.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentSearchResult".
 */
export interface DocumentSearchResult {
  backend: Backend;
  matches: Matches;
  skipped: Skipped1;
  truncated: Truncated1;
}
/**
 * 匹配位置与当前文本。
 *
 * A match location and current line text.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentMatch".
 */
export interface DocumentMatch {
  context_after?: ContextAfter;
  context_before?: ContextBefore;
  line: Line1;
  path: Path5;
  text: Text4;
}
/**
 * 带行号的搜索上下文。 Numbered search context.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentContextLine".
 */
export interface DocumentContextLine {
  line: Line;
  text: Text3;
}
/**
 * 以会话定位项目与草稿。
 *
 * Locate projects and drafts by session.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentSessionParams".
 */
export interface DocumentSessionParams {
  session_id: SessionId27;
}
/**
 * 完整可编辑文本及其读取事实。
 *
 * Complete editable text with read facts.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DocumentView".
 */
export interface DocumentView {
  change_id?: ChangeId2;
  content: Content2;
  encoding: Encoding;
  newline: Newline;
  path: Path6;
  read_at: ReadAt;
}
/**
 * 会话的可恢复草稿。
 *
 * Recoverable drafts for a session.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "DraftPage".
 */
export interface DraftPage {
  drafts: Drafts;
}
/**
 * 表示不接受参数的方法，拒绝任何额外字段。
 *
 * Represent parameterless methods and reject every extra field.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EmptyParams".
 */
export interface EmptyParams {}
/**
 * 保存一项资源的启停。 Persist resource enablement.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EnableSkillParams".
 */
export interface EnableSkillParams {
  enabled: Enabled5;
  project_id?: ProjectId8;
  session_id?: SessionId28;
  skill_id: SkillId;
}
/**
 * 设置页的可公开环境与当前项目绑定。
 *
 * Public environment settings and current project binding.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EnvironmentCatalog".
 */
export interface EnvironmentCatalog {
  binding: ProjectExecution | null;
  environments: Environments;
  revision: Revision3;
  sandbox_issue?: SandboxIssue;
  settings: ExecutionSettings;
}
/**
 * 项目唯一默认环境和后续执行方式。
 *
 * A project's default environment and future execution policy.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ProjectExecution".
 */
export interface ProjectExecution {
  environment_id: EnvironmentId1;
  environment_passthrough?: EnvironmentPassthrough1;
  mode: Mode8;
  project_id: ProjectId9;
  sandbox?: SandboxSettings;
  trusted?: Trusted1;
}
/**
 * 登记事实与当前路径可用性，未经探测不冒充版本已验证。
 *
 * Registration and live path availability, without claiming unperformed probes.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EnvironmentView".
 */
export interface EnvironmentView {
  available: Available;
  execution?: ProjectExecution | null;
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EnvironmentRecord".
 */
export interface EnvironmentRecord {
  definition: Definition;
  environment_id: EnvironmentId2;
  name: Name8;
  probe?: EnvironmentProbe | null;
}
/**
 * 用户显式选择已有本机工具，不虚构 Python 绑定。
 *
 * Explicit existing system-tool selection.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SystemEnvironment".
 */
export interface SystemEnvironment {
  kind: Kind8;
}
/**
 * 已有解释器，项目相对路径在启动时解析。
 *
 * Existing interpreter with launch-time project paths.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "PythonEnvironment".
 */
export interface PythonEnvironment {
  interpreter: Interpreter1;
  kind: Kind9;
  scope: Scope8;
}
/**
 * Conda 安装入口和明确 prefix，不默认使用 base。
 *
 * Explicit Conda launcher and environment prefix.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "CondaEnvironment".
 */
export interface CondaEnvironment {
  kind: Kind10;
  launcher: Launcher1;
  prefix: Prefix1;
  scope: Scope9;
}
/**
 * 登记 uv 与已有解释器，普通运行不自动同步依赖。
 *
 * Register uv and an existing interpreter.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "UvEnvironment".
 */
export interface UvEnvironment {
  interpreter: Interpreter2;
  kind: Kind11;
  launcher: Launcher2;
  scope: Scope10;
}
/**
 * 显式探测结果及其实际路径来源。
 *
 * Explicit probe evidence with its actual path context.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EnvironmentProbe".
 */
export interface EnvironmentProbe {
  checked_at: CheckedAt1;
  code: Code5;
  interpreter: Interpreter3;
  launcher_version: LauncherVersion;
  message: Message4;
  project_id: ProjectId10;
  version: Version;
}
/**
 * 新启动程序采用的可调预算；持续服务不套用命令寿命。
 *
 * Adjustable launch budgets; retained services have no command-lifetime timeout.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EnvironmentParams".
 */
export interface EnvironmentParams {
  environment_id: EnvironmentId3;
  project_id: ProjectId11;
}
/**
 * 可选项目用于解析相对环境。
 *
 * Optional project context for relative environments.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EnvironmentProjectParams".
 */
export interface EnvironmentProjectParams {
  project_id: ProjectId12;
}
/**
 * RPC 错误的稳定业务码与修复说明。
 *
 * Stable application error code and remediation inside an RPC error.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ProgramSummary".
 */
export interface ProgramSummary {
  code: Code7;
  command: Command;
  created_at: CreatedAt7;
  cwd: Cwd;
  dropped_bytes?: DroppedBytes;
  environment_id: EnvironmentId4;
  environment_name: EnvironmentName;
  environment_revision: EnvironmentRevision;
  exit_code: ExitCode;
  finished_at: FinishedAt4;
  http_status: HttpStatus1;
  kind: Kind14;
  message: Message5;
  mode?: Mode9;
  pid: Pid;
  program_id: ProgramId;
  project_id: ProjectId13;
  resolved_command: ResolvedCommand;
  retained: Retained;
  run_id: RunId9;
  session_id: SessionId29;
  status: Status13;
  tool_call_id?: ToolCallId1;
  url: Url;
}
/**
 * 程序和参数数组直接执行，不猜测 shell 转义。
 *
 * Execute an explicit program and argument array.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ProgramCommand".
 */
export interface ProgramCommand {
  arguments?: Arguments;
  kind: Kind12;
  program: Program;
}
/**
 * 用户任务中的显式 PowerShell 脚本，与普通 argv 区分。
 *
 * Explicit PowerShell, distinct from argv.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ShellCommand".
 */
export interface ShellCommand {
  kind: Kind13;
  script: Script;
}
/**
 * 限定导出的公开文档类型，内容由后端提供。
 *
 * Select a public export category whose content comes from the backend.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ExportParams".
 */
export interface ExportParams {
  kind: Kind15;
}
/**
 * 返回成功导出的文件位置；null 表示用户取消。
 *
 * Return the exported file location, or null when the user cancels.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ExportResult".
 */
export interface ExportResult {
  path: Path7;
}
/**
 * 删除条目正文而不删除聊天。
 *
 * Delete entry content, not conversation history.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ForgetMemoryParams".
 */
export interface ForgetMemoryParams {
  memory_id: MemoryId;
  session_id: SessionId30;
}
/**
 * 在用户选择的现有会话执行只读生成。
 *
 * Generate through a selected existing read-only session.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GenerateTeamParams".
 */
export interface GenerateTeamParams {
  objective: Objective4;
  operation_id: OperationId11;
  organisation?: Organisation1;
  session_id: SessionId31;
  task_id: TaskId10;
}
/**
 * 按成果身份与字符游标读取差异。 Read a change by identity and character cursor.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GetChangeParams".
 */
export interface GetChangeParams {
  change_id: ChangeId3;
  offset?: Offset1;
  session_id: SessionId32;
}
/**
 * 从已看到的输出序号继续读取。
 *
 * Continue reading after the last observed output sequence.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GetSessionParams".
 */
export interface GetSessionParams {
  before_seq: BeforeSeq2;
  session_id: SessionId33;
}
/**
 * 用户明确提交现有暂存区，不自动 stage 或设置身份。
 *
 * Commit existing index without staging.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitCommitParams".
 */
export interface GitCommitParams {
  message: Message6;
  project_id: ProjectId14;
}
/**
 * 提交完成后的真实 HEAD 与命令输出。
 *
 * Actual HEAD and output after commit.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitCommitResult".
 */
export interface GitCommitResult {
  commit_id: CommitId;
  output: Output;
  project_id: ProjectId15;
}
/**
 * 作为纯文本显示的当前本地差异。
 *
 * Current local diff displayed as plain text.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitDiff".
 */
export interface GitDiff {
  area: Area;
  path: Path8;
  project_id: ProjectId16;
  text: Text5;
  truncated: Truncated2;
}
/**
 * 明确查看工作区或暂存区的一个路径。
 *
 * Read one worktree or index path diff.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitDiffParams".
 */
export interface GitDiffParams {
  area?: Area1;
  path: Path9;
  project_id: ProjectId17;
}
/**
 * 本地提交列表。
 *
 * Local commit list.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitHistory".
 */
export interface GitHistory {
  commits: Commits;
  project_id: ProjectId18;
}
/**
 * 本地提交身份与简要历史，不公开 Git 配置。
 *
 * Local commit identity and concise history.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitCommit".
 */
export interface GitCommit {
  author: Author;
  authored_at: AuthoredAt;
  commit_id: CommitId1;
  subject: Subject;
}
/**
 * 本地历史的可调查询大小。
 *
 * Adjustable local-history query size.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitHistoryParams".
 */
export interface GitHistoryParams {
  limit?: Limit4;
  project_id: ProjectId19;
}
/**
 * 按明确文件操作，不能以空路径列表提交全部。
 *
 * Operate on explicit paths only.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitPathsParams".
 */
export interface GitPathsParams {
  paths: Paths;
  project_id: ProjectId20;
}
/**
 * 已登记项目身份。
 *
 * Registered project identity.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitProjectParams".
 */
export interface GitProjectParams {
  project_id: ProjectId21;
}
/**
 * 开关与实际备份事实，不探测上层仓库。
 *
 * Switch and actual backup facts, without parent discovery.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitSettings".
 */
export interface GitSettings {
  backup_path?: BackupPath;
  enabled?: Enabled6;
  project_id: ProjectId22;
  project_metadata_present?: ProjectMetadataPresent;
}
/**
 * 工具可用性与仓库事实，不需要 remote。
 *
 * Availability and repository facts without remote.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitStatus".
 */
export interface GitStatus {
  available: Available1;
  branch: Branch;
  code?: Code8;
  files: Files1;
  message?: Message7;
  project_id: ProjectId23;
  project_repository?: ProjectRepository;
  repository: Repository;
  repository_root?: RepositoryRoot;
}
/**
 * Git 的工作区与暂存区双列状态。
 *
 * Git's separate worktree and index status columns.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GitFileStatus".
 */
export interface GitFileStatus {
  index_status: IndexStatus;
  original_path?: OriginalPath;
  path: Path10;
  worktree_status: WorktreeStatus;
}
/**
 * 按创建事实倒序分页，旧目标不被新目标覆盖。
 *
 * Page goals by descending creation sequence without overwriting older objectives.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "GoalPage".
 */
export interface GoalPage {
  before_seq: BeforeSeq3;
  goals: Goals;
}
/**
 * 可直接展开的材料索引及匹配数。
 *
 * Expandable material index and match count.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "HistoryPage".
 */
export interface HistoryPage {
  complete: Complete1;
  items: Items1;
  match_unit?: MatchUnit;
  matches: Matches1;
  next_after_seq: NextAfterSeq;
  through_seq: ThroughSeq2;
}
/**
 * 公开材料片段，保留原序号和续读位置。
 *
 * Public fragment with original sequence and continuation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "HistoryItem".
 */
export interface HistoryItem {
  call_seq?: CallSeq;
  kind: Kind16;
  next_offset: NextOffset2;
  offset: Offset2;
  result_seq?: ResultSeq1;
  seq: Seq2;
  text: Text6;
  tool_call_id?: ToolCallId2;
  tool_name?: ToolName;
  total_chars: TotalChars;
}
/**
 * 桌面读取指定会话的历史。
 *
 * Read a selected session's history from the desktop.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "HistoryParams".
 */
export interface HistoryParams {
  after_seq?: AfterSeq1;
  artifact_id?: ArtifactId;
  entry_seq?: EntrySeq;
  include_lookup_results?: IncludeLookupResults;
  limit?: Limit5;
  max_chars?: MaxChars;
  offset?: Offset3;
  query?: Query2;
  session_id: SessionId34;
  through_seq?: ThroughSeq3;
}
/**
 * 分块经过原协议大小边界，完成才用于请求。
 * Chunk within the existing protocol frame boundary; use only
 * completed
 * uploads.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ImageChunk".
 */
export interface ImageChunk {
  attachment_id?: AttachmentId3;
  data: Data;
  final: Final;
  mime: Mime1;
  name: Name9;
  purpose?: Purpose1;
  session_id: SessionId35;
}
/**
 * 显式选择文件，或从编辑器提交未保存选区。
 * Explicit file selection or an unsaved editor selection.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ImportAttachment".
 */
export interface ImportAttachment {
  content?: Content3;
  draft?: Draft1;
  end_line?: EndLine1;
  path: Path11;
  purpose?: Purpose2;
  session_id: SessionId36;
  start_line?: StartLine1;
}
/**
 * 导入 JSON 为新的本地模板，不绑定会话。
 *
 * Import JSON as a new local template without session bindings.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ImportTeamTemplateParams".
 */
export interface ImportTeamTemplateParams {
  content: Content4;
  template_id: TemplateId2;
}
/**
 * 前端声明的兼容性信息；应用版本与协议版本分别处理。
 *
 * Client compatibility information, keeping app and protocol versions distinct.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "PublicConfig".
 */
export interface PublicConfig {
  allowed_models: AllowedModels;
  api: Api;
  base_url: BaseUrl;
  config_path: ConfigPath;
  credential: CredentialInfo;
  http: ConnectionSettings;
  model_id: ModelId10;
  model_source: ModelSource;
  provider: Provider;
  run: RunLimits;
}
/**
 * 同时返回当前项目与最近记录，允许初次启动为空。
 *
 * Return active and recent projects, allowing an empty first-launch state.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ProjectSummary".
 */
export interface ProjectSummary {
  available: Available2;
  canonical_path: CanonicalPath;
  last_opened_at: LastOpenedAt;
  name: Name10;
  path: Path12;
  project_id: ProjectId24;
  unavailable_code: UnavailableCode;
}
/**
 * 展示实际数据根、配置来源和存储可用状态。
 *
 * Expose the effective data root, its source and storage availability.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "StorageInfo".
 */
export interface StorageInfo {
  data_dir: DataDir;
  data_schema_version: DataSchemaVersion1;
  source: Source3;
  status: Status14;
}
/**
 * 限定当前项目的服务操作。
 *
 * Scope service operations to the current project.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "IntelligenceParams".
 */
export interface IntelligenceParams {
  project_id: ProjectId25;
}
/**
 * 位置为 LSP 零基 UTF-16；内容为空时读取磁盘。
 *
 * Positions use LSP zero-based UTF-16; absent text reads disk.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "LanguageQuery".
 */
export interface LanguageQuery {
  action: Action4;
  character?: Character;
  content?: Content5;
  language: Language;
  line?: Line2;
  new_name?: NewName;
  path: Path13;
  project_id: ProjectId26;
  version?: Version1;
}
/**
 * 返回服务原生资料及所用材料，不将诊断当成测试。
 *
 * Return native data and input provenance, not test results.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "LanguageResult".
 */
export interface LanguageResult {
  action: Action5;
  content: Content6;
  observed_at: ObservedAt;
  path: Path14;
  project_id: ProjectId27;
  rename_documents?: RenameDocuments;
  result: JsonValue;
  server_id: ServerId;
  source: Source5;
  version: Version3;
}
/**
 * 重命名建议所用正文；无法读取时保留局部错误。
 *
 * Text snapshots for rename suggestions, retaining local errors when unavailable.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "LanguageDocumentSnapshot".
 */
export interface LanguageDocumentSnapshot {
  content: Content7;
  error?: Error2;
  path: Path15;
  source: Source4;
  version: Version2;
}
/**
 * 配置与实际状态分开显示。
 *
 * Display configuration separately from actual state.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "LanguageServerCatalog".
 */
export interface LanguageServerCatalog {
  project_id: ProjectId28;
  servers: Servers;
  states?: States;
  timeout_seconds?: TimeoutSeconds1;
}
/**
 * 一个显式登记的 stdio 服务，不在启动时安装。
 *
 * An explicit stdio server, never installed on startup.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "LanguageServer".
 */
export interface LanguageServer {
  arguments?: Arguments1;
  enabled?: Enabled7;
  initialization_options?: InitializationOptions;
  languages: Languages;
  program: Program1;
  server_id: ServerId1;
  settings?: Settings;
}
export interface InitializationOptions {
  [k: string]: JsonValue;
}
export interface Settings {
  [k: string]: JsonValue;
}
/**
 * 真实连接状态与最后错误。
 *
 * Actual connection state and last error.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "LanguageServerState".
 */
export interface LanguageServerState {
  message?: Message8;
  server_id: ServerId2;
  status: Status15;
}
/**
 * 会话内分页，不接受文件系统路径。 Page by session without filesystem path input.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ListChangesParams".
 */
export interface ListChangesParams {
  cursor: Cursor1;
  limit?: Limit6;
  path?: Path16;
  scope?: Scope11;
  session_id: SessionId37;
}
/**
 * 按事实游标读取有界目标列表。 Read bounded goals by fact cursor.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ListGoalsParams".
 */
export interface ListGoalsParams {
  before_seq?: BeforeSeq4;
  limit?: Limit7;
  session_id: SessionId38;
}
/**
 * 桌面记忆检索。
 *
 * Desktop memory lookup.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ListMemoryParams".
 */
export interface ListMemoryParams {
  category?: Category;
  cursor?: Cursor2;
  include_disabled?: IncludeDisabled;
  limit?: Limit8;
  query?: Query3;
  session_id: SessionId39;
  subject?: Subject1;
}
/**
 * 用户查询卡片范围；工具另校验会话权限。
 *
 * User query scope; tools also check session ownership.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ListProgramsParams".
 */
export interface ListProgramsParams {
  cursor?: Cursor3;
  limit?: Limit9;
  project_id: ProjectId29;
  session_id?: SessionId40;
}
/**
 * 按项目分页会话列表。
 *
 * Page sessions by project.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ListSessionsParams".
 */
export interface ListSessionsParams {
  cursor: Cursor4;
  limit: Limit10;
  project_id: ProjectId30;
}
/**
 * 列出指定项目保留的终端。 List retained terminals for one project.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ListTerminalsParams".
 */
export interface ListTerminalsParams {
  project_id: ProjectId31;
}
/**
 * 手动整理可显式选择旧范围，默认仅处理增量。
 *
 * Manual maintenance can explicitly select old history.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "MaintainMemoryParams".
 */
export interface MaintainMemoryParams {
  after_seq?: AfterSeq2;
  session_id: SessionId41;
  source_ids?: SourceIds;
  title?: Title5;
}
/**
 * 图片字节分段，避免超过协议帧。
 *
 * Image byte chunks stay below protocol frame limits.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpArtifact".
 */
export interface McpArtifact {
  data: Data1;
  mime_type: MimeType;
  next_offset: NextOffset3;
}
/**
 * 仅按服务产物身份分页读取图片。
 *
 * Page an image by owned artifact identity.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpArtifactParams".
 */
export interface McpArtifactParams {
  artifact_id: ArtifactId1;
  offset?: Offset4;
  project_id?: ProjectId32;
  session_id?: SessionId42;
}
/**
 * 公开目录不含解析后的凭据。
 *
 * Public catalog excludes resolved credentials.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpCatalog".
 */
export interface McpCatalog {
  artifacts?: Artifacts2;
  install_error?: InstallError;
  installing_browser?: InstallingBrowser;
  issues?: Issues1;
  presets?: Presets;
  servers: Servers1;
}
/**
 * 由后端提供可编辑的服务预设与官方说明。
 *
 * Supply editable service presets and official setup information.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpPreset".
 */
export interface McpPreset {
  auth_help: AuthHelp;
  credential_url: CredentialUrl;
  docs_url: DocsUrl;
  oauth_help?: OauthHelp;
  oauth_setup_url?: OauthSetupUrl;
  oauth_url?: OauthUrl;
  preset_id: PresetId;
  server: McpServer;
  suggested_env: SuggestedEnv;
  toolsets?: Toolsets;
}
/**
 * 只保存凭据引用，活动连接采用启动时快照。
 *
 * Store credential references and connection snapshots.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpServer".
 */
export interface McpServer {
  all_projects?: AllProjects;
  arguments?: Arguments2;
  auth?: McpAuth;
  browser_executable?: BrowserExecutable;
  command?: Command1;
  description?: Description4;
  enabled?: Enabled8;
  env_refs?: EnvRefs;
  header_refs?: HeaderRefs;
  headers?: Headers;
  name: Name11;
  preset_id?: PresetId1;
  project_ids?: ProjectIds;
  server_id: ServerId3;
  timeout_seconds?: TimeoutSeconds2;
  transport?: Transport;
  url?: Url1;
}
/**
 * HTTP 认证只保存来源和组装方式。
 *
 * Store HTTP authentication source and formatting, never the token.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpAuth".
 */
export interface McpAuth {
  env_var?: EnvVar1;
  header?: Header;
  oauth?: McpOAuthConfig;
  prefix?: Prefix2;
  source?: Source6;
}
/**
 * OAuth 的公开登记选项；空身份使用服务器支持的动态登记。
 *
 * Public OAuth registration options; an empty identity uses server registration.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpOAuthConfig".
 */
export interface McpOAuthConfig {
  callback_port?: CallbackPort;
  client_id?: ClientId;
  client_metadata_url?: ClientMetadataUrl;
  client_secret_env?: ClientSecretEnv;
  login_timeout_seconds?: LoginTimeoutSeconds;
  scope?: Scope12;
  token_auth_method?: TokenAuthMethod;
}
export interface EnvRefs {
  [k: string]: string;
}
export interface HeaderRefs {
  [k: string]: string;
}
export interface Headers {
  [k: string]: string;
}
/**
 * 预设服务的可选工具组，不限制实际服务定义。
 *
 * Suggested toolsets do not restrict the server's actual definitions.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpToolset".
 */
export interface McpToolset {
  name: Name12;
  title: Title6;
}
/**
 * 配置与实际状态分开显示。
 *
 * Display configuration separately from actual status.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpServerView".
 */
export interface McpServerView {
  credential_message?: CredentialMessage;
  credential_status?: CredentialStatus;
  error?: Error3;
  needs_reconnect?: NeedsReconnect;
  oauth?: McpOAuthView | null;
  server: McpServer;
  status: Status17;
  tools?: Tools2;
}
/**
 * 只向管理界面提供授权状态与短期网页入口。
 *
 * Expose authorization status and a temporary browser link to management UI only.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpOAuthView".
 */
export interface McpOAuthView {
  authorization_url?: AuthorizationUrl;
  error?: Error4;
  expires_at?: ExpiresAt;
  redirect_uri?: RedirectUri;
  scope?: Scope13;
  status?: Status16;
}
/**
 * 只控制指定连接或浏览器安装。
 *
 * Control a selected connection or browser installation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpControlParams".
 */
export interface McpControlParams {
  action: Action6;
  project_id?: ProjectId33;
  server_id: ServerId4;
  session_id?: SessionId43;
}
/**
 * 设置与会话使用同一目录。
 *
 * Settings and sessions share one catalog.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "McpParams".
 */
export interface McpParams {
  project_id?: ProjectId34;
  session_id?: SessionId44;
}
/**
 * 管理页与检索结果，不隐藏局部读取失败。
 *
 * Management/retrieval results with local read failures.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "MemoryPage".
 */
export interface MemoryPage {
  entries: Entries;
  next_cursor: NextCursor2;
  state: MemoryState;
  totals?: UsageSummary;
  unavailable_count?: UnavailableCount2;
}
/**
 * 带作用域和修订来源的独立记忆。
 *
 * Independent memory with scope and revision provenance.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "MemoryEntry".
 */
export interface MemoryEntry {
  category?: Category1;
  content: Content8;
  created_at: CreatedAt8;
  enabled?: Enabled9;
  memory_id: MemoryId1;
  pinned?: Pinned;
  project_id: ProjectId35;
  related_ids?: RelatedIds;
  revision: Revision4;
  scope?: Scope14;
  session_id: SessionId45;
  source: Source7;
  source_ids?: SourceIds1;
  source_seq: SourceSeq;
  stale?: Stale;
  subjects?: Subjects;
  supersedes?: Supersedes;
  tags?: Tags;
  title: Title7;
  updated_at: UpdatedAt9;
  valid_from?: ValidFrom;
  valid_until?: ValidUntil;
}
/**
 * 会话贡献起点与最近维护事实。
 *
 * Session contribution boundary and latest maintenance facts.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "MemoryJob".
 */
export interface MemoryJob {
  finished_at?: FinishedAt5;
  job_id: JobId1;
  message?: Message9;
  model_id: ModelId11;
  requests?: Requests5;
  started_at: StartedAt1;
  status: Status18;
  through_seq: ThroughSeq4;
  usage?: TokenUsage;
}
/**
 * 当前项目内管理记忆。
 *
 * Manage memory within the current project.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "MemoryParams".
 */
export interface MemoryParams {
  session_id: SessionId46;
}
/**
 * 显式选择被测模型，不沿用当前会话选择。 Select the tested model explicitly.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ModelConnectionProbeParams".
 */
export interface ModelConnectionProbeParams {
  model_id: ModelId12;
  timeout_seconds: TimeoutSeconds3;
}
/**
 * 导航项的明确身份及显示名。 Explicit navigation identity and display name.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "NavigationItemName".
 */
export interface NavigationItemName {
  id: Id;
  kind: Kind17;
  name: Name13;
}
/**
 * 只取消指定在线操作。 Cancel only the identified online operation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillCancel".
 */
export interface OnlineSkillCancel {
  operation_id: OperationId12;
}
/**
 * 正文与文件清单的有限预览，安装仍保留完整文件。
 *
 * Bounded previews; installation keeps full files.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillDocument".
 */
export interface OnlineSkillDocument {
  content: Content9;
  file_count: FileCount;
  files: Files2;
  truncated: Truncated3;
}
/**
 * 下载明确来源，ref 和目录可覆盖链接解析结果。
 *
 * Download a source with optional ref/path overrides.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillInspect".
 */
export interface OnlineSkillInspect {
  directory?: Directory1;
  max_archive_mb?: MaxArchiveMb;
  ref?: Ref;
  source: Source8;
  timeout_seconds?: TimeoutSeconds4;
}
/**
 * 明确将所选方法保存为用户或项目资源。
 *
 * Explicitly install a user or project skill.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillInstall".
 */
export interface OnlineSkillInstall {
  path: Path17;
  preview_id: PreviewId;
  project_id?: ProjectId36;
  scope?: Scope15;
}
/**
 * 读取已下载快照，不静默更新远程版本。
 *
 * Read a downloaded snapshot without a remote refresh.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillRead".
 */
export interface OnlineSkillRead {
  path: Path18;
  preview_id: PreviewId1;
}
/**
 * 搜索公开目录，不携带应用凭据。
 *
 * Search a public catalog without application credentials.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillSearch".
 */
export interface OnlineSkillSearch {
  limit?: Limit11;
  query: Query4;
  timeout_seconds?: TimeoutSeconds5;
}
/**
 * 在线页面共用真实操作状态，离开再回来可继续查看。
 *
 * Shared operation facts survive navigation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillStatus".
 */
export interface OnlineSkillStatus {
  action?: Action7;
  error_code?: ErrorCode;
  hits?: Hits;
  installed?: SkillItem | null;
  message?: Message10;
  operation_id?: OperationId13;
  preview?: OnlineSkillPreview | null;
  query?: Query5;
  status?: Status19;
}
/**
 * 网站的搜索条目，正文以仓库快照为准。
 *
 * Website hits; bodies come from repository snapshots.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillHit".
 */
export interface OnlineSkillHit {
  installs?: Installs;
  name: Name14;
  source: Source9;
  url: Url2;
}
/**
 * 来源、覆盖关系及资源位置。 Provenance, shadowing and resource location.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillItem".
 */
export interface SkillItem {
  description: Description5;
  enabled?: Enabled10;
  name: Name15;
  origin?: SkillOrigin | null;
  path: Path19;
  resource_base: ResourceBase;
  shadowed_by?: ShadowedBy;
  skill_id: SkillId1;
  source: Source10;
  version: Version4;
}
/**
 * 记录下载来源，不作为执行门槛。 Record download provenance without an execution gate.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillOrigin".
 */
export interface SkillOrigin {
  directory: Directory2;
  downloaded_at: DownloadedAt;
  ref: Ref1;
  repository: Repository1;
  revision?: Revision5;
}
/**
 * 预览身份指向当前保留的 ZIP。 Preview identity points to the retained ZIP.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillPreview".
 */
export interface OnlineSkillPreview {
  issues?: Issues2;
  origin: SkillOrigin;
  preview_id: PreviewId2;
  skills: Skills1;
  total: Total;
}
/**
 * 仓库中实际存在的 Skill。 A skill actually present in the repository.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OnlineSkillCandidate".
 */
export interface OnlineSkillCandidate {
  bytes: Bytes;
  description: Description6;
  file_count: FileCount1;
  name: Name16;
  path: Path20;
}
/**
 * 通过用户选择的目录路径打开项目。
 *
 * Open a project using a user-selected directory path.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OpenProjectByPath".
 */
export interface OpenProjectByPath {
  path: Path21;
}
/**
 * 通过已有项目标识恢复选择，并由服务重新验证目录。
 *
 * Restore a recorded project by ID and let the service revalidate its directory.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OpenProjectById".
 */
export interface OpenProjectById {
  project_id: ProjectId37;
}
/**
 * 明确程序、项目与可选成员归属。
 *
 * Explicit program, project and optional member ownership.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OpenTerminalParams".
 */
export interface OpenTerminalParams {
  cols?: Cols;
  command: Command2;
  cwd?: Cwd1;
  member_id?: MemberId2;
  project_id: ProjectId38;
  rows?: Rows;
  session_id?: SessionId47;
}
/**
 * 用户点击来源时打开 HTTP(S) 地址；宿主仍校验 URL。
 *
 * Open an HTTP(S) source on a user click; the host also validates the URL.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OpenWebUrlParams".
 */
export interface OpenWebUrlParams {
  url: Url3;
}
/**
 * 桌面操作使用的公开错误，不包含原始异常堆栈。
 *
 * Public desktop-operation error without a raw exception traceback.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OperationError".
 */
export interface OperationError {
  code: Code9;
  message: Message11;
  remediation: Remediation3;
}
/**
 * 保留部分成功与未执行项数量。
 *
 * Preserve partial success and unattempted counts.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OperationResult".
 */
export interface OperationResult {
  items: Items2;
  partial: Partial;
  unattempted?: Unattempted;
}
/**
 * 每个文件的实际成功或失败。
 *
 * Actual success or failure for one file.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OperationItem".
 */
export interface OperationItem {
  change_id?: ChangeId4;
  code?: Code10;
  message?: Message12;
  path: Path22;
  status: Status20;
}
/**
 * 导入仅解析预览，不隐式安装资源。 Parse imported text without installing resources.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ParseWorkStyle".
 */
export interface ParseWorkStyle {
  content: Content10;
}
/**
 * 导入文本由同一后端契约解析，不立即保存。 Parse imported text without persisting it.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ParseWorkflowParams".
 */
export interface ParseWorkflowParams {
  content: Content11;
}
/**
 * 多文件精确补丁。
 *
 * Exact patches across multiple files.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "PatchDocumentsParams".
 */
export interface PatchDocumentsParams {
  edits: Edits;
  session_id: SessionId48;
}
/**
 * 替换唯一当前原文，旧摘要仅兼容接收。
 *
 * Replace unique current text; accept legacy hashes only.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "EditFileArgs".
 */
export interface EditFileArgs {
  new_text: NewText;
  old_text: OldText;
  path: Path23;
}
/**
 * 宿主填写来源和请求边界送达状态。
 *
 * The host records provenance and request-boundary delivery state.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "PeerMessage".
 */
export interface PeerMessage {
  created_at: CreatedAt9;
  delivered_run_id?: DeliveredRunId;
  message_id: MessageId1;
  params: SendMessageParams;
  task_id: TaskId11;
}
/**
 * 普通交流不等同工作请求，不唤醒空闲会话。
 *
 * Ordinary messages are not work requests and never wake idle sessions.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SendMessageParams".
 */
export interface SendMessageParams {
  content: Content12;
  operation_id: OperationId14;
  source_session_id: SourceSessionId6;
  target_session_id: TargetSessionId5;
}
/**
 * 普通消息的可追溯收发记录。
 *
 * Traceable incoming and outgoing ordinary messages.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "PeerMessagePage".
 */
export interface PeerMessagePage {
  messages: Messages;
  next_cursor?: NextCursor3;
}
/**
 * 预览回到所选请求之前的代码变化。 Preview code changes back to a selected request.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "PreviewCheckpointParams".
 */
export interface PreviewCheckpointParams {
  checkpoint_id: CheckpointId2;
  session_id: SessionId49;
}
/**
 * 按项目或会话查询卡片，损坏记录明确计数。
 *
 * Query project/session cards with damage counts.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ProgramPage".
 */
export interface ProgramPage {
  active_count: ActiveCount;
  next_cursor: NextCursor4;
  programs: Programs1;
  unavailable_count: UnavailableCount3;
}
/**
 * 只使用受管程序身份。
 *
 * Address a managed program by identity only.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ProgramView".
 */
export interface ProgramView {
  archive_id?: ArchiveId;
  archive_read?: ArchiveRead;
  next_seq: NextSeq;
  output: Output1;
  summary: ProgramSummary;
  truncated: Truncated4;
}
/**
 * 按消费顺序编号的输出块，始终作为纯文本处理。
 *
 * Numbered output chunks rendered as plain text.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "OutputChunk".
 */
export interface OutputChunk {
  seq: Seq3;
  stream: Stream;
  text: Text7;
}
/**
 * 从已消费序号后读取有界输出。 Read bounded output after an observed sequence.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ReadTerminalParams".
 */
export interface ReadTerminalParams {
  after_seq?: AfterSeq3;
  terminal_id: TerminalId;
}
/**
 * 明确把已有项目身份绑定到新目录，保留会话与记忆。
 *
 * Explicitly rebind an existing project identity, retaining sessions and memory.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RelocateProjectParams".
 */
export interface RelocateProjectParams {
  path: Path24;
  project_id: ProjectId39;
}
/**
 * 删除登记而不卸载环境。
 *
 * Remove a reference without uninstalling its environment.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RemoveEnvironmentParams".
 */
export interface RemoveEnvironmentParams {
  environment_id: EnvironmentId5;
  expected_revision: ExpectedRevision5;
  project_id: ProjectId40;
}
/**
 * 移除模板不修改既有任务。
 *
 * Remove a template without changing existing tasks.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RemoveWorkflowParams".
 */
export interface RemoveWorkflowParams {
  template_id: TemplateId3;
}
/**
 * 用户重命名操作，区别于目录移动或会话归属。
 *
 * User rename, distinct from directory moves or membership changes.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RenameNavigationParams".
 */
export interface RenameNavigationParams {
  id: Id1;
  kind: Kind18;
  name: Name17;
  operation_id: OperationId15;
}
/**
 * 更新实际 ConPTY 字符尺寸。 Resize the actual ConPTY character grid.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ResizeTerminalParams".
 */
export interface ResizeTerminalParams {
  cols: Cols1;
  rows: Rows1;
  terminal_id: TerminalId1;
}
/**
 * 明确指定恢复方式和文件，不自动执行新的模型请求。
 *
 * Restore without automatically running a new prompt.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RestoreCheckpointParams".
 */
export interface RestoreCheckpointParams {
  checkpoint_id: CheckpointId3;
  include_observed?: IncludeObserved;
  mode?: Mode10;
  operation_id: OperationId16;
  paths?: Paths1;
  session_id: SessionId50;
}
/**
 * 恢复范围、提示与来源。 Restore scope, limitations and provenance.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RestorePreview".
 */
export interface RestorePreview {
  checkpoint: FileCheckpointSummary;
  files: Files3;
  issues?: Issues3;
}
/**
 * 单文件真实预览／结果；未知写入来源不能伪造成 Agent 修改。
 *
 * Per-file preview/result with honest provenance.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RestoreFile".
 */
export interface RestoreFile {
  diff?: Diff1;
  message?: Message13;
  path: Path25;
  source: Source11;
  status: Status21;
}
/**
 * 逐文件结果与反向检查点，对话未成功回退时如实显示。 Per-file outcomes and undo checkpoint.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RestoreResult".
 */
export interface RestoreResult {
  files: Files4;
  message: Message14;
  prompt?: Prompt1;
  rewound: Rewound;
  undo_checkpoint_id: UndoCheckpointId;
}
/**
 * 不要求回复的 JSON-RPC 通知，不能与带标识请求混淆。
 *
 * JSON-RPC notification requiring no reply, distinct from an identified request.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RpcRequest".
 */
export interface RpcRequest {
  id: Id2;
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RpcSuccess".
 */
export interface RpcSuccess {
  id: Id3;
  jsonrpc: Jsonrpc2;
  result: JsonValue;
}
/**
 * 关联请求与公开错误；无法确定请求标识时允许 null。
 *
 * Associate a request with a public error, allowing null when its ID is unknown.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RpcFailure".
 */
export interface RpcFailure {
  error: RpcError;
  id: Id4;
  jsonrpc: Jsonrpc3;
}
/**
 * 将 JSON-RPC 数字错误码与应用错误信息分开表达。
 *
 * Keep JSON-RPC numeric codes distinct from application error information.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "RpcError".
 */
export interface RpcError {
  code: Code11;
  data: ErrorData;
  message: Message15;
}
/**
 * 保存时核对编辑器实际基线正文。
 *
 * Check the actual editor base text when saving.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveDocumentParams".
 */
export interface SaveDocumentParams {
  base_content: BaseContent1;
  content: Content13;
  path: Path26;
  session_id: SessionId51;
}
/**
 * 显式导入或修改引用，以版本防止覆盖较新设置。
 *
 * Import references with revision checks.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveEnvironmentParams".
 */
export interface SaveEnvironmentParams {
  definition: Definition1;
  environment_id: EnvironmentId6;
  expected_revision: ExpectedRevision6;
  name: Name18;
  project_id: ProjectId41;
}
/**
 * 仅影响后续启动，不重新执行或热切换程序。
 *
 * Affect future launches without restarting programs.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveExecutionSettings".
 */
export interface SaveExecutionSettings {
  expected_revision: ExpectedRevision7;
  project_id: ProjectId42;
  settings: ExecutionSettings;
}
/**
 * 保存项目服务登记，下一次查询生效。
 *
 * Save project registrations for subsequent queries.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveLanguageServers".
 */
export interface SaveLanguageServers {
  project_id: ProjectId43;
  servers: Servers2;
  timeout_seconds?: TimeoutSeconds6;
}
/**
 * 显式新增或保存服务。
 *
 * Explicit server registration or update.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveMcpParams".
 */
export interface SaveMcpParams {
  clear_credential?: ClearCredential;
  credential_value?: CredentialValue;
  project_id?: ProjectId44;
  server: McpServer;
  session_id?: SessionId52;
}
/**
 * 显式保存知识，可更新已知条目。
 *
 * Explicit knowledge save or update.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveMemoryParams".
 */
export interface SaveMemoryParams {
  fields: MemoryFields;
  memory_id?: MemoryId2;
  session_id: SessionId53;
}
/**
 * 用户可维护的知识正文；其余来源由宿主填写。
 *
 * Editable knowledge; the host supplies provenance.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "MemoryFields".
 */
export interface MemoryFields {
  category?: Category2;
  content: Content14;
  enabled?: Enabled11;
  pinned?: Pinned1;
  related_ids?: RelatedIds1;
  scope?: Scope16;
  source_ids?: SourceIds2;
  stale?: Stale1;
  subjects?: Subjects1;
  supersedes?: Supersedes1;
  tags?: Tags1;
  title: Title8;
  valid_from?: ValidFrom1;
  valid_until?: ValidUntil1;
}
/**
 * 显式创建或修改用户 / 项目资源。 Explicit user/project resource edits.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveSkillParams".
 */
export interface SaveSkillParams {
  content: Content15;
  import_directory?: ImportDirectory;
  name: Name19;
  overwrite?: Overwrite;
  project_id?: ProjectId45;
  scope?: Scope17;
  session_id?: SessionId54;
}
/**
 * 只保存阅读位置，不覆盖团队编辑或会话绑定。
 *
 * Save reading position without replacing team edits or session bindings.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveSpaceLayoutParams".
 */
export interface SaveSpaceLayoutParams {
  layout: SpaceLayout;
  task_id: TaskId12;
}
/**
 * 与团队草稿独立保存的图展示设置。
 *
 * Graph presentation settings saved separately from team drafts.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceLayout".
 */
export interface SpaceLayout {
  graph_open?: GraphOpen;
  viewport?: SpaceViewport | null;
}
/**
 * 关系图的阅读位置与缩放。
 *
 * Graph reading position and zoom.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceViewport".
 */
export interface SpaceViewport {
  x?: X2;
  y?: Y2;
  zoom?: Zoom;
}
/**
 * 保存草稿；空版本只用于首次创建。
 *
 * Save a draft; a null revision creates the first snapshot.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveSpaceParams".
 */
export interface SaveSpaceParams {
  config: SpaceConfig;
  expected_revision: ExpectedRevision8;
  task_id: TaskId13;
}
/**
 * 保存或更新一个团队模板。 Save or update one team template.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveTeamTemplateParams".
 */
export interface SaveTeamTemplateParams {
  description?: Description7;
  draft: SaveTeamDraftArgs;
  name: Name20;
  template_id: TemplateId4;
}
/**
 * 模型提交的可编辑团队，不创建会话。
 *
 * Model-authored editable team without session creation.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveTeamDraftArgs".
 */
export interface SaveTeamDraftArgs {
  config: SpaceConfig;
  initial_work_items?: InitialWorkItems1;
}
/**
 * 编辑任务定义，版本冲突保留草稿。
 *
 * Edit task definitions with draft-preserving revisions.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveWorkGraphParams".
 */
export interface SaveWorkGraphParams {
  expected_revision: ExpectedRevision9;
  items: Items3;
  operation_id: OperationId17;
  owner_changes?: OwnerChanges;
  task_id: TaskId14;
}
export interface OwnerChanges {
  /**
   * This interface was referenced by `OwnerChanges`'s JSON-Schema definition
   * via the `patternProperty` "^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$".
   */
  [k: string]: string | null;
}
/**
 * 保存用户编辑的组合蓝图。 Save an edited composite blueprint.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveWorkStyle".
 */
export interface SaveWorkStyle {
  style: WorkStyle;
}
/**
 * 保存或复制一个模板。
 *
 * Save or copy one template.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SaveWorkflowParams".
 */
export interface SaveWorkflowParams {
  template: WorkflowTemplate;
}
/**
 * 选择既有会话的后续模型，不创建会话或发请求。
 *
 * Select a session's next model without creating sessions or sending requests.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SelectSessionModelParams".
 */
export interface SelectSessionModelParams {
  model_id: ModelId13;
  operation_id: OperationId18;
  session_id: SessionId55;
}
/**
 * 会话引用不复制正文。 Session references do not copy bodies.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SelectSkillsParams".
 */
export interface SelectSkillsParams {
  project_id?: ProjectId46;
  selected: Selected;
  session_id?: SessionId56;
}
/**
 * 唯一支持的后端事件通知形状。
 *
 * The sole supported backend notification envelope.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SessionSignal".
 */
export interface SessionSignal {
  delta_index: DeltaIndex;
  kind: Kind19;
  message_id: MessageId2;
  model_progress?: ModelProgress | null;
  process_epoch: ProcessEpoch;
  run_id: RunId10;
  seq: Seq4;
  session_id: SessionId57;
  text: Text8;
}
/**
 * 项目会话的游标页。
 *
 * Cursor page of project sessions.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SessionPage".
 */
export interface SessionPage {
  active_session_ids: ActiveSessionIds;
  next_cursor: NextCursor5;
  sessions: Sessions1;
  unavailable_count: UnavailableCount4;
}
/**
 * 限定会话身份。
 *
 * Constrain session identity.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SessionParams".
 */
export interface SessionParams {
  session_id: SessionId58;
}
/**
 * 有界快照含历史水位与实时预览。
 *
 * Bounded snapshot with history watermark and live preview.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SessionView".
 */
export interface SessionView {
  before_seq: BeforeSeq5;
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ChatEntry".
 */
export interface ChatEntry {
  abandoned?: Abandoned;
  call: ToolCall | null;
  goal_result?: GoalView | null;
  kind: Kind20;
  message_id: MessageId3;
  model_id?: ModelId14;
  program_result?: ProgramView | null;
  reasoning?: Reasoning;
  result: ToolResult | null;
  run_id: RunId11;
  seq: Seq5;
  text: Text9;
  web_result?: WebResult;
}
/**
 * 完整参数对象，仍需工具权限校验。 Complete arguments still requiring tool policy checks.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ToolCall".
 */
export interface ToolCall {
  arguments: JsonObject;
  name: Name21;
  tool_call_id: ToolCallId3;
}
/**
 * 按调用标识关联可公开工具结果。 Associate public tool output with its call ID.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "ToolResult".
 */
export interface ToolResult {
  content: Content16;
  is_error: IsError;
  tool_call_id: ToolCallId4;
}
/**
 * 原生搜索结果；模型总结和实际来源分别呈现。
 *
 * Native search results distinguish model summaries from actual sources.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WebSearchResult".
 */
export interface WebSearchResult {
  actual_queries: ActualQueries;
  archive_id?: ArchiveId1;
  kind: Kind21;
  model_id: ModelId15;
  query: Query6;
  retrieved_at: RetrievedAt;
  search_uses: SearchUses;
  sources: Sources;
  summary: Summary2;
  truncated?: Truncated5;
  usage: TokenUsage;
}
/**
 * 只保存实际来源及可用摘录，不公开供应商不透明字段。
 *
 * Retain actual sources and available excerpts, excluding opaque provider fields.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WebSource".
 */
export interface WebSource {
  excerpt?: Excerpt;
  page_age?: PageAge;
  title: Title9;
  url: Url4;
}
/**
 * 公开正文片段及读取状态，不宣称执行了网页脚本。
 *
 * A public text excerpt and retrieval status, without claiming script execution.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WebPageResult".
 */
export interface WebPageResult {
  archive_id?: ArchiveId2;
  content: Content17;
  content_type: ContentType;
  download_truncated: DownloadTruncated;
  kind: Kind22;
  next_offset: NextOffset4;
  offset: Offset5;
  redirects: Redirects;
  requested_url: RequestedUrl;
  retrieved_at: RetrievedAt1;
  status_code?: StatusCode;
  title: Title10;
  truncated: Truncated6;
  url: Url5;
}
/**
 * 轻量目录与明确的局部错误。 Lightweight catalog with explicit local errors.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillCatalog".
 */
export interface SkillCatalog {
  issues?: Issues4;
  items: Items4;
  project_directory: ProjectDirectory;
  rule_paths?: RulePaths;
  selected?: Selected1;
  user_directory: UserDirectory;
}
/**
 * 资源详情与原文。 Resource details and original text.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillDocument".
 */
export interface SkillDocument {
  content: Content18;
  item: SkillItem;
}
/**
 * 指定项目与可选会话。 Identify a project and optional session.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillParams".
 */
export interface SkillParams {
  project_id?: ProjectId47;
  session_id?: SessionId59;
}
/**
 * 读取一项原始文本。 Read one original resource.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillReadParams".
 */
export interface SkillReadParams {
  project_id?: ProjectId48;
  session_id?: SessionId60;
  skill_id: SkillId2;
}
/**
 * 用户导航动作。 User navigation actions.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillSiteControl".
 */
export interface SkillSiteControl {
  action: Action8;
  url?: Url6;
}
/**
 * 原生网页位置及页面所有者，用于切换后隐藏。
 *
 * Native view bounds and owner for navigation cleanup.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillSiteLayout".
 */
export interface SkillSiteLayout {
  height?: Height;
  owner_id: OwnerId;
  visible: Visible;
  width?: Width;
  x?: X3;
  y?: Y3;
}
/**
 * 仅返回来源链接，不发送整页正文。 Return source links, not the entire page body.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillSiteSources".
 */
export interface SkillSiteSources {
  page_url: PageUrl;
  sources: Sources1;
}
/**
 * 用户当前页面中的可导入来源。 An import source on the user's current page.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillSiteSource".
 */
export interface SkillSiteSource {
  label: Label1;
  url: Url7;
}
/**
 * 真实页面状态，不把发起导航当成加载完成。
 *
 * Page facts, not navigation requests claimed as completion.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SkillSiteState".
 */
export interface SkillSiteState {
  can_back: CanBack;
  can_forward: CanForward;
  error: Error5;
  loading: Loading;
  title: Title11;
  url: Url8;
}
/**
 * 按实际消息 / 轮次身份读取较早历史。
 *
 * Read older history by actual message or round identity.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceChatPageParams".
 */
export interface SpaceChatPageParams {
  before_id?: BeforeId;
  limit?: Limit12;
  task_id: TaskId15;
}
/**
 * 普通消息仅路由给明确接收成员。
 *
 * Route ordinary messages only to selected recipients.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceChatParams".
 */
export interface SpaceChatParams {
  content: Content19;
  mode?: Mode11;
  operation_id: OperationId19;
  target_member_ids?: TargetMemberIds;
  task_id: TaskId16;
  work_ids?: WorkIds;
}
/**
 * 消息和轮次历史，加真实运行公开投影。
 *
 * Message and round history with real execution projections.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceChatView".
 */
export interface SpaceChatView {
  generations?: Generations;
  messages?: Messages1;
  next_before?: NextBefore;
  outputs?: Outputs;
  rounds?: Rounds;
  task_id: TaskId17;
}
/**
 * 真实生成请求及待用户采用的草稿。
 *
 * Real generation request and a draft awaiting user adoption.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TeamGeneration".
 */
export interface TeamGeneration {
  created_at?: CreatedAt10;
  draft?: SaveTeamDraftArgs | null;
  error?: Error6;
  expected_revision: ExpectedRevision10;
  params: GenerateTeamParams;
  run_id?: RunId12;
}
/**
 * 持久用户消息与接收对象快照。 Durable user message and recipient snapshots.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceChatMessage".
 */
export interface SpaceChatMessage {
  content: Content20;
  created_at: CreatedAt11;
  executions?: Executions;
  message_id: MessageId4;
  mode: Mode12;
  target_member_ids: TargetMemberIds1;
  work_ids?: WorkIds1;
}
/**
 * 宿主记录实际投递与执行关联。
 *
 * Host-recorded delivery and execution references.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceExecution".
 */
export interface SpaceExecution {
  error?: Error7;
  goal_id?: GoalId6;
  member_id: MemberId3;
  operation_id: OperationId20;
  request_id?: RequestId2;
  run_id?: RunId13;
  session_id: SessionId61;
}
/**
 * 精确 Run 的公开回答，思考和工具留在 Trace。
 *
 * Public answers from exact runs, with internals in Trace.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpacePublicOutput".
 */
export interface SpacePublicOutput {
  delta_index?: DeltaIndex2;
  error?: Error8;
  member_id: MemberId4;
  message_id?: MessageId5;
  origin_id?: OriginId;
  process_epoch?: ProcessEpoch2;
  run_id: RunId14;
  seq?: Seq6;
  session_id: SessionId62;
  status: Status22;
  streaming?: Streaming;
  text?: Text10;
  waiting_for?: WaitingFor1;
}
/**
 * 空间轮次引用已有 Goal，不运行自己的循环。
 *
 * A space round references existing goals without another loop.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceRound".
 */
export interface SpaceRound {
  budget: GoalBudget;
  created_at: CreatedAt12;
  executions?: Executions1;
  limits?: RunLimits | null;
  objective: Objective5;
  round_id: RoundId;
  stopped?: Stopped;
  work_ids?: WorkIds2;
}
/**
 * 按任务读取空间，不自动迁移旧任务。
 *
 * Lookup a task space without migrating old tasks.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceParams".
 */
export interface SpaceParams {
  task_id: TaskId18;
}
/**
 * 缺失空间和已保存空间分别表达。
 *
 * Distinguish absent spaces from durable snapshots.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceResult".
 */
export interface SpaceResult {
  space: SpaceView | null;
}
/**
 * 空间快照；普通配置保存不能覆盖绑定。
 *
 * Space snapshot with bindings preserved by config saves.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceView".
 */
export interface SpaceView {
  bindings?: Bindings;
  config: SpaceConfig;
  created_at: CreatedAt13;
  error?: Error10;
  layout?: SpaceLayout;
  project_id: ProjectId49;
  revision: Revision6;
  task_id: TaskId19;
  updated_at: UpdatedAt10;
}
/**
 * 当前会话与保留的历史，错误不冒充成功。
 *
 * Current session and retained history with explicit errors.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceBinding".
 */
export interface SpaceBinding {
  error?: Error9;
  member_id: MemberId5;
  session_id?: SessionId63;
  session_ids?: SessionIds;
}
/**
 * 显式组建已有成员的会话，不启动模型。
 *
 * Explicitly assemble member sessions without model calls.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpaceStartParams".
 */
export interface SpaceStartParams {
  task_id: TaskId20;
}
/**
 * 幂等操作 ID 独立于 RPC ID。
 *
 * Idempotent operation identity is separate from RPC identity.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "StartRunParams".
 */
export interface StartRunParams {
  attachment_ids?: AttachmentIds1;
  limits: RunLimits | null;
  mode?: Mode13;
  operation_id: OperationId21;
  plan_document?: PlanDocument1;
  prompt: Prompt2;
  session_id: SessionId64;
}
/**
 * 用户明确启动合作目标；默认由接收成员协调。
 *
 * Explicitly start a cooperative goal via the receiver.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "StartSpaceRoundParams".
 */
export interface StartSpaceRoundParams {
  budget?: GoalBudget;
  limits?: RunLimits | null;
  objective: Objective6;
  operation_id: OperationId22;
  target_member_ids?: TargetMemberIds2;
  task_id: TaskId21;
  work_ids?: WorkIds3;
}
/**
 * 用户选择工作范围与执行方式。
 *
 * Explicitly select work scope and execution mode.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "StartWorkGraphParams".
 */
export interface StartWorkGraphParams {
  budget?: GoalBudget;
  continuous?: Continuous;
  instruction?: Instruction;
  member_id: MemberId6;
  operation_id: OperationId23;
  task_id: TaskId22;
  work_ids: WorkIds4;
}
/**
 * 区分已保存的下次启动设置与本次实际数据根。
 *
 * Distinguish saved next-launch paths from the current effective data root.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "StartupPathsParams".
 */
export interface StartupPathsParams {
  data_dir: DataDir2;
  project_dir: ProjectDir1;
}
/**
 * 停止指定成员或整轮，不重试失败工作。
 *
 * Stop a member or round without retrying failures.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "StopSpaceRoundParams".
 */
export interface StopSpaceRoundParams {
  member_id?: MemberId7;
  round_id?: RoundId1;
  task_id: TaskId23;
}
/**
 * 按项目分页；损坏任务单独计数，不冒充空任务。
 *
 * Project page with explicit unreadable records.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TaskPage".
 */
export interface TaskPage {
  next_cursor: NextCursor6;
  tasks: Tasks;
  unavailable_count: UnavailableCount5;
}
/**
 * 树列表仅包含显示所需字段，详细共同信息按需读取。
 *
 * Navigation metadata; shared details load on demand.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TaskSummary".
 */
export interface TaskSummary {
  project_id: ProjectId50;
  revision: Revision7;
  status: Status23;
  task_id: TaskId24;
  title: Title12;
}
/**
 * 任务查询身份。 Task lookup identity.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TaskParams".
 */
export interface TaskParams {
  task_id: TaskId25;
}
/**
 * 可分享的团队配置快照，不包含实际会话绑定。
 *
 * Shareable team configuration without actual session bindings.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TeamTemplate".
 */
export interface TeamTemplate {
  description?: Description8;
  draft: SaveTeamDraftArgs;
  name: Name22;
  schema_version?: SchemaVersion1;
  template_id: TemplateId5;
  updated_at: UpdatedAt11;
}
/**
 * 供用户保存的 UTF-8 JSON 文本。
 *
 * UTF-8 JSON text for explicit user export.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TeamTemplateExport".
 */
export interface TeamTemplateExport {
  content: Content21;
}
/**
 * 按稳定身份读取模板。 Read a template by stable identity.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TeamTemplateParams".
 */
export interface TeamTemplateParams {
  template_id: TemplateId6;
}
/**
 * 本机模板目录。 Local team template catalog.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TeamTemplatesResult".
 */
export interface TeamTemplatesResult {
  templates: Templates;
}
/**
 * 用户显式接管或交还指定成员会话。
 *
 * Explicitly take over or return member-session control.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TerminalControlParams".
 */
export interface TerminalControlParams {
  controller: Controller;
  member_id?: MemberId8;
  session_id?: SessionId65;
  terminal_id: TerminalId2;
}
/**
 * 项目终端与可选能力可用性。
 *
 * Project terminals and optional capability availability.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TerminalPage".
 */
export interface TerminalPage {
  active_count: ActiveCount1;
  available: Available3;
  message: Message16;
  terminals: Terminals;
  unavailable_count: UnavailableCount6;
}
/**
 * 真实状态与输入归属，不由提示符猜测命令成功。
 *
 * Real state without prompt-based success guesses.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TerminalSummary".
 */
export interface TerminalSummary {
  code?: Code12;
  cols: Cols2;
  command: Command3;
  controller: Controller1;
  created_at: CreatedAt14;
  cwd: Cwd2;
  dropped_bytes?: DroppedBytes1;
  environment_name: EnvironmentName1;
  exit_code: ExitCode1;
  finished_at: FinishedAt6;
  member_id: MemberId9;
  message?: Message17;
  mode?: Mode14;
  pid: Pid1;
  project_id: ProjectId51;
  rows: Rows2;
  run_id: RunId15;
  session_id: SessionId66;
  status: Status24;
  terminal_id: TerminalId3;
  tool_call_id: ToolCallId5;
}
/**
 * 使用终端身份而非任意 PID。 Address an owned terminal, never an arbitrary PID.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TerminalParams".
 */
export interface TerminalParams {
  terminal_id: TerminalId4;
}
/**
 * 公开状态与按帧分页的输出。 Public state and frame-paged output.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TerminalView".
 */
export interface TerminalView {
  next_seq: NextSeq1;
  output: Output2;
  summary: TerminalSummary;
  truncated: Truncated7;
}
/**
 * 顺序编号的合并 PTY 输出，不冒充独立 stderr。 Ordered merged PTY output.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TerminalChunk".
 */
export interface TerminalChunk {
  seq: Seq7;
  text: Text11;
}
/**
 * 可复制的公开详情片段，原生 provider 状态不出后端。
 *
 * Copyable public detail chunk, excluding native provider state.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TraceDetail".
 */
export interface TraceDetail {
  item: TraceItem;
  links?: Links1;
  next_offset: NextOffset5;
  offset: Offset6;
  seq: Seq9;
  text: Text12;
  total_chars: TotalChars1;
}
/**
 * 轻量轨迹行及精确关联。 Compact trace row with exact associations.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TraceItem".
 */
export interface TraceItem {
  at: At1;
  duration_ms?: DurationMs;
  goal_id?: GoalId7;
  is_error?: IsError1;
  kind: Kind23;
  request_id?: RequestId3;
  run_id: RunId16;
  seq: Seq8;
  status: Status25;
  title: Title13;
  tool_call_id?: ToolCallId6;
  tool_name?: ToolName1;
  updated_seq?: UpdatedSeq;
  usage?: TokenUsage | null;
}
/**
 * 来自已保存结果的成果引用。 Artifact references from saved results.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TraceLink".
 */
export interface TraceLink {
  identity: Identity;
  kind: Kind24;
  title: Title14;
}
/**
 * 通过真实序号分段读取详情。 Read detail chunks by real fact identity.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TraceDetailParams".
 */
export interface TraceDetailParams {
  offset?: Offset7;
  part?: Part;
  seq: Seq10;
  session_id: SessionId67;
}
/**
 * 轨迹摘要页，不携带全部工具正文。 Trace summaries without full tool bodies.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TracePage".
 */
export interface TracePage {
  before_seq: BeforeSeq6;
  items: Items5;
  job_issues?: JobIssues;
  jobs?: Jobs;
  next_job_offset?: NextJobOffset;
  updates?: Updates;
  watermark: Watermark1;
}
/**
 * 按运行与事实游标筛选轨迹。 Filter trace by run and fact cursor.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "TraceParams".
 */
export interface TraceParams {
  before_seq?: BeforeSeq7;
  errors_only?: ErrorsOnly;
  job_offset?: JobOffset;
  limit?: Limit13;
  run_id?: RunId17;
  session_id: SessionId68;
  tool?: Tool;
  watch_seqs?: WatchSeqs;
}
/**
 * 仅允许保存一个受支持的默认模型标识。
 *
 * Allow saving only one supported default model ID.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "UpdateConfigParams".
 */
export interface UpdateConfigParams {
  model_id: ModelId16;
  run?: RunLimits | null;
}
/**
 * 单写者更新可选工作归属，不改变 Goal 接纳规则。
 *
 * Single-writer updates to optional work ownership without changing goal admission.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "UpdateSpaceWorkParams".
 */
export interface UpdateSpaceWorkParams {
  action: Action9;
  member_id?: MemberId10;
  operation_id: OperationId24;
  result?: Result3;
  run_id?: RunId18;
  status?: Status26;
  task_id: TaskId26;
  work_id: WorkId3;
}
/**
 * 以版本和操作 ID 防止旧页面覆盖新结论。 Guard edits with a revision and operation identity.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "UpdateTaskParams".
 */
export interface UpdateTaskParams {
  expected_revision: ExpectedRevision11;
  fields: TaskFields;
  operation_id: OperationId25;
  task_id: TaskId27;
}
/**
 * 用户修改任务流程；复用任务版本，不改运行报告。
 *
 * Edit task workflow using task revisions.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "UpdateTaskWorkflowParams".
 */
export interface UpdateTaskWorkflowParams {
  expected_revision: ExpectedRevision12;
  operation_id: OperationId26;
  task_id: TaskId28;
  workflow: TaskWorkflow | null;
}
/**
 * 工作定义、最新进度和已有运行引用。
 *
 * Definitions, progress and existing execution references.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkGraphView".
 */
export interface WorkGraphView {
  activity: SpaceChatView;
  goals?: Goals1;
  issues?: Issues5;
  items: Items6;
  suggested_items: SuggestedItems;
  task: TaskView;
}
/**
 * 组合目录和当前项目默认，不把单项故障当成空库。
 *
 * Catalog with project default and explicit issues.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkStyleCatalog".
 */
export interface WorkStyleCatalog {
  default_style_id?: DefaultStyleId;
  issues?: Issues6;
  styles?: Styles;
}
/**
 * 显式设置或清除未来任务默认。 Set or clear the default for future tasks.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkStyleDefault".
 */
export interface WorkStyleDefault {
  project_id: ProjectId52;
  style_id: StyleId3;
}
/**
 * 全局目录可选附带项目默认。 Global catalog optionally includes a project default.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkStyleQuery".
 */
export interface WorkStyleQuery {
  project_id?: ProjectId53;
}
/**
 * 按已知身份停止或继续内部工作。
 *
 * Stop or continue identified internal work.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkerControlParams".
 */
export interface WorkerControlParams {
  action: Action10;
  prompt?: Prompt3;
  session_id: SessionId69;
  worker_id: WorkerId;
}
/**
 * 子卡片列表，不进入左侧正式会话树。
 *
 * Worker cards, excluded from the formal session tree.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
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
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkerRecord".
 */
export interface WorkerRecord {
  active_seconds?: ActiveSeconds1;
  assignment: SpawnWorkerArgs;
  code?: Code13;
  created_at: CreatedAt15;
  goal_id: GoalId8;
  model_id: ModelId17;
  owner_run_id: OwnerRunId;
  owner_session_id: OwnerSessionId;
  pending_messages?: PendingMessages;
  requests?: Requests6;
  result?: Result4;
  run_id?: RunId19;
  session_id: SessionId70;
  status: Status27;
  tools?: Tools3;
  updated_at: UpdatedAt12;
  worker_id: WorkerId1;
}
/**
 * 一个独立、有边界的子任务；不要求收益评分。
 *
 * One bounded independent assignment, without benefit scores.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "SpawnWorkerArgs".
 */
export interface SpawnWorkerArgs {
  context_mode?: ContextMode1;
  mode?: Mode15;
  objective: Objective7;
  role?: Role4;
  scope?: Scope18;
}
/**
 * 用户会话中的子工作入口。
 *
 * Worker access within an owning user session.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkerSessionParams".
 */
export interface WorkerSessionParams {
  session_id: SessionId71;
}
/**
 * 模板目录与单独的加载问题。
 *
 * Template catalog and optional loading issues.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WorkflowCatalog".
 */
export interface WorkflowCatalog {
  issues?: Issues7;
  templates?: Templates1;
}
/**
 * 向当前控制者的真实输入通道写入。
 *
 * Write to the current controller's real input channel.
 *
 * This interface was referenced by `ProtocolV11`'s JSON-Schema
 * via the `definition` "WriteTerminalParams".
 */
export interface WriteTerminalParams {
  terminal_id: TerminalId5;
  text: Text13;
}
