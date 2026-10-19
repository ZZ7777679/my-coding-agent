"""把流程骨架和任务工作接入既有团队执行。

Connect workflow skeletons to existing team execution.
"""

import asyncio
import json
from typing import TYPE_CHECKING
from uuid import UUID, uuid5

from my_agent.errors import AgentError
from my_agent.goals.types import GoalView
from my_agent.spaces.team_types import SpaceChatParams, SpaceChatView, StartSpaceRoundParams
from my_agent.spaces.types import SpaceParams, SpaceView
from my_agent.spaces.work_types import SaveWorkGraphParams, StartWorkGraphParams, WorkGraphView
from my_agent.tasks.types import TaskView
from my_agent.workflow.scheduling import execution_mode
from my_agent.workflow.types import WorkItem

if TYPE_CHECKING:
    from my_agent.spaces.team_service import SpaceTeamService


def work_items(task: TaskView, space: SpaceView) -> list[WorkItem]:
    """用户定义优先，运行报告只更新其进度。

    Preserve user definitions while applying reported progress.
    """
    definitions = {item.work_id: item for item in space.config.initial_work_items}
    definitions.update((item.work_id, item) for item in task.work.planned_items)
    reports = {entry.item.work_id: entry for entry in task.work.items}
    merged = {**{key: value.item for key, value in reports.items()}, **definitions}
    for identity, item in list(merged.items()):
        report = reports.get(identity)
        if report and identity in definitions:
            item = item.model_copy(
                update={
                    "status": report.item.status,
                    "result": report.item.result,
                    "run_id": report.source.run_id,
                }
            )
        assignment = next((a for a in task.work.assignments if a.work_id == identity), None)
        if assignment:
            updates: dict[str, object] = {
                "owner_member_id": assignment.owner_member_id,
                "claim_status": assignment.claim_status,
            }
            progress_at = assignment.progress_updated_at or assignment.updated_at
            if report is None or not report.updated_at or progress_at > report.updated_at:
                if assignment.status is not None:
                    updates["status"] = assignment.status
                if assignment.result is not None:
                    updates["result"] = assignment.result
                if assignment.run_id is not None:
                    updates["run_id"] = assignment.run_id
            item = item.model_copy(update=updates)
        merged[identity] = item
    return [item for key, item in merged.items() if key not in task.work.removed_work_ids]


def workflow_skeleton(task: TaskView) -> list[WorkItem]:
    """从任务快照预览骨架，不写项目或启动会话。

    Preview the task snapshot without side effects.
    """
    if task.workflow is None:
        return []
    stages = task.workflow.template.stages
    ids = {
        stage.stage_id: "stage-" + str(uuid5(UUID(task.task_id), stage.stage_id))
        for stage in stages
    }
    return [
        WorkItem(
            work_id=ids[stage.stage_id],
            title=stage.name,
            scope=stage.goal or stage.name,
            status="planned",
            stage_id=stage.stage_id,
            depends_on=[ids[key] for key in stage.depends_on if key in ids],
            feedback_to=[ids[key] for key in stage.feedback_to if key in ids],
            method=next(
                (
                    method
                    for method in ("discuss", "plan", "implement", "diagnose", "review", "handoff")
                    if "builtin:" + method in stage.skills
                ),
                "implement",
            ),
        )
        for stage in stages
    ]


class SpaceWorkGraph:
    """复用任务版本、空间消息和原循环，不创建第二调度器。

    Reuse task journals and existing execution.
    """

    def __init__(self, team: "SpaceTeamService") -> None:
        """绑定已有业务服务。

        Bind existing business services.
        """
        self.team = team
        self.start_lock = asyncio.Lock()

    async def get(self, params: SpaceParams) -> WorkGraphView:
        """投影真实进度与历史；读取不会补发执行。

        Project progress and history without replaying work.
        """
        space = await self.team._space(params.task_id)
        task = await self.team.worker.call(self.team.spaces.tasks.store.get, params.task_id)
        activity = await self.team.chat_view(params)
        goals: list[GoalView] = []
        issues = []
        if self.team.sessions.goals:
            references = {
                execution.goal_id for item in activity.rounds for execution in item.executions
            }
            for session_id in dict.fromkeys(
                execution.session_id
                for item in activity.rounds
                for execution in item.executions
                if execution.goal_id
            ):
                try:
                    goals.extend(
                        goal
                        for goal in await self.team.sessions.goals.list(session_id)
                        if goal.goal_id in references
                    )
                except AgentError as exc:
                    issues.append(exc.code + " · " + exc.message)
        return WorkGraphView(
            task=task,
            items=work_items(task, space),
            suggested_items=workflow_skeleton(task),
            activity=activity,
            goals=goals,
            issues=issues,
        )

    async def save(self, params: SaveWorkGraphParams) -> WorkGraphView:
        """保存任务工作定义，保留执行结果。

        Save task definitions while retaining execution results.
        """
        space = await self.team._space(params.task_id)
        facts = await self.team.worker.call(self.team.spaces.tasks.store.history, params.task_id)
        baseline = next(
            (f.view for f in facts if f.view.revision == params.expected_revision), None
        )
        known = {item.work_id for item in work_items(baseline, space)} if baseline else set()
        members = {member.member_id for member in space.config.members}
        if any(
            owner is not None and owner not in members for owner in params.owner_changes.values()
        ):
            raise AgentError("SPACE_MEMBER_NOT_FOUND", "负责人已不在当前团队，请重新选择。")
        await self.team.worker.call(
            self.team.spaces.tasks.store.save_work_plan,
            params.task_id,
            params.operation_id,
            params.expected_revision,
            params.items,
            sorted(known - {item.work_id for item in params.items}),
            params.owner_changes,
        )
        return await self.get(SpaceParams(task_id=params.task_id))

    async def stage(
        self, task: TaskView, session_id: str, item: WorkItem, operation_id: str
    ) -> None:
        """将本次节点阶段用于后续 Skill 装配。

        Apply the node stage to subsequent skill assembly.
        """
        await self.team.worker.call(
            self.team.spaces.tasks.store.bind_work_stage,
            task.task_id,
            session_id,
            item.stage_id,
            operation_id,
        )

    async def start(self, params: StartWorkGraphParams) -> SpaceChatView:
        """串行接纳避免同时切换同一会话的阶段。 Serialize admission and stage selection."""
        async with self.start_lock:
            return await self._start(params)

    async def _start(self, params: StartWorkGraphParams) -> SpaceChatView:
        """执行选定范围，重复操作返回原记录，不自动组建成员。

        Run selected work without assembling sessions.
        """
        space = await self.team._space(params.task_id)
        record = await self.team.worker.call(self.team.store.chat, params.task_id)
        prior = next((m for m in record.view.messages if m.message_id == params.operation_id), None)
        prior_round = next(
            (r for r in record.view.rounds if r.round_id == params.operation_id), None
        )
        if prior or prior_round:
            original = prior_round if prior_round else prior
            if original is not None:
                owners = [e.member_id for e in original.executions]
                text = prior.content if prior else prior_round.objective if prior_round else ""
                if (
                    original.work_ids != params.work_ids
                    or owners != [params.member_id]
                    or bool(prior_round) != params.continuous
                    or not text.endswith("\nUser instruction:\n" + params.instruction)
                    or (prior_round and prior_round.budget != params.budget)
                ):
                    raise AgentError("OPERATION_CONFLICT", "操作标识已用于不同的工作范围。")
            return await self.team.chat_view(SpaceParams(task_id=params.task_id))
        task = await self.team.worker.call(self.team.spaces.tasks.store.get, params.task_id)
        items = {item.work_id: item for item in work_items(task, space)}
        if any(key not in items for key in params.work_ids):
            raise AgentError("SPACE_WORK_NOT_FOUND", "工作项已变化，请刷新后选择。")
        selected = [items[key] for key in dict.fromkeys(params.work_ids)]
        self.team.recipients(space, [params.member_id])
        execution = self.team._execution(space, params.member_id, params.operation_id)
        if self.team.sessions.active_for(execution.session_id) is not None:
            raise AgentError("RUN_BUSY", "该成员正在执行，请等待完成或选择其他成员。")
        read_only = all(execution_mode(item.method) == "plan" for item in selected)
        prompt = (
            "Execute the selected task work below using the current task graph materials. "
            "Each node is a complete agent work unit. Choose meaningful work from dependencies "
            "and feedback, delegate to existing members when useful, and wait for actual results. "
            "Claim work with manage_space_work to load its stage Skills on the next request; "
            "use status/result to share progress. Updates are optional, not execution gates. "
            "A finished Run does not alone prove a work item complete. Feedback links describe "
            "possible returns; repairs and independent review stay within the selected scope "
            "and user instruction. Hand off work IDs, conclusions and artifact references, "
            "and read history as needed. Other nodes provide context, not additional scope. "
            + (
                "Continue complete work rounds toward this objective.\n"
                if params.continuous
                else "Finish this request and return to the user.\n"
            )
            + "Selected work IDs:\n"
            + json.dumps(params.work_ids)
            + "\nUser instruction:\n"
            + params.instruction
        )
        chat_params = SpaceChatParams(
            task_id=params.task_id,
            operation_id=params.operation_id,
            content=prompt,
            target_member_ids=[params.member_id],
            mode="plan" if read_only else "normal",
            work_ids=params.work_ids,
        )
        round_params = StartSpaceRoundParams(
            task_id=params.task_id,
            operation_id=params.operation_id,
            objective=prompt,
            target_member_ids=[params.member_id],
            work_ids=params.work_ids,
            budget=params.budget,
        )
        await self.stage(
            task,
            execution.session_id,
            selected[0],
            str(uuid5(UUID(params.operation_id), "work-stage")),
        )
        if params.continuous:
            return await self.team.start_round(
                round_params,
                assemble=False,
                method="plan" if read_only else "implement",
            )
        return await self.team.chat(chat_params)
