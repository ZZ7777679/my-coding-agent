import { useRef, type ReactNode } from 'react'

/** 受控折叠，底部收起与 Escape 都把焦点归还标题。
 * Controlled disclosure with bottom collapse and Escape returning focus to its heading. */
export function KnowledgeDetails({
  title,
  open,
  onToggle,
  children,
  testId
}: {
  title: string
  open: boolean
  onToggle: (open: boolean) => void
  children: ReactNode
  testId?: string
}) {
  const heading = useRef<HTMLButtonElement>(null)
  /** 收起只改变查看状态，不丢内容。 Collapse viewing without discarding content. */
  function close() {
    onToggle(false)
    heading.current?.focus()
  }
  return (
    <section
      className="knowledge-detail"
      data-testid={testId}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          event.stopPropagation()
          close()
        }
      }}
    >
      <button
        type="button"
        className="knowledge-heading"
        ref={heading}
        aria-expanded={open}
        onClick={() => onToggle(!open)}
      >
        {open ? '▾' : '▸'} {title}
      </button>
      <div hidden={!open}>
        {children}
        <button type="button" className="knowledge-collapse" onClick={close}>
          收起{title}
        </button>
      </div>
    </section>
  )
}

/** 选中的公开文本快照发送后成为普通历史。 Selected public text becomes ordinary history when sent. */
export type QuestionMaterial = { key: string; title: string; source: string; text: string }
