"""集中定义每次运行的预算快照。 Centralize per-run budget snapshots."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ModelLimits(BaseModel):
    """模型循环的预算；None 关闭对应宿主上限，不改变服务商容量。

    Model-loop budgets; None disables a host cap, not provider capacity.
    """

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    max_requests: Annotated[int, Field(ge=1)] | None
    max_tools: Annotated[int, Field(ge=1)] | None
    max_seconds: Annotated[int, Field(ge=1)] | None
    request_timeout_seconds: Annotated[int, Field(ge=1)] | None
    max_output_tokens: Annotated[int, Field(ge=1)] | None
    max_context_bytes: Annotated[int, Field(ge=4096)] | None
    max_response_bytes: Annotated[int, Field(ge=1024)] | None
    model_retry_attempts: Annotated[int, Field(ge=0)] = 0
    model_retry_delay_seconds: Annotated[float, Field(ge=0)] = 1.0
    model_retry_max_delay_seconds: Annotated[float, Field(ge=0)] = 30.0


class RunLimits(ModelLimits):
    """累计预算可不限，网络与文件读取容量独立配置。

    Cumulative budgets may be unlimited; network and file capacities remain independent.
    """

    max_requests: Annotated[int, Field(ge=1)] | None
    max_tools: Annotated[int, Field(ge=1)] | None
    max_seconds: Annotated[int, Field(ge=1)] | None
    request_timeout_seconds: Annotated[int, Field(ge=1)]
    max_output_tokens: Annotated[int, Field(ge=1)]
    max_context_bytes: Annotated[int, Field(ge=4096)]
    max_response_bytes: Annotated[int, Field(ge=1024, le=262144)]
    max_file_bytes: Annotated[int, Field(ge=1024)]
    max_tool_bytes: Annotated[int, Field(ge=1024, le=131072)]
    max_scan_files: Annotated[int, Field(ge=1)]
    max_depth: Annotated[int, Field(ge=1, le=256)]
    include_ignored: bool
    exclude_globs: list[Annotated[str, Field(min_length=1, max_length=1024)]]


def minimum_limit(*values: float | None) -> float | None:
    """合并实际存在的上限，全部不限仍返回 None。

    Combine present limits while preserving None when every limit is unlimited.
    """
    return min((value for value in values if value is not None), default=None)
