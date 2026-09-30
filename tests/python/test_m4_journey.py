"""M4 空项目联合验收；仅替换模型决策。

Exercise M4 on an empty project, substituting only model decisions.
"""

import asyncio
import json
import os
import re
import socket
import sys
from collections import Counter
from uuid import uuid4

import pytest

from my_agent.memory.types import MemorySettings
from tests.python.test_goal_controller import app_at, call, create_session, turn

PAGE = (
    '<!doctype html><html><meta charset="utf-8"><title>Counter</title>'
    '<p id="n">0</p><button onclick="n.textContent=Number(n.textContent)+1">Add</button></html>'
)


class CounterJourney:
    """完整工具链走真实实现；显式 Review 才切换角色。

    Use real tools throughout; a review role starts only on explicit request.
    """

    def __init__(self, port):
        """保存隔离服务端口和两种角色的步骤。 Track the isolated port and role steps."""
        self.port = port
        self.steps = Counter()
        self.peer = None
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.requests = []

    def check_available(self):
        """不访问模型凭据。 Do not access model credentials."""

    async def complete(self, **kwargs):
        """脚本化调用依然接受生产 schema、执行、存储和 Trace。

        Scripted calls still use production schemas, execution, persistence and trace.
        """
        self.requests.append(kwargs)
        sid = kwargs["session_id"]
        self.steps[sid] += 1
        step = self.steps[sid]
        messages = kwargs["messages"]
        if sid == self.peer:
            if step == 1:
                return turn(call("read_file", path="index.html"))
            return turn(text="Review: add lang=en to html. No file was changed.")
        if step == 1:
            self.started.set()
            await self.release.wait()
            return turn(
                call("load_skill", skill_id="user:counter-check"),
                call(
                    "discover_mcp_tools",
                    server_id="browser",
                    names=[
                        "browser_navigate",
                        "browser_click",
                        "browser_evaluate",
                        "browser_take_screenshot",
                    ],
                ),
            )
        assert "Use a single self-contained HTML page" in messages[0]["content"]
        assert "This session's stage: implement" in messages[0]["content"]

        def browser(name, **args):
            """使用实际发现的 callable 身份，不猜哈希名。

            Use actual discovered callable identities.
            """
            found = next(
                t["function"]
                for t in kwargs["tools"]
                if t["function"]["description"].startswith(f"browser/{name}:")
            )
            return call(found["name"], **args)

        if step == 2:
            return turn(
                call("create_file", path="index.html", content=PAGE),
                call(
                    "start_service",
                    command={
                        "kind": "program",
                        "program": sys.executable,
                        "arguments": ["-m", "http.server", str(self.port), "--bind", "127.0.0.1"],
                    },
                    ready_url=f"http://127.0.0.1:{self.port}",
                ),
            )
        if step == 3:
            return turn(browser("browser_navigate", url=f"http://127.0.0.1:{self.port}"))
        if step == 4:
            snapshot = json.loads(messages[-1]["content"])
            text = "\n".join(c.get("text", "") for c in snapshot["content"])
            ref = re.search(r'button "Add".*?\[ref=([^\]]+)\]', text).group(1)
            return turn(browser("browser_click", element="Add button", target=ref))
        if step == 5:
            return turn(
                browser(
                    "browser_evaluate",
                    function=(
                        "() => { localStorage.setItem('m4','one'); "
                        "return document.querySelector('#n').textContent; }"
                    ),
                ),
                browser("browser_take_screenshot", type="png", filename="counter.png"),
            )
        if step == 6:
            result = next(
                json.loads(m["content"])
                for m in reversed(messages)
                if m["role"] == "tool" and '"browser_evaluate"' in m["content"]
            )
            assert '"1"' in str(result)
            return turn(
                call(
                    "report_work",
                    summary="Counter clicked to 1; screenshot saved.",
                    outcome="complete",
                )
            )
        if step == 7:
            return turn(
                call("edit_file", path="index.html", old_text="<html>", new_text='<html lang="en">')
            )
        return turn(text="Applied the explicitly requested lang correction.")


@pytest.mark.skipif(os.environ.get("MY_AGENT_TEST_MCP") != "1", reason="Opt-in browser journey")
def test_empty_counter_goal_review_and_restart(tmp_path):
    """验证阶段切换、Goal、独立审查、成果和重启清理。

    Verify stage changes, Goal, independent review, artifacts and restart cleanup.
    """

    async def scenario():
        """所有文件、程序、浏览器和协议都使用真实后端。 Use real backends for every capability."""
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        model = CounterJourney(port)
        project = tmp_path / "project"
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, project)
            sid, pid = created.session.session_id, created.task.project_id
            project.joinpath("AGENTS.md").write_text(
                "Keep the page self-contained.", encoding="utf-8"
            )
            await app.dispatch(
                "skills.save",
                {
                    "project_id": pid,
                    "name": "counter-check",
                    "content": (
                        "---\nname: counter-check\ndescription: Verify a counter\n---\n"
                        "Use a single self-contained HTML page. "
                        "Click Add and confirm the number changes.\n"
                    ),
                },
            )
            if executable := os.environ.get("MY_AGENT_TEST_BROWSER"):
                server = (
                    app.sessions.mcp.config()
                    .servers[0]
                    .model_copy(update={"browser_executable": executable})
                )
                await app.dispatch("mcp.save", {"project_id": pid, "server": server.model_dump()})
            goal = await app.dispatch(
                "goals.create",
                {
                    "session_id": sid,
                    "goal_id": str(uuid4()),
                    "objective": "Build and click a counter",
                    "criteria": [
                        {
                            "criterion_id": "counter",
                            "description": "A real click increments the page",
                        }
                    ],
                    "budget": {"max_requests": 12},
                },
            )
            await model.started.wait()
            flow = created.task.workflow.model_copy(deep=True)
            flow.current_stage_id = "implement"
            await app.dispatch(
                "tasks.workflow",
                {
                    "task_id": created.task.task_id,
                    "operation_id": str(uuid4()),
                    "expected_revision": created.task.revision,
                    "workflow": flow.model_dump(),
                },
            )
            model.release.set()
            while True:
                page = await app.dispatch("goals.list", {"session_id": sid})
                current = next(g for g in page.goals if g.goal_id == goal.goal_id)
                if current.status not in {"active", "running"}:
                    break
                await asyncio.sleep(0.05)
            assert current.status == "completed", current
            assert project.joinpath("index.html").read_text(encoding="utf-8") == PAGE
            task = await app.dispatch("tasks.get", {"task_id": created.task.task_id})
            assert task.fields.status != "completed"
            peer = await app.dispatch(
                "sessions.create",
                {
                    "project_id": pid,
                    "task_id": task.task_id,
                    "model_id": "glm-5.3-flash",
                    "role": "Review",
                    "scope": "Read index.html; no writes",
                },
            )
            model.peer = peer.session_id
            await app.sessions.memory.configure(peer.session_id, MemorySettings(automatic=False))
            await app.dispatch(
                "collaboration.connect",
                {
                    "source_session_id": sid,
                    "target_session_id": peer.session_id,
                    "scope": "Review index.html without edits",
                    "mode": "plan",
                },
            )
            request = await app.dispatch(
                "collaboration.request",
                {
                    "source_session_id": sid,
                    "target_session_id": peer.session_id,
                    "objective": "Review index.html",
                    "mode": "plan",
                    "operation_id": str(uuid4()),
                },
            )
            while True:
                peers = await app.dispatch("collaboration.list", {"session_id": sid})
                reply = next(r for r in peers.requests if r.request_id == request.request_id)
                if reply.status in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.05)
            assert reply.status == "completed"
            assert project.joinpath("index.html").read_text(encoding="utf-8") == PAGE
            await app.sessions.start(
                sid, str(uuid4()), "Apply the review's lang=en correction.", None, mode="normal"
            )
            await app.sessions.active_for(sid).task
            assert '<html lang="en">' in project.joinpath("index.html").read_text(encoding="utf-8")
            trace = await app.dispatch("trace.list", {"session_id": sid, "limit": 100})
            assert any(i.title.startswith("browser/browser_click") for i in trace.items)
            assert any(i.goal_id == goal.goal_id for i in trace.items)
            shot = next(
                i for i in trace.items if i.title.startswith("browser/browser_take_screenshot")
            )
            detail = await app.dispatch("trace.detail", {"session_id": sid, "seq": shot.seq})
            assert any(link.kind == "image" for link in detail.links)
        async with app_at(tmp_path / "data", None) as restored:
            task = await restored.dispatch("tasks.get", {"task_id": created.task.task_id})
            assert task.workflow.current_stage_id == "implement"
            assert (await restored.dispatch("trace.list", {"session_id": sid})).items
            catalog = await restored.dispatch("mcp.list", {"project_id": pid, "session_id": sid})
            assert all(s.status == "not_connected" for s in catalog.servers)
            assert "counter.png" in catalog.artifacts
            assert not restored.sessions.mcp.connections

    asyncio.run(asyncio.wait_for(scenario(), 120))
