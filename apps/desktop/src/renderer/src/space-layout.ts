import type { SpaceConfig, SpaceMember } from '../../generated/protocol'

// 与成员卡片的 CSS 尺寸一致；间距仅影响展示，不限制成员数或执行。
// Match the node CSS bounds; spacing affects presentation, never team capacity.
export const MEMBER_WIDTH = 240
export const MEMBER_HEIGHT = 164
const COLUMN_STEP = 430
const ROW_STEP = 240

/** 检测卡片边界及阅读留白，不以坐标完全相等代替重叠判断。 Check card bounds and spacing, not only identical coordinates. */
function overlaps(a: SpaceMember, b: SpaceMember): boolean {
  return (
    Math.abs((a.position?.x ?? 0) - (b.position?.x ?? 0)) < MEMBER_WIDTH + 40 &&
    Math.abs((a.position?.y ?? 0) - (b.position?.y ?? 0)) < MEMBER_HEIGHT + 40
  )
}

/** 保留已有人工位置，仅安放新增节点或修复恢复数据中的重叠。 Preserve manual positions, placing additions and repairing restored overlaps. */
export function prepareMemberLayout(
  config: SpaceConfig,
  previous?: SpaceConfig | null
): SpaceConfig {
  const members = config.members ?? []
  const previousById = new Map(
    (previous?.members ?? []).map((member) => [member.member_id, member])
  )
  const suggested = new Map(arrangeMembers(config).map((member) => [member.member_id, member]))
  const placed: SpaceMember[] = []
  const pending: SpaceMember[] = []
  // 先保留旧节点，避免新成员占用已有手动位置。 Reserve existing nodes before placing additions.
  const ordered = [...members].sort(
    (a, b) => Number(previousById.has(b.member_id)) - Number(previousById.has(a.member_id))
  )
  for (const member of ordered) {
    const old = previousById.get(member.member_id)
    const candidate = { ...member, position: old?.position ?? member.position }
    if (
      (!previous || old) &&
      candidate.position &&
      !placed.some((item) => overlaps(candidate, item))
    )
      placed.push(candidate)
    else pending.push(member)
  }
  for (const member of pending) {
    const position = suggested.get(member.member_id)?.position
    const candidate = { ...member, position: { x: position?.x ?? 0, y: position?.y ?? 0 } }
    while (placed.some((item) => overlaps(candidate, item))) candidate.position.y += ROW_STEP
    placed.push(candidate)
  }
  const byId = new Map(placed.map((member) => [member.member_id, member]))
  return { ...config, members: members.map((member) => byId.get(member.member_id) ?? member) }
}

/** 按组织方式重新排布草稿，不改变成员身份、关系或执行状态。
 * Arrange draft members without changing identities, relations or execution state. */
export function arrangeMembers(config: SpaceConfig): SpaceMember[] {
  const members = config.members ?? []
  if (!members.length) return []
  const root = config.receiver_member_id ?? members[0].member_id
  const ordered = [...members].sort((a, b) =>
    a.member_id === root ? -1 : b.member_id === root ? 1 : 0
  )
  if (config.organisation === 'peer') {
    const radius = Math.max(COLUMN_STEP, (members.length * (MEMBER_WIDTH + 100)) / (2 * Math.PI))
    return ordered.map((member, index) => ({
      ...member,
      position: {
        x: radius + Math.cos((index * 2 * Math.PI) / members.length) * radius,
        y: radius + Math.sin((index * 2 * Math.PI) / members.length) * radius
      }
    }))
  }
  const levels = new Map<string, number>([[root, 0]])
  if (config.organisation === 'hierarchical') {
    // 只沿委派边计算首次可达层级，反馈环不阻止排布。
    // Use first-reached delegation levels; feedback cycles never block layout.
    const queue = [root]
    for (let index = 0; index < queue.length; index++) {
      const source = queue[index]
      for (const edge of config.edges ?? []) {
        if (
          edge.kind !== 'delegate' ||
          edge.source_member_id !== source ||
          levels.has(edge.target_member_id)
        )
          continue
        levels.set(edge.target_member_id, (levels.get(source) ?? 0) + 1)
        queue.push(edge.target_member_id)
      }
    }
  }
  const groups = new Map<number, SpaceMember[]>()
  for (const member of ordered) {
    const level = levels.get(member.member_id) ?? 1
    groups.set(level, [...(groups.get(level) ?? []), member])
  }
  const tallest = Math.max(...[...groups.values()].map((group) => group.length))
  return [...groups].flatMap(([level, group]) =>
    group.map((member, index) => ({
      ...member,
      position: { x: level * COLUMN_STEP, y: ((tallest - group.length) / 2 + index) * ROW_STEP }
    }))
  )
}
