import { useEffect, useRef, useState, type ReactNode } from 'react'
import type {
  MemoryEntry,
  MemoryFields,
  MemoryPage,
  MemorySettings
} from '../../generated/protocol'
import type { Result } from '../../shared/api'
import { KnowledgeDetails, type QuestionMaterial } from './KnowledgeDetails'

/** 查询快照和未保存正文随会话缓存，关闭查看不会清空。
 * Cache search snapshots and unsaved text per session, independently of visibility. */
export type MemoryDraft = {
  query: string
  filter: string
  includeDisabled: boolean
  filterDisabled: boolean
  page: MemoryPage | null
  folds: Record<string, boolean>
  editing: MemoryEntry | null
  title: string
  content: string
  scope: 'project' | 'user'
  category: string
  pinned: boolean
  sources: string[]
  afterSeq: string
}

/** 管理已有记忆与明确的自动行为，沿用既有 RPC。
 * Manage stored memories and explicit automatic behavior through existing RPCs. */
export function MemoryManager({
  sessionId,
  connected,
  observed,
  initial,
  onSaveDraft,
  onChange,
  seed,
  onAttach
}: {
  sessionId: string
  connected: boolean
  observed: MemoryPage | null
  initial?: MemoryDraft
  onSaveDraft: (draft: MemoryDraft) => void
  onChange: (page: MemoryPage) => void
  seed: { text: string; id: number } | null
  onAttach: (material: QuestionMaterial) => void
}) {
  const [draft, setDraft] = useState<MemoryDraft>(
    () =>
      initial ?? {
        query: '',
        filter: '',
        includeDisabled: false,
        filterDisabled: false,
        page: null,
        folds: {},
        editing: null,
        title: '',
        content: '',
        scope: 'project',
        category: 'fact',
        pinned: false,
        sources: [],
        afterSeq: ''
      }
  )
  const draftRef = useRef(draft)
  const saveDraft = useRef(onSaveDraft)
  saveDraft.current = onSaveDraft
  const [memory, setMemory] = useState(observed)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const live = useRef(true)
  useEffect(() => {
    live.current = true
    return () => {
      live.current = false
    }
  }, [])

  /** 查看与编辑变化即时写入会话缓存。 Cache viewer and editor changes immediately. */
  function update(patch: Partial<MemoryDraft>) {
    const next = { ...draftRef.current, ...patch }
    draftRef.current = next
    setDraft(next)
    saveDraft.current(next)
  }
  useEffect(() => {
    setMemory(observed)
    if (observed && !draftRef.current.page) update({ page: observed })
  }, [observed])
  useEffect(() => {
    if (seed) {
      update({
        editing: null,
        title: '',
        content: seed.text,
        scope: 'project',
        category: 'fact',
        pinned: false,
        folds: { ...draftRef.current.folds, editor: true }
      })
    }
  }, [seed])

  /** 展开状态仅由交互变更，不随后台查询结果变化。
   * Change disclosure state only through interaction, never query completion. */
  function fold(key: string, open: boolean) {
    update({ folds: { ...draftRef.current.folds, [key]: open } })
  }
  /** 每层原文都能独立收起，并保留内容。 Keep each source independently collapsible. */
  function detail(key: string, title: string, children: ReactNode) {
    return (
      <KnowledgeDetails
        key={key}
        testId={`memory-${key}`}
        title={title}
        open={draft.folds[key] ?? false}
        onToggle={(open) => fold(key, open)}
      >
        {children}
      </KnowledgeDetails>
    )
  }
  /** 操作失败显示原原因，不静默重试或清空草稿。
   * Show real failures without silently retrying or clearing drafts. */
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
      if (live.current) setError('未收到操作结果，请检查连接并刷新；没有自动重试。')
    } finally {
      if (live.current) setBusy(false)
    }
  }
  /** 列表更新有独立入口；后台状态变化不覆盖用户的查询快照。
   * Refresh lists explicitly so background status updates preserve search snapshots. */
  function search(append = false) {
    const query = append ? draft.filter : draft.query
    const include_disabled = append ? draft.filterDisabled : draft.includeDisabled
    if (!append) {
      update({ filter: query, filterDisabled: include_disabled })
      fold('results', true)
    }
    void perform(
      window.agent.listMemory({
        session_id: sessionId,
        query,
        include_disabled,
        cursor: append ? draft.page?.next_cursor : null
      }),
      (value) => {
        setMemory(value)
        onChange(value)
        const old = draftRef.current.page
        update({
          page: append && old ? { ...value, entries: [...old.entries, ...value.entries] } : value
        })
      }
    )
  }
  /** 设置影响后续请求，关闭自动行为仍允许用户明确保存。
   * Settings affect later requests while explicit saves remain available. */
  function configure(settings: MemorySettings) {
    void perform(window.agent.configureMemory({ session_id: sessionId, settings }), (value) => {
      setMemory(value)
      onChange(value)
    })
  }
  /** 保留关系字段开始编辑，仅显式选择才替换草稿。
   * Start editing with existing relationships, replacing drafts only on explicit selection. */
  function edit(entry: MemoryEntry | null) {
    update({
      editing: entry,
      title: entry?.title ?? '',
      content: entry?.content ?? '',
      scope: entry?.scope ?? 'project',
      category: entry?.category ?? 'fact',
      pinned: entry?.pinned ?? false
    })
    fold('editor', true)
  }
  /** 业务修改后显示返回列表并说明筛选重置。 Show the returned list after a mutation with an explicit filter reset. */
  function accept(value: MemoryPage) {
    setMemory(value)
    onChange(value)
    update({ page: value, query: '', filter: '', includeDisabled: false, filterDisabled: false })
  }
  /** 保存只改应用记忆；迟到回包不清掉之后输入的新正文。
   * Save app memory without clearing a newer draft on a late response. */
  function save() {
    const submitted = draft
    const entry = draft.editing
    const fields: MemoryFields = {
      title: draft.title,
      content: draft.content,
      scope: draft.scope,
      category: draft.category,
      pinned: draft.pinned,
      enabled: entry?.enabled ?? true,
      stale: false,
      tags: entry?.tags,
      subjects: entry?.subjects,
      valid_from: entry?.valid_from,
      valid_until: entry?.valid_until,
      supersedes: entry?.supersedes,
      related_ids: entry?.related_ids,
      source_ids: entry?.source_ids
    }
    void perform(
      window.agent.saveMemory({
        session_id: sessionId,
        memory_id: entry?.memory_id ?? null,
        fields
      }),
      (value) => {
        accept(value)
        if (
          draftRef.current.title === submitted.title &&
          draftRef.current.content === submitted.content
        )
          update({ title: '', content: '', editing: null })
        setNotice('记忆已保存，列表已刷新为全部。后续请求按相关性带入；实际采用项在上下文中查看。')
      }
    )
  }
  /** 从可编辑字段构建停用操作，不把宿主来源回传为用户字段。
   * Toggle using editable fields without resubmitting host provenance as user fields. */
  function toggle(entry: MemoryEntry) {
    const fields: MemoryFields = {
      title: entry.title,
      content: entry.content,
      scope: entry.scope,
      category: entry.category,
      tags: entry.tags,
      subjects: entry.subjects,
      valid_from: entry.valid_from,
      valid_until: entry.valid_until,
      supersedes: entry.supersedes,
      related_ids: entry.related_ids,
      source_ids: entry.source_ids,
      stale: entry.stale,
      pinned: entry.pinned,
      enabled: !entry.enabled
    }
    void perform(
      window.agent.saveMemory({ session_id: sessionId, memory_id: entry.memory_id, fields }),
      accept
    )
  }
  const settings = memory?.state.settings
  const job = memory?.state.job
  const jobLabel = job
    ? {
        running: '提取中',
        completed: '已完成',
        failed: '失败',
        cancelled: '已停止',
        interrupted: '已中断'
      }[job.status]
    : ''
  return (
    <>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <p>这里管理本项目记忆与跨项目偏好。“上次带入”是最近请求实际使用的数量，不是已保存总数。</p>
      <p className="muted">
        Harness 按当前问题检索相关条目，在后续请求中带入；需要更多内容时使用 search_memory /
        read_memory。 也可以直接说“记住这个项目用
        uv”。临时进度放在任务报告，任务决定放在已确认结论。
      </p>
      <p className="muted">
        记忆是可纠正的参考，后台提取不代表事实已验证。发现错误可直接编辑或停用，也可以在对话中说明
        “这条记忆已过时，请纠正”。当前工具能力和执行结果以本次实际情况为准。
      </p>
      {settings && (
        <>
          <label>
            <input
              type="checkbox"
              checked={settings.use ?? true}
              disabled={busy || !connected}
              onChange={(e) => configure({ ...settings, use: e.target.checked })}
            />
            自动带入相关记忆
          </label>
          <label>
            <input
              type="checkbox"
              checked={(settings.automatic ?? true) && (settings.contribute ?? true)}
              disabled={busy || !connected}
              onChange={(e) =>
                configure({
                  ...settings,
                  automatic: e.target.checked,
                  ...(e.target.checked ? { contribute: true } : {})
                })
              }
            />
            空闲时提取项目记忆
          </label>
          <p className="muted">
            关闭自动行为后，明确要求的读取、保存仍可执行。关闭带入不删除历史中已经出现的内容。
          </p>
        </>
      )}
      <div className="knowledge-actions">
        <button type="button" onClick={() => edit(null)}>
          新增记忆
        </button>
        <button
          type="button"
          disabled={busy || !connected}
          onClick={() =>
            void perform(window.agent.maintainMemory({ session_id: sessionId }), (value) => {
              setMemory(value)
              onChange(value)
            })
          }
        >
          提取可复用记忆
        </button>
        {job?.status === 'running' && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void perform(window.agent.cancelMemory({ session_id: sessionId }), (value) => {
                setMemory(value)
                onChange(value)
              })
            }
          >
            停止提取
          </button>
        )}
      </div>
      {job && (
        <p>
          记忆提取：{jobLabel}。{job.message}
        </p>
      )}
      {detail(
        'editor',
        draft.editing ? '编辑记忆' : '新记忆草稿',
        <>
          <input
            aria-label="记忆标题"
            placeholder="标题"
            value={draft.title}
            onChange={(e) => update({ title: e.target.value })}
          />
          <textarea
            aria-label="记忆正文"
            rows={5}
            value={draft.content}
            onChange={(e) => update({ content: e.target.value })}
          />
          <select
            aria-label="记忆范围"
            value={draft.scope}
            onChange={(e) => update({ scope: e.target.value === 'user' ? 'user' : 'project' })}
          >
            <option value="project">本项目</option>
            <option value="user">跨项目偏好</option>
          </select>
          <select
            aria-label="记忆类别"
            value={draft.category}
            onChange={(e) => update({ category: e.target.value })}
          >
            <option value="fact">知识</option>
            <option value="preference">偏好</option>
            <option value="procedure">经验手册</option>
            <option value="knowledge_page">知识页</option>
          </select>
          <label>
            <input
              type="checkbox"
              checked={draft.pinned}
              onChange={(e) => update({ pinned: e.target.checked })}
            />
            优先召回（仍受容量限制）
          </label>
          <button
            type="button"
            disabled={busy || !connected || !draft.title.trim() || !draft.content.trim()}
            onClick={save}
          >
            保存记忆
          </button>
          <button type="button" onClick={() => edit(null)}>
            清空草稿
          </button>
        </>
      )}
      <div className="knowledge-actions">
        <input
          aria-label="记忆搜索"
          placeholder="按关键词查找记忆"
          value={draft.query}
          onChange={(e) => update({ query: e.target.value })}
        />
        <label>
          <input
            type="checkbox"
            checked={draft.includeDisabled}
            onChange={(e) => update({ includeDisabled: e.target.checked })}
          />
          含停用项
        </label>
        <button type="button" disabled={busy || !connected} onClick={() => search()}>
          查找 / 刷新记忆
        </button>
      </div>
      {detail(
        'results',
        `已保存记忆 · 当前列表 ${draft.page?.entries.length ?? 0} 条`,
        <>
          <p className="muted">
            列表为查询快照，后台更新后可刷新。关键词：{draft.filter || '全部'}。
          </p>
          {!draft.page?.entries.length && <p>暂无匹配记忆，可新增或让 Harness 按明确要求保存。</p>}
          {draft.page?.entries.map((entry) =>
            detail(
              entry.memory_id,
              `${entry.title} · ${entry.scope === 'user' ? '跨项目偏好' : '本项目'}${entry.enabled ? '' : ' · 已停用'}${entry.stale ? ' · 来源待更新' : ''}`,
              <>
                <pre>{entry.content}</pre>
                <button type="button" onClick={() => edit(entry)}>
                  编辑
                </button>
                <button
                  type="button"
                  onClick={() =>
                    onAttach({
                      key: `memory:${entry.memory_id}`,
                      title: entry.title,
                      source: `memory=${entry.memory_id}, revision=${entry.revision}`,
                      text: entry.content
                    })
                  }
                >
                  加入这次提问
                </button>
                <button type="button" disabled={busy || !connected} onClick={() => toggle(entry)}>
                  {entry.enabled ? '停用' : '启用'}
                </button>
                <button
                  type="button"
                  disabled={busy || !connected}
                  onClick={() =>
                    void perform(
                      window.agent.forgetMemory({
                        session_id: sessionId,
                        memory_id: entry.memory_id
                      }),
                      accept
                    )
                  }
                >
                  忘记
                </button>
                {detail(
                  `source-${entry.memory_id}`,
                  '来源与知识页选项',
                  <>
                    <p>
                      {entry.source === 'user'
                        ? '手动保存'
                        : entry.source === 'agent'
                          ? 'Agent 保存'
                          : '后台提取'}{' '}
                      · 修订 {entry.revision} · 更新 {new Date(entry.updated_at).toLocaleString()}
                    </p>
                    <p>
                      来源会话 {entry.session_id ?? '手动'} · 来源处理至事件{' '}
                      {entry.source_seq ?? '无'}
                      ；来源条目 {entry.source_ids?.join('、') || '无'}。
                    </p>
                    {entry.source === 'maintenance' && (
                      <p className="muted">
                        这是后台模型提取的内容；事件号记录处理边界，不代表该条知识已逐项验证。
                      </p>
                    )}
                    <label>
                      <input
                        type="checkbox"
                        checked={draft.sources.includes(entry.memory_id)}
                        onChange={(e) =>
                          update({
                            sources: e.target.checked
                              ? [...draft.sources, entry.memory_id]
                              : draft.sources.filter((id) => id !== entry.memory_id)
                          })
                        }
                      />
                      选为知识页来源
                    </label>
                  </>
                )}
              </>
            )
          )}
          {draft.page?.next_cursor && (
            <button type="button" disabled={busy} onClick={() => search(true)}>
              更多记忆结果
            </button>
          )}
        </>
      )}
      {settings &&
        memory &&
        detail(
          'advanced',
          '记忆高级设置与维护记录',
          <>
            {(
              [
                ['contribute', '允许 Agent 主动保存项目记忆（关闭后仅按明确要求保存）'],
                ['associations', '关联记忆实验'],
                ['auto_pages', '自动知识页实验']
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={settings[key] ?? false}
                  disabled={busy}
                  onChange={(e) => configure({ ...settings, [key]: e.target.checked })}
                />
                {label}
              </label>
            ))}
            <p>
              空闲提取同时需要允许主动保存；开启“空闲时提取项目记忆”会一起开启主动保存。自动提取从启用后的新工作开始。
            </p>
            {(
              [
                ['recall_chars', '注入正文字符数'],
                ['recall_limit', '最多召回条目'],
                ['maintenance_requests', '每批提取请求数'],
                ['maintenance_input_bytes', '提取输入字节']
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  value={settings[key]}
                  onChange={(e) =>
                    setMemory({
                      ...memory,
                      state: {
                        ...memory.state,
                        settings: { ...settings, [key]: Number(e.target.value) }
                      }
                    })
                  }
                />
              </label>
            ))}
            <button type="button" disabled={busy} onClick={() => configure(settings)}>
              保存记忆参数
            </button>
            <label>
              手动读取旧材料：从事件之后
              <input
                type="number"
                min={0}
                value={draft.afterSeq}
                onChange={(e) => update({ afterSeq: e.target.value })}
              />
            </label>
            <button
              type="button"
              disabled={busy || !draft.afterSeq}
              onClick={() =>
                void perform(
                  window.agent.maintainMemory({
                    session_id: sessionId,
                    after_seq: Number(draft.afterSeq)
                  }),
                  (value) => {
                    setMemory(value)
                    onChange(value)
                  }
                )
              }
            >
              提取指定范围
            </button>
            <button
              type="button"
              disabled={busy || !draft.sources.length}
              onClick={() =>
                void perform(
                  window.agent.maintainMemory({
                    session_id: sessionId,
                    source_ids: draft.sources,
                    title: draft.title
                  }),
                  (value) => {
                    setMemory(value)
                    onChange(value)
                  }
                )
              }
            >
              整理知识页（已选 {draft.sources.length} 条）
            </button>
            <p>
              累计维护 {memory.totals?.requests ?? 0} 次请求；已报告输入{' '}
              {memory.totals?.reported_input_tokens ?? 0} / 输出{' '}
              {memory.totals?.reported_output_tokens ?? 0} token； 未知用量作业{' '}
              {memory.totals?.unknown_jobs ?? 0}，独立于前台 Run。
            </p>
            {job && (
              <p>
                {job.model_id} · 请求 {job.requests} · 输入 {job.usage?.input_tokens ?? '未知'} /
                输出 {job.usage?.output_tokens ?? '未知'}
              </p>
            )}
            <p>忘记删除记忆正文及派生引用，原聊天与过去请求的材料预览仍保留。</p>
          </>
        )}
    </>
  )
}
