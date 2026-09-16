"""桌面延迟探针：固定模型替身，不访问网络。 Desktop latency probe with a fixed offline model."""

import asyncio
import json
import sys
import time
from pathlib import Path

from my_agent.config import resolve_data_dir
from my_agent.models.types import ModelTurn, TokenUsage
from my_agent.projects import ProjectService
from my_agent.rpc import application
from my_agent.rpc.server import read_parent_credential, serve
from my_agent.sessions.service import SessionService
from my_agent.sessions.store import SessionStore


class ImmediateModel:
    """立即发出正文，测量后端到真实页面的传输。 Emit text immediately to time the real UI path."""

    def check_available(self):
        """不访问凭据或模型服务。 Do not access credentials or providers."""
        return None

    async def complete(self, **kwargs):
        """先记录发出时刻，短暂停留便于观察流式 DOM。

        Mark emission and keep the stream open briefly for DOM observation.
        """
        record = {"before_text_ms": time.time_ns() / 1_000_000}
        await kwargs["on_text"]("LATENCY_PROBE")
        record["after_text_ms"] = time.time_ns() / 1_000_000
        await asyncio.sleep(0.3)
        with report.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        return ModelTurn(
            text="LATENCY_PROBE",
            tool_calls=[],
            native={"role": "assistant", "content": "LATENCY_PROBE"},
            usage=TokenUsage(input_tokens=1, output_tokens=1),
        )


def build_probe(storage, worker, credential, *, http=None):
    """仅替换模型，沿用生产服务、存储和协议。 Replace only the model in the production stack."""
    return SessionService(SessionStore(storage), ProjectService(storage), worker, ImmediateModel)


if __name__ == "__main__":
    report = Path(sys.argv[2]).resolve()
    if not report.is_relative_to(Path(__file__).resolve().parents[2] / ".artifacts/tests"):
        raise SystemExit("Use an isolated artifact report")
    application.build_sessions = build_probe
    credential = read_parent_credential(sys.stdin.buffer)
    serve(resolve_data_dir(sys.argv[1]), sys.stdin.buffer, sys.stdout.buffer, credential)
