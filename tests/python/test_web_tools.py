"""联网集成的最小离线检查：真实会话账本与模拟网络。

Minimal offline web integration checks using real session ledgers and simulated networking.
"""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.goals.types import GoalBudget, GoalCreated, GoalCriterion
from my_agent.models.native_search import search_result
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import CredentialInfo
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.types import AuxiliaryCompleted, AuxiliaryStarted
from my_agent.tools.web import bounded_result
from my_agent.web.fetch import PageFetcher, PageHttpClient
from my_agent.web.types import FetchArgs
from my_agent.web.urls import public_url
from tests.support.web_model import PAGE_URL, QUERY, WebModel, native_response


def test_fetch_dns_preflight_uses_actual_httpx_route(monkeypatch):
    """代理域名不依赖本机 DNS，NO_PROXY 直连仍采用原校验。

    Proxied hosts need no local DNS preflight; NO_PROXY routes retain direct checks.
    """
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9876")
    monkeypatch.setenv("NO_PROXY", "direct.example")
    checked = []

    async def check(value):
        """代替真实 DNS，仅记录直连预检。 Record direct checks without actual DNS."""
        checked.append(value)

    monkeypatch.setattr("my_agent.web.fetch.validate_target", check)

    async def scenario():
        """只读取实际路由，不发送 HTTP 请求。 Inspect actual routes without sending HTTP."""
        async with PageHttpClient() as client:
            await client.validate_destination("https://proxy.example/docs")
            await client.validate_destination("https://direct.example/docs")
        assert checked == ["https://direct.example/docs"]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "case", ["complete", "large_envelope", "run_budget", "goal_budget", "cancel", "http_error"]
)
def test_search_in_real_run_and_goal(tmp_path, monkeypatch, case):
    """一次辅助请求正确归属 / 计量，预算和取消停止，主模型不切换。

    Charge one attributed auxiliary request, stop on budgets/cancellation, preserve the main model.
    """

    async def scenario():
        """生产装配保留存储与协议，只替换模型及外部传输。

        Retain production storage/protocol, replacing only models and external transport.
        """
        secret = "sentinel-web-key"
        requests = []
        waiting = asyncio.Event()
        cancelled = asyncio.Event()

        async def native(request):
            """核对 Go 身份和查询隔离，提供成功、失败或可取消等待。

            Check Go identity/query isolation and supply success, failure or cancellable waiting.
            """
            requests.append(request)
            assert request.url == "https://opencode.ai/inference/go/anthropic/v1/messages"
            assert request.headers["x-api-key"] == secret
            assert request.headers["authorization"] == "Bearer " + secret
            assert request.headers["x-opencode-session"] == session_id
            body = json.loads(request.content)
            assert body["model"] == "deepseek-flash"
            assert body["stream"] is False
            assert "PRIVATE_TASK_CONTEXT" not in request.content.decode()
            assert QUERY in request.content.decode()
            if case == "cancel":
                waiting.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            payload = native_response()
            if case == "large_envelope":
                payload["opaque_provider_data"] = "x" * (DEFAULTS["run"]["max_file_bytes"] + 1)
            return httpx.Response(401 if case == "http_error" else 200, json=payload)

        async def checked(url):
            """测试不查真实 DNS；仍校验调用传入的公开 URL。

            Avoid real DNS while checking the public URL passed to validation.
            """
            assert public_url(url) == PAGE_URL

        def page(request):
            """公开网页不收到凭据、会话标识或 Cookie。

            Public pages receive no credentials, session identity or cookies.
            """
            assert not {"authorization", "x-api-key", "x-opencode-session", "cookie"} & set(
                request.headers
            )
            return httpx.Response(
                200, text="JSON encoder and decoder", headers={"content-type": "text/plain"}
            )

        original_fetch = PageFetcher.fetch

        async def fetch_with_transport(self, args, limits, redirects):
            """只替换传输，保留提取与限额。 Replace transport, retaining extraction and limits."""
            return await original_fetch(
                PageFetcher(transport=httpx.MockTransport(page)), args, limits, redirects
            )

        monkeypatch.setattr("my_agent.web.fetch.validate_target", checked)
        monkeypatch.setattr(PageFetcher, "fetch", fetch_with_transport)
        app = RpcApplication(
            resolve_data_dir(str(tmp_path / "data")),
            ResolvedCredential(
                SecretStr(secret),
                CredentialInfo(env_var="OPENCODE_API_KEY", source="process", present=True),
            ),
            None,
        )
        app.http.transport = httpx.MockTransport(native)
        model = WebModel()
        app.sessions.model_factory = lambda: model
        try:
            await app.dispatch(
                "initialize",
                {
                    "app_version": "test",
                    "protocol_version": DEFAULTS["protocol_version"],
                    "data_schema_version": 1,
                },
            )
            project = tmp_path / "project"
            project.mkdir()
            opened = await app.dispatch("projects.open", {"path": str(project)})
            created = await app.dispatch(
                "tasks.create",
                {
                    "operation_id": str(uuid4()),
                    "project_id": opened.active_project.project_id,
                    "model_id": "glm-5.3-flash",
                    "fields": {"title": "Web", "goal": "PRIVATE_TASK_CONTEXT"},
                },
            )
            session_id = created.session.session_id
            await app.sessions.goals.create(
                session_id,
                GoalCreated(
                    goal_id=str(uuid4()),
                    objective="Search official documentation",
                    criteria=[
                        GoalCriterion(
                            criterion_id="sources", description="Search and read a source"
                        )
                    ],
                    budget=GoalBudget(max_requests=1 if case == "goal_budget" else 5),
                    limits=RunLimits.model_validate(
                        {**DEFAULTS["run"], "max_requests": 1 if case == "run_budget" else 5}
                    ),
                ),
            )
            driver = app.sessions.goals.driver(session_id)
            if case == "cancel":
                await asyncio.wait_for(waiting.wait(), 3)
                await app.sessions.cancel(app.sessions.active_for(session_id).run_id)
            await asyncio.wait_for(driver.task, 5)
            view = await app.sessions.view(session_id)
            goal = (await app.sessions.goals.list(session_id))[0]
            log = app.sessions.store.load(session_id)
            assert log.issue is None and not list(project.iterdir())
            assert secret not in app.sessions.store.path(session_id).read_text(encoding="utf-8")
            if case in {"complete", "large_envelope"}:
                assert goal.status == "completed" and view.summary.run.status == "completed"
                assert model.calls == 4 and len(requests) == 1
                assert goal.usage.requests == view.summary.run.requests == 5
                assert goal.usage.input_tokens == 16 and goal.usage.output_tokens == 12
                cards = [entry.web_result for entry in view.entries if entry.web_result]
                assert [card.kind for card in cards] == ["web.search", "web.page"]
                assert cards[0].sources[0].excerpt == "JSON encoder and decoder"
                assert "opaque_provider_data" not in app.sessions.store.path(session_id).read_text(
                    encoding="utf-8"
                )
                assert (
                    len([fact for fact in log.facts if isinstance(fact.data, AuxiliaryCompleted)])
                    == 1
                )
            else:
                assert goal.status != "active" and model.calls == 1
                assert len(requests) == (0 if case in {"run_budget", "goal_budget"} else 1)
                assert goal.usage.requests == view.summary.run.requests == 1 + len(requests)
                assert not any(isinstance(fact.data, AuxiliaryCompleted) for fact in log.facts)
                if case == "cancel":
                    assert cancelled.is_set() and goal.status == "paused"
                    assert app.http.status().active_requests == 0
            assert len(
                [fact for fact in log.facts if isinstance(fact.data, AuxiliaryStarted)]
            ) == len(requests)
        finally:
            await app.close()

    asyncio.run(scenario())


def test_page_redirect_extraction_and_output_limit(monkeypatch):
    """无凭据逐跳读取，阻止本地重定向；保留代码并提供真实分页位置。

    Fetch unauthenticated hops, reject local redirects, preserve code and return actual offsets.
    """

    async def scenario():
        checked_urls = []

        async def checked(url):
            """记录逐跳校验，不访问真实 DNS。 Record each validation without real DNS."""
            checked_urls.append(public_url(url))

        def respond(request):
            """保留完整 HTTP 交互契约，只在内存提供页面。

            Keep HTTP request semantics and supply the page in memory.
            """
            assert "cookie" not in request.headers and "authorization" not in request.headers
            if request.url.path == "/local":
                return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
            if request.url.path == "/missing":
                return httpx.Response(
                    404, headers={"content-type": "application/problem+json"}, text='{"status":404}'
                )
            if request.url.path == "/empty":
                return httpx.Response(
                    200, headers={"content-type": "text/html"}, text="<script>app()</script>"
                )
            if request.url.path == "/start":
                return httpx.Response(
                    302, headers={"location": "/page", "set-cookie": "session=never-forward"}
                )
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<html><head><title>Docs</title></head><body><script>must-not-show</script>"
                "<p hidden>hidden-text</p><h1>Example</h1><pre>def example():\n    return 1</pre>"
                "<p>" + "正文 " * 1200 + "</p></body></html>",
            )

        monkeypatch.setattr("my_agent.web.fetch.validate_target", checked)
        fetcher = PageFetcher(transport=httpx.MockTransport(respond))
        limits = RunLimits.model_validate(DEFAULTS["run"])
        result = await fetcher.fetch(FetchArgs(url="https://example.org/start"), limits, 5)
        assert checked_urls == ["https://example.org/start", "https://example.org/page"]
        assert (
            result.title == "Docs"
            and "must-not-show" not in result.content
            and "hidden-text" not in result.content
        )
        assert "def example():\n    return 1" in result.content
        original = result.content
        bounded_result(result, 1024)
        assert result.truncated and result.next_offset == len(result.content)
        next_part = await fetcher.fetch(
            FetchArgs(url=result.url, offset=result.next_offset), limits, 5
        )
        assert result.content + next_part.content == original
        missing_page = await fetcher.fetch(FetchArgs(url="https://example.org/missing"), limits, 5)
        assert missing_page.status_code == 404 and missing_page.content == '{"status":404}'
        empty_page = await fetcher.fetch(FetchArgs(url="https://example.org/empty"), limits, 5)
        assert empty_page.status_code == 200 and empty_page.content == ""
        with pytest.raises(AgentError, match="HTTP"):
            await fetcher.fetch(FetchArgs(url="https://example.org/local"), limits, 5)
        with pytest.raises(AgentError) as missing:
            search_result(
                {"content": [{"type": "text", "text": PAGE_URL}]}, QUERY, "deepseek-v4.1-flash"
            )
        assert missing.value.code == "WEB_SEARCH_UNAVAILABLE"

    asyncio.run(scenario())
