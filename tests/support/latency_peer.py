"""桌面延迟探针：固定模型替身，不访问网络。 Desktop latency probe with a fixed offline model."""

import asyncio
import json
import sys
import time
from pathlib import Path

from my_agent.bootstrap import build_sessions
from my_agent.config import resolve_data_dir
from my_agent.models.timing import RequestTiming
from my_agent.models.types import ModelTurn, TokenUsage
from my_agent.rpc import application
from my_agent.rpc.server import read_parent_credential, serve


class ImmediateModel:
    """立即发出正文，测量后端到真实页面的传输。 Emit text immediately to time the real UI path."""

    def check_available(self):
        """不访问凭据或模型服务。 Do not access credentials or providers."""
        return None

    async def complete(self, **kwargs):
        """先记录发出时刻，短暂停留便于观察流式 DOM。

        Mark emission and keep the stream open briefly for DOM observation.
        """
        streaming = kwargs["messages"][-1]["content"] == "streaming probe"
        parts = (
            [f"STREAM_PART_{index}\n" for index in range(1, 13)] if streaming else ["LATENCY_PROBE"]
        )
        timing = RequestTiming(kwargs.get("on_progress"))
        if streaming:
            await timing.received(32)
            await timing.set_phase("reasoning")
            await asyncio.sleep(0.6)
        emissions = []
        text = ""
        for part in parts:
            text += part
            await timing.received(len(part.encode("utf-8")))
            await timing.text()
            emission = {"before_text_ms": time.time_ns() / 1_000_000, "chars": len(text)}
            await kwargs["on_text"](part)
            emission["after_text_ms"] = time.time_ns() / 1_000_000
            emissions.append(emission)
            await asyncio.sleep(0.25 if streaming else 0.3)
        await timing.set_phase("completed")
        record = {
            "before_text_ms": emissions[0]["before_text_ms"],
            "after_text_ms": emissions[-1]["after_text_ms"],
            "emissions": emissions,
        }
        with report.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        return ModelTurn(
            text=text,
            tool_calls=[],
            native={"role": "assistant", "content": text},
            usage=TokenUsage(input_tokens=1, output_tokens=1),
        )


def build_probe(storage, worker, credential, *, http=None, programs=None):
    """仅替换模型，沿用生产服务、存储和协议。 Replace only the model in the production stack."""
    service = build_sessions(storage, worker, credential, http=http, programs=programs)
    service.model_factory = ImmediateModel
    return service


if __name__ == "__main__":
    report = Path(sys.argv[2]).resolve()
    if not report.is_relative_to(Path(__file__).resolve().parents[2] / ".artifacts/tests"):
        raise SystemExit("Use an isolated artifact report")
    application.build_sessions = build_probe
    credential = read_parent_credential(sys.stdin.buffer)
    serve(resolve_data_dir(sys.argv[1]), sys.stdin.buffer, sys.stdout.buffer, credential)
