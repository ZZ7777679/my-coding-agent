/** 展示用户约定、公开历史和真实请求状态。 Show agreements, public history and actual request state. */
import { useEffect, useRef, useState } from 'react'
import type {
  CollaborationPage,
  SessionSummary,
  SessionView,
  GoalView,
  PeerMessagePage
} from '../../generated/protocol'
import type { Result } from '../../shared/api'
import type { WorkspaceSelection } from './TaskNavigation'

const statusNames = {
  preparing: '正在准备简报',
  queued: '排队中',
  running: '正在处理',
  completed: '已返回结果',
  failed: '失败',
  cancelled: '已停止',
  held: '等待明确接续'
}

/** 仅在展开时读取元数据；请求必须明确发送，切换视图不重新发送。 Load on expansion; view changes never resend requests. */
export function Collaboration({
  session,
  goal,
  onSelect,
  onChanged
}: {
  session: SessionSummary
  goal: GoalView | null
  onSelect: (selection: WorkspaceSelection) => void
  onChanged: () => void
}) {
  const [open, setOpen] = useState(false)
  const [mailbox, setMailbox] = useState<PeerMessagePage | null>(null)
  const [message, setMessage] = useState('')
  const [page, setPage] = useState<CollaborationPage | null>(null)
  const [peers, setPeers] = useState<SessionSummary[]>([])
  const [target, setTarget] = useState('')
  const [scope, setScope] = useState('')
  const [mode, setMode] = useState<'plan' | 'normal'>('plan')
  const [objective, setObjective] = useState('')
  const [kind, setKind] = useState<'request' | 'handoff' | 'review'>('request')
  const [notes, setNotes] = useState('')
  const [contextMode, setContextMode] = useState<'isolated' | 'inherit'>('isolated')
  const [transfer, setTransfer] = useState(true)
  const [history, setHistory] = useState<SessionView | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [cursor, setCursor] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const mounted = useRef(true)
  const operation = useRef<{ identity: string; fingerprint: string } | null>(null)
  const selectedPeer = useRef(target)
  selectedPeer.current = target
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    if (!open) return
    let disposed = false
    let loading = false
    /** 串行轮询本地状态，不调用模型；卸载后忽略晚到响应。 Poll local state without models and ignore late responses. */
    const load = async () => {
      if (loading) return
      loading = true
      try {
        const result = await window.agent.listCollaboration({
          session_id: session.session_id,
          cursor,
          limit: 20
        })
        const inbox = await window.agent.listPeerMessages({ session_id: session.session_id })
        if (!disposed && inbox.ok) setMailbox(inbox.data)
        if (!disposed) {
          if (result.ok) setPage(result.data)
          else setError(result.error.message)
        }
      } catch {
        if (!disposed) setError('协作状态读取失败。')
      } finally {
        loading = false
      }
    }
    void load()
    const timer = setInterval(() => void load(), 1000)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [open, session.session_id, cursor, refresh])

  useEffect(() => {
    if (!open) return
    let disposed = false
    /** 候选仅为同一任务已有会话，不读取其他会话正文。 List existing task peers without reading their histories. */
    const load = async () => {
      try {
        const all: SessionSummary[] = []
        let next: string | null = null
        do {
          const result = await window.agent.listSessions({
            project_id: session.project_id,
            cursor: next,
            limit: 20
          })
          if (disposed) return
          if (!result.ok) {
            setError(result.error.message)
            return
          }
          all.push(
            ...result.data.sessions.filter(
              (item) => item.task_id === session.task_id && item.session_id !== session.session_id
            )
          )
          next = result.data.next_cursor
        } while (next)
        setPeers(all)
      } catch {
        if (!disposed) setError('协作会话列表读取失败。')
      }
    }
    void load()
    return () => {
      disposed = true
    }
  }, [open, session.project_id, session.task_id, session.session_id])

  /** 保留输入及不确定投递的操作身份，错误不会触发自动重试。 Preserve input and uncertain delivery identity without automatic retries. */
  const perform = async <T,>(action: () => Promise<Result<T>>, done?: (value: T) => void) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const result = await action()
      if (!mounted.current) return
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      done?.(result.data)
      setRefresh((value) => value + 1)
      onChanged()
    } catch {
      if (mounted.current) setError('操作结果未确认，请刷新后查看；相同请求不会重复发送。')
    } finally {
      if (mounted.current) setBusy(false)
    }
  }

  /** 选中目标时加载已有约定，不让状态刷新覆盖编辑中的文字。 Load a selected agreement without overwriting edits on polling. */
  const choose = (identity: string) => {
    setTarget(identity)
    setHistory(null)
    const link = page?.links.find(
      (item) => item.source_session_id === session.session_id && item.target_session_id === identity
    )
    setScope(link?.scope ?? '')
    setMode(link?.mode ?? 'plan')
  }

  /** 幂等发送一项明确工作；既有约定决定接收方的能力。 Idempotently send scoped work under the saved agreement. */
  const send = () => {
    const liveRun =
      session.run && ['running', 'stopping'].includes(session.run.status) ? session.run : null
    const transferGoal =
      liveRun?.goal_id ||
      (goal && !['completed', 'cancelled'].includes(goal.status) ? goal.goal_id : null)
    const transferRun = transferGoal ? null : (liveRun?.run_id ?? null)
    const fingerprint = JSON.stringify({
      target,
      objective,
      mode,
      kind,
      notes,
      contextMode,
      transfer,
      transferGoal,
      transferRun
    })
    if (operation.current?.fingerprint !== fingerprint)
      operation.current = { identity: crypto.randomUUID(), fingerprint }
    const operationId = operation.current.identity
    if (kind !== 'request') {
      void perform(
        () =>
          window.agent.arrangeSessionWork({
            operation_id: operationId,
            source_session_id: session.session_id,
            target_session_id: target,
            kind,
            objective,
            notes,
            context_mode: contextMode,
            transfer_goal_id: kind === 'handoff' && transfer ? transferGoal : null,
            transfer_run_id: kind === 'handoff' && transfer ? transferRun : null
          }),
        () => {
          setObjective('')
          setNotes('')
          setHistoryOpen(false)
          operation.current = null
          setCursor(null)
        }
      )
      return
    }
    void perform(
      () =>
        window.agent.requestCollaboration({
          operation_id: operationId,
          source_session_id: session.session_id,
          target_session_id: target,
          objective,
          inputs: '',
          expected_result: '',
          mode
        }),
      () => {
        setObjective('')
        setHistoryOpen(false)
        operation.current = null
        setCursor(null)
      }
    )
  }

  /** 历史读取不订阅对方流式预览，保留来源和继续读取入口。 Read committed history with provenance and paging. */
  const readHistory = (before: number | null = null) => {
    const identity = target
    void perform(
      () =>
        window.agent.readPeerHistory({
          source_session_id: session.session_id,
          target_session_id: identity,
          before_seq: before,
          limit: 20
        }),
      (value) => {
        if (selectedPeer.current === identity) {
          setHistory(value)
          setHistoryOpen(true)
        }
      }
    )
  }

  const link = page?.links.find(
    (item) => item.source_session_id === session.session_id && item.target_session_id === target
  )
  const label = (identity: string) =>
    identity === session.session_id
      ? '本会话'
      : peers.find((item) => item.session_id === identity)?.role ||
        peers.find((item) => item.session_id === identity)?.title ||
        identity
  if (!session.task_id) return null
  return (
    <details
      className="collaboration-panel"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>会话协作</summary>
      {open && (
        <div className="collaboration-body">
          {(error || page?.error) && <p role="alert">{error || page?.error}</p>}
          <p className="muted">
            选择同任务的已有会话并约定分工。读取不调用模型；发送请求后，接收方可用时才开始工作。
          </p>
          <details>
            <summary>普通协作消息（空闲时只收件）</summary>
            {target && page && !link?.enabled && (
              <p className="settings-hint" role="status">
                尚未为所选会话保存协作约定。请在下方选择「日常协作请求」并保存分工，然后发送消息。
              </p>
            )}
            <textarea
              aria-label="协作消息"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
            <button
              type="button"
              disabled={busy || !target || !message.trim()}
              onClick={() =>
                void perform(
                  () =>
                    window.agent.sendPeerMessage({
                      operation_id: crypto.randomUUID(),
                      source_session_id: session.session_id,
                      target_session_id: target,
                      content: message
                    }),
                  () => setMessage('')
                )
              }
            >
              发送给所选会话
            </button>
            {mailbox?.messages.map((item) => (
              <details key={item.message_id}>
                <summary>
                  {label(item.params.source_session_id)} → {label(item.params.target_session_id)} ·{' '}
                  {item.delivered_run_id ? '已纳入模型输入' : '已保存待接收'}
                </summary>
                <pre>{item.params.content}</pre>
              </details>
            ))}
            {mailbox?.next_cursor && (
              <button
                type="button"
                onClick={() =>
                  void perform(
                    () =>
                      window.agent.listPeerMessages({
                        session_id: session.session_id,
                        cursor: mailbox.next_cursor
                      }),
                    setMailbox
                  )
                }
              >
                下一页消息
              </button>
            )}
          </details>
          <label>
            协作会话
            <select
              aria-label="协作会话"
              value={target}
              disabled={busy}
              onChange={(event) => choose(event.target.value)}
            >
              <option value="">请选择已有会话</option>
              {peers.map((peer) => (
                <option key={peer.session_id} value={peer.session_id}>
                  {peer.role || peer.title} · {peer.session_id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          {!peers.length && <p className="muted">此任务暂无其他会话，可从左侧任务新建。</p>}
          {page && (
            <p className="muted">
              {page.reason === 'no_agreements_configured'
                ? '尚未安排协作约定。'
                : page.reason === 'no_task'
                  ? '当前会话尚未归属任务。'
                  : '协作约定已配置。'}
              {page.next_step} {page.worker_reason}
            </p>
          )}
          <p className="muted">
            请求会等待接收会话空闲；已有未结束 Goal 或上次失败由你明确处理。
            可在请求卡片停止指定请求，不会停止对方无关工作。模型等待到时只返回现状。
          </p>
          {target && (
            <>
              <label>
                工作安排
                <select
                  aria-label="工作安排"
                  value={kind}
                  disabled={busy}
                  onChange={(event) => {
                    const value = event.target.value
                    if (value === 'request' || value === 'handoff' || value === 'review')
                      setKind(value)
                  }}
                >
                  <option value="request">日常协作请求</option>
                  <option value="handoff">交接工作</option>
                  <option value="review">独立 Code Review</option>
                </select>
              </label>
              {kind === 'request' && (
                <>
                  <label>
                    协作分工
                    <textarea
                      aria-label="协作分工"
                      value={scope}
                      maxLength={8000}
                      onChange={(event) => setScope(event.target.value)}
                      placeholder="例如：本会话负责实现；对方负责查资料，可请求其确认启动方法并返回来源。"
                    />
                  </label>
                  <label>
                    协作范围
                    <select
                      aria-label="协作范围"
                      value={mode}
                      onChange={(event) =>
                        setMode(event.target.value === 'normal' ? 'normal' : 'plan')
                      }
                    >
                      <option value="plan">只读资料 / 分析</option>
                      <option value="normal">按分工执行代码工作</option>
                    </select>
                  </label>
                  <div className="button-row">
                    <button
                      disabled={busy || !scope.trim()}
                      onClick={() =>
                        void perform(() =>
                          window.agent.connectSessions({
                            source_session_id: session.session_id,
                            target_session_id: target,
                            scope,
                            mode,
                            enabled: true
                          })
                        )
                      }
                    >
                      保存协作约定
                    </button>
                    <button disabled={busy || !link?.enabled} onClick={() => readHistory()}>
                      读取对方历史
                    </button>
                    {link?.enabled && (
                      <button
                        disabled={busy}
                        onClick={() =>
                          void perform(() =>
                            window.agent.connectSessions({
                              source_session_id: session.session_id,
                              target_session_id: target,
                              scope: link.scope,
                              mode: link.mode,
                              enabled: false
                            })
                          )
                        }
                      >
                        停用约定
                      </button>
                    )}
                  </div>
                </>
              )}
              {kind !== 'request' && (
                <p className="muted">
                  {kind === 'review'
                    ? '由你发起只读审查，报告发现；来源工作继续。'
                    : '传递任务事实、已有成果和接手范围。'}
                  接收方可按需读取来源会话和历史差异；不会新建会话或复制项目。
                </p>
              )}
              <label>
                {kind === 'review' ? '审查范围' : kind === 'handoff' ? '接手目标' : '协作请求'}
                <textarea
                  aria-label={
                    kind === 'review' ? '审查范围' : kind === 'handoff' ? '接手目标' : '协作请求'
                  }
                  value={objective}
                  maxLength={kind === 'request' ? undefined : 8000}
                  onChange={(event) => setObjective(event.target.value)}
                  placeholder="说明要做什么，以及希望返回什么结果。"
                />
              </label>
              {kind !== 'request' && (
                <label>
                  补充说明
                  <textarea
                    aria-label="交接补充说明"
                    value={notes}
                    maxLength={16000}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="补充接口约定、未决事项或下一步；已有任务和成果由应用带入。"
                  />
                </label>
              )}
              {kind === 'handoff' && (
                <label>
                  接续上下文
                  <select
                    value={contextMode}
                    onChange={(event) =>
                      setContextMode(event.target.value === 'inherit' ? 'inherit' : 'isolated')
                    }
                  >
                    <option value="isolated">独立：共同事实与交接简报</option>
                    <option value="inherit">继承：来源的有效上下文快照</option>
                  </select>
                </label>
              )}
              {kind === 'handoff' && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={transfer}
                    onChange={(event) => setTransfer(event.target.checked)}
                  />
                  移交本会话当前 Goal / 运行；取消勾选则仅传递成果并保留原工作
                </label>
              )}
              <button
                disabled={busy || (kind === 'request' && !link?.enabled) || !objective.trim()}
                onClick={send}
              >
                {kind === 'handoff'
                  ? '开始交接'
                  : kind === 'review'
                    ? '发起独立 Review'
                    : '发送协作请求'}
              </button>
              {history && (
                <details
                  open={historyOpen}
                  onToggle={(event) => setHistoryOpen(event.currentTarget.open)}
                >
                  <summary>
                    公开历史 · {history.summary.role || history.summary.title} · 水位{' '}
                    {history.watermark}
                  </summary>
                  {history.entries.map((entry) => (
                    <pre key={entry.seq}>
                      #{entry.seq} · {entry.kind}
                      {'\n'}
                      {entry.text || entry.result?.content || entry.call?.name}
                    </pre>
                  ))}
                  {!history.entries.length && <p className="muted">尚无已提交的历史。</p>}
                  {history.before_seq && (
                    <button disabled={busy} onClick={() => readHistory(history.before_seq)}>
                      读取更早历史
                    </button>
                  )}
                </details>
              )}
            </>
          )}
          <div className="collaboration-requests">
            {page?.requests.map((request) => (
              <article key={request.request_id} data-request-id={request.request_id}>
                {request.arrangement && (
                  <p className="muted">
                    {request.arrangement.kind === 'handoff' ? '用户交接' : '用户发起的独立 Review'}
                  </p>
                )}
                <strong>
                  {label(request.params.source_session_id)} →{' '}
                  {label(request.params.target_session_id)} · {statusNames[request.status]}
                </strong>
                <p>{request.params.objective}</p>
                {request.reason && <p>{request.reason}</p>}
                {request.outcome && (
                  <p>
                    工作报告：
                    {
                      {
                        complete: '完成',
                        continue: '部分完成，需接续',
                        wait: '等待补充信息',
                        return: '已报告，返回用户'
                      }[request.outcome]
                    }
                  </p>
                )}
                {request.next_action && <p>建议下一步：{request.next_action}</p>}
                {request.result && (
                  <details open={request.status === 'failed'}>
                    <summary>
                      {request.status === 'running' ? '查看阶段进展' : '查看返回结果'}
                    </summary>
                    <pre>{request.result}</pre>
                  </details>
                )}
                {request.brief && (
                  <details>
                    <summary>查看来源简报 · 任务版本 {request.brief.task.revision}</summary>
                    <p>任务：{request.brief.task.fields.goal}</p>
                    {request.brief.source_goal && (
                      <p>
                        来源 Goal：{request.brief.source_goal.objective} ·{' '}
                        {request.brief.source_goal.status}
                      </p>
                    )}
                    <pre>
                      {[
                        request.brief.task.fields.progress,
                        request.brief.task.work?.last_report?.summary,
                        request.brief.task.fields.decisions,
                        request.brief.task.fields.artifacts,
                        request.brief.task.fields.unresolved,
                        request.arrangement?.notes
                      ]
                        .filter(Boolean)
                        .join('\n\n')}
                    </pre>
                    <p>
                      来源会话 {request.brief.source_session_id} · 水位{' '}
                      {request.brief.source_watermark}
                    </p>
                    {request.brief.changes.changes.map((change) => (
                      <p key={change.change_id}>
                        {change.path} · {change.status} · {change.change_id}
                      </p>
                    ))}
                    {request.brief.changes.next_cursor && (
                      <p>还有其他成果，接收方可继续按游标读取。</p>
                    )}
                    <small>
                      这是交接时的记录；后续调整可直接在接收会话发送新要求，原简报保留。
                    </small>
                  </details>
                )}
                {request.target_run_id && (
                  <p className="muted">
                    运行 {request.target_run_id}
                    {request.result_seq ? ` · 结果 #${request.result_seq}` : ''}
                  </p>
                )}
                <div className="button-row">
                  <button
                    onClick={() =>
                      onSelect({
                        projectId: session.project_id,
                        taskId: session.task_id ?? null,
                        sessionId: request.params.target_session_id
                      })
                    }
                  >
                    查看接收会话
                  </button>
                  {request.status === 'held' && !request.target_run_id && (
                    <button
                      disabled={busy}
                      onClick={() =>
                        void perform(() =>
                          window.agent.controlCollaboration({
                            request_id: request.request_id,
                            action: 'resume'
                          })
                        )
                      }
                    >
                      继续此请求
                    </button>
                  )}
                  {['preparing', 'queued', 'running', 'held'].includes(request.status) && (
                    <button
                      disabled={busy}
                      onClick={() =>
                        void perform(() =>
                          window.agent.controlCollaboration({
                            request_id: request.request_id,
                            action: 'cancel'
                          })
                        )
                      }
                    >
                      停止此请求
                    </button>
                  )}
                </div>
              </article>
            ))}
            {page && !page.requests.length && <p className="muted">暂无协作请求。</p>}
            {page?.next_cursor && (
              <button onClick={() => setCursor(page.next_cursor)}>更多请求</button>
            )}
            {cursor && <button onClick={() => setCursor(null)}>返回首页</button>}
          </div>
        </div>
      )}
    </details>
  )
}
