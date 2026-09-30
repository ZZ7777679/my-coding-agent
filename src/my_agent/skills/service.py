"""资源发现和材料组装，复用业务线程与原子存储。

Resource discovery and material assembly using the business writer and atomic storage.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

# PyYAML 的解析结果在本模块作为 object 检查；它不含类型声明。
# Treat untyped YAML values as objects and check the fields used here.
import yaml  # type: ignore[import-untyped]

from my_agent.errors import AgentError
from my_agent.runtime.context import ContextMaterial, describe_material
from my_agent.sessions.projection import summarize
from my_agent.skills.types import (
    EnableSkillParams,
    SaveSkillParams,
    SelectSkillsParams,
    SkillCatalog,
    SkillDocument,
    SkillItem,
    SkillOrigin,
    SkillParams,
    SkillReadParams,
    SkillSettings,
)
from my_agent.storage import atomic_write, read_document, write_document
from my_agent.workflow.methods import bundled_skills_root
from my_agent.workflow.types import WorkMethod

if TYPE_CHECKING:
    from my_agent.sessions.service import SessionService
    from my_agent.sessions.store import SessionLog


def parse_skill(text: str) -> tuple[str, str]:
    """解析标准头部；额外字段保留在原文但不执行。

    Parse metadata without executing extra fields.
    """
    lines = text.splitlines()
    closing = next(
        (index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None
    )
    if not lines or lines[0].strip() != "---" or closing is None:
        raise AgentError("SKILL_INVALID", "SKILL.md 需要 YAML 头部和 name / description。")
    try:
        metadata: object = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise AgentError("SKILL_INVALID", "Skill YAML 无法解析。") from exc
    if not isinstance(metadata, dict):
        raise AgentError("SKILL_INVALID", "Skill 元信息应是对象。")
    name, description = metadata.get("name"), metadata.get("description")
    if not isinstance(name, str) or not name.strip() or not isinstance(description, str):
        raise AgentError("SKILL_INVALID", "Skill 需要名称与用途说明。")
    return name, description


class SkillService:
    """管理资源文本和会话引用，不代替执行后端。

    Manage resources and references, not execution.
    """

    def __init__(self, sessions: SessionService) -> None:
        """绑定现有应用服务。 Bind the existing application services."""
        self.sessions = sessions
        self.root = sessions.store.storage.root / "skills"
        self.settings_path = sessions.store.storage.root / "skills.json"
        self.rule_indexes: dict[str, list[str]] = {}

    def refresh(self, params: SkillParams) -> SkillCatalog:
        """显式刷新子目录规范索引，避免每次模型请求全项目扫描。

        Refresh nested-rule discovery explicitly rather than scanning on every model request.
        """
        if params.project_id:
            self.rule_indexes.pop(str(self.project_root(params.project_id)), None)
        return self.catalog(params)

    def project_root(self, project_id: str) -> Path:
        """从登记身份解析项目，不使用进程 cwd。

        Resolve a registered project, never process cwd.
        """
        project = next(
            (p for p in self.sessions.projects.read().projects if p.project_id == project_id), None
        )
        if project is None:
            raise AgentError("PROJECT_UNAVAILABLE", "项目未登记。")
        root = Path(project.canonical_path)
        if not root.is_dir():
            raise AgentError("PROJECT_UNAVAILABLE", "项目目录已失效，请重新定位后再导入资源。")
        return root

    def _settings(self, session_id: str | None = None) -> SkillSettings:
        """缺失使用默认，损坏保持真实错误。

        Default missing settings without hiding corruption.
        """
        path = (
            self.sessions.store.path(session_id).with_name("skills.json")
            if session_id
            else self.settings_path
        )
        return read_document(path, SkillSettings) if path.exists() else SkillSettings()

    def catalog(self, params: SkillParams) -> SkillCatalog:
        """逐项发现资源；坏资源只影响自身。

        Discover resources, isolating invalid entries.
        """
        root = self.project_root(params.project_id) if params.project_id else None
        issues: list[str] = []
        try:
            disabled = self._settings().disabled
            selected = self._settings(params.session_id).selected if params.session_id else []
        except AgentError as exc:
            disabled, selected = [], []
            issues.append(f"资源设置不可读：{exc.code}；原文件保留。")
        items: list[SkillItem] = []
        directories = [("builtin", bundled_skills_root()), ("user", self.root)]
        if root:
            directories.append(("project", root / ".agents" / "skills"))
        for source, directory in directories:
            for path in sorted(directory.glob("*/SKILL.md")):
                try:
                    text = path.read_text(encoding="utf-8-sig")
                    name, description = parse_skill(text)
                    identity = (
                        f"project:{params.project_id}:" if source == "project" else f"{source}:"
                    ) + path.parent.name
                    origin_path = path.parent / ".my-agent-source.json"
                    origin = None
                    if origin_path.exists():
                        try:
                            origin = read_document(origin_path, SkillOrigin)
                        except AgentError:
                            # 来源备注损坏不使正文失效。
                            # Invalid provenance does not disable the skill.
                            issues.append(f"{path.parent.name}: 来源记录不可读，正文仍可使用。")
                    items.append(
                        SkillItem(
                            skill_id=identity,
                            name=name,
                            description=description,
                            source=(
                                "project"
                                if source == "project"
                                else "builtin"
                                if source == "builtin"
                                else "user"
                            ),
                            path=str(path),
                            resource_base=str(path.parent.resolve()),
                            version=str(path.stat().st_mtime_ns),
                            origin=origin,
                        )
                    )
                except (AgentError, OSError, UnicodeError) as exc:
                    issues.append(
                        f"{path}: {exc.code if isinstance(exc, AgentError) else '读取失败'}"
                    )
        winners: dict[str, str] = {}
        for item in items:
            item.enabled = item.skill_id not in disabled
            if item.enabled:
                winners[item.name] = item.skill_id
        for item in items:
            if item.enabled and winners.get(item.name) != item.skill_id:
                item.shadowed_by = winners.get(item.name)
        # 沿已有文件发现规则索引规范，避免遍历依赖和忽略目录。
        # Reuse file discovery rules instead of walking ignored dependency directories.
        import threading

        from my_agent.config import load_config
        from my_agent.tools.policy import ReadPolicy

        rules = ["AGENTS.md"] if root and (root / "AGENTS.md").is_file() else []
        # 子目录规则在目录查看时也可按需读取；索引失败不阻断资源目录。
        # Nested rules remain explicitly readable even when their optional index is unavailable.
        try:
            if root and str(root) not in self.rule_indexes:
                policy = ReadPolicy(
                    root, load_config(self.sessions.store.storage.location).run, threading.Event()
                )
                self.rule_indexes[str(root)] = [
                    p
                    for p in policy.scan(glob="*AGENTS.md").files
                    if Path(p).name == "AGENTS.md" and p != "AGENTS.md"
                ]
            rules.extend(self.rule_indexes.get(str(root), []))
        except (AgentError, OSError) as exc:
            issues.append(f"子目录规范索引不可用：{type(exc).__name__}")
        return SkillCatalog(
            items=items,
            selected=selected,
            rule_paths=rules,
            issues=issues,
            user_directory=str(self.root),
            project_directory=str(root / ".agents" / "skills") if root else "",
        )

    def read(self, params: SkillReadParams) -> SkillDocument:
        """按来源身份读取，正文始终来自当前文件。

        Read current text by provenance identity.
        """
        catalog = self.catalog(params)
        item = next((i for i in catalog.items if i.skill_id == params.skill_id), None)
        if item is None:
            raise AgentError("SKILL_NOT_FOUND", "未找到 Skill，请刷新目录。")
        return self._read_item(item)

    def _read_item(self, item: SkillItem) -> SkillDocument:
        """从已解析目录项读取正文，不重复发现目录。

        Read a resolved entry without rediscovery.
        """
        try:
            text = Path(item.path).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise AgentError("SKILL_UNAVAILABLE", "Skill 文件无法读取。") from exc
        return SkillDocument(item=item, content=text)

    def save(self, params: SaveSkillParams) -> SkillCatalog:
        """显式保存资源；导入保留附属文件。 Save resources with imported assets."""
        try:
            return self._save_resource(params)
        except (OSError, UnicodeError) as exc:
            raise AgentError(
                "SKILL_SAVE_FAILED", f"资源保存失败：{type(exc).__name__}；请检查来源和目标目录。"
            ) from exc

    def _save_resource(self, params: SaveSkillParams) -> SkillCatalog:
        """完成已授权的文件写入，不吞掉部分导入失败。

        Perform authorized writes without hiding a partially failed import.
        """
        root = self.project_root(params.project_id) if params.project_id else None
        if params.scope == "project" and root is None:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "请先选择要导入 Skill 的项目。")
        directory = root / ".agents" / "skills" if params.scope == "project" and root else self.root
        destination = directory / params.name
        if not destination.resolve().is_relative_to(directory.resolve()) or (
            params.scope == "project"
            and root
            and not destination.resolve().is_relative_to(root.resolve())
        ):
            raise AgentError("INVALID_TOOL_ARGUMENTS", "目标资源目录无效。")
        text = params.content
        if params.import_directory:
            source = Path(params.import_directory).resolve(strict=True)
            text = (source / "SKILL.md").read_text(encoding="utf-8-sig")
        name, _ = parse_skill(text)
        if name != params.name:
            raise AgentError("SKILL_INVALID", "目录名称需要与 Skill name 一致。")
        if destination.exists() and not params.overwrite:
            raise AgentError("SKILL_EXISTS", "同名目录已存在；编辑已有 Skill 或改用其他名称。")
        if params.import_directory:
            if destination.exists():
                raise AgentError("SKILL_EXISTS", "导入请使用未占用的名称；已有资源可单独编辑。")
            directory.mkdir(parents=True, exist_ok=True)
            # 目录复制完成后才发布，失败不留下冒充已安装的半成品。
            # Publish only the completed directory, never a partial installation.
            with tempfile.TemporaryDirectory(prefix=".skill-import-", dir=directory) as staging:
                prepared = Path(staging) / params.name
                shutil.copytree(source, prepared)
                prepared.rename(destination)
        else:
            destination.mkdir(parents=True, exist_ok=True)
            atomic_write(destination / "SKILL.md", text)
        return self.catalog(params)

    def select(self, params: SelectSkillsParams) -> SkillCatalog:
        """原子保存会话选择，空选择解除引用。

        Persist selection; an empty list clears references.
        """
        if params.session_id is None:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "请选择会话。")
        catalog = self.catalog(params)
        available = {i.skill_id for i in catalog.items if i.enabled}
        if any(identity not in available for identity in params.selected):
            raise AgentError("SKILL_NOT_FOUND", "选择包含已移除或停用的 Skill，请刷新。")
        log = self.sessions.store.load(params.session_id)
        if summarize(log).project_id != params.project_id:
            raise AgentError("INVALID_TOOL_ARGUMENTS", "会话不属于当前项目。")
        settings = self._settings(params.session_id)
        settings.selected = list(dict.fromkeys(params.selected))
        write_document(
            self.sessions.store.path(params.session_id).with_name("skills.json"),
            settings,
        )
        return self.catalog(params)

    def enable(self, params: EnableSkillParams) -> SkillCatalog:
        """只改变目录启停，不编辑 Skill 内容。

        Toggle availability without editing resource text.
        """
        settings = self._settings()
        settings.disabled = [i for i in settings.disabled if i != params.skill_id]
        if not params.enabled:
            settings.disabled.append(params.skill_id)
        write_document(self.settings_path, settings)
        return self.catalog(params)

    def _archive_material(self, session_id: str, key: str, body: str) -> str:
        """每个资源版本只归档一次，历史回读不指向之后修改的文件。

        Archive each resource version once; history never points to a subsequently edited file.
        """
        from my_agent.context.store import ContextStore

        settings = self._settings(session_id)
        existing = settings.material_archives.get(key)
        if existing:
            return existing
        identity = ContextStore(self.sessions.store).archive(session_id, body)
        settings.material_archives[key] = identity
        write_document(self.sessions.store.path(session_id).with_name("skills.json"), settings)
        return identity

    def _material(
        self,
        session_id: str,
        *,
        key: str,
        kind: str,
        title: str,
        reason: str,
        source_id: str,
        body: str,
        issues: list[str],
    ) -> ContextMaterial:
        """历史版本可回读；可选归档失败不阻断实际任务。

        Expose immutable history without turning optional archive failures into task gates.
        """
        arguments: dict[str, str] = {}
        try:
            arguments["artifact_id"] = self._archive_material(session_id, key, body)
        except (AgentError, OSError) as exc:
            code = exc.code if isinstance(exc, AgentError) else type(exc).__name__
            issues.append(f"{title} 历史材料未归档：{code}；本次仍采用已读取正文。")
        return describe_material(
            kind=kind,
            title=title,
            form="full",
            reason=reason,
            text=body,
            source_id=source_id,
            read_tool="read_history" if arguments else None,
            read_arguments={name: value for name, value in arguments.items()},
        )

    def materials(
        self, log: SessionLog, method: WorkMethod | None = None
    ) -> tuple[str, list[ContextMaterial]]:
        """请求边界刷新规则与选中技能，压缩不删除引用。

        Refresh rules and selected skills at request boundaries; compaction keeps references.
        """
        summary = summarize(log)
        params = SkillParams(project_id=summary.project_id, session_id=log.session_id)
        catalog = self.catalog(params)
        root = self.project_root(summary.project_id)
        text: list[str] = []
        materials: list[ContextMaterial] = []
        rule = root / "AGENTS.md"
        if rule.is_file():
            try:
                body = rule.read_text(encoding="utf-8-sig")
                text.append("Project instructions (within current user scope):\n" + body)
                materials.append(
                    self._material(
                        log.session_id,
                        key=f"rules:{rule}:{rule.stat().st_mtime_ns}",
                        kind="project_rules",
                        title="AGENTS.md",
                        reason="项目根规范",
                        body=body,
                        source_id=str(rule),
                        issues=catalog.issues,
                    )
                )
            except (OSError, UnicodeError):
                catalog.issues.append("项目 AGENTS.md 读取失败，可继续处理无关任务。")
        text.append(
            "Nested project rules: "
            + json.dumps(catalog.rule_paths, ensure_ascii=False)
            + "\nRead applicable nested rules before working in those directories."
        )
        effective = [i for i in catalog.items if i.enabled and not i.shadowed_by]
        text.append(
            "Available skills (load_skill only when useful):\n"
            + json.dumps(
                [
                    {"skill_id": i.skill_id, "name": i.name, "description": i.description}
                    for i in effective
                ],
                ensure_ascii=False,
            )
        )
        materials.append(
            describe_material(
                kind="skill_catalog",
                title="Skill 与子目录规范索引",
                form="catalog",
                reason="按需选择资源",
                text="\n".join(text[-2:]),
            )
        )
        chosen = list(catalog.selected)
        if summary.task_id:
            from my_agent.tasks.store import TaskStore

            task = TaskStore(self.sessions.store.storage).get(summary.task_id)
            flow = task.workflow
            if flow:
                stage_id = flow.session_stages.get(log.session_id, flow.current_stage_id)
                stage = next((s for s in flow.template.stages if s.stage_id == stage_id), None)
                workflow_text = (
                    "Task workflow (guidance, not authorization or execution gates):\n"
                    + flow.model_dump_json()
                    + "\nThis session's stage: "
                    + str(stage_id)
                    + "\nOnly an active Goal may continue autonomously. Review findings do not "
                    "authorize fixes. Do not create formal sessions automatically."
                )
                text.append(workflow_text)
                materials.append(
                    self._material(
                        log.session_id,
                        key=f"workflow:{task.task_id}:{task.revision}:{stage_id}",
                        kind="workflow",
                        title=flow.template.name,
                        reason="任务流程快照与会话阶段",
                        body=workflow_text,
                        source_id=task.task_id,
                        issues=catalog.issues,
                    )
                )
                if stage:
                    # 模板保留旧稳定身份，默认加载遵循项目 / 用户覆盖。
                    # Keep stable template IDs while honoring project/user defaults.
                    for identity in stage.skills:
                        configured = next(
                            (item for item in catalog.items if item.skill_id == identity), None
                        )
                        resolved = (configured.shadowed_by or identity) if configured else identity
                        if resolved not in chosen:
                            chosen.append(resolved)
        if method:
            matched = next((i for i in effective if i.name == method), None)
            if matched and matched.skill_id not in chosen:
                chosen.append(matched.skill_id)
        for identity in chosen:
            item = next((i for i in catalog.items if i.skill_id == identity and i.enabled), None)
            if not item:
                catalog.issues.append(f"所选 Skill 不可用：{identity}")
                continue
            try:
                document = self._read_item(item)
            except AgentError as exc:
                catalog.issues.append(f"{identity}: {exc.code}")
                continue
            body = (
                f"Skill {identity} version {item.version} (resources: {item.resource_base}):\n"
                + document.content
            )
            text.append(body)
            materials.append(
                self._material(
                    log.session_id,
                    key=f"{identity}:{item.version}:{item.resource_base}",
                    kind="skill",
                    title=item.name,
                    reason="会话选择或当前工作方法",
                    body=body,
                    source_id=identity,
                    issues=catalog.issues,
                )
            )
        if catalog.issues:
            text.append("Resource notices: " + "\n".join(catalog.issues))
        return "\n\n" + "\n\n".join(text), materials
