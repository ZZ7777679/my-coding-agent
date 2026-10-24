"""从调用事实提取展示摘要，不改变工具参数。 Present calls without changing tool arguments."""

import json

from my_agent.models.types import ToolCall

_ACTIONS = {
    "read_file": "读取",
    "list_files": "列出文件",
    "search": "搜索",
    "create_file": "创建",
    "edit_file": "修改",
    "patch_files": "批量修改",
    "create_directory": "创建目录",
    "move_file": "移动",
    "delete_file": "删除",
    "run_command": "运行",
    "start_service": "启动服务",
    "start_terminal": "打开终端",
    "read_program": "读取程序输出",
    "stop_program": "停止程序",
    "web_search": "联网搜索",
    "web_fetch": "读取网页",
    "load_skill": "加载 Skill",
    "spawn_worker": "委派子任务",
    "code_insight": "查询代码",
    "view_image": "查看图片",
}


def tool_caption(call: ToolCall) -> str:
    """只摘取动作与目标；长度限制仅用于展示，不截断真实输入。

    Extract action and target; display limits never truncate the recorded input.
    """
    args = call.arguments
    target = next(
        (
            args[key]
            for key in (
                "path",
                "query",
                "url",
                "name",
                "directory",
                "skill_id",
                "server_id",
                "program_id",
                "terminal_id",
                "worker_id",
            )
            if isinstance(args.get(key), str)
        ),
        "",
    )
    command = args.get("command")
    if isinstance(command, str):
        try:
            command = json.loads(command)
        except ValueError:
            target = command
    if isinstance(command, dict):
        if command.get("kind") == "powershell":
            target = "PowerShell · " + str(command.get("script", ""))
        else:
            arguments = command.get("arguments", [])
            target = (
                " ".join(
                    [
                        str(command.get("program", "")),
                        *(
                            str(value)
                            for value in arguments
                            if isinstance(value, (str, int, float))
                        ),
                    ]
                )
                if isinstance(arguments, list)
                else str(command.get("program", ""))
            )
    if call.name == "move_file" and args.get("destination"):
        target = f"{target} → {args['destination']}"
    if call.name == "patch_files" and isinstance(edits := args.get("edits"), list):
        paths = [str(edit["path"]) for edit in edits if isinstance(edit, dict) and "path" in edit]
        target = ", ".join(dict.fromkeys(paths))
    if call.name == "list_files" and not target:
        target = "."
    text = " ".join(str(target).split())
    if len(text) > 160:
        text = text[:159] + "…"
    return _ACTIONS.get(call.name, call.name) + (f" · {text}" if text else "")
