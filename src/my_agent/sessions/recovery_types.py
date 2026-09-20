"""中断核对的观察与保存记录，均不代表重试授权。

Interruption observations and durable records, never replay authorization.
"""

from typing import Annotated, Literal

from pydantic import Field

from my_agent.identifiers import EntityId
from my_agent.models.types import ModelData


class ToolObservation(ModelData):
    """当前可核对的成果元数据，保留未知而不伪造旧工具响应。

    Currently observable artifact metadata, preserving uncertainty about the lost tool response.
    """

    state: Literal["not_started", "observed", "unknown"]
    message: str
    artifact_id: EntityId | None = None
    artifact_type: Literal["file", "program"] | None = None
    recorded_status: str | None = None
    current_status: str | None = None
    path: str | None = None
    current_sha256: str | None = None
    exit_code: int | None = None
    code: str | None = None


class RecoveryItem(ModelData):
    """一次未配对调用的确切来源和独立观察。

    Exact provenance and separate observations for one unpaired call.
    """

    turn_seq: Annotated[int, Field(ge=1)]
    tool_call_id: str
    tool_name: str
    started_seq: Annotated[int, Field(ge=1)] | None
    observation: ToolObservation


class SessionRecovered(ModelData):
    """原子确认全部未配对调用，不改原 Run 终态或累计用量。

    Atomically acknowledge all pending calls without rewriting run outcomes or accumulated usage.
    """

    kind: Literal["session.recovered"] = "session.recovered"
    operation_id: EntityId
    items: Annotated[list[RecoveryItem], Field(min_length=1)]
