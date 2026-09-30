/** 统一管理 Skill 资源和项目导入。 Central skill library and explicit project imports. */
import { useEffect, useState } from 'react'
import type { SkillCatalog, SkillDocument, SkillItem } from '../../generated/protocol'
import { OnlineSkills } from './OnlineSkills'
import { SkillSites } from './SkillSites'

/** 桌面只通过后端读写 Skill；选择会话后可指定持续使用的方法。
 * Manage resources through the backend, with optional per-session references.
 */
export function Skills({
  projectId,
  sessionId = null
}: {
  projectId: string | null
  sessionId?: string | null
}) {
  const [catalog, setCatalog] = useState<SkillCatalog | null>(null)
  const [document, setDocument] = useState<SkillDocument | null>(null)
  const [content, setContent] = useState('')
  const [name, setName] = useState('')
  const [scope, setScope] = useState<'user' | 'project'>('user')
  const [source, setSource] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<'installed' | 'online' | 'sites'>('installed')
  const [sourceRequest, setSourceRequest] = useState<{ id: string; url: string } | null>(null)
  useEffect(() => {
    let disposed = false
    void window.agent
      .listSkills({ project_id: projectId, session_id: sessionId })
      .then((r) => {
        if (!disposed) {
          if (r.ok) setCatalog(r.data)
          else setError(r.error.message)
        }
      })
      .catch(() => {
        if (!disposed) setError('技能目录读取失败。')
      })
    return () => {
      disposed = true
    }
  }, [projectId, sessionId])
  /** 用显式操作更新目录或选项。 Update catalog through an explicit action. */
  async function act(
    action: 'refresh' | 'save' | 'import' | 'enable' | 'select',
    id = '',
    enabled = true
  ) {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const params = { project_id: projectId, session_id: sessionId }
      const result =
        action === 'refresh'
          ? await window.agent.listSkills(params)
          : action === 'enable'
            ? await window.agent.enableSkill({ ...params, skill_id: id, enabled })
            : action === 'select'
              ? await window.agent.selectSkills({
                  ...params,
                  selected: enabled
                    ? [...(catalog?.selected ?? []), id]
                    : (catalog?.selected ?? []).filter((value) => value !== id)
                })
              : await window.agent.saveSkill({
                  ...params,
                  name,
                  content,
                  scope,
                  overwrite:
                    action === 'save' &&
                    document?.item.source === scope &&
                    document.item.name === name,
                  import_directory:
                    action === 'import'
                      ? source
                      : document?.item.source === 'builtin'
                        ? document.item.resource_base
                        : null
                })
      if (result.ok) {
        setCatalog(result.data)
        if (action === 'save') {
          const saved = result.data.items.find(
            (item) => item.source === scope && item.name === name
          )
          if (saved) setDocument({ item: saved, content })
        }
        setNotice(action === 'import' || action === 'save' ? 'Skill 已保存。' : '')
      } else setError(result.error.message)
    } catch {
      setError('资源操作失败，请查看目录中的实际状态。')
    } finally {
      setBusy(false)
    }
  }
  /** 从已发现的资源身份读取正文。 Load a discovered resource by identity. */
  async function read(id: string) {
    setBusy(true)
    setError('')
    try {
      const r = await window.agent.readSkill({
        project_id: projectId,
        session_id: sessionId,
        skill_id: id
      })
      if (r.ok) {
        setDocument(r.data)
        setContent(r.data.content)
        setName(r.data.item.name)
        setScope(r.data.item.source === 'project' ? 'project' : 'user')
      } else setError(r.error.message)
    } catch {
      setError('技能读取失败。')
    } finally {
      setBusy(false)
    }
  }
  /** 明确选择导入时才复制正文及附属文件到项目。 Copy body and assets only on explicit import. */
  async function importToProject(item: SkillItem) {
    if (!projectId || busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const params = { project_id: projectId, session_id: sessionId }
      const doc = await window.agent.readSkill({ ...params, skill_id: item.skill_id })
      if (!doc.ok) {
        setError(doc.error.message)
        return
      }
      const result = await window.agent.saveSkill({
        ...params,
        name: item.name,
        content: doc.data.content,
        scope: 'project',
        import_directory: item.resource_base
      })
      if (result.ok) {
        setCatalog(result.data)
        setNotice(`${item.name} 已导入项目 .agents/skills。`)
      } else setError(result.error.message)
    } catch {
      setError('项目导入失败，请检查来源和目标目录。')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <div className="resource-tabs" role="tablist" aria-label="Skill 来源">
        <button role="tab" aria-selected={tab === 'installed'} onClick={() => setTab('installed')}>
          已安装
        </button>
        <button role="tab" aria-selected={tab === 'sites'} onClick={() => setTab('sites')}>
          逛网站
        </button>
        <button role="tab" aria-selected={tab === 'online'} onClick={() => setTab('online')}>
          链接导入 / 快捷搜索
        </button>
      </div>
      {tab === 'sites' && (
        <SkillSites
          onImport={(url) => {
            setSourceRequest({ id: crypto.randomUUID(), url })
            setTab('online')
          }}
        />
      )}
      <div hidden={tab !== 'online'}>
        <OnlineSkills
          projectId={projectId}
          onInstalled={() => void act('refresh')}
          sourceRequest={sourceRequest}
        />
      </div>
      <section
        hidden={tab !== 'installed'}
        className="detail-card settings-card skill-manager"
        aria-label="Skill 资源库"
      >
        <p className="settings-hint">
          导入只保存资源。允许按需加载后，Agent 可通过 load_skill 读取正文；选择会话并勾选
          “本会话持续使用”会在后续请求带入正文。实际加载见会话的上下文材料与 Trace。
          用户 / 内置资源的启停为共享设置，项目资源只影响所属项目。
        </p>
        <button disabled={busy} onClick={() => void act('refresh')}>
          刷新目录
        </button>
        {error && <p role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}
        {catalog?.issues?.map((issue) => (
          <p key={issue}>{issue}</p>
        ))}
        {catalog?.items.map((item) => (
          <div className="skill-item" key={item.skill_id}>
            <div className="resource-item-heading">
              {sessionId && (
                <label className="skill-session-selection">
                  <input
                    type="checkbox"
                    aria-label={`本会话持续使用 ${item.name} ${item.source}`}
                    disabled={busy || !item.enabled}
                    checked={(catalog.selected ?? []).includes(item.skill_id)}
                    onChange={(e) => void act('select', item.skill_id, e.target.checked)}
                  />
                  本会话持续使用
                </label>
              )}
              <button disabled={busy} onClick={() => void read(item.skill_id)}>
                {item.name} · {item.source}
              </button>
              <label>
                <input
                  type="checkbox"
                  aria-label={`允许按需加载 ${item.name} ${item.source}`}
                  checked={item.enabled}
                  disabled={busy}
                  onChange={(e) => void act('enable', item.skill_id, e.target.checked)}
                />
                允许按需加载
              </label>
              {item.source !== 'project' && (
                <button disabled={busy || !projectId} onClick={() => void importToProject(item)}>
                  导入当前项目
                </button>
              )}
            </div>
            <p className="muted">
              {item.description}
              {item.shadowed_by && ` · 默认由 ${item.shadowed_by} 覆盖`}
            </p>
            {item.origin && (
              <p className="settings-hint">
                来源：{item.origin.repository} · {item.origin.directory || '仓库根目录'} ·{' '}
                {item.origin.revision?.slice(0, 12) || item.origin.ref}
              </p>
            )}
          </div>
        ))}
        <details>
          <summary>资源目录与项目规范</summary>
          <p className="settings-hint">
            用户目录：{catalog?.user_directory}
            <br />
            项目目录：{catalog?.project_directory || '尚未选择目标项目'}
          </p>
          {catalog?.rule_paths?.map((path) => (
            <p key={path}>{path}</p>
          ))}
        </details>
        <button
          onClick={() => {
            setDocument(null)
            setName('my-skill')
            setContent('---\nname: my-skill\ndescription: 描述用途\n---\n\n在这里编写方法。\n')
          }}
        >
          新建 Skill
        </button>
        <details>
          <summary>从本地文件夹导入</summary>
          <label>
            导入 Skill 文件夹
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="包含 SKILL.md 的完整目录"
            />
          </label>
          <p className="settings-hint">包含 references、scripts、assets 时会一起复制。</p>
        </details>
        {(content || source) && (
          <>
            <label>
              目录名
              <input
                value={name}
                readOnly={document?.item.source === 'builtin'}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              保存位置
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value === 'project' ? 'project' : 'user')}
              >
                <option value="user">用户目录</option>
                <option value="project" disabled={!projectId}>
                  项目 .agents/skills
                </option>
              </select>
            </label>
            {source && (
              <button disabled={busy || !name} onClick={() => void act('import')}>
                导入目录与附属资源
              </button>
            )}
          </>
        )}
        {content && (
          <>
            <button
              onClick={() => {
                setDocument(null)
                setContent('')
              }}
            >
              关闭正文
            </button>
            <p className="settings-hint">
              Hooks、内联 shell 与模型覆盖不自动执行。资源基目录：
              {document?.item.resource_base ?? '保存后确定'}
            </p>
            {document?.item.source === 'builtin' && (
              <p className="settings-hint">
                内置资源为随应用发布的版本。先复制到所选位置再编辑，参考文件、来源说明和许可证会一起保留。
              </p>
            )}
            <textarea
              aria-label="Skill 正文"
              rows={12}
              value={content}
              readOnly={document?.item.source === 'builtin'}
              onChange={(e) => setContent(e.target.value)}
            />
            <button disabled={busy || !name} onClick={() => void act('save')}>
              {document?.item.source === 'builtin' ? '复制为可编辑版本' : '保存 Skill'}
            </button>
          </>
        )}
      </section>
    </>
  )
}
