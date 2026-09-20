"""Windows 可用的有界 stdio 控制与通知传输。 Bounded Windows-compatible stdio transport."""

import asyncio
import json
import logging
import threading
from concurrent.futures import TimeoutError as FutureTimeout
from typing import BinaryIO

from pydantic import BaseModel, ValidationError

from my_agent.config import MAX_FRAME_BYTES, DataLocation
from my_agent.credentials import ResolvedCredential
from my_agent.errors import AgentError
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import RpcNotification, RpcRequest, RpcSuccess, SessionEventNotification
from my_agent.rpc.server import failure
from my_agent.sessions.types import SessionSignal


async def run_transport(
    location: DataLocation,
    reader: BinaryIO,
    writer: BinaryIO,
    credential: ResolvedCredential,
    model: str | None,
) -> None:
    """读线程、串行控制队列与单写通道分离；取消走独立控制入口。

    Separate input, serial control and one output writer; cancellation bypasses ordinary work.
    """
    loop = asyncio.get_running_loop()
    application = RpcApplication(location, credential, model)
    incoming: asyncio.Queue[bytes | None] = asyncio.Queue(32)
    controls: asyncio.Queue[RpcRequest | RpcNotification | None] = asyncio.Queue(32)
    outgoing: asyncio.Queue[BaseModel | None] = asyncio.Queue(64)
    stop_reader = threading.Event()
    stop_transport = asyncio.Event()
    auxiliaries: set[asyncio.Task[None]] = set()
    execution_probes: set[asyncio.Task[None]] = set()
    resync: dict[str, SessionSignal] = {}

    def read_frames() -> None:
        """专用守护线程读取管道；队列满时背压，不留下无限任务。

        Read pipes on a dedicated daemon with bounded backpressure and no unbounded futures.
        """
        try:
            while not stop_reader.is_set():
                line = reader.readline(MAX_FRAME_BYTES + 2)
                if len(line.rstrip(b"\r\n")) > MAX_FRAME_BYTES:
                    while line and not line.endswith(b"\n") and not stop_reader.is_set():
                        line = reader.readline(MAX_FRAME_BYTES + 2)
                    line = b"!oversized\n"
                future = asyncio.run_coroutine_threadsafe(incoming.put(line or None), loop)
                while not stop_reader.is_set():
                    try:
                        future.result(timeout=0.1)
                        break
                    except FutureTimeout:
                        continue
                if stop_reader.is_set():
                    future.cancel()
                    return
                if not line:
                    return
        except (OSError, ValueError):
            if not stop_reader.is_set():
                loop.call_soon_threadsafe(stop_transport.set)

    async def send(response: BaseModel) -> None:
        """写入队列具有背压；stdout 永不夹杂诊断。

        Queue with backpressure; stdout stays protocol-only.
        """
        await outgoing.put(response)

    def signal(value: SessionSignal) -> None:
        """溢出的瞬时通知明确转为重新同步，不猜测完成。

        Turn notification overflow into explicit resync.
        """
        if value.session_id not in application.subscriptions:
            return
        try:
            outgoing.put_nowait(
                SessionEventNotification(jsonrpc="2.0", method="session.event", params=value)
            )
        except asyncio.QueueFull:
            resync[value.session_id] = value.model_copy(update={"kind": "resync", "text": ""})

    def write_frame(response: BaseModel) -> None:
        """单线程写完整 UTF-8 帧，超量不截断 JSON。

        Write whole UTF-8 frames without truncating JSON.
        """
        raw = response.model_dump_json().encode("utf-8") + b"\n"
        if len(raw) > MAX_FRAME_BYTES:
            if isinstance(response, SessionEventNotification):
                response = SessionEventNotification(
                    jsonrpc="2.0",
                    method="session.event",
                    params=response.params.model_copy(update={"kind": "resync", "text": ""}),
                )
            else:
                response = failure(
                    getattr(response, "id", None),
                    AgentError("RESPONSE_TOO_LARGE", "响应超过容量，请缩小历史页。"),
                )
            raw = response.model_dump_json().encode("utf-8") + b"\n"
        writer.write(raw)
        writer.flush()

    async def output_loop() -> None:
        """唯一输出任务持续消费队列，断管唤醒清理。

        Drain output through one writer and detect broken pipes.
        """
        try:
            while response := await outgoing.get():
                await asyncio.to_thread(write_frame, response)
                if resync:
                    session_id = next(iter(resync))
                    value = resync.pop(session_id)
                    await asyncio.to_thread(
                        write_frame,
                        SessionEventNotification(
                            jsonrpc="2.0", method="session.event", params=value
                        ),
                    )
        except (OSError, ValueError):
            stop_transport.set()

    async def handle(request: RpcRequest | RpcNotification) -> None:
        """统一参数和业务错误；不把原始异常送到前端。

        Handle errors without exposing raw exceptions.
        """
        request_id = request.id if isinstance(request, RpcRequest) else None
        try:
            result = await application.dispatch(request.method, dict(request.params))
            if request_id is not None:
                await send(
                    RpcSuccess(
                        jsonrpc="2.0",
                        id=request_id,
                        result=result.model_dump(mode="json") if result is not None else None,
                    )
                )
        except ValidationError:
            if request_id is not None:
                await send(
                    failure(
                        request_id, AgentError("INVALID_PARAMS", "请求参数不符合接口要求。"), -32602
                    )
                )
        except AgentError as exc:
            if request_id is not None:
                await send(
                    failure(request_id, exc, -32601 if exc.code == "METHOD_NOT_FOUND" else -32000)
                )
        except Exception as exc:
            # 保留异常类别；请求 ID 也来自输入，不写入通用日志。
            # Retain the exception class; input-derived request IDs stay out of generic logs.
            logging.getLogger(__name__).error("RPC_INTERNAL_ERROR type=%s", type(exc).__name__)
            if request_id is not None:
                await send(
                    failure(
                        request_id,
                        AgentError("INTERNAL_ERROR", "后端操作失败，请检查状态。"),
                        -32603,
                    )
                )
        if application.stopping:
            stop_transport.set()

    async def control_loop() -> None:
        """普通控制保持输入顺序，模型运行由服务独立管理。

        Preserve control order independently of runs.
        """
        while request := await controls.get():
            await handle(request)

    unsubscribe = application.sessions.subscribe(signal)
    threading.Thread(target=read_frames, name="agent-stdin", daemon=True).start()
    output_task = asyncio.create_task(output_loop())
    control_task = asyncio.create_task(control_loop())
    stopped = asyncio.create_task(stop_transport.wait())
    try:
        while not stop_transport.is_set():
            next_frame = asyncio.create_task(incoming.get())
            done, _ = await asyncio.wait({next_frame, stopped}, return_when=asyncio.FIRST_COMPLETED)
            if stopped in done:
                next_frame.cancel()
                await asyncio.gather(next_frame, return_exceptions=True)
                break
            line = next_frame.result()
            if line is None:
                break
            if line == b"!oversized\n":
                await send(
                    failure(None, AgentError("FRAME_TOO_LARGE", "请求超过大小限制。"), -32600)
                )
                continue
            try:
                value = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeError):
                await send(
                    failure(None, AgentError("PARSE_ERROR", "请求不是有效的 UTF-8 JSON。"), -32700)
                )
                continue
            try:
                request = (
                    RpcNotification.model_validate(value)
                    if isinstance(value, dict) and "id" not in value
                    else RpcRequest.model_validate(value)
                )
            except ValidationError:
                await send(
                    failure(
                        None, AgentError("INVALID_REQUEST", "JSON-RPC 请求格式不正确。"), -32600
                    )
                )
                continue
            if request.method in {
                "runs.cancel",
                "goals.control",
                "diagnostics.get",
                "connections.test",
                "connections.test_model",
                "environments.probe",
                "programs.stop",
            }:
                if len(auxiliaries) >= 8:
                    if isinstance(request, RpcRequest):
                        await send(
                            failure(
                                request.id, AgentError("BACKEND_BUSY", "控制请求过多，请稍后重试。")
                            )
                        )
                    continue
                task = asyncio.create_task(handle(request))
                auxiliaries.add(task)
                task.add_done_callback(auxiliaries.discard)
                if request.method == "environments.probe":
                    execution_probes.add(task)
                    task.add_done_callback(execution_probes.discard)
            else:
                if controls.full():
                    if isinstance(request, RpcRequest):
                        await send(
                            failure(request.id, AgentError("BACKEND_BUSY", "请求队列已满。"))
                        )
                else:
                    controls.put_nowait(request)
    finally:
        stop_reader.set()
        # 退出时取消环境探测，探测自己收回句柄；不占住普通控制队列。
        # Cancel environment probes at exit; their own cleanup reaps process handles.
        for task in execution_probes:
            task.cancel()
        # EOF 仍处理已经收到的普通控制，再停止运行；关闭不会自动重发。
        # Drain accepted control work at EOF, then stop runs without replaying requests.
        if output_task.done():
            control_task.cancel()
            for task in auxiliaries:
                task.cancel()
        else:
            await controls.put(None)
        await asyncio.gather(control_task, *auxiliaries, return_exceptions=True)
        await application.close()
        unsubscribe()
        if not output_task.done():
            await outgoing.put(None)
        await output_task
        stopped.cancel()
        await asyncio.gather(stopped, return_exceptions=True)
