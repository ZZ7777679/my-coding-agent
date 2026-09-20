/** 会话归属与用户分工编辑，不请求模型或其他会话历史。 Edit session membership without model calls or history access. */
import { useEffect, useRef, useState } from 'react'
import type { SessionSummary, TaskSummary } from '../../generated/protocol'
import type { WorkspaceSelection } from './TaskNavigation'

/** 旧会话可由用户归入任务，保存失败保留原值与输入。 Let users assign old sessions while preserving failed edits. */
export function SessionMembership({
  session,
  onSelect,
  onChanged
}: {
  session: SessionSummary
  onSelect: (selection: WorkspaceSelection) => void
  onChanged: () => void
}) {
  const [open, setOpen] = useState(false)
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [taskId, setTaskId] = useState(session.task_id ?? '')
  const [role, setRole] = useState(session.role ?? '')
  const [scope, setScope] = useState(session.scope ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const current = useRef(session.session_id)
  current.current = session.session_id
  useEffect(() => {
    setTaskId(session.task_id ?? '')
    setRole(session.role ?? '')
    setScope(session.scope ?? '')
  }, [session.session_id, session.task_id, session.role, session.scope])
  useEffect(() => {
    if (!open) return
    let disposed = false
    /** 分页取可选任务，失败显示而不丢掉历史归属。 Page eligible tasks and expose failures without changing membership. */
    const load = async () => {
      try {
        let cursor: string | null = null
        const all: TaskSummary[] = []
        do {
          const result = await window.agent.listTasks({
            project_id: session.project_id,
            cursor,
            limit: 20
          })
          if (disposed) return
          if (!result.ok) {
            setError(result.error.message)
            return
          }
          all.push(...result.data.tasks)
          cursor = result.data.next_cursor
        } while (cursor)
        setTasks(all)
      } catch {
        if (!disposed) setError('可选任务读取失败。')
      }
    }
    void load()
    return () => {
      disposed = true
    }
  }, [open, session.project_id])

  /** 只修改本会话元数据；运行中的会话由后端拒绝改归属。 Save membership only; the backend rejects changes during a run. */
  const save = async () => {
    if (!taskId || busy) return
    const target = session.session_id
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.assignSession({
        session_id: target,
        task_id: taskId,
        operation_id: crypto.randomUUID(),
        role,
        scope
      })
      if (!mounted.current || current.current !== target) return
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      onChanged()
      setOpen(false)
      onSelect({ projectId: session.project_id, taskId, sessionId: target })
    } catch {
      if (mounted.current && current.current === target) setError('保存结果未确认，请刷新后检查。')
    } finally {
      if (mounted.current && current.current === target) setBusy(false)
    }
  }
  return (
    <div className="session-membership">
      <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary
          title={
            session.task_id ? '查看或调整所属任务、角色和工作范围' : '未归属会话，可选择所属任务'
          }
        >
          归属与分工{session.role ? ` · ${session.role}` : ''}
        </summary>
        <div className="session-membership-body">
          {session.task_id ? (
            <button
              className="text-button"
              onClick={() =>
                onSelect({
                  projectId: session.project_id,
                  taskId: session.task_id ?? null,
                  sessionId: null
                })
              }
            >
              查看任务共享信息
            </button>
          ) : (
            <span className="muted">未归属会话</span>
          )}
          {error && <p role="alert">{error}</p>}
          <label>
            所属任务
            <select
              aria-label="所属任务"
              value={taskId}
              onChange={(event) => setTaskId(event.target.value)}
            >
              <option value="">请选择已有任务</option>
              {tasks.map((task) => (
                <option key={task.task_id} value={task.task_id}>
                  {task.title}
                </option>
              ))}
            </select>
          </label>
          {!tasks.length && <p className="muted">先在项目下创建任务，再将此会话归入。</p>}
          <label>
            会话角色
            <input
              aria-label="会话角色"
              value={role}
              maxLength={4096}
              onChange={(event) => setRole(event.target.value)}
            />
          </label>
          <label>
            工作范围
            <textarea
              aria-label="工作范围"
              value={scope}
              maxLength={16000}
              onChange={(event) => setScope(event.target.value)}
            />
          </label>
          <p className="muted">
            角色和范围用于明确分工；在“会话协作”中指定可访问的会话和协作约定。
          </p>
          <button
            disabled={
              !taskId ||
              busy ||
              session.run?.status === 'running' ||
              session.run?.status === 'stopping'
            }
            onClick={() => void save()}
          >
            保存归属与分工
          </button>
        </div>
      </details>
    </div>
  )
}
