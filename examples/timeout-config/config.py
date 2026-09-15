"""故意保留缺陷的 M0 评测样本，修复应在后续任务的独立工作副本进行。

Deliberately faulty M0 evaluation sample; repair it only in a later isolated task copy.
"""


def resolve_timeout(config: dict[str, int]) -> int:
    """读取样本超时值；保留现有缺陷作为后续修复任务的基线。

    Read the sample timeout, preserving the existing defect for a later repair task.
    """

    return config.get("timeout") or 30
