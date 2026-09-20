/** 左侧项目、任务、会话树；选择与展开分开管理。 Project/task/session tree with independent selection and expansion. */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ProjectSummary, SessionSummary, TaskSummary } from '../../generated/protocol'

export type WorkspaceSelection = {
  projectId: string
  taskId: string | null
  sessionId: string | null
}
type Props = {
  projects: ProjectSummary[]
  selected: WorkspaceSelection | null
  revision: number
  connected: boolean
  onSelect: (selection: WorkspaceSelection) => void
}

/** 按任务和会话各自游标加载，保留不可读条目的明确提示。 Page tasks and sessions with explicit unreadable-record feedback. */
function ProjectBranch({
  project,
  selected,
  revision,
  connected,
  onSelect
}: Omit<Props, 'projects'> & { project: ProjectSummary }) {
  const [expanded, setExpanded] = useState(selected?.projectId === project.project_id)
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [openTasks, setOpenTasks] = useState<Set<string>>(new Set())
  const [taskCursor, setTaskCursor] = useState<string | null>(null)
  const [sessionCursor, setSessionCursor] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const epoch = useRef(0)
  const selection = useRef(selected)
  selection.current = selected
  const projectId = project.project_id

  /** 一次刷新有独立代次，旧页不能覆盖新状态。 Give refreshes generations so stale pages cannot replace new state. */
  const load = useCallback(
    async (kind: 'all' | 'tasks' | 'sessions', cursor: string | null = null) => {
      const ticket = ++epoch.current
      setLoading(true)
      setError('')
      try {
        const params = { project_id: projectId, cursor, limit: 20 }
        const [taskResult, sessionResult] = await Promise.all([
          kind !== 'sessions' ? window.agent.listTasks(params) : null,
          kind !== 'tasks' ? window.agent.listSessions(params) : null
        ])
        if (ticket !== epoch.current) return
        const target = selection.current
        if (target?.projectId === projectId) {
          if (
            taskResult?.ok &&
            target.taskId &&
            !taskResult.data.tasks.some((task) => task.task_id === target.taskId)
          ) {
            const detail = await window.agent.getTask(target.taskId)
            if (ticket !== epoch.current) return
            if (detail.ok && detail.data.project_id === projectId)
              taskResult.data.tasks.push({
                task_id: detail.data.task_id,
                project_id: projectId,
                title: detail.data.fields.title,
                status: detail.data.fields.status ?? 'active',
                revision: detail.data.revision
              })
          }
          if (
            sessionResult?.ok &&
            target.sessionId &&
            !sessionResult.data.sessions.some((session) => session.session_id === target.sessionId)
          ) {
            const detail = await window.agent.getSession({
              session_id: target.sessionId,
              before_seq: null
            })
            if (ticket !== epoch.current) return
            if (detail.ok && detail.data.summary.project_id === projectId)
              sessionResult.data.sessions.push(detail.data.summary)
          }
        }
        const notices: string[] = []
        if (taskResult?.ok) {
          setTasks((old) => [
            ...new Map(
              (cursor ? [...old, ...taskResult.data.tasks] : taskResult.data.tasks).map((task) => [
                task.task_id,
                task
              ])
            ).values()
          ])
          setTaskCursor(taskResult.data.next_cursor)
          if (taskResult.data.unavailable_count)
            notices.push(`${taskResult.data.unavailable_count} 个任务记录不可读`)
        } else if (taskResult) notices.push(taskResult.error.message)
        if (sessionResult?.ok) {
          setSessions((old) => [
            ...new Map(
              (cursor ? [...old, ...sessionResult.data.sessions] : sessionResult.data.sessions).map(
                (session) => [session.session_id, session]
              )
            ).values()
          ])
          setSessionCursor(sessionResult.data.next_cursor)
          if (sessionResult.data.unavailable_count)
            notices.push(`${sessionResult.data.unavailable_count} 个会话记录不可读`)
        } else if (sessionResult) notices.push(sessionResult.error.message)
        setError(notices.join('；'))
      } catch {
        if (ticket === epoch.current) setError('列表读取失败，请重试。')
      } finally {
        if (ticket === epoch.current) setLoading(false)
      }
    },
    [projectId]
  )

  useEffect(() => {
    if (expanded && connected) void load('all')
    return () => {
      ++epoch.current
    }
  }, [expanded, connected, revision, load])
  useEffect(() => {
    if (selected?.projectId !== projectId) return
    setExpanded(true)
    const taskId = selected.taskId
    if (taskId) setOpenTasks((old) => new Set([...old, taskId]))
  }, [selected, projectId])

  /** 会话始终在所属项目下面显示，不借用当前右侧页面的归属。 Render sessions under their own project. */
  const sessionButton = (session: SessionSummary) => (
    <button
      key={session.session_id}
      className={'tree-session ' + (selected?.sessionId === session.session_id ? 'selected' : '')}
      data-session-id={session.session_id}
      title={session.title}
      onClick={() =>
        onSelect({ projectId, taskId: session.task_id ?? null, sessionId: session.session_id })
      }
    >
      <span aria-hidden="true">◦</span>
      <span>{session.title}</span>
      {session.run && (
        <span
          className={'session-state ' + session.run.status}
          title={
            session.run.status === 'running'
              ? '正在运行'
              : session.run.status === 'stopping'
                ? '正在停止'
                : session.run.status === 'failed'
                  ? '运行失败'
                  : session.run.status === 'budget_exceeded'
                    ? '预算用尽'
                    : session.run.status === 'completed'
                      ? '已完成'
                      : '已停止'
          }
          aria-label={
            session.run.status === 'running'
              ? '正在运行'
              : session.run.status === 'stopping'
                ? '正在停止'
                : session.run.status === 'failed'
                  ? '运行失败'
                  : session.run.status === 'budget_exceeded'
                    ? '预算用尽'
                    : session.run.status === 'completed'
                      ? '已完成'
                      : '已停止'
          }
        >
          {session.run.status === 'running'
            ? '●'
            : session.run.status === 'stopping'
              ? '◌'
              : session.run.status === 'failed' || session.run.status === 'budget_exceeded'
                ? '!'
                : session.run.status === 'completed'
                  ? '✓'
                  : '−'}
        </span>
      )}
    </button>
  )
  const knownTasks = new Set(tasks.map((task) => task.task_id))
  const unassigned = sessions.filter((session) => !session.task_id)
  const pendingTasks = sessions.filter(
    (session) => session.task_id && !knownTasks.has(session.task_id)
  )
  return (
    <div className="project-branch">
      <div className="tree-row">
        <button
          className="tree-toggle"
          aria-label={`${expanded ? '收起' : '展开'}项目 ${project.name}`}
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? '▾' : '▸'}
        </button>
        <button
          className={'tree-project ' + (selected?.projectId === projectId ? 'selected' : '')}
          title={project.path}
          disabled={!connected}
          onClick={() => {
            setExpanded(true)
            onSelect({ projectId, taskId: null, sessionId: null })
          }}
        >
          <strong>{project.name}</strong>
          <small>{project.available ? project.path : '目录不可用'}</small>
        </button>
      </div>
      {expanded && (
        <div className="tree-children">
          <button
            className="text-button"
            disabled={!connected || !project.available}
            onClick={() => onSelect({ projectId, taskId: null, sessionId: null })}
          >
            ＋ 新建任务
          </button>
          {tasks.map((task) => (
            <div key={task.task_id}>
              <div className="tree-row">
                <button
                  className="tree-toggle"
                  aria-label={`${openTasks.has(task.task_id) ? '收起' : '展开'}任务 ${task.title}`}
                  aria-expanded={openTasks.has(task.task_id)}
                  onClick={() =>
                    setOpenTasks((old) => {
                      const next = new Set(old)
                      if (next.has(task.task_id)) next.delete(task.task_id)
                      else next.add(task.task_id)
                      return next
                    })
                  }
                >
                  {openTasks.has(task.task_id) ? '▾' : '▸'}
                </button>
                <button
                  className={
                    'tree-task ' +
                    (selected?.taskId === task.task_id && !selected.sessionId ? 'selected' : '')
                  }
                  onClick={() => onSelect({ projectId, taskId: task.task_id, sessionId: null })}
                >
                  <span>{task.title}</span>
                  <small>
                    {task.status === 'completed'
                      ? '已完成'
                      : task.status === 'archived'
                        ? '已归档'
                        : '进行中'}
                  </small>
                </button>
              </div>
              {openTasks.has(task.task_id) && (
                <div className="tree-sessions">
                  {sessions
                    .filter((session) => session.task_id === task.task_id)
                    .map(sessionButton)}
                  <button
                    className="text-button"
                    onClick={() => onSelect({ projectId, taskId: task.task_id, sessionId: null })}
                  >
                    任务概览 / 新会话
                  </button>
                </div>
              )}
            </div>
          ))}
          {!!unassigned.length && (
            <details open>
              <summary>未归属会话</summary>
              {unassigned.map(sessionButton)}
            </details>
          )}
          {!!pendingTasks.length && (
            <details open>
              <summary>任务尚未载入的会话</summary>
              {pendingTasks.map(sessionButton)}
            </details>
          )}
          {!loading && !tasks.length && !sessions.length && !error && (
            <p className="muted">创建任务开始工作。</p>
          )}
          {taskCursor && (
            <button disabled={loading} onClick={() => void load('tasks', taskCursor)}>
              更多任务
            </button>
          )}
          {sessionCursor && (
            <button disabled={loading} onClick={() => void load('sessions', sessionCursor)}>
              更多会话
            </button>
          )}
          {loading && <small role="status">读取列表…</small>}
          {error && <p role="alert">{error}</p>}
          <button className="text-button" disabled={loading} onClick={() => void load('all')}>
            刷新列表
          </button>
        </div>
      )}
    </div>
  )
}

/** 所有项目在左栏独立展开，右侧只显示选中的任务或会话。 Expand projects independently of the main detail view. */
export function TaskNavigation({ projects, ...props }: Props) {
  return (
    <nav className="task-navigation" aria-label="项目任务会话">
      {projects.map((project) => (
        <ProjectBranch key={project.project_id} project={project} {...props} />
      ))}
      {!projects.length && <p className="sidebar-empty">先选择项目文件夹。</p>}
    </nav>
  )
}
