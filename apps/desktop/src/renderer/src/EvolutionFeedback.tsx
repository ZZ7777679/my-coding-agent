/** 从具体运行事实记录意见。 Record feedback on a specific execution fact. */
import { useRef, useState } from 'react'
import type { EvolutionSource } from '../../generated/protocol'

/** 关闭后保留草稿，提交只保存反馈。 Keep drafts when closed; submitting records feedback only. */
export function EvolutionFeedbackButton({
  projectId,
  source
}: {
  projectId: string
  source: EvolutionSource
}) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const identity = useRef(crypto.randomUUID())
  return (
    <div>
      <button onClick={() => setOpen(!open)}>{open ? '关闭反馈' : '记录改进反馈'}</button>
      {open && (
        <div>
          <label>
            这一步的反馈
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value)
                identity.current = crypto.randomUUID()
              }}
            />
          </label>
          <button
            disabled={busy || !text.trim()}
            onClick={() => {
              setBusy(true)
              setStatus('')
              void window.agent
                .evolutionFeedback({
                  project_id: projectId,
                  feedback_id: identity.current,
                  source,
                  text
                })
                .then((result) => {
                  if (result.ok) {
                    setText('')
                    identity.current = crypto.randomUUID()
                    setStatus('已保存，可在左侧「经验与改进」中选取。')
                  } else setStatus(result.error.message)
                })
                .catch(() => setStatus('保存未完成，草稿保留。'))
                .finally(() => setBusy(false))
            }}
          >
            保存反馈
          </button>
          {status && <p role="status">{status}</p>}
        </div>
      )}
    </div>
  )
}
