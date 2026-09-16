"""集中定义每次运行的预算快照。 Centralize per-run budget snapshots."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RunLimits(BaseModel):
    """受信设置中的可调整限额，不代表模型能力。 Adjustable limits, not model capabilities."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    max_requests: Annotated[int, Field(ge=1)]
    max_tools: Annotated[int, Field(ge=1)]
    max_seconds: Annotated[int, Field(ge=1)]
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
