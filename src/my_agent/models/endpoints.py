"""统一 Go 协议端点，并兼容已保存的旧地址。

Resolve Go protocol endpoints while accepting the previously saved base URL.
"""

import json
from importlib.resources import files

_DEFAULTS = json.loads(files("my_agent").joinpath("defaults.json").read_text(encoding="utf-8"))
GO_BASE_URL: str = _DEFAULTS["model"]["base_url"]
LEGACY_GO_BASE_URL: str = _DEFAULTS["go_endpoints"]["legacy_base_url"]
GO_MESSAGES_URL: str = _DEFAULTS["go_endpoints"]["messages_url"]
GO_MODELS_URL: str = _DEFAULTS["go_endpoints"]["models_url"]


def current_base_url(value: str) -> str:
    """只映射已知 Go 旧地址，显式直连适配地址保持原样。

    Map the known legacy Go URL without changing explicit direct-provider adapters.
    """
    base = value.rstrip("/")
    return GO_BASE_URL if base == LEGACY_GO_BASE_URL else base


def messages_url(base_url: str) -> str:
    """Messages 使用独立协议路由，不能拼在 OpenAI 前缀下。

    Resolve the separate Messages route instead of appending it to the OpenAI prefix.
    """
    base = current_base_url(base_url)
    return GO_MESSAGES_URL if base == GO_BASE_URL else base + "/messages"
