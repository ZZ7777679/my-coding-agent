"""用受控响应检查目录探测，不访问真实服务。

Check catalog probing with controlled responses instead of live services.
"""

import io
import json
import socket
import ssl
import urllib.error

import pytest

from my_agent.network_probe import probe


@pytest.mark.parametrize(
    "failure,expected",
    [
        (urllib.error.URLError(socket.gaierror()), "DNS_ERROR"),
        (urllib.error.URLError(ssl.SSLError()), "TLS_ERROR"),
        (urllib.error.URLError(TimeoutError()), "TIMEOUT"),
        (urllib.error.URLError(ConnectionError()), "CONNECT_ERROR"),
        (
            urllib.error.HTTPError("https://test.invalid", 401, "", {}, None),
            "CATALOG_AUTH_REQUIRED",
        ),
        (urllib.error.HTTPError("https://test.invalid", 407, "", {}, None), "PROXY_ERROR"),
        (urllib.error.HTTPError("https://test.invalid", 503, "", {}, None), "HTTP_ERROR"),
    ],
)
def test_catalog_network_categories_without_live_requests(monkeypatch, failure, expected):
    """模拟 DNS、TLS、超时与 HTTP 失败，验证分类。

    Simulate DNS, TLS, timeout and HTTP failures to verify classification.
    """

    def reject(*args, **kwargs):
        """在网络入口抛出参数化失败，确保测试不联网。

        Raise the parametrized failure at the network boundary, preventing live traffic.
        """

        raise failure

    monkeypatch.setattr("urllib.request.urlopen", reject)
    assert probe()["code"] == expected


def test_catalog_request_is_bounded_and_unauthenticated(monkeypatch):
    """检查目录请求无认证头、地址正确，并拒绝超量响应。

    Check an unauthenticated catalog request targets the correct URL and rejects excess output.
    """

    def respond(request, timeout):
        """验证请求边界后返回内存中的模型目录。

        Validate request boundaries and return an in-memory model catalog.
        """

        assert not request.has_header("Authorization")
        assert request.get_header("User-agent").startswith("my-coding-agent/")
        assert request.full_url == "https://opencode.ai/zen/go/v1/models"
        assert timeout == 3
        return io.BytesIO(
            json.dumps({"data": [{"id": "glm-5.3-flash"}, {"id": "deepseek-v4.1-flash"}]}).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", respond)
    assert probe() == {"code": "OK", "models_confirmed": True}
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: io.BytesIO(b"x" * (1024 * 1024 + 1))
    )
    assert probe()["code"] == "INVALID_SERVICE_RESPONSE"
