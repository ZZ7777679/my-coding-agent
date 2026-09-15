"""样本已有的基础用例；不代表其独立验收已通过。

Existing sample baseline tests; passing these does not imply acceptance success.
"""

from config import resolve_timeout


def test_missing_timeout():
    """确认缺省输入使用样本默认超时。

    Confirm omitted input uses the sample default timeout.
    """

    assert resolve_timeout({}) == 30


def test_positive_timeout():
    """确认正数超时按输入保留。

    Confirm a positive timeout preserves the supplied value.
    """

    assert resolve_timeout({"timeout": 10}) == 10
