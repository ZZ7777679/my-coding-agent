"""独立 Python 后端包；版本从已安装的项目元数据读取。

Independent Python backend; the installed package metadata supplies its version.
"""

from importlib.metadata import version

__version__ = version("my-agent")
