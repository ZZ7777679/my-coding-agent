import { useState, type ReactNode } from 'react'
import type { OperationError } from '../../generated/protocol'
import { DiagnosticDetails } from './DiagnosticDetails'

const effectLabels = {
  not_executed: '本次运行没有已派发的工具操作',
  saved: '已保存',
  partial: '已有部分工作记录，请核对具体结果',
  unknown: '部分操作结果未知，请先核对实际状态'
}

/** 统一呈现公开错误、来源和接续建议，不把详情按钮当作自动重试。
 * Present public failure provenance and recovery hints without implicitly retrying. */
export function FailureNotice({
  error,
  sessionId,
  runId,
  children
}: {
  error: OperationError
  sessionId?: string
  runId?: string
  children?: ReactNode
}) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState('')
  /** 仅复制已经公开的诊断字段，不包含凭据或原始响应。
   * Copy only public diagnostics, never credentials or raw response bodies. */
  async function copy() {
    try {
      await navigator.clipboard.writeText(
        JSON.stringify({ ...error, session_id: sessionId, run_id: runId }, null, 2)
      )
      setCopied(true)
      setCopyError('')
    } catch {
      setCopyError('复制未完成，请手动选取诊断信息。')
    }
  }
  return (
    <section className="failure-notice" role="alert">
      <strong>{error.message}</strong>
      {error.effect_state && <p>{effectLabels[error.effect_state]}</p>}
      {error.remediation && <p>{error.remediation}</p>}
      {error.diagnostic_issue && (
        <p>诊断保存降级：{error.diagnostic_issue}；以上业务错误仍有效。</p>
      )}
      {error.diagnostic_id && (
        <DiagnosticDetails key={error.diagnostic_id} id={error.diagnostic_id} />
      )}
      <div className="failure-actions">
        {children}
        <button type="button" onClick={() => void copy()}>
          {copied ? '已复制诊断' : '复制诊断'}
        </button>
      </div>
      <details>
        <summary>错误详情</summary>
        <dl className="failure-fields">
          {Object.entries({
            错误码: error.code,
            根因: error.cause_code,
            发生阶段: error.phase,
            诊断编号: error.diagnostic_id,
            会话: sessionId,
            运行: runId,
            工具调用: error.tool_call_id
          })
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
      </details>
      {copyError && <p>{copyError}</p>}
    </section>
  )
}
