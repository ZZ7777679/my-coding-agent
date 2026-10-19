/** 查看本会话的历史修改与真实结果。 Inspect saved changes and outcomes for this session. */
import { useEffect, useRef, useState } from 'react'
import type { ChangeSummary, ChangeView } from '../../generated/protocol'

const statuses = { applied: '已保存到项目', failed: '写入失败', prepared: '结果尚未确认' }

/** 从后端分页读取成果，切换会话后丢弃迟到响应。 Page artifacts and discard stale session responses. */
export function Changes({ sessionId, revision }: { sessionId: string; revision: number }) {
  const [items, setItems] = useState<ChangeSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [view, setView] = useState<ChangeView | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [scope, setScope] = useState<'session' | 'task'>('session')
  const [path, setPath] = useState('')
  const generation = useRef(0)
  const current = useRef(sessionId)
  current.current = sessionId

  useEffect(() => {
    setItems([])
    setView(null)
    setCursor(null)
    setError('')
    setBusy(false)
    return () => {
      ++generation.current
    }
  }, [sessionId, scope, path])

  useEffect(() => {
    let disposed = false
    void window.agent
      .listChanges({ session_id: sessionId, cursor: null, limit: 20, scope, path: path || null })
      .then((result) => {
        if (disposed) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        setItems(result.data.changes)
        setCursor(result.data.next_cursor)
        setError(result.data.unavailable_count ? '部分修改记录无法读取，原文件仍保留。' : '')
      })
      .catch(() => {
        if (!disposed) setError('修改记录连接中断。')
      })
    return () => {
      disposed = true
    }
  }, [sessionId, revision, scope, path])

  /** 只读历史两端的差异，分页不把超长输出塞进消息。 Read historical diffs in bounded pages. */
  const open = async (changeId: string, sourceSession: string, offset = 0) => {
    const ticket = ++generation.current
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.getChange({
        session_id: sourceSession,
        change_id: changeId,
        offset
      })
      if (ticket !== generation.current || current.current !== sessionId) return
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setView(result.data)
    } catch {
      if (ticket === generation.current) setError('无法读取差异，请重试。')
    } finally {
      if (ticket === generation.current) setBusy(false)
    }
  }

  /** 继续元数据分页，保留已显示条目。 Append another metadata page. */
  const more = async () => {
    if (!cursor || busy) return
    const ticket = ++generation.current
    setBusy(true)
    try {
      const result = await window.agent.listChanges({
        session_id: sessionId,
        cursor,
        limit: 20,
        scope,
        path: path || null
      })
      if (ticket !== generation.current || current.current !== sessionId) return
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setItems((previous) => [
        ...new Map(
          [...previous, ...result.data.changes].map((item) => [item.change_id, item])
        ).values()
      ])
      setCursor(result.data.next_cursor)
    } catch {
      if (ticket === generation.current) setError('无法加载更多修改。')
    } finally {
      if (ticket === generation.current) setBusy(false)
    }
  }

  return (
    <aside className="changes-panel" aria-label="修改成果">
      <details open>
        <summary>
          修改成果 · {items.length}
          {cursor ? '+' : ''}
        </summary>
        <p className="muted">
          修改直接保存在原项目。这里展示历史基线与预期结果，不代表当前磁盘版本。
          只包含文件工具及编辑器记录；外部或 shell 写入的来源未知。
        </p>
        <label>
          修改范围
          <select
            aria-label="修改范围"
            value={scope}
            onChange={(e) => setScope(e.target.value === 'task' ? 'task' : 'session')}
          >
            <option value="session">本会话</option>
            <option value="task">同任务所有会话 · 最近优先</option>
          </select>
        </label>
        <input
          aria-label="按文件筛选修改"
          placeholder="项目相对路径（留空查看全部）"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        {error && (
          <p role="alert" className="notice">
            {error}
          </p>
        )}
        {!items.length && <p>当前范围尚无文件修改记录；未绑定任务时仅查看本会话。</p>}
        {items.map((item) => (
          <button
            key={item.change_id}
            type="button"
            disabled={busy}
            onClick={() => void open(item.change_id, item.session_id)}
          >
            {item.path} · {item.operation === 'create' ? '新建' : '编辑'} · {statuses[item.status]}
            {' · '}
            {item.session_id === sessionId ? '本会话' : `其他会话 ${item.session_id.slice(0, 8)}`}
            {' · '}
            {new Date(item.created_at).toLocaleString()}
          </button>
        ))}
        {cursor && (
          <button type="button" disabled={busy} onClick={() => void more()}>
            更多修改
          </button>
        )}
        {view && (
          <section>
            <strong>
              {view.summary.path} · {statuses[view.summary.status]}
            </strong>
            <p>
              {view.summary.created_at} · 会话 {view.summary.session_id} · 运行{' '}
              {view.summary.run_id}
            </p>
            {view.summary.status === 'prepared' && (
              <p className="notice">
                已保存准备记录，最终写入结果尚未确认。请核对项目文件；系统不会自动重放或回滚。
              </p>
            )}
            {view.summary.error && <p role="alert">{view.summary.error}</p>}
            <pre className="change-diff" data-testid="change-diff">
              {view.diff || '文本没有差异，可核对编码及换行。'}
            </pre>
            {view.next_offset !== null && (
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void open(view.summary.change_id, view.summary.session_id, view.next_offset ?? 0)
                }
              >
                下一页差异
              </button>
            )}
            <button type="button" onClick={() => setView(null)}>
              关闭差异
            </button>
          </section>
        )}
      </details>
    </aside>
  )
}
