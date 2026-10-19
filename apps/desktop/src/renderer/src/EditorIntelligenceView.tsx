/** 展示可导航的语言结果，原始详情只作补充。 Display navigable language results with supplemental native details. */
import type { LanguageResult } from '../../generated/protocol'
import { codeLocations, codeRange, codeSymbols } from './EditorIntelligence'

/** 校验原生对象，不让静态 DTO 类型代替结果校验。 Validate native objects independently of DTO typing. */
function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/** 纯文本说明保持模型/服务文本不受信。 Keep service explanations as untrusted plain text. */
function text(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(text).join('\n')
  const data = record(value)
  return typeof data?.value === 'string' ? data.value : ''
}

/** 用来源与具体位置呈现定义、引用、符号、诊断与补全。 Present provenance and precise locations for actual language results. */
export function EditorIntelligenceView({
  result,
  projectRoot,
  onNavigate
}: {
  result: LanguageResult
  projectRoot: string
  onNavigate?: (path: string, line: number, column: number) => void
}) {
  const data = record(result.result)
  const entries = Array.isArray(result.result)
    ? result.result
    : Array.isArray(data?.items)
      ? data.items
      : []
  const locations = codeLocations(result.result, projectRoot)
  const symbols = codeSymbols(result.result)
  const navigate = (path: string, line: number, column: number) => onNavigate?.(path, line, column)
  return (
    <div className="workspace-language-result">
      <small>
        {result.server_id} · {result.source === 'draft' ? '当前草稿' : '磁盘快照'} · {result.path}
      </small>
      {(result.action === 'definition' || result.action === 'references') && (
        <>
          {!locations.length && <p>没有项目内位置；项目外目标可在原始详情中查看。</p>}
          {locations.map((item, index) => (
            <button
              key={index}
              disabled={!onNavigate}
              onClick={() =>
                navigate(item.path, item.range.startLineNumber, item.range.startColumn)
              }
            >
              {item.path}:{item.range.startLineNumber}:{item.range.startColumn}
            </button>
          ))}
        </>
      )}
      {result.action === 'symbols' && (
        <ul>
          {symbols.map((item, index) => (
            <li key={index}>
              <button
                disabled={!onNavigate}
                onClick={() =>
                  navigate(
                    result.path,
                    item.selectionRange.startLineNumber,
                    item.selectionRange.startColumn
                  )
                }
              >
                {item.name} · {item.selectionRange.startLineNumber}
              </button>
              {item.children?.map((child, i) => (
                <button
                  key={i}
                  disabled={!onNavigate}
                  onClick={() =>
                    navigate(
                      result.path,
                      child.selectionRange.startLineNumber,
                      child.selectionRange.startColumn
                    )
                  }
                >
                  {child.name} · {child.selectionRange.startLineNumber}
                </button>
              ))}
            </li>
          ))}
        </ul>
      )}
      {result.action === 'hover' && <pre>{text(data?.contents) || '当前位置没有说明。'}</pre>}
      {(result.action === 'completion' || result.action === 'diagnostics') && (
        <ul>
          {entries.map((value, index) => {
            const item = record(value)
            if (!item) return null
            const range = codeRange(item.range)
            const label =
              typeof item.label === 'string'
                ? item.label
                : typeof item.message === 'string'
                  ? item.message
                  : ''
            return (
              <li key={index}>
                {range ? (
                  <button
                    disabled={!onNavigate}
                    onClick={() => navigate(result.path, range.startLineNumber, range.startColumn)}
                  >
                    {range.startLineNumber}:{range.startColumn} · {label}
                  </button>
                ) : (
                  <span>{label}</span>
                )}
                {typeof item.detail === 'string' && <small> · {item.detail}</small>}
              </li>
            )
          })}
          {!entries.length && <li>没有返回项目。</li>}
        </ul>
      )}
      {result.action === 'rename' && (
        <p>返回 {result.rename_documents?.length ?? 0} 个文件快照；在文件工作台预览并选择应用。</p>
      )}
      <details>
        <summary>原始服务详情</summary>
        <pre>{JSON.stringify(result.result, null, 2)}</pre>
      </details>
    </div>
  )
}
