/** 执行事实的按需视图，不参与运行控制。 On-demand facts, independent of execution control. */
import { useEffect, useRef, useState } from 'react'
import type {
  ChatEntry,
  TraceItem,
  TraceDetail,
  TraceDetailParams,
  TraceLink,
  TracePage
} from '../../generated/protocol'

/** 成果按需读取且可关闭，使用现有分页接口。 Read closable artifacts through existing paging APIs. */
function TraceArtifact({
  link,
  sessionId,
  projectId
}: {
  link: TraceLink
  sessionId: string
  projectId: string
}) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [image, setImage] = useState('')
  const [next, setNext] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  useEffect(
    () => () => {
      ++generation.current
    },
    []
  )
  /** 逐段读取差异或归档，图片只供用户查看。 Page diffs/archives; images are for human viewing. */
  async function load(offset = 0) {
    const ticket = ++generation.current
    setBusy(true)
    setError('')
    try {
      let body = ''
      let cursor: number | null = null
      if (link.kind === 'change') {
        const result = await window.agent.getChange({
          session_id: sessionId,
          change_id: link.identity,
          offset
        })
        if (!result.ok) throw new Error(result.error.message)
        body = result.data.diff
        cursor = result.data.next_offset
      } else if (link.kind === 'archive') {
        const result = await window.agent.readHistory({
          session_id: sessionId,
          artifact_id: link.identity,
          offset
        })
        if (!result.ok) throw new Error(result.error.message)
        body = result.data.items[0]?.text ?? ''
        cursor = result.data.items[0]?.next_offset ?? null
      } else {
        let position: number | null = 0
        const chunks: string[] = []
        let mime = ''
        while (position !== null) {
          const result = await window.agent.readMcpArtifact({
            project_id: projectId,
            session_id: sessionId,
            artifact_id: link.identity,
            offset: position
          })
          if (ticket !== generation.current) return
          if (!result.ok) throw new Error(result.error.message)
          chunks.push(result.data.data)
          mime = result.data.mime_type
          position = result.data.next_offset
        }
        if (ticket === generation.current) setImage(`data:${mime};base64,${chunks.join('')}`)
      }
      if (ticket === generation.current) {
        setText((previous) => (offset ? previous + body : body))
        setNext(cursor)
      }
    } catch (exc) {
      if (ticket === generation.current)
        setError(exc instanceof Error ? exc.message : '成果读取失败。')
    } finally {
      if (ticket === generation.current) setBusy(false)
    }
  }
  return (
    <details
      open={open}
      onToggle={(e) => {
        const expanded = e.currentTarget.open
        setOpen(expanded)
        if (expanded && !text && !image && !busy) void load()
      }}
    >
      <summary>
        {link.kind === 'change' ? '差异' : link.kind === 'archive' ? '归档正文' : '截图'} ·{' '}
        {link.title}
      </summary>
      {open && (
        <>
          {error && <p role="alert">{error}</p>}
          {text && <pre>{text}</pre>}
          {image && <img className="mcp-image" src={image} alt="保存的浏览器截图" />}
          {busy && <p>读取中…</p>}
          {next !== null && (
            <button disabled={busy} onClick={() => void load(next)}>
              继续读取
            </button>
          )}
          <button
            onClick={() => {
              ++generation.current
              setBusy(false)
              setOpen(false)
            }}
          >
            关闭成果
          </button>
        </>
      )}
    </details>
  )
}

/** 从真实参数提取简短目标。 Derive a short target from actual arguments. */
export function toolCaption(entry: ChatEntry, result?: ChatEntry): string {
  const args = entry.call?.arguments ?? {}
  const target = ['path', 'query', 'url', 'skill_id', 'server_id']
    .map((key) => args[key])
    .find((value) => typeof value === 'string')
  let name = entry.call?.name ?? '工具'
  try {
    const value: unknown = JSON.parse(result?.result?.content ?? '{}')
    if (value && typeof value === 'object' && 'mcp_source' in value) {
      const source = value.mcp_source
      if (source && typeof source === 'object' && 'server_id' in source && 'tool_name' in source)
        name = `${source.server_id}/${source.tool_name}`
    }
  } catch {
    /* 普通工具可以返回文本。 Ordinary tools may return plain text. */
  }
  return name + (target ? ` · ${String(target).slice(0, 140)}` : '')
}

/** 保留展开状态并按需读取详情片段。 Preserve expansion and fetch detail chunks on demand. */
function TraceRow({
  item,
  sessionId,
  projectId,
  focus
}: {
  item: TraceItem
  sessionId: string
  projectId: string
  focus: boolean
}) {
  const [open, setOpen] = useState(focus)
  const [detail, setDetail] = useState<TraceDetail | null>(null)
  const [error, setError] = useState('')
  const [part, setPart] = useState<TraceDetailParams['part']>(
    item.tool_call_id ? 'result' : 'detail'
  )
  const row = useRef<HTMLDetailsElement>(null)
  const generation = useRef(0)
  useEffect(() => {
    if (focus) {
      setOpen(true)
      row.current?.scrollIntoView({ block: 'nearest' })
    }
  }, [focus])
  useEffect(() => {
    const ticket = ++generation.current
    if (!open) return
    void window.agent
      .getTraceDetail({ session_id: sessionId, seq: item.seq, part })
      .then((result) => {
        if (ticket !== generation.current) return
        if (result.ok) {
          setDetail(result.data)
          setError('')
        } else setError(result.error.message)
      })
      .catch(() => {
        if (ticket === generation.current) setError('轨迹详情读取失败。')
      })
    return () => {
      ++generation.current
    }
  }, [open, sessionId, item.seq, item.updated_seq, part])
  /** 续读实际记录，不影响任务。 Page saved detail without affecting the run. */
  async function more() {
    if (!detail || detail.next_offset === null) return
    const ticket = generation.current
    try {
      const result = await window.agent.getTraceDetail({
        session_id: sessionId,
        seq: item.seq,
        offset: detail.next_offset,
        part
      })
      if (ticket !== generation.current) return
      if (result.ok) setDetail({ ...result.data, text: detail.text + result.data.text })
      else setError(result.error.message)
    } catch {
      if (ticket === generation.current) setError('读取后续详情失败。')
    }
  }
  return (
    <details
      ref={row}
      className={'trace-row' + (item.is_error ? ' tool-error' : '')}
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        {item.title} · {item.status}
        {item.duration_ms != null &&
          ` · ${item.kind === 'request.started' ? '请求跨度' : '调用跨度'} ${(item.duration_ms / 1000).toFixed(2)} 秒`}
      </summary>
      {open && (
        <>
          <small>
            {item.at} · 请求 {item.request_id ?? '无'} · #{item.seq}
          </small>
          {item.kind === 'request.started' && (
            <p className="muted">
              Token 输入 {item.usage?.input_tokens ?? '未知'} / 输出{' '}
              {item.usage?.output_tokens ?? '未知'} / 缓存命中输入{' '}
              {item.usage?.cached_input_tokens ?? '未提供'}（属于输入，不另加总）
            </p>
          )}
          {item.tool_call_id && (
            <div>
              {(['detail', 'parameters', 'result'] as const).map((value) => (
                <button key={value} disabled={part === value} onClick={() => setPart(value)}>
                  {value === 'detail' ? '全部详情' : value === 'parameters' ? '参数' : '结果'}
                </button>
              ))}
            </div>
          )}
          {item.kind === 'request.started' && (
            <p className="muted">
              请求详情含实际材料清单与有界预览，不是完整原始请求。材料全文可由已有归档回读。
              请求跨度为发出事实至响应提交或运行终态的墙钟时间，包含本地保存；工具调用单独计时。
            </p>
          )}
          {error && <p role="alert">{error}</p>}
          {detail ? (
            <>
              <button
                onClick={() =>
                  void navigator.clipboard
                    .writeText(detail.text)
                    .catch(() => setError('复制失败。'))
                }
              >
                复制已加载详情
              </button>
              {item.tool_call_id ? (
                <details key={`${item.seq}:${part}`} className="trace-raw-detail">
                  <summary>
                    {part === 'result'
                      ? '原始结果'
                      : part === 'parameters'
                        ? '原始参数'
                        : '完整记录'}
                  </summary>
                  <pre>{detail.text}</pre>
                </details>
              ) : (
                <pre>{detail.text}</pre>
              )}
              {detail.next_offset !== null && (
                <button onClick={() => void more()}>
                  读取更多（共 {detail.total_chars} 字符）
                </button>
              )}
              {detail.links?.map((link) => (
                <TraceArtifact
                  key={`${link.kind}:${link.identity}`}
                  link={link}
                  sessionId={sessionId}
                  projectId={projectId}
                />
              ))}
            </>
          ) : (
            <p>读取详情…</p>
          )}
        </>
      )}
    </details>
  )
}

/** 右侧轨迹分页与筛选；关闭只改变显示。 Trace paging and filtering; closing affects display only. */
export function Trace({
  sessionId,
  projectId,
  revision,
  focusSeq,
  focusRun,
  onClose
}: {
  sessionId: string
  projectId: string
  revision: number
  focusSeq: number | null
  focusRun?: string | null
  onClose: () => void
}) {
  const [items, setItems] = useState<TraceItem[]>([])
  const [cursor, setCursor] = useState<number | null>(null)
  const [tool, setTool] = useState('')
  const [errors, setErrors] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [jobs, setJobs] = useState<NonNullable<TracePage['jobs']>>([])
  const [jobCursor, setJobCursor] = useState<number | null | undefined>(undefined)
  const [refreshTick, setRefreshTick] = useState(0)
  const [jobIssues, setJobIssues] = useState<string[]>([])
  const generation = useRef(0)
  const latestItems = useRef(items)
  latestItems.current = items
  useEffect(() => {
    // 独立压缩 / 记忆作业不产生主 Run 事件，面板打开时刷新其真实状态。
    // Independent maintenance jobs need refreshes even without new Run facts.
    const timer = setInterval(() => setRefreshTick((tick) => tick + 1), 2000)
    return () => clearInterval(timer)
  }, [])
  useEffect(() => {
    setItems([])
    setCursor(null)
    setTool('')
    setErrors(false)
  }, [sessionId, focusSeq, focusRun])
  useEffect(() => {
    if (focusSeq === null) return
    let disposed = false
    void window.agent
      .listTrace({ session_id: sessionId, before_seq: focusSeq + 1, run_id: focusRun })
      .then((r) => {
        if (!disposed && r.ok) {
          setItems((previous) =>
            [...new Map([...previous, ...r.data.items].map((i) => [i.seq, i])).values()].sort(
              (a, b) => a.seq - b.seq
            )
          )
          setCursor(r.data.before_seq ?? 0)
        }
      })
      .catch(() => {
        if (!disposed) setError('目标轨迹读取失败。')
      })
    return () => {
      disposed = true
    }
  }, [sessionId, focusSeq, focusRun])
  useEffect(() => {
    const ticket = ++generation.current
    let disposed = false
    void window.agent
      .listTrace({
        session_id: sessionId,
        run_id: focusRun,
        tool,
        errors_only: errors,
        before_seq: null,
        watch_seqs: latestItems.current.filter((i) => i.status === 'running').map((i) => i.seq)
      })
      .then((result) => {
        if (disposed || ticket !== generation.current) return
        if (result.ok) {
          setItems((previous) =>
            [
              ...new Map(
                [...previous, ...result.data.items, ...(result.data.updates ?? [])].map((item) => [
                  item.seq,
                  item
                ])
              ).values()
            ]
              .filter(
                (item) =>
                  (!errors || item.is_error) &&
                  (!tool || item.tool_name?.toLowerCase().includes(tool.toLowerCase()))
              )
              .sort((a, b) => a.seq - b.seq)
          )
          setCursor((previous) =>
            previous === null
              ? result.data.before_seq
              : Math.min(previous, result.data.before_seq ?? 0)
          )
          setError('')
          setJobs((previous) => [
            ...new Map(
              [...previous, ...(result.data.jobs ?? [])].map((job) => [String(job.job_id), job])
            ).values()
          ])
          setJobCursor((previous) =>
            previous === undefined ? (result.data.next_job_offset ?? null) : previous
          )
          setJobIssues(result.data.job_issues ?? [])
        } else setError(result.error.message)
      })
      .catch(() => {
        if (!disposed) setError('轨迹读取失败。')
      })
    return () => {
      disposed = true
    }
  }, [sessionId, revision, focusSeq, focusRun, tool, errors, refreshTick])
  /** 保留当前页，向前加载历史。 Load older facts while retaining the current page. */
  async function older() {
    if (!cursor || busy) return
    const ticket = generation.current
    setBusy(true)
    try {
      const result = await window.agent.listTrace({
        session_id: sessionId,
        before_seq: cursor,
        run_id: focusRun,
        tool,
        errors_only: errors
      })
      if (ticket !== generation.current) return
      if (result.ok) {
        setItems((previous) =>
          [
            ...new Map([...result.data.items, ...previous].map((item) => [item.seq, item])).values()
          ].sort((a, b) => a.seq - b.seq)
        )
        setCursor(result.data.before_seq ?? 0)
      } else setError(result.error.message)
    } catch {
      if (ticket === generation.current) setError('历史轨迹读取失败。')
    } finally {
      setBusy(false)
    }
  }
  /** 独立维护作业不附会到最后一轮对话。 Page maintenance jobs independently of chat runs. */
  async function olderJobs() {
    if (jobCursor == null || busy) return
    setBusy(true)
    try {
      const r = await window.agent.listTrace({
        session_id: sessionId,
        job_offset: jobCursor,
        run_id: focusRun
      })
      if (r.ok) {
        setJobs((old) => [
          ...new Map(
            [...old, ...(r.data.jobs ?? [])].map((job) => [String(job.job_id), job])
          ).values()
        ])
        setJobCursor(r.data.next_job_offset ?? null)
      } else setError(r.error.message)
    } catch {
      setError('作业记录读取失败。')
    } finally {
      setBusy(false)
    }
  }
  return (
    <aside className="trace-panel" aria-label="执行轨迹">
      <header>
        <strong>Trace · 执行轨迹</strong>
        <button onClick={onClose}>关闭 Trace</button>
      </header>
      {focusRun && <p className="muted">当前运行：{focusRun}</p>}
      <div className="trace-filters">
        <input
          aria-label="筛选工具"
          placeholder="筛选工具名称"
          value={tool}
          onChange={(e) => {
            setItems([])
            setCursor(null)
            setTool(e.target.value)
          }}
        />
        <label>
          <input
            type="checkbox"
            checked={errors}
            onChange={(e) => {
              setItems([])
              setCursor(null)
              setErrors(e.target.checked)
            }}
          />
          仅失败
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="trace-scroll">
        <details>
          <summary>
            压缩与记忆作业 · {jobs.length}
            {jobCursor != null ? '+' : ''}
          </summary>
          {jobIssues.map((issue) => (
            <p key={issue} role="alert">
              {issue}
            </p>
          ))}
          {jobs.map((job) => (
            <details key={String(job.job_id)}>
              <summary>
                {job.kind === 'context' ? '压缩' : '记忆'} · {String(job.status ?? '历史状态未知')}{' '}
                · {String(job.job_id)}
              </summary>
              <pre>{JSON.stringify(job, null, 2)}</pre>
            </details>
          ))}
          {jobCursor != null && (
            <button disabled={busy} onClick={() => void olderJobs()}>
              更多作业
            </button>
          )}
        </details>
        {!!cursor && (
          <button disabled={busy} onClick={() => void older()}>
            更早轨迹
          </button>
        )}
        {!items.length && <p>暂无匹配记录。</p>}
        {items.map((item, index) => (
          <div key={item.seq}>
            {(index === 0 || items[index - 1].run_id !== item.run_id) && (
              <h4>运行 {item.run_id ?? '会话记录'}</h4>
            )}
            {item.goal_id && (index === 0 || items[index - 1].run_id !== item.run_id) && (
              <small>Goal {item.goal_id}</small>
            )}
            {(index === 0 || items[index - 1].request_id !== item.request_id) &&
              item.request_id && <small>请求 {item.request_id}</small>}
            <TraceRow
              item={item}
              sessionId={sessionId}
              projectId={projectId}
              focus={item.seq === focusSeq}
            />
          </div>
        ))}
      </div>
    </aside>
  )
}
