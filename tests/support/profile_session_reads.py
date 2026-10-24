"""隔离历史浏览计时，可选只读观察现有日志；不调用模型。

Profile isolated history browsing and optionally read an existing journal without model calls.
"""

import argparse
import json
import tempfile
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from my_agent.config import resolve_data_dir
from my_agent.sessions.reading import SessionReader
from my_agent.sessions.store import SessionStore
from my_agent.storage import Storage
from tests.support.long_session import seed


def measure(output: Path, source: Path | None) -> None:
    """输出毫秒计时；现有数据只读，持久索引实验只在隔离样本上。

    Record timings; existing data is read-only and persisted-index trials use isolated fixtures.
    """
    output.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {}
    if source is not None:
        store = SessionStore(Storage(resolve_data_dir(str(source.parent.parent.parent))))
        start = perf_counter()
        log = store.load(source.parent.name)
        report["existing_read_only"] = {
            "bytes": source.stat().st_size,
            "facts": len(log.facts),
            "cold_load_ms": round((perf_counter() - start) * 1000, 2),
            "issue": log.issue,
        }
    storage = Storage(resolve_data_dir(tempfile.mkdtemp(prefix="data-", dir=output)))
    with storage.writer():
        storage.initialize()
        store = SessionStore(storage)
        identity = seed(store, "isolated-project", 180, 52000)
        start = perf_counter()
        first = SessionReader(store).view(identity, None, str(uuid4()))
        first_ms = (perf_counter() - start) * 1000
        reopened = SessionReader(SessionStore(storage))
        start = perf_counter()
        summary = reopened.index(identity).summary
        summary_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        recent = reopened.view(identity, None, first.process_epoch)
        recent_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        previous = reopened.view(identity, recent.before_seq, first.process_epoch)
        previous_ms = (perf_counter() - start) * 1000
        assert summary == first.summary and recent.entries == first.entries
        report["isolated"] = {
            "source_bytes": store.path(identity).stat().st_size,
            "index_bytes": store.path(identity).with_name("display-index.json").stat().st_size,
            "legacy_first_page_and_index_ms": round(first_ms, 2),
            "reopened_summary_ms": round(summary_ms, 2),
            "reopened_recent_page_ms": round(recent_ms, 2),
            "previous_page_ms": round(previous_ms, 2),
            "recent_entries": len(recent.entries),
            "previous_entries": len(previous.entries),
            "model_requests": 0,
        }
    text = json.dumps(report, indent=2)
    (output / "report.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    measure(args.output.resolve(), args.source.resolve() if args.source else None)
