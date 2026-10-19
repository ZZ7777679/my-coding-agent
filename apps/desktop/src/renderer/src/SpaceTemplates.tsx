/** 生成待编辑草稿与可分享团队模板。 Generate editable drafts and shareable team templates. */
import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  SaveTeamDraftArgs,
  SpaceConfig,
  TeamGeneration,
  TeamTemplate
} from '../../generated/protocol'
import './SpaceChat.css'

type Props = {
  taskId: string
  config: SpaceConfig
  connected: boolean
  sessionId: string | null
  onDraft: (draft: SaveTeamDraftArgs) => void
  onChanged: () => void
}

/** 保存模板快照和模型生成结果，由用户显式采用草稿。 Save snapshots and generated results for explicit user adoption. */
export function SpaceTemplates({
  taskId,
  config,
  connected,
  sessionId,
  onDraft,
  onChanged
}: Props): React.JSX.Element {
  const [objective, setObjective] = useState('')
  const [name, setName] = useState('')
  const [templates, setTemplates] = useState<TeamTemplate[]>([])
  const [generation, setGeneration] = useState<TeamGeneration | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [json, setJson] = useState('')
  const identity = useRef(taskId)
  identity.current = taskId

  /** 读取已保存模板，迟到响应不能影响其他任务。 Read saved templates without applying stale task responses. */
  const load = useCallback(async (): Promise<void> => {
    if (!connected) return
    const result = await window.agent.listTeamTemplates({})
    if (identity.current !== taskId) return
    if (result.ok) setTemplates(result.data.templates)
    else setError(result.error.message)
  }, [connected, taskId])

  useEffect(() => {
    setGeneration(null)
    setError('')
    setPending(false)
    void load()
  }, [load])

  useEffect(() => {
    if (!connected) return
    let scheduled: ReturnType<typeof setTimeout> | undefined
    /** 重读持久生成结果，保存工具执行后显示真正草稿。 Read durable generation results after the real save tool executes. */
    const refresh = async (): Promise<void> => {
      const result = await window.agent.getSpaceChat({ task_id: taskId })
      if (identity.current !== taskId) return
      if (result.ok) setGeneration(result.data.generations?.at(-1) ?? null)
      else setError(result.error.message)
    }
    void refresh()
    const unsubscribe = window.agent.onSessionEvent((signal) => {
      if (signal.session_id === sessionId && ['changed', 'resync'].includes(signal.kind)) {
        if (scheduled) clearTimeout(scheduled)
        scheduled = setTimeout(() => {
          void refresh()
        }, 80)
      }
    })
    return () => {
      unsubscribe()
      if (scheduled) clearTimeout(scheduled)
    }
  }, [connected, sessionId, taskId])

  /** 现有会话运行只读生成，结果保留在编辑入口前。 Run read-only generation in the existing session and retain its result for editing. */
  async function generate(): Promise<void> {
    if (!sessionId || !objective.trim()) return
    setPending(true)
    const result = await window.agent.generateTeam({
      task_id: taskId,
      session_id: sessionId,
      operation_id: crypto.randomUUID(),
      objective,
      organisation: config.organisation ?? 'central'
    })
    if (identity.current !== taskId) return
    setPending(false)
    if (result.ok) {
      setGeneration(result.data)
      setError(result.data.error ?? '')
      onChanged()
    } else setError(result.error.message)
  }

  /** 保存当前编辑配置为独立模板。 Save the current edited configuration as an independent template. */
  async function save(): Promise<void> {
    const result = await window.agent.saveTeamTemplate({
      template_id: crypto.randomUUID(),
      name,
      description: objective,
      draft: { config, initial_work_items: generation?.draft?.initial_work_items ?? [] }
    })
    if (identity.current !== taskId) return
    if (result.ok) {
      setName('')
      setError('')
      await load()
    } else setError(result.error.message)
  }

  /** 复制模板为独立版本，不修改原团队。 Copy a template into an independent version without changing the original team. */
  async function copy(template: TeamTemplate): Promise<void> {
    const result = await window.agent.copyTeamTemplate({
      template_id: template.template_id,
      new_template_id: crypto.randomUUID(),
      name: `${template.name} 副本`
    })
    if (identity.current !== taskId) return
    if (result.ok) await load()
    else setError(result.error.message)
  }

  /** 获取可分享 JSON，内容中不包含会话历史。 Fetch shareable JSON without session history. */
  async function exportTemplate(template: TeamTemplate): Promise<void> {
    const result = await window.agent.exportTeamTemplate({ template_id: template.template_id })
    if (identity.current !== taskId) return
    if (result.ok) {
      setJson(result.data.content)
      setError('')
    } else setError(result.error.message)
  }

  /** 严格导入文本，后台只保存模板。 Strictly import text; the backend only saves its template. */
  async function importTemplate(): Promise<void> {
    const result = await window.agent.importTeamTemplate({
      template_id: crypto.randomUUID(),
      content: json
    })
    if (identity.current !== taskId) return
    if (result.ok) {
      setJson('')
      setError('')
      await load()
    } else setError(result.error.message)
  }

  /** 使用浏览器用户选定的文件内容，不访问任意本机路径。 Read a browser-selected file without arbitrary filesystem access. */
  async function selectFile(file: File | undefined): Promise<void> {
    if (file) setJson(await file.text())
  }

  return (
    <details className="space-team-tools">
      <summary>生成团队 / 团队模板</summary>
      <div className="space-team-tools-body">
        {error && <p role="alert">{error}</p>}
        <textarea
          aria-label="团队生成目标"
          placeholder="描述目标，让当前规划会话读取项目并生成可编辑团队"
          value={objective}
          onChange={(event) => setObjective(event.target.value)}
        />
        <button
          disabled={!connected || !sessionId || pending || !objective.trim()}
          onClick={() => void generate()}
        >
          生成团队草稿
        </button>
        {!sessionId && <p className="muted">请选择这个任务的现有会话用于规划。</p>}
        {generation && (
          <div>
            <p>
              {generation.error ||
                (generation.draft
                  ? `草稿包含 ${generation.draft.config.members?.length ?? 0} 个成员，采用后可继续编辑。`
                  : '已发起真实 Plan 生成；等待草稿保存，可在原会话查看状态。')}
            </p>
            {generation.draft && (
              <button onClick={() => onDraft(generation.draft!)}>采用草稿到团队编辑区</button>
            )}
          </div>
        )}
        <div className="space-template-actions">
          <input
            aria-label="团队模板名称"
            placeholder="模板名称"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button disabled={!connected || !name.trim()} onClick={() => void save()}>
            保存当前团队模板
          </button>
        </div>
        <div className="space-template-list">
          {templates.map((template) => (
            <article key={template.template_id}>
              <strong>{template.name}</strong>
              <small>{template.draft.config.members?.length ?? 0} 个成员</small>
              <button onClick={() => onDraft(template.draft)}>采用模板快照</button>
              <button disabled={!connected} onClick={() => void copy(template)}>
                复制
              </button>
              <button disabled={!connected} onClick={() => void exportTemplate(template)}>
                导出 JSON
              </button>
            </article>
          ))}
        </div>
        <label>
          导入模板文件{' '}
          <input
            type="file"
            accept="application/json,.json"
            onChange={(event) => void selectFile(event.target.files?.[0])}
          />
        </label>
        <textarea
          aria-label="团队模板导入导出 JSON"
          placeholder="粘贴模板 JSON；导出结果也显示在此处，可复制保存"
          value={json}
          onChange={(event) => setJson(event.target.value)}
        />
        <button disabled={!connected || !json.trim()} onClick={() => void importTemplate()}>
          导入 JSON 为新模板
        </button>
      </div>
    </details>
  )
}
