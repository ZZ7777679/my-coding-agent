/** 保存、导入和应用可分享团队模板。 Save, import and apply shareable team templates. */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { SaveTeamDraftArgs, SpaceConfig, TeamTemplate } from '../../generated/protocol'
import './SpaceChat.css'

type Props = {
  taskId: string
  config: SpaceConfig
  connected: boolean
  onDraft: (draft: SaveTeamDraftArgs) => void
  onChanged: () => void
}

/** 保存配置快照并将所选模板载入当前编辑图。 Save snapshots and load selected templates into the editable graph. */
export function SpaceTemplates({
  taskId,
  config,
  connected,
  onDraft,
  onChanged
}: Props): React.JSX.Element {
  const [name, setName] = useState('')
  const [templates, setTemplates] = useState<TeamTemplate[]>([])
  const [error, setError] = useState('')
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
    void load()
  }, [load])

  /** 保存当前编辑配置为独立模板。 Save the current edited configuration as an independent template. */
  async function save(): Promise<void> {
    const result = await window.agent.saveTeamTemplate({
      template_id: crypto.randomUUID(),
      name,
      description: '',
      draft: { config, initial_work_items: config.initial_work_items ?? [] }
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
      <summary>团队模板</summary>
      <div className="space-team-tools-body">
        {error && <p role="alert">{error}</p>}
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
