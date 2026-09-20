"""协调任务与会话的单文件保存边界。 Coordinate task and session persistence boundaries."""

from my_agent.errors import AgentError
from my_agent.models.types import ModelId
from my_agent.sessions.service import SessionService
from my_agent.sessions.types import SessionAssigned, SessionSummary
from my_agent.tasks.store import TaskStore
from my_agent.tasks.types import AssignSessionParams, CreateTaskParams, CreateTaskResult, TaskView
from my_agent.worker import BusinessWorker


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
