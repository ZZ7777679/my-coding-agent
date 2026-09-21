"""隔离空项目的 M3 联合流程，只替换模型决策。

Exercise the M3 journey on an empty project, replacing only model decisions.
"""

import asyncio
import json
import sys
from collections import Counter
from uuid import uuid4

from my_agent.context.service import SUMMARY_PROMPT
from my_agent.memory.types import MemorySettings
from tests.python.test_context_memory import run
from tests.python.test_goal_controller import app_at, call, create_session, turn

PAGE = '<!doctype html><meta charset="utf-8"><output id="n">0</output>'
PAGE += '<button onclick="n.textContent=Number(n.textContent)+1">Add</button>'
RESET = '<button onclick="n.textContent=0">Reset</button>'


class JourneyModel:
    """脚本化决定通过生产工具落盘、执行和协作。

    Scripted decisions use production tools for files, execution and collaboration.
    """

    def __init__(self):
        """记录实际请求与各角色进度。 Track real requests and each role's progress."""
        self.source = self.peer = self.fresh = None
        self.steps = Counter()
        self.requests = []
        self.outputs = []

    def check_available(self):
        """本地场景不读取密钥。 Local scenarios never read keys."""

    async def complete(self, **kwargs):
        """按角色返回一次明确工具动作，工具结果来自真实运行。

        Return one explicit action per role; tools produce the actual results.
        """
        self.requests.append(kwargs)
        messages = kwargs["messages"]
        sid = kwargs["session_id"]
        if messages[0]["content"] == SUMMARY_PROMPT:
            return turn(
                text="Created index.html, an offline counter. Preserve the newest reset request."
            )
        if sid == self.fresh:
            assert "Use offline bundled assets" in messages[0]["content"]
            return turn(text="The saved project preference applies to this new conversation.")
        self.steps[sid] += 1
        step = self.steps[sid]
        if messages[-1]["role"] == "tool":
            result = json.loads(messages[-1]["content"])
            assert not result.get("code"), result
            self.outputs.append(result)
        if sid == self.peer:
            if step == 1:
                assert "Reset added" in messages[0]["content"]
                return turn(call("read_file", path="index.html"))
            if step == 2:
                return turn(
                    call(
                        "create_file",
                        path="README.md",
                        content="Open index.html offline. Add increments; Reset returns to zero.",
                    )
                )
            return turn(text="README.md reflects Add and Reset.")
        if sid != self.source:
            snapshot = json.dumps(messages, ensure_ascii=False)
            assert "Source session" in snapshot
            assert "private-native-sentinel" not in snapshot
            if step == 1:
                return turn(call("read_file", path="README.md"))
            return turn(text="Read the actual README; both buttons are described.")
        if step == 1:
            result = turn(call("create_file", path="index.html", content=PAGE))
            result.native["reasoning_content"] = "private-native-sentinel"
            return result
        if step == 2:
            return turn(text="Counter created. " + "Old exploration details. " * 80)
        if step == 3:
            assert any(
                "Earlier conversation summary" in str(msg.get("content")) for msg in messages
            )
            return turn(call("edit_file", path="index.html", old_text=PAGE, new_text=PAGE + RESET))
        if step == 4:
            return turn(
                call(
                    "run_command",
                    command={
                        "kind": "program",
                        "program": sys.executable,
                        "arguments": [
                            "-c",
                            "from pathlib import Path; "
                            "assert 'Reset' in Path('index.html').read_text(); "
                            "print('reset present')",
                        ],
                    },
                )
            )
        if step == 5:
            return turn(
                call(
                    "request_collaboration",
                    target_session_id=self.peer,
                    objective="Document both buttons in README.md",
                    mode="normal",
                )
            )
        if step == 6:
            return turn(call("read_collaboration", request_id=result["request_id"]))
        if step == 7:
            assert result["status"] == "completed"
            return turn(
                call(
                    "save_memory",
                    fields={
                        "title": "Offline preference",
                        "content": "Use offline bundled assets",
                        "pinned": True,
                    },
                )
            )
        if step == 8:
            return turn(
                call(
                    "spawn_worker",
                    objective="Read README and confirm both buttons",
                    scope="Read README.md only",
                    context_mode="inherit",
                )
            )
        if step == 9:
            return turn(call("read_worker", worker_id=result["worker_id"]))
        return turn(
            call(
                "report_work",
                summary="Counter, reset, execution and peer documentation completed.",
                outcome="return",
            )
        )


def test_empty_project_context_memory_collaboration_journey(tmp_path):
    """验证摘要续作、真实程序、邮箱不唤醒、协作文件与跨会话记忆。

    Verify compaction continuation, programs, passive mail, shared files and cross-session memory.
    """

    async def scenario():
        """通过公开入口安排分工，原项目直接编辑。 Arrange roles through APIs and edit in place."""
        model = JourneyModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            model.source = sid = created.session.session_id
            peer = await app.dispatch(
                "sessions.create",
                {
                    "project_id": created.task.project_id,
                    "task_id": created.task.task_id,
                    "model_id": "glm-5.3-flash",
                    "operation_id": str(uuid4()),
                    "role": "Documentation",
                    "scope": "README.md",
                },
            )
            model.peer = peer.session_id
            await app.sessions.memory.configure(peer.session_id, MemorySettings(automatic=False))
            await app.dispatch(
                "collaboration.connect",
                {
                    "source_session_id": sid,
                    "target_session_id": peer.session_id,
                    "scope": "Document index.html in README.md",
                    "mode": "normal",
                },
            )
            assert (await run(app, sid, "Create an offline counter")).run.status == "completed"
            await app.sessions.contexts.start(sid)
            await app.sessions.contexts.wait(sid)
            assert (await app.sessions.contexts.view(sid)).checkpoint
            count = len(model.requests)
            sent = await app.dispatch(
                "collaboration.message",
                {
                    "source_session_id": sid,
                    "target_session_id": peer.session_id,
                    "operation_id": str(uuid4()),
                    "content": "Reset added in the next page update; describe both buttons.",
                },
            )
            assert len(model.requests) == count and app.sessions.active_for(peer.session_id) is None
            await app.dispatch(
                "workers.configure", {"session_id": sid, "settings": {"enabled": True}}
            )
            result = await run(
                app,
                sid,
                "Add Reset, run a check, get documentation, remember offline assets "
                "and ask a worker to read the docs",
            )
            assert result.run.status == "completed", result.run
            assert (tmp_path / "project/index.html").read_text() == PAGE + RESET
            assert "Reset" in (tmp_path / "project/README.md").read_text()
            assert not (tmp_path / "project/.git").exists()
            mailbox = await app.dispatch("collaboration.messages", {"session_id": peer.session_id})
            assert next(
                item for item in mailbox.messages if item.message_id == sent.message_id
            ).delivered_run_id
            workers = await app.dispatch("workers.list", {"session_id": sid})
            assert workers.workers[0].status == "completed"
            task = await app.dispatch("tasks.get", {"task_id": created.task.task_id})
            assert {item.source.session_id for item in task.work.members} == {sid, peer.session_id}
            fresh = await app.sessions.create(created.task.project_id, "glm-5.3-flash")
            model.fresh = fresh.session_id
            assert (
                await run(app, fresh.session_id, "What project preference applies?")
            ).run.status == "completed"
            assert not app.sessions.active_runs

    asyncio.run(scenario())
