/** 记忆候选的正文表单，保留未编辑的关联字段。 Memory proposal form preserving untouched relationships. */
import { useId, useState } from 'react'

/** 原结构仍由后端契约校验，不让普通编辑必须手写 JSON。 Backend validates the structure; ordinary edits use fields. */
export function EvolutionMemoryEditor({
  value,
  onChange,
  readOnly = false
}: {
  value: string
  onChange: (text: string) => void
  readOnly?: boolean
}) {
  const [raw, setRaw] = useState(false)
  const contentId = useId()
  const rawId = useId()
  let fields: object = {}
  let invalid = false
  if (value) {
    try {
      const parsed: unknown = JSON.parse(value)
      if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) fields = parsed
      else invalid = true
    } catch {
      invalid = true
    }
  }
  const title = 'title' in fields && typeof fields.title === 'string' ? fields.title : ''
  const content = 'content' in fields && typeof fields.content === 'string' ? fields.content : ''
  const category =
    'category' in fields && typeof fields.category === 'string' ? fields.category : 'fact'
  return (
    <div>
      <button onClick={() => setRaw(!raw)}>{raw ? '切换正文表单' : '查看结构化内容'}</button>
      {raw || invalid ? (
        <>
          <label htmlFor={rawId}>记忆结构化内容</label>
          <textarea
            id={rawId}
            className="evolution-editor"
            value={value}
            readOnly={readOnly}
            onChange={(e) => onChange(e.target.value)}
          />
        </>
      ) : (
        <>
          <label>
            记忆标题
            <input
              value={title}
              readOnly={readOnly}
              onChange={(e) =>
                onChange(JSON.stringify({ ...fields, title: e.target.value, content }, null, 2))
              }
            />
          </label>
          <label htmlFor={contentId}>记忆正文</label>
          <textarea
            id={contentId}
            value={content}
            readOnly={readOnly}
            onChange={(e) =>
              onChange(JSON.stringify({ ...fields, title, content: e.target.value }, null, 2))
            }
          />
          <label>
            知识类型
            <select
              value={category}
              disabled={readOnly}
              onChange={(e) =>
                onChange(
                  JSON.stringify({ ...fields, title, content, category: e.target.value }, null, 2)
                )
              }
            >
              <option value="fact">事实</option>
              <option value="preference">明确偏好</option>
              <option value="experience">解决经验</option>
              <option value="hypothesis">待验证假设</option>
              {!['fact', 'preference', 'experience', 'hypothesis'].includes(category) && (
                <option value={category}>{category}</option>
              )}
            </select>
          </label>
          <p>
            正文写明适用条件与证据；一次项目经验不自动成为跨项目规定。「个人偏好」目标采用时按明确偏好保存。
          </p>
        </>
      )}
      {invalid && <p role="alert">当前内容不是记忆对象，请修正结构后使用表单。</p>}
    </div>
  )
}
