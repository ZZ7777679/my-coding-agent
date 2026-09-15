"""管理受信应用配置；不从用户项目加载应用设置。

Manage trusted application configuration independently of user projects.
"""

import json
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from my_agent.errors import AgentError, DataSource
from my_agent.rpc.dto import CredentialInfo, ModelId, PublicConfig

DEFAULTS = json.loads(files("my_agent").joinpath("defaults.json").read_text(encoding="utf-8"))
DEFAULT_DATA_DIR: str = DEFAULTS["data_dir"]
DATA_DIR_ENV: str = DEFAULTS["data_dir_env"]
MAX_FRAME_BYTES: int = DEFAULTS["max_frame_bytes"]
MODEL_DEFAULTS: dict[str, object] = DEFAULTS["model"]


class ModelConfig(BaseModel):
    """约束当前阶段的 Go 服务与双模型配置，拒绝额外字段。

    Constrain Go settings to the two supported models and reject extra fields.
    """

    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Literal["opencode-go"]
    base_url: Literal["https://opencode.ai/zen/go/v1"]
    api: Literal["chat_completions"]
    model_id: ModelId
    allowed_models: list[ModelId]
    api_key_env: Literal["OPENCODE_API_KEY"]

    @field_validator("allowed_models")
    @classmethod
    def fixed_models(cls, value: list[ModelId]) -> list[ModelId]:
        """保留完整双模型白名单，不把显示顺序当作配置有效性条件。

        Require the complete two-model allowlist without constraining its display order.
        """

        allowed = get_args(ModelId)
        if len(value) != len(allowed) or set(value) != set(allowed):
            raise ValueError("Unsupported model list")
        return value


@dataclass(frozen=True)
class DataLocation:
    """保存规范化数据根及其来源，不创建目录。

    Hold a canonical data root and its source without creating directories.
    """

    root: Path
    source: DataSource


@dataclass(frozen=True)
class LoadedConfig:
    """保存已验证模型配置、文件位置与生效来源。

    Hold validated model settings, their file location and effective source.
    """

    model: ModelConfig
    path: Path
    model_source: Literal["default", "user", "cli"]

    def public(self, credential: CredentialInfo) -> PublicConfig:
        """组装可发送给前端的配置，只包含凭据元信息。

        Build renderer-safe configuration containing only credential metadata.
        """

        return PublicConfig(
            provider=self.model.provider,
            base_url=self.model.base_url,
            api=self.model.api,
            model_id=self.model.model_id,
            allowed_models=self.model.allowed_models,
            credential=credential,
            config_path=str(self.path),
            model_source=self.model_source,
        )


def resolve_data_dir(
    explicit: str | None = None, environ: Mapping[str, str] | None = None
) -> DataLocation:
    """按参数、环境变量、默认值解析数据根；失效时不回退或创建目录。

    Resolve the data root by CLI, environment, then defaults; never fall back or create it.
    """

    env = os.environ if environ is None else environ
    source: DataSource = "default"
    value = DEFAULT_DATA_DIR
    if DATA_DIR_ENV in env:
        source, value = "environment", env[DATA_DIR_ENV]
    if explicit is not None:
        source, value = "cli", explicit
    path = Path(value)
    if not value.strip() or not path.is_absolute():
        raise AgentError("DATA_DIR_INVALID", "应用数据目录必须是完整的绝对路径。")
    try:
        root = path.resolve()
        if not Path(root.anchor).is_dir():
            raise AgentError(
                "DATA_DIR_UNAVAILABLE", "应用数据所在磁盘不可用。", "连接磁盘或指定其他数据目录。"
            )
        if root.exists() and not root.is_dir():
            raise AgentError("DATA_DIR_INVALID", "应用数据路径必须是文件夹。")
    except (OSError, RuntimeError) as exc:
        raise AgentError("DATA_DIR_UNAVAILABLE", "无法访问应用数据目录。") from exc
    return DataLocation(root, source)


def load_config(location: DataLocation, model_override: str | None = None) -> LoadedConfig:
    """合并默认、用户文件和模型覆盖；损坏配置保留并返回明确错误。

    Merge defaults, user settings and overrides; preserve invalid files and report errors.
    """

    path = location.root / "config.toml"
    values = dict(MODEL_DEFAULTS)
    source: Literal["default", "user", "cli"] = "default"
    try:
        if path.exists():
            if path.stat().st_size > 65536:
                raise AgentError("CONFIG_INVALID", "配置文件超过大小限制。")
            content = tomllib.loads(path.read_text(encoding="utf-8"))
            if set(content) - {"model"} or not isinstance(content.get("model", {}), dict):
                raise AgentError("CONFIG_INVALID", "配置只支持 model 表，请检查字段名称。")
            user_model: dict[str, object] = content.get("model", {})
            values.update(user_model)
            if "model_id" in user_model:
                source = "user"
        if model_override is not None:
            values["model_id"], source = model_override, "cli"
        model = ModelConfig.model_validate(values)
    except (ValidationError, tomllib.TOMLDecodeError, UnicodeError) as exc:
        raise AgentError(
            "CONFIG_INVALID", "model 配置无效，请检查字段、类型和允许的模型。"
        ) from exc
    except OSError as exc:
        raise AgentError("CONFIG_UNAVAILABLE", "无法读取应用配置。") from exc
    return LoadedConfig(model, path, source)


def model_config_text(model: ModelConfig) -> str:
    """将已验证的模型字段写成 TOML 文本，不保留原文件注释与排版。

    Serialize validated model fields as TOML without preserving file comments or layout.
    """

    lines = ["[model]"]
    for key, value in model.model_dump().items():
        lines.append(key + " = " + json.dumps(value, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def default_config_text() -> str:
    """从集中默认值生成首次初始化使用的配置文本。

    Render initial configuration from the centralized defaults.
    """

    return model_config_text(ModelConfig.model_validate(MODEL_DEFAULTS))


def default_model() -> ModelId:
    # 先校验默认资源，使返回值符合公开模型契约。
    # Validate the defaults before returning an ID from the public model contract.
    """从经校验的默认配置读取初始模型标识。

    Read the initial model ID from validated defaults.
    """

    return ModelConfig.model_validate(MODEL_DEFAULTS).model_id
