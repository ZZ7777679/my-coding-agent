/** 用户维护的任务共享信息与正式会话入口。 User-maintained shared task information and session creation. */
import { useEffect, useRef, useState } from 'react'
import type { ModelId, ProjectSummary, TaskFields, TaskView } from '../../generated/protocol'
import type { WorkspaceSelection } from './TaskNavigation'
import { WorkItems } from './WorkItems'

type Props = {
  project: ProjectSummary | null
  taskId: string | null
  defaultModel: ModelId
  connected: boolean
  onSelect: (selection: WorkspaceSelection) => void
  onChanged: () => void
}

/** 按后端字段编辑共享记录；保存采用版本检查，错误保留草稿。 Edit shared facts with revision checks and preserved drafts. */
export function TaskPanel({
  project,
  taskId,
  defaultModel,
  connected,
  onSelect,
  onChanged
}: Props) {
  const [task, setTask] = useState<TaskView | null>(null)
  const [fields, setFields] = useState<TaskFields>({ title: '', goal: '' })
  const [model, setModel] = useState<ModelId>(defaultModel)
  const [role, setRole] = useState('')
  const [scope, setScope] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const current = useRef('')
  const identity = `${project?.project_id ?? ''}/${taskId ?? ''}`
  current.current = identity
  const pending = useRef<{ payload: string; id: string } | null>(null)

  useEffect(() => {
    let disposed = false
    setTask(null)
    setFields({ title: '', goal: '' })
    setError('')
    setNotice('')
    setBusy(!!taskId)
    pending.current = null
    if (taskId)
      void window.agent
        .getTask(taskId)
        .then((result) => {
          if (disposed) return
          if (result.ok && result.data.project_id === project?.project_id) {
            setTask(result.data)
            setFields(result.data.fields)
          } else setError(result.ok ? '任务不属于所选项目。' : result.error.message)
        })
        .catch(() => {
          if (!disposed) setError('任务读取失败，原记录已保留。')
        })
        .finally(() => {
          if (!disposed) setBusy(false)
        })
    return () => {
      disposed = true
    }
  }, [identity, reload])
  useEffect(() => setModel(defaultModel), [defaultModel])

  /** 输入未变时保留未确认操作的 ID，显式重试不会创建副本。 Reuse an unconfirmed operation ID for unchanged input. */
  const operation = (payload: object): string => {
    const text = JSON.stringify(payload)
    if (pending.current?.payload !== text)
      pending.current = { payload: text, id: crypto.randomUUID() }
    return pending.current.id
  }
  /** 任务先保存，首会话失败时停留概览并给出补齐入口。 Save the task first and expose partial session failures. */
  const save = async () => {
    if (!project || busy || !fields.goal.trim()) return
    const target = identity
    setBusy(true)
    setError('')
    setNotice('')
    const values = {
      ...fields,
      title: fields.title.trim() || fields.goal.trim().split('\n')[0].slice(0, 80)
    }
    try {
      if (task) {
        const body = { task_id: task.task_id, expected_revision: task.revision, fields: values }
        const result = await window.agent.updateTask({ ...body, operation_id: operation(body) })
        if (!mounted.current || current.current !== target) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        setTask(result.data)
        setFields(result.data.fields)
        setNotice('共享信息已保存，下次模型请求会采用新版本。')
      } else {
        const body = { project_id: project.project_id, model_id: model, fields: values }
        const result = await window.agent.createTask({ ...body, operation_id: operation(body) })
        if (!mounted.current || current.current !== target) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        if (result.data.session_error) {
          setTask(result.data.task)
          setFields(result.data.task.fields)
          setError('任务已保存，首会话尚未就绪：' + result.data.session_error)
        } else
          onSelect({
            projectId: project.project_id,
            taskId: result.data.task.task_id,
            sessionId: null
          })
      }
      pending.current = null
      onChanged()
    } catch {
      if (mounted.current && current.current === target)
        setError('保存结果未确认；可刷新查看，或用相同输入重试。')
    } finally {
      if (mounted.current && current.current === target) setBusy(false)
    }
  }

  /** 用户显式创建 / 接续会话才保存身份；不会开始模型执行。 Only explicit user actions create sessions, never start model work. */
  const createSession = async (first: boolean) => {
    if (!project || !task || busy) return
    const target = identity
    setBusy(true)
    setError('')
    try {
      const body = {
        project_id: project.project_id,
        task_id: task.task_id,
        model_id: model,
        role,
        scope
      }
      const result = first
        ? await window.agent.ensureTaskSession(task.task_id)
        : await window.agent.createSession({ ...body, operation_id: operation(body) })
      if (!mounted.current || current.current !== target) return
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      const session = 'task' in result.data ? result.data.session : result.data
      if (!session) {
        setError(
          'session_error' in result.data
            ? (result.data.session_error ?? '首会话尚未创建。')
            : '会话尚未创建。'
        )
        return
      }
      pending.current = null
      onChanged()
      onSelect({
        projectId: project.project_id,
        taskId: session.task_id ?? null,
        sessionId: session.session_id
      })
    } catch {
      if (mounted.current && current.current === target)
        setError('创建结果未确认，请刷新列表或显式重试。')
    } finally {
      if (mounted.current && current.current === target) setBusy(false)
    }
  }

  if (!project)
    return (
      <div className="content">
        <h1>先选择项目文件夹</h1>
      </div>
    )
  return (
    <div className="content task-panel">
      <div className="eyebrow">{project.name} / TASK</div>
      <h1>{task ? task.fields.title : taskId ? '读取任务' : '新建任务'}</h1>
      <p className="muted">
        任务保存阶段目标和共同信息，会话负责具体讨论与执行。创建不会调用模型。
      </p>
      {error && (
        <div role="alert" className="notice">
          {error}
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {taskId && (
        <button
          className="text-button"
          disabled={busy}
          onClick={() => setReload((value) => value + 1)}
        >
          重新载入共享信息（放弃未保存编辑）
        </button>
      )}
      {task && (
        <p className="muted">
          版本 {task.revision} · 本次更新来源：
          {task.source === 'user' ? '用户编辑' : 'Agent 工作报告'} · 更新{' '}
          {new Date(task.updated_at).toLocaleString()}
        </p>
      )}
      {(!taskId || task) && (
        <>
          {task && <WorkItems task={task} onSelect={onSelect} />}
          <form
            className="task-form"
            onSubmit={(event) => {
              event.preventDefault()
              void save()
            }}
          >
            <label>
              任务名称（可选）
              <input
                aria-label="任务名称"
                value={fields.title}
                maxLength={256}
                onChange={(event) => setFields({ ...fields, title: event.target.value })}
              />
            </label>
            <label>
              阶段目标
              <textarea
                aria-label="阶段目标"
                value={fields.goal}
                required
                rows={3}
                maxLength={16000}
                onChange={(event) => setFields({ ...fields, goal: event.target.value })}
              />
            </label>
            {task && (
              <label>
                任务状态
                <select
                  aria-label="任务状态"
                  value={fields.status ?? 'active'}
                  onChange={(event) =>
                    setFields({
                      ...fields,
                      status:
                        event.target.value === 'completed'
                          ? 'completed'
                          : event.target.value === 'archived'
                            ? 'archived'
                            : 'active'
                    })
                  }
                >
                  <option value="active">进行中</option>
                  <option value="completed">已完成</option>
                  <option value="archived">已归档</option>
                </select>
              </label>
            )}
            <details open={!!task}>
              <summary>约束、进度与接续信息</summary>
              {(
                [
                  { key: 'constraints', label: '约束' },
                  { key: 'progress', label: '当前进度' },
                  { key: 'decisions', label: '已确认结论' },
                  { key: 'unresolved', label: '未决事项' },
                  { key: 'artifacts', label: '成果与证据入口（用户记录）' }
                ] as const
              ).map(({ key, label }) => (
                <label key={key}>
                  {label}
                  <textarea
                    aria-label={label}
                    rows={2}
                    maxLength={16000}
                    value={fields[key] ?? ''}
                    onChange={(event) => setFields({ ...fields, [key]: event.target.value })}
                  />
                </label>
              ))}
            </details>
            {!task && <ModelPicker model={model} onChange={setModel} />}
            <button
              className="primary"
              disabled={busy || !connected || !project.available || !fields.goal.trim()}
            >
              {busy ? '正在保存…' : task ? '保存共享信息' : '创建任务与首会话'}
            </button>
          </form>
          {task && (
            <section className="task-session-create">
              <h2>任务会话</h2>
              <p className="muted">新会话会获得上面的已保存信息；其他会话完整历史尚不自动共享。</p>
              <button
                disabled={busy || !connected || !project.available}
                onClick={() => void createSession(true)}
              >
                打开 / 补齐首会话
              </button>
              <details>
                <summary>创建新的工作会话</summary>
                <ModelPicker model={model} onChange={setModel} />
                <label>
                  会话角色
                  <input
                    aria-label="会话角色"
                    value={role}
                    maxLength={4096}
                    onChange={(event) => setRole(event.target.value)}
                    placeholder="例如：实现、调研、Review"
                  />
                </label>
                <label>
                  工作范围
                  <textarea
                    aria-label="工作范围"
                    value={scope}
                    maxLength={16000}
                    onChange={(event) => setScope(event.target.value)}
                    placeholder="本次负责什么、涉及哪些文件或接口"
                  />
                </label>
                <button
                  className="primary"
                  disabled={busy || !connected || !project.available}
                  onClick={() => void createSession(false)}
                >
                  新建会话
                </button>
              </details>
            </section>
          )}
        </>
      )}
    </div>
  )
}

/** 模型选择只影响用户即将创建的会话。 Model choice affects only the next user-created session. */
function ModelPicker({ model, onChange }: { model: ModelId; onChange: (model: ModelId) => void }) {
  return (
    <label>
      新会话模型
      <select
        aria-label="新会话模型"
        value={model}
        onChange={(event) =>
          onChange(
            event.target.value === 'deepseek-v4.1-flash' ? 'deepseek-v4.1-flash' : 'glm-5.3-flash'
          )
        }
      >
        <option value="glm-5.3-flash">GLM-5.3-Flash</option>
        <option value="deepseek-v4.1-flash">DeepSeek V4.1 Flash</option>
      </select>
    </label>
  )
}
