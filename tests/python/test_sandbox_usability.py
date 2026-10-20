"""沙箱兼容反馈与环境继承，不提权、不启动外部服务。

Sandbox compatibility feedback and environment inheritance without elevation or external services.
"""

import asyncio
import ctypes
import json
import os
from pathlib import Path

import pytest

from my_agent.context.types import ContextSettings
from my_agent.errors import AgentError
from my_agent.execution.environments import execution_environment, inherited_environment
from my_agent.execution.sandbox import SandboxLease, SandboxRecord
from my_agent.execution.types import BindEnvironmentParams
from my_agent.mcp_client.types import McpParams, McpServer, SaveMcpParams
from my_agent.memory.types import MemorySettings
from my_agent.models.types import ToolResult
from my_agent.runtime.loop import recoverable_tool_error
from tests.python.test_context_memory import KnowledgeModel, run
from tests.python.test_goal_controller import app_at, call, create_session, turn


def test_environment_secrets_and_explicit_project_passthrough(tmp_path, monkeypatch):
    """筛除合成凭据，保留工具配置；项目显式传入只持久化名称。

    Filter synthetic credentials while retaining tool settings and persisting only opted-in names.
    """
    values = {
        "DATABASE_URL": "postgres://fixture:synthetic@localhost/db",
        "CONNECTION_STRING": "Server=localhost;Password=synthetic",
        "SERVICE_AUTH": "synthetic",
        "SERVICE_CREDENTIAL": "synthetic",
        "OPENCODE_API_KEY": "synthetic-app",
        "DEEPSEEK_API_KEY": "synthetic-app",
        "MY_AGENT_INTERNAL": "synthetic",
        "PUBLIC_URL": "https://example.invalid",
        "HTTP_PROXY": "http://localhost:9999",
        "JAVA_HOME": str(tmp_path),
        "CONDA_PREFIX": str(tmp_path),
        "SSH_AUTH_SOCK": "ordinary-socket",
        "PWD": str(tmp_path),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    env = inherited_environment()
    for name in list(values)[:7]:
        assert name not in env
    for name in list(values)[7:]:
        assert env[name] == values[name]
    assert env["PATH"] == os.environ["PATH"]

    async def scenario():
        """通过生产保存与启动快照检查可选传入，不实际启动程序。

        Verify persisted opt-in and launch snapshots without starting a process.
        """
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            session = (await create_session(app, tmp_path / "project")).session
            catalog = await app.worker.call(app.environments.catalog, session.project_id)
            saved = await app.worker.call(
                app.environments.bind,
                BindEnvironmentParams(
                    project_id=session.project_id,
                    environment_id=None,
                    mode="direct",
                    expected_revision=catalog.revision,
                    environment_passthrough=[
                        "DATABASE_URL",
                        "OPENCODE_API_KEY",
                        "MY_AGENT_INTERNAL",
                    ],
                ),
            )
            assert saved.binding.environment_passthrough[0] == "DATABASE_URL"
            view, _, _ = await app.worker.call(app.environments.selected, session.project_id)
            inherited = execution_environment(view)
            assert inherited["DATABASE_URL"] == values["DATABASE_URL"]
            assert "OPENCODE_API_KEY" not in inherited and "MY_AGENT_INTERNAL" not in inherited
            index = app.environments.read().model_dump_json()
            assert "DATABASE_URL" in index and "synthetic" not in index

    asyncio.run(scenario())


def test_sandbox_discovery_and_unstarted_mcp_feedback_continue(tmp_path):
    """目录提前说明兼容性，未派发调用反馈后 Run 仍能正常回答。

    Advertise compatibility before dispatch and continue the Run after unstarted MCP feedback.
    """

    class Model(KnowledgeModel):
        """核对真实请求定义与返回反馈。 Check actual schemas and returned feedback."""

        async def complete(self, **kwargs):
            """先发现能力，再验证未派发的 MCP 不会终止回合。

            Discover capabilities, then check that an undispatched MCP call does not stop the turn.
            """
            self.requests.append(kwargs)
            names = {item["function"]["name"] for item in kwargs["tools"]}
            assert "code_insight" not in names
            assert "git_status" in names
            assert not any(
                item["function"].get("description", "").startswith("local/probe:")
                for item in kwargs["tools"]
            )
            if len(self.requests) == 1:
                return turn(call("discover_tools", names=["code_insight", "git_status"]))
            result = json.loads(
                next(m["content"] for m in reversed(kwargs["messages"]) if m["role"] == "tool")
            )
            if len(self.requests) == 2:
                entries = {item["name"]: item for item in result["catalog"]}
                assert entries["code_insight"]["execution_compatible"] is False
                assert "search" in entries["code_insight"]["alternatives"]
                assert entries["git_status"]["execution_compatible"] is True
                return turn(call("discover_mcp_tools", server_id="local"))
            assert result["code"] == "SANDBOX_ENTRY_UNAVAILABLE"
            return turn(text="Use supported tools and continue.")

    async def scenario():
        """只修改隔离配置；无子进程、网络或真实模型调用。

        Modify isolated configuration only, without subprocesses, network or real models.
        """
        model = Model()
        async with app_at(tmp_path / "data", model) as app:
            session = (await create_session(app, tmp_path / "project")).session
            sid, pid = session.session_id, session.project_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            await app.sessions.contexts.configure(sid, ContextSettings(tool_loading="all"))
            catalog = await app.worker.call(app.environments.catalog, pid)
            await app.worker.call(
                app.environments.bind,
                BindEnvironmentParams(
                    project_id=pid,
                    environment_id=None,
                    mode="sandbox",
                    expected_revision=catalog.revision,
                ),
            )
            mcp = app.sessions.mcp
            await mcp.save(
                SaveMcpParams(
                    project_id=pid,
                    session_id=sid,
                    server=McpServer(
                        server_id="local",
                        name="Fixture",
                        command="never-started.exe",
                        transport="stdio",
                    ),
                )
            )
            catalog = await app.worker.call(mcp.catalog, McpParams(project_id=pid, session_id=sid))
            view = next(item for item in catalog.servers if item.server.server_id == "local")
            assert view.status == "unsupported_execution_mode" and view.error
            # 连接关闭也保留工具选择；沙箱请求不发送其 schema。
            # Retain selected tools without a live connection, but omit incompatible schemas.
            mcp.select_tools(sid, "local", [{"name": "probe", "inputSchema": {"type": "object"}}])
            assert (await run(app, sid, "Inspect available capabilities")).run.status == "completed"
            assert len(model.requests) == 3 and not mcp.connections

    asyncio.run(scenario())
    assert not recoverable_tool_error(
        call("run_command"),
        ToolResult(
            tool_call_id="failure",
            is_error=True,
            content=json.dumps({"code": "SANDBOX_ACCESS_FAILED"}),
        ),
    )


def test_damaged_recovery_record_does_not_skip_other_leases(tmp_path, monkeypatch):
    """坏记录保留并报告，独立的有效记录仍清理；不调用任何 Windows API。

    Preserve/report bad journals while cleaning independent valid leases without Windows APIs.
    """
    bad = tmp_path / "bad.json"
    bad.write_text("{broken", encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text(
        SandboxRecord(name="MyCodingAgent.fixture", principal="*S-1-15-2-1").model_dump_json(),
        encoding="utf-8",
    )
    closed = []

    def initialize(self, directory):
        """测试仅接收恢复记录。 Accept recovery journals only in this fixture."""
        self.directory = directory

    def close(self):
        """记录清理并删除本测试的文件。 Record cleanup and delete this fixture's own journal."""
        closed.append(self.record.name)
        self.path.unlink()

    monkeypatch.setattr(SandboxLease, "__init__", initialize)
    monkeypatch.setattr(SandboxLease, "close", close)
    with pytest.raises(AgentError) as failed:
        SandboxLease.recover(tmp_path)
    assert failed.value.code == "SANDBOX_CLEANUP_FAILED"
    assert "bad.json" in failed.value.message and bad.exists()
    assert closed == ["MyCodingAgent.fixture"] and not good.exists()


def test_ancestor_denial_is_journaled_but_other_failures_propagate(tmp_path, monkeypatch):
    """仅祖先访问拒绝允许继续，先记账及其他真实失败语义保留。

    Continue only after ancestor access denial, retaining write-ahead journals and other failures.
    """
    if os.name != "nt":
        pytest.skip("Windows error causes required")
    lease = object.__new__(SandboxLease)
    lease.path = tmp_path / "lease.json"
    lease.record = SandboxRecord(name="MyCodingAgent.fixture", principal="*S-1-15-2-1")
    ancestor = tmp_path / "ancestor"

    def fail(path, principal, permission, *, inherit):
        """验证授权前已落盘，再模拟 Windows 拒绝。

        Require the journal before simulating a Windows denial.
        """
        assert str(path) in json.loads(lease.path.read_text(encoding="utf-8"))["grants"]
        raise AgentError("SANDBOX_ACCESS_FAILED", "fixture") from ctypes.WinError(5)

    monkeypatch.setattr(lease, "acl", fail)
    lease.grant_ancestor(ancestor)
    saved = json.loads(lease.path.read_text(encoding="utf-8"))
    assert saved["skipped_ancestors"] == {str(ancestor): 5}
    assert saved["traverse_grants"] == [str(ancestor)]

    def io_failure(path, principal, permission, *, inherit):
        """其他授权失败不能变成继续执行。 Other grant failures cannot become success."""
        raise AgentError("SANDBOX_ACCESS_FAILED", "fixture") from ctypes.WinError(1117)

    monkeypatch.setattr(lease, "acl", io_failure)
    with pytest.raises(AgentError):
        lease.grant_ancestor(tmp_path / "other")


def test_cleanup_without_lease_ace_never_writes_dacl(tmp_path, monkeypatch):
    """对受保护卷根撤销不存在的唯一主体时，只查询而不写 DACL。

    Query without writing when the unique lease identity has no ACE on a protected volume root.
    """
    if os.name != "nt":
        pytest.skip("Native Windows ACL query required")
    lease = SandboxLease(tmp_path)

    def unexpected_write(*args):
        """测试不允许修改系统对象。 This check must never modify system objects."""
        raise AssertionError("A missing lease ACE must not trigger a DACL write")

    monkeypatch.setattr(lease.advapi, "SetFileSecurityW", unexpected_write)
    monkeypatch.setattr(lease.advapi, "SetNamedSecurityInfoW", unexpected_write)
    root = Path(Path(os.environ["SystemRoot"]).anchor)
    lease.acl(
        root,
        "*S-1-15-2-135792468-246813579-112233445-556677889-123456789-987654321-192837465",
        None,
        inherit=False,
    )
    lease.close()
