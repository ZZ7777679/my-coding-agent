"""M6 请求定义、发现和持久化的定向检查。 M6 checks for request schemas and durable discovery."""

import asyncio
import copy
from uuid import uuid4

import pytest

from my_agent.checkpoints.types import RestoreCheckpointParams
from my_agent.context.service import SUMMARY_PROMPT
from my_agent.context.types import ContextSettings
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.skills.types import SaveSkillParams
from tests.python.test_context_memory import KnowledgeModel, run
from tests.python.test_goal_controller import app_at, call, create_session, turn


def test_discovery_loads_and_unloads_without_extra_model_router(tmp_path):
    """真实工具链按需装配，分页目录不隐式加载，选择跨 Run 保留。

    Exercise real discovery, non-loading catalog pages and selection persistence across runs.
    """

    class Model(KnowledgeModel):
        """记录真实定义并请求两种发现工具。 Capture actual schemas and request both catalogs."""

        async def complete(self, **kwargs):
            """逐次验证已装配定义与 Skill 内容。 Check schemas and Skill content at each step."""
            self.requests.append({**kwargs, "messages": copy.deepcopy(kwargs["messages"])})
            names = {item["function"]["name"] for item in kwargs["tools"]}
            system = kwargs["messages"][0]["content"]
            step = len(self.requests)
            assert {"read_file", "run_command", "discover_tools", "discover_skills"} <= names
            if step == 1:
                assert "code_insight" not in names
                assert "SECRET_CATALOG_DESCRIPTION" not in system
                return turn(call("discover_tools", names=["code_insight"]))
            assert ("code_insight" in names) == (step < 6)
            if step == 2:
                return turn(call("discover_skills", query="quartz", limit=1))
            if step == 3:
                return turn(call("load_skill", skill_id="user:quartz"))
            if step == 4:
                assert "QUARTZ_BODY" in system
                return turn(text="Loaded")
            if step == 5:
                return turn(call("discover_tools", unload=["code_insight"]))
            return turn(text="Done")

    async def scenario():
        """使用隔离资源和生产请求装配。 Use isolated resources and production assembly."""
        model = Model()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            await app.sessions.contexts.configure(sid, ContextSettings(skill_catalog_tokens=0))
            await app.worker.call(
                app.sessions.skills.save,
                SaveSkillParams(
                    name="quartz",
                    content=(
                        "---\nname: quartz\ndescription: SECRET_CATALOG_DESCRIPTION"
                        "\n---\nQUARTZ_BODY"
                    ),
                ),
            )
            assert (await run(app, sid, "Use quartz")).run.status == "completed"
            state = app.sessions.contexts.store.read(sid)
            assert state.settings.active_tools == ["code_insight"]
            assert (await run(app, sid, "Unload extension")).run.status == "completed"
            assert app.sessions.contexts.store.read(sid).settings.active_tools == []
            assert len(model.requests) == 6

    asyncio.run(scenario())


@pytest.mark.parametrize("fail", [False, True])
def test_background_compaction_keeps_foreground_and_new_settings(tmp_path, fail):
    """慢摘要不阻塞正常回复，失败独立显示，采用时保留新尾部与设置。

    Slow summaries do not block replies; failures stay separate and adoption retains tail/settings.
    """

    class BackgroundModel(KnowledgeModel):
        """用门闩固定前台与整理时序。 Coordinate foreground and maintenance with latches."""

        def __init__(self):
            """仅控制摘要，普通回复保持可运行。 Gate summaries only, keeping replies available."""
            super().__init__()
            self.summary_started = asyncio.Event()
            self.release = asyncio.Event()

        async def complete(self, **kwargs):
            """记录请求并延后摘要结果。 Capture requests and defer summary completion."""
            if kwargs["messages"][0]["content"] == SUMMARY_PROMPT:
                self.summary_started.set()
                await self.release.wait()
                if fail:
                    raise AgentError("MODEL_STREAM_ERROR", "Isolated summary failure")
            return await super().complete(**kwargs)

    async def scenario():
        """使用真实后台调度和持久化。 Use production background scheduling and storage."""
        model = BackgroundModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            contexts = app.sessions.contexts
            await contexts.configure(sid, ContextSettings(automatic=False))
            model.long = True
            await run(app, sid, "Earlier long task")
            model.long = False
            policy = ContextSettings(
                background_compaction=True, auto_trigger_tokens=1, keep_recent_tokens=0
            )
            await contexts.configure(sid, policy)
            try:
                summary = await run(app, sid, "NEW_TAIL")
                assert summary.run.status == "completed"
                await asyncio.wait_for(model.summary_started.wait(), 5)
                assert not contexts.jobs[sid].done()
                changed = policy.model_copy(
                    update={"automatic": False, "active_tools": ["code_insight"]}
                )
                await contexts.configure(sid, changed)
                model.release.set()
                await asyncio.gather(contexts.jobs[sid], return_exceptions=True)
                state = contexts.store.read(sid)
                assert state.settings == changed
                assert state.job.status == ("failed" if fail else "ready")
                assert state.job.background and state.job.run_id is None
                assert (await run(app, sid, "After maintenance")).run.status == "completed"
                assert "NEW_TAIL" in str(model.requests[-1]["messages"])
                assert contexts.store.read(sid).job.status == ("failed" if fail else "adopted")
            finally:
                model.release.set()

    asyncio.run(scenario())


def test_cross_model_history_keeps_pairs_without_foreign_native_fields(tmp_path):
    """跨模型只发送公开历史，切回来源模型仍保留其原生接续。

    Project public history across models while retaining native fields for the original model.
    """

    class NativeModel(KnowledgeModel):
        """保留每次实际输入并返回可识别原生字段。

        Capture inputs and return identifiable native data.
        """

        async def complete(self, **kwargs):
            """公开回答与私有接续分开。 Separate public answers from native continuation."""
            self.requests.append({**kwargs, "messages": copy.deepcopy(kwargs["messages"])})
            result = (
                turn(call("read_file", path="sample.txt"))
                if len(self.requests) == 1
                else turn(text="Public result")
            )
            result.native["reasoning_content"] = "native-" + kwargs["model_id"]
            return result

    async def scenario():
        """使用同一会话的真实模型选择和装配。 Use real selection and assembly in one session."""
        model = NativeModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            (tmp_path / "project" / "sample.txt").write_text("PAIR_CONTENT", encoding="utf-8")
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            await run(app, sid, "First")
            await app.sessions.select_model(sid, str(uuid4()), "deepseek-v4.1-flash")
            await run(app, sid, "Second")
            history = [m for m in model.requests[-1]["messages"] if m["role"] == "assistant"]
            assert len(history) == 2 and all("reasoning_content" not in m for m in history)
            tool_id = history[0]["tool_calls"][0]["id"]
            results = [m for m in model.requests[-1]["messages"] if m["role"] == "tool"]
            assert len(results) == 1 and results[0]["tool_call_id"] == tool_id
            assert "PAIR_CONTENT" in results[0]["content"]
            assert history[1] == {"role": "assistant", "content": "Public result"}
            await app.sessions.select_model(sid, str(uuid4()), "glm-5.3-flash")
            await run(app, sid, "Third")
            history = [m for m in model.requests[-1]["messages"] if m["role"] == "assistant"]
            assert history[0]["reasoning_content"] == "native-glm-5.3-flash"
            assert history[1]["reasoning_content"] == "native-glm-5.3-flash"
            assert "reasoning_content" not in history[2]
            log = await app.sessions._load(sid)
            original = [m for m in log.context()[0] if m["role"] == "assistant"]
            assert original[2]["reasoning_content"] == "native-deepseek-v4.1-flash"

    asyncio.run(scenario())


def test_rewind_cancels_pending_background_summary_and_preserves_new_branch(tmp_path):
    """回退收回旧前缀整理，迟到摘要不能进入新分支。

    Rewind cancels old-prefix maintenance so late summaries cannot enter the new branch.
    """

    class WaitingModel(KnowledgeModel):
        """只等待摘要，普通回答正常结束。 Wait only for summaries, not ordinary answers."""

        def __init__(self):
            """记录摘要启动与取消的真实时序。 Track summary start and cancellation."""
            super().__init__()
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def complete(self, **kwargs):
            """旧整理必须通过任务取消结束。 Old maintenance must terminate through cancellation."""
            if kwargs["messages"][0]["content"] == SUMMARY_PROMPT:
                self.started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    self.cancelled.set()
                    raise
            return await super().complete(**kwargs)

    async def scenario():
        """真实回退 RPC 接续当前窗口，保留原始事实供历史查看。

        Use real rollback RPC and verify effective context alongside retained raw history.
        """
        model = WaitingModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            contexts = app.sessions.contexts
            await contexts.configure(sid, ContextSettings(automatic=False))
            model.long = True
            await run(app, sid, "EARLIER_LONG_TASK")
            model.long = False
            await contexts.configure(
                sid,
                ContextSettings(
                    background_compaction=True, auto_trigger_tokens=1, keep_recent_tokens=0
                ),
            )
            assert (await run(app, sid, "ABANDON_THIS_REQUEST")).run.status == "completed"
            await asyncio.wait_for(model.started.wait(), 5)
            points = await app.dispatch("checkpoints.list", {"session_id": sid})
            point = next(p for p in points.checkpoints if p.title == "ABANDON_THIS_REQUEST")
            result = await app.dispatch(
                "checkpoints.restore",
                RestoreCheckpointParams(
                    session_id=sid,
                    checkpoint_id=point.checkpoint_id,
                    operation_id=str(uuid4()),
                    mode="conversation",
                ).model_dump(),
            )
            assert result.rewound and model.cancelled.is_set()
            assert sid not in contexts.jobs
            state = contexts.store.read(sid)
            assert state.job is None and state.checkpoints == []
            await contexts.configure(sid, ContextSettings(automatic=False))
            assert (await run(app, sid, "NEW_BRANCH_REQUEST")).run.status == "completed"
            assert "ABANDON_THIS_REQUEST" not in str(model.requests[-1]["messages"])
            assert "NEW_BRANCH_REQUEST" in str(model.requests[-1]["messages"])
            assert "ABANDON_THIS_REQUEST" in str((await app.sessions._load(sid)).facts)

    asyncio.run(scenario())
