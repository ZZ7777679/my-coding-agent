/** 从既有会话和诊断选材，并展示实际输入。 Select existing evidence and display accepted input. */
import type { DiagnosticEvent, EvolutionInput, EvolutionSource } from '../../generated/protocol'
import { EvolutionSourceBrowser, evidenceKey, sourceScope } from './EvolutionSourceBrowser'

export interface SelectedEvidence {
  source: EvolutionSource
  label: string
}
const scopeNames: Record<string, string> = {
  session: '整个会话',
  run: '完整运行',
  event: '单条事件',
  diagnostic: '异常诊断',
  reference: '旧引用'
}

/** 选材不需要先伪造一条反馈；仅读取用户打开的会话。 Select evidence without manufacturing feedback records. */
export function EvolutionEvidencePicker({
  projectId,
  diagnostics,
  selected,
  onChange,
  onTrace,
  disabled
}: {
  projectId: string
  diagnostics: DiagnosticEvent[]
  selected: SelectedEvidence[]
  onChange: (items: SelectedEvidence[]) => void
  onTrace: (source: EvolutionSource) => void
  disabled: boolean
}) {
  /** 取消所选范围，不改历史记录。 Remove a selected scope without changing historical records. */
  function toggle(item: SelectedEvidence) {
    const key = evidenceKey(item.source)
    onChange(
      selected.some((v) => evidenceKey(v.source) === key)
        ? selected.filter((v) => evidenceKey(v.source) !== key)
        : [...selected, item]
    )
  }
  return (
    <div className="detail-card">
      <h2>参考哪些记录</h2>
      <p className="muted">
        Trace
        是事件记录；一次运行包含多条事件，一个会话包含多次运行。先选会话，再明确选整个会话、指定运行或指定事件。
        勾选的历史反馈也会带入其关联来源，预览中会一并列出。
      </p>
      <div className="evolution-selected" aria-label="已选参考材料">
        {!selected.length && <p>尚未选择运行记录。也可只按你的文字要求改进。</p>}
        {selected.map((item) => (
          <div className="evolution-entry" key={evidenceKey(item.source)}>
            <strong className="evolution-scope-badge">
              {scopeNames[sourceScope(item.source)]}
            </strong>
            <span>{item.label}</span>
            {item.source.session_id && (
              <button onClick={() => onTrace(item.source)}>定位原始记录</button>
            )}
            <button
              disabled={disabled}
              onClick={() => toggle(item)}
              aria-label={`移除 ${item.label}`}
            >
              移除
            </button>
          </div>
        ))}
      </div>
      {!!selected.length && (
        <p className="muted">定位只用于查看来源，不会将 Trace 面板中的其他事件加入复盘。</p>
      )}
      <EvolutionSourceBrowser
        key={projectId}
        projectId={projectId}
        selected={selected}
        onChange={onChange}
        onTrace={onTrace}
        disabled={disabled}
      />
      <details>
        <summary>从异常诊断选择 · 最近 {diagnostics.length} 条</summary>
        <p className="muted">
          来自应用数据目录 logs/diagnostics，包含已记录的运行错误和后端告警。 原会话工具输出在上面的
          Trace 中；Electron 启动日志尚不参与此处复盘。
        </p>
        {!diagnostics.length && <p>没有已记录的异常；这不表示所有运行都已检查。</p>}
        {diagnostics.map((d) => {
          const ref = { diagnostic_id: d.diagnostic_id }
          return (
            <details key={d.diagnostic_id} className="evolution-entry">
              <summary>
                {d.code} · {d.message}
              </summary>
              <p>
                {new Date(d.at).toLocaleString()} · {d.component} · {d.phase ?? '阶段未知'}
              </p>
              <label>
                <input
                  type="checkbox"
                  disabled={disabled}
                  checked={selected.some((v) => evidenceKey(v.source) === evidenceKey(ref))}
                  onChange={() => toggle({ source: ref, label: `${d.code} · ${d.message}` })}
                />
                参考此异常记录
              </label>
              <pre>{d.frames?.map((f) => `${f.file}:${f.line} ${f.function}`).join('\n')}</pre>
              {d.source?.session_id && (
                <button onClick={() => onTrace(d.source!)}>查看异常对应 Trace</button>
              )}
            </details>
          )
        })}
      </details>
    </div>
  )
}

/** 显示保存的输入正文；折叠不改变模型材料。 Display input bodies; collapsing does not change model input. */
export function EvolutionInputView({
  input,
  onTrace
}: {
  input: EvolutionInput
  onTrace: (source: EvolutionSource) => void
}) {
  const traces = input.materials?.filter((m) => m.kind === 'trace') ?? []
  const investigation = input.materials?.some((m) => m.kind === 'index') ?? false
  const partial = investigation
    ? (input.coverage?.read ?? 0) - (input.coverage?.complete ?? 0)
    : traces.filter((m) => m.truncated).length
  const complete = investigation ? (input.coverage?.complete ?? 0) : traces.length - partial
  const unread = investigation
    ? (input.coverage?.unread ?? 0)
    : Math.max(0, (input.trace_count ?? 0) - traces.length)
  return (
    <div className="evolution-input">
      {!!input.selections?.length && (
        <div className="evolution-range-total" aria-label="实际选材范围">
          <strong>本次选择范围</strong>
          {input.selections.map((selection, i) => (
            <p key={i}>
              {selection.title} · 匹配 {selection.event_count} 条事件 · 截至 #
              {selection.source.through_seq}
            </p>
          ))}
          <p>
            <strong>
              去重后 {input.trace_count} 条 Trace：{investigation ? '完整读取' : '完整引用'}{' '}
              {complete} 条，
              {investigation ? '部分读取' : '部分引用'} {partial} 条，
              {investigation ? '未读' : '省略'} {unread} 条。
            </strong>
          </p>
          {(partial > 0 || unread > 0) && (
            <p>
              {investigation
                ? '调查仅阅读了相关正文，未读部分仍未知；需要更多依据时可继续调查。'
                : '所选范围并未全文纳入。可调整“改进预算”中的材料预算，或缩小范围。'}
            </p>
          )}
        </div>
      )}
      {!input.selections?.length && traces.length > 0 && (
        <p>此旧快照没有记录选择范围；下方是保存的实际材料，不能据此推断原先选了整个会话。</p>
      )}
      <p>
        整理时间：{new Date(input.prepared_at).toLocaleString()} ·{' '}
        {investigation
          ? `首包材料预算 ${input.input_chars === null ? '不限' : `${input.input_chars} 字符`}；调查累计材料 ${input.included_chars ?? 0} 字符（含索引、已读证据与资源，不是 token 数）`
          : `参考正文 ${input.included_chars ?? 0} 字符 / ${input.input_chars === null ? '不限' : `${input.input_chars} 字符`}（不含目标资源与补充说明，不是 token 数）`}
      </p>
      {input.coverage && (
        <p aria-label="调查阅读覆盖">
          已选 {input.coverage.selected} 项 · 已读 {input.coverage.read} 项 · 完整读取{' '}
          {input.coverage.complete} 项 · 未读 {input.coverage.unread} 项。 未读内容不作为结论依据。
        </p>
      )}
      {!!input.screening?.length && (
        <details open className="evolution-screening">
          <summary>
            推荐调查线索 · {input.episode_count} 组（当前展示 {input.screening.length} 组）
          </summary>
          <p>
            本地检索与归组结果，尚不是模型结论。模型按相关性选读，未读记录仍可搜索；摘录不算完整阅读。
          </p>
          {input.screening.map((episode, index) => (
            <details key={index}>
              <summary>
                {episode.title} · {episode.count} 条同类记录
              </summary>
              <p>{episode.reasons.join(' · ')}</p>
              <pre>{episode.excerpt}</pre>
              <button onClick={() => onTrace(episode.representative)}>查看代表记录</button>
              {episode.related?.map((source, i) => (
                <button key={i} onClick={() => onTrace(source)}>
                  对照 #{source.seq}
                </button>
              ))}
            </details>
          ))}
        </details>
      )}
      {!!input.omitted_materials && (
        <p role="status">
          {investigation
            ? `有 ${input.omitted_materials} 项材料尚未完整阅读；可继续调查，不能据此判断不存在问题。`
            : `有 ${input.omitted_materials} 份材料未纳入，调整预算或减少选择后可重新生成。`}
        </p>
      )}
      {input.resource && (
        <details>
          <summary>改进目标 · {input.resource.label} · 当前内容</summary>
          <pre>{input.resource.content ?? '新资源，暂无原文'}</pre>
          {input.resource.reference_content && (
            <>
              <p>参考定义 / 实际工具契约</p>
              <pre>{input.resource.reference_content}</pre>
            </>
          )}
        </details>
      )}
      {input.instruction && (
        <details>
          <summary>你的本次要求</summary>
          <pre>{input.instruction}</pre>
        </details>
      )}
      {!input.materials?.length && <p>本次没有运行／异常／反馈材料，只使用目标内容和你的要求。</p>}
      {(input.materials ?? []).map((item, i) => (
        <details key={i}>
          <summary>
            {item.title} · {item.content.length} 字符 {item.truncated ? '· 已截断' : ''}
          </summary>
          {item.truncated && <p>来源共有 {item.total_chars} 字符；下方是实际纳入的部分。</p>}
          {item.source?.session_id && (
            <button onClick={() => onTrace(item.source!)}>打开原始 Trace</button>
          )}
          <pre>{item.content}</pre>
        </details>
      ))}
    </div>
  )
}
