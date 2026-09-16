"""连接管理的公开事实，不暴露传输私有状态。 Public connection facts without transport internals."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from my_agent.models.types import ModelId, ModelProgress, TokenUsage


class ConnectionSettings(BaseModel):
    """持久化复用偏好与手动探测等待时间。 Persist reuse preference and manual probe timeout."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    reuse_enabled: bool
    probe_timeout_seconds: Annotated[float, Field(gt=0)]


class ConnectionProbeParams(BaseModel):
    """每次手动探测明确指定总等待时间。 Specify the total timeout for one manual probe."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    timeout_seconds: Annotated[float, Field(gt=0)]


class ConnectionObservation(BaseModel):
    """最近一次操作的脱敏结果；历史成功不保证当前在线。

    A sanitized observation of one operation, never a guarantee of current connectivity.
    """

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    finished_at: Annotated[
        str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
    ]
    code: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    http_status: Annotated[int, Field(ge=100, le=599)] | None
    models_confirmed: bool | None
    progress: ModelProgress
    model_id: ModelId | None = None


class ModelConnectionProbeParams(ConnectionProbeParams):
    """显式选择被测模型，不沿用当前会话选择。 Select the tested model explicitly."""

    model_id: ModelId


class ModelConnectionResult(BaseModel):
    """单次真实模型测试的公开结果，不包含提示或回答。

    Public facts from one real model test, excluding prompts and responses.
    """

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    finished_at: Annotated[
        str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
    ]
    code: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    message: str
    remediation: str
    progress: ModelProgress
    usage: TokenUsage | None


class ModelConnectionState(BaseModel):
    """按模型保存正在测试的进度和最近结果；不代表独立套接字。

    Per-model test progress and last result, not a separate physical connection.
    """

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    model_id: ModelId
    testing: bool
    progress: ModelProgress | None
    last_test: ModelConnectionResult | None


class ConnectionStatus(BaseModel):
    """后端自身管理状态，不把客户端个数冒充在线套接字数。

    Backend-owned lifecycle state, without claiming a count of live sockets.
    """

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    reuse_enabled: bool
    client_created: bool
    active_requests: Annotated[int, Field(ge=0)]
    pending_release: bool
    last_request: ConnectionObservation | None
    last_probe: ConnectionObservation | None
    models: list[ModelConnectionState] = Field(default_factory=list)
