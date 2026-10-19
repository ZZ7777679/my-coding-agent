"""使用生产连接池做显式、无凭据目录探测。 Explicit credential-free probes on the model pool."""

import asyncio
import json
import socket
import ssl
from uuid import uuid4

import httpx

from my_agent.config import DEFAULTS, MODEL_DEFAULTS, ModelConfig
from my_agent.models.connections import ConnectionStatus
from my_agent.models.endpoints import GO_MODELS_URL
from my_agent.models.http import ModelHttpPool, public_request_headers
from my_agent.models.timing import RequestTiming


def network_error_code(error: BaseException) -> str:
    """按异常类型追溯原因，不解析或返回异常原文。 Classify causes without exposing messages."""
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "TIMEOUT"
    if isinstance(error, httpx.ProxyError):
        return "PROXY_ERROR"
    cause: BaseException | None = error
    seen: set[int] = set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if isinstance(cause, ssl.SSLError):
            return "TLS_ERROR"
        if isinstance(cause, socket.gaierror):
            return "DNS_ERROR"
        cause = cause.__cause__ or cause.__context__
    return "CONNECT_ERROR"


async def probe_connection(pool: ModelHttpPool, timeout_seconds: float) -> ConnectionStatus:
    """仅发送一个有界 GET；读完响应以复用连接，目录结果不代表认证。

    Make one bounded GET and consume its body for reuse; a catalog does not verify auth.
    """
    timing = RequestTiming(None)
    code = "UNEXPECTED_ERROR"
    status = None
    confirmed = None
    try:
        async with asyncio.timeout(timeout_seconds), pool.borrow() as client:
            async with client.stream(
                "GET",
                GO_MODELS_URL,
                headers={**public_request_headers(str(uuid4())), "Accept": "application/json"},
                timeout=timeout_seconds,
                extensions={"trace": timing.trace},
            ) as response:
                status = response.status_code
                await timing.headers()
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > DEFAULTS["http"]["probe_max_bytes"]:
                        code = "RESPONSE_TOO_LARGE"
                        break
                    raw.extend(chunk)
                else:
                    timing.progress = timing.progress.model_copy(update={"response_complete": True})
                    if status == 200:
                        payload = json.loads(raw)
                        if not isinstance(payload, dict) or not isinstance(
                            payload.get("data"), list
                        ):
                            raise ValueError("Invalid catalog")
                        ids = {
                            item["id"]
                            for item in payload["data"]
                            if isinstance(item, dict) and isinstance(item.get("id"), str)
                        }
                        confirmed = all(
                            model in ids
                            for model in ModelConfig.model_validate(MODEL_DEFAULTS).allowed_models
                        )
                        code = "OK"
                    elif status in {401, 403}:
                        code = "CATALOG_AUTH_REQUIRED"
                    else:
                        code = "PROXY_ERROR" if status == 407 else "HTTP_ERROR"
                await timing.set_phase("completed")
    except (TimeoutError, httpx.HTTPError) as exc:
        code = network_error_code(exc)
    except (ValueError, UnicodeError):
        code = "INVALID_SERVICE_RESPONSE"
    except asyncio.CancelledError:
        code = "CANCELLED"
        raise
    finally:
        await timing.publish()
        pool.record(
            timing.progress, code, probe=True, http_status=status, models_confirmed=confirmed
        )
    return pool.status()
