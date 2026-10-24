"""M5 真实团队、代码、浏览器截图与重启验收，仅用隔离材料。

Opt-in M5 joint live acceptance using isolated team/code/browser material only.
"""

import argparse
import asyncio
import json
import os
import random
import re
import socket
import sys
import time
from pathlib import Path
from uuid import uuid4

from my_agent.config import DEFAULTS, resolve_data_dir
from my_agent.context.types import ContextSettings
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError
from my_agent.mcp_client.types import McpParams
from my_agent.memory.types import MemorySettings
from my_agent.models.types import (
    JsonObject,
    ModelId,
    ModelTurn,
    ProgressSink,
    RequestSink,
    TextSink,
)
from my_agent.rpc.application import RpcApplication
from my_agent.runtime.settings import RunLimits
from my_agent.sessions.types import AssistantCommitted, ToolCompleted, ToolStarted
from my_agent.terminals.types import OpenTerminalParams
from tests.models.m5_images import image_count, parsed_answer


async def check(
    root: Path,
    request_limit: int,
    seconds_limit: int,
    probe_only: bool = False,
    implementation_model: ModelId = "glm-5.3-flash",
    resume_vision: bool = False,
    verify_saved_only: bool = False,
) -> bool:
    """生产工具执行真实模型工作，独立浏览器 oracle 检查结果并记录请求。

    Run production model tools and independently check browser results/accounting.
    """
    started = time.monotonic()
    requests: list[dict[str, object]] = []
    stages: list[dict[str, object]] = []
    report: dict[str, object] = {
        "scope": "isolated_counter_no_retries",
        "request_limit": request_limit,
        "seconds_limit": seconds_limit,
        "requests": requests,
        "stages": stages,
        "planner_model": "deepseek-v4.1-flash",
        "implementation_model": implementation_model,
        "probe_only": probe_only,
    }
    if resume_vision:
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        requests, stages = report["requests"], report["stages"]
        report["prior_failure"] = report.pop("failure", report.get("prior_failure"))
        report["prior_elapsed_seconds"] = report["elapsed_seconds"]
        report["supplement"] = "explicit_vision_only_no_code_or_collaboration_replay"
        report["request_limit"] = request_limit
    credential = resolve_credential()
    if credential.secret is None:
        raise AgentError("CREDENTIAL_UNAVAILABLE", "未找到验收凭据；未发请求。")
    app = RpcApplication(resolve_data_dir(str(root / "data")), credential, None)
    app_closed = False
    factory = app.sessions.model_factory

    def save() -> None:
        """保存公开事实，不写凭据或图片数据。 Save public facts without credentials/image bytes."""
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    class Observed:
        """计量所有成员真实请求，工具来源保持不变。

        Meter all members' actual requests without altering their tools.
        """

        def __init__(self) -> None:
            """复用生产客户端。 Reuse the production client."""
            self.client = factory()

        def check_available(self) -> None:
            """生产可用性检查不发请求。 Production availability checks send no request."""
            self.client.check_available()

        async def complete(
            self,
            *,
            model_id: ModelId,
            session_id: str,
            messages: list[JsonObject],
            tools: list[JsonObject],
            limits: RunLimits,
            on_text: TextSink,
            on_progress: ProgressSink | None = None,
            on_reasoning: TextSink | None = None,
            on_request: RequestSink | None = None,
        ) -> ModelTurn:
            """发送前保存预算计数，失败不自动重试。

            Persist sent-call accounting before requests and never retry automatically.
            """
            if len(requests) >= request_limit or time.monotonic() - started >= seconds_limit:
                raise AgentError("ACCEPTANCE_BUDGET", "隔离联合验收预算耗尽。")
            row: dict[str, object] = {
                "model": model_id,
                "session_id": session_id,
                "images": image_count(messages),
                "status": "started",
            }
            requests.append(row)
            save()
            tick = time.monotonic()
            try:
                turn = await self.client.complete(
                    model_id=model_id,
                    session_id=session_id,
                    messages=messages,
                    tools=tools,
                    limits=limits,
                    on_text=on_text,
                    on_progress=on_progress,
                    on_reasoning=on_reasoning,
                    on_request=on_request,
                )
                row.update(
                    status="completed",
                    usage=turn.usage.model_dump(),
                    tools=[call.name for call in turn.tool_calls],
                )
                return turn
            except AgentError as exc:
                row.update(status="failed", code=exc.code, message=exc.message)
                raise
            finally:
                row["seconds"] = round(time.monotonic() - tick, 3)
                save()

    app.sessions.model_factory = Observed

    async def await_run(session_id: str, label: str) -> dict[str, object]:
        """等待真实 Run，并保存工具与回答的可检验事实。

        Await the actual run and persist verifiable tool/answer evidence.
        """
        active = app.sessions.active_for(session_id)
        if active is not None and active.task is not None:
            await asyncio.wait_for(
                active.task, max(1, seconds_limit - (time.monotonic() - started))
            )
        view = await app.sessions.view(session_id)
        log = await app.worker.call(app.sessions.store.load, session_id)
        run = view.summary.run
        facts = [fact for fact in log.facts if run is not None and fact.run_id == run.run_id]
        row: dict[str, object] = {
            "label": label,
            "session_id": session_id,
            "run": run.model_dump() if run else None,
            "tools": [f.data.call.model_dump() for f in facts if isinstance(f.data, ToolStarted)],
            "tool_results": [
                f.data.result.model_dump() for f in facts if isinstance(f.data, ToolCompleted)
            ],
            "answers": [f.data.turn.text for f in facts if isinstance(f.data, AssistantCommitted)],
        }
        stages.append(row)
        save()
        print(json.dumps({"stage": label, "status": run.status if run else None}), flush=True)
        if run is None or run.status != "completed":
            raise AgentError("ACCEPTANCE_RUN_FAILED", f"{label} 未完成；查看隔离报告。")
        return row

    async def run(session_id: str, prompt: str, label: str, calls: int) -> dict[str, object]:
        """接纳一个明确授权的有限运行。 Admit one explicitly scoped bounded run."""
        limits = RunLimits.model_validate(DEFAULTS["run"]).model_copy(
            update={"max_requests": calls, "max_seconds": 480, "request_timeout_seconds": 150}
        )
        await app.dispatch(
            "runs.start",
            {
                "session_id": session_id,
                "operation_id": str(uuid4()),
                "prompt": prompt,
                "limits": limits.model_dump(),
                "mode": "normal",
            },
        )
        return await await_run(session_id, label)

    try:
        await app.dispatch(
            "initialize",
            {
                "app_version": "m5-joint-acceptance",
                "protocol_version": DEFAULTS["protocol_version"],
                "data_schema_version": DEFAULTS["data_schema_version"],
            },
        )
        if resume_vision:
            pid, main_sid, task_id = (
                report["project_id"],
                report["main_session"],
                report["task_id"],
            )
            project = root / "project"
            original = next(
                tool["arguments"]["content"]
                for stage in stages
                for tool in stage["tools"]
                if tool["name"] == "create_file"
            )
            html = (project / "index.html").read_text(encoding="utf-8")
            report["exact_label_edit"] = html == original.replace("Add", "Increment", 1)
            if not report["exact_label_edit"]:
                raise AgentError("ACCEPTANCE_DISK", "独立磁盘对比未通过。")
            if verify_saved_only:
                # 仅核实已保存生产事实；不重发模型、启动预览或重放工具。
                # Verify saved production facts without model calls, preview launches or replay.
                oracle_text = report["changed_browser_oracle"]["content"][0]["text"]
                match = re.search(
                    r"x.fillStyle='(red|green|blue|yellow)'", oracle_text.replace("\\'", "'")
                )
                if match is None:
                    raise AgentError("ACCEPTANCE_ORACLE", "保存的独立颜色 oracle 无法读取。")
                expected = {
                    "marker_color": match.group(1),
                    "marker_shape": "circle" if "x.arc(" in oracle_text else "square",
                    "count": "1",
                    "button": "increment",
                }
                vision = next(
                    stage
                    for stage in reversed(stages)
                    if stage["label"] == "screenshot_understanding_supplement"
                )
                observed = parsed_answer(vision["answers"][-1])
                report.update(
                    visual_expected=expected,
                    visual_observed=observed,
                    visual_understanding=observed == expected,
                    visual_image_requests=sum(bool(row["images"]) for row in requests),
                )
                trace = await app.worker.call(app.sessions.store.load, main_sid)
                await app.dispatch("spaces.chat_view", {"task_id": task_id})
                await app.sessions.view(main_sid)
                restored = await app.worker.call(app.sessions.store.load, main_sid)
                report["restart_no_replay"] = (
                    len(restored.facts) == len(trace.facts)
                    and not app.sessions.mcp.connections
                    and not app.sessions.active_for(main_sid)
                )
                terminal_record = json.loads(
                    (
                        root / "data" / "terminals" / (report["supplement_pty_id"] + ".json")
                    ).read_text(encoding="utf-8")
                )
                port = int(terminal_record["summary"]["command"]["arguments"][2])
                with socket.socket() as probe:
                    probe.settimeout(2)
                    report["service_stopped_on_close"] = (
                        terminal_record["summary"]["status"] == "stopped"
                        and probe.connect_ex(("127.0.0.1", port)) != 0
                    )
                report["saved_proof_recovery"] = "zero_network_calls_after_test_double_close_error"
                report["passed"] = bool(
                    report["visual_understanding"]
                    and report["visual_image_requests"]
                    and report["restart_no_replay"]
                    and report["service_stopped_on_close"]
                )
                return bool(report["passed"])
            await run(
                main_sid,
                "This is explicit continuation after the response budget exit. The independent "
                "disk verifier confirms exactly Add was renamed to Increment; the prior actual "
                "browser click/evaluate confirmed count 1 and the read-only review was received. "
                "Give a short final answer acknowledging these recorded facts and that the old "
                "preview was stopped when the app closed. Do not call any tools, start services, "
                "repeat collaboration or edit files; no report tool is needed.",
                "explicit_final_answer_after_budget",
                1,
            )
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            url = f"http://127.0.0.1:{port}/"
            terminal = await app.terminals.open(
                OpenTerminalParams.model_validate(
                    {
                        "project_id": pid,
                        "command": {
                            "kind": "program",
                            "program": sys.executable,
                            "arguments": ["-m", "http.server", str(port), "--bind", "127.0.0.1"],
                        },
                    }
                )
            )
            report["supplement_pty_id"] = terminal.summary.terminal_id
            connection = await app.sessions.mcp.connect(
                McpParams(project_id=pid, session_id=main_sid), "browser"
            )
            await connection.call("tools/list", {})
            app.sessions.mcp.select_tools(
                main_sid,
                "browser",
                [
                    tool
                    for tool in connection.tools
                    if tool.get("name") == "browser_take_screenshot"
                ],
            )
            navigated = await connection.call(
                "tools/call", {"name": "browser_navigate", "arguments": {"url": url}}
            )
            report["supplement_navigation"] = navigated
            color = random.SystemRandom().choice(["red", "blue", "green", "yellow"])
            shape = random.SystemRandom().choice(["circle", "square"])
            function = (
                "() => {document.querySelector('button').click();"
                "const c=document.createElement('canvas');c.width=180;c.height=180;"
                "document.body.appendChild(c);const x=c.getContext('2d');"
                "x.fillStyle='white';x.fillRect(0,0,180,180);"
                + f"x.fillStyle='{color}';"
                + (
                    "x.beginPath();x.arc(90,90,65,0,Math.PI*2);x.fill();"
                    if shape == "circle"
                    else "x.fillRect(25,25,130,130);"
                )
                + "return {count:document.querySelector('#count').textContent,"
                "label:document.querySelector('button').textContent};}"
            )
            oracle = await connection.call(
                "tools/call", {"name": "browser_evaluate", "arguments": {"function": function}}
            )
            report["changed_browser_oracle"] = oracle
            expected = {
                "marker_color": color,
                "marker_shape": shape,
                "count": "1",
                "button": "increment",
            }
            image_start = len(requests)
            vision = await run(
                main_sid,
                "A fresh explicitly resumed browser shows the previously authorized counter "
                "change and an independently injected colored canvas. Do not reload or change it. "
                "Use available browser_take_screenshot(filename='visual.png'), then view_image "
                "with returned image_inputs absolute path. On the next model response inspect "
                "the screenshot pixels and return ONLY JSON keys marker_color (basic English "
                "color), marker_shape (circle/square), count (digit string), button (lowercase "
                "visible label). No other tools, reports, code edits, navigation or collaboration. "
                "The previous run exhausted its response budget; its completed file edit and "
                "browser checks are already independently verified, do not replay them.",
                "screenshot_understanding_supplement",
                3,
            )
            observed = parsed_answer(vision["answers"][-1] if vision["answers"] else "")
            report.update(
                visual_expected=expected,
                visual_observed=observed,
                visual_understanding=observed == expected,
                visual_image_requests=sum(bool(r["images"]) for r in requests[image_start:]),
            )
            before = len((await app.worker.call(app.sessions.store.load, main_sid)).facts)
            await app.close()
            app_closed = True
            reopened = RpcApplication(resolve_data_dir(str(root / "data")), credential, None)
            try:
                await reopened.dispatch("spaces.chat_view", {"task_id": task_id})
                restored = await reopened.worker.call(reopened.sessions.store.load, main_sid)
                report["restart_no_replay"] = (
                    len(restored.facts) == before
                    and not reopened.sessions.mcp.connections
                    and not reopened.sessions.active_for(main_sid)
                )
                with socket.socket() as probe:
                    probe.settimeout(2)
                    report["service_stopped_on_close"] = probe.connect_ex(("127.0.0.1", port)) != 0
            finally:
                await reopened.close()
            report["passed"] = bool(
                report["visual_understanding"]
                and report["visual_image_requests"]
                and report["restart_no_replay"]
                and report["service_stopped_on_close"]
            )
            return bool(report["passed"])
        if probe_only:
            limits = RunLimits.model_validate(DEFAULTS["run"]).model_copy(
                update={"max_output_tokens": 128, "request_timeout_seconds": 40}
            )

            async def ignore_text(text: str) -> None:
                """探测不流出原始网络消息。 Avoid emitting raw network messages during probes."""

            turn = await Observed().complete(
                model_id="glm-5.3-flash",
                session_id=str(uuid4()),
                messages=[{"role": "user", "content": "Reply with exactly READY."}],
                tools=[],
                limits=limits,
                on_text=ignore_text,
            )
            report["probe_answer"] = turn.text
            report["passed"] = turn.text.strip() == "READY"
            return bool(report["passed"])
        project = root / "project"
        project.mkdir()
        (project / "AGENTS.md").write_text(
            "Use one self-contained index.html counter. No dependencies or external assets.\n"
            "Only perform the explicitly assigned task. Reviewer must never edit files.\n",
            encoding="utf-8",
        )
        opened = await app.dispatch("projects.open", {"path": str(project)})
        pid = opened.active_project.project_id
        created = await app.dispatch(
            "tasks.create",
            {
                "operation_id": str(uuid4()),
                "project_id": pid,
                "model_id": "deepseek-v4.1-flash",
                "fields": {"title": "M5 joint counter", "goal": "Build and inspect a tiny counter"},
            },
        )
        task_id, planner = created.task.task_id, created.session.session_id
        await app.sessions.memory.configure(planner, MemorySettings(automatic=False))
        await app.sessions.contexts.configure(planner, ContextSettings(automatic=False))
        await app.dispatch(
            "spaces.generate",
            {
                "task_id": task_id,
                "session_id": planner,
                "operation_id": str(uuid4()),
                "objective": (
                    "Create exactly two team members: a GLM Implementer (glm-5.3-flash) "
                    "and a DeepSeek Reviewer (deepseek-v4.1-flash). Receiver is Implementer. "
                    "Implementer builds a single HTML counter and may request read-only review "
                    "from the existing Reviewer. Reviewer inspects files without writing. "
                    "Include a delegate relationship and return/result relationship. "
                    "No work yet; save_team_draft then finish without unrelated tool calls."
                ),
            },
        )
        await await_run(planner, "team_generation")
        generated = await app.dispatch("spaces.chat_view", {"task_id": task_id})
        draft = generated.generations[-1].draft
        if draft is None or len(draft.config.members) != 2:
            raise AgentError("ACCEPTANCE_TEAM", "真实生成未得到两成员草稿。")
        before = await app.dispatch("spaces.get", {"task_id": task_id})
        report["generation_did_not_adopt"] = before.space is None
        report["generated_draft"] = draft.model_dump()
        adopted = await app.dispatch(
            "spaces.save",
            {"task_id": task_id, "expected_revision": None, "config": draft.config.model_dump()},
        )
        if adopted.space is None or adopted.space.bindings:
            raise AgentError("ACCEPTANCE_TEAM", "采用草稿应不自动创建会话。")
        assembled = await app.dispatch("spaces.start", {"task_id": task_id})
        space = assembled.space
        if space is None:
            raise AgentError("ACCEPTANCE_TEAM", "显式组队失败。")
        members = {member.model_id: member for member in space.config.members}
        bound = {binding.member_id: binding.session_id for binding in space.bindings}
        main_sid = bound[members["glm-5.3-flash"].member_id]
        review_sid = bound[members["deepseek-v4.1-flash"].member_id]
        if main_sid is None or review_sid is None or main_sid == review_sid:
            raise AgentError("ACCEPTANCE_TEAM", "成员没有独立会话。")
        if implementation_model != "glm-5.3-flash":
            # 这是用户明确选择的开发验收接续，不是产品故障自动降级。
            # This is an explicitly selected development continuation, not product fallback.
            await app.sessions.select_model(main_sid, str(uuid4()), implementation_model)
            report["explicit_implementation_selection"] = implementation_model
        report.update(
            task_id=task_id, project_id=pid, main_session=main_sid, review_session=review_sid
        )
        for sid in (main_sid, review_sid):
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            await app.sessions.contexts.configure(sid, ContextSettings(automatic=False))
        # 草稿拓扑是说明，用户在测试中明确保存实际定向约定。
        # Graph topology is descriptive; acceptance explicitly saves its actual agreement.
        await app.dispatch(
            "collaboration.connect",
            {
                "source_session_id": main_sid,
                "target_session_id": review_sid,
                "scope": "Read-only inspection of index.html; return a short factual review",
                "mode": "plan",
            },
        )
        if executable := os.environ.get("MY_AGENT_TEST_BROWSER"):
            browser = (
                app.sessions.mcp.config()
                .servers[0]
                .model_copy(update={"browser_executable": executable})
            )
            await app.dispatch("mcp.save", {"project_id": pid, "server": browser.model_dump()})
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        url = f"http://127.0.0.1:{port}/"
        service = {
            "command": {
                "kind": "program",
                "program": sys.executable,
                "arguments": ["-m", "http.server", str(port), "--bind", "127.0.0.1"],
            },
            "ready_url": url,
        }
        await run(
            main_sid,
            "Build index.html: one heading 'Counter', initial numeric count 0 in id='count', "
            "one button text Add that increments it by one. Keep a simple visible layout. "
            "Create it with the file tool. In the same response discover browser_navigate, "
            "browser_click, browser_evaluate, browser_take_screenshot from server browser. "
            "Start preview via start_service " + json.dumps(service) + ". Navigate, click Add "
            "once, verify displayed count 1, and save initial.png. After creating the file, "
            "use request_collaboration to existing target_session_id=" + review_sid + " in plan "
            "mode: inspect index.html without edits and report whether button is called Add "
            "and increments by one; read the actual file, then return a short review. "
            "Use read_collaboration(wait=true) to receive the result. Do not apply review "
            "changes yet. No global git commands, installation, or extra sessions. "
            "Finish briefly after the actual browser click and returned review; no work report "
            "is required. There are at most 9 model responses for this stage.",
            "implement_browser_review",
            9,
        )
        await await_run(review_sid, "deepseek_review")
        if not (project / "index.html").is_file():
            raise AgentError("ACCEPTANCE_DISK", "实际文件未创建。")
        html_before = (project / "index.html").read_text(encoding="utf-8")
        mcp_params = McpParams(project_id=pid, session_id=main_sid)
        browser_connection = await app.sessions.mcp.connect(mcp_params, "browser")

        async def evaluate(function: str) -> JsonObject:
            """oracle 直接调用实际 MCP，不用模型自称代替页面事实。

            Call the actual MCP for an independent page oracle.
            """
            return await browser_connection.call(
                "tools/call", {"name": "browser_evaluate", "arguments": {"function": function}}
            )

        count_oracle = await evaluate(
            "() => ({count: document.querySelector('#count').textContent, "
            "label: document.querySelector('button').textContent})"
        )
        report["initial_browser_oracle"] = count_oracle
        oracle_text = json.dumps(count_oracle, ensure_ascii=False)
        report["initial_count_one"] = '"1"' in oracle_text or '\\"1\\"' in oracle_text
        if not report["initial_count_one"]:
            raise AgentError("ACCEPTANCE_BROWSER", "独立页面 oracle 未显示 1。")
        await run(
            main_sid,
            "User now explicitly authorizes exactly one change: rename visible Add button to "
            "Increment. Preserve the counter's behavior and all other source. Read then edit "
            "index.html. Verify using the existing browser: navigate/reload the preview, click "
            "Increment once, confirm count 1. No more review or screenshot is needed yet. "
            "Do not restart the service. Finish briefly.",
            "authorized_change",
            5,
        )
        html_after = (project / "index.html").read_text(encoding="utf-8")
        report["exact_label_edit"] = html_after == html_before.replace("Add", "Increment", 1)
        report["changed_browser_oracle"] = await evaluate(
            "() => ({count: document.querySelector('#count').textContent, "
            "label: document.querySelector('button').textContent})"
        )
        if not report["exact_label_edit"]:
            raise AgentError("ACCEPTANCE_DISK", "代码改动超过一次按钮文案替换。")
        color = random.SystemRandom().choice(["red", "blue", "green", "yellow"])
        shape = random.SystemRandom().choice(["circle", "square"])
        expected = {
            "marker_color": color,
            "marker_shape": shape,
            "count": "1",
            "button": "increment",
        }
        marker = await evaluate(
            "() => {const c=document.createElement('canvas');c.id='visual-oracle';"
            "c.width=180;c.height=180;c.style.display='block';document.body.appendChild(c);"
            "const x=c.getContext('2d');x.fillStyle='white';x.fillRect(0,0,180,180);"
            + f"x.fillStyle='{color}';"
            + (
                "x.beginPath();x.arc(90,90,65,0,Math.PI*2);x.fill();"
                if shape == "circle"
                else "x.fillRect(25,25,130,130);"
            )
            + "return {canvas: c.id};}"
        )
        report["visual_oracle_injection"] = marker
        image_start = len(requests)
        vision = await run(
            main_sid,
            "An independent verifier has added a canvas below the counter. Capture the current "
            "page using browser_take_screenshot filename visual.png, without reload/navigation "
            "or evaluate. Use view_image with the absolute path returned in image_inputs; "
            "actually inspect that screenshot next response. Return only JSON keys marker_color "
            "(basic English color), marker_shape (circle or square), count (visible digit string), "
            "button (lowercase visible button label). Do not read source or DOM to guess the "
            "marker; its pixels contain the answer. No additional side effects.",
            "screenshot_understanding",
            3,
        )
        answer = vision["answers"][-1] if vision["answers"] else ""
        observed = parsed_answer(answer)
        report.update(
            visual_expected=expected,
            visual_observed=observed,
            visual_understanding=observed == expected,
            visual_image_requests=sum(bool(r["images"]) for r in requests[image_start:]),
        )
        if observed != expected or not report["visual_image_requests"]:
            raise AgentError("ACCEPTANCE_VISION", "截图原图/视觉观察未通过。")
        artifact_catalog = await app.dispatch(
            "mcp.list", {"project_id": pid, "session_id": main_sid}
        )
        report["browser_artifacts"] = artifact_catalog.artifacts
        trace_before = len((await app.worker.call(app.sessions.store.load, main_sid)).facts)
        request_before = len(requests)
        await app.close()
        app_closed = True
        reopened = RpcApplication(resolve_data_dir(str(root / "data")), credential, None)
        try:
            await reopened.dispatch("spaces.chat_view", {"task_id": task_id})
            await reopened.sessions.view(main_sid)
            after_log = await reopened.worker.call(reopened.sessions.store.load, main_sid)
            report["restart_no_replay"] = (
                len(requests) == request_before
                and len(after_log.facts) == trace_before
                and not reopened.sessions.mcp.connections
                and not reopened.sessions.active_for(main_sid)
            )
            with socket.socket() as probe:
                probe.settimeout(2)
                report["service_stopped_on_close"] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            await reopened.close()
        report["passed"] = all(
            report.get(key)
            for key in (
                "generation_did_not_adopt",
                "initial_count_one",
                "exact_label_edit",
                "visual_understanding",
                "restart_no_replay",
                "service_stopped_on_close",
            )
        )
        return bool(report["passed"])
    except AgentError as exc:
        report.update(passed=False, failure={"code": exc.code, "message": exc.message})
        return False
    finally:
        if not app_closed:
            await app.close()
        report["real_requests"] = len(requests)
        save()
        print(str(root / "report.json"), flush=True)


def main() -> None:
    """显式启用真实模型，预算只归验收。 Explicitly opt into acceptance-only live budgets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-real-models", action="store_true", required=True)
    parser.add_argument("--request-limit", type=int, default=20)
    parser.add_argument("--time-limit-seconds", type=int, default=1200)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--resume-vision-report", type=Path)
    parser.add_argument("--verify-saved-only", action="store_true")
    parser.add_argument(
        "--implementation-model",
        choices=["glm-5.3-flash", "deepseek-v4.1-flash"],
        default="glm-5.3-flash",
    )
    args = parser.parse_args()
    if args.verify_saved_only and not args.resume_vision_report:
        parser.error("--verify-saved-only requires --resume-vision-report; no requests were sent")
    root = (
        args.resume_vision_report.resolve().parent
        if args.resume_vision_report
        else (
            Path(__file__).resolve().parents[2]
            / ".artifacts/tests"
            / ("m5-joint-" + uuid4().hex[:12])
        )
    )
    root.mkdir(parents=True, exist_ok=bool(args.resume_vision_report))
    print(str(root / "report.json"), flush=True)
    raise SystemExit(
        0
        if asyncio.run(
            check(
                root,
                args.request_limit,
                args.time_limit_seconds,
                args.probe_only,
                args.implementation_model,
                bool(args.resume_vision_report),
                args.verify_saved_only,
            )
        )
        else 1
    )


if __name__ == "__main__":
    main()
