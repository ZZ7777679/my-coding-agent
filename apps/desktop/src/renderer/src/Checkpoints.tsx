/** 请求回退预览与逐文件结果；不触发模型重跑。 Request restore previews and outcomes without model replay. */
import { useEffect, useRef, useState } from 'react'
import type { CheckpointPage, RestorePreview, RestoreResult } from '../../generated/protocol'
import './Checkpoints.css'

/** 同一会话中选择代码起点，明确未知作者与未覆盖文件。 Select baselines with honest provenance and coverage. */
export function Checkpoints({
  sessionId,
  running,
  onClose,
  onRestored
}: {
  sessionId: string
  running: boolean
  onClose: () => void
  onRestored: (result: RestoreResult) => void
}) {
  const [page, setPage] = useState<CheckpointPage | null>(null)
  const [preview, setPreview] = useState<RestorePreview | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [observed, setObserved] = useState(false)
  const [result, setResult] = useState<RestoreResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    void load()
    return () => {
      mounted.current = false
    }
  }, [sessionId])

  /** 刷新明确会话的起点列表，不轮询所有文件。 Refresh this session's points without scanning files. */
  async function load() {
    try {
      const response = await window.agent.listCheckpoints({ session_id: sessionId })
      if (!mounted.current) return
      if (response.ok) setPage(response.data)
      else setError(response.error.message)
    } catch {
      if (mounted.current) setError('检查点列表读取失败，请刷新。')
    }
  }
  /** 用当前磁盘内容生成预览，避免把历史差异冒充恢复效果。 Preview against current disk contents. */
  async function inspect(checkpointId: string) {
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const response = await window.agent.previewRestore({
        session_id: sessionId,
        checkpoint_id: checkpointId
      })
      if (!mounted.current) return
      if (!response.ok) {
        setError(response.error.message)
        return
      }
      setPreview(response.data)
      setObserved(false)
      setSelected(
        response.data.files
          .filter((f) => f.source === 'agent' && ['ready', 'unchanged'].includes(f.status))
          .map((f) => f.path)
      )
    } catch {
      if (mounted.current) setError('预览读取失败，请刷新。')
    } finally {
      if (mounted.current) setBusy(false)
    }
  }
  /** 保持原会话，仅在后端确认时带回重新编辑的提问。 Populate the prompt only after confirmed rewind. */
  async function restore(mode: 'code' | 'conversation') {
    if (!preview) return
    setBusy(true)
    setError('')
    try {
      const response = await window.agent.restoreCheckpoint({
        session_id: sessionId,
        checkpoint_id: preview.checkpoint.checkpoint_id,
        operation_id: crypto.randomUUID(),
        mode,
        paths: selected,
        include_observed: observed
      })
      if (!mounted.current) return
      if (!response.ok) {
        setError(response.error.message)
        return
      }
      setResult(response.data)
      onRestored(response.data)
      await load()
    } catch {
      if (mounted.current) setError('恢复结果未确认，请先查看当前文件和撤销检查点，不要重复覆盖。')
    } finally {
      if (mounted.current) setBusy(false)
    }
  }
  return (
    <aside className="checkpoint-panel" aria-label="请求回退">
      <header>
        <strong>请求回退</strong>
        <button onClick={onClose}>关闭</button>
      </header>
      <div className="checkpoint-body">
        <p className="muted">
          恢复到请求前；原记录、Git 暂存区及未选择文件保留。依赖、忽略文件和外部服务不属于代码快照。
        </p>
        {error && <p role="alert">{error}</p>}
        {running && <p>桌面恢复前请先停止此会话运行。</p>}
        <button disabled={busy} onClick={() => void load()}>
          刷新检查点
        </button>
        {page?.unavailable_count ? <p>有 {page.unavailable_count} 项记录不可读取。</p> : null}
        {page && !page.checkpoints.length && <p>尚无请求检查点；旧版本的请求不会补造快照。</p>}
        <div className="checkpoint-list">
          {page?.checkpoints.map((point) => (
            <button
              key={point.checkpoint_id}
              disabled={busy || point.status === 'capturing' || point.status === 'failed'}
              onClick={() => void inspect(point.checkpoint_id)}
            >
              {point.title || '空请求'} · {point.changed_files} 文件 · {point.status}
            </button>
          ))}
        </div>
        {preview && (
          <section>
            <h3>{preview.checkpoint.title}</h3>
            {(preview.issues?.length ?? 0) > 0 && (
              <details>
                <summary>覆盖范围说明</summary>
                <pre>{preview.issues?.join('\n')}</pre>
              </details>
            )}
            <label>
              <input
                type="checkbox"
                checked={observed}
                onChange={(e) => {
                  setObserved(e.target.checked)
                  if (!e.target.checked)
                    setSelected((current) =>
                      current.filter(
                        (path) => preview.files.find((f) => f.path === path)?.source !== 'observed'
                      )
                    )
                }}
              />
              允许选择命令／外部程序产生的、作者未确认的变化
            </label>
            {preview.files.map((file) => (
              <details key={file.path}>
                <summary>
                  <input
                    type="checkbox"
                    aria-label={'恢复 ' + file.path}
                    checked={selected.includes(file.path)}
                    disabled={
                      busy ||
                      file.source === 'other_session' ||
                      (file.source === 'observed' && !observed) ||
                      file.status === 'conflict'
                    }
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) =>
                      setSelected((current) =>
                        e.target.checked
                          ? [...current, file.path]
                          : current.filter((p) => p !== file.path)
                      )
                    }
                  />
                  {file.path} ·{' '}
                  {file.source === 'agent'
                    ? '本会话已记录'
                    : file.source === 'observed'
                      ? '作者未确认'
                      : '含其他会话修改'}{' '}
                  · {file.status}
                </summary>
                <p>{file.message}</p>
                <pre>{file.diff}</pre>
              </details>
            ))}
            <p className="muted">
              “从该消息重新开始”仅在受影响文件全部恢复后切换有效对话；原分支可展开查看。
            </p>
            <div className="button-row">
              <button disabled={busy || running} onClick={() => void restore('code')}>
                只恢复代码
              </button>
              <button
                disabled={busy || running || preview.checkpoint.kind === 'restore'}
                onClick={() => void restore('conversation')}
              >
                恢复并重新提问
              </button>
            </div>
          </section>
        )}
        {result && (
          <section role="status">
            <p>{result.message}</p>
            {result.files.map((file) => (
              <p key={file.path}>
                {file.path} · {file.status} {file.message}
              </p>
            ))}
            <button disabled={busy} onClick={() => void inspect(result.undo_checkpoint_id)}>
              预览撤销这次恢复
            </button>
          </section>
        )}
      </div>
    </aside>
  )
}
