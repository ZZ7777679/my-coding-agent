"""可接续团队设计，复用原会话、草稿工具和合作 Goal。

Resumable team design using existing sessions, draft tools and cooperative goals.
"""

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID, uuid5

from my_agent.errors import AgentError
from my_agent.spaces.design_types import (
    OpenTeamDesignParams,
    SaveTeamDesignParams,
    SendTeamDesignParams,
    StartTeamDesignParams,
    TeamDesignLaunch,
    TeamDesignView,
)
from my_agent.spaces.team_types import GenerateTeamParams, StartSpaceRoundParams
from my_agent.spaces.types import SaveSpaceParams, SpaceConfig, SpaceParams, SpaceStartParams
from my_agent.storage import read_document, write_document

if TYPE_CHECKING:
    from my_agent.spaces.team_service import SpaceTeamService


DESIGN_INSTRUCTIONS = """You are the team-design assistant for this task. Discuss the user's
goal and create or revise the actual team and collaboration graph using save_team_draft.
Use read_team_design before editing to see the current graph, including manual edits.
Keep stable member/edge IDs and existing positions unless the user asks to change them.
Members are complete coding agents; edges describe delegation, delivery, discussion and
feedback (cycles are allowed). Use enabled Skills when useful, without requiring them.
Include concrete initial work items and dependencies when useful. Save a concise objective
reflecting the agreed team execution scope. Ordinary questions may be answered without
saving a draft. This conversation designs the team only; the user
confirms and starts it through the workspace. Do not create member sessions or execute project
changes here. Read project materials as needed. Explain actual saved changes briefly.
"""


class TeamDesignService:
    """按任务保存讨论入口与图；模型读写仍经同一业务写者。

    Persist task-scoped design entry and graph through the shared business writer.
    """

    def __init__(self, team: "SpaceTeamService") -> None:
        """注入现有服务，保存每次模型读图基线。

        Inject services and retain per-run graph read baselines.
        """
        self.team = team
        self.lock = asyncio.Lock()
        self.reads: dict[tuple[str, str], SpaceConfig | None] = {}

    def read(self, task_id: str) -> TeamDesignView | None:
        """只读设计文件，旧任务没有文件时保持缺失。

        Read design metadata without migrating old tasks.
        """
        path = self.team.spaces.store.path(task_id).with_suffix(".design.json")
        return read_document(path, TeamDesignView) if path.exists() else None

    def write(self, view: TeamDesignView) -> TeamDesignView:
        """沿用写者和原子替换，真实保存错误向上传递。

        Use the writer and atomic replacement with real failure propagation.
        """
        self.team.spaces.store.storage.require_writer()
        path = self.team.spaces.store.path(view.task_id).with_suffix(".design.json")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_document(path, view)
        except OSError as exc:
            raise AgentError("SPACE_SAVE_FAILED", "团队设计保存失败，原记录保留。") from exc
        return view

    def required(self, task_id: str) -> TeamDesignView:
        """读取已打开的设计，不隐式创建新会话。

        Read an opened design without implicitly creating sessions.
        """
        view = self.read(task_id)
        if view is None:
            raise AgentError("SPACE_DESIGN_NOT_FOUND", "请先打开这个任务的团队设计。")
        return view

    async def get(self, params: SpaceParams) -> TeamDesignView:
        """刷新仅取已存关联，不调用模型。

        Refresh saved references without model calls.
        """
        return await self.team.worker.call(self.required, params.task_id)

    async def open(self, params: OpenTeamDesignParams) -> TeamDesignView:
        """显式打开创建一个稳定专用会话，重复打开不创建副本。

        Explicitly open one stable design session; reopening never creates duplicates.
        """
        async with self.lock:
            task = await self.team.worker.call(self.team.spaces.tasks.store.get, params.task_id)
            view = await self.team.worker.call(self.read, params.task_id)
            if view is None:
                space = await self.team.spaces.get(SpaceParams(task_id=params.task_id))
                chat = await self.team.worker.call(self.team.store.chat, params.task_id)
                previous = next((g.draft for g in reversed(chat.view.generations) if g.draft), None)
                view = TeamDesignView(
                    task_id=params.task_id,
                    session_id=str(uuid5(UUID(params.task_id), "team-design")),
                    initial_model_id=params.model_id,
                    objective=task.fields.goal,
                    config=space.space.config
                    if space.space
                    else previous.config
                    if previous
                    else None,
                )
                await self.team.worker.call(self.write, view)
            await self.team.sessions.create(
                task.project_id,
                view.initial_model_id,
                session_id=view.session_id,
                operation_id=view.session_id,
                task_id=task.task_id,
                purpose="team_design",
                role="团队设计",
                inherited_context=DESIGN_INSTRUCTIONS,
            )
            await self.team.sessions.rename(
                view.session_id, str(uuid5(UUID(view.session_id), "name")), "团队设计"
            )
            return view

    def _save(self, params: SaveTeamDesignParams) -> TeamDesignView:
        """在写者一次更新指定字段，输入保存不覆盖新图。

        Update selected fields so input saves cannot replace newer graphs.
        """
        view = self.required(params.task_id)
        if params.input_text is not None:
            view.input_text = params.input_text
        if params.config is not None and params.config != view.config:
            view.config = params.config
            view.revision += 1
        return self.write(view)

    async def save(self, params: SaveTeamDesignParams) -> TeamDesignView:
        """保存用户编辑，不触发模型和成员工作。

        Save user edits without starting models or members.
        """
        return await self.team.worker.call(self._save, params)

    async def send(self, params: SendTeamDesignParams) -> TeamDesignView:
        """复用普通 Run 追加语义，设计输入始终进入专用会话。

        Reuse ordinary Run steering, always targeting the dedicated session.
        """
        async with self.lock:
            view = await self.get(SpaceParams(task_id=params.task_id))
            active = self.team.sessions.active_for(view.session_id)
            if active is not None:
                await self.team.sessions.start(
                    view.session_id, params.operation_id, params.content, None, "plan"
                )
            else:
                generation = await self.team.generate(
                    GenerateTeamParams(
                        task_id=params.task_id,
                        session_id=view.session_id,
                        operation_id=params.operation_id,
                        objective=params.content,
                        discussion=True,
                    )
                )
                if generation.error:
                    code, separator, message = generation.error.partition(" · ")
                    raise AgentError(code if separator else "SPACE_DESIGN_FAILED", message or code)
            # 只清理已提交的输入，不抹掉用户在请求接纳期间新写的草稿。
            # Clear only submitted input, not a newer draft typed during admission.
            return await self.team.worker.call(self._clear_input, params)

    def _clear_input(self, params: SendTeamDesignParams) -> TeamDesignView:
        """按内容清理已发送草稿。 Clear the matching submitted draft."""
        view = self.required(params.task_id)
        if view.input_text == params.content:
            view.input_text = ""
            self.write(view)
        return view

    def read_for_model(self, task_id: str, session_id: str, run_id: str) -> TeamDesignView:
        """给模型当前图并记录实际读到的基线。

        Return the current graph and remember its actual read baseline.
        """
        view = self.required(task_id)
        if view.session_id != session_id:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "请在团队设计会话中使用此入口。")
        self.reads = {key: value for key, value in self.reads.items() if key[0] != session_id}
        self.reads[(session_id, run_id)] = view.config
        return view

    def save_generated(
        self,
        task_id: str,
        session_id: str,
        run_id: str,
        config: SpaceConfig,
        objective: str | None = None,
    ) -> None:
        """保存模型图，检测同时发生的人工编辑。

        Save generated graphs while detecting concurrent manual edits.
        """
        view = self.read(task_id)
        if view is None or view.session_id != session_id:
            return  # 兼容旧生成入口。 Preserve the legacy generation path.
        key = session_id, run_id
        if key in self.reads and self.reads[key] != view.config:
            raise AgentError(
                "INVALID_TOOL_ARGUMENTS",
                "用户刚修改了图，请用 read_team_design 读取当前图后合并本次修改。",
            )
        view.config = config
        if objective and objective.strip():
            view.objective = objective
        view.revision += 1
        self.write(view)
        self.reads[key] = config

    async def start(self, params: StartTeamDesignParams) -> TeamDesignView:
        """单次确认保存、组建、启动；部分结果保留，不重放已接纳 Goal。

        Confirm, assemble and start once, retaining results without replaying accepted goals.
        """
        async with self.lock:
            view = await self.get(SpaceParams(task_id=params.task_id))
            launch = next((x for x in view.launches if x.operation_id == params.operation_id), None)
            if launch is not None and launch.config != params.config:
                raise AgentError("OPERATION_CONFLICT", "该启动标识已用于其他团队配置。")
            if launch is None:
                task = await self.team.worker.call(self.team.spaces.tasks.store.get, params.task_id)
                launch = TeamDesignLaunch(
                    operation_id=params.operation_id,
                    config=params.config,
                    objective=(
                        "按照当前已确认团队、工作图和分工推进任务。你负责协调：将可并行的工作"
                        "委派给现有成员，依赖结果的工作等待交接，读取真实结果后汇总。"
                        "不要重复让所有成员完成同一任务；无需逐成员请求用户批准。\n任务目标：\n"
                        + (view.objective or task.fields.goal)
                    ),
                )
                await self.save(SaveTeamDesignParams(task_id=params.task_id, config=params.config))
                await self.team.worker.call(self._store_launch, params.task_id, launch)
            if launch.stage == "started":
                return await self.get(SpaceParams(task_id=params.task_id))
            try:
                if launch.stage == "accepted":
                    current = await self.team.spaces.get(SpaceParams(task_id=params.task_id))
                    await self.team.spaces.save(
                        SaveSpaceParams(
                            task_id=params.task_id,
                            expected_revision=current.space.revision if current.space else None,
                            config=launch.config,
                        )
                    )
                    launch.stage = "saved"
                    await self.team.worker.call(self._store_launch, params.task_id, launch)
                assembled = await self.team.spaces.start(SpaceStartParams(task_id=params.task_id))
                space = assembled.space
                if space is None:
                    raise AgentError("SPACE_NOT_FOUND", "团队配置未保存。")
                members = {member.member_id for member in space.config.members}
                errors = [b.error for b in space.bindings if b.member_id in members and b.error]
                if space.error or errors:
                    raise AgentError("SPACE_ASSEMBLY_FAILED", space.error or "；".join(errors))
                launch.stage = "assembled"
                await self.team.worker.call(self._store_launch, params.task_id, launch)
                result = await self.team.start_round(
                    StartSpaceRoundParams(
                        task_id=params.task_id,
                        operation_id=params.operation_id,
                        objective=launch.objective,
                    ),
                    assemble=False,
                )
                actual = next(r for r in result.rounds if r.round_id == params.operation_id)
                launch.error = "；".join(e.error for e in actual.executions if e.error) or None
                # 已接纳的失败也保持原结果；用户可另行接续，不自动重试执行。
                # Accepted failures keep their result; continuation requires a new user action.
                launch.stage = "started"
            except AgentError as exc:
                launch.error = exc.code + " · " + exc.message
            return await self.team.worker.call(self._store_launch, params.task_id, launch)

    def _store_launch(self, task_id: str, launch: TeamDesignLaunch) -> TeamDesignView:
        """更新单次启动记录，不覆盖新输入或图。

        Update one launch without overwriting newer input or graphs.
        """
        view = self.required(task_id)
        view.launches = [x for x in view.launches if x.operation_id != launch.operation_id] + [
            launch
        ]
        return self.write(view)
