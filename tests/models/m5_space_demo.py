"""建立可交互的隔离合作空间示例，本脚本不调用模型。

Prepare an isolated interactive collaboration demo without making model requests.
"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.rpc.application import RpcApplication
from my_agent.runtime.settings import RunLimits


async def prepare() -> None:
    """通过产品服务保存团队并释放写锁，供桌面接续。

    Save a team through production services and release the writer for the desktop.
    """
    root = Path(__file__).resolve().parents[2] / ".artifacts" / "tests"
    root = root / ("m5-space-demo-" + uuid4().hex[:12])
    project = root / "counter"
    project.mkdir(parents=True)
    (project / "AGENTS.md").write_text(
        "# 计数器示例\n\n只做一个自包含 index.html，无依赖。"
        "实现者负责写代码，审查者只读检查。回复使用中文。\n",
        encoding="utf-8",
    )
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "m5-space-demo",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": DEFAULTS["data_schema_version"],
            },
        )
        limits = RunLimits.model_validate(DEFAULTS["run"]).model_copy(
            update={
                "max_requests": 12,
                "max_seconds": 600,
                "request_timeout_seconds": 120,
            }
        )
        await app.dispatch(
            "config.update",
            {
                "model_id": "deepseek-v4.1-flash",
                "run": limits.model_dump(),
            },
        )
        opened = await app.dispatch("projects.open", {"path": str(project)})
        created = await app.dispatch(
            "tasks.create",
            {
                "operation_id": str(uuid4()),
                "project_id": opened.active_project.project_id,
                "model_id": "deepseek-v4.1-flash",
                "fields": {
                    "title": "合作演示：单页计数器",
                    "goal": "实现计数器，交给独立审查者，汇总结果。",
                },
            },
        )
        implementation, review = str(uuid4()), str(uuid4())
        config = {
            "organisation": "central",
            "receiver_member_id": implementation,
            "members": [
                {
                    "member_id": implementation,
                    "name": "实现者",
                    "role": "实现与协调",
                    "scope": "创建 index.html；交给审查者只读检查；收到结果后汇总。",
                    "model_id": "deepseek-v4.1-flash",
                    "position": {"x": 20, "y": 70},
                },
                {
                    "member_id": review,
                    "name": "审查者",
                    "role": "独立 Code Review",
                    "scope": (
                        "读取 index.html，核对初始 0、加一和重置。"
                        "不修改文件；明确静态检查的限制。"
                    ),
                    "model_id": "deepseek-v4.1-flash",
                    "position": {"x": 380, "y": 70},
                },
            ],
            "edges": [
                {
                    "edge_id": str(uuid4()),
                    "source_member_id": implementation,
                    "target_member_id": review,
                    "kind": "delegate",
                    "label": "提交只读审查",
                },
                {
                    "edge_id": str(uuid4()),
                    "source_member_id": review,
                    "target_member_id": implementation,
                    "kind": "result",
                    "label": "返回审查结论",
                },
            ],
            "initial_work_items": [
                {
                    "work_id": "counter",
                    "title": "实现计数器",
                    "scope": "index.html",
                    "status": "planned",
                    "owner_member_id": implementation,
                },
                {
                    "work_id": "review",
                    "title": "独立只读审查",
                    "scope": "index.html",
                    "status": "planned",
                    "method": "review",
                    "depends_on": ["counter"],
                    "owner_member_id": review,
                },
            ],
        }
        await app.dispatch(
            "spaces.save",
            {
                "task_id": created.task.task_id,
                "expected_revision": None,
                "config": config,
            },
        )
        assembled = await app.dispatch("spaces.start", {"task_id": created.task.task_id})
        record = {
            "root": str(root),
            "project": str(project),
            "data": str(root / "data"),
            "task_id": created.task.task_id,
            "space": assembled.model_dump(mode="json"),
            "preparation_model_requests": 0,
        }
        (root / "demo.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"root": str(root), "task_id": created.task.task_id}), flush=True)
    finally:
        await app.close()


if __name__ == "__main__":
    asyncio.run(prepare())
