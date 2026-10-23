import { useEffect, useRef, type ReactNode } from 'react'
import {
  BaseEdge,
  getSmoothStepPath,
  getViewportForBounds,
  getNodesBounds,
  useReactFlow,
  useStore,
  type Edge,
  type EdgeProps,
  type Node
} from '@xyflow/react'

/** 用固定卡片边界和实际画布尺寸适配新图；拖动和改字不重置视口。 Fit fixed card bounds to the actual canvas without resetting drags or text edits. */
export function FitTeamGraph({ request, nodes }: { request: number; nodes: Node[] }) {
  const { setViewport } = useReactFlow()
  const width = useStore((state) => state.width)
  const height = useStore((state) => state.height)
  const fitted = useRef('')
  useEffect(() => {
    const key = `${request}:${width}:${height}`
    if (!nodes.length || !request || !width || !height || fitted.current === key) return
    const frame = requestAnimationFrame(() => {
      fitted.current = key
      // 适配只改变视口，不通过库的节点更新队列回写受控业务配置。
      // Fit the viewport directly instead of routing through controlled node updates.
      const bounds = getNodesBounds(nodes)
      void setViewport(getViewportForBounds(bounds, width, height, 0.15, 1, 0.22))
    })
    return () => cancelAnimationFrame(frame)
  }, [nodes, request, width, height, setViewport])
  return null
}

export type TeamGraphEdge = Edge<{ lane: number; multiple: boolean; loopRadius: number }, 'team'>

/** 双向／并行关系分开走线，自环走卡片外侧；保留可点击路径和方向箭头。 Separate parallel/directional edges and route self-loops outside cards. */
export function TeamRelationEdge(props: EdgeProps<TeamGraphEdge>) {
  const { sourceX: sx, sourceY: sy, targetX: tx, targetY: ty } = props
  let [path, x, y] = getSmoothStepPath({ ...props, borderRadius: 16 })
  if (props.source === props.target || props.data?.multiple) {
    const loop = props.source === props.target
    const lane = props.data?.lane ?? 0
    const horizontal = Math.abs(tx - sx) >= Math.abs(ty - sy)
    // 偏移采用画布坐标，同一对成员的反向线也必须占不同侧。
    // Offset in canvas coordinates so reverse edges occupy different lanes too.
    const offset = lane
    const radius = props.data?.loopRadius ?? 110
    const c1 = loop
      ? [sx, sy - radius]
      : [
          sx + (tx - sx) * 0.45 + (horizontal ? 0 : offset),
          sy + (horizontal ? offset : (ty - sy) * 0.45)
        ]
    const c2 = loop
      ? [tx + radius, sy - radius]
      : [
          tx - (tx - sx) * 0.45 + (horizontal ? 0 : offset),
          ty + (horizontal ? offset : -(ty - sy) * 0.45)
        ]
    path = `M ${sx},${sy} C ${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${tx},${ty}`
    x = (sx + tx + 3 * (c1[0] + c2[0])) / 8
    y = (sy + ty + 3 * (c1[1] + c2[1])) / 8
  }
  return (
    <BaseEdge
      id={props.id}
      path={path}
      labelX={x}
      labelY={y}
      label={props.label}
      labelBgPadding={[7, 4]}
      labelBgBorderRadius={4}
      markerEnd={props.markerEnd}
      style={props.style}
      interactionWidth={24}
    />
  )
}

/** 固定侧面编辑区让关闭／删除始终可见，不改变图的滚动或缩放。 Keep close/delete visible in a bounded inspector without moving the graph viewport. */
export function SpaceInspector({
  title,
  closeLabel,
  onClose,
  actions,
  children
}: {
  title: string
  closeLabel: string
  onClose: () => void
  actions?: ReactNode
  children: ReactNode
}) {
  const close = useRef<HTMLButtonElement>(null)
  const callback = useRef(onClose)
  callback.current = onClose
  useEffect(() => {
    const previous = document.activeElement
    close.current?.focus({ preventScroll: true })
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !document.querySelector('dialog[open]')) callback.current()
    }
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('keydown', escape)
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus({ preventScroll: true })
    }
  }, [])
  return (
    <aside className="space-inspector" aria-label={title}>
      <header>
        <strong>{title}</strong>
        <div>
          {actions}
          <button ref={close} onClick={onClose}>
            {closeLabel}
          </button>
        </div>
      </header>
      <div className="space-inspector-content">{children}</div>
    </aside>
  )
}
