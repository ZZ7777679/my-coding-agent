/** 本地 Git 双区状态、显式索引操作和历史。 Local Git worktree/index operations and history. */
import { useEffect, useRef, useState } from 'react'
import type {
  GitDiff,
  GitFileStatus,
  GitHistory,
  GitPathsParams,
  GitStatus,
  GitSettings
} from '../../generated/protocol'
import './LocalGitPanel.css'

/** 当前项目状态与差异，初始化/提交仅由实际按钮触发。 Project facts with explicit init/commit actions. */
export function LocalGitPanel({
  projectId,
  visible = true,
  onClose
}: {
  projectId: string
  visible?: boolean
  onClose?: () => void
}): React.JSX.Element {
  const [status, setStatus] = useState<GitStatus | null>(null)
  const [settings, setSettings] = useState<GitSettings | null>(null)
  const [diff, setDiff] = useState<GitDiff | null>(null)
  const [history, setHistory] = useState<GitHistory | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(true)
  const [message, setMessage] = useState('')
  const [revision, setRevision] = useState(0)
  const [selected, setSelected] = useState<string[]>([])
  const [tab, setTab] = useState<'worktree' | 'index'>('worktree')
  const generation = useRef(0)
  const diffRequest = useRef(0)
  const files =
    status?.files.filter((file) =>
      tab === 'worktree'
        ? file.worktree_status !== ' '
        : file.index_status !== ' ' && file.index_status !== '?'
    ) ?? []

  useEffect(() => {
    setStatus(null)
    setSettings(null)
    setDiff(null)
    setHistory(null)
    setSelected([])
    setMessage('')
  }, [projectId])

  useEffect(() => {
    if (!visible || !open) return
    const epoch = ++generation.current
    setLoading(true)
    /** 只刷新用户当前项目，输出按后端事实显示。 Refresh only the user's selected project. */
    async function load(): Promise<void> {
      try {
        const [response, preference] = await Promise.all([
          window.agent.getGitStatus({ project_id: projectId }),
          window.agent.getGitSettings({ project_id: projectId })
        ])
        if (epoch !== generation.current) return
        if (response.ok) {
          setStatus(response.data)
          setError(preference.ok ? '' : preference.error.message)
          setSelected([])
        } else setError(response.error.message)
        if (preference.ok) setSettings(preference.data)
      } catch {
        if (epoch === generation.current) setError('本地 Git 状态读取失败。')
      } finally {
        if (epoch === generation.current) setLoading(false)
      }
    }
    void load()
    return () => {
      generation.current++
      diffRequest.current++
    }
  }, [projectId, revision, visible, open])

  /** 修改索引仅包括明确勾选路径，保存失败不显示成功。 Modify only explicitly selected index paths. */
  async function changeIndex(action: 'stage' | 'unstage', paths: string[]): Promise<void> {
    const [first, ...rest] = paths
    if (first === undefined) return
    const epoch = generation.current
    setBusy(true)
    setError('')
    try {
      const params: GitPathsParams = { project_id: projectId, paths: [first, ...rest] }
      const response =
        action === 'stage'
          ? await window.agent.stageGitPaths(params)
          : await window.agent.unstageGitPaths(params)
      if (epoch !== generation.current) return
      if (response.ok) {
        setStatus(response.data)
        setSelected([])
        setDiff(null)
      } else setError(response.error.message)
    } catch {
      if (epoch === generation.current) setError('Git 暂存区操作未完成，请刷新状态。')
    } finally {
      setBusy(false)
    }
  }

  /** 请求身份排除快速切换路径的迟到差异。 Ignore stale diffs after fast path selection. */
  async function readDiff(file: GitFileStatus): Promise<void> {
    const request = ++diffRequest.current
    const epoch = generation.current
    setError('')
    try {
      const response = await window.agent.getGitDiff({
        project_id: projectId,
        path: file.path,
        area: tab
      })
      if (epoch !== generation.current || request !== diffRequest.current) return
      if (response.ok) setDiff(response.data)
      else setError(response.error.message)
    } catch {
      if (epoch === generation.current && request === diffRequest.current)
        setError('文件差异无法读取。')
    }
  }

  /** 用户明确选择初始化或提交，身份缺失交给 Git 真实说明。 Explicit init/commit without identity setup. */
  async function repositoryAction(action: 'init' | 'commit' | 'history'): Promise<void> {
    const epoch = generation.current
    setBusy(true)
    setError('')
    try {
      if (action === 'init') {
        const response = await window.agent.initGitRepository({ project_id: projectId })
        if (epoch !== generation.current) return
        if (response.ok) {
          setStatus(response.data)
          setDiff(null)
        } else setError(response.error.message)
      } else if (action === 'history') {
        const response = await window.agent.getGitHistory({ project_id: projectId })
        if (epoch !== generation.current) return
        if (response.ok) setHistory(response.data)
        else setError(response.error.message)
      } else {
        const response = await window.agent.commitGit({ project_id: projectId, message })
        if (epoch !== generation.current) return
        if (response.ok) {
          setMessage('')
          setDiff(null)
          setHistory(null)
          setRevision((value) => value + 1)
        } else setError(response.error.message)
      }
    } catch {
      if (epoch === generation.current) setError('本地 Git 操作未完成，未自动重试。')
    } finally {
      setBusy(false)
    }
  }

  /** 关闭保留备份；发生部分移动失败后刷新真实状态。 Preserve backups and refresh facts after move errors. */
  async function toggleGit(): Promise<void> {
    if (!settings) return
    const epoch = generation.current
    setBusy(true)
    setError('')
    setStatus(null)
    diffRequest.current++
    try {
      const response = await window.agent.configureGit({
        project_id: projectId,
        enabled: !settings.enabled
      })
      if (epoch !== generation.current) return
      if (!response.ok) setError(response.error.message)
      const [actual, current] = await Promise.all([
        window.agent.getGitSettings({ project_id: projectId }),
        window.agent.getGitStatus({ project_id: projectId })
      ])
      if (epoch !== generation.current) return
      if (actual.ok) setSettings(actual.data)
      if (current.ok) setStatus(current.data)
      setDiff(null)
      setHistory(null)
      setSelected([])
    } catch {
      if (epoch === generation.current) setError('Git 开关操作未完成，请刷新查看元数据和备份状态。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <details
      className="local-git-panel"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>本地 Git{status?.branch && ` · ${status.branch}`}</summary>
      {onClose && (
        <button className="local-git-hide" onClick={onClose}>
          关闭面板
        </button>
      )}
      <p className="settings-hint">工作区与暂存区、本地提交和历史；无需 remote 或账号登录。</p>
      {settings && (
        <div className="local-git-switch">
          <strong>项目 Git · {settings.enabled ? '已开启' : '已关闭'}</strong>{' '}
          <button disabled={busy || loading} onClick={() => void toggleGit()}>
            {busy
              ? '处理中…'
              : settings.enabled
                ? '关闭 Git 并保留备份'
                : '开启 Git（有备份时恢复）'}
          </button>
          <p className="settings-hint">
            关闭会将本项目自己的 .git
            移至应用数据目录，代码文件保留；开启可恢复。不会移动上层仓库，也不会阻止终端自行运行
            Git。
          </p>
          {settings.backup_path && (
            <p className="settings-hint">可恢复备份：{settings.backup_path}</p>
          )}
          {!settings.enabled && settings.project_metadata_present && (
            <p role="status">
              项目仍有 .git；请查看操作错误或检查后来创建的仓库，应用不会覆盖任一副本。
            </p>
          )}
        </div>
      )}
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      <button disabled={busy || loading} onClick={() => setRevision((value) => value + 1)}>
        {loading ? '读取中…' : '刷新状态'}
      </button>
      {status?.message && <p role="status">{status.message}</p>}
      {status?.repository_root && (
        <p className="settings-hint">实际仓库：{status.repository_root}</p>
      )}
      {settings?.enabled && status?.available && !status.project_repository && (
        <button disabled={busy} onClick={() => void repositoryAction('init')}>
          {status.repository ? '在本项目初始化独立仓库' : '初始化本地 Git'}
        </button>
      )}
      {settings?.enabled && status?.repository && (
        <>
          <div className="local-git-tabs" role="tablist" aria-label="Git 差异区域">
            <button
              role="tab"
              aria-selected={tab === 'worktree'}
              onClick={() => {
                setTab('worktree')
                setSelected([])
                setDiff(null)
                diffRequest.current++
              }}
            >
              工作区
            </button>
            <button
              role="tab"
              aria-selected={tab === 'index'}
              onClick={() => {
                setTab('index')
                setSelected([])
                setDiff(null)
                diffRequest.current++
              }}
            >
              暂存区
            </button>
          </div>
          <div className="local-git-actions">
            <button
              disabled={busy || !selected.length}
              onClick={() => void changeIndex(tab === 'worktree' ? 'stage' : 'unstage', selected)}
            >
              {tab === 'worktree' ? '暂存所选文件' : '取消所选暂存'}（{selected.length}）
            </button>
          </div>
          <ul className="local-git-files">
            {files.map((file) => (
              <li key={file.path}>
                <input
                  type="checkbox"
                  aria-label={`选择 ${file.path}`}
                  checked={selected.includes(file.path)}
                  onChange={(event) =>
                    setSelected((old) =>
                      event.target.checked
                        ? [...old, file.path]
                        : old.filter((path) => path !== file.path)
                    )
                  }
                />
                <code title="暂存区 / 工作区状态">
                  {file.index_status}
                  {file.worktree_status}
                </code>
                <button className="local-git-path" onClick={() => void readDiff(file)}>
                  {file.path}
                </button>
                {file.original_path && <span>← {file.original_path}</span>}
                <button
                  disabled={busy}
                  onClick={() =>
                    void changeIndex(tab === 'worktree' ? 'stage' : 'unstage', [file.path])
                  }
                >
                  {tab === 'worktree' ? '暂存' : '取消暂存'}
                </button>
              </li>
            ))}
          </ul>
          {!files.length && (
            <p className="settings-hint">
              {tab === 'worktree' ? '当前工作区没有差异。' : '暂存区为空。'}
            </p>
          )}
          {diff && (
            <details open className="local-git-diff">
              <summary>
                {diff.area === 'index' ? '暂存区' : '工作区'}差异 · {diff.path}
              </summary>
              {diff.truncated && <p role="status">差异超过当前输出预算，仅显示部分内容。</p>}
              <pre>{diff.text || '当前没有此区域差异。'}</pre>
            </details>
          )}
          <div className="local-git-commit">
            <p className="settings-hint">
              提交包含上方实际仓库的整个暂存区；文件暂存与差异只显示当前项目。
            </p>
            <label>
              本地提交说明
              <textarea
                rows={2}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
              />
            </label>
            <button
              disabled={busy || !message.trim()}
              onClick={() => void repositoryAction('commit')}
            >
              提交该仓库整个暂存区
            </button>
            <button disabled={busy} onClick={() => void repositoryAction('history')}>
              查看本地历史
            </button>
          </div>
          {history && (
            <details open className="local-git-history">
              <summary>本地提交历史 · {history.commits.length}</summary>
              {!history.commits.length && <p>尚无本地提交。</p>}
              {history.commits.map((commit) => (
                <p key={commit.commit_id}>
                  <code>{commit.commit_id.slice(0, 10)}</code> {commit.subject}
                  <small>
                    {commit.author} · {commit.authored_at}
                  </small>
                </p>
              ))}
            </details>
          )}
        </>
      )}
    </details>
  )
}
