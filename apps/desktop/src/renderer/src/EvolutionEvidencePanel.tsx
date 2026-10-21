/** 证据按需在视窗内查看，不移动底层改进页面。 View evidence on demand without moving the underlying improvement page. */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type {
  EvolutionInput,
  EvolutionJob,
  EvolutionSource,
  GenerateEvolutionCandidate
} from '../../generated/protocol'
import { EvolutionInputView } from './EvolutionEvidence'
import { Trace } from './Trace'

export type EvolutionEvidenceView =
  | { kind: 'preview'; request: GenerateEvolutionCandidate }
  | { kind: 'job'; jobId: string; title: string }
  | { kind: 'trace'; source: EvolutionSource }

/** 加载证据并在从原始 Trace 返回后保留材料阅读位置；关闭不改变选材。
 * Load evidence and preserve the material position when returning from Trace; closing never changes selection.
 */
export function EvolutionEvidencePanel({
  projectId,
  view,
  onClose
}: {
  projectId: string
  view: EvolutionEvidenceView
  onClose: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [input, setInput] = useState<EvolutionInput | null>(null)
  const [job, setJob] = useState<EvolutionJob | null>(null)
  const [loading, setLoading] = useState(view.kind !== 'trace')
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [source, setSource] = useState(view.kind === 'trace' ? view.source : null)
  const [traceProject, setTraceProject] = useState<string | null>(null)
  const [traceError, setTraceError] = useState('')
  const materialOpener = useRef<HTMLElement | null>(null)
  const title =
    view.kind === 'preview' ? '本次待参考材料' : view.kind === 'job' ? view.title : '原始 Trace'

  useEffect(() => {
    const element = dialog.current
    const opener = document.activeElement
    element?.showModal()
    return () => {
      element?.close()
      // 关闭后保持原入口及页面位置，避免 focus 默认滚动长页面。
      // Preserve the trigger and page position instead of letting focus scroll the long page.
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true })
    }
  }, [])

  useEffect(() => {
    if (view.kind === 'trace') return
    let current = true
    setLoading(true)
    setError('')
    /** 面板关闭后忽略只读请求的迟到响应。 Ignore late read-only results after the panel closes. */
    async function load() {
      try {
        if (view.kind === 'preview') {
          const result = await window.agent.evolutionPreview(view.request)
          if (!current) return
          if (!result.ok) throw new Error(result.error.message)
          setInput(result.data)
        } else if (view.kind === 'job') {
          const result = await window.agent.evolutionJob({
            project_id: projectId,
            job_id: view.jobId
          })
          if (!current) return
          if (!result.ok) throw new Error(result.error.message)
          setJob(result.data)
          setInput(result.data.review_input ?? null)
        }
      } catch (failure) {
        if (current)
          setError(failure instanceof Error ? failure.message : '证据读取失败，请重新读取。')
      } finally {
        if (current) setLoading(false)
      }
    }
    void load()
    return () => {
      current = false
    }
  }, [projectId, view, retry])

  useEffect(() => {
    if (!source?.session_id) return
    let current = true
    setTraceProject(null)
    setTraceError('')
    // 先解析来源项目，不能用候选写入项目读取跨项目证据。
    // Resolve the source project instead of using the candidate write project for cross-project evidence.
    void window.agent
      .getSession({ session_id: source.session_id, before_seq: null })
      .then((result) => {
        if (!current) return
        if (result.ok) setTraceProject(result.data.summary.project_id)
        else setTraceError(result.error.message)
      })
      .catch((failure: unknown) => {
        if (current)
          setTraceError(failure instanceof Error ? failure.message : '原始会话读取失败。')
      })
    return () => {
      current = false
    }
  }, [source, retry])

  /** 查看原始记录时保留材料节点及展开状态。 Keep material nodes and expansions while viewing the original Trace. */
  function openTrace(next: EvolutionSource) {
    if (!next.session_id) return
    materialOpener.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    setSource(next)
  }

  /** 返回原材料，或关闭直接从页面打开的 Trace。 Return to materials or close a directly opened Trace. */
  function closeTrace() {
    if (view.kind === 'trace') onClose()
    else {
      setSource(null)
      requestAnimationFrame(() => materialOpener.current?.focus({ preventScroll: true }))
    }
  }

  return createPortal(
    <dialog
      ref={dialog}
      className="evolution evolution-evidence-panel"
      aria-label="改进证据"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
    >
      <header className="evolution-evidence-heading">
        <h2>{source ? '原始 Trace' : title}</h2>
        <div className="evolution-row">
          {source && view.kind !== 'trace' && <button onClick={closeTrace}>返回参考材料</button>}
          <button autoFocus onClick={onClose}>
            关闭证据
          </button>
        </div>
      </header>
      <div className="evolution-evidence-body" hidden={source !== null}>
        {loading && <p role="status">正在读取证据…</p>}
        {error && (
          <div role="alert">
            <p>{error}</p>
            <button onClick={() => setRetry((value) => value + 1)}>重新读取</button>
          </div>
        )}
        {view.kind === 'preview' && (
          <p className="muted">
            预览不调用模型。生成时重新读取最新内容；作业中的“实际参考材料”保存生成当时的版本。
          </p>
        )}
        {input && <EvolutionInputView input={input} onTrace={openTrace} />}
        {!loading && !error && !input && job && !job.experiment_directory && (
          <p>此记录没有保存模型输入快照。</p>
        )}
        {job?.response_text && (
          <details>
            <summary>模型最终返回（排查格式）</summary>
            <pre>{job.response_text}</pre>
          </details>
        )}
        {(job?.programs ?? []).map((program) => (
          <details key={program.summary.program_id}>
            <summary>
              {program.summary.cwd} · exit {program.summary.exit_code ?? '未知'}
            </summary>
            <pre>{program.output.map((chunk) => chunk.text).join('')}</pre>
            {program.truncated && <p>这里是输出预览，完整程序记录保存在实验数据目录。</p>}
          </details>
        ))}
        {!!job?.omitted_paths?.length && (
          <details>
            <summary>副本排除项</summary>
            <pre>{job.omitted_paths.join('\n')}</pre>
          </details>
        )}
      </div>
      {source?.session_id && (
        <div className="evolution-evidence-trace">
          {!traceProject && !traceError && <p role="status">正在读取原始会话…</p>}
          {traceError && (
            <div role="alert">
              <p>{traceError}</p>
              <button onClick={() => setRetry((value) => value + 1)}>重新读取</button>
            </div>
          )}
          {traceProject && (
            <Trace
              key={`${source.session_id}:${source.run_id ?? ''}:${source.seq ?? ''}`}
              sessionId={source.session_id}
              projectId={traceProject}
              revision={0}
              focusSeq={source.seq ?? null}
              focusRun={source.run_id}
              showHeader={false}
              onClose={closeTrace}
            />
          )}
        </div>
      )}
    </dialog>,
    document.body
  )
}
