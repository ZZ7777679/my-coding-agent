"""有界 JSONL 服务；一个进程持有一个数据根，直到 shutdown 或 EOF。

Bounded JSONL server; one process owns a data root until shutdown or EOF.
"""

import json
from contextlib import ExitStack
from typing import BinaryIO

from pydantic import BaseModel, SecretStr, ValidationError

from my_agent import __version__
from my_agent.config import DEFAULTS, MAX_FRAME_BYTES, DataLocation, load_config
from my_agent.credentials import KEY_ENV, ResolvedCredential, resolve_credential
from my_agent.diagnostics import diagnose
from my_agent.errors import AgentError
from my_agent.projects import ProjectService
from my_agent.rpc.dto import (
    AppInfo,
    CredentialInfo,
    DiagnosticsParams,
    EmptyParams,
    ErrorData,
    InitializeParams,
    InitializeResult,
    OpenProjectById,
    OpenProjectParams,
    RpcError,
    RpcFailure,
    RpcNotification,
    RpcRequest,
    RpcSuccess,
    UpdateConfigParams,
)
from my_agent.storage import Storage


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
            data=ErrorData(code=error.code, remediation=error.remediation),
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
    """顺序处理有界 RPC 帧；退出时释放写入锁，初始化失败仍允许诊断。

    Process bounded RPC frames serially; release the lock on exit and retain diagnostics.
    """

    storage = Storage(location)
    projects = ProjectService(storage)
    initialized = False
    stopping = False

    def send(response: BaseModel) -> None:
        """输出一条 UTF-8 响应；超限改为公开错误，不截断合法 JSON。

        Write one UTF-8 response; replace oversized output with an error, never truncated JSON.
        """

        raw = response.model_dump_json().encode("utf-8") + b"\n"
        if len(raw) > MAX_FRAME_BYTES:
            raw = (
                failure(
                    getattr(response, "id", None),
                    AgentError("RESPONSE_TOO_LARGE", "响应超过大小限制。"),
                )
                .model_dump_json()
                .encode("utf-8")
                + b"\n"
            )
        writer.write(raw)
        writer.flush()

    with ExitStack() as stack:
        while not stopping:
            line = reader.readline(MAX_FRAME_BYTES + 2)
            if not line:
                break
            if len(line.rstrip(b"\r\n")) > MAX_FRAME_BYTES:
                # 丢弃完整超限帧，防止残余字节被当作下一条请求。
                # Drain the oversized frame so its remaining bytes cannot become another request.
                while line and not line.endswith(b"\n"):
                    line = reader.readline(MAX_FRAME_BYTES + 2)
                send(failure(None, AgentError("FRAME_TOO_LARGE", "请求超过大小限制。"), -32600))
                continue
            request_id: str | None = None
            notification = False
            try:
                try:
                    data = json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeError):
                    send(
                        failure(
                            None, AgentError("PARSE_ERROR", "请求不是有效的 UTF-8 JSON。"), -32700
                        )
                    )
                    continue
                try:
                    notification = isinstance(data, dict) and "id" not in data
                    request = (
                        RpcNotification.model_validate(data)
                        if notification
                        else RpcRequest.model_validate(data)
                    )
                    request_id = request.id if isinstance(request, RpcRequest) else None
                except ValidationError:
                    notification = False
                    send(
                        failure(
                            None, AgentError("INVALID_REQUEST", "JSON-RPC 请求格式不正确。"), -32600
                        )
                    )
                    continue
                result: BaseModel | None = None
                if request.method == "initialize":
                    if (
                        type(request.params.get("protocol_version")) is not int
                        or request.params.get("protocol_version") != DEFAULTS["protocol_version"]
                        or type(request.params.get("data_schema_version")) is not int
                        or request.params.get("data_schema_version")
                        != DEFAULTS["data_schema_version"]
                    ):
                        raise AgentError("PROTOCOL_MISMATCH", "前后端协议或数据版本不兼容。")
                    InitializeParams.model_validate(request.params)
                    config = load_config(location, model)
                    if not initialized:
                        stack.enter_context(storage.writer())
                        projects.initialize()
                        initialized = True
                    result = InitializeResult(
                        app=AppInfo(
                            name=DEFAULTS["app_name"],
                            app_version=__version__,
                            protocol_version=1,
                            stage="M0",
                        ),
                        storage=storage.info(),
                        config=config.public(credential.info),
                        projects=projects.view(),
                        capabilities=[
                            "initialize",
                            "projects.open",
                            "projects.list",
                            "config.get",
                            "config.update",
                            "diagnostics.get",
                            "shutdown",
                        ],
                    )
                elif request.method not in {
                    "projects.open",
                    "projects.list",
                    "config.get",
                    "config.update",
                    "diagnostics.get",
                    "shutdown",
                }:
                    if not notification:
                        send(
                            failure(
                                request_id, AgentError("METHOD_NOT_FOUND", "不支持该方法。"), -32601
                            )
                        )
                    continue
                elif request.method == "diagnostics.get":
                    diagnostics = DiagnosticsParams.model_validate(request.params)
                    if credential.info.source != "process":
                        credential = resolve_credential()
                    result = diagnose(
                        dev=diagnostics.dev,
                        network=diagnostics.network,
                        write_probe=diagnostics.write_probe,
                        credential=credential,
                        storage=storage,
                        model=model,
                    )
                elif not initialized:
                    raise AgentError("NOT_INITIALIZED", "后端尚未完成初始化。")
                elif request.method == "projects.open":
                    params = OpenProjectParams.model_validate(request.params).root
                    result = (
                        projects.open(project_id=params.project_id)
                        if isinstance(params, OpenProjectById)
                        else projects.open(path=params.path)
                    )
                elif request.method == "projects.list":
                    EmptyParams.model_validate(request.params)
                    result = projects.view()
                elif request.method in {"config.get", "config.update"}:
                    if request.method == "config.update":
                        update = UpdateConfigParams.model_validate(request.params)
                        storage.save_model(update.model_id)
                        model = None
                    else:
                        EmptyParams.model_validate(request.params)
                    if credential.info.source != "process":
                        credential = resolve_credential()
                    result = load_config(location, model).public(credential.info)
                elif request.method == "shutdown":
                    EmptyParams.model_validate(request.params)
                    stopping = True
                if isinstance(request, RpcRequest):
                    send(
                        RpcSuccess(
                            jsonrpc="2.0",
                            id=request.id,
                            result=result.model_dump(mode="json") if result is not None else None,
                        )
                    )
            except ValidationError:
                if not notification:
                    send(
                        failure(
                            request_id,
                            AgentError("INVALID_PARAMS", "请求参数不符合接口要求。"),
                            -32602,
                        )
                    )
            except AgentError as exc:
                if not notification:
                    send(failure(request_id, exc))
            except (BrokenPipeError, OSError):
                break
