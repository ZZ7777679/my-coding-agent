/** M5 已登记的明确 IPC 能力。 Explicit registered M5 IPC capabilities. */
import type { ProtocolV12 as P } from '../generated/protocol'
import type { Backend } from './backend'
import { validate } from '../shared/validation'
import defaults from '../../../../src/my_agent/defaults.json'

type Register = (
  channel: string,
  count: number,
  action: (...args: unknown[]) => Promise<unknown>
) => void
const routes: ReadonlyArray<readonly [string, string, keyof P, keyof P]> = [
  [
    'agent:m6-renameNavigation',
    'navigation.rename',
    'RenameNavigationParams',
    'NavigationItemName'
  ],
  ['agent:m6-listWorkStyles', 'workstyles.list', 'WorkStyleQuery', 'WorkStyleCatalog'],
  ['agent:m6-saveWorkStyle', 'workstyles.save', 'SaveWorkStyle', 'WorkStyle'],
  ['agent:m6-captureWorkStyle', 'workstyles.capture', 'CaptureWorkStyle', 'WorkStyle'],
  ['agent:m6-defaultWorkStyle', 'workstyles.default', 'WorkStyleDefault', 'WorkStyleCatalog'],
  ['agent:m6-parseWorkStyle', 'workstyles.parse', 'ParseWorkStyle', 'WorkStyle'],
  ['agent:m6-applyWorkStyle', 'workstyles.apply', 'ApplyWorkStyle', 'TaskView'],
  ['agent:m6-listCheckpoints', 'checkpoints.list', 'CheckpointParams', 'CheckpointPage'],
  ['agent:m6-previewRestore', 'checkpoints.preview', 'PreviewCheckpointParams', 'RestorePreview'],
  ['agent:m6-restoreCheckpoint', 'checkpoints.restore', 'RestoreCheckpointParams', 'RestoreResult'],
  ['agent:m5-getWorkGraph', 'spaces.work_graph', 'SpaceParams', 'WorkGraphView'],
  ['agent:m5-saveWorkGraph', 'spaces.work_graph_save', 'SaveWorkGraphParams', 'WorkGraphView'],
  ['agent:m5-startWorkGraph', 'spaces.work_graph_start', 'StartWorkGraphParams', 'SpaceChatView'],
  ['agent:m5-updateSpaceWork', 'spaces.work', 'UpdateSpaceWorkParams', 'TaskView'],
  ['agent:m5-generateTeam', 'spaces.generate', 'GenerateTeamParams', 'TeamGeneration'],
  ['agent:m5-getSpaceChat', 'spaces.chat_view', 'SpaceChatPageParams', 'SpaceChatView'],
  ['agent:m5-sendSpaceChat', 'spaces.chat', 'SpaceChatParams', 'SpaceChatView'],
  ['agent:m5-startSpaceRound', 'spaces.start_round', 'StartSpaceRoundParams', 'SpaceChatView'],
  ['agent:m5-stopSpaceRound', 'spaces.stop', 'StopSpaceRoundParams', 'SpaceChatView'],
  ['agent:m5-listTeamTemplates', 'spaces.templates', 'EmptyParams', 'TeamTemplatesResult'],
  ['agent:m5-saveTeamTemplate', 'spaces.template_save', 'SaveTeamTemplateParams', 'TeamTemplate'],
  ['agent:m5-copyTeamTemplate', 'spaces.template_copy', 'CopyTeamTemplateParams', 'TeamTemplate'],
  [
    'agent:m5-importTeamTemplate',
    'spaces.template_import',
    'ImportTeamTemplateParams',
    'TeamTemplate'
  ],
  [
    'agent:m5-exportTeamTemplate',
    'spaces.template_export',
    'TeamTemplateParams',
    'TeamTemplateExport'
  ],
  ['agent:m5-documentsList', 'documents.list', 'DocumentListParams', 'DocumentListing'],
  ['agent:m5-documentsRead', 'documents.read', 'DocumentParams', 'DocumentView'],
  ['agent:m5-documentsSearch', 'documents.search', 'DocumentSearchParams', 'DocumentSearchResult'],
  ['agent:m5-documentsSave', 'documents.save', 'SaveDocumentParams', 'DocumentView'],
  ['agent:m5-documentsDrafts', 'documents.drafts', 'DocumentSessionParams', 'DraftPage'],
  ['agent:m5-documentsDraft', 'documents.draft', 'SaveDocumentParams', 'DraftPage'],
  ['agent:m5-documentsOperate', 'documents.operate', 'DocumentOperationParams', 'OperationResult'],
  ['agent:m5-documentsPatch', 'documents.patch', 'PatchDocumentsParams', 'OperationResult'],
  ['agent:m5-documentsDiff', 'documents.diff', 'DocumentChangeParams', 'DocumentDiff'],
  ['agent:m5-documentsRestore', 'documents.restore', 'DocumentChangeParams', 'OperationResult'],
  ['agent:m5-listTerminals', 'terminals.list', 'ListTerminalsParams', 'TerminalPage'],
  ['agent:m5-openTerminal', 'terminals.open', 'OpenTerminalParams', 'TerminalView'],
  ['agent:m5-readTerminal', 'terminals.read', 'ReadTerminalParams', 'TerminalView'],
  ['agent:m5-writeTerminal', 'terminals.write', 'WriteTerminalParams', 'TerminalView'],
  ['agent:m5-resizeTerminal', 'terminals.resize', 'ResizeTerminalParams', 'TerminalView'],
  ['agent:m5-controlTerminal', 'terminals.control', 'TerminalControlParams', 'TerminalView'],
  ['agent:m5-interruptTerminal', 'terminals.interrupt', 'TerminalParams', 'TerminalView'],
  ['agent:m5-closeTerminal', 'terminals.stop', 'TerminalParams', 'TerminalView'],
  ['agent:m5-getGitStatus', 'git.status', 'GitProjectParams', 'GitStatus'],
  ['agent:m5-getGitSettings', 'git.settings', 'GitProjectParams', 'GitSettings'],
  ['agent:m5-configureGit', 'git.configure', 'ConfigureGitParams', 'GitSettings'],
  ['agent:m5-getGitDiff', 'git.diff', 'GitDiffParams', 'GitDiff'],
  ['agent:m5-stageGitPaths', 'git.stage', 'GitPathsParams', 'GitStatus'],
  ['agent:m5-unstageGitPaths', 'git.unstage', 'GitPathsParams', 'GitStatus'],
  ['agent:m5-initGitRepository', 'git.init', 'GitProjectParams', 'GitStatus'],
  ['agent:m5-commitGit', 'git.commit', 'GitCommitParams', 'GitCommitResult'],
  ['agent:m5-getGitHistory', 'git.history', 'GitHistoryParams', 'GitHistory'],
  [
    'agent:m5-getLanguageServers',
    'intelligence.list',
    'IntelligenceParams',
    'LanguageServerCatalog'
  ],
  [
    'agent:m5-saveLanguageServers',
    'intelligence.configure',
    'SaveLanguageServers',
    'LanguageServerCatalog'
  ],
  ['agent:m5-queryLanguage', 'intelligence.query', 'LanguageQuery', 'LanguageResult'],
  ['agent:m5-importAttachment', 'attachments.import', 'ImportAttachment', 'Attachment'],
  ['agent:m5-uploadImageChunk', 'attachments.chunk', 'ImageChunk', 'AttachmentUpload'],
  ['agent:m5-readAttachment', 'attachments.read', 'AttachmentParams', 'AttachmentView']
]

/** 沿主进程既有来源检查登记接口。 Register through the existing main-process sender checks. */
export function registerM5Ipc(register: Register, ready: () => Promise<Backend>): void {
  for (const [channel, method, input, output] of routes) {
    register(channel, 1, async (value) => {
      const service = await ready()
      const params = validate(input, value)
      // 文件搜索可被替代 / 退出取消；Git 命令在后端计时，排队不占命令预算。
      // Search cancels on supersession/exit; backend Git timing excludes lock queue time.
      if (method === 'documents.search' || method.startsWith('git.'))
        return service.call(method, params, output, null)
      if (method === 'intelligence.query') {
        const query = validate('LanguageQuery', value)
        const catalog = await service.call(
          'intelligence.list',
          { project_id: query.project_id },
          'LanguageServerCatalog'
        )
        return service.call(
          method,
          params,
          output,
          ((catalog.timeout_seconds ?? defaults.intelligence.timeout_seconds) * 2 +
            defaults.execution.cleanup_timeout_seconds) *
            1000 +
            defaults.http.rpc_timeout_grace_ms
        )
      }
      return service.call(method, params, output)
    })
  }
}
