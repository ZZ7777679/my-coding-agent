"""独立维护的累计计量，作业 ID 保证状态更新不重复计费。

Independent maintenance totals; job identities prevent double-counting state updates.
"""

from pathlib import Path
from typing import Protocol

from pydantic import Field

from my_agent.context.types import UsageSummary
from my_agent.errors import AgentError
from my_agent.models.types import ModelData, TokenUsage
from my_agent.storage import read_document, write_document


class JobUsage(ModelData):
    """仅保留计量，不复制源材料。

    Retain accounting without source material.
    """

    job_id: str
    requests: int
    usage: TokenUsage = Field(
        default_factory=lambda: TokenUsage(input_tokens=None, output_tokens=None)
    )


class MeteredJob(Protocol):
    """压缩与记忆共用的实际计量字段。

    Shared actual accounting fields for both services.
    """

    job_id: str
    requests: int
    usage: TokenUsage


def record_usage(directory: Path, job: MeteredJob) -> None:
    """覆盖同一作业的累计数，保留结束后历史费用。

    Update one job's cumulative values and retain accounting after completion.
    """
    directory.mkdir(parents=True, exist_ok=True)
    write_document(
        directory / (job.job_id + ".json"),
        JobUsage(job_id=job.job_id, requests=job.requests, usage=job.usage),
    )


def usage_totals(directory: Path) -> UsageSummary:
    """局部计量不可读仅提示，不挡正常代码执行。

    Unreadable accounting is reported without blocking code execution.
    """
    total = UsageSummary()
    for path in directory.glob("*.json"):
        try:
            item = read_document(path, JobUsage)
        except AgentError:
            total.unavailable_jobs += 1
            continue
        total.requests += item.requests
        total.reported_input_tokens += item.usage.input_tokens or 0
        total.reported_output_tokens += item.usage.output_tokens or 0
        total.unknown_jobs += int(
            item.requests > 0
            and (item.usage.input_tokens is None or item.usage.output_tokens is None)
        )
    return total
