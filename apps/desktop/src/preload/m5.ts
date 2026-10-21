/** M5 有限 preload 转发。 Restricted M5 preload forwarding. */
import type { ProtocolV12 as P } from '../generated/protocol'
import type { M5DesktopAPI } from '../shared/m5-api'
import type { Result } from '../shared/api'

type Invoke = <K extends keyof P>(
  channel: string,
  contract: K,
  args?: unknown[]
) => Promise<Result<P[K]>>

/** 按公开契约装配方法，不暴露通用 RPC。 Compose explicit contracts without exposing arbitrary RPC. */
export function m5Api(invoke: Invoke): M5DesktopAPI {
  return {
    renameNavigation: (params) =>
      invoke('agent:m6-renameNavigation', 'NavigationItemName', [params]),
    openProjectDirectory: (params) => invoke('agent:m6-project-directory', 'EmptyParams', [params]),
    listWorkStyles: (params) => invoke('agent:m6-listWorkStyles', 'WorkStyleCatalog', [params]),
    saveWorkStyle: (params) => invoke('agent:m6-saveWorkStyle', 'WorkStyle', [params]),
    captureWorkStyle: (params) => invoke('agent:m6-captureWorkStyle', 'WorkStyle', [params]),
    defaultWorkStyle: (params) => invoke('agent:m6-defaultWorkStyle', 'WorkStyleCatalog', [params]),
    parseWorkStyle: (params) => invoke('agent:m6-parseWorkStyle', 'WorkStyle', [params]),
    applyWorkStyle: (params) => invoke('agent:m6-applyWorkStyle', 'TaskView', [params]),
    listCheckpoints: (params) => invoke('agent:m6-listCheckpoints', 'CheckpointPage', [params]),
    previewRestore: (params) => invoke('agent:m6-previewRestore', 'RestorePreview', [params]),
    restoreCheckpoint: (params) => invoke('agent:m6-restoreCheckpoint', 'RestoreResult', [params]),
    getGitSettings: (params) => invoke('agent:m5-getGitSettings', 'GitSettings', [params]),
    configureGit: (params) => invoke('agent:m5-configureGit', 'GitSettings', [params]),
    pickAttachments: (params) => invoke('agent:m5-pick-attachments', 'AttachmentPage', [params]),
    updateSpaceWork: (params) => invoke('agent:m5-updateSpaceWork', 'TaskView', [params]),
    getWorkGraph: (params) => invoke('agent:m5-getWorkGraph', 'WorkGraphView', [params]),
    saveWorkGraph: (params) => invoke('agent:m5-saveWorkGraph', 'WorkGraphView', [params]),
    startWorkGraph: (params) => invoke('agent:m5-startWorkGraph', 'SpaceChatView', [params]),
    generateTeam: (params) => invoke('agent:m5-generateTeam', 'TeamGeneration', [params]),
    getSpaceChat: (params) => invoke('agent:m5-getSpaceChat', 'SpaceChatView', [params]),
    sendSpaceChat: (params) => invoke('agent:m5-sendSpaceChat', 'SpaceChatView', [params]),
    startSpaceRound: (params) => invoke('agent:m5-startSpaceRound', 'SpaceChatView', [params]),
    stopSpaceRound: (params) => invoke('agent:m5-stopSpaceRound', 'SpaceChatView', [params]),
    listTeamTemplates: (params) =>
      invoke('agent:m5-listTeamTemplates', 'TeamTemplatesResult', [params]),
    saveTeamTemplate: (params) => invoke('agent:m5-saveTeamTemplate', 'TeamTemplate', [params]),
    copyTeamTemplate: (params) => invoke('agent:m5-copyTeamTemplate', 'TeamTemplate', [params]),
    importTeamTemplate: (params) => invoke('agent:m5-importTeamTemplate', 'TeamTemplate', [params]),
    exportTeamTemplate: (params) =>
      invoke('agent:m5-exportTeamTemplate', 'TeamTemplateExport', [params]),
    documentsList: (params) => invoke('agent:m5-documentsList', 'DocumentListing', [params]),
    documentsRead: (params) => invoke('agent:m5-documentsRead', 'DocumentView', [params]),
    documentsSearch: (params) =>
      invoke('agent:m5-documentsSearch', 'DocumentSearchResult', [params]),
    documentsSave: (params) => invoke('agent:m5-documentsSave', 'DocumentView', [params]),
    documentsDrafts: (params) => invoke('agent:m5-documentsDrafts', 'DraftPage', [params]),
    documentsDraft: (params) => invoke('agent:m5-documentsDraft', 'DraftPage', [params]),
    documentsOperate: (params) => invoke('agent:m5-documentsOperate', 'OperationResult', [params]),
    documentsPatch: (params) => invoke('agent:m5-documentsPatch', 'OperationResult', [params]),
    documentsDiff: (params) => invoke('agent:m5-documentsDiff', 'DocumentDiff', [params]),
    documentsRestore: (params) => invoke('agent:m5-documentsRestore', 'OperationResult', [params]),
    listTerminals: (params) => invoke('agent:m5-listTerminals', 'TerminalPage', [params]),
    openTerminal: (params) => invoke('agent:m5-openTerminal', 'TerminalView', [params]),
    readTerminal: (params) => invoke('agent:m5-readTerminal', 'TerminalView', [params]),
    writeTerminal: (params) => invoke('agent:m5-writeTerminal', 'TerminalView', [params]),
    resizeTerminal: (params) => invoke('agent:m5-resizeTerminal', 'TerminalView', [params]),
    controlTerminal: (params) => invoke('agent:m5-controlTerminal', 'TerminalView', [params]),
    interruptTerminal: (params) => invoke('agent:m5-interruptTerminal', 'TerminalView', [params]),
    closeTerminal: (params) => invoke('agent:m5-closeTerminal', 'TerminalView', [params]),
    getGitStatus: (params) => invoke('agent:m5-getGitStatus', 'GitStatus', [params]),
    getGitDiff: (params) => invoke('agent:m5-getGitDiff', 'GitDiff', [params]),
    stageGitPaths: (params) => invoke('agent:m5-stageGitPaths', 'GitStatus', [params]),
    unstageGitPaths: (params) => invoke('agent:m5-unstageGitPaths', 'GitStatus', [params]),
    initGitRepository: (params) => invoke('agent:m5-initGitRepository', 'GitStatus', [params]),
    commitGit: (params) => invoke('agent:m5-commitGit', 'GitCommitResult', [params]),
    getGitHistory: (params) => invoke('agent:m5-getGitHistory', 'GitHistory', [params]),
    getLanguageServers: (params) =>
      invoke('agent:m5-getLanguageServers', 'LanguageServerCatalog', [params]),
    saveLanguageServers: (params) =>
      invoke('agent:m5-saveLanguageServers', 'LanguageServerCatalog', [params]),
    queryLanguage: (params) => invoke('agent:m5-queryLanguage', 'LanguageResult', [params]),
    importAttachment: (params) => invoke('agent:m5-importAttachment', 'Attachment', [params]),
    uploadImageChunk: (params) => invoke('agent:m5-uploadImageChunk', 'AttachmentUpload', [params]),
    readAttachment: (params) => invoke('agent:m5-readAttachment', 'AttachmentView', [params]),
    openExternalEditor: (params) => invoke('agent:m5-editor-open', 'EmptyParams', [params])
  }
}
