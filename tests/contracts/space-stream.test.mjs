import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  applySpaceDelta,
  mergeSpaceSnapshot
} from '../../apps/desktop/src/renderer/src/space-stream.ts'

test('older pages retain a stable cursor on refresh even with equal timestamps', () => {
  const latest = {
    task_id: 'task',
    messages: [{ message_id: 'b', created_at: 'same' }],
    rounds: [],
    outputs: [],
    next_before: 'b'
  }
  const older = {
    ...latest,
    messages: [{ message_id: 'a', created_at: 'same' }],
    next_before: null
  }
  const expanded = mergeSpaceSnapshot(latest, older, true)
  const refreshed = mergeSpaceSnapshot(expanded, latest)
  assert.equal(refreshed.next_before, null)
  assert.deepEqual(new Set(refreshed.messages.map((m) => m.message_id)), new Set(['a', 'b']))
})

test('space snapshots and late deltas preserve exact streamed text across message boundaries', () => {
  const snapshot = {
    task_id: 'task',
    outputs: [
      {
        session_id: 'session',
        member_id: 'member',
        run_id: 'run',
        message_id: 'first',
        process_epoch: 'epoch',
        delta_index: 2,
        text: 'Hello',
        streaming: true,
        status: 'running'
      }
    ]
  }
  const signal = {
    session_id: 'session',
    run_id: 'run',
    message_id: 'first',
    process_epoch: 'epoch',
    delta_index: 2,
    kind: 'text.delta',
    text: 'lo',
    seq: 1
  }
  assert.equal(applySpaceDelta(snapshot, signal).view.outputs[0].text, 'Hello')
  const reason = applySpaceDelta(snapshot, {
    ...signal,
    delta_index: 3,
    kind: 'reasoning.delta',
    text: 'private'
  })
  const next = applySpaceDelta(reason.view, { ...signal, delta_index: 4, text: ' world' })
  assert.equal(next.view.outputs[0].text, 'Hello world')
  assert.equal(mergeSpaceSnapshot(next.view, snapshot).outputs[0].text, 'Hello world')
  const waiting = mergeSpaceSnapshot(next.view, {
    ...snapshot,
    outputs: [{ ...snapshot.outputs[0], origin_id: 'question', waiting_for: 'reviewer' }]
  })
  assert.equal(waiting.outputs[0].text, 'Hello world')
  assert.equal(waiting.outputs[0].waiting_for, 'reviewer')
  assert.equal(waiting.outputs[0].origin_id, 'question')
  assert.equal(applySpaceDelta(next.view, { ...signal, delta_index: 6 }).resync, true)
  assert.equal(
    applySpaceDelta(next.view, { ...signal, message_id: 'second', delta_index: 1 }).resync,
    true
  )
  assert.equal(
    applySpaceDelta(next.view, { ...signal, process_epoch: 'restart', delta_index: 1 }).resync,
    true
  )
  const committed = mergeSpaceSnapshot(next.view, {
    ...snapshot,
    outputs: [{ ...snapshot.outputs[0], text: 'Hello world!', streaming: false }]
  })
  assert.equal(
    applySpaceDelta(committed, { ...signal, delta_index: 5, text: '!' }).view.outputs[0].text,
    'Hello world!'
  )
})
