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
        await kwargs["on_text"]("main.py:2 returns 42")
        return ModelTurn(
            text="main.py:2 returns 42",
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
    service = SessionService(SessionStore(storage), projects, worker, lambda: model)
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
                first = await service.start(session.session_id, operation, "Find the answer", None)
                await service.active.task
                duplicate = await service.start(
                    session.session_id, operation, "Find the answer", None
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
                reloaded = SessionService(SessionStore(storage), projects, worker, lambda: model)
                recovered = await reloaded.view(session.session_id)
                assert recovered.entries == result.entries
                assert recovered.summary.run.input_tokens == 40
                assert (project / "main.py").read_text() == "def answer():\n    return 42\n"
        finally:
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
                task = service.active.task
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
                await service.active.task
                final = await service.view(next_session.session_id)
                assert final.summary.run.status == "budget_exceeded"
                assert model.calls == 1 and final.summary.can_continue
        finally:
            await service.close()
            worker.close()

    asyncio.run(scenario())


def test_read_policy_and_search(tmp_path, monkeypatch):
    """共同过滤、目录越界、示例密钥与搜索后备。

    Check shared filters, traversal and search fallback.
    """
    (tmp_path / "main.py").write_text("alpha\nbeta alpha\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=sentinel", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET=placeholder", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored/hidden.py").write_text("alpha", encoding="utf-8")
    limits = RunLimits.model_validate(DEFAULTS["run"])
    tools = ReadTools(tmp_path, limits, threading.Event())
    for path, code in (
        ("../outside", "PATH_DENIED"),
        ("C:/Windows", "PATH_DENIED"),
        (".env", "SENSITIVE_FILE"),
        ("ignored/hidden.py", "FILE_IGNORED"),
    ):
        result = tools._execute(
            ToolCall(tool_call_id="t", name="read_file", arguments={"path": path})
        )
        assert result.is_error and json.loads(result.content)["code"] == code
    listing = json.loads(
        tools._execute(ToolCall(tool_call_id="t", name="list_files", arguments={})).content
    )
    assert ".env.example" in listing["files"] and ".env" not in listing["files"]
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
    """真实链接边界与 CLI 共用闭环。 Check real link boundaries and the shared CLI loop."""
    from my_agent.cli import app

    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("must-not-read", encoding="utf-8")
    link = project / "external"
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    tools = ReadTools(project, RunLimits.model_validate(DEFAULTS["run"]), threading.Event())
    denied = tools._execute(
        ToolCall(tool_call_id="t", name="read_file", arguments={"path": "external/secret.txt"})
    )
    assert denied.is_error and json.loads(denied.content)["code"] == "PATH_DENIED"
    listing = tools._execute(ToolCall(tool_call_id="t", name="list_files", arguments={}))
    assert "secret.txt" not in listing.content
    (project / "main.py").write_text("def answer():\n    return 42\n", encoding="utf-8")

    def compose(storage, worker, credential):
        """只替换模型，CLI 仍走共享服务。 Replace only the model; keep the shared service."""
        return SessionService(SessionStore(storage), ProjectService(storage), worker, FakeModel)

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
    assert (outside / "secret.txt").read_text() == "must-not-read"
