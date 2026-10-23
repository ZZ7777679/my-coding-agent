/** 设计会话复用原 Session 快照与增量事件。 Design conversations use existing session snapshots and deltas. */
import { useEffect, useRef, useState } from 'react'
import type { ChatEntry, SessionView } from '../../generated/protocol'
import defaults from '../../../../../src/my_agent/defaults.json'

/** 页面离开只解除订阅，不取消运行；缺口重新读取。 Leaving detaches only; missing deltas resynchronize. */
export function useDesignSession(sessionId: string | undefined, connected: boolean) {
  const [view, setView] = useState<SessionView | null>(null)
  const [older, setOlder] = useState<ChatEntry[]>([])
  const [cursor, setCursor] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [historyBusy, setHistoryBusy] = useState(false)
  const paged = useRef(false)
  useEffect(() => {
    setView(null)
    setOlder([])
    setCursor(null)
    setHistoryBusy(false)
    paged.current = false
    if (!sessionId || !connected) return
    let disposed = false
    let fetching = false
    let dirty = false
    let attached = false
    let value: SessionView | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    /** 合并持久变化事件，快照期间的新事件补读。 Coalesce changes and reread events arriving during snapshots. */
    const refresh = async (): Promise<void> => {
      if (disposed) return
      if (fetching) {
        dirty = true
        return
      }
      fetching = true
      dirty = false
      try {
        const result = await (attached ? window.agent.getSession : window.agent.attachSession)({
          session_id: sessionId,
          before_seq: null
        })
        if (disposed) return
        if (result.ok) {
          attached = true
          value = result.data
          setView(value)
          // 手动翻页后保留结束游标，轮询不能重新显示已读完的历史入口。
          // Once paged, keep the exhausted cursor instead of reviving it during polling.
          if (!paged.current) setCursor(value.before_seq ?? null)
          setError('')
        } else setError(result.error.message)
      } catch (cause) {
        if (!disposed) setError(cause instanceof Error ? cause.message : '设计会话读取失败。')
      } finally {
        fetching = false
        if (dirty && !disposed) schedule()
      }
    }
    /** 定时只合并刷新，不推迟已有刷新。 Schedule a coalesced refresh without postponing it. */
    const schedule = (): void => {
      if (!timer)
        timer = setTimeout(() => {
          timer = undefined
          void refresh()
        }, 80)
    }
    const unsubscribe = window.agent.onSessionEvent((signal) => {
      if (disposed || signal.session_id !== sessionId) return
      if (fetching) {
        dirty = true
        return
      }
      if (!value || signal.process_epoch !== value.process_epoch || signal.kind === 'resync') {
        schedule()
        return
      }
      if (signal.kind === 'model.progress' && signal.run_id === value.summary.run?.run_id) {
        if (signal.model_progress) {
          value = { ...value, model_progress: signal.model_progress }
          setView(value)
        }
        return
      }
      if (signal.kind === 'text.delta' || signal.kind === 'reasoning.delta') {
        if (signal.seq < value.watermark || signal.delta_index <= value.delta_index) return
        if (
          signal.seq !== value.watermark ||
          signal.message_id !== value.stream_message_id ||
          signal.delta_index !== value.delta_index + 1
        ) {
          schedule()
          return
        }
        value = {
          ...value,
          delta_index: signal.delta_index,
          stream_text: value.stream_text + (signal.kind === 'text.delta' ? signal.text : ''),
          stream_reasoning:
            (value.stream_reasoning ?? '') + (signal.kind === 'reasoning.delta' ? signal.text : '')
        }
        setView(value)
      } else schedule()
    })
    void refresh()
    const interval = setInterval(() => {
      if (!document.hidden) void refresh()
    }, defaults.desktop_connection.idle_refresh_ms)
    return () => {
      disposed = true
      unsubscribe()
      if (timer) clearTimeout(timer)
      clearInterval(interval)
      void window.agent.detachSession(sessionId).catch(() => undefined)
    }
  }, [sessionId, connected])

  /** 较早记录按原游标加载，不复制另一套历史。 Load earlier records using the original session cursor. */
  async function loadOlder(): Promise<void> {
    if (!sessionId || cursor === null || historyBusy) return
    setHistoryBusy(true)
    try {
      const result = await window.agent.getSession({ session_id: sessionId, before_seq: cursor })
      if (result.ok) {
        paged.current = true
        setOlder((current) => [...result.data.entries, ...current])
        setCursor(result.data.before_seq)
      } else setError(result.error.message)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '历史读取失败。')
    } finally {
      setHistoryBusy(false)
    }
  }
  const entries = [
    ...new Map([...older, ...(view?.entries ?? [])].map((entry) => [entry.seq, entry])).values()
  ].sort((a, b) => a.seq - b.seq)
  return { view, entries, cursor, loadOlder, historyBusy, error }
}
