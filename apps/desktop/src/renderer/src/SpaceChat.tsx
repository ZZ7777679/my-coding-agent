/** 空间群聊复用原会话流与 Goal。 Space group chat reuses existing session streams and goals. */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { SpaceChatView, SpaceView } from '../../generated/protocol'
import './SpaceChat.css'
import { Markdown } from './Markdown'
import { applySpaceDelta, mergeSpaceSnapshot } from './space-stream'

type Props = {
  space: SpaceView
  connected: boolean
  onSelectSession: (sessionId: string) => void
  onChanged: () => void
}

/** 展示精确成员运行输出，普通发言只发给接收成员。 Show exact member output and route ordinary input to its receiver. */
export function SpaceChat({
  space,
  connected,
  onSelectSession,
  onChanged
}: Props): React.JSX.Element {
  const [view, setView] = useState<SpaceChatView | null>(null)
  const [text, setText] = useState('')
  const [targets, setTargets] = useState<string[]>([])
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [activeOnly, setActiveOnly] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const identity = useRef(space.task_id)
  identity.current = space.task_id
  const latestRequest = useRef(0)

  /** 按需带入旧页，不让实时刷新清空已展开历史。 Load older pages without losing them on refresh. */
  async function loadOlder(): Promise<void> {
    if (!view?.next_before || loadingHistory) return
    const taskId = space.task_id
    setLoadingHistory(true)
    try {
      const response = await window.agent.getSpaceChat({
        task_id: taskId,
        before_id: view.next_before
      })
      if (identity.current !== taskId) return
      if (response.ok) setView((current) => mergeSpaceSnapshot(current, response.data, true))
      else setError(response.error.message)
    } catch {
      if (identity.current === taskId) setError('历史读取失败，请重试。')
    } finally {
      if (identity.current === taskId) setLoadingHistory(false)
    }
  }

  /** 读取持久关联和流快照，迟到响应不覆盖新任务。 Read durable references and streams without replacing a newer task. */
  const load = useCallback(async (): Promise<void> => {
    if (!connected) return
    const taskId = space.task_id
    const request = ++latestRequest.current
    try {
      const result = await window.agent.getSpaceChat({ task_id: taskId })
      if (identity.current !== taskId || request !== latestRequest.current) return
      if (result.ok) {
        setView((current) => mergeSpaceSnapshot(current, result.data))
        setError('')
      } else setError(result.error.message)
    } catch (cause) {
      if (identity.current === taskId && request === latestRequest.current)
        setError(cause instanceof Error ? cause.message : '读取合作群聊失败。')
    }
  }, [connected, space.task_id])

  useEffect(() => {
    setView(null)
    setTargets([])
    setText('')
    setPending(false)
    setActiveOnly(false)
    setLoadingHistory(false)
    setError('')
    void load()
  }, [load])

  useEffect(() => {
    const taskId = space.task_id
    const sessions = new Map(
      (space.bindings ?? [])
        .filter((item) => item.session_id)
        .map((item) => [item.session_id, item.member_id])
    )
    let scheduled: ReturnType<typeof setTimeout> | undefined
    /** 合并快照刷新而不推迟已有刷新，持续输出也能恢复。 Coalesce snapshots without postponing an already scheduled refresh. */
    const refresh = (): void => {
      if (scheduled) return
      scheduled = setTimeout(() => {
        scheduled = undefined
        void load()
      }, 75)
    }
    const unsubscribe = window.agent.onSessionEvent((signal) => {
      if (identity.current !== taskId || !sessions.has(signal.session_id)) return
      if ((signal.kind === 'text.delta' || signal.kind === 'reasoning.delta') && signal.run_id) {
        setView((current) => {
          const update = applySpaceDelta(current, signal)
          if (update.resync) refresh()
          return update.view
        })
      } else if (signal.kind === 'changed' || signal.kind === 'resync') {
        refresh()
      }
    })
    return () => {
      unsubscribe()
      if (scheduled) clearTimeout(scheduled)
    }
  }, [load, space.task_id, space.bindings])

  /** 用一个明确操作身份发送普通消息或启动持续目标。 Send an ordinary message or start a continuing goal with an explicit operation ID. */
  async function send(goal: boolean): Promise<void> {
    if (pending || !text.trim()) return
    const taskId = space.task_id
    setPending(true)
    try {
      const result = goal
        ? await window.agent.startSpaceRound({
            task_id: taskId,
            operation_id: crypto.randomUUID(),
            objective: text,
            target_member_ids: targets,
            budget: {},
            limits: null
          })
        : await window.agent.sendSpaceChat({
            task_id: taskId,
            operation_id: crypto.randomUUID(),
            content: text,
            target_member_ids: targets,
            mode: 'normal'
          })
      if (identity.current !== taskId) return
      if (result.ok) {
        setView((current) => mergeSpaceSnapshot(current, result.data))
        setText('')
        setError('')
        onChanged()
      } else setError(result.error.message)
    } catch (cause) {
      if (identity.current === taskId)
        setError(cause instanceof Error ? cause.message : '发送失败，请检查连接后再试。')
    } finally {
      if (identity.current === taskId) setPending(false)
    }
  }

  /** 停止所选成员或保存轮次，原会话保留。 Stop a selected member or saved round while retaining its session. */
  async function stop(roundId: string | null, memberId: string | null): Promise<void> {
    const taskId = space.task_id
    try {
      const result = await window.agent.stopSpaceRound({
        task_id: taskId,
        round_id: roundId,
        member_id: memberId
      })
      if (identity.current !== taskId) return
      if (result.ok) {
        setView((current) => mergeSpaceSnapshot(current, result.data))
        onChanged()
      } else setError(result.error.message)
    } catch (cause) {
      if (identity.current === taskId)
        setError(cause instanceof Error ? cause.message : '停止请求失败，请重试。')
    }
  }

  const members = space.config.members ?? []
  const name = (id: string): string => members.find((item) => item.member_id === id)?.name ?? id
  const receiver = space.config.receiver_member_id ?? members[0]?.member_id
  const outputs = view?.outputs ?? []
  const entries = [
    ...(view?.messages ?? []).map((message) => ({
      id: message.message_id,
      content: message.content,
      created: message.created_at,
      targets: message.target_member_ids,
      goal: false,
      stopped: false
    })),
    ...(view?.rounds ?? []).map((round) => ({
      id: round.round_id,
      content: round.objective,
      created: round.created_at,
      targets: (round.executions ?? []).map((execution) => execution.member_id),
      goal: true,
      stopped: round.stopped
    }))
  ].sort((a, b) => a.created.localeCompare(b.created))
  /** 只根据宿主运行状态判断活跃，不将一次回答结束当作任务完成。
   * Derive activity from host run state, never from a finished answer alone. */
  const active = (status: string): boolean =>
    ['running', 'stopping', 'pending', 'queued'].includes(status)
  const activeCount = new Set(
    outputs
      .filter((output) => active(output.status))
      .map((output) => `${output.session_id}/${output.run_id ?? output.origin_id}`)
  ).size
  const labels: Record<string, string> = {
    running: '执行中',
    stopping: '停止中',
    completed: '本次运行已结束',
    failed: '运行失败',
    cancelled: '已取消',
    budget_exceeded: '预算已用尽',
    interrupted: '已中断',
    queued: '排队中',
    pending: '等待接纳',
    unavailable: '暂不可读'
  }
  /** 回答保持独立折叠节点，实时刷新不替换展开状态或阅读位置。
   * Keep stable disclosure nodes across live updates and preserve the reader's position. */
  const renderOutput = (output: NonNullable<SpaceChatView['outputs']>[number], index: number) => {
    const waitingMember = (space.bindings ?? []).find(
      (binding) => binding.session_id === output.waiting_for
    )
    return (
      <details
        className={`space-output ${active(output.status) ? 'is-active' : ''}`}
        open
        key={`${output.session_id}:${output.run_id}:${output.message_id}:${output.seq ?? index}`}
      >
        <summary>
          <strong>{name(output.member_id)}</strong>
          <span>
            {output.waiting_for
              ? `等待 ${waitingMember ? name(waitingMember.member_id) : '协作会话'}`
              : output.streaming
                ? '正在输出'
                : (labels[output.status] ?? output.status)}
          </span>
          {output.error && <span className="space-output-error">{output.error}</span>}
        </summary>
        <div className="space-output-body">
          <div className="space-output-actions">
            <button onClick={() => onSelectSession(output.session_id)}>会话 / Trace</button>
            {output.waiting_for && (
              <button onClick={() => onSelectSession(output.waiting_for!)}>查看等待对象</button>
            )}
            {active(output.status) && (
              <button disabled={!connected} onClick={() => void stop(null, output.member_id)}>
                停止成员
              </button>
            )}
          </div>
          {output.text && <Markdown text={output.text} />}
        </div>
      </details>
    )
  }
  return (
    <section className="space-chat" aria-label="合作群聊">
      {error && <p role="alert">{error}</p>}
      <details open className="space-chat-disclosure">
        <summary>
          合作群聊{' '}
          <span className="muted">
            {activeCount ? `${activeCount} 项进行中` : '普通对话 / 合作目标'}
          </span>
        </summary>
        <div className="space-chat-body">
          <header className="space-chat-toolbar">
            <label className="space-inline-check">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(event) => setActiveOnly(event.target.checked)}
              />
              仅看进行中
            </label>
            <button disabled={!connected} onClick={() => void load()}>
              刷新
            </button>
          </header>
          <p className="muted">
            未指定对象时交给 {receiver ? name(receiver) : '接收成员'}
            。普通问题回答后返回；启动目标才持续推进。
          </p>
          <div className="space-chat-history" aria-live="polite">
            {view?.next_before && (
              <button disabled={loadingHistory} onClick={() => void loadOlder()}>
                {loadingHistory ? '正在读取…' : '加载较早历史'}
              </button>
            )}
            {entries.map((entry) => {
              const replies = outputs.filter((output) => output.origin_id === entry.id)
              if (activeOnly && !replies.some((output) => active(output.status))) return null
              return (
                <article
                  key={entry.id}
                  className={entry.goal ? 'space-exchange space-round' : 'space-exchange'}
                >
                  <header>
                    <strong>
                      {entry.goal ? `合作目标${entry.stopped ? ' · 已停止' : ''}` : '你'} →{' '}
                      {entry.targets.map(name).join('、')}
                    </strong>
                    <time dateTime={entry.created}>
                      {new Date(entry.created).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </time>
                    {entry.goal && !entry.stopped && (
                      <button disabled={!connected} onClick={() => void stop(entry.id, null)}>
                        停止本轮
                      </button>
                    )}
                  </header>
                  <p className="space-user-message">{entry.content}</p>
                  {replies
                    .filter((output) => !activeOnly || active(output.status))
                    .map(renderOutput)}
                </article>
              )
            })}
            {outputs
              .filter((output) => !output.origin_id && (!activeOnly || active(output.status)))
              .map(renderOutput)}
            {activeOnly && !activeCount && <p className="muted">当前没有正在执行或排队的工作。</p>}
            {!view && <p className="muted">{connected ? '正在读取群聊…' : '后端未连接'}</p>}
            {view && !(view.messages?.length || view.rounds?.length) && (
              <p className="muted">向接收成员提问，或选择成员后启动合作目标。</p>
            )}
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void send(false)
            }}
          >
            <fieldset>
              <legend>@ 接收成员（可多选）</legend>
              {members.map((member) => (
                <label key={member.member_id}>
                  <input
                    type="checkbox"
                    checked={targets.includes(member.member_id)}
                    onChange={(event) =>
                      setTargets((prior) =>
                        event.target.checked
                          ? [...prior, member.member_id]
                          : prior.filter((id) => id !== member.member_id)
                      )
                    }
                  />
                  {member.name}
                </label>
              ))}
            </fieldset>
            <textarea
              aria-label="群聊消息或合作目标"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="输入问题、@成员，或描述要启动的合作目标"
            />
            <div className="space-chat-actions">
              <button disabled={!connected || pending || !text.trim()} type="submit">
                发送问题
              </button>
              <button
                disabled={!connected || pending || !text.trim()}
                type="button"
                onClick={() => void send(true)}
              >
                启动合作目标
              </button>
              <button disabled={!connected} type="button" onClick={() => void stop(null, null)}>
                停止空间工作
              </button>
            </div>
          </form>
        </div>
      </details>
    </section>
  )
}
