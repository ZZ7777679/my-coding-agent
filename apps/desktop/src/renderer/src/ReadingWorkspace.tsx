import { useEffect, useRef, type ReactNode } from 'react'

/** 应用内阅读页保留内容与滚动；dialog 管理焦点回返和键盘边界。
 * Retain reading content and scroll; dialog manages focus return and keyboard scope. */
export function ReadingWorkspace({
  open,
  title,
  onClose,
  closeLabel = '返回对话',
  children
}: {
  open: boolean
  title: string
  onClose: () => void
  closeLabel?: string
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (open && !ref.current?.open) ref.current?.showModal()
    else if (!open && ref.current?.open) ref.current.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      className="reading-workspace"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
    >
      <header className="reading-header">
        <strong>{title}</strong>
        <button autoFocus onClick={onClose}>
          {closeLabel}
        </button>
      </header>
      {children}
    </dialog>
  )
}
