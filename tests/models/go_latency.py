"""显式启用的 Go 首字分段计时，不记录响应正文。

Opt-in Go latency tracing without response bodies.
"""

import argparse
import asyncio
import json
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from my_agent.bootstrap import build_model_http
from my_agent.config import DEFAULTS, MODEL_DEFAULTS
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.models import go
from my_agent.runtime.loop import SYSTEM_PROMPT
from my_agent.runtime.settings import RunLimits
from my_agent.tools.read_only import ReadTools

ROOT = Path(__file__).resolve().parents[2]
PROMPT = "你是谁？请用一句简短中文回答，不要调用工具。"
CASES = {
    "glm-default": "glm-5.3-flash",
    "deepseek-default": "deepseek-v4.1-flash",
}


class Timing:
    """仅持有单调时间、事件名和计数，不持有模型正文。

    Keep clocks/events/counts, never model text.
    """

    def __init__(self, case):
        """为一条独立请求建立计时基线。 Establish a timing origin for one independent request."""
        self.start = time.perf_counter()
        self.case = case
        self.marks = {}
        self.trace = []
        self.counts = {"body_chunks": 0, "body_bytes": 0, "reasoning_chars": 0, "text_chars": 0}
        self.status = None

    def ms(self):
        """返回从请求入口开始的毫秒数。 Return milliseconds since the call began."""
        return round((time.perf_counter() - self.start) * 1000, 3)

    def first(self, name):
        """每个首事件只记录一次。 Record each first event once."""
        self.marks.setdefault(name, self.ms())

    async def network_trace(self, name, info):
        """忽略可能含头或连接对象的 info，只记录事件名。 Ignore trace payloads and retain names."""
        if len(self.trace) < 80:
            event = {"name": name, "ms": self.ms()}
            if "exception" in info:
                event["exception_type"] = type(info["exception"]).__name__
            self.trace.append(event)


class TimedStream(httpx.AsyncByteStream):
    """透明观察首个网络片段，原流仍由 HTTPX 正常关闭。 Observe chunks without changing cleanup."""

    def __init__(self, stream, timing):
        """保存被包装流与非敏感计时器。 Keep the wrapped stream and non-sensitive timer."""
        self.stream = stream
        self.timing = timing

    async def __aiter__(self):
        """不聚合、不保存网络字节。 Yield arrivals without batching or retaining bytes."""
        async for chunk in self.stream:
            self.timing.first("first_body_byte")
            self.timing.counts["body_chunks"] += 1
            self.timing.counts["body_bytes"] += len(chunk)
            yield chunk

    async def aclose(self):
        """转发资源释放。 Forward resource cleanup."""
        await self.stream.aclose()


@contextmanager
def observe(timing, pool):
    """仅在诊断进程包装生产路径，不替换真实网络或产品配置。

    Wrap production calls only in this diagnostic process without replacing networking/config.
    """
    original_accept = go.TurnBuffer.accept
    timing.first("client_acquire_start")
    client = pool.client()
    timing.first("client_acquire_end")

    async def request_event(request):
        """保留生产 trace，额外记录事件名与请求大小。

        Preserve production tracing and record only names and request size.
        """
        timing.first("request_hook")
        timing.counts["request_bytes"] = len(request.content)
        original_trace = request.extensions.get("trace")

        async def trace(name, info):
            """同一事件同时交给诊断和生产计时器。 Forward events to both timers."""
            await timing.network_trace(name, info)
            if original_trace is not None:
                await original_trace(name, info)

        request.extensions["trace"] = trace

    async def response_event(response):
        """记录响应头到达并透明包装流。 Mark response headers and transparently wrap the stream."""
        timing.first("response_headers")
        timing.status = response.status_code
        response.stream = TimedStream(response.stream, timing)

    async def accept(buffer, value, on_text, limit):
        """计时公开字段与思考字段的首次到达，仅保存字符数。

        Time first public/reasoning fields while retaining character counts only.
        """
        timing.first("first_sse_event")
        for choice in value.get("choices", []):
            delta = choice.get("delta", {})
            reasoning = delta.get("reasoning_content")
            content = delta.get("content")
            if isinstance(reasoning, str) and reasoning:
                timing.first("first_reasoning")
                timing.counts["reasoning_chars"] += len(reasoning)
            if isinstance(content, str) and content:
                timing.first("first_text_event")
                timing.counts["text_chars"] += len(content)
            if delta.get("tool_calls"):
                timing.first("first_tool_fragment")
        return await original_accept(buffer, value, on_text, limit)

    client.event_hooks["request"].append(request_event)
    client.event_hooks["response"].append(response_event)
    go.TurnBuffer.accept = accept
    try:
        yield
    finally:
        go.TurnBuffer.accept = original_accept
        client.event_hooks["request"].remove(request_event)
        client.event_hooks["response"].remove(response_event)


async def measure(case, root, pool, session_id):
    """一次有界真实调用：沿用生产提示、工具定义和输出预算。

    Make one bounded real call with production prompt, tool definitions and output budget.
    """
    model = CASES[case]
    credential = resolve_credential()
    client = go.GoClient(credential, str(MODEL_DEFAULTS["base_url"]), pool)
    client.check_available()
    limits = RunLimits.model_validate(
        {**DEFAULTS["run"], "max_requests": 1, "max_seconds": 60, "request_timeout_seconds": 60}
    )
    fixture = root / "empty-project"
    fixture.mkdir(exist_ok=True)
    definitions = ReadTools(fixture, limits, threading.Event()).definitions()
    timing = Timing(case)

    async def text(delta):
        """标记生产客户端实际交付正文的时刻。 Mark the production client's public text delivery."""
        timing.first("first_text_callback")

    result = {"case": case, "model": model, "status": "pending"}

    async def progress(value):
        """保留生产指标，核对 UI 计时。 Retain production metrics to verify UI timing."""
        result["production_progress"] = value.model_dump()

    try:
        with observe(timing, pool):
            turn = await client.complete(
                model_id=model,
                session_id=session_id,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": PROMPT},
                ],
                tools=definitions,
                limits=limits,
                on_text=text,
                on_progress=progress,
            )
        result.update(status="completed", usage=turn.usage.model_dump(), tools=len(turn.tool_calls))
    except AgentError as exc:
        result.update(status="failed", code=exc.code)
    except Exception as exc:
        result.update(status="failed", code=type(exc).__name__)
    timing.first("finished")
    return {
        **result,
        "http_status": timing.status,
        "marks_ms": timing.marks,
        "counts": timing.counts,
        "trace": timing.trace,
    }


async def measure_batch(args, root, report, report_path):
    """同一事件循环中持有共享池，独立模式模拟旧生命周期。

    Keep pooling in one event loop; fresh mode reproduces the old per-call client lifecycle.
    """
    shared = build_model_http()
    session_id = str(uuid4())
    try:
        for index, case in enumerate(args.case):
            if report["attempts"] >= report["request_budget"]:
                raise SystemExit("Diagnostic request budget exhausted")
            if index and args.gap_seconds:
                await asyncio.sleep(args.gap_seconds)
            report["attempts"] += 1
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            pool = shared if args.client_mode == "pooled" else build_model_http()
            try:
                result = await measure(case, root, pool, session_id)
            finally:
                if args.client_mode == "fresh":
                    await pool.close()
            result.update(
                client_mode=args.client_mode, batch_index=index, gap_seconds=args.gap_seconds
            )
            report["results"].append(result)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(result), flush=True)
    finally:
        await shared.close()


def main():
    """显式启用、累计八次上限，报告进入隔离目录。 Require opt-in and bound attempts to eight."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--case", choices=CASES, action="append", required=True)
    parser.add_argument("--client-mode", choices=["pooled", "fresh"], default="pooled")
    parser.add_argument("--gap-seconds", type=float, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 0 <= args.gap_seconds <= 60:
        parser.error("Diagnostic gap must be between zero and sixty seconds")
    root = (args.output or ROOT / ".artifacts/tests" / ("go-latency-" + uuid4().hex[:12])).resolve()
    if not root.is_relative_to((ROOT / ".artifacts/tests").resolve()):
        parser.error("Use an isolated child of .artifacts/tests")
    root.mkdir(parents=True, exist_ok=True)
    report_path = root / "report.json"
    report = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.exists()
        else {
            "request_budget": 8,
            "attempts": 0,
            "network_policy": "unchanged_httpx_environment",
            "prompt": "fixed_short_identity_question_no_project_content",
            "output_tokens_limit": DEFAULTS["run"]["max_output_tokens"],
            "results": [],
        }
    )
    asyncio.run(measure_batch(args, root, report, report_path))
    print(str(report_path), flush=True)


if __name__ == "__main__":
    try:
        main()
    except AgentError as error:
        print(error.code, file=sys.stderr)
        raise SystemExit(1) from None
