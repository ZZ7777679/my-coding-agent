/** 左侧导航的身份信息和编辑入口。 Identity and editing actions for sidebar navigation. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type {
  NavigationItemName,
  ProjectSummary,
  SessionSummary,
  TaskSummary
} from '../../generated/protocol'
import type { WorkspaceSelection } from './TaskNavigation'
import './NavigationMenu.css'

export type NavigationTarget =
  | { kind: 'project'; project: ProjectSummary }
  | { kind: 'task'; project: ProjectSummary; task: TaskSummary }
  | { kind: 'session'; project: ProjectSummary; session: SessionSummary; taskName?: string }

export type NavigationPopup = {
  target: NavigationTarget
  x: number
  y: number
  anchor: HTMLElement
}

/** 使用身份而非标题寻址，同名项目或会话仍可区分。 Address by identity, allowing duplicate labels. */
function identity(target: NavigationTarget): NavigationItemName {
  if (target.kind === 'project')
    return { kind: target.kind, id: target.project.project_id, name: target.project.name }
  if (target.kind === 'task')
    return { kind: target.kind, id: target.task.task_id, name: target.task.title }
  return { kind: target.kind, id: target.session.session_id, name: target.session.title }
}

/** 将已有事实转换为可复制信息，不猜测缺失字段。 Format known facts without guessing missing data. */
function information(target: NavigationTarget): [string, string][] {
  const item = identity(target)
  const rows: [string, string][] = [
    ['名称', item.name],
    ['ID', item.id]
  ]
  const project = target.project
  if (target.kind !== 'project')
    rows.push(['所属项目', project.name], ['项目 ID', project.project_id])
  rows.push(['项目目录', project.path])
  if (target.kind === 'project') {
    rows.push(
      ['实际目录', project.canonical_path],
      [
        '目录状态',
        project.available ? '可用' : `不可用 · ${project.unavailable_code ?? '未知原因'}`
      ],
      ['最近打开', new Date(project.last_opened_at).toLocaleString()]
    )
  } else if (target.kind === 'task') {
    rows.push(['状态', taskStatus(target.task.status)], ['修订版本', String(target.task.revision)])
  } else {
    const s = target.session
    rows.push(
      ['所属任务', s.task_id ? (target.taskName ?? '名称待加载') : '未归属任务'],
      ['任务 ID', s.task_id ?? '无'],
      ['角色', s.role || '未设置'],
      ['工作范围', s.scope || '未设置'],
      ['模型', s.model_id],
      ['模式', s.mode === 'plan' ? 'Plan · 规划' : '常规'],
      ['最近运行', s.run ? `${s.run.status} · ${s.run.run_id}` : '尚无运行'],
      ['创建时间', new Date(s.created_at).toLocaleString()],
      ['更新时间', new Date(s.updated_at).toLocaleString()]
    )
    if (s.issue) rows.push(['记录提示', s.issue])
  }
  return rows
}

/** 统一任务状态文案。 Format task status consistently. */
function taskStatus(status: TaskSummary['status']): string {
  return status === 'completed' ? '已完成' : status === 'archived' ? '已归档' : '进行中'
}

/** 可关闭的右键菜单与信息／重命名对话框，不改变当前选择。 Dismissible menu and dialogs without changing selection. */
export function NavigationMenu({
  popup,
  connected,
  onClose,
  onSelect,
  onRenamed
}: {
  popup: NavigationPopup
  connected: boolean
  onClose: () => void
  onSelect: (selection: WorkspaceSelection) => void
  onRenamed: (item: NavigationItemName) => void
}) {
  const { target } = popup
  const item = identity(target)
  const label = { project: '项目', task: '任务', session: '会话' }[item.kind]
  const [mode, setMode] = useState<'menu' | 'info' | 'rename'>('menu')
  const [position, setPosition] = useState({ left: popup.x, top: popup.y })
  const [name, setName] = useState(item.name)
  const [rows, setRows] = useState(() => information(target))
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const menu = useRef<HTMLDivElement>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const mounted = useRef(true)
  const operation = useRef({ name: '', id: '' })
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLayoutEffect(() => {
    if (mode !== 'menu' || !menu.current) return
    const bounds = menu.current.getBoundingClientRect()
    setPosition({
      left: Math.max(8, Math.min(popup.x, window.innerWidth - bounds.width - 8)),
      top: Math.max(8, Math.min(popup.y, window.innerHeight - bounds.height - 8))
    })
    menu.current.querySelector<HTMLButtonElement>('button')?.focus()
  }, [mode, popup.x, popup.y])
  useEffect(() => {
    if (mode !== 'menu') dialog.current?.showModal()
  }, [mode])
  useEffect(() => {
    if (mode !== 'info') return
    let cancelled = false
    // 会话摘要已含自身信息，只补所属任务名称；任务详情按需读取。
    // Session summaries contain their own metadata; fetch task details only on demand.
    const taskId =
      target.kind === 'task'
        ? target.task.task_id
        : target.kind === 'session'
          ? target.session.task_id
          : null
    if (taskId) {
      void window.agent
        .getTask(taskId)
        .then((result) => {
          if (cancelled) return
          if (!result.ok) {
            setError(result.error.message)
            return
          }
          if (target.kind === 'session') {
            setRows(information({ ...target, taskName: result.data.fields.title }))
          } else {
            const task = result.data
            setRows([
              ...information({
                kind: 'task',
                project: target.project,
                task: {
                  task_id: task.task_id,
                  project_id: task.project_id,
                  title: task.fields.title,
                  status: task.fields.status ?? 'active',
                  revision: task.revision
                }
              }),
              ['阶段目标', task.fields.goal],
              ['创建时间', new Date(task.created_at).toLocaleString()],
              ['更新时间', new Date(task.updated_at).toLocaleString()]
            ])
          }
        })
        .catch(() => {
          if (!cancelled) setError('任务信息读取失败，可关闭后重新打开。')
        })
    }
    return () => {
      cancelled = true
    }
  }, [mode, target])

  /** 复制后显示真实反馈，失败时保留可选中的信息。 Report clipboard results and retain selectable text on failure. */
  const copy = async (text: string, description: string) => {
    try {
      await navigator.clipboard.writeText(text)
      if (mounted.current) {
        setError('')
        setNotice(`已复制${description}`)
      }
    } catch {
      if (mounted.current) setError('复制失败，请打开信息面板手动选择文字。')
    }
  }
  /** 名称独立保存，重复提交相同输入使用同一个操作身份。 Save labels independently with stable retry identity. */
  const save = async () => {
    const title = name.trim()
    if (busy || !title) return
    if (operation.current.name !== title)
      operation.current = { name: title, id: crypto.randomUUID() }
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.renameNavigation({
        ...item,
        name: title,
        operation_id: operation.current.id
      })
      if (!result.ok) {
        if (mounted.current) setError(result.error.message)
        return
      }
      onRenamed(result.data)
      if (mounted.current) onClose()
    } catch {
      if (mounted.current) setError('保存结果未确认，可保留名称重试或刷新列表查看。')
    } finally {
      if (mounted.current) setBusy(false)
    }
  }
  /** 沿用已有页面作为编辑入口，不新建会话。 Reuse existing editing pages without creating sessions. */
  const open = () => {
    onClose()
    onSelect({
      projectId: target.project.project_id,
      taskId:
        target.kind === 'task'
          ? target.task.task_id
          : target.kind === 'session'
            ? (target.session.task_id ?? null)
            : null,
      sessionId: target.kind === 'session' ? target.session.session_id : null,
      ...(target.kind === 'task' ? { editTaskRequest: crypto.randomUUID() } : {})
    })
  }
  /** 通过主进程打开已登记目录，renderer 不直接访问文件系统。 Open registered folders through the main process. */
  const openDirectory = async () => {
    setError('')
    try {
      const result = await window.agent.openProjectDirectory({
        project_id: target.project.project_id
      })
      if (!mounted.current) return
      if (result.ok) setNotice('已打开项目目录')
      else setError(result.error.message)
    } catch {
      if (mounted.current) setError('打开目录失败，请复制项目路径后手动打开。')
    }
  }
  const feedback = (
    <>
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </>
  )

  return createPortal(
    mode === 'menu' ? (
      <div
        className="navigation-menu-backdrop"
        onPointerDown={(event) => {
          if (event.target === event.currentTarget) onClose()
        }}
        onContextMenu={(event) => {
          event.preventDefault()
          if (event.target === event.currentTarget) onClose()
        }}
      >
        <div
          className="navigation-menu"
          ref={menu}
          style={position}
          role="menu"
          aria-label={`${label}操作`}
          onKeyDown={(event) => {
            if (event.key === 'Escape' || event.key === 'Tab') {
              onClose()
              return
            }
            if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return
            event.preventDefault()
            const buttons = Array.from(
              menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []
            )
            const current = buttons.findIndex((button) => button === document.activeElement)
            const index =
              event.key === 'Home'
                ? 0
                : event.key === 'End'
                  ? buttons.length - 1
                  : (current + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) %
                    buttons.length
            buttons[index]?.focus()
          }}
        >
          <strong>
            {label} · {item.name}
          </strong>
          <button
            role="menuitem"
            onClick={() => {
              setNotice('')
              setMode('info')
            }}
          >
            查看{label}信息
          </button>
          <button role="menuitem" onClick={() => void copy(item.id, `${label} ID`)}>
            复制 ID
          </button>
          <button
            role="menuitem"
            onClick={() => void copy(`${item.name}\n${item.id}`, '名称与 ID')}
          >
            复制名称与 ID
          </button>
          {target.kind === 'project' && (
            <>
              <button
                role="menuitem"
                disabled={!connected || !target.project.available}
                onClick={() => void openDirectory()}
              >
                在资源管理器中打开
              </button>
              <button role="menuitem" onClick={() => void copy(target.project.path, '项目路径')}>
                复制项目路径
              </button>
            </>
          )}
          <button
            role="menuitem"
            disabled={!connected}
            onClick={() => {
              setNotice('')
              setMode('rename')
            }}
          >
            重命名
          </button>
          {target.kind !== 'project' && (
            <button role="menuitem" disabled={!connected} onClick={open}>
              {target.kind === 'task' ? '编辑任务…' : '打开会话'}
            </button>
          )}
          {target.kind === 'session' && target.session.task_id && (
            <button
              role="menuitem"
              disabled={!connected}
              onClick={() => {
                onClose()
                onSelect({
                  projectId: target.project.project_id,
                  taskId: target.session.task_id ?? null,
                  sessionId: null
                })
              }}
            >
              打开所属任务
            </button>
          )}
          {feedback}
        </div>
      </div>
    ) : (
      <dialog
        className="navigation-dialog"
        ref={dialog}
        aria-label={mode === 'info' ? `${label}信息` : `重命名${label}`}
        onCancel={onClose}
        onClick={(event) => {
          if (event.target === event.currentTarget) onClose()
        }}
      >
        <div className="navigation-dialog-body">
          <header>
            <h2>{mode === 'info' ? `${label}信息` : `重命名${label}`}</h2>
            <button onClick={onClose}>关闭</button>
          </header>
          {mode === 'info' ? (
            <>
              <dl>
                {rows.map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              <footer>
                <button onClick={() => void copy(item.id, `${label} ID`)}>复制 ID</button>
                <button
                  onClick={() =>
                    void copy(rows.map(([key, value]) => `${key}：${value}`).join('\n'), '全部信息')
                  }
                >
                  复制全部信息
                </button>
                <button
                  disabled={!connected}
                  onClick={() => {
                    setNotice('')
                    setMode('rename')
                  }}
                >
                  重命名
                </button>
              </footer>
            </>
          ) : (
            <form
              onSubmit={(event) => {
                event.preventDefault()
                void save()
              }}
            >
              <label>
                {label}名称
                <input
                  autoFocus
                  value={name}
                  maxLength={256}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <p className="muted">
                {target.kind === 'project'
                  ? '只修改应用内显示名称，项目目录和 ID 保持不变。'
                  : '名称会保存到本地记录，ID 和已有内容保持不变。'}
              </p>
              <footer>
                <button type="button" onClick={onClose}>
                  取消
                </button>
                <button type="submit" disabled={busy || !connected || !name.trim()}>
                  {busy ? '保存中…' : '保存名称'}
                </button>
              </footer>
            </form>
          )}
          {feedback}
        </div>
      </dialog>
    ),
    document.body
  )
}
