"""验证请求检查经过真实客户端与会话存储。

Exercise request inspection through the real client/store.
"""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from my_agent.config import load_config
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.models.go import GoClient
from my_agent.models.http import ModelHttpPool
from my_agent.rpc.dto import CredentialInfo
from my_agent.sessions.requests import read_request
from my_agent.sessions.trace import TraceDetailParams, trace_detail
from my_agent.sessions.types import RequestStarted
from tests.python.test_go import sse
from tests.python.test_goal_controller import app_at, create_session


@pytest.mark.parametrize("capture_failure", [False, True])
def test_request_json_matches_http_and_capture_failure_does_not_gate_run(
    tmp_path, monkeypatch, caplog, capture_failure
):
    """实际客户端双回合与分页一致；存储失败保留业务成功并明确缺失。

    Match both HTTP turns and paged reads; failed capture preserves success and reports absence.
    """
    sent = []
    sentinel = "trace-fixture-credential-not-in-body"

    def handler(request):
        """只模拟 HTTP 服务，实际请求由 GoClient 构造。 Simulate HTTP, not request assembly."""
        assert request.headers["Authorization"] == "Bearer " + sentinel
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            packet = sse(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "read-trace",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path":"sample.txt"}'},
                        }
                    ]
                }
            ) + sse({}, "tool_calls")
        else:
            packet = sse({"content": "Trace fixture completed."}) + sse({}, "stop")
        return httpx.Response(200, content=packet + b"data: [DONE]\n\n")

    if capture_failure:
        from my_agent.storage import atomic_write

        def unwritable(path, content):
            """仅令请求产物写失败。 Fail request artifact writes only."""
            if path.parent.name == "requests":
                raise AgentError("DATA_DIR_NOT_WRITABLE", "fixture")
            atomic_write(path, content)

        monkeypatch.setattr("my_agent.storage.atomic_write", unwritable)

    async def scenario():
        """走接纳、请求、真实文件工具、结果与重读。 Run acceptance through persisted results."""
        pool = ModelHttpPool(
            reuse_enabled=True,
            keepalive_expiry=None,
            drain_timeout_seconds=0.1,
            transport=httpx.MockTransport(handler),
        )
        client = GoClient(
            ResolvedCredential(
                SecretStr(sentinel),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            "https://opencode.ai/inference/go/openai/v1",
            http=pool,
        )
        try:
            async with app_at(tmp_path / "data", client) as app:
                created = await create_session(app, tmp_path / "project")
                (tmp_path / "project" / "sample.txt").write_text(
                    "保存的工具输出。", encoding="utf-8"
                )
                sid = created.session.session_id
                prompt = "原始消息开始\n" + "long input. " * 2600 + "\n原始消息结束"
                await app.sessions.start(
                    sid, str(uuid4()), prompt, load_config(app.storage.location).run, mode="normal"
                )
                await app.sessions.active_for(sid).task
                view = await app.sessions.view(sid)
                assert view.summary.run.status == "completed"
                assert len(sent) == 2
                log = app.sessions.store.load(sid)
                directory = app.sessions.store.path(sid).parent
                requests = [f for f in log.facts if isinstance(f.data, RequestStarted)]
                for fact, outgoing in zip(requests, sent, strict=True):
                    chunks, offset = [], 0
                    while True:
                        detail = trace_detail(
                            log,
                            TraceDetailParams(
                                session_id=sid, seq=fact.seq, part="parameters", offset=offset
                            ),
                            directory,
                        )
                        chunks.append(detail.text)
                        if detail.next_offset is None:
                            break
                        offset = detail.next_offset
                    body = "".join(chunks)
                    assert sentinel not in body
                    if capture_failure:
                        assert "未保存完整请求" in body
                    else:
                        assert json.loads(body) == outgoing
                        assert len(chunks) > 1
                        assert outgoing["messages"][0]["role"] == "system"
                        assert prompt in [m.get("content") for m in outgoing["messages"]]
                        assert outgoing["tools"]
                assert any(m["role"] == "tool" for m in sent[1]["messages"])
                reply = trace_detail(
                    log,
                    TraceDetailParams(session_id=sid, seq=requests[0].seq, part="result"),
                    directory,
                )
                assert "read_file" in reply.text and "tool_calls" in reply.text
                assert "未保存完整请求" in read_request(directory, "legacy-request")
                if capture_failure:
                    assert "TRACE_REQUEST_CAPTURE_FAILED" in caplog.text
        finally:
            await pool.close()

    asyncio.run(scenario())
