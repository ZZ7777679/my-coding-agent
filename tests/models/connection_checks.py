"""显式启用的双模型连接测试验收，最多各一次。

Opt-in checks limited to one call per model.
"""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from my_agent.config import resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.models.connections import ConnectionStatus
from my_agent.rpc.application import RpcApplication
from my_agent.rpc.dto import InitializeResult


async def check(root: Path) -> bool:
    """走桌面同一 RPC 装配，保存公开结果而不创建项目会话。

    Use the desktop RPC composition, recording public results without project sessions.
    """
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    results: list[dict[str, object]] = []
    report = {
        "scope": "one_request_per_model_no_retries",
        "network_policy": "unchanged_httpx_environment",
        "timeout_seconds": 60.0,
        "attempts": 0,
        "results": results,
    }
    report_path = root / "report.json"
    try:
        initialized = await app.dispatch(
            "initialize", {"app_version": "0", "protocol_version": 6, "data_schema_version": 1}
        )
        assert isinstance(initialized, InitializeResult)
        for model in initialized.config.allowed_models:
            report["attempts"] = len(results) + 1
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            status = await app.dispatch(
                "connections.test_model", {"model_id": model, "timeout_seconds": 60.0}
            )
            assert isinstance(status, ConnectionStatus)
            row = next(item for item in status.models if item.model_id == model)
            assert row.last_test is not None
            result = {"model_id": model, **row.last_test.model_dump(mode="json")}
            results.append(result)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(result), flush=True)
        return all(result["code"] == "OK" for result in results)
    finally:
        await app.close()
        print(report_path, flush=True)


def main() -> None:
    """要求显式启用，并为每次运行创建独立产物目录。

    Require opt-in and isolate each run.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.parse_args()
    root = (
        Path(__file__).resolve().parents[2]
        / ".artifacts/tests"
        / ("model-connections-" + uuid4().hex[:12])
    )
    root.mkdir(parents=True)
    raise SystemExit(0 if asyncio.run(check(root)) else 1)


if __name__ == "__main__":
    main()
