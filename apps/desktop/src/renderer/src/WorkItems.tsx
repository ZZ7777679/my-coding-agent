import type { TaskView, WorkItem } from '../../generated/protocol'
import type { WorkspaceSelection } from './TaskNavigation'

const stateLabels: Record<WorkItem['status'], string> = {
  planned: '计划中',
  in_progress: '进行中',
  completed: '已完成',
  waiting: '等待'
}

type Props = {
  task: TaskView
  onSelect: (selection: WorkspaceSelection) => void
}

/** 展示有来源的工作报告与依赖，保留用户共同信息的优先级。 Show sourced work and dependencies while preserving user decisions. */
export function WorkItems({ task, onSelect }: Props) {
  const work = task.work
  if (!work || (!work.last_report && !work.items?.length)) return null
  const titles = new Map(work.items?.map(({ item }) => [item.work_id, item.title]))
  return (
    <section className="task-work" aria-label="工作报告与依赖">
      <h2>工作报告与依赖</h2>
      <p className="muted">以下为 Agent 根据记录给出的判断；你维护的共同信息优先。</p>
      {work.last_report && <p className="work-summary">{work.last_report.summary}</p>}
      {work.last_report?.question && (
        <p>
          待沟通：{work.last_report.question.question} · {work.last_report.question.impact}
        </p>
      )}
      {work.items?.map(({ item, source }) => (
        <details key={item.work_id}>
          <summary>
            {item.title} · {stateLabels[item.status]}
          </summary>
          <p>{item.scope}</p>
          {!!item.depends_on?.length && (
            <p>依赖：{item.depends_on.map((id) => titles.get(id) ?? id).join('、')}</p>
          )}
          <p className="muted">
            模型引用 {item.evidence?.length ?? 0} 条 · 反馈来源 {item.feedback_from?.length ?? 0} 条
          </p>
          <button
            className="text-button"
            title={`报告来自此会话的记录 #${source.seq}`}
            onClick={() =>
              onSelect({
                projectId: task.project_id,
                taskId: task.task_id,
                sessionId: source.session_id
              })
            }
          >
            打开来源会话
          </button>
        </details>
      ))}
    </section>
  )
}
