"""复用桌面 Git 服务的模型工具。

Model tools reusing the desktop Git service."""

from pydantic import ValidationError

from my_agent.errors import AgentError
from my_agent.local_git.service import LocalGitService
from my_agent.local_git.types import (
    GitCommitParams,
    GitDiffParams,
    GitHistoryParams,
    GitPathsParams,
    GitProjectParams,
)
from my_agent.models.types import JsonObject, ModelData, ToolCall, ToolResult
from my_agent.runtime.tools import ToolContext, ToolExecutor
from my_agent.tools.arguments import argument_message
from my_agent.tools.policy import checkpoint
from my_agent.tools.read_only import encode

GIT_TOOLS: dict[str, tuple[type[GitProjectParams], str]] = {
    "git_status": (
        GitProjectParams,
        "Read local worktree/index status. Reports disabled or unavailable Git; never initializes.",
    ),
    "git_diff": (
        GitDiffParams,
        "Read one path's worktree diff (against index) or index diff (against HEAD). Never stages.",
    ),
    "git_log": (GitHistoryParams, "Read local commit history; no remote access."),
    "git_stage": (
        GitPathsParams,
        "Stage explicitly selected project paths for the user's requested commit. "
        "No automatic staging of other files.",
    ),
    "git_unstage": (
        GitPathsParams,
        "Remove selected paths from the index while preserving worktree files.",
    ),
    "git_commit": (
        GitCommitParams,
        "Commit the repository's ENTIRE existing index when requested by the user. "
        "Inspect git_status first; do not configure identity or remote.",
    ),
    "git_init": (
        GitProjectParams,
        "Initialize a local repository at this project's root only when requested. "
        "No remote or identity changes.",
    ),
}
READ_GIT_TOOLS = {"git_status", "git_diff", "git_log"}


class GitTools:
    """以宿主项目身份执行本地 Git，复用预算、取消和归档。

    Local Git with host identity, budgets, cancellation and archives."""

    def __init__(
        self, context: ToolContext, delegate: ToolExecutor, service: LocalGitService
    ) -> None:
        """注入共用服务，不创建另一套 Git 运行器。

        Inject the shared service, not another Git runner."""
        self.context, self.delegate, self.service = context, delegate, service

    def definitions(self) -> list[JsonObject]:
        """Plan 只提供读取；开关由服务实时检查。

        Expose reads in Plan; the service checks the switch live."""
        result = self.delegate.definitions()
        for name, (model, description) in GIT_TOOLS.items():
            if self.context.mode == "plan" and name not in READ_GIT_TOOLS:
                continue
            schema = model.model_json_schema()
            schema["properties"].pop("project_id")
            schema["required"].remove("project_id")
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description + " Project Git must be enabled in the UI. "
                        "Respect the user's disabled switch; do not recreate Git via shell.",
                        "parameters": schema,
                    },
                }
            )
        return result

    def is_mutating(self, name: str) -> bool:
        """准确区分读取与仓库副作用。

        Distinguish reads from repository effects."""
        return name not in READ_GIT_TOOLS if name in GIT_TOOLS else self.delegate.is_mutating(name)

    async def execute(self, call: ToolCall) -> ToolResult:
        """只解析一次输入，真实失败沿运行时原规则报告。

        Parse once and preserve real execution failures."""
        if call.name not in GIT_TOOLS:
            return await self.delegate.execute(call)
        try:
            checkpoint(self.context.stop)
            if self.context.mode == "plan" and call.name not in READ_GIT_TOOLS:
                raise AgentError(
                    "INVALID_TOOL_ARGUMENTS", "Plan 模式仅支持 Git 状态、差异和历史读取。"
                )
            if "project_id" in call.arguments:
                raise AgentError(
                    "INVALID_TOOL_ARGUMENTS", "Git 工具使用当前项目，无需传入 project_id。"
                )
            model = GIT_TOOLS[call.name][0]
            args = model.model_validate({**call.arguments, "project_id": self.context.project_id})
            result: ModelData
            if isinstance(args, GitDiffParams):
                result = await self.service.diff(args)
            elif isinstance(args, GitHistoryParams):
                result = await self.service.history(args)
            elif isinstance(args, GitPathsParams):
                result = await (
                    self.service.stage(args)
                    if call.name == "git_stage"
                    else self.service.unstage(args)
                )
            elif isinstance(args, GitCommitParams):
                result = await self.service.commit(args)
            else:
                result = await (
                    self.service.init(args)
                    if call.name == "git_init"
                    else self.service.status(args)
                )
            content = result.model_dump_json()
            if len(content.encode("utf-8")) > self.context.limits.max_tool_bytes:
                archive = (
                    await self.context.archive_output(content)
                    if self.context.archive_output
                    else None
                )
                content = encode(
                    {
                        "truncated": True,
                        "archive_id": archive,
                        "preview": content[: self.context.limits.max_tool_bytes // 8],
                        "message": "使用 read_history 的 archive_id 回读完整结果。"
                        if archive
                        else "请缩小查询或调高工具输出预算。",
                    }
                )
            return ToolResult(tool_call_id=call.tool_call_id, content=content, is_error=False)
        except ValidationError as exc:
            return ToolResult(
                tool_call_id=call.tool_call_id,
                is_error=True,
                content=encode(
                    {"code": "INVALID_TOOL_ARGUMENTS", "message": argument_message(exc)}
                ),
            )
        except AgentError as exc:
            if exc.code == "CANCELLED":
                raise
            correctable = exc.code in {
                "GIT_DISABLED",
                "GIT_PATH_INVALID",
                "GIT_REPOSITORY_REQUIRED",
                "PROGRAM_UNAVAILABLE",
            }
            return ToolResult(
                tool_call_id=call.tool_call_id,
                is_error=True,
                content=encode(
                    {
                        "code": "INVALID_TOOL_ARGUMENTS" if correctable else exc.code,
                        "cause_code": exc.code,
                        "message": exc.message,
                    }
                ),
            )
