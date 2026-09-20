/** 真实进程卡片与有界日志；刷新不调用模型。 Real process cards and bounded logs without model polling. */
import { useEffect, useRef, useState } from 'react'
import type { ChatEntry, ProgramSummary, ProgramView } from '../../generated/protocol'

const states: Record<ProgramSummary['status'], string> = {
  starting: '正在启动',
  running: '正在执行',
  ready: 'HTTP 已响应',
  stopping: '正在停止',
  exited: '已退出',
  stopped: '已停止',
  failed: '执行失败',
  interrupted: '上次结果未确认'
}
const alive = new Set<ProgramSummary['status']>(['starting', 'running', 'ready', 'stopping'])
export const programTools = new Set([
  'run_command',
  'start_service',
  'read_program',
  'stop_program'
])

/** 每次调用占一个历史位置，执行中查找对应程序，结果到达后复用其身份。 One timeline card per call. */
export function ProgramCall({
  entry,
  result,
  projectId,
  sessionId,
  visible,
  running
}: {
  entry: ChatEntry
  result?: ChatEntry
  projectId: string
  sessionId: string
  visible: boolean
  running: boolean
}): React.JSX.Element {
  const call = entry.call
  const completed = result ?? (entry.result ? entry : undefined)
  const observed = completed?.program_result ?? null
  const [found, setFound] = useState<ProgramSummary | null>(null)
  const [lookupError, setLookupError] = useState('')
  useEffect(() => {
    if (!visible || !running || completed || found || !call) return
    let disposed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    /** 调用未结束时按来源定位，不把最近运行的其他程序拼到本卡片。 Match the exact pending call. */
    async function locate(): Promise<void> {
      try {
        const programId = call?.arguments.program_id
        if (typeof programId === 'string') {
          const response = await window.agent.getProgram({ program_id: programId })
          if (disposed) return
          if (response.ok) {
            setFound(response.data.summary)
            setLookupError('')
            return
          }
          setLookupError(response.error.message)
        } else {
          const response = await window.agent.listPrograms({
            project_id: projectId,
            session_id: sessionId,
            limit: 20
          })
          if (disposed) return
          if (response.ok) {
            const match = response.data.programs.find(
              (item) => item.run_id === entry.run_id && item.tool_call_id === call?.tool_call_id
            )
            setLookupError('')
            if (match) {
              setFound(match)
              return
            }
          } else setLookupError(response.error.message)
        }
      } catch {
        if (!disposed) setLookupError('暂时无法读取程序状态，调用仍由后端执行。')
      }
      if (!disposed) timer = setTimeout(() => void locate(), 1000)
    }
    void locate()
    return () => {
      disposed = true
      clearTimeout(timer)
    }
  }, [call, entry.run_id, completed, found, projectId, sessionId, visible, running])

  const summary = observed?.summary ?? found
  if (summary)
    return (
      <ProgramCard
        summary={summary}
        initialView={observed}
        visible={visible}
        toolName={call?.name}
        toolResult={completed?.result ?? null}
      />
    )
  return (
    <details className={'program-card' + (completed?.result?.is_error ? ' tool-error' : '')}>
      <summary>
        工具 · {call?.name} ·{' '}
        {completed
          ? completed.kind === 'tool.skipped'
            ? '已跳过'
            : completed.result?.is_error
              ? '工具未完成'
              : '已返回'
          : running
            ? '正在执行'
            : '未记录完整结果'}
      </summary>
      <pre className="program-command">{JSON.stringify(call?.arguments, null, 2)}</pre>
      {completed?.result && <pre className="program-output">{completed.result.content}</pre>}
      {lookupError && <p role="alert">{lookupError}</p>}
    </details>
  )
}

/** 合并同一输出流的分块，避免标签切开普通日志行。 Merge chunks without splitting log lines. */
function outputText(chunks: ProgramView['output']): string {
  let text = ''
  let previous: string | null = null
  for (const chunk of chunks) {
    if (chunk.stream !== previous) {
      if (text && !text.endsWith('\n')) text += '\n'
      text += `[${chunk.stream}] `
    }
    text += chunk.text
    previous = chunk.stream
  }
  return text
}

/** 按程序身份读取日志，挂载和轮询均不改变服务生命周期。 Read logs without affecting service lifetime. */
function ProgramCard({
  summary,
  visible,
  onRefresh,
  initialView = null,
  toolName,
  toolResult = null
}: {
  summary: ProgramSummary
  visible: boolean
  onRefresh?: () => void
  initialView?: ProgramView | null
  toolName?: string
  toolResult?: ChatEntry['result']
}): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<ProgramView | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [afterSeq, setAfterSeq] = useState(0)
  const epoch = useRef(0)
  const displayed = view ?? initialView
  const current = displayed?.summary ?? summary
  const command =
    current.command.kind === 'powershell'
      ? current.command.script
      : [current.command.program, ...(current.command.arguments ?? [])].join(' ')

  useEffect(() => {
    const generation = ++epoch.current
    let timer: ReturnType<typeof setTimeout> | undefined
    /** 只拉取当前卡片状态，长日志可继续按序号分页。 Fetch current card state with explicit log paging. */
    async function refresh(): Promise<void> {
      try {
        const result = await window.agent.getProgram({
          program_id: summary.program_id,
          after_seq: afterSeq
        })
        if (generation !== epoch.current) return
        if (result.ok) {
          setView(result.data)
          setError('')
        } else setError(result.error.message)
        if (result.ok && alive.has(result.data.summary.status))
          timer = setTimeout(() => void refresh(), 1000)
      } catch {
        if (generation === epoch.current) setError('无法读取程序状态。')
      }
    }
    // 结果到达时即使卡片收起也更新，不能让启动中的旧快照盖住终态。
    // Refresh collapsed cards on result arrival; a stale startup view must not mask completion.
    if (visible) void refresh()
    return () => {
      epoch.current++
      clearTimeout(timer)
    }
  }, [summary.program_id, summary.status, afterSeq, visible])

  /** 用户显式操作，失败显示且不自动重试。 Handle explicit controls without automatic retry. */
  async function control(action: 'stop' | 'open' | 'more'): Promise<void> {
    const generation = epoch.current
    setBusy(true)
    setError('')
    try {
      if (action === 'more' && view) {
        setAfterSeq(view.next_seq)
      } else if (action === 'stop') {
        const result = await window.agent.stopProgram(summary.program_id)
        if (generation !== epoch.current) return
        if (result.ok) {
          setView(result.data)
          onRefresh?.()
        } else setError(result.error.message)
      } else if (action === 'open') {
        const result = await window.agent.openProgram(summary.program_id)
        if (generation !== epoch.current) return
        if (!result.ok) setError(result.error.message)
      }
    } catch {
      if (generation === epoch.current) setError('程序操作未完成，请刷新查看实际状态。')
    } finally {
      // 折叠 / 隐藏期间状态读取可以过期，但用户操作已返回，按钮不能永久忙碌。
      // A view refresh may expire while hidden, but a finished control must release its busy state.
      setBusy(false)
    }
  }

  return (
    <details
      className="program-card"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="program-heading" title={command}>
        <strong>{toolName ?? (current.kind === 'service' ? '预览服务' : '命令')}</strong>
        <span className="program-caption">{command}</span>
        <span>{states[current.status]}</span>
        {current.exit_code !== null && <span>退出码 {current.exit_code}</span>}
      </summary>
      <p className="settings-hint">
        {current.environment_name} · 本机直接运行 · 未隔离 · {current.cwd}
      </p>
      <pre className="program-command">
        {current.command.kind === 'powershell'
          ? current.command.script
          : [current.command.program, ...(current.command.arguments ?? [])]
              .map((part) => JSON.stringify(part))
              .join(' ')}
      </pre>
      <p>
        来源会话：<code>{current.session_id}</code> · PID {current.pid ?? '尚未创建'}
      </p>
      {current.url && (
        <p>
          <code>{current.url}</code>
          {current.http_status !== null && ` · HTTP ${current.http_status}`}
        </p>
      )}
      {current.message && <p>{current.message}</p>}
      {toolResult?.is_error && <pre className="inline-error">{toolResult.content}</pre>}
      {current.retained && (
        <p className="settings-hint">回复结束或切换会话后继续运行；退出应用时停止。</p>
      )}
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <div className="settings-actions">
        {alive.has(current.status) && (
          <button
            disabled={busy || current.status === 'stopping'}
            onClick={() => void control('stop')}
          >
            停止程序
          </button>
        )}
        {current.status === 'ready' && current.url && (
          <button disabled={busy} onClick={() => void control('open')}>
            打开预览
          </button>
        )}
        {view && (
          <button disabled={busy} onClick={() => void control('more')}>
            读取后续输出
          </button>
        )}
      </div>
      {displayed?.truncated && (
        <p className="settings-hint">
          只保留有界输出；已丢弃约 {current.dropped_bytes} 字节，历史尾部可能不完整。
        </p>
      )}
      <pre className="program-output" aria-label="程序输出">
        {displayed ? outputText(displayed.output) || '当前没有输出。' : '展开后读取输出…'}
      </pre>
    </details>
  )
}

/** 项目或会话下的轻量入口；切走时只释放订阅，不停止程序。 List cards without stopping on navigation. */
export function ProgramCards({
  projectId,
  sessionId = null,
  visible = true
}: {
  projectId: string
  sessionId?: string | null
  visible?: boolean
}): React.JSX.Element | null {
  const [items, setItems] = useState<ProgramSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [active, setActive] = useState(0)
  const [unavailable, setUnavailable] = useState(0)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [pageCursor, setPageCursor] = useState<string | null>(null)
  const generation = useRef(0)
  useEffect(() => {
    const current = ++generation.current
    let timer: ReturnType<typeof setTimeout> | undefined
    /** 每次查询完成后安排下一次，避免慢后端请求堆叠。 Schedule polling after completion, without overlap. */
    async function refresh(): Promise<void> {
      try {
        const result = await window.agent.listPrograms({
          project_id: projectId,
          session_id: sessionId,
          cursor: pageCursor,
          limit: 20
        })
        if (current !== generation.current) return
        if (result.ok) {
          setItems(result.data.programs)
          setCursor(result.data.next_cursor)
          setActive(result.data.active_count)
          setUnavailable(result.data.unavailable_count)
          setError('')
        } else setError(result.error.message)
      } catch {
        if (current === generation.current) setError('程序列表读取失败。')
      }
      if (current === generation.current) timer = setTimeout(() => void refresh(), 1500)
    }
    if (visible) void refresh()
    return () => {
      generation.current++
      clearTimeout(timer)
    }
  }, [projectId, sessionId, revision, visible, pageCursor])

  /** 显式展开更早记录，保持来源范围。 Load earlier records within the current scope. */
  function more(): void {
    setPageCursor(cursor)
  }

  if (sessionId && !items.length && !error && !unavailable && active === 0) return null

  return (
    <details
      className="program-panel"
      aria-label="项目运行卡片"
      open={active > 0 || items.length > 0}
    >
      <summary>
        {sessionId ? '本会话程序' : '项目程序'} · 项目运行中 {active}
      </summary>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {!items.length && (
        <p className="settings-hint">
          还没有程序记录。项目默认使用本机工具，也可在设置中选择特定环境。
        </p>
      )}
      {unavailable > 0 && <p role="alert">{unavailable} 条程序记录不可读取，原文件已保留。</p>}
      {items.map((summary) => (
        <ProgramCard
          key={summary.program_id}
          summary={summary}
          visible={visible}
          onRefresh={() => setRevision((value) => value + 1)}
        />
      ))}
      {pageCursor && <button onClick={() => setPageCursor(null)}>回到最新程序</button>}
      {cursor && <button onClick={more}>更早程序</button>}
    </details>
  )
}
