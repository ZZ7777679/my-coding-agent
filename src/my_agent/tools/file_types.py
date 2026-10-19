"""无存储依赖的文件参数契约。

File arguments without storage dependencies.
"""

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from my_agent.models.types import ModelData


class CreateFileArgs(ModelData):
    """创建不存在的 UTF-8 文件。

    Create an absent UTF-8 file.
    """

    path: Annotated[str, Field(min_length=1, max_length=4096)]
    content: str


class EditFileArgs(ModelData):
    """替换唯一当前原文，旧摘要仅兼容接收。

    Replace unique current text; accept legacy hashes only.
    """

    path: Annotated[str, Field(min_length=1, max_length=4096)]
    old_text: Annotated[str, Field(min_length=1)]
    new_text: str
    expected_sha256: SkipJsonSchema[str | None] = None


class SaveFileArgs(ModelData):
    """比较人工缓冲基线，允许空文件。

    Compare human buffer baselines, including empty files.
    """

    path: Annotated[str, Field(min_length=1, max_length=4096)]
    base_content: str
    content: str


class FileOperationArgs(ModelData):
    """操作明确项目路径，不覆盖目的地。

    Operate on selected project paths without overwriting destinations.
    """

    path: Annotated[str, Field(min_length=1, max_length=4096)]
    destination: str | None = None
    recursive: bool = False


class PatchFilesArgs(ModelData):
    """顺序补丁与逐项真实结果。

    Sequential patches with actual per-item outcomes.
    """

    edits: Annotated[list[EditFileArgs], Field(min_length=1, max_length=100)]
