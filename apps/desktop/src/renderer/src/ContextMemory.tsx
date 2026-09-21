import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { ContextView, HistoryPage, HistoryParams, MemoryPage } from '../../generated/protocol'
import type { Result } from '../../shared/api'
import { KnowledgeDetails, type QuestionMaterial } from './KnowledgeDetails'
import { MemoryManager, type MemoryDraft } from './MemoryManager'

type Panel = 'context' | 'history' | 'memory'
/** 每会话独立的查看缓存，不与业务状态混用。
 * Per-session viewer cache, separate from business state. */
export type KnowledgeUi = {
  panel: Panel | null
  folds: Record<string, boolean>
  query: string
  includeLookups?: boolean
  artifactId: string
  historyRequest: HistoryParams | null
  history: HistoryPage | null
  relatedHistory?: Record<number, HistoryPage['items'][number]>
  memory?: MemoryDraft
}

/** 十进制 K / M 展示 token，不根据字节猜测。
 * Format decimal K / M tokens without estimating from bytes. */
function formatTokens(value: number | null | undefined): string {
  if (value == null) return '未知'
  if (value >= 1_000_000) return `${Number((value / 1_000_000).toFixed(2))}M`
  if (value >= 1_000) return `${Number((value / 1_000).toFixed(1))}K`
  return String(value)
}

const jobLabels: Record<string, string> = {
  preparing: '准备压缩',
  receiving: '生成摘要中',
  ready: '摘要已生成，下次请求采用',
  adopted: '已用于请求窗口',
  failed: '失败',
  cancelled: '已停止',
  interrupted: '已中断'
}

/** 三个紧凑入口共享可关闭面板；后台刷新从不改变查看状态。
 * Three compact entries share a closeable panel; updates never change disclosure state. */
export function ContextMemory({
  sessionId,
  revision,
  connected,
  cache,
  onAttach
}: {
  sessionId: string
  revision: number
  connected: boolean
  cache: Map<string, KnowledgeUi>
  onAttach: (material: QuestionMaterial) => void
}) {
  const [ui, setUi] = useState<KnowledgeUi>(
    () =>
      cache.get(sessionId) ?? {
        panel: null,
        folds: {},
        query: '',
        artifactId: '',
        historyRequest: null,
        history: null
      }
  )
  const uiRef = useRef(ui)
  const [context, setContext] = useState<ContextView | null>(null)
  const [memory, setMemory] = useState<MemoryPage | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [memorySeed, setMemorySeed] = useState<{ text: string; id: number } | null>(null)
  const entries = useRef<Partial<Record<Panel, HTMLButtonElement | null>>>({})
  const closeButton = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (ui.panel) closeButton.current?.focus({ preventScroll: true })
  }, [ui.panel])
  const live = useRef(true)
  useEffect(() => {
    live.current = true
    return () => {
      live.current = false
    }
  }, [])

  /** 同步保存查看状态，卸载后返回也能接续。
   * Cache viewer state synchronously so it survives session switches. */
  function update(patch: Partial<KnowledgeUi>) {
    const next = { ...uiRef.current, ...patch }
    uiRef.current = next
    cache.set(sessionId, next)
    setUi(next)
  }
  /** 仅用户操作修改折叠状态。 Only user actions change disclosures. */
  function fold(key: string, open: boolean) {
    update({ folds: { ...uiRef.current.folds, [key]: open } })
  }
  /** 关闭释放布局空间并还原焦点，保留查询和草稿。
   * Close and restore focus while retaining queries and drafts. */
  function close() {
    const previous = ui.panel
    update({ panel: null })
    if (previous) entries.current[previous]?.focus()
  }
  useEffect(
    () =>
      window.agent.onSessionEvent((event) => {
        if (event.session_id === sessionId && event.kind === 'changed')
          setRefresh((value) => value + 1)
      }),
    [sessionId]
  )
  useEffect(() => {
    let cancelled = false
    void Promise.all([
      window.agent.getContext({ session_id: sessionId }),
      window.agent.listMemory({ session_id: sessionId })
    ])
      .then(([a, b]) => {
        if (cancelled) return
        if (a.ok) setContext(a.data)
        else setError(a.error.message)
        if (b.ok) setMemory(b.data)
        else setError(b.error.message)
      })
      .catch(() => {
        if (!cancelled) setError('无法读取上下文状态，请检查后端连接。')
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, revision, refresh])

  /** 保留失败并忽略卸载后的回包；关闭不取消操作。
   * Keep failures and ignore unmounted responses; closing never cancels work. */
  async function perform<T>(request: Promise<Result<T>>, accept: (value: T) => void) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await request
      if (!live.current) return
      if (result.ok) accept(result.data)
      else setError(result.error.message)
    } catch {
      if (live.current) setError('未收到操作结果，请检查连接并刷新状态；没有自动重试。')
    } finally {
      if (live.current) setBusy(false)
    }
  }
  /** 固定查询参数用于续页，异步结果不打开已关闭区域。
   * Snapshot query parameters for pagination; results never reopen closed viewers. */
  function searchHistory(params?: HistoryParams, append = false) {
    const request = params ?? {
      session_id: sessionId,
      query: ui.query,
      include_lookup_results: ui.includeLookups ?? false,
      artifact_id: ui.artifactId.trim() || null
    }
    if (!append) {
      update({ historyRequest: request, relatedHistory: {} })
      fold('history-results', true)
    }
    void perform(window.agent.readHistory(request), (value) => {
      const previous = uiRef.current.history
      update({
        history:
          append && previous
            ? { ...value, matches: previous.matches, items: [...previous.items, ...value.items] }
            : value
      })
    })
  }
  /** 续读扩展原文而不替换其他结果；仍保留整个条目的收起操作。
   * Append original text without replacing other results or losing collapse controls. */
  function readMore(item: HistoryPage['items'][number], fromStart = false, related = false) {
    if (!ui.historyRequest) return
    void perform(
      window.agent.readHistory({
        session_id: sessionId,
        entry_seq: item.seq || null,
        artifact_id: related ? null : ui.historyRequest.artifact_id,
        offset: fromStart ? 0 : (item.next_offset ?? 0)
      }),
      (page) => {
        const previous = uiRef.current.history
        const next = page.items[0]
        if (!previous || !next) return
        const expanded = fromStart
          ? next
          : { ...next, offset: item.offset, text: item.text + next.text }
        if (related) {
          update({ relatedHistory: { ...uiRef.current.relatedHistory, [item.seq]: expanded } })
          return
        }
        update({
          history: {
            ...previous,
            items: previous.items.map((old) => (old.seq === item.seq ? expanded : old))
          }
        })
      }
    )
  }
  /** 关联材料单独展开，保持搜索结果与关键词快照。
   * Expand linked source separately, preserving the search results and query snapshot. */
  function readRelated(seq: number) {
    fold(`history-related-${seq}`, true)
    if (uiRef.current.relatedHistory?.[seq]) return
    void perform(window.agent.readHistory({ session_id: sessionId, entry_seq: seq }), (page) => {
      const item = page.items[0]
      if (item) update({ relatedHistory: { ...uiRef.current.relatedHistory, [seq]: item } })
    })
  }

  /** 展示真实原文范围，按需续读或从头展开。
   * Show the original character range and offer continuation or a read from the start. */
  function fragment(item: HistoryPage['items'][number], related = false) {
    return (
      <>
        <pre>{item.text}</pre>
        <p className="muted">
          {item.kind}
          {item.tool_name ? ` · ${item.tool_name}` : ''} · 原文字符范围 {item.offset}–
          {item.offset + Array.from(item.text).length} / {item.total_chars}（从 0 起）
        </p>
        {item.offset > 0 && (
          <button type="button" disabled={busy} onClick={() => readMore(item, true, related)}>
            从头查看
          </button>
        )}
        {item.next_offset != null && (
          <button type="button" disabled={busy} onClick={() => readMore(item, false, related)}>
            继续展开原文
          </button>
        )}
      </>
    )
  }
  /** 折叠键由会话缓存管理，数据刷新不影响打开状态。
   * Session-cached keys keep disclosure state independent of data refresh. */
  function detail(key: string, title: string, children: ReactNode) {
    return (
      <KnowledgeDetails
        key={key}
        testId={key}
        title={title}
        open={ui.folds[key] ?? false}
        onToggle={(open) => fold(key, open)}
      >
        {children}
      </KnowledgeDetails>
    )
  }
  /** 明确选中已查看的快照，发送前可在输入区移除。
   * Explicitly attach the viewed snapshot, removable in the composer before sending. */
  function attach(material: QuestionMaterial) {
    onAttach(material)
    setNotice('已加入这次提问，可在输入区移除；发送后才会带给模型。')
  }
  const tokens = context?.tokens
  const tokenStatus = tokens
    ? {
        reported: `上次输入 ${formatTokens(tokens.input_tokens)}`,
        not_measured: '尚未计量',
        not_reported: '输入用量未返回',
        model_changed: '切换模型后待计量',
        compacted: '压缩后待计量'
      }[tokens.status ?? 'not_measured']
    : '…'
  const percentage =
    tokens?.status === 'reported' && tokens.input_tokens != null && tokens.window_tokens
      ? (tokens.input_tokens / tokens.window_tokens) * 100
      : null
  const working = context?.job?.status === 'preparing' || context?.job?.status === 'receiving'
  const request = context?.last_request
  const adoptedMemories =
    request?.manifest.materials?.filter((item) => item.kind === 'memory') ?? []
  return (
    <div className="knowledge-panel" data-testid="context-memory">
      <div className="knowledge-entries">
        {(['context', 'history', 'memory'] as const).map((kind) => (
          <button
            type="button"
            key={kind}
            ref={(element) => {
              entries.current[kind] = element
            }}
            data-testid={`open-${kind}`}
            aria-expanded={ui.panel === kind}
            onClick={() => (ui.panel === kind ? close() : update({ panel: kind }))}
          >
            {kind === 'context' ? (
              <>
                上下文 · {tokenStatus}
                {tokens && ` / ${formatTokens(tokens.window_tokens)} token`}
                {percentage != null &&
                  `（${percentage > 0 && percentage < 0.1 ? '<0.1' : Number(percentage.toFixed(1))}%）`}
                {working ? ' · 压缩中' : context?.checkpoint ? ' · 已压缩' : ''}
              </>
            ) : kind === 'history' ? (
              '查找历史'
            ) : (
              `记忆 · 上次带入 ${request ? adoptedMemories.length : '未记录'} 条`
            )}
          </button>
        ))}
      </div>
      <div
        hidden={!ui.panel}
        className="knowledge-viewer"
        role="region"
        aria-label="上下文与记忆查看面板"
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.stopPropagation()
            close()
          }
        }}
      >
        <header className="knowledge-toolbar">
          <strong>
            {ui.panel === 'history' ? '查找历史' : ui.panel === 'memory' ? '记忆管理' : '上下文'}
          </strong>
          <button type="button" ref={closeButton} onClick={close}>
            关闭面板
          </button>
        </header>
        <div className="knowledge-body">
          {error && <p role="alert">{error}</p>}
          {notice && <p role="status">{notice}</p>}
          {!context && !error && <p>正在读取状态…</p>}
          <div hidden={ui.panel !== 'context'}>
            {context && (
              <>
                <p className="muted">
                  当前模型 {tokens?.model_id} · 窗口 {formatTokens(tokens?.window_tokens)} token。
                  用量来自最近主请求，尚未发送的内容不计入。
                </p>
                {detail(
                  'request-materials',
                  '上次实际发送的材料',
                  <>
                    {request ? (
                      <>
                        <p>
                          {request.model_id} · {new Date(request.at).toLocaleString()} ·{' '}
                          {request.manifest.message_count} 条消息。
                          以下为请求时的固定记录，后来的设置和记忆修改不会改写它。
                        </p>
                        {request.manifest.materials?.map((item, index) =>
                          detail(
                            `material-${request.message_id}-${index}`,
                            `${item.title} · ${item.form === 'fragment' ? '片段' : item.form === 'summary' ? '摘要' : item.form === 'full' ? '完整材料' : '参考材料'}`,
                            <>
                              <p>
                                {item.reason}
                                {item.revision != null && ` · 当时修订 ${item.revision}`}
                              </p>
                              <pre>{item.preview || '仅记录来源。'}</pre>
                              {!item.preview_complete && (
                                <p className="muted">
                                  这里只显示预览，实际发送范围由“完整材料 / 片段”标记说明。
                                </p>
                              )}
                              {item.kind === 'history' && (
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() => {
                                    update({ panel: 'history', query: '', artifactId: '' })
                                    fold('history-query', true)
                                    searchHistory({
                                      session_id: sessionId,
                                      entry_seq: Number(item.source_id)
                                    })
                                  }}
                                >
                                  查看历史原文
                                </button>
                              )}
                              {item.kind === 'memory' && (
                                <p className="muted">
                                  当前版本可在记忆入口按标题“{item.title}
                                  ”查找；它可能已被修改或遗忘。
                                </p>
                              )}
                              <p className="muted">
                                {item.read_tool
                                  ? `回读：${item.read_tool} ${JSON.stringify(item.read_arguments)}`
                                  : '来自宿主提供的运行材料。'}
                              </p>
                            </>
                          )
                        )}
                        {detail(
                          'request-tools',
                          '系统指令与工具',
                          <p>
                            系统指令包含当前模式、工作方法及活动 Goal（如有），工具定义也计入请求。
                            工具：{request.manifest.tool_names.join('、')}。请求 JSON{' '}
                            {request.manifest.request_bytes.toLocaleString()} 字节。
                          </p>
                        )}
                      </>
                    ) : (
                      <p>尚无请求材料记录。旧请求不倒推；下一次模型请求后显示实际采用项。</p>
                    )}
                  </>
                )}
                {detail(
                  'next-context',
                  '下次如何组装上下文',
                  <p>
                    保留最新输入和近期历史；{context.checkpoint ? '采用已保存摘要；' : '尚无摘要；'}
                    刷新任务目标、结论和协作结果；
                    {memory?.state.settings?.use
                      ? '按当前问题带入相关记忆。'
                      : '自动带入记忆已关闭。'}
                    已选材料随提问发送。此处是组装规则，实际清单在请求发出时确定。
                  </p>
                )}
                <div className="knowledge-actions">
                  <label>
                    <input
                      type="checkbox"
                      checked={context.settings.automatic ?? true}
                      disabled={busy || !connected}
                      onChange={(e) =>
                        void perform(
                          window.agent.configureContext({
                            session_id: sessionId,
                            settings: { ...context.settings, automatic: e.target.checked }
                          }),
                          setContext
                        )
                      }
                    />
                    自动压缩会话
                  </label>
                  <button
                    type="button"
                    disabled={busy || !connected || working}
                    onClick={() =>
                      void perform(
                        window.agent.compactContext({ session_id: sessionId }),
                        setContext
                      )
                    }
                  >
                    压缩当前会话
                  </button>
                  {working && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void perform(
                          window.agent.cancelCompaction({ session_id: sessionId }),
                          setContext
                        )
                      }
                    >
                      停止压缩
                    </button>
                  )}
                </div>
                <p>
                  下次历史估计 {formatTokens(context.estimated_history_tokens)} token； 下次输入预计{' '}
                  {formatTokens(context.estimated_input_tokens)} token。
                  {context.estimate_basis}；新输入和运行时变化尚未计入。
                </p>
                {context.migrated_from_bytes && (
                  <p className="muted">
                    旧字节比例设置已迁移为绝对 token
                    初值；自动开关与自定义生成额度保留，可在下方调整。
                  </p>
                )}
                <p className="muted">
                  手动压缩只保留最新要求与末尾必要交互；自动压缩先缩短已消费的长工具结果，再按近期
                  token 目标选择摘要切点。原历史可回读，不自动保存为长期记忆。
                </p>
                {context.job && (
                  <p>
                    压缩：
                    {context.job.outcome === 'trimmed'
                      ? '工具结果已减量'
                      : context.job.outcome === 'not_smaller' || context.job.outcome === 'nothing'
                        ? '无需采用新摘要'
                        : context.job.status === 'ready' && context.job.requests === 0
                          ? '无需新增摘要，保留近期内容'
                          : (jobLabels[context.job.status] ?? context.job.status)}
                    。{context.job.message}
                    {context.job.status === 'failed' &&
                      ' 原历史保留，请根据上方错误处理后手动再次压缩。'}
                  </p>
                )}
                {context.job?.history_before_tokens != null &&
                  context.job.history_after_tokens != null && (
                    <p>
                      本次历史估计：{context.job.history_before_tokens.toLocaleString()} →{' '}
                      {context.job.history_after_tokens.toLocaleString()} token （减少{' '}
                      {context.job.history_before_tokens > 0
                        ? Math.round(
                            (1 -
                              context.job.history_after_tokens /
                                context.job.history_before_tokens) *
                              100
                          )
                        : 0}
                      %）。同一快照对比，不含系统提示与工具定义；后续输入 token 以模型报告为准。
                      {context.job.retained_tokens != null &&
                        ` 保留原文及预览约 ${formatTokens(context.job.retained_tokens)} token。`}
                    </p>
                  )}
                {context.checkpoint &&
                  detail('summary', '查看摘要', <pre>{context.checkpoint.text}</pre>)}
                {detail(
                  'context-advanced',
                  '压缩参数与计量详情',
                  <>
                    <p>
                      上次输入 {tokens?.input_tokens?.toLocaleString() ?? '未知'} token；窗口来源{' '}
                      {tokens?.window_source}。 自动整理起点为{' '}
                      {formatTokens(context.trigger_tokens)} token，受模型可用容量约束。
                    </p>
                    <p>
                      历史窗口 {context.window_bytes.toLocaleString()} 字节；原历史{' '}
                      {context.raw_bytes.toLocaleString()}{' '}
                      字节。字节仅作排错计量，不是桌面上下文容量。
                    </p>
                    {(
                      [
                        ['auto_trigger_tokens', '自动整理起点（token）'],
                        ['keep_recent_tokens', '自动近期保留目标（token，完整交互可超出）'],
                        ['tool_result_preview_tokens', '旧工具结果预览目标（token，0 仅引用）'],
                        ['summary_target_tokens', '摘要正文目标（token）'],
                        ['summary_output_tokens', '摘要请求输出上限']
                      ] as const
                    ).map(([key, label]) => (
                      <label key={key}>
                        {label}
                        <input
                          type="number"
                          step={1}
                          value={context.settings[key] ?? ''}
                          placeholder={key === 'summary_output_tokens' ? '跟随运行预算' : undefined}
                          onChange={(e) =>
                            setContext({
                              ...context,
                              settings: {
                                ...context.settings,
                                [key]:
                                  key === 'summary_output_tokens' && e.target.value === ''
                                    ? null
                                    : Number(e.target.value)
                              }
                            })
                          }
                        />
                      </label>
                    ))}
                    <p>摘要输出上限留空时跟随运行预算；填写时取较小值，思考可能占用输出额度。</p>
                    <p>
                      摘要正文目标不包含思考；近期目标只用于自动压缩，手动压缩不按此值保留。工具减量只在整理时进行，保留头尾、已有状态和来源，新结果先完整送给模型。
                      参数影响后续整理，已采用的预览不会自动恢复为全文。
                    </p>
                    <button
                      type="button"
                      disabled={busy || !connected}
                      onClick={() =>
                        void perform(
                          window.agent.configureContext({
                            session_id: sessionId,
                            settings: context.settings
                          }),
                          setContext
                        )
                      }
                    >
                      保存压缩参数
                    </button>
                    {context.job && (
                      <p>
                        {context.job.model_id} · 请求 {context.job.requests} · 本次输出上限{' '}
                        {context.job.output_token_limit ?? '未知'} token · 输入{' '}
                        {context.job.usage?.input_tokens ?? '未知'} / 输出{' '}
                        {context.job.usage?.output_tokens ?? '未知'}
                        {context.job.finish_reason && ` · 结束原因 ${context.job.finish_reason}`}
                      </p>
                    )}
                    <p>
                      累计压缩 {context.totals?.requests ?? 0} 次请求；已报告输入{' '}
                      {context.totals?.reported_input_tokens ?? 0} / 输出{' '}
                      {context.totals?.reported_output_tokens ?? 0} token，未知用量作业{' '}
                      {context.totals?.unknown_jobs ?? 0}。 运行内压缩已计入相应 Run，勿重复相加。
                    </p>
                  </>
                )}
              </>
            )}
          </div>
          <div hidden={ui.panel !== 'history'}>
            <p className="muted">
              查看本会话原始记录；仅查看不会发给模型。找到后可加入这次提问或保存为记忆。
            </p>
            {detail(
              'history-query',
              '历史查询条件',
              <>
                <input
                  aria-label="历史搜索"
                  placeholder="关键词，留空查看全部"
                  value={ui.query}
                  onChange={(e) => update({ query: e.target.value })}
                />
                <label>
                  <input
                    type="checkbox"
                    checked={ui.includeLookups ?? false}
                    onChange={(e) => update({ includeLookups: e.target.checked })}
                  />
                  关键词检索也包含先前查找历史 / 状态工具的调用和结果
                </label>
                {detail(
                  'history-archive',
                  '按归档引用读取',
                  <>
                    <p>填写工具结果中的 artifact_id；普通对话无需填写。</p>
                    <input
                      aria-label="归档 ID"
                      value={ui.artifactId}
                      onChange={(e) => update({ artifactId: e.target.value })}
                    />
                  </>
                )}
                <button type="button" disabled={busy || !connected} onClick={() => searchHistory()}>
                  查询历史
                </button>
              </>
            )}
            {detail(
              'history-results',
              ui.history
                ? `历史结果 · ${ui.history.matches} ${ui.history.match_unit === 'occurrences' ? '次出现' : '项匹配'}`
                : '历史结果',
              <>
                {!ui.history ? (
                  <p>尚未查询，请展开历史查询条件。</p>
                ) : (
                  <>
                    <p className="muted">
                      本次关键词：{ui.historyRequest?.query || '全部'} · 已读{' '}
                      {ui.history.items.length} 项。修改条件后点击查询才生效。
                    </p>
                    {!ui.history.items.length && <p>没有匹配记录，可调整关键词或留空查看历史。</p>}
                    {ui.history.items.map((item) =>
                      detail(
                        `history-entry-${item.seq}`,
                        `${item.kind === 'user' ? '你的消息' : item.kind === 'assistant' ? 'Agent 回答' : item.kind === 'artifact' ? '归档输出' : (item.tool_name ?? '工具记录')} · #${item.seq} · ${item.text.replace(/\s+/g, ' ').slice(0, 48)}`,
                        <>
                          {fragment(item)}
                          {(['call_seq', 'result_seq'] as const).map((field) => {
                            const seq = item[field]
                            if (seq == null || seq === item.seq) return null
                            const linked = ui.relatedHistory?.[seq]
                            return (
                              <div key={field}>
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() => readRelated(seq)}
                                >
                                  查看对应{field === 'call_seq' ? '调用' : '结果'} #{seq}
                                </button>
                                {linked &&
                                  detail(
                                    `history-related-${seq}`,
                                    `对应${field === 'call_seq' ? '调用' : '结果'} · #${seq}`,
                                    fragment(linked, true)
                                  )}
                              </div>
                            )
                          })}
                          <button
                            type="button"
                            onClick={() =>
                              attach({
                                key: `history:${sessionId}:${ui.historyRequest?.artifact_id ?? item.seq}:${item.offset}`,
                                title: `历史 #${item.seq}${item.offset > 0 || item.next_offset != null ? '（片段）' : ''}`,
                                source: `session=${sessionId}, seq=${item.seq}, artifact=${ui.historyRequest?.artifact_id ?? ''}, offset=${item.offset}`,
                                text: item.text
                              })
                            }
                          >
                            加入这次提问
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              update({ panel: 'memory' })
                              setMemorySeed({ text: item.text, id: Date.now() })
                            }}
                          >
                            保存为记忆…
                          </button>
                        </>
                      )
                    )}
                    {ui.history.next_after_seq != null && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          searchHistory(
                            {
                              ...ui.historyRequest,
                              session_id: sessionId,
                              after_seq: ui.history?.next_after_seq ?? 0,
                              through_seq: ui.history?.through_seq
                            },
                            true
                          )
                        }
                      >
                        更多历史结果
                      </button>
                    )}
                  </>
                )}
              </>
            )}
          </div>
          <div hidden={ui.panel !== 'memory'}>
            <MemoryManager
              key={sessionId}
              sessionId={sessionId}
              connected={connected}
              observed={memory}
              initial={ui.memory}
              onSaveDraft={(draft) => update({ memory: draft })}
              onChange={setMemory}
              seed={memorySeed}
              onAttach={attach}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
