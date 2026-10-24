/** 项目对话：模式、快照、流式预览与工具证据。 Project chat with modes, snapshots and tool evidence. */
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { ContextMemory, type KnowledgeUi } from './ContextMemory'
import { Markdown } from './Markdown'
import {
  InputAttachments,
  attachmentSelection,
  type InputAttachmentHandle
} from './InputAttachments'
import type { Attachment } from '../../generated/protocol'
import type { QuestionMaterial } from './KnowledgeDetails'
import { Workers } from './Workers'
import { FailureNotice } from './FailureNotice'
import type { EvolutionEntry } from './EvolutionQuick'
import type {
  ChatEntry,
  ModelId,
  ProjectSummary,
  SessionSummary,
  SessionView,
  SessionSignal,
  GoalView,
  GoalBudget,
  CreateGoalParams
} from '../../generated/protocol'
import { SessionMembership } from './SessionMembership'
import { Collaboration } from './Collaboration'
import { Changes } from './Changes'
import { Checkpoints } from './Checkpoints'
import { ProgramCall, programTools } from './ProgramCards'
import { Goals, GoalBudgetFields, GoalHistory } from './Goals'
import { WebReferences } from './WebReferences'
import { ModelActivity } from './ModelActivity'
import { Reasoning } from './Reasoning'
import { Trace, toolCaption } from './Trace'
import type { WorkspaceSelection } from './TaskNavigation'
import defaults from '../../../../../src/my_agent/defaults.json'

type Props = {
  onReview: (entry: EvolutionEntry) => void
  onSettings: () => void
  review?: ReactNode
  project: ProjectSummary | null
  selected: string | null
  connected: boolean
  visible: boolean
  active: SessionSummary | null
  onStop: (runId: string) => void
  onRunChange: () => void
  onSelect: (selection: WorkspaceSelection) => void
  knowledgeCache: Map<string, KnowledgeUi>
  materialCache: Map<string, QuestionMaterial[]>
}

const names: Record<ModelId, string> = {
  'glm-5.3-flash': 'GLM-5.3-Flash',
  'deepseek-v4.1-flash': 'DeepSeek V4.1 Flash'
}
const collaborationActivities: Record<string, string> = {
  list_collaborators: '读取协作约定',
  read_session: '读取协作会话历史',
  request_collaboration: '发送协作请求',
  read_collaboration: '读取 / 等待协作结果',
  list_changes: '读取修改成果索引',
  read_change: '读取历史差异'
}
const statuses = {
  running: '正在运行',
  stopping: '正在停止并清理',
  completed: '回答结束',
  failed: '运行失败',
  cancelled: '已停止',
  budget_exceeded: '预算已用尽',
  interrupted: '上次运行已中断'
}
/** 将工具正文按原行展示，元信息仍可核对。 Show original source lines alongside tool metadata. */
function toolText(content: string): string {
  try {
    const value: unknown = JSON.parse(content)
    if (
      typeof value === 'object' &&
      value !== null &&
      'content' in value &&
      typeof value.content === 'string'
    ) {
      return JSON.stringify({ ...value, content: undefined }, null, 2) + '\n\n' + value.content
    }
    return JSON.stringify(value, null, 2) ?? content
  } catch {
    return content
  }
}

/** 将后端确认的工具内容作为纯文本显示。 Render backend-confirmed tool content as plain text. */
function HistoryEntry({
  entry,
  reasoningOpen,
  onReasoningToggle
}: {
  entry: ChatEntry
  reasoningOpen: boolean
  onReasoningToggle: (open: boolean) => void
}) {
  if (entry.goal_result) return <GoalHistory goal={entry.goal_result} />
  if (entry.web_result) return <WebReferences result={entry.web_result} />
  if (entry.kind === 'tool.started')
    return (
      <details className="tool-entry">
        <summary>工具 · {entry.call?.name}</summary>
        <pre>{JSON.stringify(entry.call?.arguments, null, 2)}</pre>
      </details>
    )
  if (entry.kind === 'tool.completed' || entry.kind === 'tool.skipped')
    return (
      <details className={'tool-entry ' + (entry.result?.is_error ? 'tool-error' : '')}>
        <summary>
          {entry.kind === 'tool.skipped'
            ? '工具已跳过'
            : entry.result?.is_error
              ? '工具未完成'
              : '工具结果'}
        </summary>
        <pre>{toolText(entry.result?.content ?? '')}</pre>
      </details>
    )
  if (entry.kind === 'run.finished' || entry.kind === 'goal.event')
    return (
      <div className="run-end">
        <p>{entry.text}</p>
        {(entry.partial_text || entry.reasoning) && (
          <details open>
            <summary>中断前的部分输出 · 未完整结束</summary>
            <Reasoning
              text={entry.reasoning ?? ''}
              open={reasoningOpen}
              onToggle={onReasoningToggle}
              streaming={false}
            />
            {entry.partial_text && <Markdown text={entry.partial_text} />}
          </details>
        )}
      </div>
    )
  if (entry.kind === 'assistant' && !entry.text && !entry.reasoning) return null
  return (
    <article className={'chat-message ' + entry.kind}>
      <strong>
        {entry.kind === 'user' ? '你' : entry.model_id ? names[entry.model_id] : 'Agent'}
      </strong>
      {entry.input_status && (
        <small className="input-delivery">
          追加要求 · {entry.input_status === 'queued' ? '已保存，等待处理' : '已纳入后续上下文'}
        </small>
      )}
      <Reasoning
        text={entry.reasoning ?? ''}
        open={reasoningOpen}
        onToggle={onReasoningToggle}
        streaming={false}
      />
      {entry.text && <Markdown text={entry.text} />}
    </article>
  )
}

/** 管理会话归属、快照交接与有界事件缓冲。 Manage session ownership and bounded snapshot handoff. */
export function Chat({
  onReview,
  onSettings,
  review,
  project,
  selected,
  connected,
  visible,
  active,
  onStop,
  onRunChange,
  onSelect,
  knowledgeCache,
  materialCache
}: Props) {
  const [snapshot, setSnapshot] = useState<SessionView | null>(null)
  const [older, setOlder] = useState<ChatEntry[]>([])
  const [olderCursor, setOlderCursor] = useState<number | null>(null)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [prompt, setPrompt] = useState('')
  useEffect(() => {
    /** 文件操作准备可编辑的请求，保留已有草稿及当前模式。
     * Prepare an editable file request without discarding the draft or changing mode. */
    function composeFileRun(event: Event) {
      if (!(event instanceof CustomEvent)) return
      const detail: unknown = event.detail
      if (
        !detail ||
        typeof detail !== 'object' ||
        !('sessionId' in detail) ||
        detail.sessionId !== selected ||
        !('path' in detail) ||
        typeof detail.path !== 'string'
      )
        return
      const request = `请运行项目文件 ${JSON.stringify(detail.path)} 的已保存版本。先确认合适的运行命令，使用项目已有环境，报告实际结果；需要长驻时使用服务或终端工具。`
      setPrompt((draft) => (draft ? `${draft}\n\n${request}` : request))
      requestAnimationFrame(() =>
        document.querySelector<HTMLTextAreaElement>('[aria-label="输入问题"]')?.focus()
      )
    }
    window.addEventListener('agent:compose-file-run', composeFileRun)
    return () => window.removeEventListener('agent:compose-file-run', composeFileRun)
  }, [selected])
  const attachmentInput = useRef<InputAttachmentHandle>(null)
  const visibility = useRef(visible)
  visibility.current = visible
  const [attachments, setAttachments] = useState<Attachment[]>(() =>
    selected ? (attachmentSelection.get(selected) ?? []) : []
  )
  useEffect(() => {
    const refreshAttachments = () =>
      setAttachments(selected ? (attachmentSelection.get(selected) ?? []) : [])
    refreshAttachments()
    window.addEventListener('agent:attachment-selected', refreshAttachments)
    return () => window.removeEventListener('agent:attachment-selected', refreshAttachments)
  }, [selected])
  const [questionMaterials, setQuestionMaterials] = useState<Record<string, QuestionMaterial[]>>(
    () => Object.fromEntries(materialCache)
  )
  /** 材料选择同步保存在会话缓存中，切换会话不丢选择。
   * Cache selected materials synchronously across session switches. */
  function changeMaterials(
    change: (current: Record<string, QuestionMaterial[]>) => Record<string, QuestionMaterial[]>
  ) {
    setQuestionMaterials((current) => {
      const next = change(current)
      for (const [sid, materials] of Object.entries(next)) {
        if (materials !== current[sid]) materialCache.set(sid, materials)
      }
      return next
    })
  }
  const [error, setError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<'normal' | 'plan' | 'goal'>('plan')
  const [goal, setGoal] = useState<GoalView | null>(null)
  const [criteria, setCriteria] = useState('')
  const [goalBudget, setGoalBudget] = useState<GoalBudget>({})
  const [planDocument, setPlanDocument] = useState('')
  const [showChanges, setShowChanges] = useState(false)
  const [showCheckpoints, setShowCheckpoints] = useState(false)
  const [showTrace, setShowTrace] = useState(false)
  const [foldedRuns, setFoldedRuns] = useState<Record<string, boolean>>({})
  const [traceSeq, setTraceSeq] = useState<number | null>(null)
  const [foldedReasoning, setFoldedReasoning] = useState<Record<string, boolean>>({})
  const [changingModel, setChangingModel] = useState(false)
  const notifyRun = useRef(onRunChange)
  notifyRun.current = onRunChange
  const generation = useRef(0)
  const historyElement = useRef<HTMLDivElement>(null)
  const historyAnchor = useRef<{
    sessionId: string
    seq: string | undefined
    top: number
    scrollTop: number
    height: number
  } | null>(null)

  // 插入旧页后维持原消息的位置；浏览器自己的滚动锚定已生效时差值自然为零。
  // Preserve the existing message after prepending; native anchoring yields a zero adjustment.
  useLayoutEffect(() => {
    const anchor = historyAnchor.current
    const container = historyElement.current
    historyAnchor.current = null
    if (!anchor || !container || anchor.sessionId !== selected) return
    const message = anchor.seq
      ? container.querySelector<HTMLElement>(`[data-history-seq="${anchor.seq}"]`)
      : null
    if (message) container.scrollTop += message.getBoundingClientRect().top - anchor.top
    else container.scrollTop = anchor.scrollTop + container.scrollHeight - anchor.height
    followLatest.current = false
  }, [older, selected])
  const retainedSnapshot = useRef(snapshot)
  retainedSnapshot.current = snapshot
  const followLatest = useRef(true)
  const projectId = project?.project_id
  const currentProject = useRef(projectId)
  currentProject.current = projectId
  const currentSelection = useRef(selected)
  currentSelection.current = selected
  useEffect(() => {
    ++generation.current
    setSnapshot(null)
    setOlder([])
    setLoadingOlder(false)
    historyAnchor.current = null
    setShowTrace(false)
    setTraceSeq(null)
    setPrompt('')
    setError('')
    setHistoryError('')
    setPlanDocument('')
    setGoal(null)
    setCriteria('')
    setGoalBudget({})
    setFoldedReasoning({})
    followLatest.current = true
  }, [projectId, selected])

  useEffect(() => {
    if (snapshot) setMode(snapshot.summary.mode ?? 'plan')
  }, [snapshot?.summary.session_id])

  useEffect(() => {
    if (snapshot?.summary.run) notifyRun.current()
  }, [snapshot?.summary.run?.run_id, snapshot?.summary.run?.status])

  useEffect(() => {
    if (followLatest.current && historyElement.current)
      historyElement.current.scrollTop = historyElement.current.scrollHeight
  }, [snapshot?.watermark, snapshot?.delta_index])

  useEffect(() => {
    if (!selected || !connected) return
    const ticket = ++generation.current
    let disposed = false
    let fetching = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let pending: SessionSignal[] = []
    let overflow = false
    let value: SessionView | null =
      retainedSnapshot.current?.summary.session_id === selected ? retainedSnapshot.current : null
    let attached = false
    if (!value) {
      setSnapshot(null)
      setOlder([])
      setOlderCursor(null)
      followLatest.current = true
    }
    setError('')

    /** 对新快照之后的增量去重；缺口返回 false。 Apply post-snapshot deltas; gaps require resync. */
    const applySignal = (signal: SessionSignal): boolean => {
      if (!value || signal.process_epoch !== value.process_epoch) return false
      if (signal.kind === 'model.progress') {
        if (signal.seq < value.watermark) return true
        if (
          signal.seq !== value.watermark ||
          signal.run_id !== value.summary.run?.run_id ||
          signal.message_id !== value.stream_message_id ||
          !signal.model_progress
        )
          return false
        // 快照可能比缓冲事件更新，保留同一请求较新的阶段。
        // A snapshot may be newer than buffered events from the same request.
        if (
          value.model_progress &&
          signal.model_progress.elapsed_ms < value.model_progress.elapsed_ms
        )
          return true
        value = { ...value, model_progress: signal.model_progress }
        return true
      }
      if (signal.kind !== 'text.delta' && signal.kind !== 'reasoning.delta')
        return signal.seq <= value.watermark && signal.kind !== 'resync'
      if (signal.seq < value.watermark) return true
      if (signal.seq !== value.watermark || signal.message_id !== value.stream_message_id)
        return false
      if (signal.delta_index <= value.delta_index) return true
      if (signal.delta_index !== value.delta_index + 1) return false
      value = {
        ...value,
        stream_text: value.stream_text + (signal.kind === 'text.delta' ? signal.text : ''),
        stream_reasoning:
          (value.stream_reasoning ?? '') + (signal.kind === 'reasoning.delta' ? signal.text : ''),
        delta_index: signal.delta_index,
        model_progress: signal.model_progress
      }
      return true
    }

    /** 合并通知触发的读取，避免每个 token 发一次 RPC。 Coalesce refreshes instead of requesting per token. */
    const schedule = () => {
      if (!disposed && !timer)
        timer = setTimeout(() => {
          timer = undefined
          void refresh()
        }, 0)
    }

    /** 先监听再 attach，重放有界缓冲消除快照期间的空隙。 Subscribe first, then replay buffered handoff events. */
    const refresh = async () => {
      if (disposed || fetching) return
      fetching = true
      try {
        const result = await (attached ? window.agent.getSession : window.agent.attachSession)({
          session_id: selected,
          before_seq: null
        })
        if (disposed || ticket !== generation.current) return
        if (!result.ok) {
          setHistoryError(result.error.message)
          return
        }
        setHistoryError('')
        attached = true
        value = result.data
        let needsRefresh = overflow
        overflow = false
        for (const signal of pending) if (!applySignal(signal)) needsRefresh = true
        pending = []
        setSnapshot(value)
        if (needsRefresh) schedule()
      } catch {
        if (!disposed) setHistoryError('会话连接中断。已保存的历史可在重新打开后查看。')
      } finally {
        fetching = false
      }
    }

    const unsubscribe = window.agent.onSessionEvent((signal) => {
      if (disposed || signal.session_id !== selected) return
      if (fetching || !value) {
        if (pending.length < 128) pending.push(signal)
        else overflow = true
        return
      }
      if (applySignal(signal)) setSnapshot(value)
      else schedule()
    })
    void refresh()
    // 轮询仅恢复视图，覆盖断线或最后一条通知丢失；不会重复发送输入。
    // Polling recovers views after missed final events and never resends input.
    const recovery = setInterval(() => {
      if (visibility.current && !document.hidden) void refresh()
    }, defaults.desktop_connection.idle_refresh_ms)
    return () => {
      disposed = true
      if (timer) clearTimeout(timer)
      clearInterval(recovery)
      unsubscribe()
      void window.agent.detachSession(selected).catch(() => undefined)
    }
  }, [selected, connected])

  const goalRunning = goal?.status === 'active'
  const localInterruption = goalRunning && active?.run?.status !== 'stopping'
  const supplementing =
    active?.session_id === selected && active.run?.status === 'running' && !goalRunning
  const blockedByRun = !!active && !localInterruption && !supplementing
  const unfinishedGoal = !!goal && goal.status !== 'completed' && goal.status !== 'cancelled'

  /** 只在发送动作生成操作 ID，失败不自动重发。 Generate operation IDs on explicit send only. */
  const send = async () => {
    if (
      !selected ||
      busy ||
      blockedByRun ||
      !prompt.trim() ||
      snapshot?.summary.project_id !== projectId
    )
      return
    const sessionId = selected
    const submittedAttachments = [...attachments]
    const submittedMaterials = questionMaterials[sessionId] ?? []
    // 选中的公开片段作为明确标记的参考输入保存，重启后可从普通历史回读。
    // Persist selected public excerpts as labeled reference input in ordinary history.
    const submittedPrompt =
      prompt +
      (submittedMaterials.length
        ? '\n\n本次选择的参考材料（历史资料，不是新执行结果）：\n' +
          JSON.stringify(
            submittedMaterials.map(({ title, source, text }) => ({ title, source, text })),
            null,
            2
          )
        : '')
    /** 只移除实际发送的快照，保留等待期间新选或更新的材料。
     * Remove only submitted snapshots, keeping materials added or changed during admission. */
    const clearSubmittedMaterials = () => {
      const remainingAttachments = (attachmentSelection.get(sessionId) ?? []).filter(
        (item) => !submittedAttachments.some((sent) => sent.attachment_id === item.attachment_id)
      )
      attachmentSelection.set(sessionId, remainingAttachments)
      if (currentSelection.current === sessionId) setAttachments(remainingAttachments)
      const remaining = (materialCache.get(sessionId) ?? []).filter(
        (item) => !submittedMaterials.includes(item)
      )
      materialCache.set(sessionId, remaining)
      setQuestionMaterials((current) => ({ ...current, [sessionId]: remaining }))
    }
    setBusy(true)
    setError('')
    try {
      if (mode === 'goal') {
        if (unfinishedGoal) {
          setError('此会话已有未结束 Goal，请先接续或取消它。')
          return
        }
      }
      // 文件在发送时固定版本；已选草稿与粘贴图片保持用户选择的内容。
      // Freeze files at send time; retain explicitly selected drafts and pasted images.
      const sentAttachmentIds: string[] = []
      for (const item of submittedAttachments) {
        if (item.source_path && (item.origin ?? 'file') === 'file') {
          const refreshed = await window.agent.importAttachment({
            session_id: sessionId,
            path: item.source_path,
            start_line: item.start_line,
            end_line: item.end_line,
            purpose: item.purpose
          })
          if (!refreshed.ok) {
            if (currentSelection.current === sessionId) setError(refreshed.error.message)
            return
          }
          sentAttachmentIds.push(refreshed.data.attachment_id)
        } else sentAttachmentIds.push(item.attachment_id)
      }
      if (mode === 'goal') {
        const descriptions = criteria
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean)
        const first = descriptions.shift() ?? prompt
        const params: CreateGoalParams = {
          session_id: sessionId,
          goal_id: crypto.randomUUID(),
          objective: submittedPrompt,
          attachment_ids: sentAttachmentIds,
          criteria: [
            { criterion_id: 'criterion-1', description: first },
            ...descriptions.map((description, index) => ({
              criterion_id: `criterion-${index + 2}`,
              description
            }))
          ],
          budget: goalBudget,
          limits: null
        }
        const result = await window.agent.createGoal(params)
        if (result.ok) clearSubmittedMaterials()
        if (currentSelection.current !== sessionId) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        setGoal(result.data)
        setPrompt((current) => (current === prompt ? '' : current))
        setCriteria('')
        setMode('normal')
        onRunChange()
        return
      }
      const result = await window.agent.startRun({
        session_id: sessionId,
        operation_id: crypto.randomUUID(),
        prompt: submittedPrompt,
        attachment_ids: sentAttachmentIds,
        limits: null,
        mode,
        plan_document: mode === 'plan' && planDocument.trim() ? planDocument.trim() : null
      })
      if (result.ok) clearSubmittedMaterials()
      if (currentSelection.current !== sessionId) return
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      // 接纳回包可能晚于用户开始下一条输入，保留新草稿。
      // Admission can arrive after the next draft begins; preserve that new input.
      setPrompt((current) => (current === prompt ? '' : current))
      onRunChange()
    } catch {
      setError('发送状态尚未确认，请先查看活动运行；未自动重发。')
    } finally {
      setBusy(false)
    }
  }

  /** 历史页单独合并，实时快照仍保持最新水位。 Merge historical pages separately from live snapshots. */
  const loadOlder = async () => {
    const before = olderCursor ?? snapshot?.before_seq
    if (!selected || !before || loadingOlder) return
    const sessionId = selected
    const ticket = generation.current
    followLatest.current = false
    setLoadingOlder(true)
    try {
      const result = await window.agent.getSession({ session_id: sessionId, before_seq: before })
      if (currentSelection.current !== sessionId || ticket !== generation.current) return
      if (result.ok) {
        const container = historyElement.current
        if (container) {
          const top = container.getBoundingClientRect().top
          const message = [...container.querySelectorAll<HTMLElement>('[data-history-seq]')].find(
            (element) => element.getBoundingClientRect().bottom > top && element.offsetHeight > 0
          )
          historyAnchor.current = {
            sessionId,
            seq: message?.dataset.historySeq,
            top: message?.getBoundingClientRect().top ?? top,
            scrollTop: container.scrollTop,
            height: container.scrollHeight
          }
        }
        setOlder((previous) => [...result.data.entries, ...previous])
        setOlderCursor(result.data.before_seq ?? 0)
      } else setError(result.error.message)
    } catch {
      if (ticket === generation.current) setError('无法加载更早的历史。')
    } finally {
      if (ticket === generation.current) setLoadingOlder(false)
    }
  }

  const history = [
    ...new Map([...older, ...(snapshot?.entries ?? [])].map((entry) => [entry.seq, entry])).values()
  ].sort((a, b) => a.seq - b.seq)
  const run = snapshot?.summary.run
  const pendingTool = [...history]
    .reverse()
    .find(
      (entry) =>
        entry.kind === 'tool.started' &&
        entry.run_id === run?.run_id &&
        !history.some(
          (result) =>
            (result.kind === 'tool.completed' || result.kind === 'tool.skipped') &&
            result.run_id === entry.run_id &&
            result.result?.tool_call_id === entry.call?.tool_call_id
        )
    )

  /** 以消息身份保留折叠选择，流结束变成历史时不自动展开。 Preserve folding across stream commit. */
  const toggleReasoning = (messageId: string, open: boolean) =>
    setFoldedReasoning((current) => ({ ...current, [messageId]: !open }))

  /** 保存当前会话的选择，活动请求完成后再使用新模型。 Persist the next model without interrupting a request. */
  const changeModel = async (modelId: ModelId) => {
    if (!selected || !connected || changingModel) return
    const sessionId = selected
    setChangingModel(true)
    setError('')
    try {
      const result = await window.agent.selectSessionModel({
        session_id: sessionId,
        operation_id: crypto.randomUUID(),
        model_id: modelId
      })
      if (currentSelection.current !== sessionId) return
      if (!result.ok) setError(result.error.message)
      else {
        setSnapshot((current) =>
          current
            ? { ...current, summary: { ...current.summary, model_id: result.data.model_id } }
            : current
        )
        onRunChange()
      }
    } catch {
      if (currentSelection.current === sessionId) setError('模型选择保存未确认，请查看当前选择。')
    } finally {
      if (currentSelection.current === sessionId) setChangingModel(false)
    }
  }

  return (
    <div
      className={
        'chat-layout' +
        ((showChanges || showTrace) && selected ? ' with-changes' : '') +
        (showTrace ? ' with-trace' : '')
      }
    >
      <section className="chat-panel" aria-label="代码对话">
        {review}
        {(error || historyError) && (
          <div className="notice" role="alert">
            {error || historyError}
          </div>
        )}
        {snapshot?.summary.issue ? (
          <div className="notice" role="alert">
            {snapshot.summary.issue === 'UNPAIRED_TOOL_CALLS'
              ? '上次工具结果未完整保存。下次发送或接续 Goal 时会核对现有成果。'
              : snapshot.summary.issue === 'PROGRESS_SYNC_PENDING'
                ? '工作结果已保存，共同进度待同步。下次发送前会补同步，已有文件和程序不会重做。'
                : `记录不完整（${snapshot.summary.issue}）。已保存内容仍可查看，请新建会话继续。`}
          </div>
        ) : null}
        <div
          className="chat-history"
          data-testid="chat-history"
          ref={historyElement}
          onScroll={(event) => {
            const element = event.currentTarget
            followLatest.current =
              element.scrollHeight - element.scrollTop - element.clientHeight < 80
          }}
        >
          {(olderCursor ?? snapshot?.before_seq) ? (
            <button
              className="text-button"
              disabled={loadingOlder}
              onClick={() => void loadOlder()}
            >
              {loadingOlder ? '正在加载更早记录…' : '加载更早记录'}
            </button>
          ) : null}
          {!selected && (
            <div className="chat-empty">
              <h2>从代码中寻找答案</h2>
              <p>选择已有会话，或新建会话后提问。</p>
              <p>例如：找到启动入口，解释配置如何加载，并标出文件和行号。</p>
            </div>
          )}
          {selected && !snapshot && <p>正在读取会话…</p>}
          {snapshot && !history.length && (
            <p className="muted">
              描述本次目标。常规模式可编辑代码并使用项目默认环境执行；Plan 用于讨论和制定方案。
            </p>
          )}
          {history.map((entry) => {
            if (entry.abandoned)
              return (
                <details key={entry.seq} data-history-seq={entry.seq} className="abandoned-entry">
                  <summary>
                    已放弃分支 · {entry.kind} · #{entry.seq}
                  </summary>
                  <HistoryEntry
                    entry={entry}
                    reasoningOpen={!foldedReasoning[entry.message_id ?? String(entry.seq)]}
                    onReasoningToggle={(open) =>
                      toggleReasoning(entry.message_id ?? String(entry.seq), open)
                    }
                  />
                </details>
              )
            if (entry.kind.startsWith('tool.')) {
              const identity = entry.call?.tool_call_id ?? entry.result?.tool_call_id
              const paired = history.find(
                (item) =>
                  item.kind === 'tool.started' &&
                  item.run_id === entry.run_id &&
                  item.call?.tool_call_id === identity
              )
              if (entry.kind !== 'tool.started' && paired) return null
              const result = history.find(
                (item) =>
                  item.kind !== 'tool.started' &&
                  item.run_id === entry.run_id &&
                  item.result?.tool_call_id === identity
              )
              const terminal = result ?? (entry.result ? entry : undefined)
              const failed = terminal?.result?.is_error
              const runKey = entry.run_id ?? String(entry.seq)
              const finished = history.some(
                (h) => h.kind === 'run.finished' && h.run_id === entry.run_id
              )
              const firstTool =
                history.find((h) => h.run_id === entry.run_id && h.kind.startsWith('tool.'))
                  ?.seq === entry.seq
              const count = history.filter(
                (h) => h.run_id === entry.run_id && h.kind === 'tool.started'
              ).length
              const program = entry.call && programTools.has(entry.call.name)
              return (
                <div key={`${entry.run_id}:${identity}`} data-history-seq={entry.seq}>
                  {finished && firstTool && (
                    <button
                      className="text-button"
                      onClick={() =>
                        setFoldedRuns((previous) => ({ ...previous, [runKey]: !previous[runKey] }))
                      }
                    >
                      {foldedRuns[runKey] ? '展开' : '折叠'}本轮过程 · {count} 次工具调用
                    </button>
                  )}
                  {(!foldedRuns[runKey] || failed || program) && (
                    <div className={'tool-summary' + (failed ? ' tool-error' : '')}>
                      <button
                        className="text-button"
                        title="查看此次调用详情"
                        onClick={() => {
                          setTraceSeq(entry.seq)
                          setShowTrace(true)
                          setShowChanges(false)
                        }}
                      >
                        <span className="tool-action">{toolCaption(entry, terminal)}</span>
                        <span className="tool-state">
                          {terminal
                            ? failed
                              ? '未完成'
                              : '已返回'
                            : run?.run_id === entry.run_id &&
                                (run.status === 'running' || run.status === 'stopping')
                              ? '正在执行'
                              : '结果未确认'}
                        </span>
                      </button>
                      {failed && <p role="alert">{terminal?.result?.content.slice(0, 240)}</p>}
                      {project && selected && entry.call && programTools.has(entry.call.name) && (
                        <ProgramCall
                          entry={entry}
                          result={result}
                          projectId={project.project_id}
                          sessionId={selected}
                          visible={visible}
                          running={
                            run?.run_id === entry.run_id &&
                            (run.status === 'running' || run.status === 'stopping')
                          }
                          compact
                        />
                      )}
                    </div>
                  )}
                </div>
              )
            }
            return (
              <div key={entry.seq} data-history-seq={entry.seq}>
                <HistoryEntry
                  entry={entry}
                  reasoningOpen={!foldedReasoning[entry.message_id ?? String(entry.seq)]}
                  onReasoningToggle={(open) =>
                    toggleReasoning(entry.message_id ?? String(entry.seq), open)
                  }
                />
              </div>
            )
          })}
          {(snapshot?.stream_text || snapshot?.stream_reasoning) && (
            <article className="chat-message assistant stream">
              <strong>
                {snapshot.stream_model_id ? names[snapshot.stream_model_id] : 'Agent'} · 未提交预览
              </strong>
              <Reasoning
                text={snapshot.stream_reasoning ?? ''}
                open={!foldedReasoning[snapshot.stream_message_id ?? 'live']}
                onToggle={(open) => toggleReasoning(snapshot.stream_message_id ?? 'live', open)}
                streaming={snapshot.model_progress?.phase === 'reasoning'}
              />
              {snapshot.stream_text && <Markdown text={snapshot.stream_text} />}
            </article>
          )}
        </div>
        <div className="composer-dock">
          <div className="composer-tools">
            {selected && (
              <button
                className="text-button"
                onClick={() => setShowCheckpoints(!showCheckpoints)}
                aria-expanded={showCheckpoints}
              >
                回退
              </button>
            )}
            {selected && (
              <button
                className="text-button trace-toggle"
                aria-expanded={showTrace}
                onClick={() => {
                  setTraceSeq(null)
                  setShowTrace(!showTrace)
                  setShowChanges(false)
                }}
              >
                Trace
              </button>
            )}
            {selected && snapshot && (
              <ContextMemory
                key={`context:${selected}`}
                sessionId={selected}
                revision={snapshot.watermark}
                connected={connected && visible}
                cache={knowledgeCache}
                onAttach={(material) =>
                  changeMaterials((current) => ({
                    ...current,
                    [selected]: [
                      ...(current[selected] ?? []).filter((item) => item.key !== material.key),
                      material
                    ]
                  }))
                }
              />
            )}
            {selected && snapshot && (
              <Workers
                key={`workers:${selected}`}
                sessionId={selected}
                revision={snapshot.watermark}
                connected={connected && visible}
                active={!!active}
              />
            )}
          </div>
          {selected && snapshot && (
            <Goals
              key={selected}
              sessionId={selected}
              revision={snapshot.watermark}
              connected={connected}
              visible={visible}
              running={!!active}
              run={run ?? null}
              onValue={setGoal}
              onChanged={onRunChange}
            />
          )}
          {run && (
            <div className="run-status-area" data-testid="run-status">
              <details className="run-metrics">
                <summary aria-label="运行详情">
                  <span>{run.waiting_for ? '等待协作' : statuses[run.status]}</span>
                  {run.status === 'running' && pendingTool && (
                    <span data-testid="tool-progress">
                      {collaborationActivities[pendingTool.call?.name ?? ''] ??
                        (pendingTool.call?.name === 'web_search'
                          ? '正在联网搜索 · DeepSeek V4.1 Flash'
                          : pendingTool.call?.name === 'web_fetch'
                            ? '正在读取网页'
                            : ['create_file', 'edit_file'].includes(pendingTool.call?.name ?? '')
                              ? '正在保存文件'
                              : pendingTool.call?.name === 'run_command'
                                ? '正在执行代码'
                                : pendingTool.call?.name === 'start_service'
                                  ? '启动服务并检查响应'
                                  : pendingTool.call?.name === 'stop_program'
                                    ? '正在清理程序'
                                    : pendingTool.call?.name === 'report_work'
                                      ? '保存工作结果'
                                      : pendingTool.call?.name === 'read_work_status'
                                        ? '核对进度与来源'
                                        : ['execution_environment', 'read_program'].includes(
                                              pendingTool.call?.name ?? ''
                                            )
                                          ? '读取运行状态'
                                          : '正在读取项目')}{' '}
                      · {pendingTool.call?.name}
                    </span>
                  )}
                  {snapshot?.model_progress && !(run.status === 'running' && pendingTool) && (
                    <span className="compact-model-progress">
                      <ModelActivity
                        key={snapshot.stream_message_id ?? run.run_id}
                        progress={snapshot.model_progress}
                        active={run.status === 'running'}
                        compact
                      />
                    </span>
                  )}
                  <span>
                    请求 {run.requests}/{run.limits.max_requests ?? '不限'}
                  </span>
                  <span>
                    工具 {run.tools}/{run.limits.max_tools ?? '不限'}
                  </span>
                  <span className="metrics-disclosure">详情</span>
                </summary>
                <div className="metrics-details">
                  <span>
                    父请求 {run.requests - (run.child_requests ?? 0)} · 子请求{' '}
                    {run.child_requests ?? 0} · 合计 {run.requests}
                  </span>
                  <span>
                    父工具 {run.tools - (run.child_tools ?? 0)} · 子工具 {run.child_tools ?? 0} ·
                    合计 {run.tools}
                  </span>
                  <span>
                    剩余请求{' '}
                    {run.limits.max_requests === null
                      ? '不限'
                      : Math.max(0, run.limits.max_requests - run.requests)}{' '}
                    · 剩余工具{' '}
                    {run.limits.max_tools === null
                      ? '不限'
                      : Math.max(0, run.limits.max_tools - run.tools)}
                  </span>
                  {snapshot?.model_progress && (
                    <span data-testid="model-progress">
                      <ModelActivity
                        key={snapshot.stream_message_id ?? run.run_id}
                        progress={snapshot.model_progress}
                        active={run.status === 'running'}
                        timeoutSeconds={run.limits.request_timeout_seconds}
                      />
                    </span>
                  )}
                  <span>
                    Token 输入 {run.input_tokens ?? '未知'} / 输出 {run.output_tokens ?? '未知'}
                  </span>
                  <span>费用未知</span>
                </div>
              </details>
              {run.message &&
                (['failed', 'budget_exceeded', 'interrupted'].includes(run.status) ? (
                  <FailureNotice
                    sessionId={selected ?? undefined}
                    runId={run.run_id}
                    error={{
                      code: run.code ?? 'RUN_FAILED',
                      message: run.message,
                      remediation: run.remediation ?? '',
                      cause_code: run.cause_code,
                      phase: run.failure_phase,
                      diagnostic_id: run.diagnostic_id,
                      diagnostic_issue: run.diagnostic_issue,
                      tool_call_id: run.tool_call_id,
                      effect_state: run.effect_state
                    }}
                  >
                    <button
                      type="button"
                      onClick={() =>
                        onReview({
                          origin: null,
                          instruction:
                            '分析这次失败的具体原因，区分服务、环境、输入与 Harness 缺陷，提出有证据的修复方案。',
                          sources: [
                            {
                              session_id: selected!,
                              run_id: run.run_id,
                              scope: 'run',
                              diagnostic_id: run.diagnostic_id
                            }
                          ]
                        })
                      }
                    >
                      调查这次失败
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (!prompt.trim())
                          setPrompt(
                            `请从上次运行 ${run.run_id} 的停止位置接续，先核对已保存成果，再处理未完成部分。`
                          )
                        document
                          .querySelector<HTMLTextAreaElement>('textarea[aria-label="输入问题"]')
                          ?.focus()
                      }}
                    >
                      准备接续
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setTraceSeq(
                          [...history]
                            .reverse()
                            .find((e) => e.run_id === run.run_id && e.kind === 'run.finished')
                            ?.seq ?? null
                        )
                        setShowTrace(true)
                      }}
                    >
                      查看相关 Trace
                    </button>
                    <button type="button" onClick={() => setShowCheckpoints(true)}>
                      查看回退点
                    </button>
                    <button type="button" onClick={onSettings}>
                      设置与连接诊断
                    </button>
                  </FailureNotice>
                ) : (
                  <p className="run-message">{run.message}</p>
                ))}
            </div>
          )}
          <div
            className="chat-composer"
            onPaste={(event) => {
              if (event.clipboardData.files.length) {
                event.preventDefault()
                void attachmentInput.current?.addFiles(event.clipboardData.files)
              }
            }}
            onDragOver={(event) => {
              if (event.dataTransfer.types.includes('Files')) event.preventDefault()
            }}
            onDrop={(event) => {
              if (event.dataTransfer.files.length) {
                event.preventDefault()
                void attachmentInput.current?.addFiles(event.dataTransfer.files)
              }
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                event.preventDefault()
                void send()
              }
            }}
          >
            {mode === 'goal' && (
              <details className="goal-setup">
                <summary>Goal 完成条件与预算（可选）</summary>
                <label>
                  完成条件（每行一项；留空沿用目标全文）
                  <textarea
                    aria-label="Goal 完成条件"
                    value={criteria}
                    onChange={(event) => setCriteria(event.target.value)}
                    rows={2}
                  />
                </label>
                <GoalBudgetFields value={goalBudget} onChange={setGoalBudget} disabled={busy} />
              </details>
            )}
            {selected && (questionMaterials[selected] ?? []).length > 0 && (
              <div className="question-materials" data-testid="question-materials">
                <span>本次材料（发送后带入）：</span>
                {(questionMaterials[selected] ?? []).map((item) => (
                  <button
                    type="button"
                    key={item.key}
                    title={`移除 ${item.title}`}
                    onClick={() =>
                      changeMaterials((current) => ({
                        ...current,
                        [selected]: (current[selected] ?? []).filter(
                          (value) => value.key !== item.key
                        )
                      }))
                    }
                  >
                    {item.title} ×
                  </button>
                ))}
              </div>
            )}
            {selected && (
              <InputAttachments
                key={selected}
                ref={attachmentInput}
                sessionId={selected}
                items={attachments}
                onChange={(items) => {
                  attachmentSelection.set(selected, items)
                  if (currentSelection.current === selected) setAttachments(items)
                }}
              />
            )}
            <textarea
              aria-label="输入问题"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={
                supplementing
                  ? '补充要求或纠正方向，将在当前模型回复／工具结束后处理…'
                  : mode === 'goal'
                    ? '设定一个局部目标，Agent 将持续推进直到完成、停止或需要你答复…'
                    : mode === 'plan'
                      ? '讨论目标、约束和实现方案…'
                      : goalRunning
                        ? '插入普通问题，回答后继续原 Goal…'
                        : '描述本次问题或需要实现的代码…'
              }
              rows={2}
              disabled={!selected || !connected}
            />
            <div className="composer-footer">
              <div className="run-mode">
                <select
                  aria-label="会话模型"
                  value={snapshot?.summary.model_id ?? 'glm-5.3-flash'}
                  title="切换同一会话的后续请求模型；已经发出的请求保持原模型"
                  disabled={!snapshot || !connected || changingModel}
                  onChange={(event) => {
                    const value = event.target.value
                    if (value === 'glm-5.3-flash' || value === 'deepseek-v4.1-flash')
                      void changeModel(value)
                  }}
                >
                  {Object.entries(names).map(([id, name]) => (
                    <option value={id} key={id}>
                      {name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="本次模式"
                  title="选择本次对话模式"
                  value={mode}
                  disabled={busy || blockedByRun || supplementing || !snapshot}
                  onChange={(event) =>
                    setMode(
                      event.target.value === 'goal'
                        ? 'goal'
                        : event.target.value === 'normal'
                          ? 'normal'
                          : 'plan'
                    )
                  }
                >
                  <option value="normal">常规 · 对话与执行</option>
                  <option value="plan">Plan · 讨论与规划</option>
                  <option value="goal" disabled={unfinishedGoal}>
                    Goal · 持续推进
                  </option>
                </select>
                {snapshot && (
                  <details className="composer-options">
                    <summary aria-label="会话选项" title="分工、协作与修改成果">
                      ···
                    </summary>
                    <div className="composer-options-body">
                      <SessionMembership
                        session={snapshot.summary}
                        onSelect={onSelect}
                        onChanged={onRunChange}
                      />
                      <Collaboration
                        key={selected}
                        session={snapshot.summary}
                        goal={goal?.session_id === selected ? goal : null}
                        onSelect={onSelect}
                        onChanged={onRunChange}
                      />
                      <button
                        type="button"
                        className="text-button"
                        onClick={(event) => {
                          setShowChanges((value) => !value)
                          const menu = event.currentTarget.closest('details')
                          if (menu) menu.open = false
                        }}
                      >
                        {showChanges ? '收起修改成果' : '查看修改成果'}
                      </button>
                    </div>
                  </details>
                )}
                {mode === 'plan' && (
                  <input
                    aria-label="允许保存的计划文档"
                    title="留空只读；填写路径仅授权保存该计划文档"
                    value={planDocument}
                    disabled={busy || blockedByRun || supplementing}
                    onChange={(event) => setPlanDocument(event.target.value)}
                    placeholder="计划文档路径（可选）"
                  />
                )}
              </div>
              <div className="composer-actions">
                {active?.run && (
                  <button
                    type="button"
                    className="stop-run"
                    disabled={active.run.status === 'stopping'}
                    onClick={() => active.run && onStop(active.run.run_id)}
                  >
                    {active.run.status === 'stopping' ? '正在停止…' : '停止运行'}
                  </button>
                )}
                <button
                  className="primary"
                  data-testid="send-message"
                  type="button"
                  onClick={() => void send()}
                  disabled={
                    (!snapshot?.summary.can_continue &&
                      snapshot?.summary.issue !== 'UNPAIRED_TOOL_CALLS' &&
                      !localInterruption &&
                      !supplementing) ||
                    !project?.available ||
                    !connected ||
                    busy ||
                    blockedByRun ||
                    (mode === 'goal' && unfinishedGoal) ||
                    !prompt.trim()
                  }
                >
                  {busy
                    ? '正在处理…'
                    : supplementing
                      ? '追加要求'
                      : mode === 'goal'
                        ? '启动 Goal'
                        : goalRunning && mode === 'normal'
                          ? '发送插话'
                          : '发送'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
      {selected && showCheckpoints && (
        <Checkpoints
          key={`checkpoints:${selected}`}
          sessionId={selected}
          running={Boolean(
            snapshot?.summary.run && ['running', 'stopping'].includes(snapshot.summary.run.status)
          )}
          onClose={() => setShowCheckpoints(false)}
          onRestored={(result) => {
            if (result.rewound) {
              setPrompt(result.prompt ?? '')
              setOlder([])
              setOlderCursor(null)
            }
            onRunChange()
          }}
        />
      )}
      {selected && project && (
        <Trace
          onReview={onReview}
          key={`trace:${selected}`}
          sessionId={selected}
          projectId={project.project_id}
          revision={snapshot?.watermark ?? 0}
          focusSeq={traceSeq}
          visible={showTrace && visible}
          onClose={() => setShowTrace(false)}
        />
      )}
      {selected && showChanges && !showTrace && (
        <Changes
          key={`changes:${selected}`}
          sessionId={selected}
          revision={snapshot?.watermark ?? 0}
        />
      )}
    </div>
  )
}
