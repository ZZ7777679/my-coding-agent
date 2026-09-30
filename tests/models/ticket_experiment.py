"""小型合成工单实验；输入与 oracle 由评测准备，实现只由产品 Agent 编写。

Small synthetic ticket experiment; the evaluator seeds inputs and oracles, never the solution.
"""

import argparse
import asyncio
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, load_config, resolve_data_dir
from my_agent.context.types import ContextSettings
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.memory.types import MemorySettings
from my_agent.models.types import JsonObject, ToolCall, ToolResult
from my_agent.rpc.application import RpcApplication
from my_agent.runtime.tools import ToolExecutor
from my_agent.sessions.types import AssistantCommitted, RequestStarted, ToolStarted
from tests.models.ticket_manifest import save_manifest

ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ("baseline", "implement_only", "tools_subset", "brief", "examples", "batch")
TOOL_SUBSET = {
    "list_files",
    "read_file",
    "search",
    "create_file",
    "edit_file",
    "run_command",
    "inspect_python",
    "execution_environment",
    "read_program",
    "report_work",
    "load_skill",
    "search_memory",
    "read_task",
    "read_history",
    "get_context_status",
}
FIELDS = ["id", "title", "status", "priority", "owner"]
ROWS = [
    [" T001 ", "登录失败", " OPEN ", " HIGH ", " Ada "],
    ["T002", "Export report", "closed", "low", "Ben"],
    ["T001", "duplicate", "open", "medium", "Cara"],
    ["", "missing id", "open", "low", "Dave"],
    ["T003", "", "open", "high", "Eli"],
    ["T004", "bad status", "waiting", "high", "Finn"],
    ["T005", "bad priority", "open", "urgent", "Gail"],
    [
        "T006",
        "<script>window.__ticket_injected=1</script> & "
        '<img src=x onerror="window.__ticket_injected=1">',
        "in_progress",
        "medium",
        "",
    ],
]
PROMPT = """请读取这个项目的 AGENTS.md 和 REQUIREMENTS.md，完成一个离线工单整理器。
用 Python 标准库实现 ticket_report.py，处理 tickets.csv，生成规定的清洗 CSV、拒绝明细、
统计 JSON 和可筛选静态 HTML。请实际运行正常、空数据和错误表头样本；发现问题自行修复。
不要安装依赖、访问网络或创建服务。先看是否有适用的已启用方法，再按需使用，不必凑工具。
最后简短说明文件、实际命令、检查结果与未验证项。当前只实现第一轮需求。"""
FOLLOWUP = """继续刚才同一个工单整理器，保留此前全部校验、去重、HTML 安全文本和两个筛选条件。
追加：空 owner 统一为 unassigned；summary.json 增加 by_owner（只统计接纳行）；
HTML 增加 input#search，按 title 做不区分大小写的子串搜索，与状态/优先级筛选同时生效。
请更新实现及 README，重新运行正常和边界样本，不要修改输入文件或增加依赖。"""
REQUIREMENTS = """# 离线工单整理器：第一轮

仅用 Python 标准库实现 `ticket_report.py --input <CSV> --out-dir <目录>`。
输入 UTF-8 CSV 必须具有 id,title,status,priority,owner 五列；错误表头非零退出，且不得生成输出。
去除字段首尾空格，status/priority 转小写。id 和 title 必填；status 仅 open/in_progress/closed，
priority 仅 low/medium/high；owner 第一轮允许空值。只把通过字段校验的行加入去重集合，
相同 id 保留第一条有效行。拒绝原因按 missing_id、missing_title、invalid_status、
invalid_priority、duplicate_id 的先后顺序选择一个。空数据正常输出全零统计。

输出 cleaned.csv 保持五列及输入有效行顺序；rejected.json 为数组，每项仅 row/id/reason，
row 是含表头的 CSV 记录序号（首条数据为 2），id 使用去空格后的值。
summary.json 包含 total_rows/accepted_rows/rejected_rows/duplicates，及 by_status/by_priority；
两组统计始终含上述全部枚举，值为接纳行数量。重复行计入 rejected_rows，duplicates 单列计数。

report.html 离线可打开，table#tickets 的 tbody 每行五个 td，顺序同 CSV。select#status-filter
和 select#priority-filter 的选项值分别为空字符串（全部）及对应枚举；两条件同时生效。
隐藏行可以保留在 DOM，但不能仍显示。标题等输入是普通文本，不能执行输入里的脚本 / HTML。
不加载任何外部资源。README 说明运行和已实际完成的验证。

样本 tickets.csv 含 8 行：3 行接纳、5 行拒绝，其中重复 1 行；状态和优先级各枚举均接纳 1 行。
不要为样本硬编码输出；评测还会使用不同 ID 的正常和异常行。
"""


class TicketToolMenu:
    """只对实验菜单做单变量筛选，执行仍交给产品工具。

    Filter only the experiment menu; execution remains with production tools.
    """

    def __init__(self, delegate: ToolExecutor) -> None:
        """持有本次产品工具。 Hold the production tools for this run."""
        self.delegate = delegate

    def definitions(self) -> list[JsonObject]:
        """筛选菜单，不改 schema。 Filter the menu without schema edits."""
        return [
            d
            for d in self.delegate.definitions()
            if isinstance(f := d.get("function"), dict) and f.get("name") in TOOL_SUBSET
        ]

    def is_mutating(self, name: str) -> bool:
        """沿产品副作用分类。 Preserve production effect classification."""
        return self.delegate.is_mutating(name)

    async def execute(self, call: ToolCall) -> ToolResult:
        """沿生产参数、冲突与执行规则，不自动重放。 Keep production validation without replays."""
        return await self.delegate.execute(call)


def variant_prompt(prompt: str, variant: str) -> str:
    """每个候选只追加自己的一个提示因素。 Append only the candidate's own prompt factor."""
    extra = {
        "brief": (
            "\n这是小任务：准备简短，尽快分步骤写出首个可运行文件；避免重复规划。原验收不减少。"
        ),
        "examples": (
            '\n参数示例：run_command({"command":{"kind":"program","program":"python",'
            '"arguments":["ticket_report.py","--input","tickets.csv","--out-dir","out-normal"]},'
            '"timeout_seconds":60})。timeout_seconds 是工具外层整数，'
            "command 内没有 cwd/timeout_seconds。"
            "report_work 只需 summary/outcome；其他字段按 schema 提供，不猜测 work_items 形状。"
            "edit_file 使用 path/old_text/new_text，唯一匹配原文后编辑。"
        ),
        "batch": (
            "\n若多处编辑彼此独立且原文已明确，可在同一响应中给出少量独立工具调用；"
            "保留唯一匹配与冲突处理，不减少验收。"
        ),
    }
    return prompt + extra.get(variant, "")


def save(path: Path, value: object) -> None:
    """只保存脱敏实验事实。 Save sanitized experiment facts only."""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def csv_text(rows: list[list[str]], fields: list[str] = FIELDS) -> str:
    """生成合成 CSV，明确使用 LF。 Build synthetic CSV with explicit LF."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(fields)
    writer.writerows(rows)
    return stream.getvalue()


def prepare(root: Path) -> None:
    """仅创建缺失实验输入，不写产品答案或覆盖已有文件。

    Create only missing experiment inputs without answers or overwriting existing files.
    """
    root.mkdir(parents=True, exist_ok=True)
    project = root / "project"
    project.mkdir(exist_ok=True)
    inputs = {
        "AGENTS.md": "仅修改本实验项目；标准库、离线、不安装依赖、不更改样本。保持 UTF-8。\n",
        "REQUIREMENTS.md": REQUIREMENTS,
        "tickets.csv": csv_text(ROWS),
        "empty.csv": csv_text([]),
        "bad-header.csv": csv_text([], FIELDS[:-1]),
    }
    for name, content in inputs.items():
        path = project / name
        if path.exists():
            if path.read_text(encoding="utf-8") != content:
                raise ValueError(f"Input changed: {name}")
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    save(
        root / "input-manifest.json",
        {name: hashlib.sha256(text.encode()).hexdigest() for name, text in inputs.items()},
    )
    save(root / "prompts.json", {"implementation": PROMPT, "followup": FOLLOWUP})


def oracle(root: Path, phase: str) -> dict:
    """独立运行 Agent 实现，核对固定样本、留出样本和浏览器行为。

    Independently run the agent implementation against fixed/holdout inputs and browser behavior.
    """
    project = root / "project"
    directory = root / ("oracle-" + phase + "-" + uuid4().hex[:6])
    directory.mkdir()
    env = {
        k: v
        for k, v in os.environ.items()
        if not re.search("KEY|PASSWORD|SECRET|TOKEN", k, re.I) and not k.startswith("MY_AGENT_")
    }
    env["PYTHONUTF8"] = "1"
    checks = []
    expected_clean = [dict(zip(FIELDS, ROWS[index], strict=True)) for index in (0, 1, 7)]
    for row in expected_clean:
        row.update({key: value.strip() for key, value in row.items()})
        row["status"], row["priority"] = row["status"].lower(), row["priority"].lower()
        if phase == "followup" and not row["owner"]:
            row["owner"] = "unassigned"
    cases = [
        ("main", project / "tickets.csv", expected_clean),
        ("empty", project / "empty.csv", []),
    ]
    holdout = directory / "holdout.csv"
    holdout.write_text(
        csv_text(
            [
                ["H1", "Other title", "closed", "high", "Zed"],
                ["H1", "dup", "open", "low", ""],
                ["H2", "bad", "other", "low", ""],
            ]
        ),
        encoding="utf-8",
    )
    cases.append(
        (
            "holdout",
            holdout,
            [dict(zip(FIELDS, ["H1", "Other title", "closed", "high", "Zed"], strict=True))],
        )
    )
    for label, input_path, clean in cases:
        output = directory / label
        process = subprocess.run(
            [
                sys.executable,
                "ticket_report.py",
                "--input",
                str(input_path),
                "--out-dir",
                str(output),
            ],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        (directory / (label + ".log")).write_text(process.stdout + process.stderr, encoding="utf-8")
        try:
            assert process.returncode == 0, f"exit {process.returncode}"
            with (output / "cleaned.csv").open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                assert reader.fieldnames == FIELDS
                assert list(reader) == clean, "cleaned rows mismatch"
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            total, rejected, duplicates = {
                "main": (8, 5, 1),
                "empty": (0, 0, 0),
                "holdout": (3, 2, 1),
            }[label]
            expected = {
                "total_rows": total,
                "accepted_rows": len(clean),
                "rejected_rows": rejected,
                "duplicates": duplicates,
                "by_status": {
                    s: sum(r["status"] == s for r in clean)
                    for s in ("open", "in_progress", "closed")
                },
                "by_priority": {
                    p: sum(r["priority"] == p for r in clean) for p in ("low", "medium", "high")
                },
            }
            if phase == "followup":
                expected["by_owner"] = {
                    owner: sum(r["owner"] == owner for r in clean)
                    for owner in {r["owner"] for r in clean}
                }
            assert all(summary.get(key) == value for key, value in expected.items()), (
                "summary mismatch"
            )
            rejects = json.loads((output / "rejected.json").read_text(encoding="utf-8"))
            wanted = (
                []
                if label == "empty"
                else [
                    {"row": 3, "id": "H1", "reason": "duplicate_id"},
                    {"row": 4, "id": "H2", "reason": "invalid_status"},
                ]
                if label == "holdout"
                else [
                    {"row": i, "id": identity, "reason": reason}
                    for i, identity, reason in [
                        (4, "T001", "duplicate_id"),
                        (5, "", "missing_id"),
                        (6, "T003", "missing_title"),
                        (7, "T004", "invalid_status"),
                        (8, "T005", "invalid_priority"),
                    ]
                ]
            )
            assert rejects == wanted, "rejected rows mismatch"
            assert (output / "report.html").is_file(), "HTML missing"
            checks.append({"case": label, "passed": True})
        except (AssertionError, OSError, ValueError) as exc:
            checks.append({"case": label, "passed": False, "reason": str(exc)})
    invalid_output = directory / "bad-header"
    invalid = subprocess.run(
        [
            sys.executable,
            "ticket_report.py",
            "--input",
            str(project / "bad-header.csv"),
            "--out-dir",
            str(invalid_output),
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    checks.append(
        {
            "case": "bad-header",
            "passed": invalid.returncode != 0 and not any(invalid_output.glob("*")),
            "exit_code": invalid.returncode,
        }
    )
    html = directory / "main" / "report.html"
    if html.exists():
        browser = subprocess.run(
            [
                "node",
                str(ROOT / "tests/models/ticket_browser.mjs"),
                str(html),
                phase,
                str(directory / "browser.json"),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        (directory / "browser.log").write_text(browser.stdout + browser.stderr, encoding="utf-8")
        checks.append(
            {"case": "browser", "passed": browser.returncode == 0, "exit_code": browser.returncode}
        )
    report = {
        "phase": phase,
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "directory": str(directory),
    }
    save(directory / "result.json", report)
    return report


async def run(
    root: Path,
    resume: bool = False,
    *,
    variant: str = "baseline",
    only_phase: str | None = None,
    output_tokens: int | None = None,
    request_timeout: int | None = None,
) -> None:
    """沿生产会话服务执行两轮真实工作；保护失败与重启事实。

    Run two real assignments through production sessions while preserving failure/restart facts.
    """
    probe = json.loads((root / "probe.json").read_text(encoding="utf-8"))
    if probe["result"]["code"] != "OK":
        raise ValueError("A successful live model probe is required")
    model = probe["model"]
    report = {
        "model": model,
        "started_at": datetime.now(UTC).isoformat(),
        "requests": [],
        "phases": [],
        "probe": probe,
        "request_limit": 50,
        "time_limit_seconds": 1200,
        "variant": variant,
        "only_phase": only_phase,
    }
    spent = 0.0
    if resume:
        previous = json.loads((root / "report.json").read_text(encoding="utf-8"))
        save(root / ("report-before-resume-" + uuid4().hex[:6] + ".json"), previous)
        report = previous
        spent = report["seconds"]
        report.setdefault("resumes", []).append(
            {"at": datetime.now(UTC).isoformat(), "previous_status": report["status"]}
        )
        report["status"] = "running"
    started = time.monotonic()
    app = None
    sid = report.get("session_id") if resume else None

    def persist() -> None:
        """逐请求落盘，不记录秘密。 Persist each request without secrets."""
        report["seconds"] = round(spent + time.monotonic() - started, 3)
        save(root / "report.json", report)

    async def open_app() -> RpcApplication:
        """新建产品后端并复用同一隔离根和计量包装。

        Start the production backend on the same isolated root and metering wrapper.
        """
        instance = RpcApplication(resolve_data_dir(str(root / "data")), resolve_credential(), None)
        await instance.dispatch(
            "initialize",
            {
                "app_version": "ticket-experiment",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": 1,
            },
        )
        factory = instance.sessions.model_factory

        class Observed:
            """不替换模型决策，只观察真实客户端。

            Observe the real client without changing decisions.
            """

            def __init__(self):
                """复用生产工厂。 Reuse the production factory."""
                self.client = factory()

            def check_available(self):
                """沿原凭据检查。 Use the original credential check."""
                return self.client.check_available()

            async def complete(self, **kwargs):
                """发送前记请求，失败计数，保持正常 token 配置。

                Count attempts before sending, including failures, with normal token settings.
                """
                if len(report["requests"]) >= 50 or spent + time.monotonic() - started >= 1200:
                    raise AgentError("EVALUATION_BUDGET", "Experiment guard reached")
                row = {
                    "model": kwargs["model_id"],
                    "status": "started",
                    "phase": report.get("current_phase"),
                }
                report["requests"].append(row)
                persist()
                tick = time.monotonic()
                try:
                    turn = await self.client.complete(**kwargs)
                    row.update(
                        status="completed",
                        usage=turn.usage.model_dump(),
                        tools=[call.name for call in turn.tool_calls],
                    )
                    return turn
                except AgentError as exc:
                    row.update(status="failed", code=exc.code)
                    if hasattr(exc, "usage"):
                        row["usage"] = exc.usage.model_dump()
                    raise
                except asyncio.CancelledError:
                    row.update(status="cancelled")
                    raise
                finally:
                    row["seconds"] = round(time.monotonic() - tick, 3)
                    persist()
                    print(json.dumps(row), flush=True)

        instance.sessions.model_factory = Observed
        if variant == "tools_subset":
            production = instance.sessions.tool_factory
            instance.sessions.tool_factory = lambda ctx: TicketToolMenu(production(ctx))
        return instance

    try:
        app = await open_app()
        config = load_config(app.storage.location)
        report["effective_config"] = {
            "provider": config.model.provider,
            "model": model,
            "base_url": config.model.base_url,
            "limits": config.run.model_dump(),
            "automatic_memory": False,
            "automatic_compaction": False,
        }
        report["source"] = {
            "head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "working_tree": subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ),
        }
        if not resume:
            opened = await app.dispatch("projects.open", {"path": str(root / "project")})
            created = await app.dispatch(
                "tasks.create",
                {
                    "operation_id": str(uuid4()),
                    "project_id": opened.active_project.project_id,
                    "model_id": model,
                    "fields": {
                        "title": "离线工单整理器实验",
                        "goal": "处理合成 CSV 并生成离线报告",
                    },
                },
            )
            sid = created.session.session_id
            if variant == "implement_only":
                flow = created.task.workflow.model_copy(deep=True)
                flow.session_stages[sid] = "implement"
                await app.dispatch(
                    "tasks.workflow",
                    {
                        "task_id": created.task.task_id,
                        "operation_id": str(uuid4()),
                        "expected_revision": created.task.revision,
                        "workflow": flow.model_dump(),
                    },
                )
        report["session_id"] = sid
        await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
        await app.sessions.contexts.configure(sid, ContextSettings(automatic=False))
        persist()
        completed = {p["phase"] for p in report["phases"] if p.get("oracle", {}).get("passed")}
        for phase, prompt in (("implementation", PROMPT), ("followup", FOLLOWUP)):
            if only_phase is not None and phase != only_phase:
                continue
            if phase in completed:
                continue
            prompt = variant_prompt(prompt, variant)
            if resume and phase == "implementation":
                prompt = (
                    "上次模型以 length 结束，未产生代码文件。请接续原工单任务，"
                    "利用已有读取结果，分步骤创建文件，不要在一个请求中生成全部产物。"
                    "只需完成小实现和必要实际检查，避免重复规划。\n" + PROMPT
                )
            report["current_phase"] = phase
            if phase == "followup":
                before = await app.sessions.view(sid)
                facts = app.sessions.store.path(sid).read_bytes()
                await app.close()
                app = await open_app()
                after = await app.sessions.view(sid)
                report["restart"] = {
                    "watermark_unchanged": before.watermark == after.watermark,
                    "facts_unchanged": app.sessions.store.path(sid).read_bytes() == facts,
                    "active_runs": len(app.sessions.active_runs),
                }
            limits = load_config(app.storage.location).run
            if resume:
                limits = limits.model_copy(
                    update={"max_output_tokens": 16384, "request_timeout_seconds": 300}
                )
                report["retry_limits"] = limits.model_dump()
            overrides = {}
            if output_tokens is not None:
                overrides["max_output_tokens"] = output_tokens
            if request_timeout is not None:
                overrides["request_timeout_seconds"] = request_timeout
            if overrides:
                limits = type(limits).model_validate({**limits.model_dump(), **overrides})
            report["effective_config"]["limits"] = limits.model_dump()
            save(root / ("prompt-" + phase + ".json"), {"prompt": prompt, "variant": variant})
            snapshot = await asyncio.to_thread(
                save_manifest,
                root,
                phase,
                {
                    **report["effective_config"],
                    "limits": limits.model_dump(),
                    "variant": variant,
                    "only_phase": only_phase,
                },
                prompt,
            )
            report.setdefault("manifests", []).append(snapshot["path"])
            persist()
            await app.sessions.start(sid, str(uuid4()), prompt, limits, mode="normal")
            active = app.sessions.active_for(sid)
            await asyncio.wait_for(
                asyncio.shield(active.task),
                min(limits.max_seconds + 20, 1200 - spent - (time.monotonic() - started)),
            )
            view = await app.sessions.view(sid)
            log = await app.sessions._load(sid)
            run_id = view.summary.run.run_id
            entry = {
                "phase": phase,
                "run": view.summary.run.model_dump(),
                "answers": [
                    fact.data.turn.text
                    for fact in log.facts
                    if fact.run_id == run_id and isinstance(fact.data, AssistantCommitted)
                ],
                "tool_names": [
                    fact.data.call.name
                    for fact in log.facts
                    if fact.run_id == run_id and isinstance(fact.data, ToolStarted)
                ],
                "request_facts": sum(
                    isinstance(fact.data, RequestStarted) and fact.run_id == run_id
                    for fact in log.facts
                ),
                "contexts": [
                    {
                        "seq": f.seq,
                        "message_count": f.data.context.message_count,
                        "request_bytes": f.data.context.request_bytes,
                        "estimated_fixed_tokens": f.data.context.estimated_fixed_tokens,
                        "estimated_input_tokens": f.data.context.estimated_input_tokens,
                        "tool_count": len(f.data.context.tool_names),
                        "skills": [
                            m.source_id for m in f.data.context.materials if m.kind == "skill"
                        ],
                    }
                    for f in log.facts
                    if f.run_id == run_id and isinstance(f.data, RequestStarted) and f.data.context
                ],
            }
            report["phases"].append(entry)
            persist()
            if view.summary.run.status != "completed":
                report["status"] = "stopped_after_run_failure"
                break
            entry["oracle"] = await asyncio.to_thread(oracle, root, phase)
            persist()
            print(
                json.dumps({"phase": phase, "oracle_passed": entry["oracle"]["passed"]}), flush=True
            )
            if not entry["oracle"]["passed"]:
                report["status"] = "stopped_after_oracle_failure"
                break
        else:
            report["status"] = "completed"
    except (AgentError, OSError, ValueError, TimeoutError) as exc:
        report["status"] = "failed"
        report["error"] = {
            "type": type(exc).__name__,
            "code": exc.code if isinstance(exc, AgentError) else None,
            "message": str(exc) if not isinstance(exc, AgentError) else exc.message,
        }
        raise
    finally:
        if app:
            await app.close()
        persist()


def main() -> None:
    """默认只准备输入，真实运行需要显式开关。 Prepare by default; live execution requires a flag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--enable-real-models", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--variant", choices=VARIANTS, default="baseline")
    parser.add_argument("--only-phase", choices=("implementation", "followup"))
    parser.add_argument("--output-tokens", type=int)
    parser.add_argument("--request-timeout", type=int)
    parser.add_argument("--seed-project", type=Path)
    parser.add_argument("--probe-reference", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_relative_to((ROOT / ".artifacts/tests").resolve()):
        parser.error("Experiment root must be under .artifacts/tests")
    prepare(root)
    if args.probe_reference and not (root / "probe.json").exists():
        reference = args.probe_reference.resolve()
        if not reference.is_relative_to((ROOT / ".artifacts/tests").resolve()):
            parser.error("Probe reference must be an existing sanitized artifact")
        probe = json.loads(reference.read_text(encoding="utf-8"))
        probe["reused_from"] = str(reference.relative_to(ROOT)).replace("\\", "/")
        save(root / "probe.json", probe)
    if args.seed_project:
        seed = args.seed_project.resolve()
        if not seed.is_relative_to((ROOT / ".artifacts/tests").resolve()) or args.resume:
            parser.error("Seed must be a separate artifact project on a fresh run")
        for name in ("ticket_report.py", "README.md"):
            target = root / "project" / name
            if target.exists():
                parser.error("Seed cannot overwrite existing implementation")
            shutil.copyfile(seed / name, target)
    print(str(root), flush=True)
    if args.enable_real_models:
        if (root / "report.json").exists() and not args.resume:
            parser.error("An existing run must not be replayed; inspect its report first")
        if args.resume and not (root / "report.json").exists():
            parser.error("Resume needs an existing report")
        asyncio.run(
            run(
                root,
                args.resume,
                variant=args.variant,
                only_phase=args.only_phase,
                output_tokens=args.output_tokens,
                request_timeout=args.request_timeout,
            )
        )


if __name__ == "__main__":
    main()
