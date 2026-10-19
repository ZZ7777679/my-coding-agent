"""CLI / RPC 共用 M5 工具与生命周期的最小离线验证。

Minimal offline verification of shared M5 tools and lifecycle across CLI/RPC.
"""

import asyncio
import threading
from uuid import uuid4

import pytest

from my_agent.bootstrap import build_sessions
from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import CredentialInfo
from my_agent.runtime.settings import RunLimits
from my_agent.runtime.tools import ToolContext
from my_agent.storage import Storage
from my_agent.worker import BusinessWorker


def test_cli_m5_tools_and_shared_rpc_cleanup(tmp_path, monkeypatch):
    """CLI 提供 M5 工具；RPC 复用实例；一个清理故障不跳过其余资源。

    CLI exposes M5 tools, RPC shares instances, and one cleanup failure cannot skip others.
    """
    credential = ResolvedCredential(
        None, CredentialInfo(env_var="OPENCODE_API_KEY", source="none", present=False)
    )
    storage = Storage(resolve_data_dir(str(tmp_path / "cli-data")))
    worker = BusinessWorker()

    async def scenario():
        """只装配工具与清理，不启动可选进程或模型。

        Compose and close tools without launching optional processes or models.
        """
        service = build_sessions(storage, worker, credential)
        project = tmp_path / "project"
        project.mkdir()
        context = ToolContext(
            project,
            RunLimits.model_validate(DEFAULTS["run"]),
            threading.Event(),
            str(uuid4()),
            str(uuid4()),
            str(uuid4()),
            "normal",
            None,
        )
        names = {tool["function"]["name"] for tool in service.tool_factory(context).definitions()}
        assert {
            "start_terminal",
            "read_terminal",
            "write_terminal",
            "view_image",
            "read_attachment",
            "code_insight",
            "git_status",
            "git_commit",
            "git_diff",
            "git_log",
        }.issubset(names)
        assert service.team is not None and service.team.spaces is service.spaces
        assert service.spaces is not None and service.spaces.tasks is service.tasks
        app = RpcApplication(resolve_data_dir(str(tmp_path / "rpc-data")), credential, None)
        try:
            for name in (
                "team",
                "spaces",
                "tasks",
                "documents",
                "terminals",
                "intelligence",
                "local_git",
                "attachments",
            ):
                assert getattr(app, name) is getattr(app.sessions, name)
        finally:
            await app.close()
        closed = []
        for name in ("terminals", "intelligence", "local_git", "attachments", "mcp"):
            component = getattr(service, name)
            original = component.close

            async def close_component(label=name, close=original):
                """真实清理后注入一个明确故障，核对其余清理仍执行。

                Inject one explicit failure after real cleanup and observe remaining cleanup.
                """
                closed.append(label)
                await close()
                if label == "terminals":
                    raise AgentError("TEST_CLEANUP", "isolated cleanup fault")

            monkeypatch.setattr(component, "close", close_component)
        close_execution, close_model = service.close_execution, service.close_model

        async def close_programs():
            """记录共用执行清理。 Observe shared execution cleanup."""
            closed.append("programs")
            await close_execution()

        async def close_http():
            """记录共用模型连接清理，不发送请求。 Observe connection cleanup without requests."""
            closed.append("http")
            await close_model()

        service.close_execution, service.close_model = close_programs, close_http
        with pytest.raises(AgentError, match="isolated cleanup fault"):
            await service.close()
        assert sorted(closed) == sorted(
            ["terminals", "intelligence", "local_git", "attachments", "mcp", "programs", "http"]
        )

    try:
        with storage.writer():
            storage.initialize()
            asyncio.run(scenario())
    finally:
        worker.close()
