import type { SpaceConfig, SpaceMember } from '../../generated/protocol'

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
    const radius = Math.max(220, members.length * 48)
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
      position: { x: level * 360, y: ((tallest - group.length) / 2 + index) * 194 }
    }))
  )
}
