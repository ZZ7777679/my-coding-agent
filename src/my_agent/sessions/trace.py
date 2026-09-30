"""从会话事实生成运行轨迹，不另存日志。 Project traces from session facts without a second log."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from my_agent.errors import AgentError
from my_agent.models.types import JsonObject, ModelData, TokenUsage
from my_agent.sessions.types import (
    AssistantCommitted,
    Fact,
    RequestStarted,
    RunAccepted,
    RunFinished,
    SessionId,
    ToolCompleted,
    ToolSkipped,
    ToolStarted,
)

if TYPE_CHECKING:
    from my_agent.sessions.store import SessionLog


class TraceParams(ModelData):
    """按运行与事实游标筛选轨迹。 Filter trace by run and fact cursor."""

    session_id: SessionId
    run_id: SessionId | None = None
    before_seq: int | None = None
    tool: str = ""
    errors_only: bool = False
    watch_seqs: list[int] = Field(default_factory=list)
    job_offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 40


class TraceDetailParams(ModelData):
    """通过真实序号分段读取详情。 Read detail chunks by real fact identity."""

    session_id: SessionId
    seq: Annotated[int, Field(ge=1)]
    offset: Annotated[int, Field(ge=0)] = 0
    part: Literal["detail", "parameters", "result"] = "detail"


class TraceLink(ModelData):
    """来自已保存结果的成果引用。 Artifact references from saved results."""

    kind: Literal["change", "archive", "image"]
    identity: str
    title: str


class TraceItem(ModelData):
    """轻量轨迹行及精确关联。 Compact trace row with exact associations."""

    seq: int
    run_id: str | None
    request_id: str | None = None
    kind: str
    title: str
    at: str
    status: str
    tool_name: str | None = None
    duration_ms: float | None = None
    is_error: bool = False
    updated_seq: int = 0
    goal_id: str | None = None
    tool_call_id: str | None = None
    usage: TokenUsage | None = None


class TracePage(ModelData):
    """轨迹摘要页，不携带全部工具正文。 Trace summaries without full tool bodies."""

    items: list[TraceItem]
    before_seq: int | None
    watermark: int
    updates: list[TraceItem] = Field(default_factory=list)
    jobs: list[JsonObject] = Field(default_factory=list)
    job_issues: list[str] = Field(default_factory=list)
    next_job_offset: int | None = None


class TraceDetail(ModelData):
    """可复制的公开详情片段，原生 provider 状态不出后端。

    Copyable public detail chunk, excluding native provider state.
    """

    seq: int
    text: str
    offset: int
    next_offset: int | None
    total_chars: int
    item: TraceItem
    links: list[TraceLink] = Field(default_factory=list)


def _public(fact: Fact) -> JsonObject:
    """只序列化明确的公开事实。 Serialize explicitly public fields only."""
    data = fact.data
    if isinstance(data, AssistantCommitted):
        return {
            "kind": data.kind,
            "message_id": data.message_id,
            "model_id": data.model_id,
            "text": data.turn.text,
            "reasoning": data.turn.reasoning,
            "usage": data.turn.usage.model_dump(mode="json"),
            "model_progress": data.model_progress.model_dump(mode="json")
            if data.model_progress
            else None,
        }
    return data.model_dump(mode="json")


def _rows(log: SessionLog) -> list[tuple[TraceItem, list[Fact]]]:
    """按请求和调用身份配对，分页之前完成关联。

    Associate requests and calls before pagination, never by adjacency.
    """
    results = {
        (fact.run_id, fact.data.result.tool_call_id): fact
        for fact in log.facts
        if isinstance(fact.data, (ToolCompleted, ToolSkipped))
    }
    calls = {
        (fact.run_id, fact.data.call.tool_call_id)
        for fact in log.facts
        if isinstance(fact.data, ToolStarted)
    }
    requests: dict[str | None, str] = {}
    finished = {fact.run_id: fact for fact in log.facts if isinstance(fact.data, RunFinished)}
    goals = {
        fact.run_id: fact.data.goal_id for fact in log.facts if isinstance(fact.data, RunAccepted)
    }
    replies = {
        fact.data.message_id: fact
        for fact in log.facts
        if isinstance(fact.data, AssistantCommitted)
    }
    last_requests = {
        fact.run_id: fact.data.message_id
        for fact in log.facts
        if isinstance(fact.data, RequestStarted)
    }
    rows: list[tuple[TraceItem, list[Fact]]] = []
    for fact in log.facts:
        data = fact.data
        if (
            isinstance(data, (ToolCompleted, ToolSkipped))
            and (fact.run_id, data.result.tool_call_id) in calls
        ):
            continue
        if isinstance(data, RequestStarted):
            requests[fact.run_id] = data.message_id
        item = TraceItem(
            seq=fact.seq,
            run_id=fact.run_id,
            request_id=requests.get(fact.run_id),
            kind=data.kind,
            title=data.kind,
            at=fact.at,
            status="recorded",
            updated_seq=fact.seq,
            goal_id=goals.get(fact.run_id),
        )
        members = [fact]
        if isinstance(data, ToolStarted):
            item.tool_call_id = data.call.tool_call_id
            item.tool_name = data.call.name
            target = next(
                (
                    str(data.call.arguments[key])
                    for key in ("path", "query", "url", "skill_id", "server_id")
                    if key in data.call.arguments
                ),
                "",
            )
            item.title = data.call.name + (" · " + target[:160] if target else "")
            result = results.get((fact.run_id, data.call.tool_call_id))
            item.status = "unfinished" if fact.run_id in finished else "running"
            if fact.run_id in finished:
                item.updated_seq = finished[fact.run_id].seq
            if result and isinstance(result.data, (ToolCompleted, ToolSkipped)):
                members.append(result)
                item.updated_seq = result.seq
                try:
                    content = json.loads(result.data.result.content)
                except (ValueError, TypeError):
                    content = None
                source = content.get("mcp_source") if isinstance(content, dict) else None
                if isinstance(source, dict):
                    item.tool_name = f"{source.get('server_id')}/{source.get('tool_name')}"
                    item.title = item.tool_name + (" · " + target[:160] if target else "")
                item.is_error = result.data.result.is_error
                item.status = (
                    "skipped"
                    if isinstance(result.data, ToolSkipped)
                    else "failed"
                    if item.is_error
                    else "completed"
                )
                item.duration_ms = max(
                    0,
                    (
                        datetime.fromisoformat(result.at) - datetime.fromisoformat(fact.at)
                    ).total_seconds()
                    * 1000,
                )
        elif isinstance(data, (ToolCompleted, ToolSkipped)):
            item.title = data.result.tool_call_id
            item.is_error = data.result.is_error
            item.status = "failed" if item.is_error else "recorded"
        elif isinstance(data, RequestStarted):
            item.title = "模型请求 · " + (data.model_id or "未知模型")
            reply = replies.get(data.message_id)
            item.status = "running" if fact.run_id not in finished else "unfinished"
            if reply:
                members.append(reply)
                item.status = "completed"
                item.updated_seq = reply.seq
                if isinstance(reply.data, AssistantCommitted):
                    item.usage = reply.data.turn.usage
                item.duration_ms = max(
                    0,
                    (
                        datetime.fromisoformat(reply.at) - datetime.fromisoformat(fact.at)
                    ).total_seconds()
                    * 1000,
                )
            elif fact.run_id in finished:
                terminal = finished[fact.run_id]
                item.updated_seq = terminal.seq
                if (
                    last_requests.get(fact.run_id) == data.message_id
                    and isinstance(terminal.data, RunFinished)
                    and terminal.data.status != "completed"
                ):
                    # 只关联最后一个未提交请求，不把已成功请求或工具故障误判为模型失败。
                    # Attribute only the unanswered request, not successful turns or tool faults.
                    members.append(terminal)
                    item.status = terminal.data.status
                    if terminal.data.failed_request_id == data.message_id:
                        item.usage = terminal.data.failed_request_usage
                    item.is_error = item.status in {"failed", "interrupted", "budget_exceeded"}
                    item.duration_ms = max(
                        0,
                        (
                            datetime.fromisoformat(terminal.at) - datetime.fromisoformat(fact.at)
                        ).total_seconds()
                        * 1000,
                    )
        elif isinstance(data, AssistantCommitted):
            item.title = "模型响应 · " + (data.model_id or "未知模型")
            item.status = "completed"
        elif isinstance(data, RunFinished):
            item.title = "运行结束"
            item.status = data.status
            item.is_error = data.status in {"failed", "interrupted"}
        rows.append((item, members))
    return rows


def trace_page(log: SessionLog, params: TraceParams, directory: Path | None = None) -> TracePage:
    """先筛选再分页，游标对应显示行。 Filter before paging with displayed-row cursors."""
    all_rows = _rows(log)
    rows = [
        item
        for item, _ in all_rows
        if (params.run_id is None or item.run_id == params.run_id)
        and (params.before_seq is None or item.seq < params.before_seq)
        and (not params.tool or params.tool.casefold() in (item.tool_name or "").casefold())
        and (not params.errors_only or item.is_error)
    ]
    selected = rows[-params.limit :]
    jobs, issues = _jobs(directory) if directory else ([], [])
    return TracePage(
        items=selected,
        before_seq=selected[0].seq if len(rows) > len(selected) else None,
        watermark=log.facts[-1].seq if log.facts else 0,
        updates=[item for item, _ in all_rows if item.seq in set(params.watch_seqs)],
        jobs=jobs[params.job_offset : params.job_offset + params.limit],
        job_issues=issues,
        next_job_offset=(
            params.job_offset + params.limit
            if params.job_offset + params.limit < len(jobs)
            else None
        ),
    )


def _jobs(directory: Path) -> tuple[list[JsonObject], list[str]]:
    """读取现有作业计量与最近状态，不制造另一份 Trace 日志。

    Project existing job accounting and latest state without a second trace log.
    """
    from my_agent.context.accounting import JobUsage
    from my_agent.context.types import ContextState
    from my_agent.memory.types import MemoryState
    from my_agent.storage import read_document

    jobs: list[JsonObject] = []
    issues: list[str] = []
    for name in ("context", "memory"):
        latest = None
        try:
            if (directory / f"{name}.json").exists():
                latest = (
                    read_document(directory / "context.json", ContextState).job
                    if name == "context"
                    else read_document(directory / "memory.json", MemoryState).job
                )
            if latest:
                # 作业在首个计量文件写入前也有可展示的实际状态。
                # A job has visible state even before its first usage record is saved.
                jobs.append({"kind": name, **latest.model_dump(mode="json")})
            for path in sorted((directory / f"{name}-usage").glob("*.json")):
                usage = read_document(path, JobUsage)
                if not latest or latest.job_id != usage.job_id:
                    jobs.append({"kind": name, **usage.model_dump(mode="json")})
        except AgentError as exc:
            issues.append(f"{name} 作业记录不可用：{exc.code}；源文件保留。")
    return jobs, issues


def _links(facts: list[Fact]) -> list[TraceLink]:
    """从工具结果和材料清单提取已有引用，不猜测文件。

    Extract known result and manifest references without guessing files.
    """
    links: dict[tuple[str, str], TraceLink] = {}
    for fact in facts:
        data = fact.data
        values: list[JsonObject] = []
        if isinstance(data, (ToolCompleted, ToolSkipped)):
            try:
                value = json.loads(data.result.content)
                if isinstance(value, dict):
                    values.append(value)
            except ValueError:
                continue
        elif isinstance(data, RequestStarted) and data.context:
            values.extend(
                {**m.read_arguments, "title": m.title}
                for m in data.context.materials
                if m.read_tool == "read_history"
            )
        for value in values:
            for key, kind in (("change_id", "change"), ("artifact_id", "archive")):
                identity = value.get(key)
                if isinstance(identity, str):
                    link = TraceLink(
                        kind="change" if key == "change_id" else "archive",
                        identity=identity,
                        title=str(value.get("title") or value.get("path") or key),
                    )
                    links[kind, identity] = link
            images = value.get("mcp_artifacts")
            if isinstance(images, list):
                for identity in images:
                    if isinstance(identity, str):
                        links["image", identity] = TraceLink(
                            kind="image", identity=identity, title=identity
                        )
    return list(links.values())


def trace_detail(log: SessionLog, params: TraceDetailParams) -> TraceDetail:
    """只读取所选行正文，分段不改变保存结果。 Read selected detail without changing saved facts."""
    for item, facts in _rows(log):
        if item.seq != params.seq:
            continue
        value: object = {
            "entry": item.model_dump(mode="json"),
            "facts": [{"seq": f.seq, "at": f.at, "data": _public(f)} for f in facts],
        }
        if params.part == "parameters":
            value = next(
                (f.data.call.arguments for f in facts if isinstance(f.data, ToolStarted)), None
            )
        elif params.part == "result":
            value = next(
                (
                    f.data.result.content
                    for f in facts
                    if isinstance(f.data, (ToolCompleted, ToolSkipped))
                ),
                None,
            )
        text = (
            value
            if isinstance(value, str)
            else json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
            )
        )
        end = min(len(text), params.offset + 24000)
        return TraceDetail(
            seq=params.seq,
            text=text[params.offset : end],
            offset=params.offset,
            next_offset=end if end < len(text) else None,
            total_chars=len(text),
            item=item,
            links=_links(facts),
        )
    raise AgentError("TRACE_NOT_FOUND", "该轨迹记录不存在，请刷新列表。")
