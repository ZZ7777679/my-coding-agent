"""只在隔离目录生成旧会话样本，不调用模型。 Seed isolated old histories without model calls."""

import json
import sys
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.models.types import ModelTurn, TokenUsage
from my_agent.projects import ProjectService
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.store import SessionStore
from my_agent.sessions.types import (
    AssistantCommitted,
    Fact,
    RequestStarted,
    RunAccepted,
    RunFinished,
    SessionCreated,
)
from my_agent.storage import Storage, utc_now


def seed(store: SessionStore, project_id: str, rounds: int, text_bytes: int) -> str:
    """保存完整轮次的格式化夹具，首次读取仍走真实恢复检查。

    Save complete formatted fixture turns; initial reads use real recovery checks.
    """
    identity = str(uuid4())
    facts = [
        Fact(
            session_id=identity,
            run_id=None,
            seq=1,
            at=utc_now(),
            data=SessionCreated(
                project_id=project_id, model_id="glm-5.3-flash", initial_mode="normal"
            ),
        )
    ]
    for index in range(rounds):
        run, message = str(uuid4()), str(uuid4())
        text = f"History answer {index}\n" + "historical sample " * (text_bytes // 18)
        data = [
            RunAccepted(
                operation_id=str(uuid4()),
                prompt=f"Archived question {index}",
                limits=RunLimits.model_validate(DEFAULTS["run"]),
                requested_limits=None,
                mode="normal",
            ),
            RequestStarted(message_id=message, model_id="glm-5.3-flash"),
            AssistantCommitted(
                message_id=message,
                turn=ModelTurn(
                    text=text,
                    tool_calls=[],
                    native={"role": "assistant", "content": text},
                    usage=TokenUsage(input_tokens=100, output_tokens=30),
                ),
            ),
            RunFinished(status="completed", code=None, message=None, elapsed_seconds=0.1),
        ]
        for item in data:
            facts.append(
                Fact(session_id=identity, run_id=run, seq=len(facts) + 1, at=utc_now(), data=item)
            )
    target = store.path(identity)
    target.parent.mkdir(parents=True)
    target.write_text("".join(f.model_dump_json() + "\n" for f in facts), encoding="utf-8")
    return identity


if __name__ == "__main__":
    storage = Storage(resolve_data_dir(sys.argv[1]))
    project = Path(sys.argv[2])
    project.mkdir(parents=True, exist_ok=True)
    with storage.writer():
        storage.initialize()
        record = ProjectService(storage).open(path=str(project)).active_project
        assert record is not None
        store = SessionStore(storage)
        identities = [
            seed(store, record.project_id, 180, 19000),
            seed(store, record.project_id, 2, 20),
        ]
        print(json.dumps(identities))
