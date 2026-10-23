/** 集中代码、终端、本地 Git 和语言服务，面板切换保留实例。 Centralize code, terminal, local Git and LSP while retaining mounted panels. */
import { useRef, useState, useEffect } from 'react'
import { WorkspaceEditor } from './WorkspaceEditor'
import { TerminalPanel } from './TerminalPanel'
import { LocalGitPanel } from './LocalGitPanel'
import { CodeIntelligence } from './CodeIntelligence'
import { attachmentSelection } from './InputAttachments'

/** 各能力单独占用主区域，避免所有管理卡片常驻。 Give each capability its own main area instead of permanent stacked cards. */
export function CodeWorkbench({
  projectId,
  sessionId,
  visible,
  onChat
}: {
  projectId: string
  sessionId: string | null
  visible: boolean
  onChat: () => void
}) {
  const [tab, setTab] = useState<'files' | 'terminal' | 'git' | 'language'>('files')
  const [error, setError] = useState('')
  const [opening, setOpening] = useState(false)
  const [terminalId, setTerminalId] = useState<string | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  /** 在已选择目录启动真实终端，不把文件路径拼进 shell 命令。
   * Open a real terminal at the selected directory without interpolating shell commands. */
  async function openTerminal(cwd: string, shell: 'powershell' | 'cmd') {
    if (opening) return
    setOpening(true)
    setError('')
    try {
      const result = await window.agent.openTerminal({
        project_id: projectId,
        session_id: sessionId,
        cwd,
        command: {
          kind: 'program',
          program: shell === 'cmd' ? 'cmd.exe' : 'powershell.exe',
          arguments: shell === 'cmd' ? ['/D'] : ['-NoLogo', '-NoProfile']
        }
      })
      if (!mounted.current) return
      if (result.ok) {
        setTerminalId(result.data.summary.terminal_id)
        setTab('terminal')
      } else setError(result.error.message)
    } catch (cause) {
      if (mounted.current)
        setError(cause instanceof Error ? cause.message : '终端启动结果未知，请刷新核对。')
    } finally {
      if (mounted.current) setOpening(false)
    }
  }
  return (
    <section className="code-workbench">
      <nav className="workbench-tabs" aria-label="编码工作台">
        <button onClick={() => setTab('files')}>文件 / 编辑器</button>
        <button onClick={() => setTab('terminal')}>交互终端</button>
        <button onClick={() => setTab('git')}>本地 Git</button>
        <button onClick={() => setTab('language')}>代码理解</button>
        <button onClick={onChat}>关闭工作台</button>
      </nav>
      {error && <small role="alert">{error}</small>}
      <div className="workbench-pane" hidden={tab !== 'files'}>
        <WorkspaceEditor
          sessionId={sessionId}
          terminalBusy={opening}
          onTerminal={(cwd, shell) => void openTerminal(cwd, shell)}
          onRunFile={(path) => {
            window.dispatchEvent(
              new CustomEvent('agent:compose-file-run', { detail: { sessionId, path } })
            )
            onChat()
          }}
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
        <TerminalPanel
          projectId={projectId}
          sessionId={sessionId}
          visible={visible && tab === 'terminal'}
          selectedTerminalId={terminalId}
        />
      </div>
      <div className="workbench-pane" hidden={tab !== 'git'}>
        <LocalGitPanel projectId={projectId} visible={visible && tab === 'git'} />
      </div>
      <div className="workbench-pane" hidden={tab !== 'language'}>
        <CodeIntelligence projectId={projectId} />
      </div>
    </section>
  )
}
