import { useLayoutEffect, useRef, useState } from 'react'

/** 可独立收起的 JSON 阅读区；折叠保留正文和滚动位置。
 * Independently fold JSON while retaining loaded text and its reading position.
 */
export function TraceJson({
  text,
  label,
  hidden = false
}: {
  text: string
  label: string
  hidden?: boolean
}) {
  const [open, setOpen] = useState(false)
  const reader = useRef<HTMLDivElement>(null)
  const position = useRef(0)
  useLayoutEffect(() => {
    if (open && !hidden && reader.current) reader.current.scrollTop = position.current
  }, [open, hidden])
  return (
    <div className="trace-json" hidden={hidden}>
      <button aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? '收起' : '展开'}
        {label}
      </button>
      <div
        className="trace-json-content"
        ref={reader}
        hidden={!open}
        onScroll={(event) => {
          if (open && !hidden) position.current = event.currentTarget.scrollTop
        }}
      >
        <pre>{text}</pre>
      </div>
    </div>
  )
}
