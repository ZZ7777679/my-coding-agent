"""跨领域身份的单一格式；身份不表达权限。 Shared identity format, not authorization."""

from typing import Annotated

from pydantic import Field

EntityId = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
]
