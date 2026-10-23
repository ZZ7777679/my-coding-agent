/** 就地复盘与独立页共用后台作业。 Contextual reviews share jobs with the independent page. */
import { useEffect, useRef, useState } from 'react'
import type { EvolutionJob, EvolutionScope, EvolutionSource } from '../../generated/protocol'
import './Evolution.css'

export interface EvolutionEntry {
  origin: EvolutionScope | null
  instruction: string
  jobId?: string
  sources?: EvolutionSource[]
}

const labels = { project: '项目', task: '任务', session: '会话' }

/** 范围内一键启动、查看和停止，折叠时不挤占工作区。 Start, inspect and stop without taking over the workspace. */
export function EvolutionQuick({
  projectId,
  origin,
  onOpen
}: {
  projectId: string
  origin: EvolutionScope
  onOpen: (entry: EvolutionEntry) => void
}) {
  const [open, setOpen] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [job, setJob] = useState<EvolutionJob | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const alive = useRef(false)
  const operation = useRef(0)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      ++operation.current
    }
  }, [])
  useEffect(() => {
    if (!open) return
    let current = true
    let pending = false
    /** 列表只读摘要；迟到轮询不覆盖刚启动或停止的作业。 Read summaries without overwriting newer operations. */
    async function refresh() {
      if (pending) return
      pending = true
      const ticket = operation.current
      try {
        const result = await window.agent.evolutionList({ project_id: projectId, origin, limit: 1 })
        if (!current || ticket !== operation.current) return
        if (result.ok) setJob(result.data.jobs?.[0] ?? null)
        else setError(result.error.message)
      } catch {
        if (current) setError('复盘状态读取失败，可重新展开。')
      } finally {
        pending = false
      }
    }
    void refresh()
    const timer = setInterval(() => void refresh(), 2500)
    return () => {
      current = false
      clearInterval(timer)
    }
  }, [open, projectId, origin.kind, origin.identity])

  /** 同一后台入口接纳作业，不要求先选目标或保存反馈。 Start without a target or saved-feedback prerequisite. */
  async function start() {
    ++operation.current
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.evolutionGenerate({
        project_id: projectId,
        origin,
        instruction,
        mode: 'investigate'
      })
      if (!alive.current) return
      ++operation.current
      if (result.ok) setJob(result.data)
      else setError(result.error.message)
    } catch {
      if (alive.current) setError('复盘未能启动，输入已保留。')
    } finally {
      if (alive.current) setBusy(false)
    }
  }
  /** 停止独立复盘，不改变原会话运行。 Stop the review without changing the source run. */
  async function stop() {
    if (!job) return
    ++operation.current
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.evolutionStop({ project_id: projectId, job_id: job.job_id })
      if (!alive.current) return
      ++operation.current
      if (result.ok) setJob(result.data)
      else setError(result.error.message)
    } catch {
      if (alive.current) setError('停止失败，可重试。')
    } finally {
      if (alive.current) setBusy(false)
    }
  }
  return (
    <details
      className="evolution-quick"
      onToggle={(event) => setOpen(event.currentTarget.open)}
      onKeyDown={(event) => {
        if (event.key === 'Escape') event.currentTarget.open = false
      }}
    >
      <summary>
        复盘此{labels[origin.kind]}
        {job?.status === 'running' ? ' · 调查中' : ''}
      </summary>
      <div>
        <p className="muted">
          范围：此{labels[origin.kind]}的正式会话 Trace。先筛选线索，再按需查证。
        </p>
        <label>
          关注点（可选）
          <input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="例如：反复失败的工具调用；留空则寻找可复用经验与问题"
          />
        </label>
        <div className="button-row">
          <button
            className="primary"
            disabled={busy || job?.status === 'running'}
            onClick={() => void start()}
          >
            开始复盘
          </button>
          <button onClick={() => onOpen({ origin, instruction })}>自定义范围与预算</button>
          {job && (
            <button onClick={() => onOpen({ origin, instruction, jobId: job.job_id })}>
              查看本次改进
            </button>
          )}
          {job?.status === 'running' && (
            <button disabled={busy} onClick={() => void stop()}>
              停止复盘
            </button>
          )}
        </div>
        {job && (
          <p role="status">
            {job.message || job.status} · 请求 {job.requests ?? 0}
            {job.summary && ` · ${job.summary}`}
          </p>
        )}
        {error && <p role="alert">{error}</p>}
      </div>
    </details>
  )
}
