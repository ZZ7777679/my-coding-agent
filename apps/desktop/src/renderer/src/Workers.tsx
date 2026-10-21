import { useEffect, useState } from 'react'
import type { WorkerPage, SessionView } from '../../generated/protocol'
import { useLatestRefresh } from './useLatestRefresh'

/** 子任务入口贴近输入区，结果各自折叠；不增加侧栏用户会话。
 * Keep worker controls beside the composer and results in collapsible cards. */
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
  useEffect(
    () =>
      window.agent.onSessionEvent((event) => {
        if (event.session_id === sessionId && event.kind === 'changed')
          setRefresh((value) => value + 1)
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

  /** 显式保存能力开关，正在运行的孩子可分别停止。
   * Save delegation settings; existing children retain individual stop controls. */
  async function configure(enabled: boolean, concurrency: number) {
    setBusy(true)
    const result = await window.agent.configureWorkers({
      session_id: sessionId,
      settings: { enabled, concurrency }
    })
    if (result.ok) {
      setPage(result.data)
      setError('')
    } else setError(result.error.message)
    setBusy(false)
  }
  /** 控制真实子任务，未活动时继续工作交回主输入区。
   * Control actual workers; idle continuation goes through the main conversation. */
  async function control(workerId: string, action: 'stop' | 'continue') {
    setBusy(true)
    const result = await window.agent.controlWorker({
      session_id: sessionId,
      worker_id: workerId,
      action,
      prompt
    })
    if (result.ok) {
      setPage(result.data)
      setError('')
      setPrompt('')
    } else setError(result.error.message)
    setBusy(false)
  }
  return (
    <details className="knowledge-panel" data-testid="workers">
      <summary>
        子 agent · {page?.settings.enabled ? '已开启' : '关闭'} ·{' '}
        {page?.workers.filter((item) => ['running', 'queued'].includes(item.status)).length ?? 0}{' '}
        项进行中
      </summary>
      <div className="knowledge-body">
        {error && <p role="alert">{error}</p>}
        <label>
          <input
            type="checkbox"
            aria-label="允许拆分子 agent"
            checked={page?.settings.enabled ?? false}
            disabled={busy || !connected || !page}
            onChange={(event) =>
              void configure(event.target.checked, page?.settings.concurrency ?? 2)
            }
          />
          允许按需拆分子 agent
        </label>
        <label>
          同时执行数量
          <input
            type="number"
            min={1}
            value={page?.settings.concurrency ?? 2}
            disabled={busy || !page}
            onChange={(event) => {
              if (page)
                setPage({
                  ...page,
                  settings: { ...page.settings, concurrency: Number(event.target.value) }
                })
            }}
          />
        </label>
        <button
          type="button"
          disabled={!page || busy}
          onClick={() =>
            void configure(page?.settings.enabled ?? false, page?.settings.concurrency ?? 2)
          }
        >
          保存并发数
        </button>
        <p className="muted">
          仅在独立工作可并行、角色分工或隔离探索确有收益时拆分。共用来源预算；停止主任务会停止其子工作。
        </p>
        <input
          aria-label="子任务补充"
          placeholder="给已有子任务的补充要求"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
        />
        {!active && <p className="muted">当前没有运行。需要继续子任务时，在主输入区说明即可。</p>}
        {page?.workers.map((item) => (
          <details key={item.worker_id}>
            <summary>
              {item.assignment.objective} · {item.status} ·{' '}
              {item.assignment.context_mode === 'inherit' ? '继承上下文' : '独立上下文'}
            </summary>
            <p>
              {item.assignment.role} · {item.assignment.scope} · {item.model_id}
            </p>
            <p>
              请求 {item.requests ?? 0} · 工具 {item.tools ?? 0} · 活跃{' '}
              {(item.active_seconds ?? 0).toFixed(1)} 秒（已计入父安排）
            </p>
            <pre>{item.result || '结果尚未返回'}</pre>
            {item.code && <p>{item.code}</p>}
            <button
              type="button"
              disabled={busy || !['queued', 'running'].includes(item.status)}
              onClick={() => void control(item.worker_id, 'stop')}
            >
              停止子任务
            </button>
            <button
              type="button"
              disabled={busy || !active || !prompt.trim()}
              onClick={() => void control(item.worker_id, 'continue')}
            >
              补充 / 继续
            </button>
            <button
              type="button"
              onClick={() =>
                void window.agent
                  .getSession({ session_id: item.session_id, before_seq: null })
                  .then((result) => {
                    if (result.ok) setDetail(result.data)
                    else setError(result.error.message)
                  })
              }
            >
              查看子任务记录
            </button>
          </details>
        ))}
        {detail && (
          <details open>
            <summary>子任务公开记录</summary>
            {detail.entries.map((item) => (
              <pre key={item.seq}>
                {item.text || JSON.stringify(item.call ?? item.result, null, 2)}
              </pre>
            ))}
            {detail.before_seq && (
              <button
                type="button"
                onClick={() =>
                  void window.agent
                    .getSession({
                      session_id: detail.summary.session_id,
                      before_seq: detail.before_seq
                    })
                    .then((result) => {
                      if (result.ok) setDetail(result.data)
                      else setError(result.error.message)
                    })
                }
              >
                更早记录
              </button>
            )}
          </details>
        )}
      </div>
    </details>
  )
}
