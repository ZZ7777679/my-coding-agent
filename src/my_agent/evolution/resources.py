"""通过已有服务读写改进目标，保留原资源的职责。

Read/write improvement targets through existing services.
"""

import asyncio
import base64
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid4, uuid5

from my_agent.changes.store import ChangeStore
from my_agent.config import load_config
from my_agent.errors import AgentError
from my_agent.evolution.store import EvolutionStore
from my_agent.evolution.types import (
    EvolutionCandidate,
    EvolutionResource,
    EvolutionTarget,
)
from my_agent.memory.store import MemoryStore
from my_agent.memory.types import (
    MemoryEntry,
    MemoryEvolutionSource,
    MemoryFields,
    MemoryTraceSource,
)
from my_agent.models.types import ModelData, ToolCall
from my_agent.runtime.tools import ToolContext
from my_agent.sessions.store import SessionLog
from my_agent.sessions.trace import trace_items
from my_agent.skills.service import parse_skill
from my_agent.skills.types import SaveSkillParams, SkillCatalog, SkillParams, SkillReadParams
from my_agent.storage import read_document, write_document
from my_agent.tools.file_types import CreateFileArgs, FileOperationArgs, SaveFileArgs
from my_agent.tools.files import FileCoordinator, FileTools
from my_agent.workflow.style_types import WorkStyle
from my_agent.workflow.workstyles import WorkStyleStore

if TYPE_CHECKING:
    from my_agent.sessions.service import SessionService


class ToolGuidance(ModelData):
    """工具说明补充独立于服务器 schema。

    Supplemental guidance never replaces the server schema.
    """

    name: str
    content: str
    revision: int = 1
    candidate_id: str


class EvolutionResources:
    """复用记忆、Skill、工作方式和文件服务，不复制其执行规则。

    Reuse memory, Skill, workstyle and file services without duplicating execution rules.
    """

    def __init__(self, sessions: "SessionService") -> None:
        """绑定应用实例和已有文件协调器。

        Bind the app instance and shared file coordinator.
        """
        self.sessions = sessions
        self.storage = sessions.store.storage
        self.memory = MemoryStore(self.storage)
        self.styles = WorkStyleStore(self.storage)
        self.coordinator = sessions.file_coordinator or FileCoordinator()

    async def file_tools(self, project_id: str, identity: str) -> FileTools:
        """改进写入使用维护身份，不自动创建正式会话。

        Use maintenance identity without creating a formal session.
        """
        root = await self.sessions.validate_project(project_id)
        config = await self.sessions.worker.call(load_config, self.storage.location)
        context = ToolContext(
            root=root,
            limits=config.run,
            stop=threading.Event(),
            project_id=project_id,
            session_id=identity,
            run_id=identity,
            mode="normal",
            plan_document=None,
        )
        return FileTools(context, ChangeStore(self.storage), self.sessions.worker, self.coordinator)

    def guidance_path(self, project_id: str, name: str) -> Path:
        """用稳定内部身份存储任意工具名称。

        Store tool names under stable internal identities.
        """
        return (
            self.storage.root
            / "evolution"
            / project_id
            / "guidance"
            / (str(uuid5(NAMESPACE_URL, name)) + ".json")
        )

    def guidance(self, project_id: str) -> list[ToolGuidance]:
        """读取项目工具补充；单项损坏不隐藏错误。

        Read project guidance without concealing damaged entries.
        """
        directory = self.storage.root / "evolution" / project_id / "guidance"
        return [read_document(path, ToolGuidance) for path in directory.glob("*.json")]

    async def read(self, project_id: str, target: EvolutionTarget) -> EvolutionResource:
        """读取真实当前值；不存在的新资源明确为 null。

        Read actual current content; absent new resources are null.
        """
        await self.sessions.validate_project(project_id)
        worker = self.sessions.worker
        if target.kind in {"preference", "memory"}:
            if not target.identity or not self.memory.path(target.identity).exists():
                return EvolutionResource(target=target, content=None, label="新记忆")
            entry = await worker.call(self.memory.read, target.identity, project_id)
            fields = MemoryFields.model_validate(
                entry.model_dump(include=set(MemoryFields.model_fields))
            )
            return EvolutionResource(
                target=target.model_copy(update={"scope": entry.scope}),
                content=fields.model_dump_json(indent=2),
                label=entry.title,
                version=str(entry.revision),
            )
        if target.kind == "workstyle":
            style = await worker.call(self.styles.load, target.identity)
            return EvolutionResource(
                target=target.model_copy(update={"scope": "user"}),
                content=style.model_dump_json(indent=2, exclude={"updated_at"}),
                label=style.name,
                version=style.updated_at,
            )
        if target.kind == "tool_guidance":
            path = self.guidance_path(project_id, target.identity)
            item = await worker.call(read_document, path, ToolGuidance) if path.exists() else None
            files = await self.file_tools(project_id, str(uuid4()))
            definitions = self.sessions.tool_factory(files.context).definitions()
            definition = next(
                (
                    entry
                    for entry in definitions
                    if isinstance(function := entry.get("function"), dict)
                    and function.get("name") == target.identity
                ),
                None,
            )
            return EvolutionResource(
                target=target.model_copy(update={"scope": "project"}),
                content=item.content if item else None,
                label=target.identity,
                version=str(item.revision) if item else None,
                reference_content=(
                    json.dumps(definition, ensure_ascii=False, indent=2)
                    if definition
                    else "当前工具目录没有此定义；不能据此推断实现行为。"
                ),
            )
        if target.kind == "skill":
            skills = self.sessions.skills
            if skills is None:
                raise AgentError("SKILL_UNAVAILABLE", "Skill 服务未装配。")
            if target.identity.startswith("project:"):
                pieces = target.identity.split(":")
                if len(pieces) != 3 or pieces[1] != project_id:
                    raise AgentError("PROJECT_MISMATCH", "项目 Skill 不属于当前项目。")
                target = target.model_copy(update={"scope": "project"})
            elif target.identity.startswith("user:"):
                target = target.model_copy(update={"scope": "user"})
            elif not target.identity.startswith("builtin:"):
                prefix = f"project:{project_id}:" if target.scope == "project" else "user:"
                target = target.model_copy(update={"identity": prefix + target.identity})
            catalog = await worker.call(skills.catalog, SkillParams(project_id=project_id))
            item = next((item for item in catalog.items if item.skill_id == target.identity), None)
            reference_content = None
            if item and item.source == "builtin":
                original = await worker.call(
                    skills.read, SkillReadParams(project_id=project_id, skill_id=item.skill_id)
                )
                reference_content = original.content
                target = target.model_copy(
                    update={"scope": "user", "identity": "user:" + item.name}
                )
                item = next(
                    (entry for entry in catalog.items if entry.skill_id == target.identity), None
                )
            if item is None:
                return EvolutionResource(
                    target=target,
                    content=None,
                    label=target.identity,
                    reference_content=reference_content,
                )
            document = await worker.call(
                skills.read, SkillReadParams(project_id=project_id, skill_id=item.skill_id)
            )
            return EvolutionResource(
                target=target.model_copy(update={"scope": item.source}),
                content=document.content,
                label=item.name,
                version=item.version,
                reference_content=reference_content,
            )
        tools = await self.file_tools(project_id, str(uuid4()))
        file_path = target.identity or "AGENTS.md"
        target = target.model_copy(update={"identity": file_path, "scope": "project"})
        # 读取改进目标与写入范围一致；不是扫描任意宿主目录。
        # Read the same project target that adoption can write, not arbitrary host files.
        try:
            await asyncio.to_thread(tools._operation_target, file_path)
        except AgentError as exc:
            if exc.code != "FILE_NOT_FOUND":
                raise
            await asyncio.to_thread(tools._operation_target, file_path, new=True)
            return EvolutionResource(target=target, content=None, label=file_path)
        content, _, _ = await asyncio.to_thread(tools.read._read, file_path)
        return EvolutionResource(target=target, content=content, label=file_path)

    async def memory_sources(
        self, candidate: EvolutionCandidate
    ) -> tuple[list[MemoryTraceSource], list[str]]:
        """从实际作业材料或模型提案的当前运行保留记忆来源。

        Retain memory provenance from accepted job materials or a proposal's current run.
        """
        worker = self.sessions.worker
        store = EvolutionStore(self.storage)
        sources = candidate.sources
        # 候选已按发现关联实际阅读；不能在采用时扩大为整次调查。
        # Candidate links already select actual reads; adoption must not expand to the whole job.
        selected: set[tuple[str, int]] = set()
        for source in sources:
            if not source.session_id:
                continue
            log = await self.sessions._load(source.session_id)
            if source.through_seq is not None:
                log = SessionLog(
                    log.session_id,
                    [fact for fact in log.facts if fact.seq <= source.through_seq],
                )
            rows = await worker.call(trace_items, log)
            for row in rows:
                if (
                    (source.seq is not None and row.seq == source.seq)
                    or (source.seq is None and source.run_id and row.run_id == source.run_id)
                    or (source.seq is None and source.run_id is None and source.scope == "session")
                ):
                    # 合并行的结果／模型回复也必须失效，而非只关联调用起点。
                    # Invalidate paired results/replies too, not just their starting facts.
                    selected.add((log.session_id, row.seq))
                    selected.add((log.session_id, row.updated_seq))
        memory_ids = [
            ref.target.identity
            for ref in candidate.resource_sources
            if ref.target.kind in {"memory", "preference"}
            and ref.target.identity
            and ref.target.identity != candidate.target.identity
        ]
        # 旧人工候选保留显式反馈关联；新调查使用逐候选的实际资源来源。
        # Preserve legacy explicit feedback links; new investigations use candidate-specific reads.
        for identity in dict.fromkeys(candidate.feedback_ids if not candidate.finding_id else []):
            feedback = await worker.call(store.read_feedback, candidate.project_id, identity)
            if feedback.target and feedback.target.kind in {"memory", "preference"}:
                if (
                    feedback.target.identity
                    and feedback.target.identity != candidate.target.identity
                ):
                    memory_ids.append(feedback.target.identity)
        return (
            [
                MemoryTraceSource(session_id=session_id, seq=seq)
                for session_id, seq in sorted(selected)
            ],
            memory_ids,
        )

    async def write(
        self, candidate: EvolutionCandidate, *, revert: bool, automatic: bool = False
    ) -> None:
        """采用或恢复一个资源；基线变化只影响该候选，不阻断业务任务。

        Adopt or restore one resource; changed baselines affect only this candidate.
        """
        target = candidate.target
        desired, expected = (
            (candidate.before, candidate.after) if revert else (candidate.after, candidate.before)
        )
        current = await self.read(candidate.project_id, target)
        if current.content != expected:
            raise AgentError(
                "EVOLUTION_TARGET_CHANGED",
                "目标已被其他工作修改，请刷新候选后再采用；原任务不受影响。",
            )
        worker = self.sessions.worker
        if target.kind in {"preference", "memory"}:
            fields = MemoryFields.model_validate_json(desired) if desired is not None else None
            trace_sources, memory_ids = (
                await self.memory_sources(candidate) if automatic and not revert else ([], [])
            )
            if fields is not None and not revert:
                fields.scope = target.scope
                if target.kind == "preference":
                    fields.category = "preference"
                    fields.pinned = True
            evolution_sources = [
                MemoryEvolutionSource(
                    project_id=candidate.project_id,
                    candidate_id=source.candidate_id,
                    content_revision=source.content_revision,
                    status=source.candidate_status or "unknown",
                    comparison_at=source.comparison_at,
                )
                for source in candidate.sources
                if source.candidate_id and source.content_revision
            ]

            def save_memory() -> MemoryEntry | None:
                """同一写线程内比较后保存，避免排队期间覆盖用户改动。

                Compare and save on the writer without overwriting queued user changes.
                """
                if target.identity:
                    latest = self.memory.read(target.identity, candidate.project_id)
                    if str(latest.revision) != current.version:
                        raise AgentError("EVOLUTION_TARGET_CHANGED", "记忆刚被更新，未覆盖。")
                    if automatic and not revert:
                        trace_sources.extend(latest.trace_sources)
                        if latest.session_id and latest.source_seq is not None:
                            trace_sources.append(
                                MemoryTraceSource(
                                    session_id=latest.session_id, seq=latest.source_seq
                                )
                            )
                        memory_ids.extend(latest.source_ids)
                if fields is None:
                    self.memory.forget(target.identity, candidate.project_id)
                    return None
                if automatic and not revert:
                    fields.source_ids = list(dict.fromkeys([*fields.source_ids, *memory_ids]))
                    for ref in candidate.resource_sources:
                        if ref.target.identity not in memory_ids:
                            continue
                        try:
                            origin = self.memory.read(ref.target.identity, candidate.project_id)
                            fields.stale = (
                                fields.stale
                                or origin.stale
                                or not origin.enabled
                                or (ref.version is not None and str(origin.revision) != ref.version)
                            )
                        except AgentError:
                            # 来源变化只影响经验召回，不阻断候选保存。
                            # Changed sources affect recall, never candidate persistence.
                            fields.stale = True
                return self.memory.save(
                    candidate.project_id,
                    fields,
                    identity=target.identity or None,
                    source="agent" if automatic else "user",
                    trace_sources=list(
                        {
                            (source.session_id, source.seq): source for source in trace_sources
                        }.values()
                    ),
                    evolution_sources=evolution_sources,
                )

            entry = await worker.call(save_memory)
            if entry is None:
                candidate.target = target.model_copy(update={"identity": ""})
                return
            candidate.target = target.model_copy(update={"identity": entry.memory_id})
            # 保存规范化正文，恢复比较使用实际写入值。
            # Preserve normalized content so restoration compares actual stored data.
            if not revert:
                candidate.after = MemoryFields.model_validate(
                    entry.model_dump(include=set(MemoryFields.model_fields))
                ).model_dump_json(indent=2)
            return
        if target.kind == "workstyle":
            if desired is None:
                raise AgentError("EVOLUTION_TARGET_MISSING", "工作方式目标必须是已有模板。")
            style = WorkStyle.model_validate_json(desired)
            if style.style_id != target.identity:
                raise AgentError("INVALID_TOOL_ARGUMENTS", "工作方式身份与目标不一致。")

            def save_style() -> WorkStyle:
                """保存前保留排队期间的人工模板更新。

                Preserve template edits made while adoption was queued.
                """
                latest = self.styles.load(target.identity)
                if latest.updated_at != current.version:
                    raise AgentError("EVOLUTION_TARGET_CHANGED", "工作方式刚被更新，未覆盖。")
                return self.styles.save(style)

            saved = await worker.call(save_style)
            if not revert:
                candidate.after = saved.model_dump_json(indent=2, exclude={"updated_at"})
            return
        if target.kind == "tool_guidance":
            path = self.guidance_path(candidate.project_id, target.identity)

            def save_guidance() -> None:
                """比较与保存说明属于同一个写入操作。

                Compare and save guidance in one writer operation.
                """
                latest = read_document(path, ToolGuidance).content if path.exists() else None
                if latest != expected:
                    raise AgentError("EVOLUTION_TARGET_CHANGED", "工具说明刚被更新，未覆盖。")
                if desired is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    write_document(
                        path,
                        ToolGuidance(
                            name=target.identity,
                            content=desired,
                            candidate_id=candidate.candidate_id,
                            revision=int(current.version or "0") + 1,
                        ),
                    )

            await worker.call(save_guidance)
            return
        if target.kind == "skill":
            skills = self.sessions.skills
            if skills is None:
                raise AgentError("SKILL_UNAVAILABLE", "Skill 服务未装配。")

            def latest_skill() -> str | None:
                """读取确切身份的当前正文，缺失和读取失败不同。

                Read the exact resource; absence differs from read failure.
                """
                catalog = skills.catalog(SkillParams(project_id=candidate.project_id))
                found = next(
                    (item for item in catalog.items if item.skill_id == target.identity), None
                )
                if found is None:
                    return None
                return skills.read(
                    SkillReadParams(
                        project_id=candidate.project_id,
                        skill_id=target.identity,
                    )
                ).content

            if desired is None:
                # 恢复新资源只移除本次正文，附属文件保留。
                # Restoring a newly created resource removes only its body, preserving assets.
                document = await worker.call(
                    skills.read,
                    SkillReadParams(project_id=candidate.project_id, skill_id=target.identity),
                )

                def remove_skill() -> None:
                    """恢复只移除本次创建的正文。

                    Restoration removes only the body introduced by this candidate.
                    """
                    if latest_skill() != expected:
                        raise AgentError("EVOLUTION_TARGET_CHANGED", "Skill 刚被更新，未删除。")
                    Path(document.item.path).unlink()

                await worker.call(remove_skill)
                return
            name, _ = parse_skill(desired)
            if target.identity.split(":")[-1] != name:
                raise AgentError(
                    "SKILL_NAME_MISMATCH", "候选名称与目标不同，请作为新的 Skill 保存。"
                )

            def save_skill() -> SkillCatalog:
                """排队期间的新 Skill 修改必须保留。

                Preserve intervening Skill edits before saving.
                """
                if latest_skill() != expected:
                    raise AgentError("EVOLUTION_TARGET_CHANGED", "Skill 刚被更新，未覆盖。")
                return skills.save(
                    SaveSkillParams(
                        project_id=candidate.project_id,
                        name=name,
                        content=desired,
                        scope=target.scope,
                        overwrite=True,
                    )
                )

            result = await worker.call(save_skill)
            selected = next(
                item for item in result.items if item.name == name and item.source == target.scope
            )
            candidate.target = target.model_copy(update={"identity": selected.skill_id})
            return
        tools = await self.file_tools(candidate.project_id, candidate.candidate_id)
        file_path = target.identity or "AGENTS.md"
        if desired is None:
            content, raw, _ = await asyncio.to_thread(tools.read._read, file_path)
            if content != expected:
                raise AgentError("EVOLUTION_TARGET_CHANGED", "目标已变化，未删除。")
            await tools._operation_one(
                "delete_file",
                FileOperationArgs(path=file_path),
                source="restore",
                expected_before=raw,
            )
        else:
            if target.kind == "code" and not revert:
                from my_agent.evolution.recovery import prepare_recovery

                args = (
                    CreateFileArgs(path=file_path, content=desired)
                    if expected is None
                    else SaveFileArgs(path=file_path, content=desired, base_content=expected)
                )
                resolved = await asyncio.to_thread(tools._target, args)
                original_bytes, proposed_bytes = await asyncio.to_thread(
                    tools._prepare, args, resolved
                )
                directory = (
                    self.storage.root
                    / "evolution"
                    / "recovery"
                    / (candidate.candidate_id + "-" + str(candidate.revision))
                )
                candidate.recovery_directory = await worker.call(
                    prepare_recovery,
                    directory,
                    candidate,
                    tools.context.root,
                    resolved,
                    original_bytes,
                    proposed_bytes,
                )
                saved_candidate = await worker.call(EvolutionStore(self.storage).save, candidate)
                candidate.revision = saved_candidate.revision
            file_result = await tools._write(
                ToolCall(
                    tool_call_id=str(uuid4()),
                    name="create_file" if expected is None else "save_file",
                    arguments={
                        "path": file_path,
                        "content": desired,
                        **({"base_content": expected} if expected is not None else {}),
                    },
                ),
                source="restore" if revert else "user",
            )
            change_id = str(json.loads(file_result.content)["change_id"])
            candidate.change_ids.append(change_id)
            if not revert:
                # 编辑工具保留原换行；恢复时比较真实保存内容而非模型的 LF 草稿。
                # Match the actually preserved line endings, not the model's LF proposal.
                record = await worker.call(tools.store.load, candidate.candidate_id, change_id)
                candidate.after = base64.b64decode(record.after_base64).decode("utf-8-sig")
