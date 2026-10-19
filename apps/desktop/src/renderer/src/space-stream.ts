import type { SessionSignal, SpaceChatView } from '../../generated/protocol'

/** 保留同一回答水位较新的流，完成记录始终采用后端事实。 Keep the newer stream watermark; committed answers remain authoritative. */
export function mergeSpaceSnapshot(
  current: SpaceChatView | null,
  incoming: SpaceChatView,
  older = false
): SpaceChatView {
  if (!current || current.task_id !== incoming.task_id) return incoming
  const incomingIds = new Set([
    ...(incoming.messages ?? []).map((m) => m.message_id),
    ...(incoming.rounds ?? []).map((r) => r.round_id)
  ])
  return {
    ...incoming,
    messages: [
      ...new Map(
        [...(current.messages ?? []), ...(incoming.messages ?? [])].map((m) => [m.message_id, m])
      ).values()
    ].sort((a, b) => a.created_at.localeCompare(b.created_at)),
    rounds: [
      ...new Map(
        [...(current.rounds ?? []), ...(incoming.rounds ?? [])].map((r) => [r.round_id, r])
      ).values()
    ].sort((a, b) => a.created_at.localeCompare(b.created_at)),
    next_before: older ? incoming.next_before : current.next_before,
    outputs: [
      ...(current.outputs ?? []).filter((o) => o.origin_id && !incomingIds.has(o.origin_id)),
      ...(incoming.outputs ?? []).map((output) => {
        const live = current.outputs?.find(
          (item) =>
            item.streaming &&
            output.streaming &&
            item.session_id === output.session_id &&
            item.run_id === output.run_id &&
            item.message_id === output.message_id &&
            item.process_epoch === output.process_epoch
        )
        // 较新的文本水位不能掩盖本次快照更新的等待对象或消息归属。
        // A newer text watermark must not hide updated waiting targets or message origins.
        return live && (live.delta_index ?? 0) > (output.delta_index ?? 0)
          ? { ...output, text: live.text, delta_index: live.delta_index }
          : output
      })
    ]
  }
}

/** 仅续接同一回答的连续片段，缺口由快照恢复。 Append contiguous deltas only; recover gaps from the authoritative snapshot. */
export function applySpaceDelta(
  current: SpaceChatView | null,
  signal: SessionSignal
): { view: SpaceChatView | null; resync: boolean } {
  if (!current) return { view: current, resync: true }
  const outputs = [...(current.outputs ?? [])]
  const index = outputs.findIndex(
    (item) =>
      item.session_id === signal.session_id &&
      item.run_id === signal.run_id &&
      item.message_id === signal.message_id
  )
  if (index < 0) return { view: current, resync: true }
  const output = outputs[index]
  if (!output.streaming) return { view: current, resync: false }
  if (output.process_epoch !== signal.process_epoch) return { view: current, resync: true }
  const watermark = output.delta_index ?? 0
  if (signal.delta_index <= watermark) return { view: current, resync: false }
  if (signal.delta_index !== watermark + 1) return { view: current, resync: true }
  outputs[index] = {
    ...output,
    text: (output.text ?? '') + (signal.kind === 'text.delta' ? signal.text : ''),
    delta_index: signal.delta_index
  }
  return { view: { ...current, outputs }, resync: false }
}
