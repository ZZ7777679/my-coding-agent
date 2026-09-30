"""流程是用户可编辑的数据，不是额外执行运行时。

Workflows are editable task data, not a separate execution runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from my_agent.errors import AgentError
from my_agent.models.types import ModelData
from my_agent.sessions.types import SessionId

if TYPE_CHECKING:
    from pathlib import Path


class WorkflowStage(ModelData):
    """阶段说明与依赖是接续信息，不构成执行门槛。

    Stages describe work without gating execution."""

    stage_id: str
    name: str
    goal: str = ""
    skills: list[str] = Field(default_factory=list)
    artifacts: str = ""
    depends_on: list[str] = Field(default_factory=list)
    feedback_to: list[str] = Field(default_factory=list)
    suggested_role: str = ""


class WorkflowTemplate(ModelData):
    """可分享的流程模板不含机器路径。

    Shareable template without machine-specific paths."""

    template_id: str
    name: str
    description: str = ""
    stages: list[WorkflowStage] = Field(default_factory=list)


class TaskWorkflow(ModelData):
    """模板快照与当前阶段、会话分工独立保存。

    Persist snapshot, current stage and assignments."""

    template: WorkflowTemplate
    current_stage_id: str | None = None
    session_stages: dict[str, str] = Field(default_factory=dict)


class WorkflowCatalog(ModelData):
    """模板目录与单独的加载问题。

    Template catalog and optional loading issues."""

    templates: list[WorkflowTemplate] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class SaveWorkflowParams(ModelData):
    """保存或复制一个模板。

    Save or copy one template."""

    template: WorkflowTemplate


class ParseWorkflowParams(ModelData):
    """导入文本由同一后端契约解析，不立即保存。 Parse imported text without persisting it."""

    content: str


class RemoveWorkflowParams(ModelData):
    """移除模板不修改既有任务。

    Remove a template without changing existing tasks."""

    template_id: str


class UpdateTaskWorkflowParams(ModelData):
    """用户修改任务流程；复用任务版本，不改运行报告。

    Edit task workflow using task revisions."""

    task_id: SessionId
    operation_id: SessionId
    expected_revision: int = Field(ge=1)
    workflow: TaskWorkflow | None


def default_template() -> WorkflowTemplate:
    """内置个人工作方式可复制修改。

    Built-in personal workflow can be copied and edited."""
    stages = [
        ("discuss", "讨论", "澄清目标与约束", "discuss"),
        ("plan", "规划", "安排范围与接续方式", "plan"),
        ("implement", "实现", "完成当前授权的代码工作", "implement"),
        ("verify", "验证", "按需要验证并报告结果", "diagnose"),
        ("review", "审查", "由用户启动独立审查并返回结果", "review"),
        ("handoff", "交接", "保存进度、依据和未决事项", "handoff"),
        ("close", "收尾", "按用户要求确认成果并记录任务状态", "handoff"),
    ]
    return WorkflowTemplate(
        template_id="builtin:personal",
        name="个人开发流程",
        description="可直接实现、跳过、返回或重复阶段；不自动创建会话或授权修复。",
        stages=[
            WorkflowStage(
                stage_id=identity,
                name=name,
                goal=goal,
                skills=["builtin:" + skill],
                depends_on=[stages[index - 1][0]] if index else [],
                feedback_to=["implement"] if identity in {"verify", "review"} else [],
                suggested_role=name,
            )
            for index, (identity, name, goal, skill) in enumerate(stages)
        ],
    )


class WorkflowTemplates:
    """复用数据根原子写入，目录问题不阻断无关任务。

    Atomic templates isolated from ordinary work."""

    def __init__(self, root: Path) -> None:
        """只保存定位，不初始化可选文件。

        Locate optional storage without creating it."""
        self.path = root / "workflow-templates.json"

    def _saved(self) -> WorkflowCatalog:
        """损坏时保留原文件与真实错误。

        Preserve corrupt data and report its error."""
        from my_agent.storage import read_document

        return (
            read_document(self.path, WorkflowCatalog) if self.path.exists() else WorkflowCatalog()
        )

    def list(self) -> WorkflowCatalog:
        """内置模板始终可用，坏配置作为问题展示。

        Keep the builtin available with visible load issues."""
        try:
            saved = self._saved()
        except AgentError as exc:
            return WorkflowCatalog(templates=[default_template()], issues=[exc.message])
        return WorkflowCatalog(templates=[default_template(), *saved.templates])

    def snapshot(self, identity: str | None) -> TaskWorkflow | None:
        """创建时复制模板，后续编辑不会反向改变任务。

        Copy at creation, never mutate existing tasks."""
        if identity is None:
            return None
        template = next((t for t in self.list().templates if t.template_id == identity), None)
        if template is None:
            raise AgentError("WORKFLOW_NOT_FOUND", "所选流程模板不存在，请重新选择。")
        return TaskWorkflow(
            template=template.model_copy(deep=True),
            current_stage_id=template.stages[0].stage_id if template.stages else None,
        )

    def save(self, params: SaveWorkflowParams) -> WorkflowCatalog:
        """按身份保存用户模板；内置模板通过复制修改。

        Save user templates; copy builtins to edit."""
        from my_agent.storage import write_document

        if params.template.template_id == "builtin:personal":
            raise AgentError("WORKFLOW_BUILTIN", "请复制为自定义模板后保存。")
        catalog = self._saved()
        catalog.templates = [
            t for t in catalog.templates if t.template_id != params.template.template_id
        ]
        catalog.templates.append(params.template)
        write_document(self.path, catalog)
        return self.list()

    def remove(self, params: RemoveWorkflowParams) -> WorkflowCatalog:
        """只移除目录条目，任务快照保持不变。

        Remove catalog entries, preserving task snapshots."""
        from my_agent.storage import write_document

        catalog = self._saved()
        catalog.templates = [t for t in catalog.templates if t.template_id != params.template_id]
        write_document(self.path, catalog)
        return self.list()
