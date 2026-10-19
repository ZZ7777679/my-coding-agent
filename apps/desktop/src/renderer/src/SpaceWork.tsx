/** 合作工作归属与结果，复用任务版本。 Collaboration ownership and results reuse task revisions. */
import { useEffect, useRef, useState } from 'react'
import type { SpaceView, TaskView, UpdateSpaceWorkParams } from '../../generated/protocol'

/** 明确更新工作承接，工作图不作为执行门槛。 Explicitly update work ownership without gating execution on the work graph. */
export function SpaceWork({ space, connected }: { space: SpaceView; connected: boolean }) {
  const [task, setTask] = useState<TaskView | null>(null)
  const [error, setError] = useState('')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const current = useRef(space.task_id)
  current.current = space.task_id
  useEffect(() => {
    let disposed = false
    const load = async () => {
      const result = await window.agent.getTask(space.task_id)
      if (!disposed && result.ok) setTask(result.data)
      else if (!disposed && !result.ok) setError(result.error.message)
    }
    void load()
    const unsubscribe = window.agent.onSessionEvent((event) => {
      if (
        event.kind === 'changed' &&
        (space.bindings ?? []).some((item) => item.session_id === event.session_id)
      )
        void load()
    })
    return () => {
      disposed = true
      unsubscribe()
    }
  }, [space.task_id, space.bindings, connected])
  const works = new Map((space.config.initial_work_items ?? []).map((item) => [item.work_id, item]))
  for (const { item } of task?.work?.items ?? []) works.set(item.work_id, item)
  /** 保存用户分配、领取或结果后显示宿主事实。 Persist user assignment, claim or result and show host facts. */
  const update = async (
    workId: string,
    member: string | null,
    action: UpdateSpaceWorkParams['action'],
    result?: string
  ) => {
    const taskId = space.task_id
    const response = await window.agent.updateSpaceWork({
      task_id: taskId,
      operation_id: crypto.randomUUID(),
      work_id: workId,
      member_id: member,
      action,
      result: result ?? null
    })
    if (current.current !== taskId) return
    if (response.ok) {
      setTask(response.data)
      setError('')
    } else setError(response.error.message)
  }
  return (
    <details className="space-work">
      <summary>协同工作 · {works.size} 项</summary>
      {error && <p role="alert">{error}</p>}
      {!works.size && (
        <p className="muted">草稿或成员报告中的工作项会显示在这里，无需填写即可执行。</p>
      )}
      {[...works.values()].map((item) => {
        const assignment = task?.work?.assignments?.find((value) => value.work_id === item.work_id)
        const owner = (assignment ? assignment.owner_member_id : item.owner_member_id) ?? ''
        return (
          <details key={item.work_id}>
            <summary>
              {item.title} · {item.status} · {assignment?.claim_status ?? '待分配'}
            </summary>
            <p>{item.scope}</p>
            <select
              aria-label={`${item.title}负责人`}
              value={owner}
              disabled={!connected}
              onChange={(event) =>
                void update(
                  item.work_id,
                  event.target.value || null,
                  event.target.value ? 'assign' : 'release'
                )
              }
            >
              <option value="">未分配</option>
              {(space.config.members ?? []).map((member) => (
                <option key={member.member_id} value={member.member_id}>
                  {member.name}
                </option>
              ))}
            </select>
            <button
              disabled={!connected || !owner}
              onClick={() => void update(item.work_id, owner, 'claim')}
            >
              标记领取
            </button>
            <button
              disabled={!connected}
              onClick={() => void update(item.work_id, null, 'release')}
            >
              释放
            </button>
            <textarea
              aria-label={`${item.title}结果`}
              value={drafts[item.work_id] ?? assignment?.result ?? item.result ?? ''}
              onChange={(event) =>
                setDrafts((previous) => ({ ...previous, [item.work_id]: event.target.value }))
              }
            />
            <button
              disabled={!connected || drafts[item.work_id] === undefined}
              onClick={() =>
                void update(item.work_id, owner || null, 'result', drafts[item.work_id])
              }
            >
              保存结果
            </button>
          </details>
        )
      })}
    </details>
  )
}
