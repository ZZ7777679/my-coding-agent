"""在隔离空项目验证真实 Go 设计、改图与组队执行。

Exercise real Go design, revision and team execution in an isolated project.
"""

import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.rpc.application import RpcApplication
from my_agent.runtime.settings import RunLimits


async def demonstrate() -> None:
    """复用产品 RPC，只发送本脚本创建的样本，保留失败和真实成果。

    Use production RPC with synthetic material only, preserving failures and artifacts.
    """
    root = (
        Path(__file__).resolve().parents[2]
        / ".artifacts/tests"
        / ("team-design-go-" + uuid4().hex[:8])
    )
    project = root / "project"
    project.mkdir(parents=True)
    app = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
    report: dict[str, object] = {"steps": [], "project": str(project)}
    steps: list[dict[str, object]] = []
    report["steps"] = steps
    started = time.monotonic()

    async def wait_session(identity: str) -> None:
        """等待真实运行终态，观察超时保留为失败。

        Await the real terminal state without interpreting observer timeout as success.
        """
        active = app.sessions.active_for(identity)
        if active is not None:
            await asyncio.wait_for(asyncio.shield(active.task), 180)
        view = await app.sessions.view(identity)
        steps.append(
            {
                "session_id": identity,
                "run": view.summary.run.model_dump(mode="json") if view.summary.run else None,
            }
        )

    try:
        async with asyncio.timeout(420):
            await app.dispatch(
                "initialize",
                {
                    "app_version": "team-design-acceptance",
                    "protocol_version": DEFAULTS["protocol_version"],
                    "data_schema_version": DEFAULTS["data_schema_version"],
                },
            )
            limits = RunLimits.model_validate(DEFAULTS["run"]).model_copy(
                update={
                    "max_requests": 8,
                    "max_tools": 35,
                    "max_seconds": 180,
                    "request_timeout_seconds": 90,
                }
            )
            await app.dispatch(
                "config.update", {"model_id": "glm-5.3-flash", "run": limits.model_dump()}
            )
            opened = await app.dispatch("projects.open", {"path": str(project)})
            created = await app.dispatch(
                "tasks.create",
                {
                    "operation_id": str(uuid4()),
                    "project_id": opened.active_project.project_id,
                    "model_id": "glm-5.3-flash",
                    "fields": {
                        "title": "隔离团队设计验收",
                        "goal": (
                            "创建 README.md，仅一行 TEAM_OK；独立成员只读核对后返回。"
                            "无需测试、服务或额外文件。"
                        ),
                    },
                },
            )
            task_id = created.task.task_id
            design = await app.dispatch(
                "spaces.design_open", {"task_id": task_id, "model_id": "glm-5.3-flash"}
            )
            await app.dispatch(
                "spaces.design_send",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "content": (
                        "按任务目标设计两个成员：实现协调者负责写 README 并委派审查；"
                        "独立审查者只读核对并返回。成员模型都用 glm-5.3-flash。"
                        "保存完整团队与委派、结果关系图，先不执行。"
                    ),
                },
            )
            await wait_session(design.session_id)
            initial = await app.dispatch("spaces.design_get", {"task_id": task_id})
            if initial.config is None or len(initial.config.members) != 2:
                raise RuntimeError("真实模型未保存两个成员的图，停止后续验收。")
            steps.append({"generated": initial.model_dump(mode="json")})
            await app.dispatch(
                "sessions.select_model",
                {
                    "session_id": design.session_id,
                    "operation_id": str(uuid4()),
                    "model_id": "deepseek-v4.1-flash",
                },
            )
            await app.dispatch(
                "spaces.design_send",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "content": (
                        "把实现协调者改名为文档负责人，保留全部身份、分工、模型和关系，"
                        "保存修改后的图。无需读取项目文件。"
                    ),
                },
            )
            await wait_session(design.session_id)
            revised = await app.dispatch("spaces.design_get", {"task_id": task_id})
            steps.append({"revised": revised.model_dump(mode="json")})
            if {m.member_id for m in revised.config.members} != {
                m.member_id for m in initial.config.members
            }:
                raise RuntimeError("改图后成员身份变化，停止自动启动。")
            if not any(m.name == "文档负责人" for m in revised.config.members):
                raise RuntimeError("改名未落地，停止后续启动。")
            launched = await app.dispatch(
                "spaces.design_start",
                {
                    "task_id": task_id,
                    "operation_id": str(uuid4()),
                    "config": revised.config.model_dump(),
                },
            )
            steps.append({"launch": launched.model_dump(mode="json")})
            space = await app.dispatch("spaces.get", {"task_id": task_id})
            for binding in space.space.bindings:
                await wait_session(binding.session_id)
            report["result_file"] = (
                (project / "README.md").read_text(encoding="utf-8")
                if (project / "README.md").exists()
                else None
            )
            report["chat"] = (
                await app.dispatch("spaces.chat_view", {"task_id": task_id})
            ).model_dump(mode="json")
    except Exception as exc:
        # 仅测试顶层记账边界；产品错误仍保留在原日志。
        # Test-only reporting boundary; product failures remain in the original logs.
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        await app.close()
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(root / "report.json", flush=True)


if __name__ == "__main__":
    asyncio.run(demonstrate())
