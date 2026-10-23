import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  arrangeMembers,
  prepareMemberLayout,
  MEMBER_HEIGHT,
  MEMBER_WIDTH
} from '../../apps/desktop/src/renderer/src/space-layout.ts'

/** 布局检查使用卡片尺寸，覆盖非完全重合的旧数据。 Check actual card bounds, including partial overlaps. */
function assertSeparate(members) {
  for (let a = 0; a < members.length; a++)
    for (let b = a + 1; b < members.length; b++)
      assert.ok(
        Math.abs(members[a].position.x - members[b].position.x) >= MEMBER_WIDTH ||
          Math.abs(members[a].position.y - members[b].position.y) >= MEMBER_HEIGHT
      )
}

const members = Array.from({ length: 8 }, (_, i) => ({
  member_id: `m${i}`,
  name: `Member ${i}`,
  model_id: 'glm-5.3-flash',
  position: { x: i * 20, y: i * 10 }
}))
const config = {
  members,
  receiver_member_id: 'm0',
  edges: [
    { source_member_id: 'm0', target_member_id: 'm1', kind: 'delegate' },
    { source_member_id: 'm1', target_member_id: 'm0', kind: 'delegate' }
  ]
}

test('initial layouts are readable with feedback cycles, disconnected nodes and all organisations', () => {
  for (const organisation of ['central', 'hierarchical', 'peer'])
    assertSeparate(arrangeMembers({ ...config, organisation }))
})
test('restored partial overlaps are repaired, then reopening keeps the exact layout', () => {
  const restored = prepareMemberLayout(config)
  assertSeparate(restored.members)
  assert.deepEqual(prepareMemberLayout(restored), restored)
  assert.deepEqual(restored.edges, config.edges)
})
test('model edits preserve manual positions and new nodes avoid existing cards', () => {
  const previous = { ...config, members: arrangeMembers(config) }
  previous.members[0].position = { x: -1200, y: 400 }
  const incoming = {
    ...config,
    members: [
      ...members.map((m) => ({ ...m, name: `${m.name} renamed`, position: { x: 0, y: 0 } })),
      { ...members[0], member_id: 'new' }
    ]
  }
  const next = prepareMemberLayout(incoming, previous)
  assertSeparate(next.members)
  for (const old of previous.members)
    assert.deepEqual(next.members.find((m) => m.member_id === old.member_id).position, old.position)
  assert.equal(next.members[0].name, 'Member 0 renamed')
})
