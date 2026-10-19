"""在独立探测进程内发送一次有界、无凭据的模型目录请求。

Make one bounded, unauthenticated model-catalog request in a separate probe process.
"""

import json
import socket
import ssl
import urllib.error
import urllib.request

from my_agent import __version__
from my_agent.config import MODEL_DEFAULTS, ModelConfig
from my_agent.models.endpoints import GO_MODELS_URL


def probe() -> dict[str, object]:
    """只查询 Go 模型目录；限制读取大小并返回脱敏错误分类，不验证认证。

    Query the Go catalog with bounded reads and public error codes, without verifying auth.
    """

    request = urllib.request.Request(
        GO_MODELS_URL,
        headers={"Accept": "application/json", "User-Agent": "my-coding-agent/" + __version__},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                return {"code": "INVALID_SERVICE_RESPONSE"}
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                return {"code": "INVALID_SERVICE_RESPONSE"}
            ids = [
                item["id"]
                for item in payload["data"]
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
            return {
                "code": "OK",
                "models_confirmed": all(
                    model in ids
                    for model in ModelConfig.model_validate(MODEL_DEFAULTS).allowed_models
                ),
            }
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return {"code": "CATALOG_AUTH_REQUIRED"}
        return {"code": "PROXY_ERROR" if exc.code == 407 else "HTTP_ERROR"}
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return {"code": "DNS_ERROR"}
        if isinstance(reason, ssl.SSLError):
            return {"code": "TLS_ERROR"}
        if isinstance(reason, TimeoutError):
            return {"code": "TIMEOUT"}
        return {"code": "CONNECT_ERROR"}
    except TimeoutError:
        return {"code": "TIMEOUT"}
    except (ValueError, UnicodeError):
        return {"code": "INVALID_SERVICE_RESPONSE"}
    except OSError:
        return {"code": "CONNECT_ERROR"}


if __name__ == "__main__":
    print(json.dumps(probe()))
