/** 集中代码、终端、本地 Git 和语言服务，面板切换保留实例。 Centralize code, terminal, local Git and LSP while retaining mounted panels. */
import { useState } from 'react'
import { WorkspaceEditor } from './WorkspaceEditor'
import { TerminalPanel } from './TerminalPanel'
import { LocalGitPanel } from './LocalGitPanel'
import { CodeIntelligence } from './CodeIntelligence'
import { attachmentSelection } from './InputAttachments'

/** 各能力单独占用主区域，避免所有管理卡片常驻。 Give each capability its own main area instead of permanent stacked cards. */
export function CodeWorkbench({
  projectId,
  sessionId,
  onChat
}: {
  projectId: string
  sessionId: string | null
  onChat: () => void
}) {
  const [tab, setTab] = useState<'files' | 'terminal' | 'git' | 'language'>('files')
  const [error, setError] = useState('')
  return (
    <section className="code-workbench">
      <nav className="workbench-tabs" aria-label="编码工作台">
        <button onClick={() => setTab('files')}>文件 / 编辑器</button>
        <button onClick={() => setTab('terminal')}>交互终端</button>
        <button onClick={() => setTab('git')}>本地 Git</button>
        <button onClick={() => setTab('language')}>代码理解</button>
        <button onClick={onChat}>返回对话</button>
      </nav>
      {error && <small role="alert">{error}</small>}
      <div className="workbench-pane" hidden={tab !== 'files'}>
        <WorkspaceEditor
          sessionId={sessionId}
          onReference={async (reference) => {
            if (!sessionId) return
            const result = await window.agent.importAttachment({
              session_id: sessionId,
              ...reference
            })
            if (!result.ok) {
              setError(result.error.message)
              return
            }
            attachmentSelection.set(sessionId, [
              ...(attachmentSelection.get(sessionId) ?? []),
              result.data
            ])
            window.dispatchEvent(
              new CustomEvent('agent:attachment-selected', { detail: { sessionId } })
            )
            onChat()
          }}
        />
      </div>
      <div className="workbench-pane" hidden={tab !== 'terminal'}>
        <TerminalPanel projectId={projectId} sessionId={sessionId} visible={tab === 'terminal'} />
      </div>
      <div className="workbench-pane" hidden={tab !== 'git'}>
        <LocalGitPanel projectId={projectId} visible={tab === 'git'} />
      </div>
      <div className="workbench-pane" hidden={tab !== 'language'}>
        <CodeIntelligence projectId={projectId} />
      </div>
    </section>
  )
}
