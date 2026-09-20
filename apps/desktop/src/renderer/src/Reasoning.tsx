/** 只呈现 provider 返回的可见思考文本。 Display only visible reasoning returned by the provider. */
import { useEffect, useRef } from 'react'

/** 默认展开并跟随末尾，用户向上阅读或折叠后保留选择。 Follow the tail until the user scrolls or folds. */
export function Reasoning({
  text,
  open,
  streaming,
  onToggle
}: {
  text: string
  open: boolean
  streaming: boolean
  onToggle: (open: boolean) => void
}) {
  const body = useRef<HTMLPreElement>(null)
  const following = useRef(true)
  useEffect(() => {
    if (open && following.current && body.current)
      body.current.scrollTop = body.current.scrollHeight
  }, [text, open])
  if (!text) return null
  return (
    <details
      className="reasoning-block"
      open={open}
      onToggle={(event) => {
        if (event.currentTarget.open !== open) onToggle(event.currentTarget.open)
      }}
    >
      <summary>思考{streaming ? ' · 接收中' : ''}</summary>
      <pre
        data-testid="reasoning-content"
        ref={body}
        onScroll={(event) => {
          const element = event.currentTarget
          following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 40
        }}
      >
        {text}
      </pre>
    </details>
  )
}
