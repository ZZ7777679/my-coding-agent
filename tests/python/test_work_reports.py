"""真实文件 / RPC 链路中的工作报告与同步恢复，模型离线替换。

Work reporting and sync recovery over real files and RPC, with an offline model substitute.
"""

import asyncio
import json
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.models.types import ModelTurn, TokenUsage, ToolCall
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import CredentialInfo
from my_agent.sessions.types import ProgressSynced, RunFinished, ToolSkipped


class ReportModel:
    """执行真实文件工具，直接复制结果来源并报告；禁止额外总结回合。

    Use real file tools and their attached references, reporting without a summarization turn.
    """

    def __init__(self) -> None:
        """记录请求数，不连接任何 provider。

        Count requests without connecting to a provider.
        """
        self.calls = 0
        self.reference = None

    def check_available(self) -> None:
        """离线模型不读取凭据。

        The offline model never reads credentials.
        """

    async def complete(self, **kwargs):
        """返回完整工具参数，复制结果所带来源，不猜序号。

        Return complete calls using attached references instead of guessed sequences.
        """
        self.calls += 1
        report_tool = next(
            item["function"]
            for item in kwargs["tools"]
            if item["function"]["name"] == "report_work"
        )
        assert "use return" in report_tool["description"]
        assert "use continue, complete or wait" not in report_tool["description"]
        assert set(report_tool["parameters"]["properties"]["outcome"]["enum"]) == {"return", "wait"}
        if self.calls == 1:
            calls = [
                ToolCall(
                    tool_call_id="file",
                    name="create_file",
                    arguments={"path": "index.html", "content": "<h1>Saved</h1>"},
                )
            ]
        elif self.calls == 2:
            result = json.loads(kwargs["messages"][-1]["content"])
            reference = dict(result["_evidence"])
            self.reference = dict(reference)
            reference["expectation"] = "succeeded"
            calls = [
                ToolCall(
                    tool_call_id="report",
                    name="report_work",
                    arguments={
                        "summary": "已创建页面，尚未运行预览。",
                        "outcome": "return",
                        "work_items": [
                            {
                                "work_id": "page",
                                "title": "Create page",
                                "scope": "Requested file",
                                "status": "completed",
                                "evidence": [reference],
                            }
                        ],
                    },
                ),
                ToolCall(
                    tool_call_id="after-report",
                    name="create_file",
                    arguments={"path": "must-not-run.txt", "content": "invalid extra action"},
                ),
            ]
        else:
            raise AssertionError("No extra model call should follow a terminal report")
        return ModelTurn(
            text="",
            tool_calls=calls,
            native={
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in calls
                ],
            },
            usage=TokenUsage(input_tokens=20, output_tokens=10),
        )


class ObserveModel:
    """恢复后只观察新上下文，不执行文件或程序。

    Observe refreshed context after recovery without file or program effects.
    """

    def __init__(self) -> None:
        """保存明确请求次数与收到的上下文。

        Store request count and received context.
        """
        self.calls = 0
        self.messages = []

    def check_available(self) -> None:
        """本地观察无需凭据。

        Local observation requires no credentials.
        """

    async def complete(self, **kwargs):
        """返回一次普通回答，不请求新工具。

        Return one ordinary answer without requesting tools.
        """
        self.calls += 1
        self.messages = kwargs["messages"]
        return ModelTurn(
            text="已接续共同信息。",
            tool_calls=[],
            native={"role": "assistant", "content": "已接续共同信息。"},
            usage=TokenUsage(input_tokens=10, output_tokens=5),
        )


def test_report_ends_work_and_sync_recovers_without_replaying(tmp_path):
    """真实创建后终止余下工具；同步故障跨重启恢复，不重写项目文件。

    End pending tools after creation; recover failed sync across restart without rewriting files.
    """

    async def scenario():
        """使用真实服务装配，两次启动共享隔离应用数据。

        Use real service composition across two starts of isolated app data.
        """
        location = resolve_data_dir(str(tmp_path / "data"))
        credential = ResolvedCredential(
            None, CredentialInfo(env_var="OPENCODE_API_KEY", source="none", present=False)
        )
        project = tmp_path / "empty"
        project.mkdir()
        init = {
            "app_version": "test",
            "protocol_version": DEFAULTS["protocol_version"],
            "data_schema_version": 1,
        }
        app = RpcApplication(location, credential, None)
        model = ReportModel()
        app.sessions.model_factory = lambda: model

        async def unavailable(session_id, result_seq):
            """只模拟共同进度保存失败，原始执行结果继续保留。

            Fail only shared-progress saving while preserving actual execution results.
            """
            raise AgentError("TASK_SAVE_FAILED", "simulated")

        app.sessions.sync_report = unavailable
        try:
            await app.dispatch("initialize", init)
            opened = await app.dispatch("projects.open", {"path": str(project)})
            created = await app.dispatch(
                "tasks.create",
                {
                    "operation_id": str(uuid4()),
                    "project_id": opened.active_project.project_id,
                    "model_id": "glm-5.3-flash",
                    "fields": {"title": "Page", "goal": "Create a page"},
                },
            )
            session_id = created.session.session_id
            await app.dispatch(
                "runs.start",
                {
                    "session_id": session_id,
                    "operation_id": str(uuid4()),
                    "prompt": "Create index.html",
                    "limits": None,
                    "mode": "normal",
                },
            )
            active = app.sessions.active_for(session_id)
            await active.task
            view = await app.sessions.view(session_id)
            assert model.calls == 2 and view.summary.run.tools == 2
            assert view.summary.run.status == "completed"
            assert view.summary.run.progress_sync == "pending"
            assert view.summary.issue == "PROGRESS_SYNC_PENDING"
            assert active.sync_error == "TASK_SAVE_FAILED"
            assert (project / "index.html").read_text() == "<h1>Saved</h1>"
            modified = (project / "index.html").stat().st_mtime_ns
            assert not (project / "must-not-run.txt").exists()
            log = app.sessions.store.load(session_id)
            assert log.context()[1]
            restored = next(item for item in log.context()[0] if item.get("tool_call_id") == "file")
            assert json.loads(restored["content"])["_evidence"] == model.reference
            assert sum(isinstance(fact.data, ToolSkipped) for fact in log.facts) == 1
            finish = next(fact for fact in log.facts if isinstance(fact.data, RunFinished))
            assert finish.data.report.summary == "已创建页面，尚未运行预览。"
            assert finish.data.elapsed_seconds is not None and finish.data.elapsed_seconds > 0
            assert app.tasks.store.get(created.task.task_id).work.items == []
        finally:
            await app.close()
        resumed = RpcApplication(location, credential, None)
        observation = ObserveModel()
        resumed.sessions.model_factory = lambda: observation
        try:
            await resumed.dispatch("initialize", init)
            assert observation.calls == 0
            assert (
                await resumed.sessions.view(session_id)
            ).summary.issue == "PROGRESS_SYNC_PENDING"
            await resumed.dispatch(
                "runs.start",
                {
                    "session_id": session_id,
                    "operation_id": str(uuid4()),
                    "prompt": "What was saved?",
                    "limits": None,
                    "mode": "plan",
                },
            )
            await resumed.sessions.active_for(session_id).task
            assert observation.calls == 1
            assert "已创建页面，尚未运行预览。" in observation.messages[0]["content"]
            current = resumed.tasks.store.get(created.task.task_id)
            # 后续只读回合增加成员观察，保留原明确报告及来源。
            # The read-only turn adds an observation without replacing the explicit report.
            assert current.fields.status == "active" and current.revision == 3
            assert current.work.items[0].item.work_id == "page"
            assert current.work.source.seq == finish.seq
            assert current.source == "run_report"
            assert (project / "index.html").stat().st_mtime_ns == modified
            assert not (project / "must-not-run.txt").exists()
            assert (await resumed.sessions.view(session_id)).summary.issue is None
            final_log = resumed.sessions.store.load(session_id)
            assert sum(isinstance(fact.data, ProgressSynced) for fact in final_log.facts) == 2
        finally:
            await resumed.close()

    asyncio.run(scenario())
