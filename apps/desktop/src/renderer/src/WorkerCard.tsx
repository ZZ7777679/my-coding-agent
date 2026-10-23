import { useEffect, useRef, useState } from 'react'
import type { SessionView, WorkerRecord } from '../../generated/protocol'
import { FailureNotice } from './FailureNotice'
import { Markdown } from './Markdown'
import { Trace } from './Trace'

const statuses: Record<WorkerRecord['status'], string> = {
  queued: '排队中',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
  budget_exceeded: '预算已用完'
}

/** 优先显示工作短名称，旧记录使用目标首行，不以 UUID 代替角色。
 * Prefer a work name, falling back to the objective's first line for older records. */
function workerName(worker: WorkerRecord): string {
  const explicit = worker.assignment.name?.trim()
  if (explicit) return explicit
  const objective = worker.assignment.objective.trim().split(/\r?\n/)[0]
  return objective.length > 64 ? objective.slice(0, 64) + '…' : objective
}

/** 单个子任务的独立阅读卡片，刷新不重置折叠、草稿或已读历史。
 * Preserve folding, drafts and loaded history independently for each worker. */
export function WorkerCard({
  worker,
  ownerSessionId,
  connected,
  active,
  visible,
  initiallyOpen,
  onChanged
}: {
  worker: WorkerRecord
  ownerSessionId: string
  connected: boolean
  active: boolean
  visible: boolean
  initiallyOpen: boolean
  onChanged: () => void
}) {
  const [expanded, setExpanded] = useState(initiallyOpen)
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<SessionView | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [trace, setTrace] = useState(false)
  const ticket = useRef(0)
  useEffect(
    () => () => {
      ++ticket.current
    },
    []
  )

  /** 控制请求只派发一次，响应迟到不清掉新草稿。 Dispatch once and preserve newer drafts. */
  async function control(action: 'continue' | 'stop') {
    const id = ++ticket.current
    const submitted = prompt
    setBusy(true)
    try {
      const result = await window.agent.controlWorker({
        session_id: ownerSessionId,
        worker_id: worker.worker_id,
        action,
        prompt: submitted
      })
      if (id !== ticket.current) return
      if (result.ok) {
        setError('')
        setPrompt((value) => (value === submitted ? '' : value))
        onChanged()
      } else setError(result.error.message)
    } catch {
      if (id === ticket.current) setError('子任务操作结果未确认，请刷新核对；没有自动重试。')
    } finally {
      if (id === ticket.current) setBusy(false)
    }
  }

  /** 按需分页读取该子任务，关闭正文不删除已加载数据。 Page only this worker's requested history. */
  async function history(older = false) {
    const id = ++ticket.current
    setBusy(true)
    try {
      const result = await window.agent.getSession({
        session_id: worker.session_id,
        before_seq: older ? (detail?.before_seq ?? null) : null
      })
      if (id !== ticket.current) return
      if (result.ok) {
        setDetail((old) =>
          older && old
            ? {
                ...result.data,
                entries: [...result.data.entries, ...old.entries]
              }
            : result.data
        )
        setError('')
      } else setError(result.error.message)
    } catch {
      if (id === ticket.current) setError('子任务记录读取失败。')
    } finally {
      if (id === ticket.current) setBusy(false)
    }
  }

  return (
    <details
      className="worker-card"
      open={expanded}
      data-worker-id={worker.worker_id}
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary title={worker.assignment.objective}>{workerName(worker)}</summary>
      <div className="worker-card-body reading-detail">
        {error && <p role="alert">{error}</p>}
        <section className="worker-section">
          <h3>目标与范围</h3>
          <p className="worker-objective">{worker.assignment.objective}</p>
          <dl className="worker-facts">
            <dt>角色</dt>
            <dd>{worker.assignment.role === 'research' ? '调研与分析' : '代码实现'}</dd>
            <dt>工作范围</dt>
            <dd>{worker.assignment.scope || '未单独指定'}</dd>
            <dt>上下文</dt>
            <dd>{worker.assignment.context_mode === 'inherit' ? '继承来源材料' : '独立上下文'}</dd>
          </dl>
        </section>
        <section className="worker-section">
          <h3>当前进度</h3>
          <dl className="worker-metrics">
            <div>
              <dt>状态</dt>
              <dd>{statuses[worker.status]}</dd>
            </div>
            <div>
              <dt>模型</dt>
              <dd>{worker.model_id}</dd>
            </div>
            <div>
              <dt>模型请求</dt>
              <dd>{worker.requests ?? 0}</dd>
            </div>
            <div>
              <dt>工具调用</dt>
              <dd>{worker.tools ?? 0}</dd>
            </div>
            <div>
              <dt>活跃时间</dt>
              <dd>{(worker.active_seconds ?? 0).toFixed(1)} 秒</dd>
            </div>
          </dl>
          <dl className="worker-facts">
            <dt>最近动作</dt>
            <dd>
              {worker.last_tool
                ? `${worker.last_tool} · ${worker.last_tool_status ?? '状态未知'}`
                : (worker.model_progress?.phase ?? '尚无工具事实')}
            </dd>
            <dt>更新时间</dt>
            <dd>
              {worker.last_event_at ? new Date(worker.last_event_at).toLocaleTimeString() : '未知'}
            </dd>
          </dl>
          {!!worker.pending_messages?.length && (
            <p>待处理补充：{worker.pending_messages?.length} 条</p>
          )}
        </section>
        {worker.failure && (
          <FailureNotice
            error={{
              ...worker.failure,
              remediation: '已保存输出和记录可读取；修正原因后在主会话明确接续。'
            }}
            sessionId={worker.session_id}
            runId={worker.run_id ?? undefined}
          />
        )}
        {worker.history_issue && <p role="alert">{worker.history_issue}</p>}
        <section className="worker-section worker-result">
          <h3>{worker.status === 'completed' ? '输出结果' : '已保存的部分输出'}</h3>
          {worker.result ? (
            <Markdown text={worker.result} />
          ) : (
            <p className="muted">
              {['running', 'queued'].includes(worker.status)
                ? '尚未提交正文，可查看最近动作或 Trace。'
                : '未保存回答正文；工具记录仍可查。'}
            </p>
          )}
        </section>
        <section className="worker-section">
          <h3>操作</h3>
          <label className="worker-supplement">
            补充要求
            <textarea
              aria-label="子任务补充"
              rows={2}
              value={prompt}
              placeholder="给这个子任务的补充要求，可换行"
              onChange={(event) => setPrompt(event.target.value)}
            />
          </label>
          <div className="worker-actions">
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
            <p className="muted">原安排已结束；继续工作请在主输入区说明，可引用 Worker ID。</p>
          )}
          <div className="worker-actions">
            <button
              disabled={busy || !connected}
              onClick={() => {
                setShowHistory((value) => !value)
                if (!detail && !showHistory) void history()
              }}
            >
              {showHistory ? '收起子任务记录' : '查看子任务记录'}
            </button>
            <button
              onClick={() => {
                setTrace((value) => !value)
                if (!detail && !trace) void history()
              }}
            >
              {trace ? '收起 Trace' : '查看 Trace'}
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
        </section>
        <details className="worker-section">
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
            <dt>记录位置</dt>
            <dd>{worker.last_seq ?? '未知'}</dd>
          </dl>
        </details>
        {showHistory && detail && (
          <section className="worker-section">
            <h3>子任务公开记录</h3>
            {detail.before_seq && (
              <button disabled={busy} onClick={() => void history(true)}>
                更早记录
              </button>
            )}
            {detail.entries.map((entry) => (
              <article className="worker-history-entry" key={entry.seq}>
                <small>
                  #{entry.seq} · {entry.kind}
                </small>
                {entry.text || entry.partial_text ? (
                  <Markdown text={entry.text || entry.partial_text || ''} />
                ) : (
                  <p>{entry.call?.name ?? (entry.result ? '工具结果（详情见 Trace）' : '')}</p>
                )}
              </article>
            ))}
          </section>
        )}
        {trace && detail && (
          <Trace
            sessionId={worker.session_id}
            projectId={detail.summary.project_id}
            revision={detail.watermark}
            focusSeq={null}
            onClose={() => setTrace(false)}
            initialExpanded
            visible={visible && expanded}
          />
        )}
      </div>
    </details>
  )
}
