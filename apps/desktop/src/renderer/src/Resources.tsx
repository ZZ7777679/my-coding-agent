/** 左侧入口共用项目与会话选择，不更改当前打开的项目。
 * Resource pages share target selection without reopening the working project.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ProjectSummary, SessionSummary } from '../../generated/protocol'
import { Skills } from './Skills'
import { Mcp } from './Mcp'
import type { WorkspaceSelection } from './TaskNavigation'

/** 管理资源库并明确选择导入目标；会话选择只改变引用和连接查看。
 * Manage the library with explicit import targets and optional session scope.
 */
export function Resources({
  kind,
  projects,
  selected,
  activeProjectId
}: {
  kind: 'skills' | 'mcp'
  projects: ProjectSummary[]
  selected: WorkspaceSelection | null
  activeProjectId: string | null
}) {
  const [projectId, setProjectId] = useState<string | null>(selected?.projectId ?? activeProjectId)
  return (
    <div className="content resource-page">
      <div className="page-heading">
        <div>
          <h1>{kind === 'skills' ? 'Skill 管理' : 'MCP 管理'}</h1>
          <p>
            {kind === 'skills'
              ? '管理可复用方法，按需要导入到项目。'
              : '登记工具服务，选择哪些项目可以使用。'}
          </p>
        </div>
      </div>
      <label className="resource-target">
        目标项目
        <select value={projectId ?? ''} onChange={(e) => setProjectId(e.target.value || null)}>
          <option value="">资源库（未选择项目）</option>
          {projects.map((project) => (
            <option key={project.project_id} value={project.project_id}>
              {project.name}
            </option>
          ))}
        </select>
      </label>
      <ResourceScope
        key={`${kind}/${projectId}`}
        kind={kind}
        projects={projects}
        projectId={projectId}
        initialSessionId={selected?.projectId === projectId ? selected.sessionId : null}
      />
    </div>
  )
}

/** 分页列出已有会话，不因管理资源自动创建会话。 Page existing sessions without creating any. */
function ResourceScope({
  kind,
  projectId,
  initialSessionId,
  projects
}: {
  kind: 'skills' | 'mcp'
  projectId: string | null
  initialSessionId: string | null
  projects: ProjectSummary[]
}) {
  const [sessionId, setSessionId] = useState(initialSessionId)
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const generation = useRef(0)
  /** 只接纳当前页面的列表响应。 Accept results only for the current mounted resource scope. */
  const load = useCallback(
    async (next: string | null) => {
      if (!projectId) return
      const ticket = ++generation.current
      setLoading(true)
      try {
        const result = await window.agent.listSessions({
          project_id: projectId,
          cursor: next,
          limit: 30
        })
        if (ticket !== generation.current) return
        if (result.ok) {
          setSessions((old) => (next ? [...old, ...result.data.sessions] : result.data.sessions))
          setCursor(result.data.next_cursor)
          setError(
            result.data.unavailable_count ? `${result.data.unavailable_count} 条会话记录不可读` : ''
          )
        } else setError(result.error.message)
      } catch {
        if (ticket === generation.current) setError('会话列表读取失败。')
      } finally {
        if (ticket === generation.current) setLoading(false)
      }
    },
    [projectId]
  )
  useEffect(() => {
    void load(null)
    return () => {
      ++generation.current
    }
  }, [load])
  return (
    <>
      {projectId && (
        <div className="resource-scope">
          <label>
            会话（可选）
            <select value={sessionId ?? ''} onChange={(e) => setSessionId(e.target.value || null)}>
              <option value="">仅管理项目资源</option>
              {sessionId && !sessions.some((s) => s.session_id === sessionId) && (
                <option value={sessionId}>当前选中会话</option>
              )}
              {sessions.map((s) => (
                <option key={s.session_id} value={s.session_id}>
                  {s.title}
                </option>
              ))}
            </select>
          </label>
          {cursor && (
            <button disabled={loading} onClick={() => void load(cursor)}>
              更多会话
            </button>
          )}
          {error && <p role="alert">{error}</p>}
        </div>
      )}
      {kind === 'skills' ? (
        <Skills key={sessionId} projectId={projectId} sessionId={sessionId} />
      ) : (
        <Mcp
          key={`${projectId}:${sessionId}`}
          projectId={projectId}
          sessionId={sessionId}
          projects={projects}
        />
      )}
    </>
  )
}
