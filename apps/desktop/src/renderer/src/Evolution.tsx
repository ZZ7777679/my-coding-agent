/** 反馈、候选和恢复的项目入口。 Project feedback, candidate and restoration interface. */
import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  EvolutionCandidate,
  EvolutionCatalog,
  EvolutionJob,
  EvolutionPage,
  EvolutionSource,
  EvolutionTarget,
  EvolutionScope,
  ProjectSummary,
  DiagnosticEvent
} from '../../generated/protocol'
import type { Result } from '../../shared/api'
import type { CandidateDraft, EvolutionDraft, EvolutionDraftCache } from './EvolutionDrafts'
import { EvolutionMemoryEditor } from './EvolutionMemoryEditor'
import { EvolutionEvidencePicker, type SelectedEvidence } from './EvolutionEvidence'
import { EvolutionEvidencePanel, type EvolutionEvidenceView } from './EvolutionEvidencePanel'
import { EvolutionBudgetSettings, formatEvolutionBudget } from './EvolutionBudgetSettings'
import './Evolution.css'
import type { EvolutionEntry } from './EvolutionQuick'

const kinds: Array<[EvolutionTarget['kind'], string]> = [
  ['project_rule', '项目规范'],
  ['preference', '个人偏好'],
  ['memory', '经验与记忆'],
  ['skill', 'Skill'],
  ['tool_guidance', '工具使用说明'],
  ['workstyle', '组合工作方式'],
  ['code', 'Tool / Harness 代码']
]
const kindHints: Record<EvolutionTarget['kind'], string> = {
  project_rule: '约束这个项目今后如何开发，例如测试范围、代码风格。默认修改根目录 AGENTS.md。',
  preference: '你希望 Agent 长期遵循的习惯，例如回答方式；可用于当前项目或个人所有项目。',
  memory: '修正已保存的事实或经验，避免以后召回同一个错误结论。',
  skill: '优化可重复使用的操作方法。选择现有 Skill 即可；内置内容采用时复制为用户版本。',
  tool_guidance: '改善模型如何使用某个工具的说明，不改变工具程序。修复工具逻辑请选代码。',
  workstyle: '调整已保存的工作流、团队图和 Skill 组合；当前没有保存项时可先在工作方式中保存。',
  code: '修复当前项目的具体源文件。选择 Harness 源码项目时，可提出 Harness 自身代码改进。'
}
const findingKinds: Record<string, string> = {
  rule: '项目规范',
  preference: '个人偏好',
  skill: '操作方法',
  tool_usage: '工具使用问题',
  implementation: '实现问题',
  unknown: '原因待查'
}

/** 保留后端公开错误。 Preserve backend public errors. */
function unwrap<T>(result: Result<T>): T {
  if (!result.ok) throw new Error(result.error.message)
  return result.data
}

/** 展示当前项目的独立维护任务，不占用原对话。 Display maintenance independently of source conversations. */
export function Evolution({
  projectId,
  projectName,
  draftCache,
  entry
}: {
  projectId: string
  projectName: string
  draftCache: EvolutionDraftCache
  entry?: EvolutionEntry | null
}) {
  const saved = useRef(draftCache.get(projectId)).current
  const [page, setPage] = useState<EvolutionPage | null>(null)
  const [catalog, setCatalog] = useState<EvolutionCatalog | null>(null)
  const [target, setTarget] = useState<EvolutionTarget>(
    saved?.target ?? {
      kind: 'project_rule',
      identity: 'AGENTS.md',
      scope: 'project'
    }
  )
  const customize = entry && !entry.jobId
  const [origin, setOrigin] = useState<EvolutionScope | null>(
    customize ? entry.origin : (saved?.origin ?? null)
  )
  const [feedback, setFeedback] = useState(customize ? entry.instruction : (saved?.feedback ?? ''))
  const [selected, setSelected] = useState<string[]>(customize ? [] : (saved?.selected ?? []))
  const [instruction, setInstruction] = useState(customize ? '' : (saved?.instruction ?? ''))
  const [references, setReferences] = useState<SelectedEvidence[]>(
    customize ? [] : (saved?.references ?? [])
  )
  const [evidence, setEvidence] = useState<EvolutionEvidenceView | null>(null)
  const [resourceFilter, setResourceFilter] = useState('')
  const [candidate, setCandidate] = useState<EvolutionCandidate | null>(saved?.candidate ?? null)
  const [drafts, setDrafts] = useState(saved?.drafts ?? new Map<string, CandidateDraft>())
  const [sourceProjectId, setSourceProjectId] = useState(saved?.sourceProjectId ?? projectId)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [sourceDiagnostics, setSourceDiagnostics] = useState<DiagnosticEvent[]>([])
  const [directed, setDirected] = useState(customize ? false : (saved?.directed ?? false))
  const [generation, setGeneration] = useState(saved?.generation ?? null)
  const [proposalJobs, setProposalJobs] = useState<Record<string, string>>(
    saved?.proposalJobs ?? {}
  )
  const [findingSelections, setFindingSelections] = useState<Record<string, string[]>>({})
  const feedbackIdentity = useRef({ key: '', id: crypto.randomUUID() })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const alive = useRef(false)
  const refreshId = useRef(0)
  const loading = useRef(false)
  const candidateRef = useRef(candidate)
  const candidateGeneration = useRef(0)
  candidateRef.current = candidate
  const editorKey = candidate?.candidate_id ?? `target:${JSON.stringify(target)}`
  const editor = drafts.get(editorKey)
  const draft = editor?.text ?? candidate?.after ?? ''
  const dirty = !!editor && editor.text !== editor.base
  const contentConflict = !!candidate && dirty && editor.base !== candidate.after
  const comparison = editor?.comparison ?? ''
  const checkScript = editor?.checkScript ?? ''
  const snapshot = useRef<EvolutionDraft | null>(null)
  snapshot.current = {
    origin,
    target,
    feedback,
    selected,
    instruction,
    references,
    candidate,
    drafts,
    sourceProjectId,
    directed,
    generation,
    proposalJobs
  }
  useEffect(
    () => () => {
      if (snapshot.current) draftCache.set(projectId, snapshot.current)
    },
    [draftCache, projectId]
  )

  /** 按资源或候选分别保存编辑内容，切换时不丢失。 Keep independent drafts for each resource and candidate. */
  function updateEditor(change: Partial<CandidateDraft>) {
    setDrafts((previous) => {
      const next = new Map(previous)
      next.set(editorKey, {
        text: draft,
        base: editor?.base ?? candidate?.after ?? '',
        comparison,
        checkScript,
        ...change
      })
      return next
    })
  }
  const setDraft = (text: string) => updateEditor({ text })
  const setComparison = (text: string) => updateEditor({ comparison: text })
  const setCheckScript = (text: string) => updateEditor({ checkScript: text })

  /** 刷新事实与版本，只有干净草稿才同步正文。 Refresh facts and versions without overwriting dirty text. */
  function mergeCandidate(value: EvolutionCandidate) {
    setDrafts((previous) => {
      const next = new Map(previous)
      const old = next.get(value.candidate_id)
      next.set(
        value.candidate_id,
        old && old.text !== old.base && old.text !== value.after
          ? old
          : {
              text: value.after,
              base: value.after,
              comparison: old?.comparison ?? '',
              checkScript: old?.checkScript ?? ''
            }
      )
      return next
    })
    setCandidate(value)
  }
  /** 立即打开证据面板，加载和错误均在入口对应的视窗内显示。 Open evidence immediately with loading and errors in the same viewport. */
  function setSource(value: EvolutionSource | null) {
    if (value?.session_id) setEvidence({ kind: 'trace', source: value })
  }
  useEffect(() => {
    let current = true
    void window.agent
      .listProjects()
      .then((result) => {
        if (!current) return
        if (result.ok) setProjects(result.data.recent_projects)
        else setError(result.error.message)
      })
      .catch(() => {
        if (current) setError('读取项目目录失败。')
      })
    return () => {
      current = false
    }
  }, [])
  useEffect(() => {
    let current = true
    setSourceDiagnostics([])
    void window.agent
      .evolutionList({ project_id: sourceProjectId })
      .then((result) => {
        if (!current) return
        if (result.ok) setSourceDiagnostics(result.data.diagnostics ?? [])
        else setError(result.error.message)
      })
      .catch(() => {
        if (current) setError('读取来源项目诊断失败。')
      })
    return () => {
      current = false
    }
  }, [sourceProjectId])
  const refresh = useCallback(
    async (before?: string) => {
      const ticket = ++refreshId.current
      const value = unwrap(await window.agent.evolutionList({ project_id: projectId, before }))
      if (entry?.jobId && !value.jobs?.some((item) => item.job_id === entry.jobId)) {
        const detail = unwrap(
          await window.agent.evolutionJob({ project_id: projectId, job_id: entry.jobId })
        )
        value.jobs = [detail, ...(value.jobs ?? [])]
      }
      if (alive.current && ticket === refreshId.current) {
        setPage(value)
        const current = candidateRef.current
        if (current) {
          const latest = unwrap(
            await window.agent.evolutionCandidate({
              project_id: projectId,
              candidate_id: current.candidate_id
            })
          )
          if (
            alive.current &&
            ticket === refreshId.current &&
            candidateRef.current?.candidate_id === current.candidate_id
          )
            mergeCandidate(latest)
        }
      }
    },
    [projectId, entry?.jobId]
  )
  useEffect(() => {
    alive.current = true
    void Promise.all([
      refresh(),
      window.agent.evolutionCatalog({ project_id: projectId }).then((result) => {
        if (alive.current) setCatalog(unwrap(result))
      })
    ]).catch((e: unknown) => {
      if (alive.current) setError(e instanceof Error ? e.message : '读取失败')
    })
    return () => {
      alive.current = false
      ++refreshId.current
    }
  }, [projectId, refresh])
  const running = page?.jobs?.some((job) => job.status === 'running') ?? false
  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => {
      if (loading.current) return
      loading.current = true
      void refresh()
        .catch((e: unknown) => {
          if (alive.current) setError(e instanceof Error ? e.message : '刷新失败')
        })
        .finally(() => {
          loading.current = false
        })
    }, 2000)
    return () => clearInterval(timer)
  }, [running, refresh])

  /** 请求失败保留输入；切换项目后不更新旧页面。 Preserve drafts on failure and ignore departed views. */
  async function action(work: () => Promise<void>) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await work()
      if (alive.current) {
        await refresh()
        const next = unwrap(await window.agent.evolutionCatalog({ project_id: projectId }))
        if (alive.current) setCatalog(next)
      }
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : '操作失败，输入已保留。')
    } finally {
      if (alive.current) setBusy(false)
    }
  }
  /** 详情按需打开，列表刷新不重置编辑内容。 Open details without replacing drafts during polling. */
  async function openCandidate(id: string) {
    const ticket = ++candidateGeneration.current
    const value = unwrap(
      await window.agent.evolutionCandidate({ project_id: projectId, candidate_id: id })
    )
    if (alive.current && ticket === candidateGeneration.current) {
      mergeCandidate(value)
    }
  }
  /** 读取真实目标；内置 Skill 的参考与用户副本分开。 Read actual targets and separate bundled Skill references. */
  async function readTarget() {
    const resource = unwrap(await window.agent.evolutionResource({ project_id: projectId, target }))
    if (!alive.current) return
    setTarget(resource.target)
    const key = `target:${JSON.stringify(resource.target)}`
    setDrafts((previous) => {
      const old = previous.get(key)
      if (old && old.text !== old.base) return previous
      const next = new Map(previous)
      const text = resource.content ?? resource.reference_content ?? ''
      next.set(key, { text, base: text, comparison: '', checkScript: '' })
      return next
    })
    setNotice(
      resource.content === null ? '目标尚不存在，采用时创建。' : '已读取当前版本，尚未修改。'
    )
    setCandidate(null)
  }
  const matches =
    catalog?.items.filter(
      (item) =>
        item.target.kind === target.kind &&
        `${item.label} ${item.target.identity}`.toLowerCase().includes(resourceFilter.toLowerCase())
    ) ?? []
  const names = new Map(kinds)
  const requestInput = {
    project_id: projectId,
    origin,
    target: directed ? target : null,
    mode: directed ? ('propose' as const) : ('investigate' as const),
    feedback_ids: selected,
    sources: references.map((item) => item.source),
    instruction: [feedback.trim(), instruction.trim()].filter(Boolean).join('\n\n')
  }
  const inputKey = JSON.stringify(requestInput)
  const feedbackKey = JSON.stringify([feedback, references, directed ? target : null])
  if (feedbackIdentity.current.key !== feedbackKey)
    feedbackIdentity.current = { key: feedbackKey, id: crypto.randomUUID() }
  const linkedJobId = generation?.key === inputKey ? generation.jobId : null
  const linkedJob = page?.jobs?.find((job) => job.job_id === linkedJobId)
  /** 同一份输入连接已有作业；重新调查必须显式发起。 Link unchanged input to its job and make reruns explicit. */
  async function generateAgain() {
    const job = unwrap(await window.agent.evolutionGenerate(requestInput))
    if (alive.current) {
      setGeneration({ key: inputKey, jobId: job.job_id })
      setNotice(
        directed
          ? '候选生成已启动，可继续使用原会话。'
          : '调查已启动，将先归纳问题和建议，再由你生成关联候选。'
      )
    }
  }
  /** 展开同一作业，避免查看进度触发另一次请求。 Expand the existing job without issuing another model request. */
  function showJob(id: string) {
    const element = document.getElementById(`evolution-job-${id}`)
    if (element instanceof HTMLDetailsElement) element.open = true
    element?.scrollIntoView({ block: 'center' })
  }
  const shownEntry = useRef<string | null>(null)
  useEffect(() => {
    if (
      entry?.jobId &&
      shownEntry.current !== entry.jobId &&
      page?.jobs?.some((job) => job.job_id === entry.jobId)
    ) {
      shownEntry.current = entry.jobId
      showJob(entry.jobId)
    }
  }, [entry?.jobId, page])
  /** 相同发现的生成入口连接既有作业，变更勾选后可另行生成。 Reuse a proposal job for the same findings and allow a changed selection. */
  function proposalKey(job: EvolutionJob) {
    return JSON.stringify([
      job.job_id,
      findingSelections[job.job_id] ?? (job.findings ?? []).map((item) => item.finding_id)
    ])
  }
  return (
    <section className="content evolution">
      <div className="card-heading">
        <div>
          <h1>经验与改进</h1>
          <p>{projectName} · 发现问题 → 生成改进候选 → 采用 / 恢复</p>
        </div>
        <button disabled={busy} onClick={() => void action(() => refresh())}>
          刷新
        </button>
      </div>
      <section className="detail-card evolution-start" aria-label="启动改进">
        <h2>新建改进</h2>
        {origin && (
          <p className="evolution-inherited">
            已带入{origin.kind === 'project' ? '项目' : origin.kind === 'task' ? '任务' : '会话'}
            范围；启动时冻结现有记录。
            <button onClick={() => setOrigin(null)}>清除继承范围，手动选材</button>
          </p>
        )}
        <p className="muted">
          {directed
            ? '已指定资源；仍先按相关性筛选证据，再生成该资源的候选。可在下方调整目标或取消定向。'
            : '描述问题即可开始，也可以在下方添加会话、Trace 或诊断记录。先调查原因和相关资源，再选择生成候选。'}
        </p>
        <label>
          反馈或改进要求
          <textarea
            disabled={busy}
            rows={3}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="例如：工具调用反复失败，请分析原因，并找出需要改进的规范、Skill 或代码。"
          />
        </label>
        <div className="evolution-row">
          <button
            className="evolution-primary"
            disabled={busy}
            onClick={() => (linkedJobId ? showJob(linkedJobId) : void action(generateAgain))}
          >
            {linkedJobId ? '查看本次改进进度' : '开始改进'}
          </button>
          <button
            disabled={busy}
            onClick={() => setEvidence({ kind: 'preview', request: requestInput })}
          >
            预览本次参考材料
          </button>
          {linkedJobId && (
            <button disabled={busy} onClick={() => void action(generateAgain)}>
              重新发起改进
            </button>
          )}
          <span className="muted">
            已选 {references.length} 个来源、{selected.length} 条反馈
            {origin && '，另含上方继承范围'}
            {directed && ` · 定向生成：${names.get(target.kind)} / ${target.identity || '新资源'}`}
          </span>
        </div>
        {linkedJob && (
          <p role="status">
            本次改进 · {linkedJob.message} · 请求 {linkedJob.requests ?? 0}
          </p>
        )}
        {page && (
          <EvolutionBudgetSettings
            settings={page.settings}
            disabled={busy}
            onSave={async (budget, inputChars) => {
              setBusy(true)
              try {
                const settings = unwrap(
                  await window.agent.evolutionConfigure({
                    ...page.settings,
                    budget,
                    input_chars: inputChars
                  })
                )
                if (alive.current) {
                  ++refreshId.current
                  setPage((current) => (current ? { ...current, settings } : current))
                }
              } finally {
                if (alive.current) setBusy(false)
              }
            }}
          />
        )}
        <details className="evolution-start-options">
          <summary>补充说明与保存反馈（可选）</summary>
          <label>
            本次补充说明
            <input
              disabled={busy}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
          </label>
          <p className="muted">
            无需先保存反馈即可开始改进；保存用于以后复用。
            {page?.settings.automatic_review &&
              directed &&
              '当前已开启保存带目标反馈后自动生成候选。'}
          </p>
          <button
            disabled={busy || !feedback.trim()}
            onClick={() =>
              void action(async () => {
                const value = unwrap(
                  await window.agent.evolutionFeedback({
                    project_id: projectId,
                    feedback_id: feedbackIdentity.current.id,
                    text: feedback,
                    sources: references.map((item) => item.source),
                    target: directed ? target : null
                  })
                )
                if (alive.current) {
                  const nextSelected = [...selected, value.feedback_id]
                  setSelected(nextSelected)
                  setFeedback('')
                  if (value.review_job_id) {
                    setGeneration({
                      jobId: value.review_job_id,
                      key: JSON.stringify({
                        ...requestInput,
                        feedback_ids: nextSelected,
                        instruction: instruction.trim()
                      })
                    })
                  }
                  setNotice(
                    value.review_job_id
                      ? '反馈已保存并已启动复盘；可查看同一作业，无需重复生成。'
                      : '反馈已保存。'
                  )
                }
              })
            }
          >
            保存反馈
          </button>
        </details>
      </section>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {[...(page?.issues ?? []), ...(catalog?.issues ?? [])].map((issue, i) => (
        <p className="muted" key={i}>
          {issue}
        </p>
      ))}
      <details className="detail-card">
        <summary>复盘与采用设置</summary>
        {page && (
          <>
            <label>
              复盘模型{' '}
              <select
                value={page.settings.model_id}
                disabled={busy}
                onChange={(e) => {
                  const model =
                    e.target.value === 'glm-5.3-flash' ? 'glm-5.3-flash' : 'deepseek-v4.1-flash'
                  void action(async () => {
                    unwrap(
                      await window.agent.evolutionConfigure({ ...page.settings, model_id: model })
                    )
                  })
                }}
              >
                <option value="glm-5.3-flash">GLM-5.3-Flash</option>
                <option value="deepseek-v4.1-flash">DeepSeek V4.1 Flash</option>
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={page.settings.automatic_review ?? false}
                disabled={busy}
                onChange={(e) =>
                  void action(async () => {
                    unwrap(
                      await window.agent.evolutionConfigure({
                        ...page.settings,
                        automatic_review: e.target.checked
                      })
                    )
                  })
                }
              />
              保存带目标的反馈后自动生成候选
            </label>
            <p>下列资源可按你的项目设置自动采用；留空则只生成候选。代码使用明确的采用入口。</p>
            <div className="evolution-options">
              {kinds
                .filter(([kind]) => kind !== 'code')
                .map(([kind, label]) => (
                  <label key={kind}>
                    <input
                      type="checkbox"
                      disabled={busy}
                      checked={page.settings.auto_apply?.includes(kind) ?? false}
                      onChange={(e) => {
                        const existing = page.settings.auto_apply ?? []
                        const next = e.target.checked
                          ? [...existing, kind]
                          : existing.filter((v) => v !== kind)
                        void action(async () => {
                          unwrap(
                            await window.agent.evolutionConfigure({
                              ...page.settings,
                              auto_apply: next
                            })
                          )
                        })
                      }}
                    />
                    {label}
                  </label>
                ))}
            </div>
          </>
        )}
      </details>
      <div className="detail-card">
        <label>
          参考记录所在项目
          <select
            aria-label="参考记录所在项目"
            value={sourceProjectId}
            disabled={busy}
            onChange={(event) => setSourceProjectId(event.target.value)}
          >
            {!projects.some((item) => item.project_id === projectId) && (
              <option value={projectId}>{projectName}</option>
            )}
            {projects.map((item) => (
              <option key={item.project_id} value={item.project_id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <p>切换来源项目保留已选证据；候选保存及修改写入项目：{projectName}。</p>
      </div>
      <EvolutionEvidencePicker
        projectId={sourceProjectId}
        diagnostics={sourceDiagnostics}
        selected={references}
        onChange={(items) =>
          setReferences(
            items.map((item) =>
              references.includes(item)
                ? item
                : {
                    ...item,
                    label: `${projects.find((value) => value.project_id === sourceProjectId)?.name ?? projectName} · ${item.label}`
                  }
            )
          )
        }
        onTrace={setSource}
        disabled={busy}
      />
      <details className="detail-card">
        <summary>选择已保存的反馈 · 已选 {selected.length} 条</summary>
        {!page?.feedback?.length && <p>暂无反馈。可以直接选择上面的运行记录，无需先写反馈。</p>}
        {(page?.feedback ?? []).map((item) => (
          <div className="evolution-entry" key={item.feedback_id}>
            <label>
              <input
                type="checkbox"
                disabled={busy}
                checked={selected.includes(item.feedback_id)}
                onChange={(e) =>
                  setSelected((ids) =>
                    e.target.checked
                      ? [...ids, item.feedback_id]
                      : ids.filter((id) => id !== item.feedback_id)
                  )
                }
              />
              {item.text}
            </label>
            <small>
              {new Date(item.created_at).toLocaleString()} ·{' '}
              {item.sources?.length
                ? `关联 ${item.sources.length} 个来源`
                : item.source?.session_id
                  ? '关联 Trace'
                  : item.source?.diagnostic_id
                    ? '关联诊断'
                    : '仅文字反馈'}
            </small>
            {item.source?.session_id && (
              <button onClick={() => setSource(item.source ?? null)}>原始 Trace</button>
            )}
            {item.sources
              ?.filter((s) => s.session_id)
              .map((s, i) => (
                <button key={i} onClick={() => setSource(s)}>
                  来源 Trace {i + 1}
                </button>
              ))}
          </div>
        ))}
        {!!selected.length && (
          <button disabled={busy} onClick={() => setSelected([])}>
            清空反馈选择
          </button>
        )}
        {page?.next_cursor && (
          <button
            onClick={() =>
              void refresh(page.next_cursor ?? undefined).catch((e: unknown) =>
                setError(e instanceof Error ? e.message : '读取失败')
              )
            }
          >
            读取更早反馈
          </button>
        )}
      </details>
      <details className="detail-card">
        <summary>指定资源快捷入口</summary>
        <label>
          <input
            type="checkbox"
            checked={directed}
            disabled={busy}
            onChange={(event) => setDirected(event.target.checked)}
          />
          我已确定要修改的资源
        </label>
        <p>调查无需预选资源。明确知道修改对象时，可在此直接生成定向候选。</p>
        <h2>改进对象</h2>
        <p>{kindHints[target.kind]}</p>
        <div className="evolution-row">
          <select
            disabled={busy}
            aria-label="改进对象类型"
            value={target.kind}
            onChange={(e) => {
              const kind = kinds.find(([key]) => key === e.target.value)?.[0]
              if (kind) {
                setTarget({
                  kind,
                  identity: kind === 'project_rule' ? 'AGENTS.md' : '',
                  scope: kind === 'preference' ? 'user' : 'project'
                })
                setCandidate(null)
                setResourceFilter('')
              }
            }}
          >
            {kinds.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <input
            aria-label="筛选已有资源"
            placeholder="按名称筛选资源"
            value={resourceFilter}
            disabled={busy}
            onChange={(e) => setResourceFilter(e.target.value)}
          />
          <select
            disabled={busy}
            aria-label="已有资源"
            value={
              matches.some((item) => item.target.identity === target.identity)
                ? target.identity
                : ''
            }
            onChange={(e) => {
              const item = matches.find((v) => v.target.identity === e.target.value)
              if (item) {
                setTarget(item.target)
                setCandidate(null)
              }
            }}
          >
            <option value="">选择已有资源，或填写新目标</option>
            {matches.map((item) => (
              <option key={item.target.identity} value={item.target.identity}>
                {item.label}
              </option>
            ))}
          </select>
          <button disabled={busy} onClick={() => void action(readTarget)}>
            读取当前内容
          </button>
        </div>
        {(['code', 'project_rule'].includes(target.kind) || !target.identity) && (
          <label>
            目标{' '}
            {target.kind === 'code' || target.kind === 'project_rule' ? '项目相对文件路径' : '身份'}
            <input
              disabled={busy}
              value={target.identity}
              onChange={(e) => {
                setTarget({ ...target, identity: e.target.value })
                setCandidate(null)
              }}
              placeholder={
                target.kind === 'skill'
                  ? '新 Skill 名称；也可直接选择已有 Skill'
                  : '新偏好 / 记忆可留空'
              }
            />
          </label>
        )}
        {target.identity && !['code', 'project_rule'].includes(target.kind) && (
          <details>
            <summary>资源身份与作用范围</summary>
            <code>{target.identity}</code>
            <button disabled={busy} onClick={() => setTarget({ ...target, identity: '' })}>
              改为新资源
            </button>
          </details>
        )}
        {['memory', 'preference', 'skill'].includes(target.kind) && (
          <label>
            作用范围
            <select
              disabled={busy}
              value={target.scope ?? 'project'}
              onChange={(e) =>
                setTarget({ ...target, scope: e.target.value === 'user' ? 'user' : 'project' })
              }
            >
              <option value="project">当前项目</option>
              <option value="user">个人（跨项目）</option>
            </select>
          </label>
        )}
        {target.kind === 'code' && (
          <p>
            修改写入项目 {projectName} 中的代码。Harness
            自改应在源码项目打开此页，并从上方选择发生问题的业务项目记录。
            采用后重启对应应用生效；恢复代码不回滚业务数据。
          </p>
        )}
      </details>
      {(page?.jobs ?? []).map((job) => (
        <details className="detail-card" key={job.job_id} id={`evolution-job-${job.job_id}`}>
          <summary>
            {job.mode === 'investigate' ? '调查' : '复盘'} · {job.status} · 请求 {job.requests ?? 0}{' '}
            · {job.message}
          </summary>
          {job.summary && <p>{job.summary}</p>}
          {!job.experiment_directory && (
            <p className="muted">
              {job.budget
                ? `本次预算：请求 ${formatEvolutionBudget(job.budget.max_requests, ' 次')} · 工具 ${formatEvolutionBudget(job.budget.max_tools, ' 次')} · 总时限 ${formatEvolutionBudget(job.budget.max_seconds, ' 秒')} · 单请求 ${formatEvolutionBudget(job.budget.request_timeout_seconds, ' 秒')} · 每次输出 ${formatEvolutionBudget(job.budget.max_output_tokens, ' token')} · 上下文容量 ${formatEvolutionBudget(job.budget.max_context_bytes, ' 字节')} · 响应容量 ${formatEvolutionBudget(job.budget.max_response_bytes, ' 字节')}`
                : '本次预算：旧记录未保存，无法确定。'}
            </p>
          )}
          {job.review_job_id && (
            <button onClick={() => showJob(job.review_job_id!)}>查看来源调查</button>
          )}
          {job.mode === 'investigate' && !!job.findings?.length && (
            <section aria-label="调查发现与建议">
              <h3>调查发现与建议</h3>
              <p>勾选要处理的问题，再生成关联候选。工具使用方法与实现缺陷会分别落到说明或代码。</p>
              {(job.findings ?? []).map((finding) => {
                const chosen =
                  findingSelections[job.job_id] ??
                  (job.findings ?? []).map((item) => item.finding_id)
                return (
                  <div className="evolution-entry" key={finding.finding_id}>
                    <label>
                      <input
                        type="checkbox"
                        disabled={busy}
                        checked={chosen.includes(finding.finding_id)}
                        onChange={(event) =>
                          setFindingSelections((old) => ({
                            ...old,
                            [job.job_id]: event.target.checked
                              ? [...chosen, finding.finding_id]
                              : chosen.filter((id) => id !== finding.finding_id)
                          }))
                        }
                      />
                      {finding.title}
                    </label>
                    <p>{finding.explanation}</p>
                    <small>
                      {findingKinds[finding.category]} ·{' '}
                      {(finding.targets ?? [])
                        .map((item) => `${names.get(item.kind)} / ${item.identity || '新资源'}`)
                        .join('；') || '修改位置待进一步定位'}
                    </small>
                    {!!finding.unknowns?.length && <p>尚不确定：{finding.unknowns.join('；')}</p>}
                    {(finding.sources ?? [])
                      .filter((item) => item.session_id)
                      .map((item, index) => (
                        <button key={index} onClick={() => void setSource(item)}>
                          查看依据 {index + 1}
                        </button>
                      ))}
                  </div>
                )
              })}
              <button
                disabled={
                  busy ||
                  !(
                    findingSelections[job.job_id] ??
                    (job.findings ?? []).map((item) => item.finding_id)
                  ).length
                }
                onClick={() =>
                  void action(async () => {
                    const existing = proposalJobs[proposalKey(job)]
                    if (existing) {
                      showJob(existing)
                      return
                    }
                    const next = unwrap(
                      await window.agent.evolutionGenerate({
                        project_id: projectId,
                        mode: 'propose',
                        target: null,
                        review_job_id: job.job_id,
                        finding_ids:
                          findingSelections[job.job_id] ??
                          (job.findings ?? []).map((item) => item.finding_id)
                      })
                    )
                    setProposalJobs((old) => ({ ...old, [proposalKey(job)]: next.job_id }))
                    setNotice(`关联候选生成已启动：${next.job_id}`)
                  })
                }
              >
                {proposalJobs[proposalKey(job)] ? '查看关联候选进度' : '生成所选问题的关联候选'}
              </button>
            </section>
          )}
          <p>
            输入 {job.usage?.input_tokens ?? '未知'} / 输出 {job.usage?.output_tokens ?? '未知'}{' '}
            token
          </p>
          {job.experiment_directory && <p>实验：{job.experiment_directory}</p>}
          {job.details_available && (
            <button
              disabled={busy}
              onClick={() =>
                setEvidence({
                  kind: 'job',
                  jobId: job.job_id,
                  title: job.experiment_directory ? '实验详情' : '实际参考材料'
                })
              }
            >
              {job.experiment_directory ? '读取实验详情' : '查看实际参考材料'}
            </button>
          )}
          {job.status === 'running' && (
            <button
              onClick={() =>
                void action(async () => {
                  unwrap(
                    await window.agent.evolutionStop({ project_id: projectId, job_id: job.job_id })
                  )
                })
              }
            >
              停止复盘
            </button>
          )}
          {[
            ...new Set([
              ...(job.candidate_ids ?? []),
              ...(job.candidate_id ? [job.candidate_id] : [])
            ])
          ].map((id, index, ids) => (
            <button key={id} onClick={() => void action(() => openCandidate(id))}>
              {ids.length === 1 ? '查看候选' : `查看候选 ${index + 1}`}
            </button>
          ))}
        </details>
      ))}
      <div className="detail-card">
        <h2>改进记录</h2>
        {!page?.candidates?.length && <p>暂无候选。可生成建议，或展开下面的编辑器创建草稿。</p>}
        {(page?.candidates ?? []).map((item) => (
          <div className="evolution-entry" key={item.candidate_id}>
            <button onClick={() => void action(() => openCandidate(item.candidate_id))}>
              {item.title}
            </button>
            <span>
              {names.get(item.target.kind)} · {item.status} ·{' '}
              {item.comparison?.outcome ?? '尚未评价'}
              {item.comparison &&
                item.comparison.content_revision !== item.content_revision &&
                ' · 旧版本结果，已过期'}
            </span>
            <p>{item.message}</p>
          </div>
        ))}
        {page?.next_cursor && (
          <button
            onClick={() =>
              void refresh(page.next_cursor ?? undefined).catch((e: unknown) => {
                if (alive.current) setError(e instanceof Error ? e.message : '读取失败')
              })
            }
          >
            更早记录
          </button>
        )}
      </div>
      <details className="detail-card" open={candidate !== null || undefined}>
        <summary>{candidate ? `候选详情 · ${candidate.title}` : '手动编写候选'}</summary>
        {candidate && (
          <>
            <button
              onClick={() => {
                ++candidateGeneration.current
                setCandidate(null)
              }}
            >
              关闭详情
            </button>
            <p>{candidate.rationale}</p>
            {dirty && <p role="status">此候选有未保存的编辑。切换页面或候选后会保留。</p>}
            {contentConflict && (
              <div role="alert">
                <p>已保存的候选正文发生变化；你的编辑已保留。核对最新版本后选择如何继续。</p>
                <details>
                  <summary>最新已保存内容</summary>
                  <pre>{candidate.after}</pre>
                </details>
                <button
                  onClick={() => updateEditor({ text: candidate.after, base: candidate.after })}
                >
                  使用最新内容
                </button>
                <button onClick={() => updateEditor({ base: candidate.after })}>
                  基于最新版本保留我的编辑
                </button>
              </div>
            )}
            <p>
              {candidate.target.identity} · 修订 {candidate.revision} · 正文版本{' '}
              {candidate.content_revision} · {candidate.message}
            </p>
            {candidate.review_job_id ? (
              <button
                disabled={busy}
                onClick={() =>
                  setEvidence({
                    kind: 'job',
                    jobId: candidate.review_job_id!,
                    title: `候选证据 · ${candidate.title}`
                  })
                }
              >
                查看候选实际参考材料
              </button>
            ) : (
              <p className="muted">此候选未保存模型输入快照（手动创建或旧记录）。</p>
            )}
            {!!candidate.sources?.length && (
              <details>
                <summary>关联来源 · {candidate.sources.length}</summary>
                {candidate.sources.map((item, i) => (
                  <p key={i}>
                    {item.session_id ? (
                      <button onClick={() => setSource(item)}>
                        查看关联 Trace {item.seq ? `#${item.seq}` : '运行'}
                      </button>
                    ) : item.diagnostic_id ? (
                      `诊断 ${item.diagnostic_id}`
                    ) : (
                      '文字反馈'
                    )}
                  </p>
                ))}
              </details>
            )}
            {candidate.recovery_directory && (
              <p>
                启动失败时可关闭应用，运行独立恢复入口：
                <code>{candidate.recovery_directory}\Restore.cmd</code>。它不依赖被修改的应用源码。
              </p>
            )}
            {candidate.pending_action && (
              <p role="alert">上次采用 / 恢复未确认完成，请检查当前目标；不会自动重放。</p>
            )}
            <details>
              <summary>修改前</summary>
              <pre>{candidate.before ?? '资源不存在'}</pre>
            </details>
          </>
        )}
        {['preference', 'memory'].includes(candidate?.target.kind ?? target.kind) ? (
          <EvolutionMemoryEditor
            value={draft}
            onChange={setDraft}
            readOnly={candidate?.status === 'applied'}
          />
        ) : (
          <label>
            建议完整内容
            <textarea
              className="evolution-editor"
              value={draft}
              readOnly={candidate?.status === 'applied'}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="可读取原资源后编辑；组合工作方式保留原有结构。"
            />
          </label>
        )}
        <div className="evolution-row">
          <button
            disabled={busy || !draft || contentConflict || candidate?.status === 'applied'}
            onClick={() =>
              void action(async () => {
                const value = candidate
                  ? unwrap(
                      await window.agent.evolutionEdit({
                        project_id: projectId,
                        candidate_id: candidate.candidate_id,
                        title: candidate.title,
                        rationale: candidate.rationale,
                        after: draft,
                        revision: candidate.revision ?? 1
                      })
                    )
                  : unwrap(
                      await window.agent.evolutionCreate({
                        project_id: projectId,
                        target,
                        after: draft,
                        title: instruction || `${names.get(target.kind)}改进`,
                        rationale: instruction,
                        feedback_ids: selected
                      })
                    )
                if (alive.current) mergeCandidate(value)
              })
            }
          >
            保存候选
          </button>
          {candidate && (
            <button
              disabled={busy || draft !== candidate.after}
              onClick={() =>
                void action(async () => {
                  const value = unwrap(
                    await window.agent.evolutionControl({
                      project_id: projectId,
                      candidate_id: candidate.candidate_id,
                      action: candidate.status === 'applied' ? 'revert' : 'apply'
                    })
                  )
                  if (alive.current) {
                    mergeCandidate(value)
                  }
                })
              }
            >
              {candidate.status === 'applied' ? '恢复修改前版本' : '采用候选'}
            </button>
          )}
        </div>
        {candidate?.target.kind === 'code' && (
          <details>
            <summary>独立代码实验</summary>
            <p>
              在两个独立副本中执行同一检查，复用当前项目环境与执行方式。默认不复制
              .git、虚拟环境、node_modules 和
              .env。请使用相对项目路径，解释器可使用原环境的绝对路径。
            </p>
            <label>
              PowerShell 检查命令
              <textarea
                value={checkScript}
                onChange={(e) => setCheckScript(e.target.value)}
                placeholder="例如 python check_example.py"
              />
            </label>
            <button
              disabled={busy || !checkScript.trim() || draft !== candidate.after}
              onClick={() =>
                void action(async () => {
                  unwrap(
                    await window.agent.evolutionExperiment({
                      project_id: projectId,
                      candidate_id: candidate.candidate_id,
                      command: { command: { kind: 'powershell', script: checkScript } }
                    })
                  )
                })
              }
            >
              比较原版与候选
            </button>
          </details>
        )}
        {candidate && (
          <details>
            <summary>记录实际效果</summary>
            <textarea
              aria-label="比较说明"
              value={comparison}
              onChange={(e) => setComparison(e.target.value)}
            />
            <div className="evolution-row">
              {(
                [
                  ['improved', '有改善'],
                  ['unchanged', '没有变化'],
                  ['regressed', '变差'],
                  ['inconclusive', '暂无法判断']
                ] as const
              ).map(([outcome, label]) => (
                <button
                  key={outcome}
                  disabled={busy || !comparison.trim()}
                  onClick={() =>
                    void action(async () => {
                      const value = unwrap(
                        await window.agent.evolutionCompare({
                          project_id: projectId,
                          candidate_id: candidate.candidate_id,
                          outcome,
                          summary: comparison
                        })
                      )
                      if (alive.current) mergeCandidate(value)
                    })
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            {(candidate.comparisons ?? []).map((item, i) => (
              <p key={i}>
                {item.at} · {item.outcome} · 正文版本 {item.content_revision}{' '}
                {item.content_revision !== candidate.content_revision && '· 旧版本结果，已过期'} ·{' '}
                {item.summary}
              </p>
            ))}
          </details>
        )}
      </details>
      {evidence && (
        <EvolutionEvidencePanel
          projectId={projectId}
          view={evidence}
          onClose={() => setEvidence(null)}
        />
      )}
    </section>
  )
}
