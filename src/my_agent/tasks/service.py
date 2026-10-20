"""协调任务与会话的单文件保存边界。 Coordinate task and session persistence boundaries."""

from my_agent.errors import AgentError
from my_agent.models.types import ModelId
from my_agent.sessions.service import SessionService
from my_agent.sessions.types import SessionAssigned, SessionSummary
from my_agent.tasks.store import TaskStore
from my_agent.tasks.types import AssignSessionParams, CreateTaskParams, CreateTaskResult, TaskView
from my_agent.worker import BusinessWorker
from my_agent.workflow.style_types import ApplyWorkStyle
from my_agent.workflow.workstyles import WorkStyleStore


class TaskService:
    """任务保存在前，首会话在后；部分失败能显式接续。

    Save the task first and expose recoverable partial creation.
    """

    def __init__(self, store: TaskStore, sessions: SessionService, worker: BusinessWorker) -> None:
        """注入共享服务，不另开业务写入者。 Inject shared services without a second writer."""
        self.store = store
        self.sessions = sessions
        self.worker = worker

    async def create(self, params: CreateTaskParams) -> CreateTaskResult:
        """验证空项目也可创建任务，不调用模型。 Allow an empty project without invoking a model."""
        await self.sessions.validate_project(params.project_id)
        task = await self.worker.call(self.store.create, params)
        if task.workstyle:
            from my_agent.spaces.store import SpaceStore
            from my_agent.spaces.types import SaveSpaceParams

            def seed_team() -> None:
                """只补初次空间，不覆盖已有配置；不创建其他正式会话。

                Seed only missing space without extra sessions.
                """
                spaces = SpaceStore(self.store.storage)
                if spaces.get(task.task_id) is None and task.workstyle:
                    spaces.save_config(
                        task,
                        SaveSpaceParams(
                            task_id=task.task_id, expected_revision=None, config=task.workstyle.team
                        ),
                    )

            await self.worker.call(seed_team)
        return await self.first_session(task)

    async def first_session(self, task: TaskView) -> CreateTaskResult:
        """只补齐同一首会话；错误返回已保存任务，供用户接续。

        Complete the same first session or return the saved task.
        """
        try:
            session = await self.sessions.create(
                task.project_id,
                task.initial_model_id,
                session_id=task.initial_session_id,
                operation_id=task.task_id,
                task_id=task.task_id,
            )
            return CreateTaskResult(task=task, session=session, session_error=None)
        except AgentError as exc:
            return CreateTaskResult(
                task=task, session=None, session_error=exc.code + " · " + exc.message
            )

    async def apply_workstyle(self, params: ApplyWorkStyle) -> TaskView:
        """配置更新保留历史，空间保存失败可重试补齐，不创建／启动会话。

        Retain history; retry partial space saves without creating or starting sessions.
        """
        from my_agent.spaces.store import SpaceStore
        from my_agent.spaces.types import SaveSpaceParams
        from my_agent.storage import utc_now
        from my_agent.tasks.types import TaskFact
        from my_agent.workflow.templates import TaskWorkflow
        from my_agent.workflow.types import WorkAssignment

        def apply() -> TaskView:
            """同一业务线程保存任务后空间，明确不是跨文件事务。

            Save task then space on one worker, not a transaction.
            """
            facts = self.store.history(params.task_id)
            current = facts[-1].view
            repeated = next((f for f in facts if f.operation_id == params.operation_id), None)
            spaces = SpaceStore(self.store.storage)
            space = spaces.get(params.task_id)
            if repeated:
                if (
                    not repeated.view.workstyle
                    or repeated.view.workstyle.style_id != params.style_id
                ):
                    raise AgentError("OPERATION_CONFLICT", "该操作已用于另一工作方式。")
                style = repeated.view.workstyle
                # 后来的人工配置不因旧请求重试被覆盖。
                # An old retry must not replace later user configuration.
                if current.revision != repeated.view.revision:
                    return current
            else:
                if current.revision != params.expected_revision:
                    raise AgentError("TASK_VERSION_CONFLICT", "任务已变化，请刷新后合并。")
                if (space.view.revision if space else None) != params.expected_space_revision:
                    raise AgentError("SPACE_VERSION_CONFLICT", "空间已变化，请刷新后采用。")
                style = WorkStyleStore.instantiate(
                    WorkStyleStore(self.store.storage).load(params.style_id), params.task_id
                )
                current = current.model_copy(deep=True)
                current.workstyle = style
                current.workflow = (
                    TaskWorkflow(
                        template=style.workflow,
                        current_stage_id=style.workflow.stages[0].stage_id
                        if style.workflow.stages
                        else None,
                    )
                    if style.workflow
                    else None
                )
                # 采用的是新蓝图，不让旧分配、完成报告或删除标记覆盖它；历史留在 facts。
                # Reset stale node state; prior facts retain history.
                adopted_ids = {item.work_id for item in style.team.initial_work_items}
                member_ids = {member.member_id for member in style.team.members}
                definitions = {
                    item.work_id: item
                    for item in (space.view.config.initial_work_items if space else [])
                }
                definitions.update((item.work_id, item) for item in current.work.planned_items)
                definitions.update((item.work_id, item) for item in style.team.initial_work_items)
                current.work.planned_items = [
                    item
                    if item.owner_member_id in member_ids or item.owner_member_id is None
                    else item.model_copy(
                        update={"owner_member_id": None, "claim_status": "unclaimed"}
                    )
                    for item in definitions.values()
                ]
                current.work.items = [
                    entry for entry in current.work.items if entry.item.work_id not in adopted_ids
                ]
                current.work.removed_work_ids = [
                    identity
                    for identity in current.work.removed_work_ids
                    if identity not in adopted_ids
                ]
                now = utc_now()
                retained = [
                    entry
                    if entry.owner_member_id in member_ids or entry.owner_member_id is None
                    else entry.model_copy(
                        update={"owner_member_id": None, "claim_status": "released"}
                    )
                    for entry in current.work.assignments
                    if entry.work_id not in adopted_ids
                ]
                current.work.assignments = retained + [
                    WorkAssignment(
                        work_id=item.work_id,
                        owner_member_id=item.owner_member_id,
                        claim_status="assigned" if item.owner_member_id else "released",
                        status=item.status,
                        updated_at=now,
                        progress_updated_at=now,
                    )
                    for item in style.team.initial_work_items
                ]
                current.revision += 1
                current.updated_at, current.source = now, "user"
                current = self.store._save(
                    [
                        *facts,
                        TaskFact(
                            operation_id=params.operation_id,
                            expected_revision=params.expected_revision,
                            view=current,
                        ),
                    ]
                )
            if space and space.view.config == style.team:
                return current
            spaces.save_config(
                current,
                SaveSpaceParams(
                    task_id=params.task_id,
                    expected_revision=params.expected_space_revision,
                    config=style.team,
                ),
            )
            return current

        return await self.worker.call(apply)

    async def create_session(
        self,
        project_id: str,
        model_id: ModelId,
        task_id: str | None,
        operation_id: str | None,
        role: str,
        scope: str,
    ) -> SessionSummary:
        """只接受用户指定的任务归属，创建动作不执行任务。

        Create a user-selected task session without execution.
        """
        if task_id:
            task = await self.worker.call(self.store.get, task_id)
            if task.project_id != project_id:
                raise AgentError("TASK_PROJECT_MISMATCH", "任务不属于当前项目。")
        return await self.sessions.create(
            project_id,
            model_id,
            session_id=operation_id,
            operation_id=operation_id,
            task_id=task_id,
            role=role,
            scope=scope,
        )

    async def assign(self, params: AssignSessionParams) -> SessionSummary:
        """验证目标任务后追加归属事实，不重写历史。

        Validate ownership before appending a membership fact.
        """
        task = await self.worker.call(self.store.get, params.task_id)
        return await self.sessions.assign(
            params.session_id,
            task.project_id,
            SessionAssigned(
                operation_id=params.operation_id,
                task_id=params.task_id,
                role=params.role,
                scope=params.scope,
            ),
        )
