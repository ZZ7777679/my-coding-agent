import { useRef, useState } from 'react'
import type { EvolutionBudget, EvolutionSettings } from '../../generated/protocol'

type BudgetKey = keyof EvolutionBudget | 'input_chars'
const fields: Array<{ key: BudgetKey; label: string; min: number; advanced?: boolean }> = [
  { key: 'max_requests', label: '模型请求次数', min: 1 },
  { key: 'max_tools', label: '工具调用次数', min: 1 },
  { key: 'max_seconds', label: '总运行时间（秒）', min: 1 },
  { key: 'request_timeout_seconds', label: '单请求总时限（秒）', min: 1 },
  { key: 'max_output_tokens', label: '每次输出 token 上限', min: 1 },
  { key: 'input_chars', label: '参考材料正文预算（字符）', min: 1 },
  { key: 'max_context_bytes', label: '累计调查上下文容量（字节）', min: 4096, advanced: true },
  { key: 'max_response_bytes', label: '单次模型响应容量（字节）', min: 1024, advanced: true }
]

/** 明确区分不限、未知和已设限额。 Distinguish unlimited, unknown and numeric limits. */
export function formatEvolutionBudget(value: number | null | undefined, unit = ''): string {
  return value === null ? '不限' : value === undefined ? '未知' : `${value}${unit}`
}

/** 就地编辑项目改进预算，草稿不随作业轮询丢失。 Edit project improvement budgets in place without polling replacing drafts. */
export function EvolutionBudgetSettings({
  settings,
  disabled,
  onSave
}: {
  settings: EvolutionSettings
  disabled: boolean
  onSave: (budget: EvolutionBudget, inputChars: number | null) => Promise<void>
}) {
  const [draft, setDraft] = useState<Partial<Record<BudgetKey, string | null>>>({})
  const numbers = useRef<Partial<Record<BudgetKey, string>>>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const dirty = Object.keys(draft).length > 0

  /** null 明确代表不限，不能用空值合并回默认上限。 Null means unlimited and must not fall back to defaults. */
  function value(key: BudgetKey): string | null {
    const current =
      draft[key] !== undefined
        ? draft[key]
        : key === 'input_chars'
          ? settings.input_chars
          : settings.budget?.[key]
    return current === null ? null : String(current ?? '')
  }

  /** 保留本页切换前的数值，重新设限时不伪造默认值。 Retain local numeric input when toggling without inventing defaults. */
  function toggle(key: BudgetKey, unlimited: boolean) {
    const current = value(key)
    if (unlimited && current !== null) numbers.current[key] = current
    setDraft((old) => ({ ...old, [key]: unlimited ? null : (numbers.current[key] ?? '') }))
    setNotice('')
  }

  /** 输出明确的 null 或数值，类型和范围在原协议边界检查。 Serialize null or numbers for the existing protocol boundary. */
  function number(key: BudgetKey): number | null {
    const current = value(key)
    return current === null ? null : Number(current)
  }

  /** 保存整组预算，失败时保留输入并就地显示原因。 Save the budget together, preserving input and displaying failures locally. */
  async function save() {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await onSave(
        {
          max_requests: number('max_requests'),
          max_tools: number('max_tools'),
          max_seconds: number('max_seconds'),
          request_timeout_seconds: number('request_timeout_seconds'),
          max_output_tokens: number('max_output_tokens'),
          max_context_bytes: number('max_context_bytes'),
          max_response_bytes: number('max_response_bytes')
        },
        number('input_chars')
      )
      setDraft({})
      setNotice('改进预算已保存，对下一次调查或生成生效。')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '预算保存失败，输入已保留。')
    } finally {
      setSaving(false)
    }
  }

  /** 每项使用独立的不限开关，保留可识别的输入与键盘标签。 Give each option its own unlimited toggle and accessible labels. */
  function renderField({ key, label, min }: (typeof fields)[number]) {
    const current = value(key)
    return (
      <div key={key}>
        <label htmlFor={`evolution-budget-${key}`}>{label}</label>
        <div className="evolution-budget-control">
          <input
            id={`evolution-budget-${key}`}
            type="number"
            min={min}
            step={1}
            required={current !== null}
            disabled={current === null}
            value={current ?? ''}
            placeholder={current === null ? '不限' : '输入上限'}
            onChange={(event) => {
              setDraft((old) => ({ ...old, [key]: event.target.value }))
              setNotice('')
            }}
          />
          <label>
            <input
              type="checkbox"
              aria-label={`${label}不限`}
              checked={current === null}
              onChange={(event) => toggle(key, event.target.checked)}
            />
            不限
          </label>
        </div>
      </div>
    )
  }

  return (
    <details className="evolution-start-options evolution-budget">
      <summary>
        改进预算 · 请求 {formatEvolutionBudget(settings.budget?.max_requests, ' 次')} · 工具{' '}
        {formatEvolutionBudget(settings.budget?.max_tools, ' 次')} · 总时限{' '}
        {formatEvolutionBudget(settings.budget?.max_seconds, ' 秒')}
      </summary>
      <p className="muted">
        仅用于当前项目的调查和候选生成，与普通对话预算独立。每次作业重新计数，同次生成的多个候选共用预算；保存不改变正在运行的作业。
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void save()
        }}
      >
        <fieldset disabled={disabled || saving}>
          <div className="evolution-budget-fields">
            {fields.filter((field) => !field.advanced).map(renderField)}
          </div>
          <details>
            <summary>高级容量设置</summary>
            <div className="evolution-budget-fields">
              {fields.filter((field) => field.advanced).map(renderField)}
            </div>
            <p className="muted">
              累计容量包含调查中继续读取的材料；字节不是 token，文件读取规则仍沿用应用设置。
            </p>
          </details>
          <p className="muted">
            “不限”取消这一项的应用预算；模型服务自身的上下文和输出能力仍适用。输出 token
            不限时省略请求中的输出上限参数。
            材料字符数只控制初始参考正文，后续可按需读取。代码比较仍使用项目执行环境的命令限额。
          </p>
          <button type="submit" disabled={!dirty}>
            {saving ? '保存中…' : '保存改进预算'}
          </button>
          {dirty && <span className="muted"> 有未保存的修改，启动作业仍使用已保存预算。</span>}
        </fieldset>
      </form>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
    </details>
  )
}
