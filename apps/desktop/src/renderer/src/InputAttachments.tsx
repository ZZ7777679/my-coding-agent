/** 输入材料选择与图片分块上传。 Input material selection and chunked image uploads. */
import { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import type { Attachment } from '../../generated/protocol'

export type EditorReference = {
  path: string
  content: string
  start_line: number
  end_line: number
  draft: boolean
}

/** 每个会话保留尚未发送的选择，不因切换丢失。 Preserve unsent selections per session across navigation. */
export const attachmentSelection = new Map<string, Attachment[]>()

export type InputAttachmentHandle = { addFiles: (files: FileList | File[]) => Promise<void> }

/** 添加、预览和移除本次材料；发送在主输入入口完成。 Add, preview and remove current materials; the main composer sends them. */
export const InputAttachments = forwardRef<
  InputAttachmentHandle,
  {
    sessionId: string
    items: Attachment[]
    onChange: (items: Attachment[]) => void
  }
>(function InputAttachments(
  {
    sessionId,
    items,
    onChange
  }: {
    sessionId: string
    items: Attachment[]
    onChange: (items: Attachment[]) => void
  },
  ref
) {
  const picker = useRef<HTMLInputElement>(null)
  const [path, setPath] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<{
    name: string
    text?: string | null
    image?: string | null
  } | null>(null)
  const current = useRef(items)
  current.current = items
  /** 快照文本按明确路径提交，图片分块保持协议帧大小。 Snapshot explicit paths and upload image chunks within protocol frame limits. */
  const addFiles = async (files: FileList | File[]) => {
    setBusy(true)
    setError('')
    try {
      for (const file of Array.from(files)) {
        if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(file.type)) {
          setError('拖放和粘贴支持图片；文本请用文件路径或编辑器选区。')
          continue
        }
        const bytes = new Uint8Array(await file.arrayBuffer())
        let identity: string | null = null
        // 192 KiB 二进制块只控制传输帧，不限制整张图片大小。
        // 192 KiB binary chunks bound transport frames, not the full image size.
        const size = 192 * 1024
        for (let offset = 0; offset < bytes.length; offset += size) {
          let binary = ''
          for (const byte of bytes.subarray(offset, offset + size))
            binary += String.fromCharCode(byte)
          const mime =
            file.type === 'image/png'
              ? 'image/png'
              : file.type === 'image/jpeg'
                ? 'image/jpeg'
                : file.type === 'image/webp'
                  ? 'image/webp'
                  : 'image/gif'
          const result = await window.agent.uploadImageChunk({
            session_id: sessionId,
            attachment_id: identity,
            name: file.name || 'clipboard.png',
            mime,
            data: btoa(binary),
            final: offset + size >= bytes.length,
            purpose: '用户本次选择的图片'
          })
          if (!result.ok) throw new Error(result.error.message)
          identity = result.data.attachment_id
          if (result.data.attachment) {
            current.current = [...current.current, result.data.attachment]
            onChange(current.current)
          }
        }
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '材料添加失败。')
    } finally {
      setBusy(false)
    }
  }
  useImperativeHandle(ref, () => ({ addFiles }))
  /** 文件路径在选择时固定实际文本，可在发送前移除。 Snapshot the selected path before sending and allow removal. */
  const addPath = async () => {
    const result = await window.agent.importAttachment({
      session_id: sessionId,
      path: path.trim().replace(/^@/, ''),
      content: null
    })
    if (!result.ok) setError(result.error.message)
    else {
      current.current = [...current.current, result.data]
      onChange(current.current)
      setPath('')
    }
  }
  return (
    <div className="input-attachments">
      <details>
        <summary>添加文件 / 图片 · 可粘贴或拖入图片</summary>
        <small>文件发送时读取最新内容；编辑器选区和粘贴图片使用已选择快照。</small>
        <input
          aria-label="引用文件路径"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder="项目相对路径，或明确的绝对路径 / @文件"
        />
        <button type="button" disabled={!path.trim() || busy} onClick={() => void addPath()}>
          引用文件
        </button>
        <button type="button" disabled={busy} onClick={() => picker.current?.click()}>
          选择图片
        </button>
        <button type="button" disabled={busy} onClick={async () => {
          setBusy(true)
          try {
            const result = await window.agent.pickAttachments({ session_id: sessionId })
            if (result.ok) {
              current.current = [...current.current, ...result.data.attachments]
              onChange(current.current)
            } else setError(result.error.message)
          } finally { setBusy(false) }
        }}>选择文件</button>
        <input
          ref={picker}
          hidden
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          multiple
          onChange={(event) => {
            if (event.target.files) void addFiles(event.target.files)
            event.target.value = ''
          }}
        />
        {busy && <span>正在保存图片…</span>}
      </details>
      {items.map((item) => (
        <span className="attachment-chip" key={item.attachment_id}>
          <button
            type="button"
            onClick={async () => {
              let offset = 0
              let text = ''
              let image = ''
              do {
                const r = await window.agent.readAttachment({
                  session_id: sessionId,
                  attachment_id: item.attachment_id,
                  offset
                })
                if (!r.ok) {
                  setError(r.error.message)
                  return
                }
                text += r.data.text ?? ''
                image += r.data.image_data ?? ''
                if (r.data.next_offset === null || r.data.next_offset === undefined) break
                offset = r.data.next_offset
              } while (true)
              setPreview({
                name: item.name,
                text,
                image: image ? `data:${item.mime};base64,${image}` : null
              })
            }}
          >
            {item.name}
            {item.draft ? ' · 草稿' : ''}
          </button>
          <button
            type="button"
            aria-label={`移除 ${item.name}`}
            onClick={() =>
              onChange(current.current.filter((i) => i.attachment_id !== item.attachment_id))
            }
          >
            ×
          </button>
        </span>
      ))}
      {error && <small role="alert">{error}</small>}
      {preview && (
        <details open>
          <summary>
            {preview.name}
            <button type="button" onClick={() => setPreview(null)}>
              关闭预览
            </button>
          </summary>
          {preview.image ? (
            <img
              style={{ maxWidth: '100%', maxHeight: 240 }}
              src={preview.image}
              alt={preview.name}
            />
          ) : (
            <pre>{preview.text}</pre>
          )}
        </details>
      )}
    </div>
  )
})
