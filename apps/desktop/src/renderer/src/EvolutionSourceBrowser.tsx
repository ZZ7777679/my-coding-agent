/** 明确会话、运行和事件三个选材层级。 Explicit session, run and event selection scopes. */
import { useEffect, useRef, useState } from 'react'
import type {
  EvolutionRunItem,
  EvolutionRunsPage,
  EvolutionSource,
  SessionPage,
  TracePage
} from '../../generated/protocol'
import type { SelectedEvidence } from './EvolutionEvidence'

/** 兼容旧记录的隐式范围，但不把纯会话引用推断为全部历史。 Interpret legacy scopes without broadening bare session references. */
export function sourceScope(source: EvolutionSource): string {
  return (
    source.scope ??
    (source.seq
      ? 'event'
      : source.run_id
        ? 'run'
        : source.diagnostic_id
          ? 'diagnostic'
          : 'reference')
  )
}

/** 分页不改变用户的选择身份。 Paging does not change selection identity. */
export function evidenceKey(source: EvolutionSource): string {
  return [
    sourceScope(source),
    source.session_id,
    source.run_id,
    source.seq,
    source.diagnostic_id
  ].join(':')
}

/** 目录按完整运行分页，事件在指定运行内按需展开。 Page complete runs and expand events within a chosen run. */
export function EvolutionSourceBrowser({
  projectId,
  selected,
  onChange,
  onTrace,
  disabled
}: {
  projectId: string
  selected: SelectedEvidence[]
  onChange: (items: SelectedEvidence[]) => void
  onTrace: (source: EvolutionSource) => void
  disabled: boolean
}) {
  const [sessions, setSessions] = useState<SessionPage | null>(null)
  const [sessionId, setSessionId] = useState('')
  const [runs, setRuns] = useState<EvolutionRunsPage | null>(null)
  const [mode, setMode] = useState<'session' | 'run' | 'event'>('run')
  const [sessionFilter, setSessionFilter] = useState('')
  const [query, setQuery] = useState('')
  const [appliedQuery, setAppliedQuery] = useState('')
  const [events, setEvents] = useState<TracePage | null>(null)
  const [eventRun, setEventRun] = useState<EvolutionRunItem | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const generation = useRef(0)
  useEffect(
    () => () => {
      ++generation.current
    },
    []
  )

  /** 累积会话目录，加载更多不会抹去当前会话。 Accumulate session pages without discarding the current session. */
  async function loadSessions(cursor: string | null = null) {
    const ticket = ++generation.current
    setLoading(true)
    setError('')
    try {
      const result = await window.agent.listSessions({ project_id: projectId, cursor, limit: 30 })
      if (ticket !== generation.current) return
      if (!result.ok) throw new Error(result.error.message)
      setSessions((old) => ({
        ...result.data,
        sessions: cursor && old ? [...old.sessions, ...result.data.sessions] : result.data.sessions
      }))
    } catch (e) {
      if (ticket === generation.current) setError(e instanceof Error ? e.message : '读取失败')
    } finally {
      if (ticket === generation.current) setLoading(false)
    }
  }

  /** 按轮读取，不从某页 Trace 猜运行列表。 Read runs directly instead of inferring them from one Trace page. */
  async function loadRuns(id: string, search: string, before: number | null = null) {
    const ticket = ++generation.current
    setLoading(true)
    setError('')
    if (!before) {
      setRuns(null)
      setEvents(null)
      setEventRun(null)
    }
    if (id !== sessionId) {
      const scope = sourceScope(selected.find((s) => s.source.session_id === id)?.source ?? {})
      setMode(scope === 'session' || scope === 'event' ? scope : 'run')
    }
    setSessionId(id)
    try {
      const result = await window.agent.evolutionRuns({
        project_id: projectId,
        session_id: id,
        query: search,
        before_seq: before
      })
      if (ticket !== generation.current) return
      if (!result.ok) throw new Error(result.error.message)
      setRuns((old) => ({
        ...result.data,
        runs: before && old ? [...old.runs, ...result.data.runs] : result.data.runs
      }))
      setAppliedQuery(search)
    } catch (e) {
      if (ticket === generation.current) setError(e instanceof Error ? e.message : '读取失败')
    } finally {
      if (ticket === generation.current) setLoading(false)
    }
  }

  /** 单轮事件累积加载，选中项由父组件保留。 Append one run's event pages while retaining selection in the parent. */
  async function loadEvents(run: EvolutionRunItem, before: number | null = null) {
    const ticket = ++generation.current
    setLoading(true)
    setError('')
    setEventRun(run)
    if (!before) setEvents(null)
    try {
      const result = await window.agent.listTrace({
        session_id: sessionId,
        run_id: run.run_id,
        before_seq: before
      })
      if (ticket !== generation.current) return
      if (!result.ok) throw new Error(result.error.message)
      setEvents((old) => ({
        ...result.data,
        items: before && old ? [...result.data.items, ...old.items] : result.data.items
      }))
    } catch (e) {
      if (ticket === generation.current) setError(e instanceof Error ? e.message : '读取失败')
    } finally {
      if (ticket === generation.current) setLoading(false)
    }
  }

  /** 层级切换只清除本会话的旧范围，不混合“全部”和“局部”。 Change scope explicitly without mixing whole-session and partial selections. */
  function changeMode(next: 'session' | 'run' | 'event') {
    setMode(next)
    onChange(selected.filter((s) => s.source.session_id !== sessionId || !!s.source.diagnostic_id))
  }
  function toggle(item: SelectedEvidence) {
    const key = evidenceKey(item.source)
    onChange(
      selected.some((s) => evidenceKey(s.source) === key)
        ? selected.filter((s) => evidenceKey(s.source) !== key)
        : [...selected, item]
    )
  }
  /** 从目录生成明确的一轮选择，不随随后到达的事件扩张。 Freeze a run selection at the catalog watermark. */
  function runSelection(run: EvolutionRunItem): SelectedEvidence {
    return {
      source: {
        scope: 'run',
        session_id: sessionId,
        run_id: run.run_id,
        through_seq: run.through_seq
      },
      label: `指定运行 · ${run.prompt} · ${run.event_count} 条事件 · 截至 #${run.through_seq}`
    }
  }
  const selectedHere = selected.filter(
    (s) => s.source.session_id === sessionId && !s.source.diagnostic_id
  )
  const whole: SelectedEvidence | null = runs
    ? {
        source: { scope: 'session', session_id: sessionId, through_seq: runs.through_seq },
        label: `整个会话 · ${runs.title} · ${runs.total_runs} 轮 / ${runs.total_events} 条事件 · 截至 #${runs.through_seq}`
      }
    : null
  return (
    <details className="evolution-source-browser">
      <summary>从会话 / Trace 选择</summary>
      <button disabled={disabled || loading} onClick={() => void loadSessions()}>
        读取项目会话
      </button>
      {sessions && (
        <>
          <label>
            筛选已加载会话
            <input
              value={sessionFilter}
              onChange={(e) => setSessionFilter(e.target.value)}
              placeholder="会话名称或角色"
            />
          </label>
          <label>
            参考会话
            <select
              disabled={disabled || loading}
              value={sessionId}
              onChange={(e) => {
                if (e.target.value) {
                  setQuery('')
                  void loadRuns(e.target.value, '')
                }
              }}
            >
              <option value="">选择一个会话</option>
              {sessions.sessions
                .filter((s) =>
                  `${s.title} ${s.role ?? ''}`.toLowerCase().includes(sessionFilter.toLowerCase())
                )
                .map((s) => (
                  <option key={s.session_id} value={s.session_id}>
                    {s.title} · {s.role || '未设角色'}
                  </option>
                ))}
            </select>
          </label>
          {!sessions.sessions.length && <p>此项目还没有会话记录。</p>}
          {!!sessions.unavailable_count && <p>{sessions.unavailable_count} 个会话暂不可读。</p>}
          {sessions.next_cursor && (
            <button
              disabled={disabled || loading}
              onClick={() => void loadSessions(sessions.next_cursor)}
            >
              加载更多会话
            </button>
          )}
        </>
      )}
      {runs && (
        <>
          <p className="evolution-range-total">
            此会话共{' '}
            <strong>
              {runs.total_runs} 轮运行、{runs.total_events} 条 Trace 事件
            </strong>
            。 当前已选 {selectedHere.length} 个范围。
          </p>
          <label>
            选材范围
            <select
              aria-label="选材范围"
              disabled={disabled || loading}
              value={mode}
              onChange={(e) => {
                const next = e.target.value
                if (next === 'session' || next === 'run' || next === 'event') changeMode(next)
              }}
            >
              <option value="session">整个会话：所有已记录的 Trace</option>
              <option value="run">指定运行：多选完整轮次</option>
              <option value="event">指定事件：多选具体步骤</option>
            </select>
          </label>
          <p className="muted">
            切换范围会清除本会话的旧选择。选择固定到显示的截止序号，之后新增内容不会自动混入。
          </p>
          {mode === 'session' && whole ? (
            <label className="evolution-range-total">
              <input
                type="checkbox"
                disabled={disabled}
                checked={selected.some((s) => evidenceKey(s.source) === evidenceKey(whole.source))}
                onChange={() => toggle(whole)}
              />{' '}
              参考整个会话 · {runs.total_runs} 轮 / {runs.total_events} 条事件
            </label>
          ) : (
            <>
              <form
                className="evolution-row"
                onSubmit={(e) => {
                  e.preventDefault()
                  void loadRuns(sessionId, query)
                }}
              >
                <input
                  aria-label="搜索全部运行"
                  placeholder="按提问搜索整个会话，包含更早运行"
                  value={query}
                  disabled={disabled || loading}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button disabled={disabled || loading}>搜索运行</button>
              </form>
              <p>
                已加载 {runs.runs.length} / {runs.matched_runs} 轮
                {appliedQuery && `（搜索：${appliedQuery}）`}， 每轮的工具数量不影响此列表。
                {mode === 'event' && '先打开某轮，再勾选具体事件。'}
              </p>
              {mode === 'run' && (
                <button
                  disabled={disabled || !runs.runs.length}
                  onClick={() => {
                    const added = runs.runs.map(runSelection)
                    const keys = new Set(added.map((s) => evidenceKey(s.source)))
                    onChange([
                      ...selected.filter((s) => !keys.has(evidenceKey(s.source))),
                      ...added
                    ])
                  }}
                >
                  选中已加载的 {runs.runs.length} 轮
                </button>
              )}
              <div className="evolution-run-list">
                {runs.runs.map((run) => (
                  <div className="evolution-entry" key={run.run_id}>
                    {mode === 'run' ? (
                      <label>
                        <input
                          type="checkbox"
                          disabled={disabled}
                          checked={selected.some(
                            (s) => evidenceKey(s.source) === evidenceKey(runSelection(run).source)
                          )}
                          onChange={() => toggle(runSelection(run))}
                        />
                        指定运行 · {run.prompt} · {run.event_count} 条事件
                      </label>
                    ) : (
                      <strong>{run.prompt}</strong>
                    )}
                    <small>
                      {new Date(run.at).toLocaleString()} · {run.status} · {run.event_count} 条事件
                    </small>
                    {mode === 'event' ? (
                      <button disabled={disabled || loading} onClick={() => void loadEvents(run)}>
                        选择本轮事件
                      </button>
                    ) : (
                      <button onClick={() => onTrace(runSelection(run).source)}>
                        查看整轮 Trace
                      </button>
                    )}
                  </div>
                ))}
              </div>
              {!runs.runs.length && <p>没有匹配的运行，修改搜索内容即可。</p>}
              {runs.before_seq && (
                <button
                  disabled={disabled || loading}
                  onClick={() => void loadRuns(sessionId, appliedQuery, runs.before_seq)}
                >
                  加载更早运行（保留当前列表）
                </button>
              )}
              {mode === 'event' && events && eventRun && (
                <section className="evolution-event-list" aria-label="选择具体事件">
                  <div className="card-heading">
                    <strong>{eventRun.prompt}</strong>
                    <button
                      onClick={() => {
                        setEvents(null)
                        setEventRun(null)
                      }}
                    >
                      收起事件列表
                    </button>
                  </div>
                  <p>
                    已加载 {events.items.length}{' '}
                    条事件；勾选一条只参考该条，工具事件包含配对的调用与结果。
                  </p>
                  {events.items.map((row) => {
                    const ref: EvolutionSource = {
                      scope: 'event',
                      session_id: sessionId,
                      run_id: row.run_id,
                      seq: row.seq,
                      through_seq: events.watermark
                    }
                    return (
                      <div className="evolution-entry" key={row.seq}>
                        <label>
                          <input
                            type="checkbox"
                            disabled={disabled}
                            checked={selected.some(
                              (s) => evidenceKey(s.source) === evidenceKey(ref)
                            )}
                            onChange={() =>
                              toggle({
                                source: ref,
                                label: `单条事件 · ${runs.title} · #${row.seq} ${row.title}`
                              })
                            }
                          />
                          单条事件 #{row.seq} · {row.title} · {row.status}
                        </label>
                        <button onClick={() => onTrace(ref)}>查看这条事件</button>
                      </div>
                    )
                  })}
                  {events.before_seq && (
                    <button
                      disabled={disabled || loading}
                      onClick={() => void loadEvents(eventRun, events.before_seq)}
                    >
                      加载更早事件（保留当前列表）
                    </button>
                  )}
                </section>
              )}
            </>
          )}
          {!!selectedHere.length && (
            <button
              disabled={disabled}
              onClick={() =>
                onChange(
                  selected.filter(
                    (s) => s.source.session_id !== sessionId || !!s.source.diagnostic_id
                  )
                )
              }
            >
              清空本会话选择
            </button>
          )}
          <p className="muted">
            选择范围与实际发送量是两回事。生成前预览会显示匹配事件数、完整引用、部分引用和省略数量。
          </p>
        </>
      )}
      {loading && <p role="status">正在读取目录…</p>}
      {error && <p role="alert">{error}</p>}
    </details>
  )
}
