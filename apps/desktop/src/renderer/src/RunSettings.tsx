/** 新运行的集中预算设置，不修改活动运行快照。 Centralized budgets for new runs only. */
import { useState } from 'react'
import type { PublicConfig, RunLimits } from '../../generated/protocol'

type Props = { config: PublicConfig; disabled: boolean; onSaved: (config: PublicConfig) => void }
const fields: {
  key: Exclude<keyof RunLimits, 'include_ignored' | 'exclude_globs'>
  label: string
  min: number
  max?: number
}[] = [
  { key: 'max_requests', label: '模型请求次数', min: 1 },
  { key: 'max_tools', label: '工具调用次数', min: 1 },
  { key: 'max_seconds', label: '总运行时间（秒）', min: 1 },
  { key: 'request_timeout_seconds', label: '单请求等待（秒）', min: 1 },
  { key: 'max_output_tokens', label: '输出 token 上限', min: 1 },
  { key: 'max_context_bytes', label: '估算上下文容量（字节）', min: 4096 },
  { key: 'max_response_bytes', label: '单回合内容容量（字节）', min: 1024, max: 262144 },
  { key: 'max_file_bytes', label: '单文件读取容量（字节）', min: 1024 },
  { key: 'max_tool_bytes', label: '工具结果容量（字节）', min: 1024, max: 131072 },
  { key: 'max_scan_files', label: '扫描条目上限', min: 1 },
  { key: 'max_depth', label: '扫描目录深度', min: 1, max: 256 }
]

/** 保留尚未提交的编辑，只有保存成功才采用后端事实。 Keep drafts until the backend confirms saving. */
export function RunSettings({ config, disabled, onSaved }: Props) {
  const [draft, setDraft] = useState<RunLimits | null>(null)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const limits = draft ?? config.run

  /** 合并受信预算表单字段。 Merge trusted budget form fields. */
  const change = (patch: Partial<RunLimits>) => {
    setDraft({ ...limits, ...patch })
    setNotice('')
  }
  /** 保存默认预算，不触发模型调用。 Save default budgets without calling a model. */
  const save = async () => {
    if (saving || disabled) return
    setSaving(true)
    try {
      const result = await window.agent.saveConfig({ model_id: config.model_id, run: limits })
      if (result.ok) {
        onSaved(result.data)
        setDraft(null)
        setNotice('已保存，对下一次运行生效。')
      } else setNotice(result.error.message)
    } catch {
      setNotice('预算保存未确认，请重新读取配置。')
    } finally {
      setSaving(false)
    }
  }
  return (
    <details className="detail-card run-settings">
      <summary>高级运行预算与读取规则</summary>
      <p className="muted">容量是本地保护预算，不代表模型真实上下文上限。修改只影响下一次运行。</p>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void save()
        }}
      >
        <div className="budget-grid">
          {fields.map((field) => (
            <label key={field.key}>
              {field.label}
              <input
                type="number"
                required
                min={field.min}
                max={field.max}
                step={1}
                value={limits[field.key]}
                onChange={(event) => change({ [field.key]: Number(event.target.value) })}
              />
            </label>
          ))}
        </div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={limits.include_ignored}
            onChange={(event) => change({ include_ignored: event.target.checked })}
          />
          允许读取普通忽略文件（凭据和 Git 元数据仍受保护）
        </label>
        <label>
          额外排除 glob（每行一项）
          <textarea
            rows={3}
            value={limits.exclude_globs.join('\n')}
            onChange={(event) =>
              change({
                exclude_globs: event.target.value.split('\n').filter((line) => line.trim())
              })
            }
          />
        </label>
        <button className="primary" type="submit" disabled={disabled || saving || !draft}>
          {saving ? '正在保存…' : '保存运行设置'}
        </button>
        {notice && <p role="status">{notice}</p>}
      </form>
    </details>
  )
}
