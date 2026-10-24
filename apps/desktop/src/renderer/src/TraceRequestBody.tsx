import { useMemo, useState } from 'react'
import { TraceJson } from './TraceJson'

/** 只将经过对象检查的 JSON 用于消息视图。 Narrow JSON objects before inspecting messages. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 同一保存正文的 JSON／逐消息视图；折叠仅改变显示。
 * JSON and message views of the same saved body; folding only changes presentation.
 */
export function TraceRequestBody({
  text,
  complete,
  loading,
  onLoadAll
}: {
  text: string
  complete: boolean
  loading: boolean
  onLoadAll: () => void
}) {
  const [structured, setStructured] = useState(false)
  const [opened, setOpened] = useState<Set<number>>(new Set())
  const [toolsOpen, setToolsOpen] = useState(false)
  const parsed: unknown = useMemo(() => {
    if (!complete) return null
    try {
      const value: unknown = JSON.parse(text)
      return value
    } catch {
      // 不完整／非 JSON 仍可查看保存原文，不伪造结构。
      // Keep incomplete or non-JSON content readable without inventing structure.
      return null
    }
  }, [text, complete])
  const request = isRecord(parsed) && Array.isArray(parsed.messages) ? parsed : null
  const issue = isRecord(parsed) && typeof parsed._trace === 'string' ? parsed._trace : null
  const messages: unknown[] = request && Array.isArray(request.messages) ? request.messages : []
  const tools: unknown[] = request && Array.isArray(request.tools) ? request.tools : []
  const counts = messages.reduce<Record<string, number>>((result, message) => {
    const role = isRecord(message) && typeof message.role === 'string' ? message.role : 'unknown'
    result[role] = (result[role] ?? 0) + 1
    return result
  }, {})
  const roles: Record<string, string> = {
    system: '系统提示',
    developer: '开发者提示',
    user: '用户消息',
    assistant: 'AI 消息',
    tool: '工具结果'
  }
  return (
    <div className="trace-request-body">
      <p className="muted trace-input-scope">
        这是本次请求携带的上下文，包含保留的历史消息，不是本轮新增消息的集合，也不是整个 Trace
        日志。
      </p>
      {request && (
        <div className="trace-input-counts">
          <strong>
            本次输入：{messages.length} 条消息 · {tools.length} 个工具定义
          </strong>
          <small>
            按请求角色统计：
            {Object.entries(counts)
              .map(([role, count]) => `${roles[role] ?? role} ${count}`)
              .join(' · ')}
          </small>
          <small>
            用户角色也可能承载接续摘要；工具定义与工具返回消息分别计数。折叠不会改变模型上下文。
          </small>
        </div>
      )}
      {issue && <p role="status">{issue}</p>}
      <div>
        <button disabled={!structured} onClick={() => setStructured(false)}>
          原始 JSON
        </button>
        <button
          disabled={loading || (complete && (!request || structured))}
          onClick={() => {
            setStructured(true)
            if (!complete) onLoadAll()
          }}
        >
          按消息查看
        </button>
      </div>
      {!complete && (
        <small>
          {loading ? '正在加载完整消息…' : '当前为分页预览；按消息查看会读取完整正文。'}
        </small>
      )}
      {structured && request && (
        <>
          <details>
            <summary>其他请求参数</summary>
            <pre>
              {JSON.stringify(
                Object.fromEntries(
                  Object.entries(request).filter(([key]) => key !== 'messages' && key !== 'tools')
                ),
                null,
                2
              )}
            </pre>
          </details>
          {messages.map((message, index) => (
            <details
              key={index}
              open={opened.has(index)}
              onToggle={(event) => {
                const open = event.currentTarget.open
                setOpened((previous) => {
                  const next = new Set(previous)
                  if (open) next.add(index)
                  else next.delete(index)
                  return next
                })
              }}
            >
              <summary>
                #{index + 1} ·{' '}
                {isRecord(message) && typeof message.role === 'string'
                  ? (roles[message.role] ?? message.role)
                  : '消息'}
              </summary>
              {opened.has(index) &&
                (isRecord(message) && typeof message.content === 'string' ? (
                  <>
                    <pre>{message.content}</pre>
                    {Object.keys(message).some((key) => key !== 'role' && key !== 'content') && (
                      <pre>
                        {JSON.stringify(
                          Object.fromEntries(
                            Object.entries(message).filter(([key]) => key !== 'content')
                          ),
                          null,
                          2
                        )}
                      </pre>
                    )}
                  </>
                ) : (
                  <pre>{JSON.stringify(message, null, 2)}</pre>
                ))}
            </details>
          ))}
          <details open={toolsOpen} onToggle={(event) => setToolsOpen(event.currentTarget.open)}>
            <summary>工具定义 · {tools.length}</summary>
            {toolsOpen && <pre>{JSON.stringify(tools, null, 2)}</pre>}
          </details>
        </>
      )}
      <TraceJson
        text={text}
        label={complete ? '完整请求 JSON' : '请求 JSON（已加载部分）'}
        hidden={structured && request !== null}
      />
    </div>
  )
}
