import { useEffect, useState } from 'react'
import type { WorkerPage } from '../../generated/protocol'
import { useLatestRefresh } from './useLatestRefresh'
import { ReadingWorkspace } from './ReadingWorkspace'
import { WorkerCard } from './WorkerCard'

/** 集中管理委派，每个子任务保留独立折叠与阅读状态。
 * Manage delegation with independently collapsible worker cards. */
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
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [open, setOpen] = useState(false)
  const [concurrency, setConcurrency] = useState<number | null>(null)
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

  /** 设置只影响未来委派，当前运行沿用快照。 Apply settings only to future assignments. */
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
      {page && !page.settings.enabled && (
        <button
          className="worker-entry"
          disabled={busy || !connected}
          onClick={() => void configure(true)}
        >
          开启子 Agent
        </button>
      )}
      <ReadingWorkspace open={open} title="子 Agent 工作空间" onClose={() => setOpen(false)}>
        <details className="worker-options">
          <summary>委派设置 · {page?.settings.enabled ? '已开启' : '关闭'}</summary>
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
            默认总预算不限；有限预算时父子共用该安排预算。停止主任务会停止其子工作，已保存输出保留。
          </p>
        </details>
        {error && <p role="alert">{error}</p>}
        <div className="worker-cards" aria-label="子任务列表">
          {!page?.workers.length && (
            <p>暂无子任务。在委派设置中开启后，告诉 Agent 如何分工即可。</p>
          )}
          {page?.workers
            .slice()
            .reverse()
            .map((worker, index) => (
              <WorkerCard
                key={worker.worker_id}
                worker={worker}
                ownerSessionId={sessionId}
                connected={connected}
                active={active}
                visible={open}
                initiallyOpen={index === 0}
                onChanged={() => setRefresh((n) => n + 1)}
              />
            ))}
        </div>
      </ReadingWorkspace>
    </div>
  )
}
