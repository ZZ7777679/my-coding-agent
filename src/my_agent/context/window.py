"""有界材料组装及工具完整边界。

Bounded material assembly and complete tool boundaries.
"""

import json

from my_agent.context.tokens import estimate_tokens, head_tail
from my_agent.context.types import Checkpoint, ContextTokens, ToolPreview
from my_agent.models.types import JsonObject
from my_agent.runtime.context import ContextMaterial, describe_material
from my_agent.sessions.store import SessionLog
from my_agent.sessions.types import (
    AssistantCommitted,
    RequestStarted,
    SessionCreated,
    SessionModelChanged,
)
from my_agent.tasks.types import TaskView


def byte_size(value: object) -> int:
    """度量实际 JSON UTF-8 字节，不转换成假 token。

    Measure JSON UTF-8 bytes without invented tokens.
    """
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def observe_tokens(
    log: SessionLog, checkpoint: Checkpoint | None, observation: ContextTokens
) -> ContextTokens:
    """从最近主请求取 usage，不累计费用，不用旧窗口冒充压缩后的计量。

    Read the latest main request's usage without summing costs or reusing pre-compaction counts.
    """
    completed: AssistantCommitted | None = None
    for fact in reversed(log.facts):
        data = fact.data
        if isinstance(data, AssistantCommitted) and completed is None:
            completed = data
        if not isinstance(data, RequestStarted):
            continue
        # 旧事件没有请求模型字段，按当时的选择恢复，不套用后来切换的模型。
        # Resolve legacy requests from their historical selection, not a later model switch.
        request_model = data.model_id or (completed.model_id if completed else None)
        if request_model is None:
            request_model = next(
                (
                    prior.data.model_id
                    for prior in reversed(log.facts[: fact.seq])
                    if isinstance(prior.data, (SessionCreated, SessionModelChanged))
                ),
                None,
            )
        if request_model != observation.model_id:
            observation.status = "model_changed"
        elif checkpoint and checkpoint.created_at > fact.at:
            observation.status = "compacted"
            if completed and completed.message_id == data.message_id:
                observation.input_tokens = completed.turn.usage.input_tokens
        elif completed is None or completed.message_id != data.message_id:
            observation.status = "not_reported"
        elif completed.turn.usage.input_tokens is None:
            observation.status = "not_reported"
        else:
            observation.input_tokens = completed.turn.usage.input_tokens
            observation.status = "reported"
        return observation
    return observation


def task_context(task: TaskView, budget: int) -> str:
    """用户字段保持完整，成员进展与共同决定按容量提供近期索引。

    Keep user fields intact; bound recent member progress and shared decisions.
    """
    work = {
        "decisions": [item.model_dump(mode="json") for item in reversed(task.work.decisions)],
        "members": [item.model_dump(mode="json") for item in reversed(task.work.members)],
        "items": [item.model_dump(mode="json") for item in task.work.items],
        "assignments": [item.model_dump(mode="json") for item in task.work.assignments],
    }
    text = json.dumps(work, ensure_ascii=False)
    if len(text.encode("utf-8")) > budget:
        # 长工作记录按原文分页回读，不让成员全文在每次请求持续膨胀。
        # Long work records remain pageable instead of growing every request's shared input.
        text = text.encode("utf-8")[: max(1, budget)].decode("utf-8", errors="ignore")
        text += "\n[Incomplete task work preview; read_task(offset=0) returns full current facts.]"
    return json.dumps(
        {
            "task_id": task.task_id,
            "revision": task.revision,
            "fields": task.fields.model_dump(mode="json"),
            "work": text,
        },
        ensure_ascii=False,
    )


def records(log: SessionLog) -> list[tuple[int, JsonObject]]:
    """给完整消息附加源事件位置，供窗口和继承共用。

    Attach source positions to complete messages.
    """
    positions: list[int] = []
    messages, _ = log.context(positions)
    return list(zip(positions, messages, strict=True))


def externalize(seq: int, message: JsonObject, preview_tokens: int) -> JsonObject:
    """将较长旧材料变为可回读引用，原事件不变。

    Replace bulky material with readable references.
    """
    content = message.get("content")
    if not isinstance(content, str) or estimate_tokens(content) <= preview_tokens:
        return message
    reference = (
        f"\n[Incomplete tool preview; original received text has {len(content)} characters. "
        "Middle text is omitted; missing facts/errors cannot be inferred absent. "
        "History contains only originally received text, not any original tool omissions. "
        f"Read history seq {seq} with read_history(entry_seq={seq}, offset=0).]"
    )
    # 保留工具已有事实字段；头尾片段是文本而不是伪造的完整 JSON。
    # Preserve existing factual fields; head/tail snippets are text, not pretend complete JSON.
    facts: dict[str, object] = {}
    try:
        payload = json.loads(content)
    except (ValueError, TypeError):
        payload = None
    if isinstance(payload, dict):
        facts = {
            key: payload[key]
            for key in (
                "status",
                "exit_code",
                "code",
                "path",
                "program_id",
                "artifact_id",
                "truncated",
                "start_line",
                "end_line",
                "total_lines",
            )
            if key in payload and not isinstance(payload[key], (dict, list))
        }
    header = (json.dumps(facts, ensure_ascii=False) + "\n") if facts else ""
    preview = head_tail(content, max(0, preview_tokens - estimate_tokens(header + reference)))
    result: JsonObject = {
        **message,
        "content": header + preview + reference,
    }
    # 引用元信息也有成本，短结果不因“缩短”而反增。
    # Reference metadata has a cost; keep short results when the reference would be larger.
    return result if estimate_tokens(result) < estimate_tokens(message) else message


def projected_records(log: SessionLog, previews: list[ToolPreview]) -> list[tuple[int, JsonObject]]:
    """按已保存来源恢复减量投影，不随新提问自动重新裁剪。

    Restore adopted reductions without trimming again on every new user turn.
    """
    budgets = {item.seq: item.tokens for item in previews}
    return [
        (
            seq,
            externalize(seq, msg, budgets[seq])
            if seq in budgets and msg.get("role") == "tool"
            else msg,
        )
        for seq, msg in records(log)
    ]


def trim_candidates(
    log: SessionLog, checkpoint: Checkpoint | None, previews: list[ToolPreview], budget: int
) -> list[ToolPreview]:
    """仅缩短已被后续助手消费的结果，最新未消费输出保持完整。

    Trim consumed results only, preserving output not yet seen by a subsequent assistant.
    """
    items = records(log)
    last_assistant = max((seq for seq, msg in items if msg.get("role") == "assistant"), default=0)
    known = {item.seq for item in previews}
    return [
        ToolPreview(seq=seq, tokens=budget)
        for seq, msg in items
        if seq not in known
        and (checkpoint is None or seq > checkpoint.through_seq)
        and seq < last_assistant
        and msg.get("role") == "tool"
        and externalize(seq, msg, budget) is not msg
    ]


def groups(items: list[tuple[int, JsonObject]]) -> list[list[tuple[int, JsonObject]]]:
    """仅在工具调用全部配对后切分。

    Split only after all tool calls have results.
    """
    result: list[list[tuple[int, JsonObject]]] = []
    group: list[tuple[int, JsonObject]] = []
    pending: set[str] = set()
    for item in items:
        group.append(item)
        message = item[1]
        calls = message.get("tool_calls")
        if isinstance(calls, list):
            for call in calls:
                identifier = call.get("id") if isinstance(call, dict) else None
                if isinstance(identifier, str):
                    pending.add(identifier)
        identifier = message.get("tool_call_id")
        if isinstance(identifier, str):
            pending.discard(identifier)
        if not pending:
            result.append(group)
            group = []
    # 不把在途尾部当作摘要前缀；调用方仍保留它作为近期输入。
    # An unfinished tail is never a summary prefix; callers retain it as recent input.
    return result


def assemble(
    log: SessionLog,
    checkpoint: Checkpoint | None,
    previews: list[ToolPreview],
    materials: list[ContextMaterial] | None = None,
) -> list[JsonObject]:
    """拼接摘要和尾部；旧工具输出回读，当前工具链保持完整。

    Join summary and tail; reference old outputs while preserving the current tool chain.
    """
    items = records(log)
    latest_request = next((item for item in reversed(items) if item[1].get("role") == "user"), None)
    if checkpoint:
        items = [(seq, msg) for seq, msg in items if seq > checkpoint.through_seq]
        if latest_request and latest_request[0] <= checkpoint.through_seq:
            items.insert(0, latest_request)
    budgets = {item.seq: item.tokens for item in previews}
    messages = [
        externalize(seq, msg, budgets[seq]) if seq in budgets and msg.get("role") == "tool" else msg
        for seq, msg in items
    ]
    if materials is not None:
        for (seq, original), message in zip(items, messages, strict=True):
            role = str(message.get("role", ""))
            content = message.get("content")
            materials.append(
                describe_material(
                    kind="history",
                    title=f"{'近期对话' if role != 'tool' else '工具结果'} · #{seq}",
                    form="fragment" if message is not original else "full",
                    reason="旧工具结果预览，原文可回读"
                    if message is not original
                    else "会话连续历史",
                    source_id=str(seq),
                    text=content if isinstance(content, str) else "",
                    read_tool="read_history",
                    read_arguments={"entry_seq": seq},
                )
            )
    if checkpoint:
        if materials is not None:
            materials.insert(
                0,
                describe_material(
                    kind="summary",
                    title="会话摘要",
                    form="summary",
                    reason="已保存的压缩结果",
                    source_id=checkpoint.checkpoint_id,
                    text=checkpoint.text,
                    read_tool="read_history",
                    read_arguments={"through_seq": checkpoint.through_seq},
                ),
            )
        messages.insert(
            0,
            {
                "role": "user",
                "content": (
                    "Earlier conversation summary (reference history; current task and latest "
                    "user instructions take precedence; ended goals remain ended). Original "
                    "entries are readable with read_history through "
                    f"seq {checkpoint.through_seq}:\n"
                    f"{checkpoint.text}"
                ),
            },
        )
    return messages
