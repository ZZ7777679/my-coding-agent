"""M1 核心的集中最小证据。 Focused M1 core behavior evidence."""

import asyncio
import json
import os
import shutil
import subprocess
import threading
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from my_agent.config import DEFAULTS, load_config, resolve_data_dir
from my_agent.errors import AgentError
from my_agent.models.types import ModelTurn, TokenUsage, ToolCall
from my_agent.projects import ProjectService
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.service import SessionService
from my_agent.sessions.store import SessionStore
from my_agent.sessions.types import RequestStarted
from my_agent.storage import Storage
from my_agent.tools.read_only import ReadTools
from my_agent.worker import BusinessWorker


class FakeModel:
    """只有测试注入的模型，验证工具回传和真实读取内容。

    Injected model verifying actual file results.
    """

    def __init__(self, delay=False):
        """记录调用次数，可模拟长等待。 Track calls and optionally simulate a long wait."""
        self.calls = 0
        self.delay = delay
        self.started = asyncio.Event()
        self.closed = False

    def check_available(self):
        """测试不依赖凭据。 Tests require no credentials."""
        return None

    async def complete(self, **kwargs):
        """第一次请求读文件，下一次核验工具输出再回答。 Request a file, then verify its output."""
        self.calls += 1
        self.started.set()
        if self.delay:
            try:
                await asyncio.Event().wait()
            finally:
                self.closed = True
        if self.calls == 1:
            call = ToolCall(tool_call_id="read-1", name="read_file", arguments={"path": "main.py"})
            return ModelTurn(
                text="",
                tool_calls=[call],
                native={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "read-1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path":"main.py"}'},
                        }
                    ],
                },
                usage=TokenUsage(input_tokens=10, output_tokens=5),
            )
        assert "return 42" in kwargs["messages"][-1]["content"]
        await kwargs["on_reasoning"]("先读取入口。")
        await kwargs["on_reasoning"]("再核对返回值。")
        await kwargs["on_text"]("main.py:2 returns 42")
        return ModelTurn(
            text="main.py:2 returns 42",
            reasoning="先读取入口。再核对返回值。",
            tool_calls=[],
            native={
                "role": "assistant",
                "content": "main.py:2 returns 42",
                "reasoning_content": "private continuation",
            },
            usage=TokenUsage(input_tokens=30, output_tokens=10),
        )


def setup(tmp_path, model):
    """创建独立项目与应用数据。 Create isolated project and application data."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    worker = BusinessWorker()
    projects = ProjectService(storage)
    service = SessionService(
        SessionStore(storage),
        projects,
        worker,
        lambda: model,
        tool_factory=lambda c: ReadTools(c.root, c.limits, c.stop),
    )
    return project, storage, worker, projects, service


def test_roundtrip_idempotency_and_restart(tmp_path):
    """一个场景核对闭环、幂等、原生字段隔离与重启。 Check loop, idempotency, privacy and restart."""

    async def scenario():
        """用同一共享服务执行并重新加载事实。

        Execute and reload facts through the shared service.
        """
        model = FakeModel()
        project, storage, worker, projects, service = setup(tmp_path, model)
        try:
            with storage.writer():
                view = projects.open(path=str(project))
                session = await service.create(view.active_project.project_id, "glm-5.3-flash")
                operation = str(uuid4())
                limits = load_config(storage.location).run.model_copy(
                    update={"max_context_bytes": 20000, "max_output_tokens": 100000}
                )
                first = await service.start(
                    session.session_id, operation, "Find the answer", limits
                )
                await service.active_for(session.session_id).task
                duplicate = await service.start(
                    session.session_id, operation, "Find the answer", limits
                )
                assert duplicate.run.run_id == first.run.run_id
                assert model.calls == 2
                with pytest.raises(AgentError, match="不同输入"):
                    await service.start(session.session_id, operation, "different", None)
                result = await service.view(session.session_id)
                assert result.summary.run.status == "completed"
                assert result.summary.can_continue
                assert "private continuation" not in result.model_dump_json()
                assert any(
                    entry.result and "return 42" in entry.result.content for entry in result.entries
                )
                reloaded = SessionService(
                    SessionStore(storage),
                    projects,
                    worker,
                    lambda: model,
                    tool_factory=lambda c: ReadTools(c.root, c.limits, c.stop),
                )
                recovered = await reloaded.view(session.session_id)
                assert recovered.entries == result.entries
                assert recovered.summary.run.input_tokens == 40
                assert (project / "main.py").read_text() == "def answer():\n    return 42\n"
        finally:
            await service.close()
            worker.close()

    asyncio.run(scenario())


def test_read_field_correction_continues_same_run(tmp_path):
    """字段名和类型反馈交回模型，同一 Run 修正后完成。

    Return field/type feedback to the model and complete the same run after correction.
    """
    from tests.python.test_goal_controller import call, turn

    class CorrectingModel(FakeModel):
        """按具体反馈改正读取参数，不伪造工具结果。

        Correct read arguments from concrete feedback without inventing tool results.
        """

        async def complete(self, **kwargs):
            """依次误用字段、误用类型、实际读取并回答。

            Try a wrong field/type, then read the actual file and answer.
            """
            self.calls += 1
            if self.calls == 1:
                return turn(call("read_file", path="main.py", limit="50"))
            message = kwargs["messages"][-1]["content"]
            if self.calls == 2:
                assert "limit: Extra inputs" in message
                return turn(call("read_file", path="main.py", lines="50"))
            if self.calls == 3:
                assert "lines: Input should be a valid integer" in message
                return turn(call("read_file", path="main.py", lines=50))
            assert self.calls == 4 and "return 42" in message
            return turn(text="The answer is 42.")

    async def scenario():
        """仅替换模型，保留生产工具与终态存储。

        Substitute only the model while retaining production tools and terminal storage.
        """
        model = CorrectingModel()
        project, storage, worker, projects, service = setup(tmp_path, model)
        try:
            with storage.writer():
                view = projects.open(path=str(project))
                session = await service.create(view.active_project.project_id, "glm-5.3-flash")
                await service.start(session.session_id, str(uuid4()), "Read the answer", None)
                await service.active_for(session.session_id).task
                result = await service.view(session.session_id)
                assert model.calls == 4 and result.summary.run.status == "completed"
                assert result.summary.run.tools == 3
        finally:
            await service.close()
            worker.close()

    asyncio.run(scenario())


def test_model_selection_mid_request_and_reasoning_snapshots(tmp_path):
    """切换保留在途请求，后续模型与思考快照可跨重启恢复。

    Keep the admitted model while switching subsequent calls and preserving reasoning history.
    """

    class SwitchingModel(FakeModel):
        """使用显式门闩观察请求与分片边界。 Observe request and display boundaries with latches."""

        def __init__(self):
            """只保存本地控制状态。 Store local control state only."""
            super().__init__()
            self.admitted = asyncio.Event()
            self.release = asyncio.Event()
            self.preview = asyncio.Event()
            self.finish = asyncio.Event()
            self.models = []

        async def complete(self, **kwargs):
            """暂停首请求与下一请求首个思考片段，不使用时间猜测。

            Pause the first request and the next request's first reasoning fragment.
            """
            self.models.append(kwargs["model_id"])
            if not self.calls:
                self.admitted.set()
                await self.release.wait()
            else:
                deliver = kwargs["on_reasoning"]

                async def observed(delta):
                    """交付片段后等待读取快照。

                    Wait for a snapshot after delivering the fragment.
                    """
                    await deliver(delta)
                    self.preview.set()
                    await self.finish.wait()

                kwargs["on_reasoning"] = observed
            return await super().complete(**kwargs)

    async def scenario():
        """使用真实会话存储与工具，模型仅作替身。

        Use actual storage and tools with a model double.
        """
        model = SwitchingModel()
        _, storage, worker, projects, service = setup(tmp_path, model)
        signals = []
        service.subscribe(signals.append)
        try:
            with storage.writer():
                project = projects.open(path=str(tmp_path / "project"))
                session = await service.create(project.active_project.project_id, "glm-5.3-flash")
                await service.start(session.session_id, str(uuid4()), "Find the answer", None)
                active = service.active_for(session.session_id)
                await model.admitted.wait()
                operation = str(uuid4())
                selected = await service.select_model(
                    session.session_id, operation, "deepseek-v4.1-flash"
                )
                assert selected.model_id == "deepseek-v4.1-flash"
                await service.select_model(session.session_id, operation, "deepseek-v4.1-flash")
                model.release.set()
                await model.preview.wait()
                live = await service.view(session.session_id)
                assert live.stream_reasoning == "先读取入口。" and live.stream_text == ""
                assert live.stream_model_id == "deepseek-v4.1-flash"
                model.finish.set()
                await active.task
                result = await service.view(session.session_id)
                assert result.summary.run.status == "completed"
                assert model.models == ["glm-5.3-flash", "deepseek-v4.1-flash"]
                assistant = [item for item in result.entries if item.kind == "assistant"]
                assert assistant[-1].reasoning == "先读取入口。再核对返回值。"
                assert assistant[-1].model_id == "deepseek-v4.1-flash"
                assert "private continuation" not in result.model_dump_json()
                deltas = [
                    item for item in signals if item.kind in {"text.delta", "reasoning.delta"}
                ]
                assert [item.delta_index for item in deltas] == [1, 2, 3]
                log = service.store.load(session.session_id)
                assert [
                    f.data.model_id for f in log.facts if isinstance(f.data, RequestStarted)
                ] == model.models
                reloaded = SessionService(
                    SessionStore(storage),
                    projects,
                    worker,
                    lambda: model,
                    tool_factory=lambda c: ReadTools(c.root, c.limits, c.stop),
                )
                recovered = await reloaded.view(session.session_id)
                assert recovered.entries == result.entries
                assert recovered.summary.model_id == "deepseek-v4.1-flash"
        finally:
            model.release.set()
            model.finish.set()
            await service.close()
            worker.close()

    asyncio.run(scenario())


def test_cancel_cleans_up_and_budget_prevents_next_request(tmp_path):
    """取消清理完成才结束；请求预算到达不再发请求。

    Reap cancellation and enforce request budgets.
    """

    async def scenario():
        """复用隔离数据核对取消与预算终态。 Verify cancellation and budget terminal states."""
        model = FakeModel(delay=True)
        project, storage, worker, projects, service = setup(tmp_path, model)
        try:
            with storage.writer():
                project_id = projects.open(path=str(project)).active_project.project_id
                session = await service.create(project_id, "glm-5.3-flash")
                started = await service.start(session.session_id, str(uuid4()), "Read", None)
                task = service.active_for(session.session_id).task
                await model.started.wait()
                stopped = await service.cancel(started.run.run_id)
                assert stopped.run.status == "stopping"
                await task
                final = await service.view(session.session_id)
                assert model.closed and model.calls == 1
                assert final.summary.run.status == "cancelled" and final.summary.can_continue
                model.delay = False
                model.calls = 0
                next_session = await service.create(project_id, "glm-5.3-flash")
                limits = load_config(storage.location).run.model_copy(update={"max_requests": 1})
                await service.start(next_session.session_id, str(uuid4()), "Read", limits)
                await service.active_for(next_session.session_id).task
                final = await service.view(next_session.session_id)
                assert final.summary.run.status == "budget_exceeded"
                assert model.calls == 1 and final.summary.can_continue
        finally:
            await service.close()
            worker.close()

    asyncio.run(scenario())


def test_read_policy_and_search(tmp_path, monkeypatch):
    """发现过滤不阻断定向读取，搜索缺少 rg 时保留后备。

    Discovery filters do not block targeted reads; search retains its rg fallback.
    """
    (tmp_path / "main.py").write_text("alpha\nbeta alpha\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=sentinel", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET=placeholder", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored/\n#" + "padding" * 10000, encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored/hidden.py").write_text("alpha", encoding="utf-8")
    limits = RunLimits.model_validate(DEFAULTS["run"])
    tools = ReadTools(tmp_path, limits, threading.Event())
    for path, code in (
        ("../missing", "FILE_NOT_FOUND"),
        ("CON", "PATH_DENIED"),
    ):
        result = tools._execute(
            ToolCall(tool_call_id="t", name="read_file", arguments={"path": path})
        )
        assert result.is_error and json.loads(result.content)["code"] == code
    listing = json.loads(
        tools._execute(ToolCall(tool_call_id="t", name="list_files", arguments={})).content
    )
    assert ".env.example" in listing["files"] and ".env" in listing["files"]
    assert "ignored/hidden.py" not in listing["files"]
    for path in (".env", "ignored/hidden.py", str(tmp_path / "main.py")):
        result = tools._execute(
            ToolCall(tool_call_id="read", name="read_file", arguments={"path": path})
        )
        assert not result.is_error
    actual = json.loads(
        tools._execute(
            ToolCall(tool_call_id="t", name="search", arguments={"query": "alpha", "limit": 1})
        ).content
    )
    assert actual["backend"] == ("rg" if shutil.which("rg") else "python")
    assert actual["truncated"] and actual["matches"][0]["line"] == 1
    monkeypatch.setattr("my_agent.tools.read_only.shutil.which", lambda name: None)
    result = json.loads(
        tools._execute(
            ToolCall(tool_call_id="t", name="search", arguments={"query": "alpha", "limit": 1})
        ).content
    )
    assert result["backend"] == "python" and result["truncated"] and len(result["matches"]) == 1
    result = json.loads(
        tools._execute(
            ToolCall(tool_call_id="t", name="search", arguments={"query": "no-such-text"})
        ).content
    )
    assert result["matches"] == [] and not result["truncated"]


def test_corrupt_tail_preserved_and_old_config_defaults(tmp_path):
    """损坏尾部保留，旧配置补预算且保存模型不丢预算。

    Preserve corrupt tails and old config compatibility.
    """

    async def scenario():
        """新会话仍可创建，不自动修复损坏记录。

        Keep new sessions usable without automatic repair.
        """
        project, storage, worker, projects, service = setup(tmp_path, FakeModel())
        try:
            with storage.writer():
                view = projects.open(path=str(project))
                session = await service.create(view.active_project.project_id, "glm-5.3-flash")
                path = service.store.path(session.session_id)
                with path.open("ab") as stream:
                    stream.write(b'{"broken":')
                before = path.read_bytes()
                result = await service.view(session.session_id)
                assert not result.summary.can_continue and result.summary.issue
                await service.create(view.active_project.project_id, "deepseek-v4.1-flash")
                assert path.read_bytes() == before
                config_path = storage.root / "config.toml"
                config_path.write_text('[model]\nmodel_id="glm-5.3-flash"\n', encoding="utf-8")
                config = load_config(storage.location)
                assert config.run.max_requests == 25
                limits = config.run.model_copy(update={"max_requests": 7})
                storage.save_model("deepseek-v4.1-flash", limits)
                storage.save_model("glm-5.3-flash")
                assert load_config(storage.location).run.max_requests == 7
        finally:
            await service.close()
            worker.close()

    asyncio.run(scenario())


def test_junction_targets_and_cli_shared_service(tmp_path, monkeypatch):
    """显式链接读取与 CLI 共用闭环。 Check explicit linked reads and the shared CLI loop."""
    from my_agent.cli import app

    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (outside / "fixture.txt").write_text("external-fixture", encoding="utf-8")
    link = project / "external"
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    tools = ReadTools(project, RunLimits.model_validate(DEFAULTS["run"]), threading.Event())
    read = tools._execute(
        ToolCall(tool_call_id="t", name="read_file", arguments={"path": "external/fixture.txt"})
    )
    assert not read.is_error and "external-fixture" in read.content
    listing = tools._execute(ToolCall(tool_call_id="t", name="list_files", arguments={}))
    assert "fixture.txt" not in listing.content
    (project / "main.py").write_text("def answer():\n    return 42\n", encoding="utf-8")

    def compose(storage, worker, credential):
        """只替换模型，CLI 仍走共享服务。 Replace only the model; keep the shared service."""
        return SessionService(
            SessionStore(storage),
            ProjectService(storage),
            worker,
            FakeModel,
            tool_factory=lambda c: ReadTools(c.root, c.limits, c.stop),
        )

    monkeypatch.setattr("my_agent.cli.build_sessions", compose)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path / "data"),
            "ask",
            "Find answer",
            "--project",
            str(project),
            "--run-json",
            '{"max_requests":2}',
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    view = json.loads(result.stdout.splitlines()[-1])
    assert view["summary"]["run"]["status"] == "completed"
    assert view["summary"]["run"]["limits"]["max_requests"] == 2
    assert "private continuation" not in result.stdout
    mismatch = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path / "data"),
            "--model",
            "deepseek-v4.1-flash",
            "ask",
            "continue",
            "--session",
            view["summary"]["session_id"],
            "--json",
        ],
    )
    assert mismatch.exit_code == 1
    assert json.loads(mismatch.stdout)["error"]["code"] == "SESSION_MODEL_MISMATCH"
    assert (outside / "fixture.txt").read_text() == "external-fixture"
