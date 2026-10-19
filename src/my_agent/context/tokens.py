"""无需模型调用的本地 token 估算；并非服务端 tokenizer。

Local token estimates without model requests; not a provider tokenizer.
"""

import json
import math
import re


def estimate_tokens(value: object) -> int:
    """按文本类型粗估，包含 JSON 参数、工具和原生续接字段。

    Estimate mixed text including JSON arguments, tools and native continuation fields.
    """
    text = (
        value
        if isinstance(value, str)
        else json.dumps(without_image_bytes(value), ensure_ascii=False)
    )
    # ASCII 与非 ASCII 分开计量；CJK 并不等同英文四字符一 token。
    # Price ASCII and non-ASCII separately; CJK is not English at four characters per token.
    ascii_chars = sum(len(match[0]) for match in re.finditer(r"[\x00-\x7f]+", text))
    return math.ceil(ascii_chars / 4 + (len(text) - ascii_chars) * 1.5)


def without_image_bytes(value: object) -> object:
    """
    图片传输字节不计为正文 token；实际用量由服务返回。
    Exclude transport image bytes from text tokens; actual usage comes
    from the provider.
    """
    if isinstance(value, str) and value.startswith("data:image/"):
        return "[image: token usage unknown]"
    if isinstance(value, dict):
        return {key: without_image_bytes(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [without_image_bytes(item) for item in value]
    return value


def head_tail(text: str, budget: int) -> str:
    """在估计 token 预算内保留头尾，明确中间省略。

    Keep head and tail within an estimated token budget, marking the omitted middle.
    """
    if estimate_tokens(text) <= budget:
        return text
    marker = "\n[… omitted …]\n"
    low, high = 0, len(text)
    while low < high:
        size = (low + high + 1) // 2
        head = (size + 1) // 2
        tail = size // 2
        preview = text[:head] + marker + (text[-tail:] if tail else "")
        if estimate_tokens(preview) <= budget:
            low = size
        else:
            high = size - 1
    if not low:
        return ""
    tail = low // 2
    return text[: (low + 1) // 2] + marker + (text[-tail:] if tail else "")
