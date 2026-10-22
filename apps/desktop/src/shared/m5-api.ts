/** M5 明确能力接口，数据类型仅来自生成协议。 Explicit M5 capabilities using generated contracts only. */
import type { ProtocolV13 as P } from '../generated/protocol'
import type { Result } from './api'

export interface M5DesktopAPI {
  /** 重命名导航项，保持身份和项目文件。 Rename a navigation label, retaining identity and files. */
  renameNavigation(params: P['RenameNavigationParams']): Promise<Result<P['NavigationItemName']>>
  /** 打开已登记项目的目录。 Open a registered project directory. */
  openProjectDirectory(params: P['EnvironmentProjectParams']): Promise<Result<P['EmptyParams']>>
  /** 读取组合工作方式及项目默认。 Read composite workstyles and project default. */
  listWorkStyles(params: P['WorkStyleQuery']): Promise<Result<P['WorkStyleCatalog']>>
  /** 保存组合定义。 Save composite definitions. */
  saveWorkStyle(params: P['SaveWorkStyle']): Promise<Result<P['WorkStyle']>>
  /** 从任务生成可编辑预览。 Preview reusable definitions from a task. */
  captureWorkStyle(params: P['CaptureWorkStyle']): Promise<Result<P['WorkStyle']>>
  /** 保存未来任务默认。 Save future-task default. */
  defaultWorkStyle(params: P['WorkStyleDefault']): Promise<Result<P['WorkStyleCatalog']>>
  /** 解析导入文本。 Parse imported text. */
  parseWorkStyle(params: P['ParseWorkStyle']): Promise<Result<P['WorkStyle']>>
  /** 显式采用模板定义，保留历史。 Adopt template definitions with retained history. */
  applyWorkStyle(params: P['ApplyWorkStyle']): Promise<Result<P['TaskView']>>
  /** 读取请求检查点。 Read request checkpoints. */
  listCheckpoints(params: P['CheckpointParams']): Promise<Result<P['CheckpointPage']>>
  /** 预览实际恢复差异。 Preview actual restoration changes. */
  previewRestore(params: P['PreviewCheckpointParams']): Promise<Result<P['RestorePreview']>>
  /** 恢复代码或从原消息重新开始。 Restore code or restart from the selected message. */
  restoreCheckpoint(params: P['RestoreCheckpointParams']): Promise<Result<P['RestoreResult']>>
  /** 读取开关和可恢复备份。 Read switch and recoverable backup. */
  getGitSettings(params: P['GitProjectParams']): Promise<Result<P['GitSettings']>>
  /** 移走或恢复项目自身 Git 元数据。 Relocate or restore this project's Git metadata. */
  configureGit(params: P['ConfigureGitParams']): Promise<Result<P['GitSettings']>>
  /** 读取任务工作图。 Read a task work graph. */
  getWorkGraph(params: P['SpaceParams']): Promise<Result<P['WorkGraphView']>>
  /** 保存任务工作定义。 Save task work definitions. */
  saveWorkGraph(params: P['SaveWorkGraphParams']): Promise<Result<P['WorkGraphView']>>
  /** 执行选择的工作范围。 Execute selected work. */
  startWorkGraph(params: P['StartWorkGraphParams']): Promise<Result<P['SpaceChatView']>>
  /** 原生选择文件并保存输入快照。 Pick native files and save input snapshots. */
  pickAttachments(params: P['DocumentSessionParams']): Promise<Result<P['AttachmentPage']>>
  /** 更新工作归属。 Update work ownership. */
  updateSpaceWork(params: P['UpdateSpaceWorkParams']): Promise<Result<P['TaskView']>>
  /** spaces.generate 的受信入口。 Trusted spaces.generate entry. */
  generateTeam(params: P['GenerateTeamParams']): Promise<Result<P['TeamGeneration']>>
  /** spaces.chat_view 的受信入口。 Trusted spaces.chat_view entry. */
  getSpaceChat(params: P['SpaceChatPageParams']): Promise<Result<P['SpaceChatView']>>
  /** spaces.chat 的受信入口。 Trusted spaces.chat entry. */
  sendSpaceChat(params: P['SpaceChatParams']): Promise<Result<P['SpaceChatView']>>
  /** spaces.start_round 的受信入口。 Trusted spaces.start_round entry. */
  startSpaceRound(params: P['StartSpaceRoundParams']): Promise<Result<P['SpaceChatView']>>
  /** spaces.stop 的受信入口。 Trusted spaces.stop entry. */
  stopSpaceRound(params: P['StopSpaceRoundParams']): Promise<Result<P['SpaceChatView']>>
  /** spaces.templates 的受信入口。 Trusted spaces.templates entry. */
  listTeamTemplates(params: P['EmptyParams']): Promise<Result<P['TeamTemplatesResult']>>
  /** spaces.template_save 的受信入口。 Trusted spaces.template_save entry. */
  saveTeamTemplate(params: P['SaveTeamTemplateParams']): Promise<Result<P['TeamTemplate']>>
  /** spaces.template_copy 的受信入口。 Trusted spaces.template_copy entry. */
  copyTeamTemplate(params: P['CopyTeamTemplateParams']): Promise<Result<P['TeamTemplate']>>
  /** spaces.template_import 的受信入口。 Trusted spaces.template_import entry. */
  importTeamTemplate(params: P['ImportTeamTemplateParams']): Promise<Result<P['TeamTemplate']>>
  /** spaces.template_export 的受信入口。 Trusted spaces.template_export entry. */
  exportTeamTemplate(params: P['TeamTemplateParams']): Promise<Result<P['TeamTemplateExport']>>
  /** documents.list 的受信入口。 Trusted documents.list entry. */
  documentsList(params: P['DocumentListParams']): Promise<Result<P['DocumentListing']>>
  /** documents.read 的受信入口。 Trusted documents.read entry. */
  documentsRead(params: P['DocumentParams']): Promise<Result<P['DocumentView']>>
  /** documents.search 的受信入口。 Trusted documents.search entry. */
  documentsSearch(params: P['DocumentSearchParams']): Promise<Result<P['DocumentSearchResult']>>
  /** documents.save 的受信入口。 Trusted documents.save entry. */
  documentsSave(params: P['SaveDocumentParams']): Promise<Result<P['DocumentView']>>
  /** documents.drafts 的受信入口。 Trusted documents.drafts entry. */
  documentsDrafts(params: P['DocumentSessionParams']): Promise<Result<P['DraftPage']>>
  /** documents.draft 的受信入口。 Trusted documents.draft entry. */
  documentsDraft(params: P['SaveDocumentParams']): Promise<Result<P['DraftPage']>>
  /** documents.operate 的受信入口。 Trusted documents.operate entry. */
  documentsOperate(params: P['DocumentOperationParams']): Promise<Result<P['OperationResult']>>
  /** documents.patch 的受信入口。 Trusted documents.patch entry. */
  documentsPatch(params: P['PatchDocumentsParams']): Promise<Result<P['OperationResult']>>
  /** documents.diff 的受信入口。 Trusted documents.diff entry. */
  documentsDiff(params: P['DocumentChangeParams']): Promise<Result<P['DocumentDiff']>>
  /** documents.restore 的受信入口。 Trusted documents.restore entry. */
  documentsRestore(params: P['DocumentChangeParams']): Promise<Result<P['OperationResult']>>
  /** terminals.list 的受信入口。 Trusted terminals.list entry. */
  listTerminals(params: P['ListTerminalsParams']): Promise<Result<P['TerminalPage']>>
  /** terminals.open 的受信入口。 Trusted terminals.open entry. */
  openTerminal(params: P['OpenTerminalParams']): Promise<Result<P['TerminalView']>>
  /** terminals.read 的受信入口。 Trusted terminals.read entry. */
  readTerminal(params: P['ReadTerminalParams']): Promise<Result<P['TerminalView']>>
  /** terminals.write 的受信入口。 Trusted terminals.write entry. */
  writeTerminal(params: P['WriteTerminalParams']): Promise<Result<P['TerminalView']>>
  /** terminals.resize 的受信入口。 Trusted terminals.resize entry. */
  resizeTerminal(params: P['ResizeTerminalParams']): Promise<Result<P['TerminalView']>>
  /** terminals.control 的受信入口。 Trusted terminals.control entry. */
  controlTerminal(params: P['TerminalControlParams']): Promise<Result<P['TerminalView']>>
  /** terminals.interrupt 的受信入口。 Trusted terminals.interrupt entry. */
  interruptTerminal(params: P['TerminalParams']): Promise<Result<P['TerminalView']>>
  /** terminals.stop 的受信入口。 Trusted terminals.stop entry. */
  closeTerminal(params: P['TerminalParams']): Promise<Result<P['TerminalView']>>
  /** git.status 的受信入口。 Trusted git.status entry. */
  getGitStatus(params: P['GitProjectParams']): Promise<Result<P['GitStatus']>>
  /** git.diff 的受信入口。 Trusted git.diff entry. */
  getGitDiff(params: P['GitDiffParams']): Promise<Result<P['GitDiff']>>
  /** git.stage 的受信入口。 Trusted git.stage entry. */
  stageGitPaths(params: P['GitPathsParams']): Promise<Result<P['GitStatus']>>
  /** git.unstage 的受信入口。 Trusted git.unstage entry. */
  unstageGitPaths(params: P['GitPathsParams']): Promise<Result<P['GitStatus']>>
  /** git.init 的受信入口。 Trusted git.init entry. */
  initGitRepository(params: P['GitProjectParams']): Promise<Result<P['GitStatus']>>
  /** git.commit 的受信入口。 Trusted git.commit entry. */
  commitGit(params: P['GitCommitParams']): Promise<Result<P['GitCommitResult']>>
  /** git.history 的受信入口。 Trusted git.history entry. */
  getGitHistory(params: P['GitHistoryParams']): Promise<Result<P['GitHistory']>>
  /** intelligence.list 的受信入口。 Trusted intelligence.list entry. */
  getLanguageServers(params: P['IntelligenceParams']): Promise<Result<P['LanguageServerCatalog']>>
  /** intelligence.configure 的受信入口。 Trusted intelligence.configure entry. */
  saveLanguageServers(params: P['SaveLanguageServers']): Promise<Result<P['LanguageServerCatalog']>>
  /** intelligence.query 的受信入口。 Trusted intelligence.query entry. */
  queryLanguage(params: P['LanguageQuery']): Promise<Result<P['LanguageResult']>>
  /** attachments.import 的受信入口。 Trusted attachments.import entry. */
  importAttachment(params: P['ImportAttachment']): Promise<Result<P['Attachment']>>
  /** attachments.chunk 的受信入口。 Trusted attachments.chunk entry. */
  uploadImageChunk(params: P['ImageChunk']): Promise<Result<P['AttachmentUpload']>>
  /** attachments.read 的受信入口。 Trusted attachments.read entry. */
  readAttachment(params: P['AttachmentParams']): Promise<Result<P['AttachmentView']>>
  /** 用户指定外部编辑器打开项目文件。 Open a project file in the user-selected external editor. */
  openExternalEditor(params: P['DocumentParams']): Promise<Result<P['EmptyParams']>>
}
