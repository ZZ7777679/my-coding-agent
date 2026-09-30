/** 公开网站发现与快照安装。 Public skill discovery and snapshot installation. */
import { useEffect, useRef, useState } from 'react'
import defaults from '../../../../../src/my_agent/defaults.json'
import type { OnlineSkillDocument, OnlineSkillStatus } from '../../generated/protocol'
import type { Result } from '../../shared/api'

/** 通过短 RPC 展示可取消网络操作，正文按需读取。
 * Show cancellable network jobs through short RPCs and load details on demand.
 */
export function OnlineSkills({
  projectId,
  onInstalled,
  sourceRequest
}: {
  projectId: string | null
  onInstalled: () => void
  sourceRequest?: { id: string; url: string } | null
}) {
  const [state, setState] = useState<OnlineSkillStatus | null>(null)
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [ref, setRef] = useState('')
  const [directory, setDirectory] = useState('')
  const [timeout, setTimeoutSeconds] = useState<number>(defaults.skill_online.timeout_seconds)
  const [maxMb, setMaxMb] = useState<number>(defaults.skill_online.max_archive_mb)
  const [selected, setSelected] = useState('')
  const [document, setDocument] = useState<OnlineSkillDocument | null>(null)
  const [showPreview, setShowPreview] = useState(true)
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const epoch = useRef(0)
  const preferredName = useRef('')
  const notified = useRef('')
  const acceptedSource = useRef('')
  const installedCallback = useRef(onInstalled)
  installedCallback.current = onInstalled
  const preview = state?.preview
  const busy = sending || state?.status === 'running'

  useEffect(() => {
    if (!sourceRequest || sourceRequest.id === acceptedSource.current) return
    acceptedSource.current = sourceRequest.id
    setRef('')
    setDirectory('')
    setSource(sourceRequest.url)
    const url = new URL(sourceRequest.url)
    preferredName.current = ['skills.sh', 'www.skills.sh'].includes(url.hostname)
      ? (url.pathname.split('/').filter(Boolean).at(-1) ?? '')
      : ''
    void perform(() =>
      window.agent.inspectOnlineSkill({
        source: sourceRequest.url,
        timeout_seconds: timeout,
        max_archive_mb: maxMb
      })
    )
  }, [sourceRequest?.id])

  useEffect(() => {
    let disposed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const generation = epoch.current
    /** 保存当前页面的事实；完成只通知一次。 Accept current facts and notify once per installation. */
    async function poll() {
      try {
        const result = await window.agent.onlineSkillStatus()
        if (disposed || generation !== epoch.current) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        setState(result.data)
        if (result.data.status === 'installed' && notified.current !== result.data.operation_id) {
          notified.current = result.data.operation_id ?? ''
          installedCallback.current()
        }
        if (result.data.status === 'running') timer = setTimeout(() => void poll(), 600)
      } catch {
        if (!disposed && generation === epoch.current)
          setError('在线操作状态读取失败，可刷新状态。')
      }
    }
    void poll()
    return () => {
      disposed = true
      if (timer) clearTimeout(timer)
    }
  }, [refresh])

  useEffect(() => {
    if (!preview) {
      setDocument(null)
      return
    }
    setSelected(
      preview.skills.find((s) => s.name === preferredName.current)?.path ??
        preview.skills[0]?.path ??
        ''
    )
    setShowPreview(true)
  }, [preview?.preview_id])

  useEffect(() => {
    let disposed = false
    setDocument(null)
    if (!preview || !showPreview || !preview.skills.some((s) => s.path === selected)) return
    void window.agent
      .readOnlineSkill({ preview_id: preview.preview_id, path: selected })
      .then((result) => {
        if (disposed) return
        if (result.ok) setDocument(result.data)
        else setError(result.error.message)
      })
      .catch(() => {
        if (!disposed) setError('正文预览读取失败。')
      })
    return () => {
      disposed = true
    }
  }, [preview?.preview_id, selected, showPreview])

  useEffect(
    () => () => {
      ++epoch.current
    },
    []
  )

  /** 控制响应与状态轮询不能被旧请求覆盖。 Fence late polling and control responses. */
  async function perform(action: () => Promise<Result<OnlineSkillStatus>>) {
    const generation = ++epoch.current
    setSending(true)
    setError('')
    try {
      const result = await action()
      if (generation !== epoch.current) return
      if (result.ok) setState(result.data)
      else setError(result.error.message)
    } catch {
      if (generation === epoch.current) setError('操作未确认，请刷新状态查看实际结果。')
    } finally {
      if (generation === epoch.current) {
        setSending(false)
        setRefresh((old) => old + 1)
      }
    }
  }
  /** 链接或结果只触发预览，下载时不自动安装。 Sources trigger previews, not automatic installation. */
  function inspect(value: string, name = '') {
    preferredName.current = name
    setSource(value)
    // 搜索结果属于新来源，不沿用之前手填的分支和目录。
    // Search hits are new sources, so do not reuse stale manual overrides.
    if (name) {
      setRef('')
      setDirectory('')
    }
    void perform(() =>
      window.agent.inspectOnlineSkill({
        source: value,
        ref: name ? '' : ref,
        directory: name ? '' : directory,
        timeout_seconds: timeout,
        max_archive_mb: maxMb
      })
    )
  }
  /** 使用当前快照与明确目标保存。 Install the current snapshot into the explicit target. */
  function install(scope: 'user' | 'project') {
    if (!preview) return
    void perform(() =>
      window.agent.installOnlineSkill({
        preview_id: preview.preview_id,
        path: selected,
        scope,
        project_id: scope === 'project' ? projectId : null
      })
    )
  }
  return (
    <section className="detail-card settings-card online-skills" aria-label="Skill 在线发现">
      <h2>在线发现</h2>
      <p className="settings-hint">
        搜索 skills.sh，或从 SkillHub 详情、公开 GitHub 仓库导入。无需额外 API
        key；安装保留附属文件，下载时不运行脚本。
      </p>
      <form
        className="resource-search"
        onSubmit={(e) => {
          e.preventDefault()
          void perform(() =>
            window.agent.searchOnlineSkills({ query: query.trim(), timeout_seconds: timeout })
          )
        }}
      >
        <input
          aria-label="搜索 Skill"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索方法，例如 react、review、testing"
        />
        <button disabled={busy || !query.trim()} type="submit">
          搜索
        </button>
      </form>
      <div className="resource-search">
        <input
          aria-label="Skill 来源链接"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="SkillHub / GitHub / skills.sh 链接，或 owner/repo"
        />
        <button disabled={busy || !source.trim()} onClick={() => inspect(source)}>
          查看链接
        </button>
      </div>
      <details>
        <summary>下载与来源参数</summary>
        <div className="resource-options">
          <label>
            GitHub 分支 / SkillHub 版本（可选）
            <input
              value={ref}
              onChange={(e) => setRef(e.target.value)}
              placeholder="默认按链接、最新版本或 HEAD"
            />
          </label>
          <label>
            GitHub 仓库内目录（可选）
            <input
              value={directory}
              onChange={(e) => setDirectory(e.target.value)}
              placeholder="例如 skills/review"
            />
          </label>
          <label>
            网络操作超时（秒）
            <input
              type="number"
              min="1"
              value={timeout}
              onChange={(e) => setTimeoutSeconds(Number(e.target.value))}
            />
          </label>
          <label>
            下载上限（MiB）
            <input
              type="number"
              min="1"
              value={maxMb}
              onChange={(e) => setMaxMb(Number(e.target.value))}
            />
          </label>
        </div>
        <p className="settings-hint">
          带斜线的分支名请在此完整填写分支和目录。解压预算为下载上限的四倍。
        </p>
      </details>
      <div className="resource-item-heading">
        <span role={state?.status === 'failed' ? 'alert' : 'status'}>
          {state?.message || '尚未搜索；只在主动操作时访问网站。'}
        </span>
        {state?.status === 'running' && state.action !== 'install' && (
          <button
            disabled={sending}
            onClick={() =>
              void perform(() =>
                window.agent.cancelOnlineSkill({ operation_id: state.operation_id ?? '' })
              )
            }
          >
            取消
          </button>
        )}
        <button
          disabled={sending}
          onClick={() => {
            setError('')
            setRefresh((old) => old + 1)
          }}
        >
          刷新状态
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {state?.installed && (
        <p className="settings-hint">可切回「已安装」查看、编辑、启停或导入项目。</p>
      )}
      {preview && (
        <button onClick={() => setShowPreview((old) => !old)}>
          {showPreview ? '关闭预览' : '显示预览'}
        </button>
      )}
      {preview && showPreview && (
        <div className="online-preview">
          <h3>{preview.origin.repository}</h3>
          <p className="muted">
            来源版本 / 分支：{preview.origin.ref} · 下载于{' '}
            {new Date(preview.origin.downloaded_at).toLocaleString()}
          </p>
          {preview.origin.revision && (
            <details>
              <summary>来源版本</summary>
              <code>{preview.origin.revision}</code>
            </details>
          )}
          {preview.total > preview.skills.length && (
            <p>
              当前显示 {preview.skills.length} / {preview.total} 项，可填写仓库内目录缩小范围。
            </p>
          )}
          {(preview.issues ?? []).map((issue, i) => (
            <p role="alert" key={i}>
              {issue}
            </p>
          ))}
          {preview.skills.length === 0 ? (
            <p>当前来源 / 目录未发现有效 SKILL.md，可检查分支、目录或换一个来源。</p>
          ) : (
            <>
              <label>
                选择下载包中的 Skill
                <select value={selected} onChange={(e) => setSelected(e.target.value)}>
                  {preview.skills.map((s) => (
                    <option value={s.path} key={s.path}>
                      {s.name} · {s.path || '仓库根目录'}
                    </option>
                  ))}
                </select>
              </label>
              <p>{preview.skills.find((s) => s.path === selected)?.description}</p>
              <div className="resource-item-heading">
                <button disabled={busy} onClick={() => install('user')}>
                  安装到资源库
                </button>
                <button disabled={busy || !projectId} onClick={() => install('project')}>
                  导入当前项目
                </button>
              </div>
              {document ? (
                <>
                  <details open key={`${preview.preview_id}/${selected}`}>
                    <summary>SKILL.md 正文{document.truncated ? '（部分预览）' : ''}</summary>
                    <pre>{document.content}</pre>
                  </details>
                  <details>
                    <summary>附属文件与正文 · {document.file_count} 个文件</summary>
                    <ul>
                      {document.files.map((file) => (
                        <li key={file}>{file}</li>
                      ))}
                    </ul>
                    {document.files.length < document.file_count && (
                      <p>仅列出前 {document.files.length} 项；安装包含此目录全部文件。</p>
                    )}
                  </details>
                </>
              ) : (
                <p className="muted">正在读取正文…</p>
              )}
            </>
          )}
        </div>
      )}
      <div className="online-results">
        {state?.hits?.map((hit) => (
          <article className="skill-item" key={hit.url}>
            <div className="resource-item-heading">
              <button disabled={busy} onClick={() => inspect(hit.source, hit.name)}>
                {hit.name}
              </button>
              {hit.installs !== null && <small>{hit.installs?.toLocaleString()} 次安装</small>}
            </div>
            <p className="muted">{hit.source}</p>
            <button onClick={() => void window.agent.openWebUrl(hit.url)}>查看网站条目</button>
          </article>
        ))}
      </div>
    </section>
  )
}
