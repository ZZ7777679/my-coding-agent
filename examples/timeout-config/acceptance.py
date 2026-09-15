"""独立验收断言，用于暴露样本缺陷；当前基线预期失败。

Independent acceptance assertion exposing the sample defect; the baseline should fail.
"""

from config import resolve_timeout

if __name__ == "__main__":
    assert resolve_timeout({"timeout": 0}) == 0, "Explicit zero must mean no timeout"
