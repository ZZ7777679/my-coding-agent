/** 局部 Goal 的真实状态、用户控制与累计预算。 Real local-goal state, controls and budgets. */
import { useEffect, useRef, useState } from 'react'
import type { ControlGoalParams, GoalBudget, GoalView, RunView } from '../../generated/protocol'
import { useLatestRefresh } from './useLatestRefresh'

const labels: Record<GoalView['status'], string> = {
  active: '持续推进中',
  paused: '已暂停',
  waiting: '等待你的答复',
  failed: '运行失败，已停止',
  budget_exceeded: '累计预算已用尽',
  interrupted: '已中断，待明确接续',
  completed: '局部目标已完成',
  cancelled: '已取消'
}
const criterionLabels = {
  met: '已满足',
  unmet: '未满足',
  not_checked: '未验证',
  needs_user: '待用户确认'
}
type Action =
  | Omit<
      Extract<ControlGoalParams, { action: 'budget' }>,
      'session_id' | 'goal_id' | 'operation_id' | 'expected_revision'
    >
  | Omit<
      Extract<ControlGoalParams, { action: 'answer' }>,
      'session_id' | 'goal_id' | 'operation_id' | 'expected_revision'
    >
  | { action: 'resume' | 'pause' | 'cancel' }

/** 终态目标只在发生位置留一张只读卡片，不占输入区。 Keep ended goals in the timeline only. */
export function GoalHistory({ goal }: { goal: GoalView }): React.JSX.Element {
  return (
    <details
      className="tool-entry goal-history"
      data-testid="goal-history"
      data-status={goal.status}
    >
      <summary>
        Goal · {labels[goal.status]} · {goal.objective}
      </summary>
      <p>已结束，后续对话不会自动接续这个 Goal。</p>
      {goal.last_report && <p>{goal.last_report.summary}</p>}
      <p>
        累计请求 {goal.usage.requests} · 累计工具 {goal.usage.tools}
      </p>
      <ul>
        {goal.criteria.map((criterion) => {
          const result = goal.last_report?.criteria?.find(
            (item) => item.criterion_id === criterion.criterion_id
          )
          return (
            <li key={criterion.criterion_id}>
              {criterion.description} · {result ? criterionLabels[result.status] : '未验证'}
              {result && <p>{result.explanation}</p>}
              {result?.evidence?.map((ref) => (
                <small key={`${ref.session_id}:${ref.seq}`}>
                  来源 {ref.kind} · 会话 {ref.session_id} · 记录 #{ref.seq}
                  <br />
                </small>
              ))}
            </li>
          )
        })}
      </ul>
    </details>
  )
}

/** 编辑可空的累计额度；留空不另加 Goal 上限。 Edit nullable cumulative limits without hidden caps. */
export function GoalBudgetFields({
  value,
  onChange,
  disabled = false
}: {
  value: GoalBudget
  onChange: (value: GoalBudget) => void
  disabled?: boolean
}) {
  const fields: { name: keyof GoalBudget; label: string; step: number }[] = [
    { name: 'max_requests', label: 'Goal 累计请求', step: 1 },
    { name: 'max_tools', label: 'Goal 累计工具', step: 1 },
    { name: 'max_active_seconds', label: 'Goal 活跃秒数', step: 0.1 }
  ]
  return (
    <div className="goal-budgets">
      {fields.map(({ name, label, step }) => (
        <label key={name}>
          {label}
          <input
            aria-label={label}
            type="number"
            min={step}
            step={step}
            value={value[name] ?? ''}
            placeholder="不另设上限"
            disabled={disabled}
            onChange={(event) =>
              onChange({
                ...value,
                [name]: event.target.value === '' ? null : event.target.valueAsNumber
              })
            }
          />
        </label>
      ))}
      <small>跨工作单元累计，接续不清零；每次运行仍使用设置中的 Run 预算。</small>
    </div>
  )
}

/** 按会话和事实水位更新；普通流式文本不触发额外读取。 Refresh by session/fact watermark, not tokens. */
export function Goals({
  sessionId,
  revision,
  connected,
  visible,
  running,
  run,
  onValue,
  onChanged
}: {
  sessionId: string
  revision: number
  connected: boolean
  visible: boolean
  running: boolean
  run: RunView | null
  onValue: (value: GoalView | null) => void
  onChanged: () => void
}) {
  const [goal, setGoal] = useState<GoalView | null>(null)
  const [older, setOlder] = useState<GoalView[]>([])
  const [cursor, setCursor] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState('')
  const [editingBudget, setEditingBudget] = useState(false)
  const [budget, setBudget] = useState<GoalBudget>({})
  const [refresh, setRefresh] = useState(0)
  const [expanded, setExpanded] = useState(false)
  const callbacks = useRef({ onValue, onChanged })
  callbacks.current = { onValue, onChanged }
  const generation = useRef(0)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useLatestRefresh(
    async (isCurrent) => {
      const ticket = ++generation.current
      try {
        const result = await window.agent.listGoals({
          session_id: sessionId,
          limit: 1,
          before_seq: null
        })
        if (!isCurrent() || ticket !== generation.current) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        const current = result.data.goals[0] ?? null
        setError('')
        setGoal(current)
        setCursor(result.data.before_seq)
        callbacks.current.onValue(current)
      } catch {
        if (isCurrent()) setError('无法读取 Goal 状态，未自动重启工作。')
      }
    },
    [sessionId, revision, refresh],
    connected && visible,
    2500
  )

  useEffect(() => {
    setExpanded(false)
    setEditingBudget(false)
  }, [goal?.goal_id])

  useEffect(() => {
    setAnswer('')
    if (goal?.question) setExpanded(true)
  }, [goal?.question?.question_id])

  /** 每个点击只发送一个明确操作，版本冲突需刷新，不隐式重试。 Send once; refresh version conflicts. */
  const act = async (action: Action) => {
    if (!goal || busy || !connected) return
    setBusy(true)
    setError('')
    ++generation.current
    try {
      const result = await window.agent.controlGoal({
        session_id: sessionId,
        goal_id: goal.goal_id,
        operation_id: crypto.randomUUID(),
        expected_revision: goal.revision,
        ...action
      })
      if (!mounted.current) return
      if (!result.ok) setError(`${result.error.message}（${result.error.code}）`)
      else {
        setGoal(result.data)
        callbacks.current.onValue(result.data)
        setEditingBudget(false)
      }
      callbacks.current.onChanged()
    } catch {
      if (mounted.current) setError('控制结果尚未确认，请先查看状态；未自动重发。')
    } finally {
      if (mounted.current) {
        setBusy(false)
        setRefresh((value) => value + 1)
      }
    }
  }

  /** 分页读取过去目标，不把旧状态应用到当前输入框。 Page old goals without changing current input. */
  const loadOlder = async () => {
    if (cursor === null || busy) return
    setBusy(true)
    try {
      const result = await window.agent.listGoals({
        session_id: sessionId,
        before_seq: cursor,
        limit: 10
      })
      if (!mounted.current) return
      if (result.ok) {
        setOlder((items) => [
          ...new Map([...items, ...result.data.goals].map((item) => [item.goal_id, item])).values()
        ])
        setCursor(result.data.before_seq)
      } else setError(result.error.message)
    } catch {
      if (mounted.current) setError('无法读取更早的 Goal。')
    } finally {
      if (mounted.current) setBusy(false)
    }
  }

  if (!goal)
    return error ? (
      <div role="alert" className="notice">
        {error}
      </div>
    ) : null
  const terminal = goal.status === 'completed' || goal.status === 'cancelled'
  if (terminal) return null
  return (
    <section className="goal-card" aria-label="当前 Goal" data-testid="goal-panel">
      <details open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
        <summary className="goal-heading" title={goal.objective}>
          <strong>Goal · {labels[goal.status]}</strong>
          <span className="goal-objective">{goal.objective}</span>
          <span className="sr-only" data-testid="goal-state">
            {goal.status}
          </span>
        </summary>
        <div className="goal-body">
          <p className="work-summary">{goal.objective}</p>
          <div className="goal-usage">
            <span data-testid="goal-request-usage">
              累计请求 {goal.usage.requests ?? '未知'} / {goal.budget.max_requests ?? '不限'}
            </span>
            <span>
              累计工具 {goal.usage.tools ?? '未知'} / {goal.budget.max_tools ?? '不限'}
            </span>
            <span>
              活跃 {goal.usage.active_seconds?.toFixed(1) ?? '未知'} 秒 /{' '}
              {goal.budget.max_active_seconds ?? '不限'}
            </span>
          </div>
          {(goal.usage.reserved_seconds ?? 0) > 0 && (
            <p>另有 {goal.usage.reserved_seconds} 秒未知区间预留；离线时间不计入活跃耗时。</p>
          )}
          {goal.code && <small>停止原因：{goal.code}</small>}
          {goal.status === 'failed' && run?.goal_id === goal.goal_id && run.status === 'failed' && (
            <p role="alert" className="notice">
              {run.message}
            </p>
          )}
          {goal.last_report && <p className="work-summary">{goal.last_report.summary}</p>}
          <details>
            <summary>原始完成条件与证据</summary>
            <ul>
              {goal.criteria.map((criterion) => {
                const result = goal.last_report?.criteria?.find(
                  (item) => item.criterion_id === criterion.criterion_id
                )
                return (
                  <li key={criterion.criterion_id}>
                    {criterion.description} · {result ? criterionLabels[result.status] : '未验证'}
                    {result && <p>{result.explanation}</p>}
                    {result?.evidence?.map((ref) => (
                      <small key={`${ref.session_id}:${ref.seq}`}>
                        来源 {ref.kind} · 会话 {ref.session_id} · 记录 #{ref.seq}
                        <br />
                      </small>
                    ))}
                  </li>
                )
              })}
            </ul>
            <small>
              完成条件保留用户原文。模型判断与引用的执行事实仍需分别理解；Goal 完成不结束整个任务。
            </small>
          </details>
          {!!goal.pending_inputs?.length && (
            <div className="goal-queue">
              <strong>已收到，等待完整执行边界</strong>
              <ul>
                {goal.pending_inputs.map((item) => (
                  <li key={item.operation_id}>{item.prompt}</li>
                ))}
              </ul>
              {goal.status !== 'active' && <p>Goal 已停止，排队输入保留，尚未自动处理。</p>}
            </div>
          )}
          {goal.question && !terminal && (
            <form
              className="goal-question"
              onSubmit={(event) => {
                event.preventDefault()
                if (goal.question && answer.trim())
                  void act({ action: 'answer', question_id: goal.question.question_id, answer })
              }}
            >
              <strong data-testid="goal-question">{goal.question.question}</strong>
              <p>{goal.question.impact}</p>
              {!!goal.question.options?.length && (
                <div>
                  {goal.question.options.map((option) => (
                    <button
                      key={option}
                      type="button"
                      disabled={busy || running}
                      onClick={() => setAnswer(option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              )}
              <textarea
                aria-label="Goal 答复"
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                disabled={busy || running || !connected}
              />
              <button type="submit" disabled={busy || running || !connected || !answer.trim()}>
                提交答复并接续
              </button>
              <small>普通聊天不会代替此答复。</small>
            </form>
          )}
          {!terminal && (
            <div className="goal-actions">
              {goal.status === 'active' ? (
                <button disabled={busy || !connected} onClick={() => void act({ action: 'pause' })}>
                  暂停 Goal
                </button>
              ) : (
                !goal.question && (
                  <button
                    disabled={busy || running || !connected}
                    onClick={() => void act({ action: 'resume' })}
                  >
                    接续 Goal
                  </button>
                )
              )}
              <button disabled={busy || !connected} onClick={() => void act({ action: 'cancel' })}>
                取消 Goal
              </button>
              <button
                disabled={busy || !connected}
                onClick={() => {
                  setBudget(goal.budget)
                  setEditingBudget((value) => !value)
                }}
              >
                调整 Goal 预算
              </button>
            </div>
          )}
          {editingBudget && !terminal && (
            <form
              onSubmit={(event) => {
                event.preventDefault()
                void act({ action: 'budget', budget })
              }}
            >
              <GoalBudgetFields value={budget} onChange={setBudget} disabled={busy} />
              <button disabled={busy || !connected} type="submit">
                保存预算
              </button>
              <small>修改预算不自动恢复已停止的 Goal。</small>
            </form>
          )}
          {error && (
            <div className="notice" role="alert">
              {error}
            </div>
          )}
          {older.map((item) => (
            <details key={item.goal_id}>
              <summary>过去的 Goal · {labels[item.status]}</summary>
              <p>{item.objective}</p>
              <p>{item.last_report?.summary}</p>
            </details>
          ))}
          {cursor !== null && (
            <button
              type="button"
              disabled={busy}
              className="text-button"
              onClick={() => void loadOlder()}
            >
              加载更早 Goal
            </button>
          )}
        </div>
      </details>
    </section>
  )
}
