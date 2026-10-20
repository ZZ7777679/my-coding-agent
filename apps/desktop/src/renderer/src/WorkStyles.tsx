/** 组合蓝图管理，套用不启动模型或创建协作会话。 Composite blueprints never auto-start models or peer sessions. */
import { useEffect, useRef, useState } from 'react'
import type { TaskView, WorkStyle, WorkStyleCatalog } from '../../generated/protocol'

/** 从当前任务保存、编辑与复用工作方式，并设置项目默认。 Capture, edit and reuse workstyles with project defaults. */
export function WorkStyles({
  projectId,
  task,
  selected,
  onSelect,
  onApplied
}: {
  projectId?: string
  task?: TaskView | null
  selected?: string
  onSelect?: (id: string) => void
  onApplied?: (value: TaskView) => void
}) {
  const [catalog, setCatalog] = useState<WorkStyleCatalog | null>(null)
  const [draft, setDraft] = useState<WorkStyle | null>(null)
  const [json, setJson] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  useEffect(() => {
    const ticket = ++generation.current
    void window.agent
      .listWorkStyles({ project_id: projectId })
      .then((result) => {
        if (ticket !== generation.current) return
        if (result.ok) setCatalog(result.data)
        else setError(result.error.message)
      })
      .catch(() => {
        if (ticket === generation.current) setError('工作方式目录读取失败。')
      })
    return () => {
      generation.current += 1
    }
  }, [projectId])

  /** 每个动作只更新同一界面的状态，失败保留草稿。 Keep drafts and discard stale action responses. */
  async function action(job: () => Promise<void>) {
    const ticket = generation.current
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await job()
    } catch {
      if (ticket === generation.current) setError('操作未完成，当前草稿保留。')
    } finally {
      if (ticket === generation.current) setBusy(false)
    }
  }
  /** 从持久配置提取，不从尚未保存的编辑器猜测。 Capture persisted definitions, never unsaved editor guesses. */
  async function capture() {
    if (!task) return
    const ticket = generation.current
    const response = await window.agent.captureWorkStyle({
      task_id: task.task_id,
      style_id: crypto.randomUUID(),
      name: task.fields.title + ' · 工作方式'
    })
    if (ticket !== generation.current) return
    if (response.ok) {
      setDraft(response.data)
      setNotice('预览已生成，请编辑并保存。当前未保存的任务草稿不在其中。')
    } else setError(response.error.message)
  }
  /** 保存模板只影响未来采用它的任务。 Save without mutating task snapshots. */
  async function save() {
    if (!draft) return
    const ticket = generation.current
    const response = await window.agent.saveWorkStyle({ style: draft })
    if (ticket !== generation.current) return
    if (!response.ok) {
      setError(response.error.message)
      return
    }
    setDraft(response.data)
    setNotice('工作方式已保存；已有任务快照保持独立。')
    const refreshed = await window.agent.listWorkStyles({ project_id: projectId })
    if (ticket === generation.current && refreshed.ok) setCatalog(refreshed.data)
  }
  /** 应用配置前读取最新空间版本，不修改目标和历史。 Adopt configuration with current space revision and retained history. */
  async function apply(style: WorkStyle) {
    if (!task) return
    const ticket = generation.current
    const space = await window.agent.getSpace(task.task_id)
    if (ticket !== generation.current) return
    if (!space.ok) {
      setError(space.error.message)
      return
    }
    const response = await window.agent.applyWorkStyle({
      task_id: task.task_id,
      style_id: style.style_id,
      operation_id: crypto.randomUUID(),
      expected_revision: task.revision,
      expected_space_revision: space.data.space?.revision ?? null
    })
    if (ticket !== generation.current) return
    if (response.ok) {
      onApplied?.(response.data)
      setNotice('定义已采用，任务目标与原运行记录保留。尚未启动工作。')
    } else setError(response.error.message)
  }
  return (
    <details className="detail-card settings-card workstyles">
      <summary>组合工作方式 · 流程／团队／工作图／Skill</summary>
      <p className="muted">
        模板 → 项目默认 →
        任务独立快照。模板只包含方法与角色定义；不会带入旧会话、运行结果或创建新成员会话。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {catalog?.issues?.map((issue) => (
        <p key={issue} role="alert">
          {issue}
        </p>
      ))}
      {onSelect && (
        <label>
          新任务工作方式
          <select
            aria-label="新任务工作方式"
            value={selected ?? '@project'}
            onChange={(e) => onSelect(e.target.value)}
          >
            <option value="@project">
              使用项目默认
              {catalog?.default_style_id
                ? ' · ' + catalog.styles?.find((s) => s.style_id === catalog.default_style_id)?.name
                : '（未设置则用下方流程）'}
            </option>
            <option value="">只使用单独工作流</option>
            {catalog?.styles?.map((style) => (
              <option key={style.style_id} value={style.style_id}>
                {style.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {projectId && (
        <label>
          项目默认（仅影响未来任务）
          <select
            aria-label="项目默认工作方式"
            disabled={busy}
            value={catalog?.default_style_id ?? ''}
            onChange={(e) => {
              const id = e.target.value
              const ticket = generation.current
              void action(async () => {
                const response = await window.agent.defaultWorkStyle({
                  project_id: projectId,
                  style_id: id || null
                })
                if (ticket !== generation.current) return
                if (response.ok) setCatalog(response.data)
                else setError(response.error.message)
              })
            }}
          >
            <option value="">无组合默认</option>
            {catalog?.styles?.map((style) => (
              <option key={style.style_id} value={style.style_id}>
                {style.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {task && (
        <button disabled={busy} onClick={() => void action(capture)}>
          从当前任务保存为工作方式
        </button>
      )}
      {!catalog?.styles?.length && <p>暂无组合；可从一个已经配置的任务保存，或导入 JSON。</p>}
      {catalog?.styles?.map((style) => (
        <details key={style.style_id}>
          <summary>{style.name}</summary>
          <p>{style.description}</p>
          <p>
            流程：{style.workflow?.name ?? '无'}；角色 {style.team?.members?.length ?? 0}；工作节点{' '}
            {style.team?.initial_work_items?.length ?? 0}
          </p>
          <p>
            Skill：{style.skill_ids?.join('、') || '无额外全局 Skill'}（阶段与角色的 Skill
            保留在相应定义中）
          </p>
          <button disabled={busy} onClick={() => setDraft(style)}>
            预览／编辑
          </button>
          <button
            disabled={busy}
            onClick={() =>
              setDraft({ ...style, style_id: crypto.randomUUID(), name: style.name + ' · 副本' })
            }
          >
            复制
          </button>
          <button onClick={() => setJson(JSON.stringify(style, null, 2))}>导出 JSON</button>
          {task && (
            <button disabled={busy} onClick={() => void action(() => apply(style))}>
              采用定义到当前任务
            </button>
          )}
        </details>
      ))}
      {draft && (
        <fieldset className="detail-card" disabled={busy}>
          <label>
            名称
            <input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </label>
          <label>
            用途
            <textarea
              value={draft.description ?? ''}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
          </label>
          <label>
            共同 Skill（每行一个身份）
            <textarea
              value={draft.skill_ids?.join('\n') ?? ''}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  skill_ids: e.target.value
                    .split('\n')
                    .map((v) => v.trim())
                    .filter(Boolean)
                })
              }
            />
          </label>
          <details>
            <summary>阶段 {draft.workflow?.stages?.length ?? 0}</summary>
            {draft.workflow?.stages?.map((stage, index) => (
              <label key={stage.stage_id}>
                {stage.name}
                <textarea
                  value={stage.goal ?? ''}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      workflow: draft.workflow
                        ? {
                            ...draft.workflow,
                            stages: draft.workflow.stages?.map((s, i) =>
                              i === index ? { ...s, goal: e.target.value } : s
                            )
                          }
                        : null
                    })
                  }
                />
              </label>
            ))}
          </details>
          <details>
            <summary>团队角色与工作图</summary>
            {draft.team?.members?.map((member, index) => (
              <label key={member.member_id}>
                {member.name}
                <textarea
                  value={member.role ?? ''}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      team: {
                        ...draft.team,
                        members: draft.team?.members?.map((m, i) =>
                          i === index ? { ...m, role: e.target.value } : m
                        )
                      }
                    })
                  }
                />
              </label>
            ))}
            {draft.team?.initial_work_items?.map((item) => (
              <p key={item.work_id}>
                {item.title} · {item.scope}
                <br />
                依赖：{item.depends_on?.join('、') || '无'}；反馈：
                {item.feedback_to?.join('、') || '无'}
              </p>
            ))}
          </details>
          <button disabled={busy || !draft.name.trim()} onClick={() => void action(save)}>
            保存组合工作方式
          </button>
          <button
            onClick={() => {
              setJson(JSON.stringify(draft, null, 2))
              setNotice('完整定义已放入下方 JSON，可编辑关系和工作节点，再解析预览。')
            }}
          >
            编辑完整定义
          </button>
          <button onClick={() => setDraft(null)}>关闭预览</button>
        </fieldset>
      )}
      <details>
        <summary>JSON 导入／导出／完整定义编辑</summary>
        <textarea
          aria-label="工作方式 JSON"
          rows={12}
          value={json}
          onChange={(e) => setJson(e.target.value)}
        />
        <button
          disabled={busy || !json.trim()}
          onClick={() => {
            const ticket = generation.current
            void action(async () => {
              const response = await window.agent.parseWorkStyle({ content: json })
              if (ticket !== generation.current) return
              if (response.ok) {
                setDraft(response.data)
                setNotice('已解析；保存前可检查角色、路径和 Skill 引用。')
              } else setError(response.error.message)
            })
          }}
        >
          解析预览
        </button>
        <button
          disabled={!json}
          onClick={() =>
            void navigator.clipboard
              .writeText(json)
              .catch(() => setError('复制失败，可手动选中复制。'))
          }
        >
          复制 JSON
        </button>
      </details>
    </details>
  )
}
