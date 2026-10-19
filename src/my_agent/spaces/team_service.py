"""群聊、模板和 Goal 的空间级关联，无额外模型循环。

Space associations for chat, templates and goals without another model loop.
"""

import asyncio
import json
from typing import Literal
from uuid import UUID, uuid5

from pydantic import ValidationError

from my_agent.collaboration.types import CollaborationRequestParams, ControlCollaborationParams
from my_agent.errors import AgentError
from my_agent.goals.types import GoalControl, GoalCreated, GoalCriterion
from my_agent.runtime.modes import RunMode
from my_agent.sessions.types import AssistantCommitted, Fact, RunAccepted, RunFinished, SessionView
from my_agent.spaces.service import SpaceService
from my_agent.spaces.team_store import SpaceTeamStore
from my_agent.spaces.team_types import (
    CopyTeamTemplateParams,
    GenerateTeamParams,
    ImportTeamTemplateParams,
    SaveTeamDraftArgs,
    SaveTeamTemplateParams,
    SpaceChatMessage,
    SpaceChatPageParams,
    SpaceChatParams,
    SpaceChatView,
    SpaceExecution,
    SpacePublicOutput,
    SpaceRound,
    StartSpaceRoundParams,
    StopSpaceRoundParams,
    TeamGeneration,
    TeamTemplate,
    TeamTemplateExport,
    TeamTemplateParams,
    TeamTemplatesResult,
    UpdateSpaceWorkParams,
)
from my_agent.spaces.types import SpaceParams, SpaceView
from my_agent.spaces.work_graph import SpaceWorkGraph, work_items
from my_agent.storage import utc_now
from my_agent.tasks.types import TaskView
from my_agent.workflow.types import WorkAssignment, WorkMethod


class SpaceTeamService:
    """只组织持久消息与已有运行，成员执行继续由原服务管理。

    Organize durable messages and existing runs while original services own execution.
    """

    def __init__(self, spaces: SpaceService) -> None:
        """复用空间及其运行服务，按操作保存关联。

        Reuse spaces and their execution services for durable associations.
        """
        self.spaces = spaces
        self.sessions = spaces.sessions
        self.worker = spaces.worker
        self.store = SpaceTeamStore(spaces.store)
        self.lock = asyncio.Lock()
        self.generating: dict[str, str] = {}
        self.work_graph = SpaceWorkGraph(self)

    async def _space(self, task_id: str) -> SpaceView:
        """读取真实已保存团队。 Read the actual saved team."""
        result = await self.spaces.get(SpaceParams(task_id=task_id))
        if result.space is None:
            raise AgentError("SPACE_NOT_FOUND", "请先保存合作空间。")
        return result.space

    def generation_for(self, session_id: str, run_id: str) -> str | None:
        """只向已登记生成请求暴露草稿工具。

        Expose the draft tool only to registered generation requests.
        """
        active = self.sessions.active_for(session_id)
        if active is None or active.run_id != run_id:
            return None
        accepted = next(
            (
                fact.data
                for fact in active.log.facts
                if fact.run_id == run_id and isinstance(fact.data, RunAccepted)
            ),
            None,
        )
        return self.generating.get(accepted.operation_id) if accepted else None

    async def generate(self, params: GenerateTeamParams) -> TeamGeneration:
        """现有会话执行只读 Plan，生成不自动采用或创建成员。

        Run a read-only plan in an existing session without adopting or creating members.
        """
        async with self.lock:
            task = await self.worker.call(self.spaces.tasks.store.get, params.task_id)
            session = await self.sessions.view(params.session_id)
            if (
                session.summary.task_id != params.task_id
                or session.summary.project_id != task.project_id
            ):
                raise AgentError("SPACE_SESSION_MISMATCH", "请选择这个任务下的现有规划会话。")
            record = await self.worker.call(self.store.chat, params.task_id)
            prior = next(
                (
                    item
                    for item in record.view.generations
                    if item.params.operation_id == params.operation_id
                ),
                None,
            )
            if prior is not None:
                if prior.params != params:
                    raise AgentError("OPERATION_CONFLICT", "生成标识已用于其他输入。")
                return prior
            saved = await self.worker.call(self.spaces.store.get, params.task_id)
            generation = TeamGeneration(
                params=params,
                expected_revision=saved.view.revision if saved else None,
                created_at=utc_now(),
            )
            record.view.generations.append(generation)
            await self.worker.call(self.store.save_chat, record)
            # Register the accepted operation before the separate Run driver starts.
            # 独立 Run 驱动开始前登记接纳操作，Run 身份仍由原服务生成。
            self.generating[params.operation_id] = params.task_id
            prompt = (
                "Generate an editable team draft for the following project goal. "
                "Read project materials when useful. Use save_team_draft to save "
                "the structured draft; do not create sessions, start work, or write project files. "
                "Use stable UUID member/edge IDs, only glm-5.3-flash "
                "or deepseek-v4.1-flash models, and existing enabled skills when useful. "
                f"Organisation: {params.organisation}. "
                "Include a receiver, duties, scopes, relationships "
                "and concrete initial work items when useful. Use the task workflow snapshot's "
                "stage_id on work items; one stage may contain several items. Assign their "
                "owner_member_id to proposed members, depends_on to work IDs, and feedback_to "
                "to work IDs that may be revisited. Member edges differ from work dependencies. "
                "Relations may include feedback cycles.\nGoal:\n" + params.objective
            )
            try:
                summary = await self.sessions.start(
                    params.session_id, params.operation_id, prompt, None, "plan"
                )
                generation = generation.model_copy(
                    update={"run_id": summary.run.run_id if summary.run else None}
                )
            except AgentError as exc:
                self.generating.pop(params.operation_id, None)
                generation = generation.model_copy(update={"error": exc.code + " · " + exc.message})
            record.view.generations[-1] = generation
            await self.worker.call(self.store.save_chat, record)
            return generation

    async def save_generated(
        self, session_id: str, run_id: str, draft: SaveTeamDraftArgs
    ) -> TeamGeneration:
        """保存模型的完整结构供用户编辑，不改团队或成员绑定。

        Save complete model structure for user edits without changing teams or bindings.
        """
        async with self.lock:
            if draft.initial_work_items:
                draft = draft.model_copy(
                    update={
                        "config": draft.config.model_copy(
                            update={"initial_work_items": draft.initial_work_items}
                        )
                    }
                )
            task_id = self.generation_for(session_id, run_id)
            if task_id is None:
                raise AgentError("SPACE_DRAFT_NOT_REQUESTED", "本次运行没有团队生成请求。")
            record = await self.worker.call(self.store.chat, task_id)
            active = self.sessions.active_for(session_id)
            accepted = (
                next(
                    (
                        fact.data
                        for fact in active.log.facts
                        if fact.run_id == run_id and isinstance(fact.data, RunAccepted)
                    ),
                    None,
                )
                if active
                else None
            )
            index = next(
                (
                    i
                    for i, item in enumerate(record.view.generations)
                    if item.params.session_id == session_id
                    and accepted
                    and item.params.operation_id == accepted.operation_id
                ),
                None,
            )
            if index is None:
                raise AgentError("SPACE_DRAFT_NOT_REQUESTED", "草稿请求来源不一致。")
            generation = record.view.generations[index].model_copy(
                update={"run_id": run_id, "draft": draft, "error": None}
            )
            record.view.generations[index] = generation
            await self.worker.call(self.store.save_chat, record)
            return generation

    @staticmethod
    def recipients(space: SpaceView, requested: list[str], content: str = "") -> list[str]:
        """明确对象优先，@名字支持多选；无对象只发接收成员。

        Prefer explicit recipients, support multiple name mentions, and default to one receiver.
        """
        identities = {item.member_id for item in space.config.members}
        targets = list(dict.fromkeys(requested))
        if not targets:
            targets = [
                member.member_id
                for member in space.config.members
                if f"@{member.name}" in content or f"@{member.member_id}" in content
            ]
        if not targets:
            receiver = space.config.receiver_member_id
            if receiver is None and space.config.members:
                receiver = space.config.members[0].member_id
            if receiver is not None:
                targets = [receiver]
        if not targets:
            raise AgentError("SPACE_NO_MEMBERS", "请添加接收成员。")
        if any(identity not in identities for identity in targets):
            raise AgentError("SPACE_MEMBER_NOT_FOUND", "所选接收成员不在当前团队。")
        return list(dict.fromkeys(targets))

    @staticmethod
    def _execution(space: SpaceView, member_id: str, operation_id: str) -> SpaceExecution:
        """从当前绑定保存执行来源快照。

        Snapshot execution provenance from the current binding.
        """
        binding = next((item for item in space.bindings if item.member_id == member_id), None)
        if binding is None or binding.session_id is None:
            raise AgentError("SPACE_MEMBER_UNBOUND", "请先组建成员会话。")
        return SpaceExecution(
            member_id=member_id,
            session_id=binding.session_id,
            operation_id=str(uuid5(UUID(operation_id), member_id)),
        )

    async def _send(
        self, space: SpaceView, execution: SpaceExecution, content: str, mode: RunMode
    ) -> SpaceExecution:
        """复用 Run 与已有忙队列，失败只记录当前接收方。

        Reuse runs and the existing busy queue; failures remain local to this recipient.
        """
        try:
            summary = await self.sessions.start(
                execution.session_id, execution.operation_id, content, None, mode
            )
            return execution.model_copy(
                update={"run_id": summary.run.run_id if summary.run else None}
            )
        except AgentError as exc:
            if exc.code != "RUN_BUSY":
                return execution.model_copy(update={"error": exc.code + " · " + exc.message})
            service = self.spaces.collaboration or self.sessions.collaboration
            source = next(
                (
                    item.session_id
                    for item in space.bindings
                    if item.session_id is not None and item.session_id != execution.session_id
                ),
                None,
            )
            if service is None or source is None:
                return execution.model_copy(update={"error": exc.code + " · " + exc.message})
            try:
                request = await service.submit(
                    CollaborationRequestParams(
                        operation_id=execution.operation_id,
                        source_session_id=source,
                        target_session_id=execution.session_id,
                        objective=content,
                        mode=mode,
                    )
                )
                return execution.model_copy(
                    update={"request_id": request.request_id, "run_id": request.target_run_id}
                )
            except AgentError as queued_error:
                return execution.model_copy(
                    update={"error": queued_error.code + " · " + queued_error.message}
                )

    async def chat(self, params: SpaceChatParams) -> SpaceChatView:
        """普通输入启动有限请求或 Goal 插话，不广播也不创建 Goal。

        Ordinary input starts bounded requests or goal questions without broadcast or new goals.
        """
        async with self.lock:
            space = await self._space(params.task_id)
            record = await self.worker.call(self.store.chat, params.task_id)
            prior = next(
                (item for item in record.view.messages if item.message_id == params.operation_id),
                None,
            )
            targets = self.recipients(space, params.target_member_ids, params.content)
            if prior is not None:
                if (prior.content, prior.target_member_ids, prior.mode) != (
                    params.content,
                    targets,
                    params.mode,
                ):
                    raise AgentError("OPERATION_CONFLICT", "消息标识已用于其他内容。")
            else:
                message = SpaceChatMessage(
                    work_ids=params.work_ids,
                    message_id=params.operation_id,
                    content=params.content,
                    mode=params.mode,
                    target_member_ids=targets,
                    created_at=utc_now(),
                    executions=[
                        self._execution(space, member, params.operation_id) for member in targets
                    ],
                )
                record.view.messages.append(message)
                await self.worker.call(self.store.save_chat, record)
                # 每次接纳后保存，重启读取不重发任何副作用。
                # Persist each admission; restart reads never replay effects.
                for index, execution in enumerate(message.executions):
                    message.executions[index] = await self._send(
                        space, execution, params.content, params.mode
                    )
                    await self.worker.call(self.store.save_chat, record)
        return await self.chat_view(SpaceParams(task_id=params.task_id))

    async def start_round(
        self,
        params: StartSpaceRoundParams,
        *,
        assemble: bool = True,
        method: WorkMethod = "implement",
    ) -> SpaceChatView:
        """显式组建后仅启动选定成员 Goal，协作委派仍走现有工具。

        Explicitly assemble and start selected member goals; delegation uses existing tools.
        """
        from my_agent.spaces.types import SpaceStartParams

        async with self.lock:
            if assemble:
                space_result = await self.spaces.start(SpaceStartParams(task_id=params.task_id))
                space = space_result.space
            else:
                space = await self._space(params.task_id)
            if space is None:
                raise AgentError("SPACE_NOT_FOUND", "合作空间不存在。")
            record = await self.worker.call(self.store.chat, params.task_id)
            prior = next(
                (item for item in record.view.rounds if item.round_id == params.operation_id), None
            )
            targets = self.recipients(space, params.target_member_ids)
            if prior is not None:
                if (
                    prior.objective,
                    prior.budget,
                    prior.limits,
                    [item.member_id for item in prior.executions],
                ) != (params.objective, params.budget, params.limits, targets):
                    raise AgentError("OPERATION_CONFLICT", "轮次标识已用于其他目标。")
            else:
                if self.sessions.goals is None:
                    raise AgentError("GOALS_UNAVAILABLE", "Goal 服务不可用。")
                round_view = SpaceRound(
                    work_ids=params.work_ids,
                    round_id=params.operation_id,
                    objective=params.objective,
                    budget=params.budget,
                    limits=params.limits,
                    created_at=utc_now(),
                    executions=[
                        self._execution(space, member, params.operation_id) for member in targets
                    ],
                )
                record.view.rounds.append(round_view)
                await self.worker.call(self.store.save_chat, record)
                for index, execution in enumerate(round_view.executions):
                    try:
                        goal = await self.sessions.goals.create(
                            execution.session_id,
                            GoalCreated(
                                method=method,
                                goal_id=execution.operation_id,
                                objective=params.objective,
                                criteria=[
                                    GoalCriterion(
                                        criterion_id="objective",
                                        description="完成本轮明确的合作目标。",
                                    )
                                ],
                                budget=params.budget,
                                limits=params.limits,
                            ),
                        )
                        execution = execution.model_copy(update={"goal_id": goal.goal_id})
                    except AgentError as exc:
                        execution = execution.model_copy(
                            update={"error": exc.code + " · " + exc.message}
                        )
                    round_view.executions[index] = execution
                    await self.worker.call(self.store.save_chat, record)
        return await self.chat_view(SpaceParams(task_id=params.task_id))

    async def chat_view(self, params: SpaceParams | SpaceChatPageParams) -> SpaceChatView:
        """从精确操作和 Goal / 协作事实投影公开流，不自动执行。

        Project public streams from exact operation, goal and collaboration facts without executing.
        """
        async with self.lock:
            await self.worker.call(self.spaces.tasks.store.get, params.task_id)
            record = await self.worker.call(self.store.chat, params.task_id)
            page = (
                params
                if isinstance(params, SpaceChatPageParams)
                else SpaceChatPageParams(task_id=params.task_id)
            )
            ordered = sorted(
                [(m.created_at, m.message_id) for m in record.view.messages]
                + [(r.created_at, r.round_id) for r in record.view.rounds]
            )
            end = len(ordered)
            if page.before_id is not None:
                end = next(
                    (i for i, (_, identity) in enumerate(ordered) if identity == page.before_id), -1
                )
                if end < 0:
                    raise AgentError("SPACE_PAGE_INVALID", "历史位置不存在，请刷新列表。")
            start = max(0, end - page.limit)
            visible = {identity for _, identity in ordered[start:end]}
            if page.before_id is None:
                # 旧轮次仍活跃时继续展示，分页不能把运行控制藏起来。
                # Keep active older rounds visible so pagination never hides live controls.
                entries: list[SpaceChatMessage | SpaceRound] = [
                    *record.view.messages,
                    *record.view.rounds,
                ]
                for item in entries:
                    if any(
                        (active := self.sessions.active_for(e.session_id)) is not None
                        and (
                            active.run_id == e.run_id
                            or (
                                e.goal_id is not None
                                and active.goal
                                and active.goal.goal_id == e.goal_id
                            )
                            or (
                                e.request_id is not None and active.collaboration_id == e.request_id
                            )
                        )
                        for e in item.executions
                    ):
                        visible.add(
                            item.message_id if isinstance(item, SpaceChatMessage) else item.round_id
                        )
            record.view.messages = [m for m in record.view.messages if m.message_id in visible]
            record.view.rounds = [r for r in record.view.rounds if r.round_id in visible]
            record.view.next_before = ordered[start][1] if start > 0 else None
            record.view.generations = record.view.generations[-1:]
            generations: list[TeamGeneration] = []
            for generation in record.view.generations:
                if generation.draft is not None or generation.error is not None:
                    generations.append(generation)
                    continue
                try:
                    async with self.sessions.lock:
                        log = await self.sessions._load(generation.params.session_id)
                        accepted = next(
                            (
                                fact
                                for fact in log.facts
                                if isinstance(fact.data, RunAccepted)
                                and fact.data.operation_id == generation.params.operation_id
                            ),
                            None,
                        )
                        ended = next(
                            (
                                fact.data
                                for fact in log.facts
                                if accepted
                                and fact.run_id == accepted.run_id
                                and isinstance(fact.data, RunFinished)
                            ),
                            None,
                        )
                    if ended:
                        generation = generation.model_copy(
                            update={
                                "error": ended.message
                                or "本次运行未保存结构化团队草稿，请查看原会话或重新生成。"
                            }
                        )
                except AgentError as exc:
                    generation = generation.model_copy(
                        update={"error": exc.code + " · " + exc.message}
                    )
                generations.append(generation)
            references = [
                (message.message_id, execution)
                for message in record.view.messages
                for execution in message.executions
            ]
            references += [
                (item.round_id, execution)
                for item in record.view.rounds
                for execution in item.executions
            ]
            outputs: list[SpacePublicOutput] = []
            snapshots: dict[str, tuple[SessionView, list[Fact]]] = {}
            seen: set[tuple[str, str | None, int | None]] = set()
            for origin_id, execution in references:
                first_output = len(outputs)
                active_run = None
                try:
                    if execution.session_id not in snapshots:
                        snapshot = await self.sessions.view(execution.session_id)
                        async with self.sessions.lock:
                            log = await self.sessions._load(execution.session_id)
                            snapshots[execution.session_id] = (snapshot, list(log.facts))
                    view, facts = snapshots[execution.session_id]
                    active_run = view.summary.run
                    runs = list(
                        dict.fromkeys(
                            fact.run_id
                            for fact in facts
                            if isinstance(fact.data, RunAccepted)
                            and (
                                fact.data.operation_id == execution.operation_id
                                or (
                                    execution.goal_id is not None
                                    and fact.data.goal_id == execution.goal_id
                                )
                                or (
                                    execution.request_id is not None
                                    and fact.data.collaboration_id == execution.request_id
                                )
                            )
                        )
                    )
                    if execution.error:
                        outputs.append(
                            SpacePublicOutput(
                                member_id=execution.member_id,
                                session_id=execution.session_id,
                                run_id=execution.run_id,
                                status="failed",
                                error=execution.error,
                            )
                        )
                    for run_id in runs:
                        ended = next(
                            (
                                fact.data
                                for fact in reversed(facts)
                                if fact.run_id == run_id and isinstance(fact.data, RunFinished)
                            ),
                            None,
                        )
                        status: str = (
                            ended.status
                            if ended
                            else "running"
                            if view.summary.run
                            and view.summary.run.run_id == run_id
                            and view.summary.run.status in {"running", "stopping"}
                            else "interrupted"
                        )
                        emitted = False
                        for fact in facts:
                            if (
                                fact.run_id == run_id
                                and isinstance(fact.data, AssistantCommitted)
                                and fact.data.turn.text
                            ):
                                key = execution.session_id, run_id, fact.seq
                                if key not in seen:
                                    outputs.append(
                                        SpacePublicOutput(
                                            member_id=execution.member_id,
                                            session_id=execution.session_id,
                                            run_id=run_id,
                                            message_id=fact.data.message_id,
                                            seq=fact.seq,
                                            text=fact.data.turn.text,
                                            status=status,
                                        )
                                    )
                                    seen.add(key)
                                emitted = True
                        if (
                            view.summary.run
                            and view.summary.run.run_id == run_id
                            and view.stream_text
                        ):
                            outputs.append(
                                SpacePublicOutput(
                                    member_id=execution.member_id,
                                    session_id=execution.session_id,
                                    run_id=run_id,
                                    message_id=view.stream_message_id,
                                    text=view.stream_text,
                                    streaming=True,
                                    process_epoch=view.process_epoch,
                                    delta_index=view.delta_index,
                                    status=status,
                                )
                            )
                            emitted = True
                        if not emitted:
                            outputs.append(
                                SpacePublicOutput(
                                    member_id=execution.member_id,
                                    session_id=execution.session_id,
                                    run_id=run_id,
                                    status=status,
                                    error=ended.message if ended else None,
                                )
                            )
                    if not runs and not execution.error:
                        status = "queued" if execution.request_id else "pending"
                        outputs.append(
                            SpacePublicOutput(
                                member_id=execution.member_id,
                                session_id=execution.session_id,
                                run_id=None,
                                status=status,
                            )
                        )
                except AgentError as exc:
                    outputs.append(
                        SpacePublicOutput(
                            member_id=execution.member_id,
                            session_id=execution.session_id,
                            run_id=execution.run_id,
                            status="unavailable",
                            error=exc.code + " · " + exc.message,
                        )
                    )
                # 从原投递关联推导来源和等待，不复制日志或猜测成员的整体完成状态。
                # Project exact delivery origins and waits without a second log or completion guess.
                for output in outputs[first_output:]:
                    output.origin_id = origin_id
                    if active_run and active_run.run_id == output.run_id:
                        output.waiting_for = active_run.waiting_for
            return record.view.model_copy(update={"outputs": outputs, "generations": generations})

    async def stop(self, params: StopSpaceRoundParams) -> SpaceChatView:
        """按保存来源停止成员或整轮，保留无关工作和程序。

        Stop members or rounds by durable provenance, preserving unrelated work and programs.
        """
        async with self.lock:
            record = await self.worker.call(self.store.chat, params.task_id)
            rounds = [
                item
                for item in record.view.rounds
                if params.round_id is None or item.round_id == params.round_id
            ]
            references = [
                execution
                for item in rounds
                for execution in item.executions
                if params.member_id is None or execution.member_id == params.member_id
            ]
            if params.round_id is None:
                references += [
                    execution
                    for item in record.view.messages
                    for execution in item.executions
                    if params.member_id is None or execution.member_id == params.member_id
                ]
            for execution in references:
                if execution.goal_id and self.sessions.goals:
                    goals = await self.sessions.goals.list(execution.session_id)
                    goal = next((item for item in goals if item.goal_id == execution.goal_id), None)
                    if goal and goal.status in {"active", "waiting"}:
                        await self.sessions.goals.control(
                            execution.session_id,
                            GoalControl(
                                goal_id=goal.goal_id,
                                operation_id=str(
                                    uuid5(UUID(goal.goal_id), f"space-stop:{goal.revision}")
                                ),
                                expected_revision=goal.revision,
                                action="pause",
                            ),
                        )
                if execution.request_id:
                    service = self.spaces.collaboration or self.sessions.collaboration
                    if service:
                        await service.control(
                            ControlCollaborationParams(
                                request_id=execution.request_id, action="cancel"
                            )
                        )
                active = self.sessions.active_for(execution.session_id)
                if active and active.run_id == execution.run_id:
                    await self.sessions.cancel(active.run_id)
            for item in rounds:
                if params.member_id is None:
                    item.stopped = True
            await self.worker.call(self.store.save_chat, record)
        return await self.chat_view(SpaceParams(task_id=params.task_id))

    async def templates(self) -> TeamTemplatesResult:
        """读取可复用的模板目录。 Read the reusable template catalog."""
        return TeamTemplatesResult(templates=await self.worker.call(self.store.templates))

    async def update_work(self, params: UpdateSpaceWorkParams) -> TaskView:
        """保存分配、领取和结果，进度仍由 TaskWork 记录。

        Save assignments, claims and results in the existing TaskWork version journal.
        """
        async with self.lock:
            space = await self._space(params.task_id)
            task = await self.worker.call(self.spaces.tasks.store.get, params.task_id)
            if params.member_id is not None:
                self.recipients(space, [params.member_id])
            existing = next(
                (item for item in task.work.assignments if item.work_id == params.work_id), None
            )
            items = {item.work_id: item for item in work_items(task, space)}
            known = set(items)
            if params.work_id not in known and existing is None:
                raise AgentError("SPACE_WORK_NOT_FOUND", "当前任务没有该工作项。")
            owner = existing.owner_member_id if existing else None
            claim: Literal["assigned", "claimed", "released"] = (
                existing.claim_status if existing else "assigned"
            )
            if params.action in {"assign", "claim"}:
                if params.member_id is None:
                    raise AgentError("SPACE_MEMBER_NOT_FOUND", "请选择负责人。")
                owner = params.member_id
                claim = "claimed" if params.action == "claim" else "assigned"
            elif params.action == "release":
                owner, claim = None, "released"
            assignment = WorkAssignment(
                progress_updated_at=utc_now()
                if params.status is not None or params.result is not None
                else existing.progress_updated_at
                if existing
                else None,
                status=params.status
                if params.status is not None
                else existing.status
                if existing
                else None,
                work_id=params.work_id,
                owner_member_id=owner,
                claim_status=claim,
                run_id=params.run_id
                if params.run_id is not None
                else existing.run_id
                if existing
                else None,
                result=params.result
                if params.result is not None
                else existing.result
                if existing
                else None,
                updated_at=utc_now(),
            )
            saved = await self.worker.call(
                self.spaces.tasks.store.assign_work, params.task_id, params.operation_id, assignment
            )
            if params.action == "claim" and owner is not None and params.work_id in items:
                binding = next((b for b in space.bindings if b.member_id == owner), None)
                if binding and binding.session_id:
                    await self.work_graph.stage(
                        saved,
                        binding.session_id,
                        items[params.work_id],
                        str(uuid5(UUID(params.operation_id), "work-stage")),
                    )
                    saved = await self.worker.call(self.spaces.tasks.store.get, params.task_id)
            return saved

    async def save_template(self, params: SaveTeamTemplateParams) -> TeamTemplate:
        """保存独立团队快照，后续更改不影响运行团队。

        Save an independent snapshot without changing running teams.
        """
        async with self.lock:
            return await self.worker.call(
                self.store.save_template, TeamTemplate(**params.model_dump(), updated_at=utc_now())
            )

    async def copy_template(self, params: CopyTeamTemplateParams) -> TeamTemplate:
        """复制为独立身份和快照。 Copy into a distinct identity and snapshot."""
        source = await self.worker.call(self.store.template, params.template_id)
        return await self.save_template(
            SaveTeamTemplateParams(
                template_id=params.new_template_id,
                name=params.name,
                description=source.description,
                draft=source.draft,
            )
        )

    async def import_template(self, params: ImportTeamTemplateParams) -> TeamTemplate:
        """严格导入分享 JSON，不执行其中命令或创建会话。

        Strictly import JSON without executing commands or creating sessions.
        """
        try:
            template = TeamTemplate.model_validate_json(params.content)
        except ValidationError as exc:
            raise AgentError("SPACE_TEMPLATE_INVALID", "模板 JSON 格式或版本不支持。") from exc
        return await self.save_template(
            SaveTeamTemplateParams(
                template_id=params.template_id,
                name=template.name,
                description=template.description,
                draft=template.draft,
            )
        )

    async def export_template(self, params: TeamTemplateParams) -> TeamTemplateExport:
        """返回仅含团队配置的可分享 JSON。

        Return shareable JSON containing only team configuration.
        """
        template = await self.worker.call(self.store.template, params.template_id)
        return TeamTemplateExport(
            content=json.dumps(template.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n"
        )
