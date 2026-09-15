/**
 * 项目工作台与页面导航；所有业务状态来自受限 preload。
 * Project workspace and navigation; all business state comes through restricted preload.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import type {
  InitializeResult,
  OperationError,
  ProjectsView,
  PublicConfig
} from '../../generated/protocol'
import type { Result } from '../../shared/api'
import { Settings } from './Settings'
import './style.css'

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
  const [info, setInfo] = useState<InitializeResult | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [view, setView] = useState<'projects' | 'settings'>('projects')
  const generation = useRef(0)
  const occupied = useRef(false)
  const mounted = useRef(true)

  /**
   * 轮询最新状态；用代次标识防止旧响应覆盖新的选择。
   * Refresh current state, using generation tickets to prevent stale selection updates.
   */
  const refresh = useCallback(async () => {
    if (occupied.current) return
    const ticket = ++generation.current
    try {
      const result = await window.agent.getAppInfo()
      if (!mounted.current || ticket !== generation.current) return
      if (result.ok) {
        setInfo(result.data)
        setPhase('ready')
      } else {
        setPhase('error')
        setNotice(errorNotice(result.error))
      }
    } catch {
      if (mounted.current && ticket === generation.current) {
        setPhase('error')
        setNotice('桌面连接未能初始化，请重新打开应用。')
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void refresh()
    const timer = setInterval(() => void refresh(), 2500)
    return () => {
      mounted.current = false
      ++generation.current
      clearInterval(timer)
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
          if (projects !== null)
            setInfo((current) => (current ? { ...current, projects } : current))
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

  return (
    <div className="app">
      <aside className="sidebar">
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
          className={'nav-item ' + (view === 'settings' ? 'nav-current' : '')}
          onClick={() => setView('settings')}
        >
          <span className="settings-nav-icon" aria-hidden="true">
            ⚙
          </span>
          <span>设置与诊断</span>
        </button>
        <div className="section-label">
          最近打开<span>{info?.projects.recent_projects.length ?? 0}</span>
        </div>
        <nav className="recent-list" aria-label="最近项目">
          {info?.projects.recent_projects.map((item) => (
            <button
              key={item.project_id}
              className={
                'recent-project' + (project?.project_id === item.project_id ? ' selected' : '')
              }
              onClick={() => {
                setView('projects')
                void select(item.project_id)
              }}
              disabled={busy || !connected}
              title={item.path}
              aria-current={project?.project_id === item.project_id ? 'page' : undefined}
            >
              <FolderIcon size={19} />
              <span>
                <strong>{item.name}</strong>
                <small>{item.available ? item.path : '目录不可用'}</small>
              </span>
            </button>
          ))}
          {!info?.projects.recent_projects.length && (
            <p className="sidebar-empty">
              打开的项目会保存在这里，
              <br />
              下次可以直接继续。
            </p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <span className={'connection-dot ' + (connected ? 'online' : '')} />
          <span data-testid="connection-status">
            {phase === 'loading' ? '正在连接后端' : connected ? '本地后端已连接' : '后端不可用'}
          </span>
          <small>M0</small>
        </div>
      </aside>

      <main className="workspace">
        <header className="toolbar">
          <div>
            <span className="breadcrumb">工作台</span>
            <span className="separator">/</span>
            <strong>{view === 'projects' ? '项目' : '设置与诊断'}</strong>
          </div>
          <span className="local-badge">
            <span />
            本地工作空间
          </span>
        </header>
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
                    ? '凭据已检测，尚未验证调用'
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
                <p className="muted">项目记录与应用状态保存在这里。</p>
                <button
                  className="text-button"
                  onClick={() => void openData()}
                  disabled={!connected}
                >
                  打开数据文件夹 <span>↗</span>
                </button>
              </section>
            </div>
            <footer className="footer-note">
              <span>◎</span>
              <p>当前已支持项目选择与本地记录。后续阶段将接入对话、代码修改与验证。</p>
              <span className="version">v{info?.app.app_version ?? '—'}</span>
            </footer>
          </div>
        </div>
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
    <App />
  </React.StrictMode>
)
