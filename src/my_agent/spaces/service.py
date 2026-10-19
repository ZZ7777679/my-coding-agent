"""任务级组队服务，复用已有会话与协作执行。

Task-level assembly over existing session and collaboration services.
"""

import asyncio
from uuid import UUID, uuid5

from my_agent.collaboration.service import CollaborationService
from my_agent.collaboration.types import ConnectSessionsParams
from my_agent.errors import AgentError
from my_agent.sessions.service import SessionService
from my_agent.skills.types import SelectSkillsParams
from my_agent.spaces.store import SpaceStore
from my_agent.spaces.types import (
    BindSpaceMemberParams,
    SaveSpaceLayoutParams,
    SaveSpaceParams,
    SpaceBinding,
    SpaceBindingOperation,
    SpaceMember,
    SpaceParams,
    SpaceRecord,
    SpaceResult,
    SpaceStartParams,
)
from my_agent.tasks.service import TaskService
from my_agent.tasks.types import AssignSessionParams
from my_agent.worker import BusinessWorker


class SpaceService:
    """管理成员配置、绑定与部分失败，不建立第二套运行循环。

    Own member configuration, bindings and partial failures without another runtime.
    """

    def __init__(
        self,
        store: SpaceStore,
        tasks: TaskService,
        sessions: SessionService,
        worker: BusinessWorker,
        collaboration: CollaborationService | None = None,
    ) -> None:
        """注入共享写者与业务服务，按空间操作串行组队。

        Inject shared services and serialize space assembly operations.
        """
        self.store, self.tasks, self.sessions, self.worker = store, tasks, sessions, worker
        self.collaboration = collaboration
        self.lock = asyncio.Lock()

    async def get(self, params: SpaceParams) -> SpaceResult:
        """核实真实任务，只读返回空间或缺失状态。

        Validate the task and read a space or its absence.
        """
        async with self.lock:
            task = await self.worker.call(self.tasks.store.get, params.task_id)
            record = await self.worker.call(self.store.get, params.task_id)
            if record is not None and record.view.project_id != task.project_id:
                raise AgentError("SPACE_PROJECT_MISMATCH", "空间与任务项目归属不一致。")
            return SpaceResult(space=record.view if record is not None else None)

    async def _required(self, task_id: str) -> SpaceRecord:
        """显式操作要求已有草稿，不自动建立团队。

        Explicit operations require a draft without automatic team creation.
        """
        task = await self.worker.call(self.tasks.store.get, task_id)
        record = await self.worker.call(self.store.get, task_id)
        if record is None:
            raise AgentError("SPACE_NOT_FOUND", "请先保存合作空间草稿。")
        if record.view.project_id != task.project_id:
            raise AgentError("SPACE_PROJECT_MISMATCH", "空间与任务项目归属不一致。")
        return record

    async def save(self, params: SaveSpaceParams) -> SpaceResult:
        """保存草稿不创建会话；已有成员选择用于后续请求。

        Save drafts without session creation and refresh existing member choices.
        """
        async with self.lock:
            task = await self.worker.call(self.tasks.store.get, params.task_id)
            previous = await self.worker.call(self.store.get, params.task_id)
            if previous is not None:
                active_members = {member.member_id for member in params.config.members}
                session_ids = [
                    binding.session_id
                    for binding in previous.view.bindings
                    if binding.member_id in active_members and binding.session_id is not None
                ]
                if len(set(session_ids)) != len(session_ids):
                    raise AgentError(
                        "SPACE_SESSION_ALREADY_BOUND",
                        "同一当前会话不能同时绑定两个成员，请先更换绑定。",
                    )
            record = await self.worker.call(self.store.save_config, task, params)
            for member in record.view.config.members:
                binding = self._binding(record, member.member_id)
                if binding.session_id is not None:
                    prior_member = (
                        next(
                            (
                                item
                                for item in previous.view.config.members
                                if item.member_id == member.member_id
                            ),
                            None,
                        )
                        if previous is not None
                        else None
                    )
                    if prior_member is None or (
                        prior_member.model_id,
                        prior_member.skill_ids,
                        prior_member.role,
                        prior_member.scope,
                    ) != (member.model_id, member.skill_ids, member.role, member.scope):
                        record = await self._refresh(record, member, binding, prior_member)
            return SpaceResult(space=record.view)

    async def layout(self, params: SaveSpaceLayoutParams) -> SpaceResult:
        """独立保存图面板与阅读位置，不应用团队成员设置。

        Save graph visibility and reading position without applying team settings.
        """
        async with self.lock:
            record = await self._required(params.task_id)
            if record.view.layout != params.layout:
                record = await self.worker.call(
                    self.store.save,
                    record.model_copy(
                        update={"view": record.view.model_copy(update={"layout": params.layout})}
                    ),
                )
            return SpaceResult(space=record.view)

    @staticmethod
    def _member(record: SpaceRecord, member_id: str) -> SpaceMember:
        """按稳定身份定位当前成员。

        Locate a current member by stable identity.
        """
        member = next((m for m in record.view.config.members if m.member_id == member_id), None)
        if member is None:
            raise AgentError("SPACE_MEMBER_NOT_FOUND", "空间中不存在该成员。")
        return member

    @staticmethod
    def _binding(record: SpaceRecord, member_id: str) -> SpaceBinding:
        """读取独立绑定，未启动成员保持未绑定。

        Read separate bindings, leaving unstarted members unbound.
        """
        return next(
            (binding for binding in record.view.bindings if binding.member_id == member_id),
            SpaceBinding(member_id=member_id),
        )

    async def _save_binding(
        self, record: SpaceRecord, binding: SpaceBinding, *, force: bool = False
    ) -> SpaceRecord:
        """逐成员保存真实结果，保留移除成员的历史。

        Save actual member results and retain removed members' history.
        """
        existing = self._binding(record, binding.member_id)
        if (
            not force
            and existing == binding
            and any(item.member_id == binding.member_id for item in record.view.bindings)
        ):
            return record
        bindings = [
            binding if item.member_id == binding.member_id else item
            for item in record.view.bindings
        ]
        if not any(item.member_id == binding.member_id for item in record.view.bindings):
            bindings.append(binding)
        return await self.worker.call(
            self.store.save,
            record.model_copy(
                update={"view": record.view.model_copy(update={"bindings": bindings})}
            ),
        )

    async def _refresh(
        self,
        record: SpaceRecord,
        member: SpaceMember,
        binding: SpaceBinding,
        previous: SpaceMember | None = None,
    ) -> SpaceRecord:
        """同步后续请求设置，配置已保存时局部错误仍可恢复。

        Refresh next-request settings and preserve recoverable local errors.
        """
        session_id = binding.session_id
        if session_id is None:
            return record
        try:
            view = await self.sessions.view(session_id)
            if (
                view.summary.task_id != record.view.task_id
                or view.summary.project_id != record.view.project_id
            ):
                raise AgentError("SPACE_SESSION_MISMATCH", "成员会话已不属于该任务或项目。")
            if (
                previous is None or previous.model_id != member.model_id
            ) and view.summary.model_id != member.model_id:
                await self.sessions.select_model(
                    session_id,
                    str(
                        uuid5(
                            UUID(session_id),
                            f"space-model:{record.view.revision}:{member.model_id}",
                        )
                    ),
                    member.model_id,
                )
            update_skills = previous is None or previous.skill_ids != member.skill_ids
            if update_skills and self.sessions.skills is not None:
                await self.worker.call(
                    self.sessions.skills.select,
                    SelectSkillsParams(
                        project_id=record.view.project_id,
                        session_id=session_id,
                        selected=member.skill_ids,
                    ),
                )
            elif update_skills and member.skill_ids:
                raise AgentError("SKILLS_UNAVAILABLE", "Skill 服务不可用，成员选择尚未应用。")
            if (view.summary.role, view.summary.scope) != (member.role, member.scope):
                try:
                    await self.tasks.assign(
                        AssignSessionParams(
                            task_id=record.view.task_id,
                            session_id=session_id,
                            operation_id=str(
                                uuid5(UUID(session_id), f"space-role:{record.view.revision}")
                            ),
                            role=member.role,
                            scope=member.scope,
                        )
                    )
                except AgentError as exc:
                    if exc.code != "RUN_BUSY":
                        raise
                    # 运行中不追加归属事实；已保存职责从共同上下文在下次请求采用。
                    # Busy runs keep membership; shared context applies duties next request.
            error = None
        except AgentError as exc:
            error = exc.code + " · " + exc.message
        return await self._save_binding(record, binding.model_copy(update={"error": error}))

    async def _reserve(
        self,
        record: SpaceRecord,
        member: SpaceMember,
        operation_id: str,
        requested_session_id: str | None,
    ) -> tuple[SpaceRecord, SpaceBindingOperation]:
        """副作用前保存原输入快照，显式重试使用同一身份。

        Save original inputs before effects so explicit retries retain identity.
        """
        prior = next((o for o in record.operations if o.operation_id == operation_id), None)
        if prior is not None:
            if (
                prior.member_id != member.member_id
                or prior.requested_session_id != requested_session_id
            ):
                raise AgentError("OPERATION_CONFLICT", "该操作标识已用于其他成员绑定。")
            return record, prior
        operation = SpaceBindingOperation(
            operation_id=operation_id,
            member_id=member.member_id,
            requested_session_id=requested_session_id,
            session_id=requested_session_id or operation_id,
            member=member,
        )
        record = await self.worker.call(
            self.store.save,
            record.model_copy(update={"operations": [*record.operations, operation]}),
        )
        return record, operation

    async def _bind_operation(
        self, record: SpaceRecord, operation: SpaceBindingOperation
    ) -> SpaceRecord:
        """复用已创建会话，部分失败保存明确错误。

        Reuse created sessions and persist explicit partial errors.
        """
        binding = self._binding(record, operation.member_id)
        if operation.completed:
            if binding.session_id == operation.session_id and binding.error is not None:
                return await self._refresh(
                    record, self._member(record, operation.member_id), binding
                )
            return record
        try:
            if any(
                member.member_id != operation.member_id
                and self._binding(record, member.member_id).session_id == operation.session_id
                for member in record.view.config.members
            ):
                raise AgentError(
                    "SPACE_SESSION_ALREADY_BOUND", "该会话已绑定空间中另一个当前成员。"
                )
            if operation.requested_session_id is None:
                await self.tasks.create_session(
                    record.view.project_id,
                    operation.member.model_id,
                    record.view.task_id,
                    operation.operation_id,
                    operation.member.role,
                    operation.member.scope,
                )
            else:
                view = await self.sessions.view(operation.session_id)
                if (
                    view.summary.task_id != record.view.task_id
                    or view.summary.project_id != record.view.project_id
                ):
                    raise AgentError("SPACE_SESSION_MISMATCH", "只能绑定同一任务和项目下的会话。")
            # 会话已保存后才更新成员；创建成功而本文件保存失败仍可用预留身份接续。
            # Reserved identity recovers durable session creation after a binding save failure.
            binding = binding.model_copy(
                update={
                    "session_id": operation.session_id,
                    "session_ids": list(
                        dict.fromkeys([*binding.session_ids, operation.session_id])
                    ),
                    "error": None,
                }
            )
            operations = [
                item.model_copy(update={"completed": True})
                if item.operation_id == operation.operation_id
                else item
                for item in record.operations
            ]
            record = record.model_copy(update={"operations": operations})
        except AgentError as exc:
            binding = binding.model_copy(update={"error": exc.code + " · " + exc.message})
        record = await self._save_binding(
            record,
            binding,
            force=any(
                item.operation_id == operation.operation_id and item.completed
                for item in record.operations
            ),
        )
        if operation.session_id == binding.session_id:
            record = await self._refresh(record, self._member(record, operation.member_id), binding)
        return record

    async def _connect(self, record: SpaceRecord) -> SpaceRecord:
        """全部当前成员互相接入既有协作，图不决定权限。

        Connect all current members through existing collaboration independently of graph edges.
        """
        service = self.collaboration or self.sessions.collaboration
        session_ids = list(
            dict.fromkeys(
                binding.session_id
                for member in record.view.config.members
                if (binding := self._binding(record, member.member_id)).session_id is not None
            )
        )
        error: str | None = None
        if service is not None:
            try:
                for source in session_ids:
                    for target in session_ids:
                        if source != target:
                            existing = await self.worker.call(service.store.link, source, target)
                            if (
                                existing is not None
                                and existing.enabled
                                and existing.task_id == record.view.task_id
                            ):
                                continue
                            await service.connect(
                                ConnectSessionsParams(
                                    source_session_id=source,
                                    target_session_id=target,
                                    scope=(
                                        "同一合作空间内按成员职责协作。 "
                                        "Collaborate within this task space "
                                        "by member responsibilities."
                                    ),
                                    mode="normal",
                                )
                            )
            except AgentError as exc:
                error = exc.code + " · " + exc.message
        elif len(session_ids) > 1:
            error = "COLLABORATION_UNAVAILABLE · 协作服务不可用，成员会话已保留。"
        if error != record.view.error:
            record = await self.worker.call(
                self.store.save,
                record.model_copy(update={"view": record.view.model_copy(update={"error": error})}),
            )
        return record

    async def start(self, params: SpaceStartParams) -> SpaceResult:
        """显式组建缺失成员会话，重复操作不重复创建。

        Explicitly assemble missing sessions without duplicates on retries.
        """
        async with self.lock:
            record = await self._required(params.task_id)
            for member in record.view.config.members:
                binding = self._binding(record, member.member_id)
                if binding.session_id is not None:
                    continue
                operation_id = str(uuid5(UUID(params.task_id), f"space-member:{member.member_id}"))
                record, operation = await self._reserve(record, member, operation_id, None)
                record = await self._bind_operation(record, operation)
            record = await self._connect(record)
            return SpaceResult(space=record.view)

    async def bind(self, params: BindSpaceMemberParams) -> SpaceResult:
        """显式更换成员会话，旧会话历史继续保留。

        Explicitly replace a member session while retaining old history.
        """
        async with self.lock:
            record = await self._required(params.task_id)
            member = self._member(record, params.member_id)
            record, operation = await self._reserve(
                record, member, params.operation_id, params.session_id
            )
            record = await self._bind_operation(record, operation)
            record = await self._connect(record)
            return SpaceResult(space=record.view)
