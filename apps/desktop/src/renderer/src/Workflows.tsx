/** 任务流程编辑复用现有任务与会话。 Edit workflows on existing tasks and sessions. */
import { useEffect, useState } from 'react'
import type {
  SessionSummary,
  TaskView,
  TaskWorkflow,
  WorkflowCatalog,
  WorkflowStage,
  WorkflowTemplate
} from '../../generated/protocol'

/** 列表表单只修改配置，不自动执行阶段。 List forms edit configuration without starting work. */
function StageEditor({
  template,
  onChange
}: {
  template: WorkflowTemplate
  onChange: (value: WorkflowTemplate) => void
}) {
  const stages = template.stages ?? []
  /** 以阶段身份更新原列表。 Update a stage by stable identity. */
  function update(index: number, values: Partial<WorkflowStage>) {
    onChange({ ...template, stages: stages.map((s, i) => (i === index ? { ...s, ...values } : s)) })
  }
  return (
    <>
      <label>
        流程名称
        <input
          value={template.name}
          onChange={(e) => onChange({ ...template, name: e.target.value })}
        />
      </label>
      <label>
        说明
        <textarea
          value={template.description ?? ''}
          onChange={(e) => onChange({ ...template, description: e.target.value })}
        />
      </label>
      {stages.map((stage, index) => (
        <details key={stage.stage_id} className="detail-card">
          <summary>
            {index + 1}. {stage.name}
          </summary>
          <p className="muted">阶段身份：{stage.stage_id}</p>
          <label>
            阶段名称
            <input value={stage.name} onChange={(e) => update(index, { name: e.target.value })} />
          </label>
          <label>
            目标
            <textarea
              value={stage.goal ?? ''}
              onChange={(e) => update(index, { goal: e.target.value })}
            />
          </label>
          <label>
            Skill 身份（每行一个）
            <textarea
              value={(stage.skills ?? []).join('\n')}
              onChange={(e) =>
                update(index, { skills: e.target.value.split('\n').filter(Boolean) })
              }
            />
          </label>
          <label>
            建议角色
            <input
              value={stage.suggested_role ?? ''}
              onChange={(e) => update(index, { suggested_role: e.target.value })}
            />
          </label>
          <label>
            可选产物说明
            <textarea
              value={stage.artifacts ?? ''}
              onChange={(e) => update(index, { artifacts: e.target.value })}
            />
          </label>
          {(['depends_on', 'feedback_to'] as const).map((field) => (
            <fieldset key={field}>
              <legend>
                {field === 'depends_on' ? '依赖阶段（说明，不阻断跳过）' : '反馈可返回阶段'}
              </legend>
              {stages
                .filter((s) => s.stage_id !== stage.stage_id)
                .map((other) => (
                  <label key={other.stage_id}>
                    <input
                      type="checkbox"
                      checked={(stage[field] ?? []).includes(other.stage_id)}
                      onChange={(e) =>
                        update(index, {
                          [field]: e.target.checked
                            ? [...(stage[field] ?? []), other.stage_id]
                            : (stage[field] ?? []).filter((id) => id !== other.stage_id)
                        })
                      }
                    />
                    {other.name}
                  </label>
                ))}
            </fieldset>
          ))}
          <button
            type="button"
            disabled={index === 0}
            onClick={() => {
              const copy = [...stages]
              ;[copy[index - 1], copy[index]] = [copy[index], copy[index - 1]]
              onChange({ ...template, stages: copy })
            }}
          >
            上移
          </button>
          <button
            type="button"
            onClick={() =>
              onChange({
                ...template,
                stages: stages
                  .filter((s) => s.stage_id !== stage.stage_id)
                  .map((s) => ({
                    ...s,
                    depends_on: s.depends_on?.filter((id) => id !== stage.stage_id),
                    feedback_to: s.feedback_to?.filter((id) => id !== stage.stage_id)
                  }))
              })
            }
          >
            删除阶段
          </button>
        </details>
      ))}
      <button
        type="button"
        onClick={() =>
          onChange({
            ...template,
            stages: [...stages, { stage_id: crypto.randomUUID(), name: '新阶段' }]
          })
        }
      >
        添加阶段
      </button>
    </>
  )
}

/** 模板编辑、JSON 交换与新任务模板选择共用目录。 Share a catalog for template editing and selection. */
export function Workflows({
  selected,
  onSelect
}: {
  selected?: string | null
  onSelect?: (identity: string | null) => void
}) {
  const [catalog, setCatalog] = useState<WorkflowCatalog | null>(null)
  const [draft, setDraft] = useState<WorkflowTemplate | null>(null)
  const [json, setJson] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let disposed = false
    void window.agent
      .listWorkflows({})
      .then((r) => {
        if (!disposed) {
          if (r.ok) setCatalog(r.data)
          else setError(r.error.message)
        }
      })
      .catch(() => {
        if (!disposed) setError('模板目录读取失败。')
      })
    return () => {
      disposed = true
    }
  }, [])
  /** 原模板修改仅影响未来创建的任务。 Template edits affect future tasks only. */
  async function save(remove = false) {
    if (!draft || busy) return
    setBusy(true)
    setError('')
    try {
      const r = remove
        ? await window.agent.removeWorkflow({ template_id: draft.template_id })
        : await window.agent.saveWorkflow({ template: draft })
      if (r.ok) {
        setCatalog(r.data)
        setDraft(null)
      } else setError(r.error.message)
    } catch {
      setError('模板保存失败，编辑内容已保留。')
    } finally {
      setBusy(false)
    }
  }
  /** 导入内容用后端的同一契约解析。 Parse imported content through the backend contract. */
  async function importJson() {
    try {
      const result = await window.agent.parseWorkflow({ content: json })
      if (result.ok) {
        setDraft(result.data)
        setError('')
      } else setError(result.error.message)
    } catch {
      setError('JSON 不是有效的流程模板。')
    }
  }
  return (
    <details className="detail-card settings-card">
      <summary>
        工作流模板
        {onSelect &&
          ` · ${catalog?.templates?.find((t) => t.template_id === selected)?.name ?? '无模板'}`}
      </summary>
      {onSelect && (
        <label>
          新任务使用
          <select value={selected ?? ''} onChange={(e) => onSelect(e.target.value || null)}>
            <option value="">不使用模板</option>
            {catalog?.templates?.map((t) => (
              <option key={t.template_id} value={t.template_id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="muted">任务保存独立快照；编辑模板不改动已有任务。内置模板请复制后修改。</p>
      {catalog?.issues?.map((item) => (
        <p key={item} className="error">
          {item}
        </p>
      ))}
      {catalog?.templates?.map((t) => (
        <div key={t.template_id}>
          {t.name}{' '}
          <button type="button" onClick={() => setDraft(t)}>
            查看 / 编辑
          </button>
          <button
            type="button"
            onClick={() =>
              setDraft({ ...t, template_id: crypto.randomUUID(), name: `${t.name} 副本` })
            }
          >
            复制
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => setDraft({ template_id: crypto.randomUUID(), name: '新流程', stages: [] })}
      >
        新建模板
      </button>
      {draft && (
        <fieldset disabled={busy}>
          <StageEditor template={draft} onChange={setDraft} />
          <button
            type="button"
            disabled={draft.template_id === 'builtin:personal'}
            onClick={() => void save()}
          >
            保存模板
          </button>
          <button type="button" onClick={() => setJson(JSON.stringify(draft, null, 2))}>
            导出为 JSON
          </button>
          <button
            type="button"
            disabled={draft.template_id === 'builtin:personal'}
            onClick={() => void save(true)}
          >
            删除模板
          </button>
          <button type="button" onClick={() => setDraft(null)}>
            关闭编辑
          </button>
        </fieldset>
      )}
      <details>
        <summary>JSON 导入 / 导出</summary>
        <textarea rows={8} value={json} onChange={(e) => setJson(e.target.value)} />
        <button type="button" onClick={() => void importJson()}>
          载入编辑器
        </button>
        <button
          type="button"
          onClick={() =>
            void navigator.clipboard.writeText(json).catch(() => setError('无法复制 JSON。'))
          }
        >
          复制 JSON
        </button>
      </details>
      {error && <p className="error">{error}</p>}
    </details>
  )
}

/** 修改当前任务快照与阶段，会话和 Goal 保持原生命周期。 Edit task stages without starting sessions or Goals. */
export function TaskWorkflowEditor({
  task,
  onChanged,
  onSession
}: {
  task: TaskView
  onChanged: (task: TaskView) => void
  onSession: (id: string) => void
}) {
  const [draft, setDraft] = useState<TaskWorkflow | null>(task.workflow ?? null)
  const [chosen, setChosen] = useState<string | null>('builtin:personal')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [members, setMembers] = useState<SessionSummary[]>([])
  useEffect(() => {
    setDraft(task.workflow ?? null)
  }, [task])
  useEffect(() => {
    let disposed = false
    /** 从项目分页中收集当前任务成员。 Collect task members from project pages. */
    async function loadMembers() {
      let cursor: string | null = null
      const rows: SessionSummary[] = []
      do {
        const r = await window.agent.listSessions({
          project_id: task.project_id,
          limit: 100,
          cursor
        })
        if (disposed) return
        if (!r.ok) {
          setError(r.error.message)
          return
        }
        rows.push(...r.data.sessions.filter((s) => s.task_id === task.task_id))
        cursor = r.data.next_cursor
      } while (cursor !== null)
      setMembers(rows)
    }
    void loadMembers().catch(() => {
      if (!disposed) setError('会话目录读取失败。')
    })
    return () => {
      disposed = true
    }
  }, [task.task_id, task.revision])
  /** 应用模板只修改草稿，保存后才更新任务。 Applying a template only edits the draft until saved. */
  async function applyTemplate() {
    const r = await window.agent.listWorkflows({})
    if (!r.ok) {
      setError(r.error.message)
      return
    }
    const t = r.data.templates?.find((t) => t.template_id === chosen)
    setDraft(
      t
        ? { template: t, current_stage_id: t.stages?.[0]?.stage_id ?? null, session_stages: {} }
        : null
    )
  }
  /** 复用任务版本防止旧表单覆盖新进度。 Reuse task revisions to preserve newer progress. */
  async function save() {
    setBusy(true)
    setError('')
    try {
      const r = await window.agent.updateTaskWorkflow({
        task_id: task.task_id,
        operation_id: crypto.randomUUID(),
        expected_revision: task.revision,
        workflow: draft
      })
      if (r.ok) onChanged(r.data)
      else setError(r.error.message)
    } catch {
      setError('任务流程保存失败；草稿保留。')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="detail-card">
      <h2>任务流程</h2>
      <p className="muted">当前阶段描述长期工作位置；切换阶段不启动 Goal，也不授权修复。</p>
      <details>
        <summary>套用 / 替换模板</summary>
        <Workflows selected={chosen} onSelect={setChosen} />
        <button
          disabled={busy}
          onClick={() => void applyTemplate().catch(() => setError('模板读取失败。'))}
        >
          应用到任务草稿
        </button>
      </details>
      {draft ? (
        <>
          <label>
            当前阶段
            <select
              aria-label="当前阶段"
              value={draft.current_stage_id ?? ''}
              onChange={(e) => setDraft({ ...draft, current_stage_id: e.target.value || null })}
            >
              <option value="">未选择</option>
              {draft.template.stages?.map((s) => (
                <option key={s.stage_id} value={s.stage_id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <ol>
            {draft.template.stages?.map((s) => (
              <li key={s.stage_id}>
                {s.name} · {s.goal}
              </li>
            ))}
          </ol>
          {members.map((m) => (
            <div key={m.session_id}>
              <button onClick={() => onSession(m.session_id)}>
                {m.title}
                {m.role ? ` · ${m.role}` : ''}
              </button>
              <select
                aria-label={`${m.title} 的阶段`}
                value={draft.session_stages?.[m.session_id] ?? ''}
                onChange={(e) => {
                  const next = { ...draft.session_stages }
                  if (e.target.value) next[m.session_id] = e.target.value
                  else delete next[m.session_id]
                  setDraft({ ...draft, session_stages: next })
                }}
              >
                <option value="">跟随任务阶段</option>
                {draft.template.stages?.map((s) => (
                  <option key={s.stage_id} value={s.stage_id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
          ))}
          <details>
            <summary>编辑当前任务流程（不修改模板）</summary>
            <StageEditor
              template={draft.template}
              onChange={(template) => setDraft({ ...draft, template })}
            />
          </details>
        </>
      ) : (
        <p>此任务尚未采用流程模板，可继续正常工作。</p>
      )}
      <button disabled={busy} onClick={() => void save()}>
        保存任务流程
      </button>
      {error && <p className="error">{error}</p>}
    </section>
  )
}
