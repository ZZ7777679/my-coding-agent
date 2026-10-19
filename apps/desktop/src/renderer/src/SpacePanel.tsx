/** 任务级合作空间配置与显式会话组建。 Task-level space configuration and explicit session assembly. */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Background, Controls, Handle, MarkerType, Position, ReactFlow } from '@xyflow/react'
import type {
  Connection,
  Edge,
  Node,
  NodeProps,
  NodeChange,
  EdgeChange,
  Viewport,
  ReactFlowInstance
} from '@xyflow/react'
import type {
  SessionSummary,
  SkillCatalog,
  SpaceConfig,
  SpaceEdge,
  SpaceMember,
  SpaceLayout,
  SpaceResult,
  SpaceView,
  TaskView
} from '../../generated/protocol'
import type { Result } from '../../shared/api'
import type { WorkspaceSelection } from './TaskNavigation'
import '@xyflow/react/dist/style.css'
import './SpacePanel.css'
import { SpaceChat } from './SpaceChat'
import { SpaceTemplates } from './SpaceTemplates'
import { WorkGraphPanel } from './WorkGraphPanel'
import { arrangeMembers } from './space-layout'

type Props = {
  task: TaskView
  connected: boolean
  onSelect: (selection: WorkspaceSelection) => void
  onChanged: () => void
}
type DraftState = {
  space: SpaceView | null
  draft: SpaceConfig | null
  baseRevision: number | null
  selectedMember: string | null
  selectedEdge: string | null
  graphOpen: boolean
  viewport?: Viewport
  error: string
  notice: string
  pendingBinding?: { payload: string; operationId: string }
}

// 切换任务或会话保留本窗口草稿；持久配置仍由后端保存。
// Preserve window drafts across navigation; durable configuration remains backend-owned.
const drafts = new Map<string, DraftState>()
const edgeLabels: Record<SpaceEdge['kind'], string> = {
  delegate: '委派',
  result: '结果交付',
  discuss: '讨论',
  feedback: '反馈'
}

type MemberNode = Node<{ label: ReactNode }, 'member'>

/** 四侧连接点使反馈线从相邻边出入，源和目标分开以支持拖线。
 * Keep directional handles on each side so feedback edges need not cross the cards. */
function MemberNodeView({ data }: NodeProps<MemberNode>): React.JSX.Element {
  return (
    <>
      {data.label}
      {Object.values(Position).flatMap((position) =>
        ['source', 'target'].map((kind) => (
          <Handle
            key={`${position}-${kind}`}
            id={`${kind}-${position}`}
            type={kind === 'source' ? 'source' : 'target'}
            position={position}
            style={
              position === Position.Left || position === Position.Right
                ? { top: kind === 'source' ? '35%' : '65%' }
                : { left: kind === 'source' ? '35%' : '65%' }
            }
          />
        ))
      )}
    </>
  )
}

const nodeTypes = { member: MemberNodeView }

/** 补齐生成 DTO 的可选默认字段，方便比较实际编辑内容。 Normalize optional DTO defaults for draft comparison. */
function normalize(config: SpaceConfig): SpaceConfig {
  return {
    organisation: config.organisation ?? 'central',
    receiver_member_id: config.receiver_member_id ?? null,
    initial_work_items: config.initial_work_items ?? [],
    members: (config.members ?? []).map((member) => ({
      ...member,
      role: member.role ?? '',
      scope: member.scope ?? '',
      skill_ids: member.skill_ids ?? [],
      position: { x: member.position?.x ?? 0, y: member.position?.y ?? 0 }
    })),
    edges: (config.edges ?? []).map((edge) => ({ ...edge, label: edge.label ?? '' }))
  }
}

/** 真实会话摘要转换为短状态；未读到记录时不猜测运行状态。 Describe real session summaries without inferring missing state. */
function sessionStatus(session: SessionSummary | undefined): string {
  if (!session) return '状态尚未读取'
  if (session.issue) return session.issue
  if (!session.run) return '尚无运行'
  if (session.run.waiting_for) return '等待协作'
  const labels = {
    running: '运行中',
    stopping: '停止中',
    completed: '最近运行已完成',
    failed: '最近运行失败',
    cancelled: '已取消',
    budget_exceeded: '预算已用尽',
    interrupted: '运行已中断'
  }
  return labels[session.run.status]
}

/** 按任务身份隔离编辑器，旧任务异步结果不能覆盖新任务。 Isolate editors by task identity against stale responses. */
export function SpacePanel(props: Props) {
  return <SpaceEditor key={`${props.task.project_id}/${props.task.task_id}`} {...props} />
}

/** 编辑图和成员，保存配置与组建会话分别执行。 Edit graph and members with separate config and assembly actions. */
function SpaceEditor({ task, connected, onSelect, onChanged }: Props) {
  const identity = `${task.project_id}/${task.task_id}`
  const [state, setState] = useState<DraftState>(
    () =>
      drafts.get(identity) ?? {
        space: null,
        draft: null,
        baseRevision: null,
        selectedMember: null,
        selectedEdge: null,
        graphOpen: true,
        error: '',
        notice: ''
      }
  )
  const stateRef = useRef(state)
  const mounted = useRef(true)
  const [loading, setLoading] = useState(true)
  const [perspective, setPerspective] = useState<'team' | 'work'>('team')
  const [spaceKnown, setSpaceKnown] = useState(false)
  const [busy, setBusy] = useState(false)
  const [catalog, setCatalog] = useState<SkillCatalog | null>(null)
  const [catalogError, setCatalogError] = useState('')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [sessionCursor, setSessionCursor] = useState<string | null>(null)
  const [sessionError, setSessionError] = useState('')
  const [sessionBusy, setSessionBusy] = useState(false)
  const [bindingTarget, setBindingTarget] = useState('')
  const sessionGeneration = useRef(0)
  const spaceGeneration = useRef(0)
  const actionBusy = useRef(false)
  const layoutPending = useRef<SpaceLayout | null>(null)
  const layoutPromise = useRef<Promise<void> | null>(null)
  const graph = useRef<ReactFlowInstance<MemberNode> | null>(null)
  const members = state.draft?.members ?? []
  const relations = state.draft?.edges ?? []
  const member = members.find((item) => item.member_id === state.selectedMember)
  const relation = relations.find((item) => item.edge_id === state.selectedEdge)
  const dirty =
    !!state.draft &&
    (!state.space ||
      JSON.stringify(normalize(state.draft)) !== JSON.stringify(normalize(state.space.config)))

  /** 同步本任务草稿缓存，卸载后的结果仅更新原任务缓存。 Update this task's cache; late responses stay with their original task. */
  const update = useCallback(
    (change: (old: DraftState) => DraftState) => {
      const next = change(drafts.get(identity) ?? stateRef.current)
      stateRef.current = next
      drafts.set(identity, next)
      if (mounted.current) setState(next)
    },
    [identity]
  )

  /** 后端重读保留未保存草稿和其版本，冲突由保存边界报告。 Reload backend facts while retaining draft contents and their base revision. */
  const loadSpace = useCallback(
    async (discard = false) => {
      if (!mounted.current) return
      const generation = ++spaceGeneration.current
      setLoading(true)
      try {
        const result = await window.agent.getSpace(task.task_id)
        if (!mounted.current || generation !== spaceGeneration.current) return
        if (!result.ok) update((old) => ({ ...old, error: result.error.message }))
        else if (result.data.space && result.data.space.project_id !== task.project_id)
          update((old) => ({ ...old, error: '空间不属于所选任务项目。' }))
        else {
          setSpaceKnown(true)
          update((old) => {
            const space = result.data.space
            const keep =
              !discard &&
              old.draft !== null &&
              (!old.space ||
                JSON.stringify(normalize(old.draft)) !==
                  JSON.stringify(normalize(old.space.config)))
            return {
              ...old,
              space,
              draft: keep ? old.draft : space ? normalize(space.config) : null,
              baseRevision: keep ? old.baseRevision : (space?.revision ?? null),
              graphOpen: keep ? old.graphOpen : (space?.layout?.graph_open ?? true),
              viewport: keep
                ? old.viewport
                : space?.layout?.viewport
                  ? {
                      x: space.layout.viewport.x ?? 0,
                      y: space.layout.viewport.y ?? 0,
                      zoom: space.layout.viewport.zoom ?? 1
                    }
                  : undefined,
              error: '',
              notice: discard ? '已重新载入保存的配置。' : old.notice
            }
          })
        }
      } catch {
        if (mounted.current && generation === spaceGeneration.current)
          update((old) => ({ ...old, error: '空间读取失败，编辑草稿已保留。' }))
      } finally {
        if (mounted.current && generation === spaceGeneration.current) setLoading(false)
      }
    },
    [task.task_id, task.project_id, update]
  )

  /** 串行保存展示状态，仅合并最新布局，不能保存成员草稿。 Serialize presentation saves, coalescing the latest layout without saving team drafts. */
  const flushLayout = (): Promise<void> => {
    if (layoutPromise.current) return layoutPromise.current
    if (!connected || actionBusy.current || !layoutPending.current || !stateRef.current.space)
      return Promise.resolve()
    /** 队列只写显示布局，失败保留本窗口状态并明确提示。 Drain presentation writes while preserving local state on failure. */
    const save = async () => {
      while (layoutPending.current && !actionBusy.current) {
        const layout = layoutPending.current
        layoutPending.current = null
        try {
          const result = await window.agent.saveSpaceLayout({ task_id: task.task_id, layout })
          if (!result.ok) {
            update((old) => ({ ...old, error: result.error.message }))
            break
          }
          const space = result.data.space
          if (!space || space.task_id !== task.task_id || space.project_id !== task.project_id) {
            update((old) => ({ ...old, error: '布局保存结果未确认，请重新载入空间检查。' }))
            break
          }
          update((old) => ({
            ...old,
            space,
            // 仅展示状态推进版本；外部配置变更仍保留原草稿的冲突版本。
            // Advance a presentation-only revision; external config changes retain the draft's conflict revision.
            baseRevision:
              old.baseRevision === old.space?.revision &&
              JSON.stringify(normalize(old.space.config)) ===
                JSON.stringify(normalize(space.config))
                ? space.revision
                : old.baseRevision
          }))
        } catch {
          update((old) => ({ ...old, error: '布局保存未确认，当前窗口布局已保留。' }))
          break
        }
      }
    }
    layoutPromise.current = save().finally(() => {
      layoutPromise.current = null
    })
    return layoutPromise.current
  }

  /** 图开关与视口自动保存展示状态，新空间未保存时仅保留窗口草稿。 Persist graph visibility and viewport, caching presentation for unsaved spaces. */
  const changeLayout = (fields: { graphOpen?: boolean; viewport?: Viewport }) => {
    update((old) => ({ ...old, ...fields }))
    if (!stateRef.current.space) return
    layoutPending.current = {
      graph_open: stateRef.current.graphOpen,
      viewport: stateRef.current.viewport ?? null
    }
    void flushLayout()
  }

  /** 分页读取同任务会话，并补读图上绑定；失败保留已知摘要。 Page task sessions and resolve bound references, retaining facts on failures. */
  const loadSessions = useCallback(
    async (cursor: string | null = null) => {
      const generation = ++sessionGeneration.current
      setSessionBusy(true)
      try {
        const result = await window.agent.listSessions({
          project_id: task.project_id,
          cursor,
          limit: 50
        })
        if (!mounted.current || generation !== sessionGeneration.current) return
        if (!result.ok) {
          setSessionError(result.error.message)
          return
        }
        const page = result.data.sessions.filter((item) => item.task_id === task.task_id)
        const ids = (stateRef.current.space?.bindings ?? []).flatMap((item) =>
          item.session_id ? [item.session_id] : []
        )
        const missing = [...new Set(ids)].filter(
          (id) => !page.some((item) => item.session_id === id)
        )
        const details = await Promise.allSettled(
          missing.map((session_id) => window.agent.getSession({ session_id, before_seq: null }))
        )
        if (!mounted.current || generation !== sessionGeneration.current) return
        const errors: string[] = []
        details.forEach((detail) => {
          if (detail.status === 'fulfilled' && detail.value.ok) {
            const summary = detail.value.data.summary
            if (summary.project_id === task.project_id && summary.task_id === task.task_id)
              page.push(summary)
          } else
            errors.push(
              detail.status === 'rejected'
                ? '部分绑定会话读取失败。'
                : detail.value.ok
                  ? ''
                  : detail.value.error.message
            )
        })
        setSessions((old) => [
          ...new Map(
            (cursor ? [...old, ...page] : page).map((item) => [item.session_id, item])
          ).values()
        ])
        setSessionCursor(result.data.next_cursor)
        if (result.data.unavailable_count)
          errors.push(`${result.data.unavailable_count} 个项目会话记录不可读。`)
        setSessionError([...new Set(errors)].join('；'))
      } catch {
        if (mounted.current && generation === sessionGeneration.current)
          setSessionError('会话状态读取失败，已知摘要已保留。')
      } finally {
        if (mounted.current && generation === sessionGeneration.current) setSessionBusy(false)
      }
    },
    [task.project_id, task.task_id]
  )

  useEffect(() => {
    mounted.current = true
    if (connected) {
      void loadSpace().then(() => {
        if (mounted.current) void loadSessions()
      })
      void window.agent
        .listSkills({ project_id: task.project_id, session_id: null })
        .then((result) => {
          if (!mounted.current) return
          if (result.ok) {
            setCatalog(result.data)
            setCatalogError('')
          } else setCatalogError(result.error.message)
        })
        .catch(() => {
          if (mounted.current) setCatalogError('Skill 目录读取失败，可在左侧资源管理中检查。')
        })
    } else setLoading(false)
    return () => {
      mounted.current = false
      ++sessionGeneration.current
      ++spaceGeneration.current
    }
  }, [connected, loadSpace, loadSessions, task.project_id])
  useEffect(() => {
    if (!connected) return
    // 只读状态刷新不订阅/接管会话，也不调用模型。
    // Read-only refreshes neither attach to sessions nor call models.
    const timer = window.setInterval(() => {
      if (!actionBusy.current) void loadSessions()
    }, 5000)
    const unsubscribe = window.agent.onSessionEvent((signal) => {
      const bound = stateRef.current.space?.bindings?.some(
        (item) => item.session_id === signal.session_id
      )
      if (bound && (signal.kind === 'changed' || signal.kind === 'resync')) void loadSessions()
    })
    return () => {
      window.clearInterval(timer)
      unsubscribe()
    }
  }, [connected, loadSessions])
  useEffect(() => setBindingTarget(''), [state.selectedMember])

  /** 草稿更新不创建会话或触发执行。 Draft changes never create sessions or start execution. */
  const editConfig = (change: (config: SpaceConfig) => SpaceConfig) => {
    if (busy || loading) return
    update((old) => (old.draft ? { ...old, draft: change(old.draft), notice: '' } : old))
  }
  /** 保留成员身份，仅更新选中的配置字段。 Preserve member identity while changing its configuration. */
  const editMember = (fields: Partial<SpaceMember>) =>
    editConfig((config) => ({
      ...config,
      members: (config.members ?? []).map((item) =>
        item.member_id === member?.member_id ? { ...item, ...fields } : item
      )
    }))
  /** 删除图节点只改配置，后端继续保存成员旧会话历史。 Remove graph nodes from config while the backend retains session history. */
  const removeMembers = (ids: Set<string>) =>
    editConfig((config) => ({
      ...config,
      members: (config.members ?? []).filter((item) => !ids.has(item.member_id)),
      edges: (config.edges ?? []).filter(
        (item) => !ids.has(item.source_member_id) && !ids.has(item.target_member_id)
      ),
      receiver_member_id:
        config.receiver_member_id && ids.has(config.receiver_member_id)
          ? null
          : config.receiver_member_id
    }))
  /** 新成员采用任务已确定模型和独立身份，不自动扩编会话。 New draft members use the task model and do not create sessions. */
  const addMember = () => {
    const id = crypto.randomUUID()
    editConfig((config) => ({
      ...config,
      members: [
        ...(config.members ?? []),
        {
          member_id: id,
          name: `成员 ${members.length + 1}`,
          role: '',
          scope: '',
          model_id: task.initial_model_id,
          skill_ids: [],
          position: { x: (members.length % 3) * 330, y: Math.floor(members.length / 3) * 194 }
        }
      ]
    }))
    update((old) => ({ ...old, selectedMember: id, selectedEdge: null }))
  }
  /** 创建有向关系；反馈环和同成员关系交由协议既有规则处理。 Add directed relations under the existing protocol rules, including feedback cycles. */
  const addRelation = (source: string, target: string) => {
    const id = crypto.randomUUID()
    editConfig((config) => ({
      ...config,
      edges: [
        ...(config.edges ?? []),
        {
          edge_id: id,
          source_member_id: source,
          target_member_id: target,
          kind: 'delegate',
          label: ''
        }
      ]
    }))
    update((old) => ({ ...old, selectedEdge: id, selectedMember: null }))
  }
  /** 接收保存事实，失败保留输入；成员局部错误独立展示。 Accept durable facts and retain inputs on failures, exposing member errors separately. */
  const accept = (result: Result<SpaceResult>, notice: string, submitted: SpaceConfig | null) => {
    if (!result.ok) {
      update((old) => ({ ...old, error: result.error.message }))
      return false
    }
    const space = result.data.space
    if (!space || space.task_id !== task.task_id || space.project_id !== task.project_id) {
      update((old) => ({ ...old, error: '操作未返回所选任务的空间，请重新读取确认。' }))
      return false
    }
    const partial = space.error || (space.bindings ?? []).some((binding) => binding.error)
    update((old) => ({
      ...old,
      space,
      draft:
        JSON.stringify(old.draft) === JSON.stringify(submitted)
          ? normalize(space.config)
          : old.draft,
      baseRevision: space.revision,
      error: space.error ?? '',
      notice: partial ? '部分操作未完成，请查看成员错误并明确重试。' : notice,
      // 部分失败保留原绑定操作，明确重试不会另建一个会话。
      // Retain the binding identity on partial failure so explicit retries reuse the session.
      pendingBinding: partial ? old.pendingBinding : undefined
    }))
    onChanged()
    if (mounted.current) void loadSessions()
    return true
  }
  /** 保存配置、批量组建或单成员绑定都来自明确点击，结果不明可用原操作身份重试。 Run explicit save, assembly or binding actions with retryable operation identities. */
  const act = async (kind: 'save' | 'start' | 'bind') => {
    if (!connected || actionBusy.current || loading || !stateRef.current.draft) return
    const intendedDraft = stateRef.current.draft
    const intendedMember = stateRef.current.selectedMember
    actionBusy.current = true
    setBusy(true)
    update((old) => ({ ...old, error: '', notice: '' }))
    try {
      // 在展示写入完成后取配置版本，避免正常布局保存造成版本冲突。
      // Read the config revision after presentation writes to avoid ordinary layout-save conflicts.
      await layoutPromise.current
      const current = stateRef.current
      if (kind === 'save') {
        const result = await window.agent.saveSpace({
          task_id: task.task_id,
          expected_revision: current.baseRevision,
          config: intendedDraft
        })
        if (accept(result, '空间配置已保存。成员会话尚不会自动执行。', intendedDraft)) {
          layoutPending.current = {
            graph_open: stateRef.current.graphOpen,
            viewport: stateRef.current.viewport ?? null
          }
        }
      } else if (kind === 'start') {
        accept(
          await window.agent.startSpace({ task_id: task.task_id }),
          '团队会话已组建，可打开成员会话讨论或执行。',
          intendedDraft
        )
      } else if (kind === 'bind' && intendedMember) {
        const payload = JSON.stringify({ member: intendedMember, target: bindingTarget })
        const operationId =
          current.pendingBinding?.payload === payload
            ? current.pendingBinding.operationId
            : crypto.randomUUID()
        update((old) => ({ ...old, pendingBinding: { payload, operationId } }))
        accept(
          await window.agent.bindSpaceMember({
            task_id: task.task_id,
            member_id: intendedMember,
            session_id: bindingTarget || null,
            operation_id: operationId
          }),
          '成员会话已绑定，旧会话历史仍可打开。',
          intendedDraft
        )
      }
    } catch {
      update((old) => ({
        ...old,
        error: '操作结果未确认，草稿已保留；请重新读取事实或用相同输入明确重试。'
      }))
    } finally {
      actionBusy.current = false
      if (mounted.current) setBusy(false)
      void flushLayout()
    }
  }
  /** 打开真实会话身份，导航不启动模型。 Navigate to a real session without starting model work. */
  const openSession = (sessionId: string) =>
    onSelect({ projectId: task.project_id, taskId: task.task_id, sessionId })
  const nodes = useMemo<MemberNode[]>(
    () =>
      members.map((item) => {
        const binding = state.space?.bindings?.find((value) => value.member_id === item.member_id)
        const session = sessions.find((value) => value.session_id === binding?.session_id)
        const tone =
          binding?.error || session?.issue || session?.run?.status === 'failed'
            ? 'failed'
            : session?.run?.waiting_for
              ? 'waiting'
              : session?.run?.status === 'running'
                ? 'running'
                : 'idle'
        return {
          id: item.member_id,
          type: 'member',
          className: `space-member-node ${tone}`,
          position: { x: item.position?.x ?? 0, y: item.position?.y ?? 0 },
          selected: state.selectedMember === item.member_id,
          data: {
            label: (
              <div className="space-node-label">
                <div className="space-node-heading">
                  <span className={`space-status-dot ${tone}`} />
                  <strong>{item.name}</strong>
                </div>
                <span title={item.role || ''}>{item.role || '未填写职责'}</span>
                <div className="space-node-badges">
                  <span>{item.model_id.startsWith('glm') ? 'GLM' : 'DeepSeek'}</span>
                  {state.draft?.receiver_member_id === item.member_id && <span>接收成员</span>}
                </div>
                <small>
                  {binding?.error ||
                    (binding?.session_id
                      ? sessionStatus(
                          sessions.find((value) => value.session_id === binding.session_id)
                        )
                      : '尚未绑定会话')}
                </small>
              </div>
            )
          }
        }
      }),
    [members, state.space, state.selectedMember, state.draft?.receiver_member_id, sessions]
  )
  const edges = useMemo<Edge[]>(
    () =>
      relations.map((item) => {
        const source = members.find(
          (member) => member.member_id === item.source_member_id
        )?.position
        const target = members.find(
          (member) => member.member_id === item.target_member_id
        )?.position
        const dx = (target?.x ?? 0) - (source?.x ?? 0)
        const dy = (target?.y ?? 0) - (source?.y ?? 0)
        const vertical = Math.abs(dy) > Math.abs(dx)
        const from = vertical ? (dy >= 0 ? 'bottom' : 'top') : dx >= 0 ? 'right' : 'left'
        const to = vertical ? (dy >= 0 ? 'top' : 'bottom') : dx >= 0 ? 'left' : 'right'
        const reciprocal = relations.some(
          (other) =>
            other.edge_id !== item.edge_id &&
            other.source_member_id === item.target_member_id &&
            other.target_member_id === item.source_member_id
        )
        return {
          id: item.edge_id,
          source: item.source_member_id,
          target: item.target_member_id,
          sourceHandle: `source-${from}`,
          targetHandle: `target-${item.source_member_id === item.target_member_id ? 'bottom' : to}`,
          type: 'smoothstep',
          pathOptions: { borderRadius: 12, stepPosition: reciprocal ? 0.3 : 0.5 },
          label: edgeLabels[item.kind],
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 18,
            height: 18,
            color:
              item.kind === 'feedback' ? '#d6ad83' : item.kind === 'result' ? '#a7d8bc' : '#869ebb'
          },
          selected: state.selectedEdge === item.edge_id,
          style: {
            stroke:
              item.kind === 'feedback' ? '#d6ad83' : item.kind === 'result' ? '#a7d8bc' : '#869ebb',
            strokeWidth: state.selectedEdge === item.edge_id ? 2.5 : 1.6,
            strokeDasharray: item.kind === 'feedback' || item.kind === 'discuss' ? '5 4' : undefined
          }
        }
      }),
    [relations, members, state.selectedEdge]
  )

  /** 只保存拖动位置及显式删除，不把测量数据写入业务配置。 Store only positions and explicit deletions, excluding graph measurements. */
  const changeNodes = (changes: NodeChange[]) => {
    const removed = new Set(
      changes.filter((change) => change.type === 'remove').map((change) => change.id)
    )
    if (removed.size) removeMembers(removed)
    const positions = changes.filter((change) => change.type === 'position')
    if (positions.length)
      editConfig((config) => ({
        ...config,
        members: (config.members ?? []).map((item) => {
          const change = positions.find((value) => value.id === item.member_id)
          return change?.position ? { ...item, position: change.position } : item
        })
      }))
  }
  /** 连线删除同步到草稿，其他图状态保持为显示状态。 Reflect edge deletion in drafts while keeping graph display state separate. */
  const changeEdges = (changes: EdgeChange[]) => {
    const removed = new Set(
      changes.filter((change) => change.type === 'remove').map((change) => change.id)
    )
    if (removed.size)
      editConfig((config) => ({
        ...config,
        edges: (config.edges ?? []).filter((item) => !removed.has(item.edge_id))
      }))
  }
  /** 拖动连接点创建关系，关系类型可在编辑区修改。 Create a relation from dragged handles, then edit its kind in the form. */
  const connect = (connection: Connection) => {
    if (connection.source && connection.target) addRelation(connection.source, connection.target)
  }
  /** 用户点击后复用首会话，保留模型和 Skill 选择，不新建会话。
   * Reuse the initial session with its current model and skills on explicit user action. */
  const useInitialSession = async () => {
    if (actionBusy.current) return
    actionBusy.current = true
    setBusy(true)
    try {
      const [session, skills] = await Promise.all([
        window.agent.getSession({ session_id: task.initial_session_id, before_seq: null }),
        window.agent.listSkills({
          project_id: task.project_id,
          session_id: task.initial_session_id
        })
      ])
      if (!session.ok || !skills.ok) {
        update((old) => ({
          ...old,
          error: !session.ok ? session.error.message : !skills.ok ? skills.error.message : ''
        }))
        return
      }
      const id = crypto.randomUUID()
      const config = normalize({
        receiver_member_id: id,
        members: [
          {
            member_id: id,
            name: '任务执行者',
            role: session.data.summary.role || '任务执行与协调',
            scope: session.data.summary.scope || task.fields.goal,
            model_id: session.data.summary.model_id,
            skill_ids: skills.data.selected ?? []
          }
        ]
      })
      update((old) => ({ ...old, draft: config }))
      if (
        !accept(
          await window.agent.saveSpace({ task_id: task.task_id, expected_revision: null, config }),
          '已建立工作空间。',
          config
        )
      )
        return
      accept(
        await window.agent.bindSpaceMember({
          task_id: task.task_id,
          member_id: id,
          session_id: task.initial_session_id,
          operation_id: crypto.randomUUID()
        }),
        '已接入首会话，可以创建工作图。',
        config
      )
      if (mounted.current) setPerspective('work')
    } finally {
      actionBusy.current = false
      if (mounted.current) setBusy(false)
    }
  }
  const binding = state.space?.bindings?.find((item) => item.member_id === member?.member_id)
  const disabled = busy || loading || !connected
  const retired = (state.space?.bindings ?? []).filter(
    (item) => !members.some((value) => value.member_id === item.member_id)
  )

  return (
    <section className="space-panel" aria-label="合作空间">
      <header className="space-heading">
        <div>
          <h2>合作空间</h2>
          <p className="muted">生成或编辑团队草稿，组建后通过群聊与合作目标推进。</p>
        </div>
        <span className="space-version">
          {state.space ? `版本 ${state.space.revision}` : '尚未创建'}
        </span>
      </header>
      {!connected && (
        <p role="status" className="muted">
          后端未连接，草稿已保留。
        </p>
      )}
      {state.error && (
        <p role="alert" className="notice">
          {state.error}
        </p>
      )}
      {state.notice && <p role="status">{state.notice}</p>}
      {loading && <p role="status">正在读取合作空间…</p>}
      <div className="space-toolbar" aria-label="合作空间视角">
        <button aria-pressed={perspective === 'team'} onClick={() => setPerspective('team')}>
          团队视角
        </button>
        <button
          aria-pressed={perspective === 'work'}
          disabled={!state.space}
          onClick={() => setPerspective('work')}
        >
          工作视角
        </button>
      </div>
      {state.space && (
        <div hidden={perspective !== 'work'}>
          <WorkGraphPanel
            active={perspective === 'work'}
            key={task.task_id}
            space={state.space}
            connected={connected}
            onChanged={onChanged}
            onSelectSession={(id) =>
              onSelect({ projectId: task.project_id, taskId: task.task_id, sessionId: id })
            }
          />
        </div>
      )}
      <div hidden={perspective !== 'team'}>
        <SpaceTemplates
          taskId={task.task_id}
          config={state.draft ?? normalize({})}
          connected={connected}
          sessionId={task.initial_session_id}
          onDraft={(draft) =>
            update((old) => ({
              ...old,
              draft: normalize({
                ...draft.config,
                initial_work_items:
                  draft.initial_work_items ?? draft.config.initial_work_items ?? []
              }),
              selectedMember: draft.config.members?.[0]?.member_id ?? null,
              selectedEdge: null,
              graphOpen: true,
              error: '',
              notice:
                '已进入团队编辑：可拖动节点、连接端口，点击成员或关系修改属性；保存后新增成员才需要组建。'
            }))
          }
          onChanged={onChanged}
        />
        {state.space && (
          <SpaceChat
            space={state.space}
            connected={connected}
            onSelectSession={(id) =>
              onSelect({ projectId: task.project_id, taskId: task.task_id, sessionId: id })
            }
            onChanged={onChanged}
          />
        )}
        {!state.draft && !loading && spaceKnown && (
          <div className="space-empty">
            <p>此任务仍使用已有会话。创建合作空间后可手动配置稳定成员。</p>
            <button
              disabled={disabled}
              onClick={() =>
                update((old) => ({
                  ...old,
                  draft: normalize({}),
                  baseRevision: null,
                  error: '',
                  notice: ''
                }))
              }
            >
              创建合作空间草稿
            </button>
            <button disabled={disabled} onClick={() => void useInitialSession()}>
              用首会话建立工作空间
            </button>
          </div>
        )}
        {state.draft && (
          <>
            <div className="space-toolbar">
              <button className="primary" disabled={disabled} onClick={() => void act('save')}>
                {busy ? '正在处理…' : '保存空间配置'}
              </button>
              <button
                disabled={disabled || !state.space || dirty || members.length === 0}
                onClick={() => void act('start')}
              >
                组建团队会话
              </button>
              <button disabled={disabled} onClick={addMember}>
                添加成员
              </button>
              <button
                disabled={disabled || members.length === 0}
                onClick={() => {
                  if (members[0])
                    addRelation(members[0].member_id, members[1]?.member_id ?? members[0].member_id)
                }}
              >
                添加关系
              </button>
              <button
                aria-expanded={state.graphOpen}
                disabled={busy || loading}
                onClick={() => changeLayout({ graphOpen: !state.graphOpen })}
              >
                {state.graphOpen ? '收起关系图' : '展开关系图'}
              </button>
              <button
                disabled={disabled || !members.length}
                onClick={() => {
                  editConfig((config) => ({ ...config, members: arrangeMembers(config) }))
                  changeLayout({ graphOpen: true, viewport: undefined })
                  window.requestAnimationFrame(() => {
                    void graph.current?.fitView({ padding: 0.22, maxZoom: 1 })
                  })
                }}
              >
                自动排布
              </button>
            </div>
            <p className="space-save-state muted">
              {dirty
                ? '有未保存编辑；保存后可组建或绑定成员会话。'
                : '配置已保存；组建只创建或绑定成员会话，不调用模型。'}
            </p>
            <details className="space-organisation">
              <summary>组织方式与输入接收成员</summary>
              <div className="space-fields">
                <label>
                  组织方式
                  <select
                    aria-label="组织方式"
                    value={state.draft.organisation ?? 'central'}
                    disabled={disabled}
                    onChange={(event) =>
                      editConfig((config) => ({
                        ...config,
                        organisation:
                          event.target.value === 'peer'
                            ? 'peer'
                            : event.target.value === 'hierarchical'
                              ? 'hierarchical'
                              : 'central'
                      }))
                    }
                  >
                    <option value="central">中心协调</option>
                    <option value="hierarchical">分层协作</option>
                    <option value="peer">对等协作</option>
                  </select>
                </label>
                <label>
                  输入接收成员
                  <select
                    aria-label="输入接收成员"
                    value={state.draft.receiver_member_id ?? ''}
                    disabled={disabled}
                    onChange={(event) =>
                      editConfig((config) => ({
                        ...config,
                        receiver_member_id: event.target.value || null
                      }))
                    }
                  >
                    <option value="">暂未指定</option>
                    {members.map((item) => (
                      <option key={item.member_id} value={item.member_id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="muted">组织方式保存为可编辑预设；关系描述协作方式，允许反馈环。</p>
            </details>
            <div className="space-graph-layout">
              <div>
                {state.graphOpen && (
                  <div className="space-graph" aria-label="成员关系图">
                    <ReactFlow
                      onInit={(instance) => {
                        graph.current = instance
                      }}
                      nodes={nodes}
                      nodeTypes={nodeTypes}
                      edges={edges}
                      onNodesChange={changeNodes}
                      onEdgesChange={changeEdges}
                      onConnect={connect}
                      nodesDraggable={!disabled}
                      nodesConnectable={!disabled}
                      deleteKeyCode={disabled ? null : 'Delete'}
                      colorMode="dark"
                      fitView={!state.viewport}
                      fitViewOptions={{ padding: 0.22, maxZoom: 1 }}
                      minZoom={0.15}
                      maxZoom={1.8}
                      defaultViewport={state.viewport}
                      onMoveEnd={(_event, viewport) => changeLayout({ viewport })}
                      onNodeClick={(_event, node) =>
                        update((old) => ({ ...old, selectedMember: node.id, selectedEdge: null }))
                      }
                      onNodeDoubleClick={(_event, node) => {
                        const sessionId = state.space?.bindings?.find(
                          (item) => item.member_id === node.id
                        )?.session_id
                        if (sessionId) openSession(sessionId)
                      }}
                      onEdgeClick={(_event, edge) =>
                        update((old) => ({ ...old, selectedEdge: edge.id, selectedMember: null }))
                      }
                    >
                      <Background gap={24} size={1} color="#34463e" />
                      <Controls
                        showInteractive={false}
                        position="bottom-right"
                        fitViewOptions={{ padding: 0.22, maxZoom: 1 }}
                      />
                    </ReactFlow>
                  </div>
                )}
                {state.graphOpen && (
                  <p className="space-graph-legend muted">
                    <span>实线：委派 / 结果</span>
                    <span>虚线：讨论 / 反馈</span>
                    <span>点击关系查看说明 · 双击成员打开会话 · 排布修改需保存</span>
                  </p>
                )}
                <div className="space-member-list" aria-label="空间成员">
                  {members.map((item) => {
                    const current = state.space?.bindings?.find(
                      (value) => value.member_id === item.member_id
                    )
                    return (
                      <button
                        key={item.member_id}
                        className={state.selectedMember === item.member_id ? 'selected' : ''}
                        onClick={() =>
                          update((old) => ({
                            ...old,
                            selectedMember: item.member_id,
                            selectedEdge: null
                          }))
                        }
                      >
                        <strong>{item.name}</strong>
                        <span>
                          {current?.error ||
                            (current?.session_id
                              ? sessionStatus(
                                  sessions.find((value) => value.session_id === current.session_id)
                                )
                              : '待组建')}
                        </span>
                      </button>
                    )
                  })}
                  {members.length === 0 && <p className="muted">添加成员开始配置团队。</p>}
                </div>
                <details className="space-relation-list">
                  <summary>全部关系（{relations.length}）</summary>
                  {relations.map((item) => (
                    <button
                      key={item.edge_id}
                      onClick={() =>
                        update((old) => ({
                          ...old,
                          selectedEdge: item.edge_id,
                          selectedMember: null
                        }))
                      }
                    >
                      {members.find((value) => value.member_id === item.source_member_id)?.name} →{' '}
                      {members.find((value) => value.member_id === item.target_member_id)?.name} ·{' '}
                      {edgeLabels[item.kind]}
                      {item.label ? ` · ${item.label}` : ''}
                    </button>
                  ))}
                </details>
              </div>
              {member && (
                <details className="space-editor" open key={member.member_id}>
                  <summary>成员配置 · {member.name}</summary>
                  <button onClick={() => update((old) => ({ ...old, selectedMember: null }))}>
                    关闭成员编辑
                  </button>
                  <fieldset disabled={disabled}>
                    <div className="space-fields">
                      <label>
                        成员名称
                        <input
                          aria-label="成员名称"
                          value={member.name}
                          maxLength={256}
                          onChange={(event) => editMember({ name: event.target.value })}
                        />
                      </label>
                      <label>
                        成员模型
                        <select
                          aria-label="成员模型"
                          value={member.model_id}
                          onChange={(event) =>
                            editMember({
                              model_id:
                                event.target.value === 'deepseek-v4.1-flash'
                                  ? 'deepseek-v4.1-flash'
                                  : 'glm-5.3-flash'
                            })
                          }
                        >
                          <option value="glm-5.3-flash">GLM-5.3-Flash</option>
                          <option value="deepseek-v4.1-flash">DeepSeek V4.1 Flash</option>
                        </select>
                      </label>
                    </div>
                    <label>
                      成员职责
                      <input
                        aria-label="成员职责"
                        value={member.role ?? ''}
                        maxLength={4096}
                        placeholder="例如：实现、调研、Review"
                        onChange={(event) => editMember({ role: event.target.value })}
                      />
                    </label>
                    <label>
                      成员工作范围
                      <textarea
                        aria-label="成员工作范围"
                        value={member.scope ?? ''}
                        maxLength={16000}
                        rows={2}
                        onChange={(event) => editMember({ scope: event.target.value })}
                      />
                    </label>
                    <details>
                      <summary>成员 Skill（{member.skill_ids?.length ?? 0}，可选）</summary>
                      {catalogError && <p role="alert">{catalogError}</p>}
                      {catalog?.issues?.map((issue) => (
                        <p key={issue} className="muted">
                          {issue}
                        </p>
                      ))}
                      {(catalog?.items ?? [])
                        .filter((item) => !item.shadowed_by)
                        .map((item) => (
                          <label className="space-skill" key={item.skill_id}>
                            <input
                              type="checkbox"
                              checked={member.skill_ids?.includes(item.skill_id) ?? false}
                              disabled={
                                item.enabled === false && !member.skill_ids?.includes(item.skill_id)
                              }
                              onChange={(event) =>
                                editMember({
                                  skill_ids: event.target.checked
                                    ? [...(member.skill_ids ?? []), item.skill_id]
                                    : (member.skill_ids ?? []).filter((id) => id !== item.skill_id)
                                })
                              }
                            />
                            <span>
                              {item.name}
                              {item.enabled === false ? '（未启用）' : ''}
                              <small>{item.description}</small>
                            </span>
                          </label>
                        ))}
                      {(member.skill_ids ?? [])
                        .filter(
                          (id) =>
                            !catalog?.items.some(
                              (item) => item.skill_id === id && !item.shadowed_by
                            )
                        )
                        .map((id) => (
                          <label className="space-skill" key={id}>
                            <input
                              type="checkbox"
                              checked
                              onChange={() =>
                                editMember({
                                  skill_ids: (member.skill_ids ?? []).filter(
                                    (value) => value !== id
                                  )
                                })
                              }
                            />
                            <span>目录中不可用：{id}</span>
                          </label>
                        ))}
                      {catalog && catalog.items.length === 0 && (
                        <p className="muted">尚无可选 Skill，可从左侧资源管理添加。</p>
                      )}
                    </details>
                    <button onClick={() => removeMembers(new Set([member.member_id]))}>
                      移除成员配置（保留旧会话）
                    </button>
                  </fieldset>
                  <details className="space-binding">
                    <summary>当前会话与历史</summary>
                    <p className="muted">
                      成员身份 {member.member_id}。更换会话保留成员职责与旧会话。
                    </p>
                    {binding?.error && <p role="alert">{binding.error}</p>}
                    {binding?.session_id ? (
                      <div className="space-session-row">
                        <span>
                          {sessionStatus(
                            sessions.find((item) => item.session_id === binding.session_id)
                          )}
                        </span>
                        <button
                          onClick={() => {
                            if (binding.session_id) openSession(binding.session_id)
                          }}
                        >
                          打开成员会话
                        </button>
                      </div>
                    ) : (
                      <p className="muted">尚未绑定成员会话。</p>
                    )}
                    <label>
                      绑定会话
                      <select
                        aria-label="绑定会话"
                        value={bindingTarget}
                        disabled={disabled || dirty}
                        onChange={(event) => setBindingTarget(event.target.value)}
                      >
                        <option value="">新建成员会话</option>
                        {sessions.map((item) => (
                          <option key={item.session_id} value={item.session_id}>
                            {item.title} · {item.session_id.slice(0, 8)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      disabled={disabled || dirty || !state.space}
                      onClick={() => void act('bind')}
                    >
                      {bindingTarget ? '绑定所选会话' : '新建并绑定成员会话'}
                    </button>
                    <div className="space-history">
                      {(binding?.session_ids ?? [])
                        .filter((id) => id !== binding?.session_id)
                        .map((id) => (
                          <button key={id} onClick={() => openSession(id)}>
                            打开历史会话 ·{' '}
                            {sessions.find((item) => item.session_id === id)?.title ??
                              id.slice(0, 8)}
                          </button>
                        ))}
                    </div>
                  </details>
                </details>
              )}
              {relation && (
                <details className="space-editor" open key={relation.edge_id}>
                  <summary>关系配置</summary>
                  <button onClick={() => update((old) => ({ ...old, selectedEdge: null }))}>
                    关闭关系编辑
                  </button>
                  <fieldset disabled={disabled}>
                    <div className="space-fields">
                      {(['source_member_id', 'target_member_id'] as const).map((field) => (
                        <label key={field}>
                          {field === 'source_member_id' ? '关系来源' : '关系目标'}
                          <select
                            aria-label={field === 'source_member_id' ? '关系来源' : '关系目标'}
                            value={relation[field]}
                            onChange={(event) =>
                              editConfig((config) => ({
                                ...config,
                                edges: (config.edges ?? []).map((item) =>
                                  item.edge_id === relation.edge_id
                                    ? { ...item, [field]: event.target.value }
                                    : item
                                )
                              }))
                            }
                          >
                            {members.map((item) => (
                              <option key={item.member_id} value={item.member_id}>
                                {item.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      ))}
                    </div>
                    <label>
                      关系类型
                      <select
                        aria-label="关系类型"
                        value={relation.kind}
                        onChange={(event) => {
                          const kind: SpaceEdge['kind'] =
                            event.target.value === 'result'
                              ? 'result'
                              : event.target.value === 'discuss'
                                ? 'discuss'
                                : event.target.value === 'feedback'
                                  ? 'feedback'
                                  : 'delegate'
                          editConfig((config) => ({
                            ...config,
                            edges: (config.edges ?? []).map((item) =>
                              item.edge_id === relation.edge_id ? { ...item, kind } : item
                            )
                          }))
                        }}
                      >
                        {Object.entries(edgeLabels).map(([kind, label]) => (
                          <option key={kind} value={kind}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      关系说明
                      <input
                        aria-label="关系说明"
                        maxLength={4096}
                        value={relation.label ?? ''}
                        onChange={(event) =>
                          editConfig((config) => ({
                            ...config,
                            edges: (config.edges ?? []).map((item) =>
                              item.edge_id === relation.edge_id
                                ? { ...item, label: event.target.value }
                                : item
                            )
                          }))
                        }
                      />
                    </label>
                    <button
                      onClick={() =>
                        editConfig((config) => ({
                          ...config,
                          edges: (config.edges ?? []).filter(
                            (item) => item.edge_id !== relation.edge_id
                          )
                        }))
                      }
                    >
                      移除关系
                    </button>
                  </fieldset>
                </details>
              )}
            </div>
            {retired.length > 0 && (
              <details className="space-binding">
                <summary>已移除成员的保留会话</summary>
                {retired.map((item) => (
                  <div className="space-history" key={item.member_id}>
                    <span className="muted">成员 {item.member_id.slice(0, 8)}</span>
                    {(item.session_ids ?? []).map((id) => (
                      <button key={id} onClick={() => openSession(id)}>
                        打开历史会话 ·{' '}
                        {sessions.find((value) => value.session_id === id)?.title ?? id.slice(0, 8)}
                      </button>
                    ))}
                  </div>
                ))}
              </details>
            )}
          </>
        )}
        <div className="space-footer">
          <button disabled={disabled} onClick={() => void loadSpace(true)}>
            重新载入空间（放弃未保存编辑）
          </button>
          <button disabled={!connected || sessionBusy} onClick={() => void loadSessions()}>
            刷新会话状态
          </button>
          {sessionCursor && (
            <button
              disabled={!connected || sessionBusy}
              onClick={() => void loadSessions(sessionCursor)}
            >
              加载更多可绑定会话
            </button>
          )}
        </div>
        {sessionError && (
          <p role="alert" className="muted">
            {sessionError}
          </p>
        )}
      </div>
    </section>
  )
}
