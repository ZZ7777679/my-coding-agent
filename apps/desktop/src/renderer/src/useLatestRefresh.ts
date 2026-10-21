import { useEffect, useRef, type DependencyList } from 'react'

/** 合并未完成读取期间的刷新，只接纳最新选择；轮询从上次完成后计时。
 * Coalesce pending reads, accept only the latest selection, and poll after completion. */
export function useLatestRefresh(
  read: (isCurrent: () => boolean) => Promise<void>,
  dependencies: DependencyList,
  enabled = true,
  intervalMs?: number
): void {
  const queue = useRef<{ running: boolean; next: (() => Promise<void>) | null }>({
    running: false,
    next: null
  })
  useEffect(() => {
    let current = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const state = queue.current

    /** 同一组件最多一个在途读取，变化只保留最后一次刷新。
     * Keep one in-flight read and only the latest requested refresh. */
    async function drain() {
      if (state.running) return
      state.running = true
      try {
        while (state.next) {
          const next = state.next
          state.next = null
          await next()
        }
      } finally {
        state.running = false
      }
    }
    /** 读取函数负责展示真实错误；失效回包不能恢复已离开的视图。
     * Readers display real errors; obsolete replies cannot restore departed views. */
    function request() {
      if (!current) return
      state.next = async () => {
        if (!current) return
        try {
          await read(() => current)
        } finally {
          if (current && intervalMs !== undefined) timer = setTimeout(request, intervalMs)
        }
      }
      void drain()
    }
    if (enabled) request()
    return () => {
      current = false
      if (timer) clearTimeout(timer)
    }
  }, [...dependencies, enabled, intervalMs])
}
