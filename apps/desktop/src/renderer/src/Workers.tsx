import { useEffect, useRef, useState } from 'react'
import type { WorkerPage, WorkerRecord, SessionView } from '../../generated/protocol'
import { useLatestRefresh } from './useLatestRefresh'
import { ReadingWorkspace } from './ReadingWorkspace'
import { FailureNotice } from './FailureNotice'
import { Markdown } from './Markdown'
import { Trace } from './Trace'

const workerLabels: Record<WorkerRecord['status'], string> = {
  queued: '排队中',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
  budget_exceeded: '预算已用完'
}

/** 紧凑入口进入独立列表与详情；复用原 worker 身份，不创建正式会话。
 * Open a list/detail surface for existing workers without creating formal sessions. */
export function Workers({
  sessionId,
  revision,
  connected,
  active
}: {
  sessionId: string
  revision: number
  connected: boolean
  active: boolean
}) {
  const [page, setPage] = useState<WorkerPage | null>(null)
  const [error, setError] = useState('')
  const [prompt, setPrompt] = useState('')
  const [detail, setDetail] = useState<SessionView | null>(null)
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [trace, setTrace] = useState(false)
  const [concurrency, setConcurrency] = useState<number | null>(null)
  const ticket = useRef(0)
  const detailPane = useRef<HTMLElement>(null)
  const scrolls = useRef(new Map<string, number>())
  const worker = page?.workers.find((item) => item.worker_id === selected) ?? page?.workers.at(-1)
  useEffect(
    () => () => {
      ++ticket.current
    },
    []
  )
  useEffect(
    () =>
      window.agent.onSessionEvent((event) => {
        if (event.session_id === sessionId && event.kind === 'changed') setRefresh((n) => n + 1)
      }),
    [sessionId]
  )
  useLatestRefresh(
    async (isCurrent) => {
      try {
        const result = await window.agent.listWorkers({ session_id: sessionId })
        if (!isCurrent()) return
        if (result.ok) {
          setPage(result.data)
          setError('')
        } else setError(result.error.message)
      } catch {
        if (isCurrent()) setError('无法读取子任务状态，请检查连接。')
      }
    },
    [sessionId, revision, refresh],
    connected
  )
  useEffect(() => {
    const node = detailPane.current
    if (node && worker) node.scrollTop = scrolls.current.get(worker.worker_id) ?? 0
  }, [worker?.worker_id])

  /** 只更新未来委派设置，已启动工作保留快照。 Save settings for later assignments. */
  async function configure(enabled: boolean) {
    setBusy(true)
    try {
      const result = await window.agent.configureWorkers({
        session_id: sessionId,
        settings: { enabled, concurrency: concurrency ?? page?.settings.concurrency ?? 2 }
      })
      if (result.ok) {
        setPage(result.data)
        setConcurrency(null)
        setError('')
      } else setError(result.error.message)
    } catch {
      setError('设置保存未确认，请刷新核对。')
    } finally {
      setBusy(false)
    }
  }
  /** 操作只发一次，失败保持原结果。 Dispatch once and preserve previous results on failure. */
  async function control(action: 'stop' | 'continue') {
    if (!worker) return
    const id = ++ticket.current
    setBusy(true)
    try {
      const result = await window.agent.controlWorker({
        session_id: sessionId,
        worker_id: worker.worker_id,
        action,
        prompt
      })
      if (id !== ticket.current) return
      if (result.ok) {
        setPage(result.data)
        setError('')
        setPrompt('')
      } else setError(result.error.message)
    } catch {
      if (id === ticket.current) setError('子任务操作结果未确认，请刷新核对；没有自动重试。')
    } finally {
      if (id === ticket.current) setBusy(false)
    }
  }
  /** 历史按需分页并核对身份，迟到结果不覆盖另一项。 Page history without crossing worker identities. */
  async function history(older = false) {
    if (!worker) return
    const id = ++ticket.current
    setBusy(true)
    try {
      const result = await window.agent.getSession({
        session_id: worker.session_id,
        before_seq: older ? (detail?.before_seq ?? null) : null
      })
      if (id !== ticket.current) return
      if (result.ok)
        setDetail((old) =>
          older && old
            ? { ...result.data, entries: [...result.data.entries, ...old.entries] }
            : result.data
        )
      else setError(result.error.message)
    } catch {
      if (id === ticket.current) setError('子任务记录读取失败。')
    } finally {
      if (id === ticket.current) setBusy(false)
    }
  }
  /** 切换保留各自阅读位置，不控制执行。 Switch views without controlling workers. */
  function select(id: string) {
    ++ticket.current
    setSelected(id)
    setDetail(null)
    setTrace(false)
    setBusy(false)
  }
  return (
    <div data-testid="workers">
      <button
        type="button"
        className="worker-entry"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        子 agent · {page?.settings.enabled ? '已开启' : '关闭'} ·{' '}
        {page?.workers.filter((w) => ['queued', 'running'].includes(w.status)).length ?? 0} 项进行中
        · 查看
      </button>
      <ReadingWorkspace open={open} title="子 Agent 工作空间" onClose={() => setOpen(false)}>
        <details className="worker-options">
          <summary>
            委派设置 · {page?.settings.enabled ? '已开启' : '关闭'} · 并发{' '}
            {page?.settings.concurrency ?? 2}
          </summary>
          <label>
            <input
              type="checkbox"
              aria-label="允许拆分子 agent"
              checked={page?.settings.enabled ?? false}
              disabled={busy || !connected || !page}
              onChange={(e) => void configure(e.target.checked)}
            />
            允许按需拆分子 agent
          </label>
          <label>
            同时执行数量
            <input
              type="number"
              aria-label="子任务并发数"
              min={1}
              value={concurrency ?? page?.settings.concurrency ?? 2}
              onChange={(e) => setConcurrency(Number(e.target.value))}
            />
          </label>
          <button
            disabled={busy || !connected || !page}
            onClick={() => void configure(page?.settings.enabled ?? false)}
          >
            保存并发数
          </button>
          <p className="muted">
            默认总预算不限；主动设置有限预算时父子共用该安排预算。停止主任务会停止其子工作，已保存输出保留。
          </p>
        </details>
        {error && <p role="alert">{error}</p>}
        <div className="reading-body">
          <nav className="reading-list" aria-label="子任务列表">
            {!page?.workers.length && (
              <p>暂无子任务。在委派设置中开启后，告诉 Agent 如何分工即可。</p>
            )}
            {page?.workers
              .slice()
              .reverse()
              .map((item) => (
                <button
                  key={item.worker_id}
                  aria-current={worker?.worker_id === item.worker_id}
                  onClick={() => select(item.worker_id)}
                >
                  {item.assignment.objective}
                  <small>
                    {workerLabels[item.status]} ·{' '}
                    {item.assignment.role === 'research' ? '调研' : '实现'}
                  </small>
                  <small>
                    累计请求 {item.requests ?? 0} · 工具 {item.tools ?? 0}
                  </small>
                </button>
              ))}
          </nav>
          <section
            ref={detailPane}
            className="reading-detail"
            onScroll={(e) => {
              if (worker) scrolls.current.set(worker.worker_id, e.currentTarget.scrollTop)
            }}
          >
            {worker ? (
              <>
                <h2>{worker.assignment.objective}</h2>
                <p className="worker-counts">
                  {workerLabels[worker.status]} · {worker.model_id} · 累计请求{' '}
                  {worker.requests ?? 0} · 工具 {worker.tools ?? 0} · 活跃{' '}
                  {(worker.active_seconds ?? 0).toFixed(1)} 秒
                </p>
                <dl className="worker-facts">
                  <dt>范围</dt>
                  <dd>{worker.assignment.scope || '未单独指定'}</dd>
                  <dt>上下文</dt>
                  <dd>
                    {worker.assignment.context_mode === 'inherit' ? '继承来源材料' : '独立上下文'}
                  </dd>
                  <dt>最近动作</dt>
                  <dd>
                    {worker.last_tool
                      ? `${worker.last_tool} · ${worker.last_tool_status ?? '状态未知'}`
                      : (worker.model_progress?.phase ?? '尚无工具事实')}{' '}
                    ·{' '}
                    {worker.last_event_at
                      ? new Date(worker.last_event_at).toLocaleTimeString()
                      : '时间未知'}
                  </dd>
                </dl>
                {worker.failure && (
                  <FailureNotice
                    error={{
                      ...worker.failure,
                      remediation: '已保存的输出和工具记录仍可读取；修正原因后在主会话明确接续。'
                    }}
                    sessionId={worker.session_id}
                    runId={worker.run_id ?? undefined}
                  />
                )}
                {worker.history_issue && <p role="alert">{worker.history_issue}</p>}
                <div className="worker-actions">
                  <input
                    aria-label="子任务补充"
                    placeholder="给这个子任务的补充要求"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                  />
                  <button
                    disabled={busy || !active || !connected || !prompt.trim()}
                    onClick={() => void control('continue')}
                  >
                    补充 / 继续
                  </button>
                  <button
                    disabled={busy || !connected || !['running', 'queued'].includes(worker.status)}
                    onClick={() => void control('stop')}
                  >
                    停止子任务
                  </button>
                </div>
                {!active && (
                  <p className="muted">
                    原安排已结束；要继续工作，请回到主输入区说明，可以引用下方 Worker ID。
                  </p>
                )}
                <h3>{worker.status === 'completed' ? '子任务结果' : '已保存的部分输出'}</h3>
                {worker.result ? (
                  <Markdown text={worker.result} />
                ) : (
                  <p>
                    {['running', 'queued'].includes(worker.status)
                      ? '尚未提交正文，可查看最近动作或 Trace。'
                      : '未保存回答正文；已执行工具记录仍可查。'}
                  </p>
                )}
                <div className="worker-actions">
                  <button disabled={busy || !connected} onClick={() => void history()}>
                    查看子任务记录
                  </button>
                  <button
                    onClick={() => {
                      setTrace(true)
                      if (!detail) void history()
                    }}
                  >
                    查看 Trace
                  </button>
                  <button
                    onClick={() =>
                      void navigator.clipboard
                        .writeText(worker.worker_id)
                        .catch(() => setError('无法复制 Worker ID。'))
                    }
                  >
                    复制 Worker ID
                  </button>
                </div>
                <details>
                  <summary>身份与来源</summary>
                  <dl className="worker-facts">
                    <dt>Worker</dt>
                    <dd>{worker.worker_id}</dd>
                    <dt>子会话</dt>
                    <dd>{worker.session_id}</dd>
                    <dt>原安排</dt>
                    <dd>{worker.owner_run_id}</dd>
                    <dt>原 Goal</dt>
                    <dd>{worker.goal_id ?? '无'}</dd>
                    <dt>中断位置</dt>
                    <dd>{worker.last_seq ?? '未知'}</dd>
                  </dl>
                </details>
                {detail && (
                  <details open>
                    <summary>子任务公开记录</summary>
                    {detail.before_seq && (
                      <button disabled={busy} onClick={() => void history(true)}>
                        更早记录
                      </button>
                    )}
                    {detail.entries.map((entry) => (
                      <div key={entry.seq}>
                        <small>
                          #{entry.seq} · {entry.kind}
                        </small>
                        {entry.text || entry.partial_text ? (
                          <Markdown text={entry.text || entry.partial_text || ''} />
                        ) : (
                          <p>
                            {entry.call?.name ?? (entry.result ? '工具结果（详情见 Trace）' : '')}
                          </p>
                        )}
                      </div>
                    ))}
                  </details>
                )}
                {trace && detail && (
                  <Trace
                    sessionId={worker.session_id}
                    projectId={detail.summary.project_id}
                    revision={detail.watermark}
                    focusSeq={null}
                    onClose={() => setTrace(false)}
                    initialExpanded
                    visible={open}
                  />
                )}
              </>
            ) : (
              <p>选择一个子任务查看目标、进度与成果。</p>
            )}
          </section>
        </div>
      </ReadingWorkspace>
    </div>
  )
}
