import { useEffect, useRef, useState } from 'react'
import type { DiagnosticEvent } from '../../generated/protocol'
import { ReadingWorkspace } from './ReadingWorkspace'

/** 就地阅读同一条脱敏诊断，关闭不影响任务。 Read one sanitized diagnostic in place without affecting work. */
export function DiagnosticDetails({ id }: { id: string }) {
  const [open, setOpen] = useState(false)
  const [event, setEvent] = useState<DiagnosticEvent | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const generation = useRef(0)
  useEffect(() => {
    ++generation.current
    setEvent(null)
    setError('')
    setCopied(false)
    setBusy(false)
    return () => {
      ++generation.current
    }
  }, [id])
  /** 只读原记录，失败不触发业务重试。 Read the original record without retrying business operations. */
  async function load() {
    const ticket = ++generation.current
    setBusy(true)
    setError('')
    try {
      const result = await window.agent.evolutionDiagnostic({ diagnostic_id: id })
      if (ticket !== generation.current) return
      if (result.ok) setEvent(result.data)
      else setError(`${result.error.code}：${result.error.message}`)
    } catch {
      if (ticket === generation.current) setError('诊断读取失败，原错误仍保留，可重新读取。')
    } finally {
      if (ticket === generation.current) setBusy(false)
    }
  }
  return (
    <div className="diagnostic-details">
      <button
        onClick={() => {
          setOpen(true)
          if (!event && !busy) void load()
        }}
      >
        具体原因与调用位置
      </button>
      <ReadingWorkspace
        open={open}
        title="异常诊断"
        closeLabel="关闭诊断"
        onClose={() => setOpen(false)}
      >
        <div className="diagnostic-body">
          {busy && <p>读取诊断…</p>}
          {error && (
            <p role="alert">
              {error} <button onClick={() => void load()}>重新读取</button>
            </p>
          )}
          {event && (
            <>
              <p>
                {event.code} · {event.message}
              </p>
              <dl className="failure-fields">
                {Object.entries({
                  操作: event.operation,
                  阶段: event.phase,
                  请求: event.request_id,
                  工具调用: event.tool_call_id,
                  诊断编号: event.diagnostic_id
                })
                  .filter(([, value]) => value)
                  .map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
              </dl>
              {!event.causes?.length && <p>旧记录没有保存逐层异常消息；不能从错误码还原原因。</p>}
              {event.causes?.map((cause, index) => (
                <section key={index} className="diagnostic-cause">
                  <strong>
                    {index + 1}. {cause.type}
                    {cause.code ? ` · ${cause.code}` : ''}
                  </strong>
                  {cause.parent != null && (
                    <small>
                      {' '}
                      · 来自第 {cause.parent + 1} 层（{cause.relation}）
                    </small>
                  )}
                  <pre>{cause.message || '底层异常未提供说明'}</pre>
                  {!!cause.frames?.length && (
                    <details>
                      <summary>代码位置</summary>
                      <pre>
                        {cause.frames.map((f) => `${f.file}:${f.line} · ${f.function}`).join('\n')}
                      </pre>
                    </details>
                  )}
                  {!!Object.keys(cause.details ?? {}).length && (
                    <details>
                      <summary>服务／操作详情</summary>
                      <pre>{JSON.stringify(cause.details, null, 2)}</pre>
                    </details>
                  )}
                </section>
              ))}
              <button
                onClick={() =>
                  void navigator.clipboard
                    .writeText(JSON.stringify(event, null, 2))
                    .then(() => setCopied(true))
                    .catch(() => setError('复制未完成，可手动选取。'))
                }
              >
                {copied ? '已复制具体诊断' : '复制具体诊断'}
              </button>
            </>
          )}
        </div>
      </ReadingWorkspace>
    </div>
  )
}
