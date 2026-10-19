/** 工作图关联任务定义和真实执行。 Task work graphs connect definitions with real execution. */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
  type Edge,
  type NodeChange,
  type EdgeChange,
  type Connection
} from '@xyflow/react'
import type { GoalView, SpaceView, WorkGraphView, WorkItem } from '../../generated/protocol'
import './WorkGraphPanel.css'
import { mergeSpaceSnapshot } from './space-stream'

type Props = {
  active: boolean
  space: SpaceView
  connected: boolean
  onSelectSession: (id: string) => void
  onChanged: () => void
}
const statusLabels = {
  planned: '待开展',
  in_progress: '进行中',
  completed: '已报告完成',
  waiting: '等待'
}
const methods: Record<NonNullable<WorkItem['method']>, string> = {
  discuss: '讨论',
  plan: '规划',
  implement: '实现',
  diagnose: '验证 / 调试',
  review: '审查',
  handoff: '交接'
}

type WorkNode = Node<{ label: ReactNode }, 'work'>
/** 四侧端口让反馈线绕开节点正文。 Side handles route feedback around node content. */
function WorkNodeView({ data }: NodeProps<WorkNode>) {
  return (
    <>
      {[Position.Left, Position.Right, Position.Top, Position.Bottom].map((side) => (
        <span key={side}>
          <Handle
            type="source"
            id={`source-${side}`}
            position={side}
            title="关系起点"
            style={
              side === Position.Left || side === Position.Right ? { top: '35%' } : { left: '35%' }
            }
          />
          <Handle
            type="target"
            id={`target-${side}`}
            position={side}
            title="关系终点"
            style={
              side === Position.Left || side === Position.Right ? { top: '65%' } : { left: '65%' }
            }
          />
        </span>
      ))}
      {data.label}
    </>
  )
}
const workNodeTypes = { work: WorkNodeView }

/** 异步刷新保留用户草稿，节点历史读取既有空间事件。 Refresh facts without replacing drafts or duplicating logs. */
export function WorkGraphPanel({ active, space, connected, onSelectSession, onChanged }: Props) {
  const [view, setView] = useState<WorkGraphView | null>(null)
  const [draft, setDraft] = useState<WorkItem[] | null>(null)
  const [revision, setRevision] = useState<number | null>(null)
  const [selected, setSelected] = useState('')
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null)
  const [ownerChanges, setOwnerChanges] = useState<Record<string, string | null>>({})
  const [connectionKind, setConnectionKind] = useState<'depends_on' | 'feedback_to'>('depends_on')
  const [chosen, setChosen] = useState<string[]>([])
  const [receiver, setReceiver] = useState(space.config.receiver_member_id ?? '')
  const [instruction, setInstruction] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [resultText, setResultText] = useState('')
  const [resultStatus, setResultStatus] = useState<WorkItem['status']>('planned')
  const epoch = useRef(0)
  const alive = useRef(true)
  const action = useRef(false)
  const canvas = useRef<HTMLDivElement>(null)
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 })
  const [flow, setFlow] = useState<ReactFlowInstance<WorkNode, Edge> | null>(null)
  const members = space.config.members ?? []
  const stages = view?.task.workflow?.template.stages ?? []
  const items = draft ?? view?.items ?? []
  const item = items.find((entry) => entry.work_id === selected)
  const columns = Math.max(1, Math.min(3, Math.floor(canvasSize.width / 270)))

  // 容器变化只调整显示，不改工作顺序、依赖或运行状态。
  // Container changes affect layout only, never work order, dependencies or execution.
  useEffect(() => {
    if (!canvas.current || !active) return
    const observer = new ResizeObserver(([entry]) => {
      setCanvasSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    observer.observe(canvas.current)
    return () => observer.disconnect()
  }, [active, !!items.length])
  useEffect(() => {
    if (!flow || !active) return
    const frame = requestAnimationFrame(() => {
      void flow.fitView({ padding: 0.12, maxZoom: 1 })
    })
    return () => cancelAnimationFrame(frame)
  }, [flow, active, columns, canvasSize, items.length])

  /** 最新刷新才能替换后端投影，任务卸载后丢弃。 Only the newest refresh may update the mounted projection. */
  const refresh = useCallback(async () => {
    const current = ++epoch.current
    const response = await window.agent.getWorkGraph({ task_id: space.task_id })
    if (!alive.current || current !== epoch.current) return
    if (response.ok) {
      setView((previous) => ({
        ...response.data,
        activity: mergeSpaceSnapshot(previous?.activity ?? null, response.data.activity)
      }))
      setError('')
    } else setError(response.error.message)
  }, [space.task_id])

  /** 按需读取旧执行页，复用群聊来源且保留已加载记录。 Load older execution pages from shared chat records. */
  async function loadOlder(): Promise<void> {
    if (!view?.activity.next_before || busy) return
    setBusy(true)
    try {
      const response = await window.agent.getSpaceChat({
        task_id: space.task_id,
        before_id: view.activity.next_before
      })
      if (!alive.current) return
      if (response.ok)
        setView((current) =>
          current
            ? { ...current, activity: mergeSpaceSnapshot(current.activity, response.data, true) }
            : current
        )
      else setError(response.error.message)
    } catch {
      if (alive.current) setError('执行历史读取失败，请重试。')
    } finally {
      if (alive.current) setBusy(false)
    }
  }
  useEffect(() => {
    alive.current = true
    void refresh()
    const unsubscribe = window.agent.onSessionEvent((event) => {
      if (
        event.kind === 'changed' &&
        (space.bindings ?? []).some((b) => b.session_id === event.session_id)
      )
        void refresh()
    })
    return () => {
      alive.current = false
      epoch.current++
      unsubscribe()
    }
  }, [refresh, space.bindings, connected])
  useEffect(() => {
    setResultText(item?.result ?? '')
    setResultStatus(item?.status ?? 'planned')
  }, [selected, item?.result, item?.status])

  /** 首次编辑固定基础修订，后台进度刷新不悄悄重置版本。 Capture a draft revision before editing. */
  const edit = (next: WorkItem[]) => {
    if (draft === null) setRevision(view?.task.revision ?? null)
    setDraft(next)
  }
  /** 修改选中节点而不改其他任务或模板。 Update only the selected task node. */
  const change = (fields: Partial<WorkItem>) => {
    if ('owner_member_id' in fields)
      setOwnerChanges((old) => ({ ...old, [selected]: fields.owner_member_id ?? null }))
    edit(items.map((entry) => (entry.work_id === selected ? { ...entry, ...fields } : entry)))
  }
  /** 删除当前图节点及其连线，历史由后端保留。 Remove current nodes and edges while preserving history. */
  const removeNodes = (ids: Set<string>) => {
    edit(
      items
        .filter((work) => !ids.has(work.work_id))
        .map((work) => ({
          ...work,
          depends_on: work.depends_on?.filter((id) => !ids.has(id)),
          feedback_to: work.feedback_to?.filter((id) => !ids.has(id))
        }))
    )
    setChosen((old) => old.filter((id) => !ids.has(id)))
    setOwnerChanges((old) => Object.fromEntries(Object.entries(old).filter(([id]) => !ids.has(id))))
    if (ids.has(selected)) setSelected('')
  }
  /** 图位置属于用户草稿，测量事件不写业务数据。 Keep positions in drafts and ignore measurements. */
  const changeNodes = (changes: NodeChange[]) => {
    const selection = changes.find((change) => change.type === 'select' && change.selected)
    if (selection?.type === 'select') {
      setSelected(selection.id)
      setSelectedEdge(null)
    }
    const removed = new Set(changes.filter((c) => c.type === 'remove').map((c) => c.id))
    if (removed.size) return removeNodes(removed)
    const positions = changes.filter((c) => c.type === 'position').filter((c) => c.position)
    if (positions.length)
      edit(
        items.map((work) => {
          const position = positions.find((c) => c.id === work.work_id)?.position
          // 首次拖动同时固定其余节点，避免侧栏变宽后自动位置与手动位置重叠。
          // Freeze the visible layout on drag so resizing cannot mix automatic and saved positions.
          return {
            ...work,
            position: position ?? nodes.find((node) => node.id === work.work_id)?.position
          }
        })
      )
  }
  /** 连线类型明确选择，依赖箭头从前置工作指向后续工作。 Choose edge semantics explicitly. */
  const connect = ({ source, target }: Connection) => {
    if (!source || !target) return
    const id = connectionKind === 'depends_on' ? target : source
    const reference = connectionKind === 'depends_on' ? source : target
    edit(
      items.map((work) =>
        work.work_id === id
          ? {
              ...work,
              [connectionKind]: [...new Set([...(work[connectionKind] ?? []), reference])]
            }
          : work
      )
    )
  }
  /** 删除所选关系直接更新草稿，允许反馈环。 Remove selected relations while retaining feedback cycles. */
  const changeEdges = (changes: EdgeChange[]) => {
    const selection = changes.find((change) => change.type === 'select' && change.selected)
    if (selection?.type === 'select') {
      setSelectedEdge(selection.id)
      setSelected('')
    }
    const removed = new Set(changes.filter((c) => c.type === 'remove').map((c) => c.id))
    if (!removed.size) return
    if (selectedEdge && removed.has(selectedEdge)) setSelectedEdge(null)
    edit(
      items.map((work) => ({
        ...work,
        depends_on: work.depends_on?.filter(
          (id) => !removed.has(`dependency:${id}:${work.work_id}`)
        ),
        feedback_to: work.feedback_to?.filter(
          (id) => !removed.has(`feedback:${work.work_id}:${id}`)
        )
      }))
    )
  }
  /** 保存图定义；真实结果仍留在独立进度中。 Save definitions while retaining independent progress. */
  const save = async () => {
    if (!draft || revision === null || action.current) return
    action.current = true
    setBusy(true)
    try {
      const response = await window.agent.saveWorkGraph({
        task_id: space.task_id,
        operation_id: crypto.randomUUID(),
        expected_revision: revision,
        items: draft,
        owner_changes: ownerChanges
      })
      if (!alive.current) return
      if (response.ok) {
        epoch.current++
        setView(response.data)
        setDraft(null)
        setOwnerChanges({})
        setNotice('工作图已保存到当前任务。')
        onChanged()
      } else setError(response.error.message)
    } finally {
      action.current = false
      if (alive.current) setBusy(false)
    }
  }
  /** 明确选择单次或持续执行，同一按钮操作只提交一次。 Start selected work once in the chosen execution mode. */
  const start = async (continuous: boolean) => {
    const [first, ...remaining] = chosen
    if (action.current || !first) return
    action.current = true
    setBusy(true)
    setError('')
    try {
      const response = await window.agent.startWorkGraph({
        task_id: space.task_id,
        operation_id: crypto.randomUUID(),
        work_ids: [first, ...remaining],
        member_id: receiver,
        continuous,
        instruction
      })
      if (!alive.current) return
      if (response.ok) {
        const record = continuous ? response.data.rounds?.at(-1) : response.data.messages?.at(-1)
        const failure = record?.executions?.find((execution) => execution.error)?.error
        await refresh()
        if (failure) setError(failure)
        else setNotice(continuous ? '已开始持续推进所选工作。' : '已发送本次工作请求。')
        onChanged()
      } else setError(response.error.message)
    } finally {
      action.current = false
      if (alive.current) setBusy(false)
    }
  }
  /** 保存负责人或结果，失败保留输入。 Save ownership or progress without discarding failed input. */
  const update = async (owner: string | null, result?: string) => {
    if (!item || action.current) return
    action.current = true
    setBusy(true)
    try {
      const response = await window.agent.updateSpaceWork({
        task_id: space.task_id,
        operation_id: crypto.randomUUID(),
        work_id: item.work_id,
        member_id: owner,
        action: result === undefined ? (owner ? 'assign' : 'release') : 'result',
        result: result ?? null,
        status: result === undefined ? null : resultStatus
      })
      if (!alive.current) return
      if (response.ok) {
        await refresh()
        onChanged()
      } else setError(response.error.message)
    } finally {
      action.current = false
      if (alive.current) setBusy(false)
    }
  }
  /** 控制已有轮次，恢复保持原范围。 Control an existing round while retaining its original scope. */
  const control = async (goal: GoalView, actionName: 'resume' | 'cancel') => {
    if (action.current) return
    action.current = true
    setBusy(true)
    try {
      const response = await window.agent.controlGoal({
        session_id: goal.session_id,
        goal_id: goal.goal_id,
        expected_revision: goal.revision,
        operation_id: crypto.randomUUID(),
        action: actionName
      })
      if (!alive.current) return
      if (response.ok) {
        await refresh()
        onChanged()
      } else setError(response.error.message)
    } finally {
      action.current = false
      if (alive.current) setBusy(false)
    }
  }
  const attempts = [
    ...(view?.activity.messages ?? []).map((message) => ({
      id: message.message_id,
      ids: message.work_ids ?? [],
      time: message.created_at,
      executions: message.executions ?? [],
      continuous: false
    })),
    ...(view?.activity.rounds ?? []).map((round) => ({
      id: round.round_id,
      ids: round.work_ids ?? [],
      time: round.created_at,
      executions: round.executions ?? [],
      continuous: true
    }))
  ].sort((a, b) => a.time.localeCompare(b.time))
  const { nodes, edges } = useMemo(() => {
    const ordered = [...items].sort(
      (a, b) =>
        stages.findIndex((stage) => stage.stage_id === a.stage_id) -
        stages.findIndex((stage) => stage.stage_id === b.stage_id)
    )
    const nodes: WorkNode[] = ordered.map((work, index) => {
      const row = Math.floor(index / columns)
      const column = row % 2 ? columns - 1 - (index % columns) : index % columns
      const owner = members.find((member) => member.member_id === work.owner_member_id)
      const attempt = [...attempts].reverse().find((entry) => entry.ids.includes(work.work_id))
      const output = [...(view?.activity.outputs ?? [])]
        .reverse()
        .find((entry) => entry.origin_id === attempt?.id)
      return {
        id: work.work_id,
        type: 'work',
        position: work.position ?? { x: column * 310, y: row * 180 },
        selected: selected === work.work_id,
        className: `work-node work-node-${work.status}`,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          label: (
            <>
              <strong>{work.title}</strong>
              <span>
                {owner?.name ?? '待分配'} · {statusLabels[work.status]}
              </span>
              <small>
                {stages.find((s) => s.stage_id === work.stage_id)?.name ??
                  methods[work.method ?? 'implement']}
              </small>
              {output && <small>关联执行：{output.waiting_for ? '等待协作' : output.status}</small>}
            </>
          )
        }
      }
    })
    const positions = new Map(nodes.map((node) => [node.id, node.position]))
    /** 根据实际相对位置选择出入口，反馈使用另一条通道。 Route edges by relative node positions. */
    const ports = (source: string, target: string, feedback = false) => {
      const from = positions.get(source)!
      const to = positions.get(target)!
      const horizontal = Math.abs(to.x - from.x) > Math.abs(to.y - from.y)
      const side = horizontal
        ? to.x > from.x
          ? 'right'
          : 'left'
        : to.y > from.y
          ? 'bottom'
          : 'top'
      const opposite = { right: 'left', left: 'right', bottom: 'top', top: 'bottom' }
      return {
        sourceHandle: `source-${feedback ? (horizontal ? 'bottom' : 'right') : side}`,
        targetHandle: `target-${feedback ? (horizontal ? 'bottom' : 'right') : opposite[side]}`
      }
    }
    const known = new Set(items.map((work) => work.work_id))
    const edges: Edge[] = items.flatMap((work) => [
      ...(work.depends_on ?? [])
        .filter((id) => known.has(id))
        .map((id) => ({
          id: `dependency:${id}:${work.work_id}`,
          source: id,
          target: work.work_id,
          ...ports(id, work.work_id),
          type: 'smoothstep',
          label: '依赖',
          markerEnd: { type: MarkerType.ArrowClosed }
        })),
      ...(work.feedback_to ?? [])
        .filter((id) => known.has(id))
        .map((id) => ({
          id: `feedback:${work.work_id}:${id}`,
          source: work.work_id,
          target: id,
          ...ports(work.work_id, id, true),
          type: 'smoothstep',
          label: '反馈',
          style: { strokeDasharray: '5 4', stroke: '#c0a76b' },
          markerEnd: { type: MarkerType.ArrowClosed }
        }))
    ])
    return { nodes, edges: edges.map((edge) => ({ ...edge, selected: edge.id === selectedEdge })) }
  }, [items, stages, members, selected, selectedEdge, view?.activity, columns])
  const disabled = !connected || busy
  return (
    <section className="work-graph-panel" aria-label="任务工作图">
      <div className="work-graph-toolbar">
        <strong>
          {view?.task.workflow?.template.name ?? '自定义工作图'} · {items.length} 项
        </strong>
        <button
          disabled={disabled || !view?.suggested_items.length}
          onClick={() => {
            const known = new Set(items.map((work) => work.work_id))
            edit([
              ...items,
              ...(view?.suggested_items ?? []).filter((work) => !known.has(work.work_id))
            ])
            setNotice('流程骨架已加入草稿，可修改范围与分工；保存不会开始执行。')
          }}
        >
          从流程补充骨架
        </button>
        <button
          disabled={disabled || !view}
          onClick={() => {
            const id = `work-${crypto.randomUUID()}`
            edit([
              ...items,
              {
                work_id: id,
                title: '新工作',
                scope: '描述本次工作范围',
                status: 'planned',
                stage_id: stages[0]?.stage_id ?? null,
                position: { x: 0, y: Math.max(-180, ...nodes.map((node) => node.position.y)) + 180 }
              }
            ])
            setSelected(id)
          }}
        >
          添加工作
        </button>
        <button disabled={disabled || !draft} onClick={() => void save()}>
          保存工作图
        </button>
        <button
          disabled={disabled || !items.length}
          onClick={() => {
            edit(
              items.map((work, index) => ({
                ...work,
                position: {
                  x: (index % columns) * 310,
                  y: Math.floor(index / columns) * 180
                }
              }))
            )
          }}
        >
          自动排布
        </button>
        <button
          disabled={disabled || !selectedEdge}
          onClick={() => {
            if (selectedEdge) changeEdges([{ type: 'remove', id: selectedEdge }])
          }}
        >
          删除选中关系
        </button>
        <button
          disabled={disabled}
          onClick={() => {
            setDraft(null)
            setOwnerChanges({})
            setRevision(null)
            void refresh()
          }}
        >
          刷新 / 放弃草稿
        </button>
      </div>
      <p className="muted">
        工作图属于当前任务；阶段是分组，节点是完整工作。选择节点查看分工与历史，执行范围在下方选择。
        可让协调成员持续推进，其他成员承接单次委派；各成员未结束的 Goal 不会被新委派替换。
      </p>
      <label>
        拖动连线类型
        <select
          aria-label="拖动连线类型"
          value={connectionKind}
          onChange={(e) =>
            setConnectionKind(e.target.value === 'feedback_to' ? 'feedback_to' : 'depends_on')
          }
        >
          <option value="depends_on">依赖：前置 → 后续</option>
          <option value="feedback_to">反馈：当前 → 返回</option>
        </select>
      </label>
      <p className="muted">
        可拖动节点、连接端口；选中关系按 Delete 删除。修改与分工统一保存，删除节点保留历史。
      </p>
      {error && <p role="alert">{error}</p>}
      {view?.issues?.map((issue) => (
        <p role="alert" key={issue}>
          {issue}
        </p>
      ))}
      {notice && <p role="status">{notice}</p>}
      {!view && !error && <p>正在读取工作图…</p>}
      <div className="work-graph-layout">
        <div>
          {active && !!items.length && (
            <div className="work-graph-canvas" ref={canvas}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={workNodeTypes}
                onInit={setFlow}
                fitViewOptions={{ padding: 0.12, maxZoom: 1 }}
                fitView
                nodesDraggable={!disabled}
                nodesConnectable={!disabled}
                onNodesChange={changeNodes}
                onEdgesChange={changeEdges}
                onConnect={connect}
                deleteKeyCode={disabled ? null : 'Delete'}
                onNodeClick={(_, node) => {
                  setSelected(node.id)
                  setSelectedEdge(null)
                }}
                onEdgeClick={(_, edge) => {
                  setSelectedEdge(edge.id)
                  setSelected('')
                }}
              >
                <Background />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          )}
          {!items.length && view && (
            <p>尚无工作项。可从已选流程生成骨架，或自行添加；普通会话照常使用。</p>
          )}
          {!!view?.goals?.length && (
            <details>
              <summary>持续执行轮次 · {view.goals.length}</summary>
              {view.goals.map((goal) => (
                <div className="work-attempt" key={goal.goal_id}>
                  <span>
                    {members.find((member) =>
                      (space.bindings ?? []).some(
                        (binding) =>
                          binding.member_id === member.member_id &&
                          binding.session_id === goal.session_id
                      )
                    )?.name ?? '成员'}{' '}
                    · {goal.status}
                    {goal.code ? ` · ${goal.code}` : ''}
                  </span>
                  <button onClick={() => onSelectSession(goal.session_id)}>查看会话与问题</button>
                  {['paused', 'failed', 'budget_exceeded', 'interrupted'].includes(goal.status) && (
                    <button disabled={disabled} onClick={() => void control(goal, 'resume')}>
                      继续本轮
                    </button>
                  )}
                  {!['completed', 'cancelled'].includes(goal.status) && (
                    <button disabled={disabled} onClick={() => void control(goal, 'cancel')}>
                      取消本轮
                    </button>
                  )}
                </div>
              ))}
            </details>
          )}
        </div>
        {item && (
          <details open className="work-graph-node-details">
            <summary>节点 · {item.title}</summary>
            <div className="work-graph-toolbar">
              <button onClick={() => setSelected('')}>关闭节点编辑</button>
              <button disabled={disabled} onClick={() => removeNodes(new Set([item.work_id]))}>
                删除节点
              </button>
            </div>
            <div className="work-graph-fields">
              <label>
                标题
                <input
                  aria-label="标题"
                  value={item.title}
                  onChange={(e) => change({ title: e.target.value })}
                />
              </label>
              <label>
                所属阶段
                <select
                  aria-label="所属阶段"
                  value={item.stage_id ?? ''}
                  onChange={(e) => change({ stage_id: e.target.value || null })}
                >
                  <option value="">不指定</option>
                  {stages.map((stage) => (
                    <option key={stage.stage_id} value={stage.stage_id}>
                      {stage.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                方法
                <select
                  aria-label="方法"
                  value={item.method ?? 'implement'}
                  onChange={(e) => {
                    const method = Object.keys(methods).find(
                      (key) => key === e.target.value
                    ) as WorkItem['method']
                    change({ method })
                  }}
                >
                  {Object.entries(methods).map(([key, value]) => (
                    <option key={key} value={key}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                负责人
                <select
                  aria-label="负责人"
                  value={item.owner_member_id ?? ''}
                  disabled={disabled}
                  onChange={(e) => change({ owner_member_id: e.target.value || null })}
                >
                  <option value="">未分配</option>
                  {members.map((member) => (
                    <option key={member.member_id} value={member.member_id}>
                      {member.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              工作范围
              <textarea
                aria-label="工作范围"
                value={item.scope}
                onChange={(e) => change({ scope: e.target.value })}
              />
            </label>
            <div className="work-graph-fields">
              {(['depends_on', 'feedback_to'] as const).map((field) => (
                <details key={field}>
                  <summary>
                    {field === 'depends_on' ? '依赖的工作' : '反馈可返回的工作'} ·{' '}
                    {item[field]?.length ?? 0}
                  </summary>
                  {items
                    .filter((other) => other.work_id !== item.work_id || field === 'feedback_to')
                    .map((other) => (
                      <label className="work-check" key={other.work_id}>
                        <input
                          type="checkbox"
                          checked={(item[field] ?? []).includes(other.work_id)}
                          onChange={(e) =>
                            change({
                              [field]: e.target.checked
                                ? [...(item[field] ?? []), other.work_id]
                                : (item[field] ?? []).filter((id) => id !== other.work_id)
                            })
                          }
                        />
                        {other.title}
                      </label>
                    ))}
                </details>
              ))}
            </div>
            <details>
              <summary>结果与反馈</summary>
              <select
                aria-label="工作状态"
                value={resultStatus}
                disabled={disabled || !!draft}
                onChange={(e) => setResultStatus(e.target.value as WorkItem['status'])}
              >
                {Object.entries(statusLabels).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
              <textarea
                aria-label="工作结果与反馈"
                value={resultText}
                onChange={(e) => setResultText(e.target.value)}
              />
              <button
                disabled={disabled || !!draft}
                onClick={() => void update(item.owner_member_id ?? null, resultText)}
              >
                保存结果与状态
              </button>
            </details>
            <details>
              <summary>
                执行记录 · {attempts.filter((attempt) => attempt.ids.includes(item.work_id)).length}{' '}
                次{view?.activity.next_before ? '（还有旧记录）' : ''}
              </summary>
              {view?.activity.next_before && (
                <button disabled={busy} onClick={() => void loadOlder()}>
                  加载更早执行记录
                </button>
              )}
              {attempts
                .filter((attempt) => attempt.ids.includes(item.work_id))
                .map((attempt) => (
                  <article className="work-attempt" key={attempt.id}>
                    <span>
                      {new Date(attempt.time).toLocaleString()} ·{' '}
                      {attempt.continuous ? '持续推进' : '单次请求'}
                    </span>
                    {attempt.executions.map((execution) => (
                      <div key={execution.operation_id}>
                        <button onClick={() => onSelectSession(execution.session_id)}>
                          查看会话与 Trace
                        </button>
                        {execution.error && <p role="alert">{execution.error}</p>}
                      </div>
                    ))}
                    {(view?.activity.outputs ?? [])
                      .filter((output) => output.origin_id === attempt.id)
                      .map((output, index) => (
                        <details key={`${output.run_id}-${index}`}>
                          <summary>
                            {members.find((member) => member.member_id === output.member_id)
                              ?.name ?? '成员'}{' '}
                            · {output.status}
                            {output.waiting_for ? ' · 等待协作' : ''}
                          </summary>
                          <p>{output.text || output.error || '尚无正文'}</p>
                        </details>
                      ))}
                  </article>
                ))}
            </details>
          </details>
        )}
      </div>
      {!!items.length && (
        <details className="work-graph-execution" open>
          <summary>执行工作</summary>
          <div className="work-graph-selection">
            {items.map((work) => (
              <label className="work-check" key={work.work_id}>
                <input
                  type="checkbox"
                  checked={chosen.includes(work.work_id)}
                  onChange={(e) =>
                    setChosen((old) =>
                      e.target.checked
                        ? [...old, work.work_id]
                        : old.filter((id) => id !== work.work_id)
                    )
                  }
                />
                {work.title}
              </label>
            ))}
          </div>
          <label>
            执行 / 协调成员
            <select
              aria-label="执行 / 协调成员"
              value={receiver}
              onChange={(e) => setReceiver(e.target.value)}
            >
              <option value="">选择已有成员</option>
              {members.map((member) => (
                <option key={member.member_id} value={member.member_id}>
                  {member.name}
                </option>
              ))}
            </select>
          </label>
          <textarea
            aria-label="本次执行说明"
            placeholder="补充本次目标，例如：完成所选实现；发现问题时一并修复。"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />
          <div className="work-graph-toolbar">
            <button
              disabled={disabled || !!draft || !chosen.length || !receiver}
              onClick={() => void start(false)}
            >
              执行一次
            </button>
            <button
              disabled={disabled || !!draft || !chosen.length || !receiver}
              onClick={() => void start(true)}
            >
              持续推进所选工作
            </button>
            <button
              disabled={disabled || !receiver}
              onClick={async () => {
                const response = await window.agent.stopSpaceRound({
                  task_id: space.task_id,
                  member_id: receiver || null
                })
                if (!alive.current) return
                if (!response.ok) setError(response.error.message)
                else void refresh()
              }}
            >
              停止所选成员
            </button>
          </div>
          <p className="muted">
            使用已绑定会话；不自动组建成员。依赖和反馈供 Agent
            安排工作，未选节点不会自动取得执行授权。
          </p>
        </details>
      )}
    </section>
  )
}
