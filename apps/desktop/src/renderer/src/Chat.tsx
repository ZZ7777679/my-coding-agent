/** 项目只读对话：快照、流式预览与可核对工具结果。 Read-only chat with snapshots and tool evidence. */
import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  ChatEntry,
  ModelId,
  ModelProgress,
  ProjectSummary,
  SessionSummary,
  SessionView,
  SessionSignal
} from '../../generated/protocol'

type Props = {
  project: ProjectSummary | null
  defaultModel: ModelId
  connected: boolean
  visible: boolean
  active: SessionSummary | null
  onRunChange: () => void
}

const names: Record<ModelId, string> = {
  'glm-5.3-flash': 'GLM-5.3-Flash',
  'deepseek-v4.1-flash': 'DeepSeek V4.1 Flash'
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
const phases: Record<ModelProgress['phase'], string> = {
  preparing: '准备请求',
  connecting: '建立连接',
  tls: '建立安全连接',
  waiting: '等待模型响应',
  receiving: '已收到响应，等待正文',
  reasoning: '模型正在思考',
  text: '正在输出正文',
  completed: '本次请求结束'
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
function HistoryEntry({ entry }: { entry: ChatEntry }) {
  if (entry.kind === 'tool.started')
    return (
      <details className="tool-entry">
        <summary>工具 · {entry.call?.name}</summary>
        <pre>{JSON.stringify(entry.call?.arguments, null, 2)}</pre>
      </details>
    )
  if (entry.kind === 'tool.completed')
    return (
      <details className={'tool-entry ' + (entry.result?.is_error ? 'tool-error' : '')}>
        <summary>{entry.result?.is_error ? '工具未完成' : '工具结果'}</summary>
        <pre>{toolText(entry.result?.content ?? '')}</pre>
      </details>
    )
  if (entry.kind === 'run.finished') return <p className="run-end">{entry.text}</p>
  if (entry.kind === 'assistant' && !entry.text) return null
  return (
    <article className={'chat-message ' + entry.kind}>
      <strong>{entry.kind === 'user' ? '你' : 'Agent'}</strong>
      <pre>{entry.text}</pre>
    </article>
  )
}

/** 管理会话归属、快照交接与有界事件缓冲。 Manage session ownership and bounded snapshot handoff. */
export function Chat({ project, defaultModel, connected, visible, active, onRunChange }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [model, setModel] = useState<ModelId>(defaultModel)
  const [snapshot, setSnapshot] = useState<SessionView | null>(null)
  const [older, setOlder] = useState<ChatEntry[]>([])
  const [olderCursor, setOlderCursor] = useState<number | null>(null)
  const [prompt, setPrompt] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  const historyElement = useRef<HTMLDivElement>(null)
  const followLatest = useRef(true)
  const projectId = project?.project_id
  const currentProject = useRef(projectId)
  currentProject.current = projectId
  const currentSelection = useRef(selected)
  currentSelection.current = selected
  useEffect(() => setModel(defaultModel), [defaultModel])

  /** 分页读取真实会话，不在刷新时发模型请求。 Page actual sessions without issuing model requests. */
  const loadList = useCallback(
    async (page: string | null = null) => {
      if (!projectId || !connected) return
      try {
        const result = await window.agent.listSessions({
          project_id: projectId,
          cursor: page,
          limit: 20
        })
        if (currentProject.current !== projectId) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        setSessions((previous) =>
          page ? [...previous, ...result.data.sessions] : result.data.sessions
        )
        setCursor(result.data.next_cursor)
        if (result.data.unavailable_count)
          setError(
            `${result.data.unavailable_count} 条记录无法读取或确认归属，原文件已保留；其他会话仍可使用。`
          )
      } catch {
        if (currentProject.current === projectId) setError('无法读取会话列表，请检查后端连接。')
      }
    },
    [projectId, connected]
  )

  useEffect(() => {
    ++generation.current
    setSelected(null)
    setSnapshot(null)
    setOlder([])
    setSessions([])
    setPrompt('')
    setError('')
    setModel(defaultModel)
    followLatest.current = true
    // 默认模型变化只影响新会话，不改变已选历史会话。
    // Default model changes never mutate an existing session.
  }, [projectId])

  useEffect(() => {
    if (followLatest.current && historyElement.current)
      historyElement.current.scrollTop = historyElement.current.scrollHeight
  }, [snapshot?.watermark, snapshot?.delta_index])

  useEffect(() => {
    if (visible) void loadList()
  }, [visible, loadList, active?.run?.run_id])

  useEffect(() => {
    if (!selected || !connected) return
    const ticket = ++generation.current
    let disposed = false
    let fetching = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let pending: SessionSignal[] = []
    let overflow = false
    let value: SessionView | null = null
    let attached = false
    setSnapshot(null)
    setOlder([])
    setOlderCursor(null)
    followLatest.current = true
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
      if (signal.kind !== 'text.delta')
        return signal.seq <= value.watermark && signal.kind !== 'resync'
      if (signal.seq < value.watermark) return true
      if (signal.seq !== value.watermark || signal.message_id !== value.stream_message_id)
        return false
      if (signal.delta_index <= value.delta_index) return true
      if (signal.delta_index !== value.delta_index + 1) return false
      value = {
        ...value,
        stream_text: value.stream_text + signal.text,
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
          setError(result.error.message)
          return
        }
        attached = true
        value = result.data
        let needsRefresh = overflow
        overflow = false
        for (const signal of pending) if (!applySignal(signal)) needsRefresh = true
        pending = []
        setSnapshot(value)
        if (needsRefresh) schedule()
      } catch {
        if (!disposed) setError('会话连接中断。已保存的历史可在重新打开后查看。')
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
    const recovery = setInterval(() => void refresh(), 2500)
    return () => {
      disposed = true
      if (timer) clearTimeout(timer)
      clearInterval(recovery)
      unsubscribe()
      void window.agent.detachSession(selected).catch(() => undefined)
    }
  }, [selected, connected])

  /** 创建指定模型的新会话，模型切换通过新会话完成。 Create a fresh session when choosing a model. */
  const create = async () => {
    if (!projectId || busy) return
    const target = projectId
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.createSession({ project_id: target, model_id: model })
      if (currentProject.current !== target) return
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setSessions((previous) => [result.data, ...previous])
      setSelected(result.data.session_id)
    } catch {
      setError('会话创建未确认，请刷新列表后检查。')
    } finally {
      setBusy(false)
    }
  }

  /** 只在发送动作生成操作 ID，失败不自动重发。 Generate operation IDs on explicit send only. */
  const send = async () => {
    if (!selected || busy || active || !prompt.trim() || snapshot?.summary.project_id !== projectId)
      return
    const sessionId = selected
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.startRun({
        session_id: sessionId,
        operation_id: crypto.randomUUID(),
        prompt,
        limits: null
      })
      if (currentSelection.current !== sessionId) return
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setPrompt('')
      onRunChange()
      void loadList()
    } catch {
      setError('发送状态尚未确认，请先查看活动运行；未自动重发。')
    } finally {
      setBusy(false)
    }
  }

  /** 历史页单独合并，实时快照仍保持最新水位。 Merge historical pages separately from live snapshots. */
  const loadOlder = async () => {
    const before = olderCursor ?? snapshot?.before_seq
    if (!selected || !before || busy) return
    const sessionId = selected
    followLatest.current = false
    setBusy(true)
    try {
      const result = await window.agent.getSession({ session_id: sessionId, before_seq: before })
      if (currentSelection.current !== sessionId) return
      if (result.ok) {
        setOlder((previous) => [...result.data.entries, ...previous])
        setOlderCursor(result.data.before_seq ?? 0)
      } else setError(result.error.message)
    } catch {
      setError('无法加载更早的历史。')
    } finally {
      setBusy(false)
    }
  }

  const history = [
    ...new Map([...older, ...(snapshot?.entries ?? [])].map((entry) => [entry.seq, entry])).values()
  ].sort((a, b) => a.seq - b.seq)
  const run = snapshot?.summary.run
  return (
    <div className="chat-layout">
      <aside className="session-sidebar">
        <h2>项目会话</h2>
        <p className="muted">{project?.name ?? '请先选择项目'}</p>
        <label>
          新会话模型
          <select
            aria-label="新会话模型"
            value={model}
            onChange={(event) =>
              setModel(
                event.target.value === 'deepseek-v4.1-flash'
                  ? 'deepseek-v4.1-flash'
                  : 'glm-5.3-flash'
              )
            }
          >
            <option value="glm-5.3-flash">GLM-5.3-Flash</option>
            <option value="deepseek-v4.1-flash">DeepSeek V4.1 Flash</option>
          </select>
        </label>
        <button
          className="primary"
          onClick={() => void create()}
          disabled={!connected || !project?.available || busy}
        >
          新建会话
        </button>
        {active && active.project_id === projectId && (
          <button className="text-button" onClick={() => setSelected(active.session_id)}>
            查看当前运行
          </button>
        )}
        <nav aria-label="会话列表">
          {sessions.map((session) => (
            <button
              key={session.session_id}
              className={'session-item ' + (selected === session.session_id ? 'selected' : '')}
              onClick={() => setSelected(session.session_id)}
            >
              <strong>{session.title}</strong>
              <small>{names[session.model_id]}</small>
            </button>
          ))}
        </nav>
        {!sessions.length && <p className="muted">还没有会话。新建后即可开始阅读代码。</p>}
        {cursor && <button onClick={() => void loadList(cursor)}>更多会话</button>}
        <button className="text-button" onClick={() => void loadList()}>
          刷新会话
        </button>
      </aside>
      <section className="chat-panel" aria-label="只读对话">
        <header className="chat-heading">
          <strong>{snapshot ? names[snapshot.summary.model_id] : '阅读和理解你的代码'}</strong>
          <span className="tag">只读 · 不执行项目命令</span>
        </header>
        {error && (
          <div className="notice" role="alert">
            {error}
          </div>
        )}
        {snapshot?.summary.issue && (
          <div className="notice" role="alert">
            记录不完整（{snapshot.summary.issue}）。已保存内容仍可查看，请新建会话继续。
          </div>
        )}
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
            <button className="text-button" disabled={busy} onClick={() => void loadOlder()}>
              加载更早记录
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
            <p className="muted">输入问题后，Agent 会按需要搜索和读取项目文件。</p>
          )}
          {history.map((entry) => (
            <HistoryEntry key={entry.seq} entry={entry} />
          ))}
          {snapshot?.stream_text && (
            <article className="chat-message assistant stream">
              <strong>Agent · 未提交预览</strong>
              <pre>{snapshot.stream_text}</pre>
            </article>
          )}
        </div>
        {run && (
          <div className="run-metrics" data-testid="run-status">
            <span>{statuses[run.status]}</span>
            {snapshot?.model_progress && (
              <span data-testid="model-progress">
                {run.status === 'running' || snapshot.model_progress.phase === 'completed'
                  ? phases[snapshot.model_progress.phase]
                  : `结束于：${phases[snapshot.model_progress.phase]}`}
                {snapshot.model_progress.first_text_ms != null &&
                  ` · 本次请求首字 ${(snapshot.model_progress.first_text_ms / 1000).toFixed(2)} 秒`}
              </span>
            )}
            <span>
              请求 {run.requests}/{run.limits.max_requests}
            </span>
            <span>
              工具 {run.tools}/{run.limits.max_tools}
            </span>
            <span>
              Token 输入 {run.input_tokens ?? '未知'} / 输出 {run.output_tokens ?? '未知'}
            </span>
            <span>费用未知</span>
            {run.message && (
              <p>
                {run.code} · {run.message}
              </p>
            )}
          </div>
        )}
        <form
          className="chat-composer"
          onSubmit={(event) => {
            event.preventDefault()
            void send()
          }}
        >
          <textarea
            aria-label="输入问题"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="描述你想理解的代码或问题…"
            rows={3}
            disabled={!selected || !connected}
          />
          <div>
            <small>工具结果提供实际文件、行号和版本；历史内容可能已变化。</small>
            <button
              className="primary"
              type="submit"
              disabled={
                !snapshot?.summary.can_continue ||
                !project?.available ||
                !connected ||
                busy ||
                !!active ||
                !prompt.trim()
              }
            >
              {busy ? '正在处理…' : '发送'}
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}
