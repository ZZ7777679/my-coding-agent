"""导出确定性的公开 schema，也可只读检查生成漂移。

Export deterministic public schemas or check for generation drift without writing.
"""

import argparse
import json
from pathlib import Path

from my_agent.rpc.dto import PUBLIC_TYPES

ROOT = Path(__file__).resolve().parents[1]


def build_schema() -> str:
    """合并公开 DTO 与共享定义；同名结构冲突时拒绝生成。

    Merge public DTOs and shared definitions, rejecting conflicting structures with one name.
    """

    definitions: dict[str, object] = {}
    for name, model in PUBLIC_TYPES.items():
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        for key, value in schema.pop("$defs", {}).items():
            if key in definitions and definitions[key] != value:
                raise ValueError("Conflicting schema definition: " + key)
            definitions[key] = value
        definitions[name] = schema
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://my-coding-agent.local/protocol-v12.schema.json",
        "title": "ProtocolV12",
        "type": "object",
        "additionalProperties": False,
        "properties": {name: {"$ref": "#/$defs/" + name} for name in PUBLIC_TYPES},
        "required": list(PUBLIC_TYPES),
        "$defs": definitions,
    }
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    """生成 schema 文件，或在 check 模式下只比较内容。

    Write the schema file or compare its content in check mode.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "schemas/protocol-v12.schema.json"
    content = build_schema()
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit("Schema drift: run scripts/export_schemas.py")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
