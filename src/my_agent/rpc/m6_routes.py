"""M6 请求回退的显式路由与契约。 Explicit M6 rollback routes and contracts."""

from typing import TYPE_CHECKING

from pydantic import BaseModel

from my_agent.checkpoints.service import RollbackService
from my_agent.checkpoints.types import (
    CheckpointParams,
    PreviewCheckpointParams,
    RestoreCheckpointParams,
)
from my_agent.rpc.m6_types import NavigationItemName, RenameNavigationParams
from my_agent.workflow.style_types import (
    ApplyWorkStyle,
    CaptureWorkStyle,
    ParseWorkStyle,
    SaveWorkStyle,
    WorkStyle,
    WorkStyleDefault,
    WorkStyleQuery,
)
from my_agent.workflow.workstyles import WorkStyleStore

if TYPE_CHECKING:
    from my_agent.rpc.application import RpcApplication

M6_METHODS = (
    "navigation.rename",
    "checkpoints.list",
    "checkpoints.preview",
    "checkpoints.restore",
    "workstyles.list",
    "workstyles.save",
    "workstyles.capture",
    "workstyles.default",
    "workstyles.parse",
    "workstyles.apply",
)


async def dispatch_m6(app: "RpcApplication", method: str, params: dict[str, object]) -> BaseModel:
    """解析一次输入，复用会话服务与文件存储。 Parse input once and reuse session/file services."""
    if method == "navigation.rename":
        rename = RenameNavigationParams.model_validate(params)
        name = rename.name
        if rename.kind == "project":
            await app.worker.call(app.projects.rename, rename.id, name)
        elif rename.kind == "task":
            task = await app.worker.call(
                app.tasks.store.rename, rename.id, rename.operation_id, name
            )
            name = task.fields.title
        else:
            session = await app.sessions.rename(rename.id, rename.operation_id, name)
            name = session.title
        return NavigationItemName(kind=rename.kind, id=rename.id, name=name)
    service = RollbackService(app.sessions)
    styles = WorkStyleStore(app.storage)
    if method == "workstyles.list":
        query_style = WorkStyleQuery.model_validate(params)
        if query_style.project_id:
            await app.sessions.validate_project(query_style.project_id)
        return await app.worker.call(styles.catalog, query_style.project_id)
    if method == "workstyles.save":
        return await app.worker.call(styles.save, SaveWorkStyle.model_validate(params).style)
    if method == "workstyles.capture":
        capture = CaptureWorkStyle.model_validate(params)
        task = await app.worker.call(app.tasks.store.get, capture.task_id)
        root = await app.sessions.validate_project(task.project_id)
        if app.sessions.skills:
            from my_agent.skills.types import SkillParams

            catalog = await app.worker.call(
                app.sessions.skills.catalog,
                SkillParams(project_id=task.project_id, session_id=task.initial_session_id),
            )
            capture.skill_ids = list(dict.fromkeys([*catalog.selected, *capture.skill_ids]))
        return await app.worker.call(styles.capture, task, capture, root)
    if method == "workstyles.default":
        defaults = WorkStyleDefault.model_validate(params)
        await app.sessions.validate_project(defaults.project_id)
        return await app.worker.call(styles.set_default, defaults)
    if method == "workstyles.parse":
        return styles.portable(
            WorkStyle.model_validate_json(ParseWorkStyle.model_validate(params).content)
        )
    if method == "workstyles.apply":
        return await app.tasks.apply_workstyle(ApplyWorkStyle.model_validate(params))
    if method == "checkpoints.list":
        query = CheckpointParams.model_validate(params)
        await app.sessions.view(query.session_id)
        return await app.worker.call(service.store.page, query.session_id)
    if method == "checkpoints.preview":
        return await service.preview(PreviewCheckpointParams.model_validate(params))
    return await service.restore(RestoreCheckpointParams.model_validate(params))
