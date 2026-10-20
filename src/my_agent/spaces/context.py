"""将成员职责放入现有请求材料，不复制其他会话历史。

Include member duties in the existing request materials without copying peer history.
"""

import json

from my_agent.runtime.context import ContextMaterial, describe_material
from my_agent.spaces.types import SpaceView
from my_agent.spaces.work_graph import work_items
from my_agent.tasks.types import TaskView


def member_context(
    space: SpaceView, session_id: str, task: TaskView | None = None
) -> tuple[str, ContextMaterial] | None:
    """仅为当前绑定会话生成团队简报，关系描述不形成执行门槛。

    Build a brief for the currently bound session; descriptive edges never gate execution.
    """
    binding = next((item for item in space.bindings if item.session_id == session_id), None)
    if binding is None:
        return None
    member = next(
        (item for item in space.config.members if item.member_id == binding.member_id), None
    )
    if member is None:
        return None
    bindings = {item.member_id: item for item in space.bindings}
    items = work_items(task, space) if task is not None else space.config.initial_work_items
    relevant_ids = {item.work_id for item in items if item.owner_member_id == member.member_id}
    owned_ids = set(relevant_ids)
    for item in items:
        # 只带当前工作的直接依赖和反馈，避免数组顺序偶然展开整张图。
        # Include direct neighbors only, independent of node ordering.
        if item.work_id in owned_ids:
            relevant_ids.update(item.depends_on)
            relevant_ids.update(item.feedback_to)
    peers = {
        edge.target_member_id
        if edge.source_member_id == member.member_id
        else edge.source_member_id
        for edge in space.config.edges
        if member.member_id in (edge.source_member_id, edge.target_member_id)
    }
    peers.update(
        item.owner_member_id
        for item in items
        if item.work_id in relevant_ids and item.owner_member_id
    )
    brief = {
        "task_id": space.task_id,
        "space_revision": space.revision,
        "organisation": space.config.organisation,
        "receiver_member_id": space.config.receiver_member_id,
        "current_member": {
            "member_id": member.member_id,
            "name": member.name,
            "role": member.role,
            "scope": member.scope,
        },
        "members": [
            {
                "member_id": peer.member_id,
                "name": peer.name,
                **({"role": peer.role, "scope": peer.scope} if peer.member_id in peers else {}),
                "session_id": bindings[peer.member_id].session_id
                if peer.member_id in bindings
                else None,
            }
            for peer in space.config.members
            if peer.member_id != member.member_id
        ],
        "relationships": [
            edge.model_dump(mode="json")
            for edge in space.config.edges
            if member.member_id in (edge.source_member_id, edge.target_member_id)
        ],
        "current_work_items": [
            item.model_dump(mode="json") for item in items if item.work_id in relevant_ids
        ],
        "other_work_index": [
            {
                "work_id": item.work_id,
                "title": item.title,
                "owner_member_id": item.owner_member_id,
                "status": item.status,
            }
            for item in items
            if item.work_id not in relevant_ids
        ],
        "read_more": "read_task and read_work_status return full work; "
        "list_collaborators returns peer details",
    }
    text = (
        "\n\nCurrent collaboration-space duties supersede older session role/scope notes. "
        "Relations describe planned cooperation, not a tool graph or communication whitelist. "
        "Use existing collaboration tools for the listed sessions within the current request. "
        "Work items belong to this task, not to the reusable template. When changing nodes, "
        "manage_space_work claim activates the node's stage Skills on the next request. "
        "Use selected objectives to decide what to do; graph membership alone grants no new scope. "
        "Use result and status to share progress, including feedback; these updates are optional. "
        "Saving or assembling this team has not itself started a Goal or granted new work.\n"
        + json.dumps(brief, ensure_ascii=False)
    )
    return text, describe_material(
        kind="space",
        title="合作空间与当前成员职责",
        form="reference",
        reason="当前成员职责与任务工作进度；不含其他成员历史",
        source_id=space.task_id,
        revision=space.revision,
        text=text,
    )
