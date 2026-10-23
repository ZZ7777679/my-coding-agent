"""有界 JSONL 服务；一个进程持有一个数据根，直到 shutdown 或 EOF。

Bounded JSONL server; one process owns a data root until shutdown or EOF.
"""

import json
from typing import BinaryIO

from pydantic import SecretStr

from my_agent.config import DataLocation
from my_agent.credentials import KEY_ENV, ResolvedCredential, resolve_credential
from my_agent.errors import AgentError
from my_agent.rpc.dto import (
    CredentialInfo,
    ErrorData,
    RpcError,
    RpcFailure,
)


def failure(request_id: str | None, error: AgentError, rpc_code: int = -32000) -> RpcFailure:
    """把公开业务错误包装为 JSON-RPC 失败响应。

    Wrap a public application error in a JSON-RPC failure response.
    """

    return RpcFailure(
        jsonrpc="2.0",
        id=request_id,
        error=RpcError(
            code=rpc_code,
            message=error.message,
            data=ErrorData(
                code=error.code,
                remediation=error.remediation,
                cause_code=error.cause_code,
                phase=error.phase,
                diagnostic_id=error.diagnostic_id,
                diagnostic_issue=error.diagnostic_issue,
                tool_call_id=error.tool_call_id,
                effect_state=error.effect_state,
            ),
        ),
    )


def read_parent_credential(reader: BinaryIO) -> ResolvedCredential:
    # 首帧是父子进程间的私有引导，不能进入公开 RPC 或日志。
    # The first frame is private bootstrap data, never a public RPC or log entry.
    """读取父进程的私有首帧凭据；缺失时按正常来源解析，不返回原始输入。

    Read the private parent bootstrap; resolve normal sources if absent and hide raw input.
    """

    raw = reader.readline(16385)
    try:
        if len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("Invalid bootstrap")
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) - {"key"}:
            raise ValueError("Invalid bootstrap")
        value = data.get("key")
        if value is None:
            return resolve_credential()
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Invalid bootstrap")
        return ResolvedCredential(
            SecretStr(value), CredentialInfo(env_var=KEY_ENV, source="process", present=True)
        )
    except (ValueError, UnicodeError) as exc:
        raise AgentError("BOOTSTRAP_INVALID", "后端凭据初始化失败。") from exc


def serve(
    location: DataLocation,
    reader: BinaryIO,
    writer: BinaryIO,
    credential: ResolvedCredential,
    *,
    model: str | None = None,
) -> None:
    """运行有界异步控制通道；EOF 后清理任务并释放锁。

    Run bounded asynchronous control; clean up tasks and the writer lock after EOF.
    """
    import asyncio

    from my_agent.rpc.transport import run_transport

    asyncio.run(run_transport(location, reader, writer, credential, model))
