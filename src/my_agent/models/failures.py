"""按真实异常类型说明请求失败，不从最后一个输出阶段推测原因。

Explain failures from exception types, never from the last output phase.
"""

import httpx

from my_agent.errors import AgentError
from my_agent.models.timing import RequestTiming
from my_agent.models.types import TokenUsage


class ModelResponseError(AgentError):
    """保留失败响应的结束原因与真实用量，不携带模型原文。

    Retain a failed response's stop reason and usage without carrying response text.
    """

    def __init__(
        self, code: str, message: str, usage: TokenUsage, finish_reason: str | None
    ) -> None:
        """向调用方交付已观察到的统计。 Pass observed statistics to the caller."""
        super().__init__(code, message)
        self.usage = usage
        self.finish_reason = finish_reason


def request_failure(error: BaseException, timing: RequestTiming, timeout: float) -> AgentError:
    """区分总时限、网络等待与传输失败，仅公开时间和稳定类别。

    Distinguish deadlines, network waits and transport failures using public timing and categories.
    """
    if isinstance(error, httpx.ConnectTimeout):
        code, message = "MODEL_CONNECT_TIMEOUT", "建立模型连接超时。"
    elif isinstance(error, httpx.ReadTimeout):
        code = "MODEL_READ_TIMEOUT"
        message = (
            "等待模型响应头超时。"
            if timing.progress.response_headers_ms is None
            else "等待后续响应数据超时。"
        )
    elif isinstance(error, httpx.WriteTimeout):
        code, message = "MODEL_WRITE_TIMEOUT", "发送模型请求数据超时。"
    elif isinstance(error, httpx.PoolTimeout):
        code, message = "MODEL_POOL_TIMEOUT", "等待可用模型连接超时。"
    elif isinstance(error, TimeoutError):
        code = "MODEL_REQUEST_TIMEOUT"
        message = f"模型请求达到设定的 {timeout:g} 秒总时限，未收到完整回合。"
    elif isinstance(error, httpx.ProxyError):
        code, message = "MODEL_PROXY_ERROR", "模型请求的代理连接失败。"
    elif isinstance(error, httpx.ConnectError):
        code, message = "MODEL_CONNECT_ERROR", "建立模型连接失败。"
    elif isinstance(error, (httpx.ReadError, httpx.RemoteProtocolError)):
        code, message = "MODEL_STREAM_ERROR", "读取模型响应时发生连接或传输协议错误。"
    elif isinstance(error, httpx.WriteError):
        code, message = "MODEL_WRITE_ERROR", "发送模型请求失败。"
    else:
        code, message = "MODEL_NETWORK", "模型请求发生网络传输错误。"
    if timing.progress.last_data_ms is not None:
        gap = max(0, timing.milliseconds() - timing.progress.last_data_ms) / 1000
        phase = {
            "reasoning": "思考片段",
            "tool_arguments": "工具参数片段（尚未执行）",
            "text": "回答正文片段",
        }.get(timing.progress.phase, "响应数据")
        message += (
            f"已接收 {(timing.progress.received_bytes or 0) / 1024:.1f} KiB，"
            f"最后观测为{phase}；结束前 {gap:.1f} 秒未收到新数据。"
        )
    else:
        message += "尚未收到响应正文数据。"
    return AgentError(code, message + " 未自动重试。")
