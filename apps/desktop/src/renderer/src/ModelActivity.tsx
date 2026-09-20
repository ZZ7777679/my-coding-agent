/** 展示最近观测与等待时长，不从旧片段推断模型在线。 Show observations, not inferred liveness. */
import { useEffect, useMemo, useState } from 'react'
import type { ModelProgress } from '../../generated/protocol'

const phases: Record<ModelProgress['phase'], string> = {
  preparing: '准备请求',
  connecting: '尝试建立连接',
  tls: '尝试建立安全连接',
  waiting: '已发送请求',
  receiving: '已收到响应头',
  reasoning: '已收到思考片段',
  text: '已收到正文',
  tool_arguments: '已收到工具参数片段',
  completed: '本次请求结束'
}

/** 只有本地等待时间随时钟增长；阶段与收包时间必须来自后端。
 * Only the local waiting clock advances; phases and data arrival times come from the backend.
 */
export function ModelActivity({
  progress,
  active,
  compact = false
}: {
  progress: ModelProgress
  active: boolean
  compact?: boolean
}) {
  const live = active && progress.phase !== 'completed'
  const observedAt = useMemo(() => performance.now(), [progress.elapsed_ms, live])
  const [clock, setClock] = useState(() => performance.now())
  useEffect(() => {
    if (!live) return
    const timer = setInterval(() => setClock(performance.now()), 1000)
    return () => clearInterval(timer)
  }, [live])
  const elapsed = progress.elapsed_ms + (live ? Math.max(0, clock - observedAt) : 0)
  const gap = progress.last_data_ms == null ? null : Math.max(0, elapsed - progress.last_data_ms)
  if (compact)
    return (
      <span>
        {phases[progress.phase]} · {(elapsed / 1000).toFixed(1)} 秒
      </span>
    )
  return (
    <span>
      最后观测：{phases[progress.phase]}
      {live && ' · 等待后续响应'}
      {progress.received_bytes != null &&
        ` · 已接收响应数据 ${(progress.received_bytes / 1024).toFixed(1)} KiB`}
      {gap != null &&
        ` · ${live ? '距上次数据' : '结束前未收到新数据'} ${(gap / 1000).toFixed(1)} 秒`}
      {progress.first_text_ms == null && progress.received_bytes != null && ' · 尚未收到回答正文'}
      {progress.phase === 'reasoning' && ' · 思考与正文分开展示'}
      {progress.phase === 'tool_arguments' && ' · 工具参数完整后展示，不属于回答正文'}
      {progress.first_text_ms != null &&
        ` · 本次请求首字 ${(progress.first_text_ms / 1000).toFixed(2)} 秒`}
    </span>
  )
}
