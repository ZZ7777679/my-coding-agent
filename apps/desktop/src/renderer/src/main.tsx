/**
 * 项目工作台与页面导航；所有业务状态来自受限 preload。
 * Project workspace and navigation; all business state comes through restricted preload.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import type {
  InitializeResult,
  NavigationItemName,
  OperationError,
  ProjectsView,
  PublicConfig,
  SessionSummary
} from '../../generated/protocol'
import type { Result } from '../../shared/api'
import { Settings } from './Settings'
import { Chat } from './Chat'
import { CodeWorkbench } from './CodeWorkbench'
import type { KnowledgeUi } from './ContextMemory'
import type { QuestionMaterial } from './KnowledgeDetails'
import { TaskNavigation, type WorkspaceSelection } from './TaskNavigation'
import { TaskPanel } from './TaskPanel'
import { ProgramCards } from './ProgramCards'
import { Resources } from './Resources'
import { Workflows } from './Workflows'
import { WorkStyles } from './WorkStyles'
import { FailureNotice } from './FailureNotice'
import { AppearanceProvider, SidebarResize, useAppearance } from './Appearance'
import defaults from '../../../../../src/my_agent/defaults.json'
import { Evolution } from './Evolution'
import { EvolutionQuick, type EvolutionEntry } from './EvolutionQuick'
import type { EvolutionDraftCache } from './EvolutionDrafts'
import './style.css'
import './appearance.css'

/**
 * 合并后端公开错误和修复说明，保留可操作的信息。
 * Combine the public error and remediation into actionable feedback.
 */
function errorNotice(error: OperationError): string {
  return [error.message, error.remediation].filter(Boolean).join(' ')
}

/**
 * 绘制装饰性文件夹图标，避免影响按钮的可访问名称。
 * Render a decorative folder icon without altering accessible button names.
 */
function FolderIcon({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3V7Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M3 10h18" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

/**
 * 展示项目与设置状态，统一互斥操作并丢弃过期异步响应。
 * Display project and settings state, serialize actions and discard stale async responses.
 */
function App() {
  const appearance = useAppearance()
  const evolutionDraftCache = useRef<EvolutionDraftCache>(new Map())
  const [evolutionEntry, setEvolutionEntry] = useState<EvolutionEntry | null>(null)
  /** 将现场范围或现有作业带到同一改进页。 Carry a contextual scope or job into the shared page. */
  function openEvolution(entry: EvolutionEntry) {
    setEvolutionEntry(entry)
    setView('evolution')
  }
  const knowledgeCache = useRef(new Map<string, KnowledgeUi>())
  const materialCache = useRef(new Map<string, QuestionMaterial[]>())
  const [info, setInfo] = useState<InitializeResult | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [connectionError, setConnectionError] = useState<OperationError | null>(null)
  const reconnectAttempts = useRef(0)
  const [recoveryPaused, setRecoveryPaused] = useState(false)
  const pauseRecovery = useRef(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [view, setView] = useState<
    'projects' | 'settings' | 'chat' | 'task' | 'skills' | 'mcp' | 'workflows' | 'evolution'
  >('projects')
  const [workbenchOpen, setWorkbenchOpen] = useState(false)
  const [workbenchVisited, setWorkbenchVisited] = useState(false)
  const [selection, setSelection] = useState<WorkspaceSelection | null>(null)
  const [treeRevision, setTreeRevision] = useState(0)
  const [renamedItem, setRenamedItem] = useState<NavigationItemName | null>(null)
  const [activeRuns, setActiveRuns] = useState<SessionSummary[]>([])
  const runGeneration = useRef(0)
  const generation = useRef(0)
  const occupied = useRef(false)
  const infoPending = useRef(false)
  const runsPending = useRef(false)
  const mounted = useRef(true)

  /**
   * 轮询最新状态；用代次标识防止旧响应覆盖新的选择。
   * Refresh current state, using generation tickets to prevent stale selection updates.
   */
  const refresh = useCallback(async () => {
    if (occupied.current || infoPending.current) return
    infoPending.current = true
    const ticket = ++generation.current
    try {
      const result = await window.agent.getAppInfo()
      if (!mounted.current || ticket !== generation.current) return
      if (result.ok) {
        setInfo(result.data)
        setPhase('ready')
        reconnectAttempts.current = 0
        setConnectionError(null)
        pauseRecovery.current = false
        setRecoveryPaused(false)
      } else {
        setPhase('error')
        reconnectAttempts.current += 1
        setConnectionError(result.error)
        if (reconnectAttempts.current >= defaults.desktop_connection.auto_reconnect_attempts) {
          pauseRecovery.current = true
          setRecoveryPaused(true)
        }
      }
    } catch {
      if (mounted.current && ticket === generation.current) {
        setPhase('error')
        reconnectAttempts.current += 1
        setConnectionError({
          code: 'DESKTOP_CONNECTION',
          message: '桌面连接暂不可用。',
          remediation: '正在尝试恢复读取连接，输入和当前选择会保留。'
        })
        if (reconnectAttempts.current >= defaults.desktop_connection.auto_reconnect_attempts) {
          pauseRecovery.current = true
          setRecoveryPaused(true)
        }
      }
    } finally {
      infoPending.current = false
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let cancelled = false
    /** 等上次读取完成后再安排下一次，失败按退避重连；不触发模型或工具。
     * Schedule after the previous read settles, backing off failures without dispatching work. */
    async function poll() {
      if (!pauseRecovery.current) await refresh()
      if (!cancelled)
        timer = setTimeout(
          () => void poll(),
          Math.min(
            defaults.desktop_connection.reconnect_max_delay_ms,
            reconnectAttempts.current
              ? defaults.desktop_connection.refresh_ms * 2 ** Math.min(reconnectAttempts.current, 8)
              : defaults.desktop_connection.idle_refresh_ms
          )
        )
    }
    void poll()
    return () => {
      mounted.current = false
      ++generation.current
      cancelled = true
      clearTimeout(timer)
    }
  }, [refresh])

  /**
   * 打开已有或新选项目；取消和错误不覆盖原来的选择。
   * Open a recent or newly selected project, preserving selection on cancel or failure.
   */
  const select = useCallback(
    async (projectId?: string) => {
      if (occupied.current || phase !== 'ready') return
      occupied.current = true
      const ticket = ++generation.current
      setBusy(true)
      setNotice('')
      try {
        const result: Result<ProjectsView | null> = projectId
          ? await window.agent.openRecentProject(projectId)
          : await window.agent.chooseProject()
        if (!mounted.current || ticket !== generation.current) return
        if (result.ok) {
          const projects = result.data
          if (projects !== null) {
            setInfo((current) => (current ? { ...current, projects } : current))
            setSelection((current) =>
              current?.projectId === projects.active_project?.project_id ? current : null
            )
            return true
          }
        } else {
          setNotice(errorNotice(result.error))
        }
      } catch {
        if (mounted.current) setNotice('操作未完成，原来的项目选择已保留。')
      } finally {
        occupied.current = false
        if (mounted.current) setBusy(false)
      }
    },
    [phase]
  )

  /** 项目打开确认后才切换任务 / 会话，失败保留原选择。 Navigate only after project selection is confirmed. */
  const navigate = useCallback(
    async (next: WorkspaceSelection) => {
      if (
        info?.projects.active_project?.project_id !== next.projectId &&
        !(await select(next.projectId))
      )
        return
      setSelection(next)
      setView(next.sessionId ? 'chat' : 'task')
    },
    [info?.projects.active_project?.project_id, select]
  )

  /** 刷新树的数据版本，不发模型请求。 Invalidate navigation data without model calls. */
  const refreshTree = useCallback(() => setTreeRevision((value) => value + 1), [])

  /**
   * 请求打开实际数据文件夹，并显示受信入口返回的错误。
   * Request the effective data folder and display trusted-entry errors.
   */
  const openData = async () => {
    try {
      const result = await window.agent.openDataDirectory()
      if (!result.ok) setNotice(errorNotice(result.error))
    } catch {
      setNotice('无法打开数据文件夹。')
    }
  }

  /**
   * 设置操作占用期间暂停项目轮询，并使此前的刷新结果失效。
   * Pause project polling during settings work and invalidate earlier refresh results.
   */
  const settingsBusy = useCallback((value: boolean) => {
    occupied.current = value
    ++generation.current
    setBusy(value)
  }, [])
  /**
   * 将已保存的后端配置合入页面状态，不自行生成配置事实。
   * Merge saved backend settings into page state without inventing configuration values.
   */
  const updateConfig = useCallback((config: PublicConfig) => {
    setInfo((current) => (current ? { ...current, config } : current))
  }, [])

  const project = info?.projects.active_project
  const connected = phase === 'ready'
  const modelName =
    info?.config.model_id === 'deepseek-v4.1-flash' ? 'DeepSeek V4.1 Flash' : 'GLM-5.3-Flash'
  const credential = info?.config.credential

  /** 显示所有会话的运行，丢弃过期刷新。 Display all session runs and discard stale refreshes. */
  const refreshRun = useCallback(async () => {
    if (runsPending.current) return
    runsPending.current = true
    const ticket = ++runGeneration.current
    try {
      const result = await window.agent.getActiveRuns()
      if (mounted.current && ticket === runGeneration.current) {
        if (result.ok) setActiveRuns(result.data.sessions)
        else setNotice(errorNotice(result.error))
      }
    } catch {
      if (mounted.current && ticket === runGeneration.current)
        setNotice('无法刷新运行状态，请检查后端连接。')
    } finally {
      runsPending.current = false
    }
  }, [])
  useEffect(() => {
    if (!connected) return
    void refreshRun()
    const timer = setInterval(
      () => {
        if (!document.hidden) void refreshRun()
      },
      activeRuns.length
        ? defaults.desktop_connection.refresh_ms
        : defaults.desktop_connection.idle_refresh_ms
    )
    return () => clearInterval(timer)
  }, [connected, refreshRun, activeRuns.length])
  const runningRevision = activeRuns
    .map((item) => `${item.run?.run_id}:${item.run?.status}`)
    .join('|')
  useEffect(() => {
    refreshTree()
  }, [runningRevision, refreshTree])

  /** 停止按钮只确认请求，保持 stopping 直到后端退出任务。 Keep stopping until backend cleanup ends. */
  const stopRun = async (runId: string) => {
    try {
      const result = await window.agent.cancelRun(runId)
      if (result.ok) {
        setActiveRuns((current) =>
          current.map((item) => (item.run?.run_id === runId ? result.data : item))
        )
        await refreshRun()
      } else setNotice(errorNotice(result.error))
    } catch {
      setNotice('停止请求未确认，请检查连接。')
    }
  }

  return (
    <div className={'app' + (appearance.value.sidebar_collapsed ? ' sidebar-collapsed' : '')}>
      <aside className="sidebar">
        <button
          className="sidebar-toggle"
          aria-label={appearance.value.sidebar_collapsed ? '展开侧栏' : '收起侧栏'}
          disabled={!appearance.ready}
          onClick={() =>
            void appearance.save({
              ...appearance.value,
              sidebar_collapsed: !appearance.value.sidebar_collapsed
            })
          }
        >
          {appearance.value.sidebar_collapsed ? '☰' : '‹'}
        </button>
        <div className="brand">
          <div className="brand-mark">
            m<span>_</span>
          </div>
          <div>
            <strong>My Coding Agent</strong>
            <small>你的本地开发空间</small>
          </div>
        </div>
        <button
          className={'nav-item ' + (view === 'projects' ? 'nav-current' : '')}
          onClick={() => setView('projects')}
        >
          <FolderIcon size={18} />
          <span>项目工作台</span>
          <span className="nav-dot" />
        </button>
        <button
          className={'nav-item ' + (view === 'chat' && workbenchOpen ? 'nav-current' : '')}
          disabled={!project}
          aria-expanded={view === 'chat' && workbenchOpen}
          onClick={() => {
            setWorkbenchVisited(true)
            setWorkbenchOpen(view !== 'chat' || !workbenchOpen)
            setView('chat')
          }}
        >
          <span aria-hidden="true">⌨</span>
          <span>项目文件</span>
        </button>
        <button
          className={'nav-item ' + (view === 'settings' ? 'nav-current' : '')}
          onClick={() => setView('settings')}
        >
          <span className="settings-nav-icon" aria-hidden="true">
            ⚙
          </span>
          <span>设置与诊断</span>
        </button>
        <button
          className={'nav-item ' + (view === 'skills' ? 'nav-current' : '')}
          onClick={() => setView('skills')}
        >
          <span aria-hidden="true">◇</span>
          <span>Skill 管理</span>
        </button>
        <button
          className={'nav-item ' + (view === 'mcp' ? 'nav-current' : '')}
          onClick={() => setView('mcp')}
        >
          <span aria-hidden="true">⌘</span>
          <span>MCP 管理</span>
        </button>
        <button
          className={'nav-item ' + (view === 'workflows' ? 'nav-current' : '')}
          onClick={() => setView('workflows')}
        >
          <span aria-hidden="true">⇢</span>
          <span>工作流管理</span>
        </button>
        <button
          className={'nav-item ' + (view === 'evolution' ? 'nav-current' : '')}
          onClick={() => {
            setEvolutionEntry(null)
            setView('evolution')
          }}
        >
          <span aria-hidden="true">↗</span>
          <span>经验与改进</span>
        </button>
        <div className="section-label">
          项目与任务<span>{info?.projects.recent_projects.length ?? 0}</span>
        </div>
        <TaskNavigation
          projects={info?.projects.recent_projects ?? []}
          selected={selection}
          revision={treeRevision}
          connected={connected && !busy}
          onSelect={(next) => void navigate(next)}
          onRenamed={(item) => {
            setRenamedItem(item)
            refreshTree()
            void refresh()
          }}
        />
        <div className="sidebar-bottom">
          <span className={'connection-dot ' + (connected ? 'online' : '')} />
          <span data-testid="connection-status">
            {phase === 'loading' ? '正在连接后端' : connected ? '本地后端已连接' : '连接恢复中'}
          </span>
          <small>{info?.app.stage ?? defaults.stage}</small>
        </div>
      </aside>
      <SidebarResize />

      <main className={'workspace' + (view === 'chat' ? ' workspace-chat' : '')}>
        {connectionError && (
          <FailureNotice error={connectionError}>
            <button
              type="button"
              onClick={() => {
                reconnectAttempts.current = 0
                pauseRecovery.current = false
                setRecoveryPaused(false)
                void refresh()
              }}
            >
              立即重新读取
            </button>
            <button
              type="button"
              onClick={() => {
                pauseRecovery.current = !pauseRecovery.current
                setRecoveryPaused(pauseRecovery.current)
                reconnectAttempts.current = 0
                if (!pauseRecovery.current) void refresh()
              }}
            >
              {recoveryPaused ? '恢复自动重连' : '暂停自动重连'}
            </button>
            {recoveryPaused && <span>自动恢复已暂停，当前输入和项目选择保留。</span>}
            <button type="button" onClick={() => setView('settings')}>
              打开诊断
            </button>
          </FailureNotice>
        )}
        {view !== 'chat' && (
          <header className="toolbar">
            <div>
              <span className="breadcrumb">工作台</span>
              <span className="separator">/</span>
              <strong>
                {view === 'projects'
                  ? '项目'
                  : view === 'task'
                    ? '任务'
                    : view === 'skills'
                      ? 'Skill 管理'
                      : view === 'mcp'
                        ? 'MCP 管理'
                        : view === 'workflows'
                          ? '工作流管理'
                          : view === 'evolution'
                            ? '经验与改进'
                            : '设置与诊断'}
              </strong>
            </div>
            {
              <span className="local-badge">
                <span />
                本地工作空间
              </span>
            }
          </header>
        )}
        <div hidden={view !== 'projects'}>
          <div className="content">
            <div className="page-heading">
              <div>
                <div className="eyebrow">WORKSPACE</div>
                <h1>{project ? '继续你的项目' : '从一个项目开始'}</h1>
                <p>选择代码所在的文件夹，建立属于你的开发工作空间。</p>
              </div>
              <button
                className="primary"
                onClick={() => void select()}
                disabled={busy || !connected}
              >
                <span className="plus">+</span>
                {busy ? '正在打开…' : '选择项目文件夹'}
              </button>
            </div>
            {notice && (
              <div className="notice" role="alert">
                <span>!</span>
                <p>{notice}</p>
              </div>
            )}
            {phase === 'loading' && (
              <div className="loading-line">
                <i />
                正在准备本地工作空间…
              </div>
            )}

            <section className={'project-panel ' + (project ? '' : 'empty')}>
              <div className="panel-label">
                <span className="line" />
                当前项目
              </div>
              {project ? (
                <div className="active-project">
                  <div className="folder-tile">
                    <FolderIcon size={34} />
                  </div>
                  <div className="project-details">
                    <div className="project-title">
                      <h2 data-testid="active-project-name">{project.name}</h2>
                      <span className={project.available ? 'tag' : 'tag unavailable'}>
                        {project.available ? '已打开' : '目录不可用'}
                      </span>
                    </div>
                    <p className="path" title={project.path} data-testid="active-project-path">
                      {project.path}
                    </p>
                    <p className="project-note">
                      {project.available
                        ? '项目选择已保存。重新打开应用时，会恢复到这里。'
                        : '原来的记录已保留。请连接磁盘，或重新选择项目目录。'}
                    </p>
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() => {
                        void (async () => {
                          const choice = await window.agent.chooseStartupDirectory({
                            kind: 'project'
                          })
                          if (!choice.ok) {
                            setNotice(errorNotice(choice.error))
                            return
                          }
                          if (!choice.data.path) return
                          const result = await window.agent.relocateProject({
                            project_id: project.project_id,
                            path: choice.data.path
                          })
                          if (result.ok) {
                            setInfo((current) =>
                              current ? { ...current, projects: result.data } : current
                            )
                            setTreeRevision((value) => value + 1)
                          } else setNotice(errorNotice(result.error))
                        })()
                      }}
                    >
                      重新定位目录（保留任务与记忆）
                    </button>
                    <button
                      className="text-button"
                      onClick={() =>
                        void navigate({
                          projectId: project.project_id,
                          taskId: null,
                          sessionId: null
                        })
                      }
                    >
                      新建任务 →
                    </button>
                  </div>
                </div>
              ) : (
                <div className="empty-content">
                  <div className="empty-art">
                    <div className="art-back" />
                    <div className="art-folder">
                      <FolderIcon size={48} />
                    </div>
                    <span className="art-plus">+</span>
                  </div>
                  <h2>还没有打开项目</h2>
                  <p>
                    普通文件夹或 Git 仓库都可以。
                    <br />
                    打开后，你的项目会显示在这里。
                  </p>
                  <button
                    className="text-button"
                    onClick={() => void select()}
                    disabled={busy || !connected}
                  >
                    浏览文件夹 <span>↗</span>
                  </button>
                </div>
              )}
            </section>

            {view === 'projects' && project && (
              <EvolutionQuick
                key={`review-project-${project.project_id}`}
                projectId={project.project_id}
                origin={{ kind: 'project', identity: project.project_id }}
                onOpen={openEvolution}
              />
            )}
            <div className="details-grid">
              <section className="detail-card">
                <div className="card-heading">
                  <span className="small-symbol">◇</span>
                  <h3>模型配置</h3>
                  <span className="subtle-tag">默认服务</span>
                </div>
                <div className="model-name">{info ? modelName : '等待连接'}</div>
                <p className="muted">OpenCode Go</p>
                <div className="credential-status">
                  <span className={credential?.present ? 'tiny-dot present' : 'tiny-dot'} />
                  {credential?.present
                    ? '凭据已检测，调用结果以当前运行为准'
                    : credential?.source === 'restricted'
                      ? '凭据读取受限'
                      : '未检测到模型凭据'}
                </div>
              </section>
              <section className="detail-card storage-card">
                <div className="card-heading">
                  <span className="small-symbol">▤</span>
                  <h3>应用数据</h3>
                </div>
                <code data-testid="data-dir">
                  {info?.storage.data_dir ?? '等待后端确认保存位置'}
                </code>
                <p className="muted">项目记录、会话历史与应用状态保存在这里。</p>
                <button
                  className="text-button"
                  onClick={() => void openData()}
                  disabled={!connected}
                >
                  打开数据文件夹 <span>↗</span>
                </button>
              </section>
            </div>
            {project && (
              <ProgramCards
                key={project.project_id}
                projectId={project.project_id}
                visible={view === 'projects'}
              />
            )}
            <footer className="footer-note">
              <span>◎</span>
              <p>
                任务与会话在左侧管理。可在原项目编辑并直接使用本机工具；需要特定环境时再到设置中选择。
              </p>
              <span className="version">v{info?.app.app_version ?? '—'}</span>
            </footer>
          </div>
        </div>
        <div
          className={'chat-page' + (workbenchOpen ? ' with-workbench' : '')}
          hidden={view !== 'chat'}
        >
          <div className="conversation-pane">
            <Chat
              onSettings={() => setView('settings')}
              onReview={openEvolution}
              review={
                view === 'chat' &&
                project &&
                selection?.sessionId && (
                  <EvolutionQuick
                    key={selection.sessionId}
                    projectId={project.project_id}
                    origin={{ kind: 'session', identity: selection.sessionId }}
                    onOpen={openEvolution}
                  />
                )
              }
              knowledgeCache={knowledgeCache.current}
              materialCache={materialCache.current}
              visible={view === 'chat'}
              key={selection?.sessionId ?? 'empty'}
              project={project ?? null}
              selected={selection?.sessionId ?? null}
              connected={connected}
              active={activeRuns.find((item) => item.session_id === selection?.sessionId) ?? null}
              onStop={(id) => void stopRun(id)}
              onRunChange={() => {
                void refreshRun()
                refreshTree()
              }}
              onSelect={(next) => void navigate(next)}
            />
          </div>
          <div className="workbench-page" hidden={!workbenchOpen}>
            {project && workbenchVisited && (
              <CodeWorkbench
                key={project.project_id + '/' + (selection?.sessionId ?? '')}
                projectId={project.project_id}
                sessionId={selection?.sessionId ?? null}
                visible={view === 'chat' && workbenchOpen}
                onChat={() => setWorkbenchOpen(false)}
              />
            )}
          </div>
        </div>
        {view === 'task' && (
          <>
            {project && selection?.taskId && (
              <EvolutionQuick
                key={selection.taskId}
                projectId={project.project_id}
                origin={{ kind: 'task', identity: selection.taskId }}
                onOpen={openEvolution}
              />
            )}
            <TaskPanel
              key={`${project?.project_id}/${selection?.taskId}`}
              project={project ?? null}
              taskId={selection?.taskId ?? null}
              defaultModel={info?.config.model_id ?? 'glm-5.3-flash'}
              connected={connected}
              onSelect={(next) => void navigate(next)}
              onChanged={refreshTree}
              renamedItem={renamedItem}
              editRequest={selection?.editTaskRequest}
              designRequest={selection?.designRequest}
            />
          </>
        )}
        {(view === 'skills' || view === 'mcp') && (
          <Resources
            key={view}
            kind={view}
            projects={info?.projects.recent_projects ?? []}
            selected={selection}
            activeProjectId={project?.project_id ?? null}
          />
        )}
        {view === 'workflows' && (
          <section className="content" aria-label="工作流管理">
            <h1>开发工作流</h1>
            <p className="muted">
              在这里查看、复制和编辑开发方法；新建任务时选择，已有任务可在「任务流程」中套用。
              个人流程仍是默认，开源方法均为本应用适配版。
            </p>
            <Workflows initiallyOpen />
            <WorkStyles key={project?.project_id ?? 'global'} projectId={project?.project_id} />
          </section>
        )}
        {view === 'evolution' &&
          (project ? (
            <Evolution
              key={project.project_id + JSON.stringify(evolutionEntry)}
              projectId={project.project_id}
              projectName={project.name}
              draftCache={evolutionDraftCache.current}
              entry={evolutionEntry}
            />
          ) : (
            <section className="content">
              <h1>经验与改进</h1>
              <p>先选择要改进的项目，再描述问题并点击“开始改进”。</p>
              <button onClick={() => setView('projects')}>选择项目</button>
            </section>
          ))}
        <div hidden={view !== 'settings'}>
          <Settings
            info={info}
            connected={connected}
            busy={busy}
            onBusy={settingsBusy}
            onConfig={updateConfig}
          />
        </div>
      </main>
    </div>
  )
}

const container = document.getElementById('root')
if (!container) throw new Error('Missing application container')
createRoot(container).render(
  <React.StrictMode>
    <AppearanceProvider>
      <App />
    </AppearanceProvider>
  </React.StrictMode>
)
