/** 可返回的团队设计讨论，使用原模型运行和组队入口。 Resumable team design using existing runs and assembly. */
import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  ModelId,
  SaveTeamDesignParams,
  SpaceConfig,
  TeamDesignView
} from '../../generated/protocol'
import { Markdown } from './Markdown'
import { ModelActivity } from './ModelActivity'
import { Trace } from './Trace'
import { useDesignSession } from './useDesignSession'
import './TeamDesigner.css'

type Props = {
  taskId: string
  modelId: ModelId
  connected: boolean
  config: SpaceConfig | null
  onDraft: (config: SpaceConfig, source: 'restore' | 'model') => void
  onStarted: () => void
}

/** 只比较 UI 配置内容，忽略对象属性顺序。 Compare UI configuration independent of object key order. */
function graphKey(config: SpaceConfig | null | undefined): string {
  return JSON.stringify(config, (_key, value: unknown) =>
    value && typeof value === 'object' && !Array.isArray(value)
      ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)))
      : value
  )
}

/** 保存讨论与图，页面离开不影响运行。 Save conversation inputs and graph without stopping work on navigation. */
export function TeamDesigner({ taskId, modelId, connected, config, onDraft, onStarted }: Props) {
  const [design, setDesign] = useState<TeamDesignView | null>(null)
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [trace, setTrace] = useState(false)
  const callbacks = useRef({ onDraft, onStarted })
  callbacks.current = { onDraft, onStarted }
  const mounted = useRef(true)
  const savedGraph = useRef('')
  const queued = useRef<SaveTeamDesignParams | null>(null)
  const chain = useRef<Promise<void>>(Promise.resolve())
  const inputVersion = useRef(0)
  const sendOperation = useRef<{ text: string; id: string } | null>(null)
  const startOperation = useRef<{ config: string; id: string } | null>(null)
  const {
    view,
    entries,
    cursor,
    loadOlder,
    historyBusy,
    error: historyError
  } = useDesignSession(design?.session_id, connected)
  const running =
    view?.summary.run?.status === 'running' || view?.summary.run?.status === 'stopping'
  const history = useRef<HTMLDivElement>(null)
  const following = useRef(true)

  /** 串行保存待提交字段，关闭时也保留最后输入。 Serialize pending fields, including the last input on close. */
  const flush = useCallback(async (): Promise<void> => {
    const params = queued.current
    queued.current = null
    if (params) {
      const pending = chain.current.then(async () => {
        const result = await window.agent.saveTeamDesign(params)
        if (!result.ok) throw new Error(result.error.message)
        if (params.config) savedGraph.current = graphKey(params.config)
      })
      chain.current = pending.catch((cause: unknown) => {
        queued.current = { ...params, ...queued.current }
        if (mounted.current) setError(cause instanceof Error ? cause.message : '设计草稿保存失败。')
      })
      await pending
    } else await chain.current
  }, [])

  useEffect(() => {
    mounted.current = true
    let disposed = false
    if (connected)
      void window.agent
        .openTeamDesign({ task_id: taskId, model_id: modelId })
        .then((result) => {
          if (disposed) return
          if (!result.ok) {
            setError(result.error.message)
            return
          }
          setDesign(result.data)
          setInput(result.data.input_text ?? '')
          savedGraph.current = graphKey(result.data.config)
          if (result.data.config) callbacks.current.onDraft(result.data.config, 'restore')
        })
        .catch((cause: unknown) => {
          if (!disposed) setError(cause instanceof Error ? cause.message : '团队设计打开失败。')
        })
    return () => {
      disposed = true
      mounted.current = false
      void flush().catch(() => undefined)
    }
  }, [taskId, connected, modelId, flush])

  useEffect(() => {
    if (!design) return
    const serialized = graphKey(config)
    if (config && serialized !== savedGraph.current)
      queued.current = { ...queued.current, task_id: taskId, config }
    const timer = setTimeout(() => {
      void flush().catch(() => undefined)
    }, 250)
    return () => clearTimeout(timer)
  }, [config, input, design?.session_id, flush, taskId])

  useEffect(() => {
    if (!design || !connected) return
    let disposed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let fetching = false
    /** 读取保存后的图，不用生成中的 JSON 片段改图。 Read committed graphs, never partially streamed JSON. */
    const refresh = async (): Promise<void> => {
      if (fetching || disposed) return
      fetching = true
      try {
        await chain.current
        const result = await window.agent.getTeamDesign({ task_id: taskId })
        if (disposed) return
        if (!result.ok) {
          setError(result.error.message)
          return
        }
        setDesign(result.data)
        if (
          !queued.current?.config &&
          result.data.config &&
          graphKey(result.data.config) !== savedGraph.current
        ) {
          savedGraph.current = graphKey(result.data.config)
          callbacks.current.onDraft(result.data.config, 'model')
        }
      } catch (cause) {
        if (!disposed) setError(cause instanceof Error ? cause.message : '团队图刷新失败。')
      } finally {
        fetching = false
      }
    }
    const unsubscribe = window.agent.onSessionEvent((signal) => {
      if (
        signal.session_id === design.session_id &&
        (signal.kind === 'changed' || signal.kind === 'resync') &&
        !timer
      )
        timer = setTimeout(() => {
          timer = undefined
          void refresh()
        }, 100)
    })
    void refresh()
    return () => {
      disposed = true
      unsubscribe()
      if (timer) clearTimeout(timer)
    }
  }, [design?.session_id, connected, taskId, view?.watermark])

  useEffect(() => {
    if (following.current && history.current)
      history.current.scrollTop = history.current.scrollHeight
  }, [view?.watermark, view?.delta_index])

  /** 输入立即进入待保存队列，发送不丢失接纳期间的新输入。 Queue input immediately without clearing newer typing. */
  function editInput(text: string): void {
    inputVersion.current++
    setInput(text)
    queued.current = { ...queued.current, task_id: taskId, input_text: text }
  }

  /** 新要求进入当前设计会话，运行中使用已有追加机制。 Send or steer the same design session. */
  async function send(): Promise<void> {
    if (busy || !input.trim() || !design) return
    setBusy(true)
    setError('')
    setNotice('')
    const version = inputVersion.current
    if (sendOperation.current?.text !== input)
      sendOperation.current = { text: input, id: crypto.randomUUID() }
    try {
      await flush()
      const result = await window.agent.sendTeamDesign({
        task_id: taskId,
        operation_id: sendOperation.current.id,
        content: input
      })
      if (!result.ok) throw new Error(result.error.message)
      sendOperation.current = null
      if (!mounted.current) return
      setDesign(result.data)
      if (inputVersion.current === version) setInput('')
      setNotice(running ? '补充要求已保存，将在当前步骤结束后处理。' : '')
    } catch (cause) {
      if (mounted.current)
        setError(cause instanceof Error ? cause.message : '发送失败，输入已保留。')
    } finally {
      if (mounted.current) setBusy(false)
    }
  }

  /** 确认当前图，一次接纳创建和启动；相同输入失败后复用操作 ID。 Confirm and start once; unchanged failed requests keep their operation ID. */
  async function start(): Promise<void> {
    if (!config?.members?.length || busy) return
    setBusy(true)
    setError('')
    setNotice('正在保存团队并创建成员会话…')
    const payload = graphKey(config)
    const prior = [...(design?.launches ?? [])]
      .reverse()
      .find((launch) => graphKey(launch.config) === payload)
    if (startOperation.current?.config !== payload)
      startOperation.current = {
        config: payload,
        id: prior ? prior.operation_id : crypto.randomUUID()
      }
    try {
      await flush()
      const result = await window.agent.startTeamDesign({
        task_id: taskId,
        operation_id: startOperation.current.id,
        config
      })
      if (!result.ok) throw new Error(result.error.message)
      if (!mounted.current) return
      setDesign(result.data)
      const launch = result.data.launches?.at(-1)
      if (launch?.error) {
        setError(launch.error)
        setNotice('已创建的成员和成果已保留。')
      } else setNotice('团队已开始工作。可关闭设计进入合作群聊，或从左侧打开成员会话。')
      callbacks.current.onStarted()
    } catch (cause) {
      if (mounted.current)
        setError(cause instanceof Error ? cause.message : '启动失败，已完成步骤保留。')
    } finally {
      if (mounted.current) setBusy(false)
    }
  }

  /** 停止真实设计 Run，保留原讨论和图。 Stop the design Run while retaining discussion and graph. */
  async function stop(): Promise<void> {
    if (!view?.summary.run) return
    const result = await window.agent.cancelRun(view.summary.run.run_id)
    if (!result.ok) setError(result.error.message)
  }

  /** 模型选择只影响下一请求，沿用会话配置接口。 Model selection affects the next request via the session API. */
  async function selectModel(value: string): Promise<void> {
    if (!design || (value !== 'glm-5.3-flash' && value !== 'deepseek-v4.1-flash')) return
    try {
      const result = await window.agent.selectSessionModel({
        session_id: design.session_id,
        operation_id: crypto.randomUUID(),
        model_id: value
      })
      if (!result.ok) setError(result.error.message)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '模型选择保存失败。')
    }
  }

  return (
    <section className="team-design-chat" aria-label="团队设计讨论">
      <header>
        <h3>团队设计</h3>
        <span>
          {running
            ? '讨论进行中'
            : config?.members?.length
              ? '图已生成 · 可继续调整'
              : '描述目标，开始设计'}
        </span>
      </header>
      <p className="muted">可以切换页面后从左侧「团队设计」返回。确认前不会创建或启动成员。</p>
      <div
        className="team-design-history"
        ref={history}
        onScroll={(event) => {
          const element = event.currentTarget
          following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 40
        }}
      >
        {cursor !== null && (
          <button disabled={historyBusy} onClick={() => void loadOlder()}>
            更早讨论
          </button>
        )}
        {entries
          .filter((entry) => entry.kind !== 'assistant' || entry.text || entry.reasoning)
          .map((entry) =>
            entry.kind === 'user' || entry.kind === 'assistant' || entry.kind === 'run.finished' ? (
              <article key={entry.seq} className={`design-message ${entry.kind}`}>
                <strong>
                  {entry.kind === 'user'
                    ? '你'
                    : entry.kind === 'assistant'
                      ? '团队设计助手'
                      : '本轮结果'}
                </strong>
                {entry.reasoning && (
                  <details open>
                    <summary>思考</summary>
                    <pre>{entry.reasoning}</pre>
                  </details>
                )}
                <Markdown text={entry.text || entry.partial_text || ''} />
              </article>
            ) : entry.kind === 'tool.started' ? (
              <div className="design-action" key={entry.seq}>
                {entry.call?.name === 'save_team_draft'
                  ? '更新团队与协作图'
                  : entry.call?.name === 'read_team_design'
                    ? '读取当前团队图'
                    : `调用 ${entry.call?.name}`}{' '}
                <button className="text-button" onClick={() => setTrace(true)}>
                  Trace
                </button>
              </div>
            ) : null
          )}
        {(view?.stream_text || view?.stream_reasoning) && (
          <article className="design-message">
            <strong>团队设计助手</strong>
            {view.stream_reasoning && (
              <details open>
                <summary>思考 · 接收中</summary>
                <pre>{view.stream_reasoning}</pre>
              </details>
            )}
            <Markdown text={view.stream_text} />
          </article>
        )}
      </div>
      {(error || historyError) && <p role="alert">{error || historyError}</p>}
      {notice && <p role="status">{notice}</p>}
      {view?.model_progress && (
        <ModelActivity
          progress={view.model_progress}
          active={!!running}
          compact
          timeoutSeconds={view.summary.run?.limits.request_timeout_seconds}
        />
      )}
      <textarea
        aria-label="团队设计输入"
        placeholder="描述目标，或说说想怎样调整团队和协作图…"
        value={input}
        onChange={(event) => editInput(event.target.value)}
        disabled={!design || !connected}
      />
      <div className="team-design-actions">
        <select
          aria-label="团队设计模型"
          value={view?.summary.model_id ?? modelId}
          disabled={!design || !connected}
          onChange={(event) => void selectModel(event.target.value)}
        >
          <option value="glm-5.3-flash">GLM-5.3-Flash</option>
          <option value="deepseek-v4.1-flash">DeepSeek V4.1 Flash</option>
        </select>
        <button
          disabled={!connected || busy || !input.trim() || !design}
          onClick={() => void send()}
        >
          {running ? '追加要求' : '发送设计要求'}
        </button>
        {running && <button onClick={() => void stop()}>停止设计</button>}
        <button disabled={!design} onClick={() => setTrace(true)}>
          查看 Trace
        </button>
      </div>
      <div className="team-design-launch">
        {design?.objective && (
          <details className="design-objective">
            <summary>团队启动目标</summary>
            <Markdown text={design.objective} />
          </details>
        )}
        <button
          className="primary"
          disabled={!connected || busy || running || !config?.members?.length}
          onClick={() => void start()}
        >
          确认并开始工作
        </button>
        <button
          disabled={!design || busy}
          onClick={() =>
            void flush()
              .then(() => setNotice('设计已保存，可稍后返回并开始。'))
              .catch(() => undefined)
          }
        >
          保存，稍后开始
        </button>
      </div>
      {trace && design && (
        <Trace
          projectId={view?.summary.project_id ?? ''}
          sessionId={design.session_id}
          revision={view?.watermark ?? 0}
          focusSeq={null}
          onClose={() => setTrace(false)}
        />
      )}
    </section>
  )
}
