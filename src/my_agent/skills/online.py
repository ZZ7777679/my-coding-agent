"""公开 Skill 网站适配：异步下载，显式安装，不执行下载内容。

Public skill sources: asynchronous downloads and explicit installation, never script execution.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4

import httpx

from my_agent import __version__
from my_agent.errors import AgentError
from my_agent.skills.online_types import (
    ONLINE_DEFAULTS,
    OnlineSkillCancel,
    OnlineSkillCandidate,
    OnlineSkillDocument,
    OnlineSkillHit,
    OnlineSkillInspect,
    OnlineSkillInstall,
    OnlineSkillPreview,
    OnlineSkillRead,
    OnlineSkillSearch,
    OnlineSkillStatus,
)
from my_agent.skills.service import SkillService, parse_skill
from my_agent.skills.types import SaveSkillParams, SkillItem, SkillOrigin
from my_agent.storage import write_document
from my_agent.worker import BusinessWorker


def github_source(source: str) -> tuple[str, str, str]:
    """解析公开 GitHub / skills.sh 来源，分支含斜线时由显式 ref 覆盖。

    Parse GitHub/skills.sh sources; slash-containing branches can use the explicit ref override.
    """
    value = source.strip()
    ref, directory = "HEAD", ""
    if "://" in value:
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password:
            raise AgentError("SKILL_SOURCE_INVALID", "请使用不含凭据的 HTTPS 公开来源链接。")
        parts = unquote(url.path).strip("/").split("/")
        if url.hostname in {"skills.sh", "www.skills.sh"}:
            if parts[0] == "site":
                raise AgentError(
                    "SKILL_SOURCE_UNSUPPORTED",
                    "这是外部网站发布的 Skill，请打开其来源页；本版自动下载支持公开 GitHub 来源。",
                )
            parts = parts[:2]
        elif url.hostname == "github.com":
            if len(parts) > 2:
                if len(parts) < 4 or parts[2] not in {"tree", "blob"}:
                    raise AgentError("SKILL_SOURCE_INVALID", "请粘贴仓库、目录或 SKILL.md 链接。")
                ref = parts[3]
                directory = "/".join(parts[4:])
                if parts[2] == "blob" and directory.endswith("SKILL.md"):
                    directory = str(PurePosixPath(directory).parent)
            parts = parts[:2]
        else:
            raise AgentError("SKILL_SOURCE_UNSUPPORTED", "本版支持 skills.sh 与公开 GitHub 仓库。")
    else:
        parts = value.split("/")
    if len(parts) != 2:
        raise AgentError(
            "SKILL_SOURCE_INVALID", "来源应为 owner/repo 或完整 GitHub / skills.sh 链接。"
        )
    parts[1] = parts[1].removesuffix(".git")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", p) or p in {".", ".."} for p in parts):
        raise AgentError("SKILL_SOURCE_INVALID", "GitHub 仓库名称无法解析。")
    return "/".join(parts), ref, directory


def skillhub_source(source: str) -> str | None:
    """从 SkillHub 详情地址取公开 slug，其他来源交给原有解析器。

    Extract a public SkillHub slug from a detail URL; leave other sources unchanged.
    """
    url = urlsplit(source.strip())
    if url.hostname not in {"skillhub.cn", "www.skillhub.cn"}:
        return None
    parts = unquote(url.path).strip("/").split("/")
    if (
        url.scheme != "https"
        or url.username
        or url.password
        or len(parts) not in {2, 3}
        or parts[0] != "skills"
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", parts[-1])
        or (len(parts) == 3 and not re.fullmatch(r"[A-Za-z0-9_-]+", parts[1]))
    ):
        raise AgentError("SKILL_SOURCE_INVALID", "请使用 SkillHub 的具体 Skill 详情 HTTPS 链接。")
    return parts[-1]


def check_response(response: httpx.Response) -> None:
    """按 HTTP 事实区分来源与网络错误，不把失败变成空结果。

    Report HTTP failures, not empty results.
    """
    if response.status_code in {401, 403, 429}:
        raise AgentError(
            "SKILL_SOURCE_LIMITED", "网站拒绝访问或限流；可稍后重试，或使用本地目录导入。"
        )
    if response.status_code == 404:
        raise AgentError(
            "SKILL_SOURCE_NOT_FOUND", "公开来源或分支不存在，也可能是需要登录的私有仓库。"
        )
    if not response.is_success:
        raise AgentError("SKILL_SOURCE_HTTP", f"网站返回 HTTP {response.status_code}。")


class OnlineSkills:
    """持有一个在线管理操作与预览快照；不影响已安装 Skill 或普通会话。

    Own one catalog operation and preview snapshot, independent of installed skills and chat.
    """

    def __init__(self, skills: SkillService, worker: BusinessWorker) -> None:
        """复用现有资源写入服务。 Reuse the resource writer."""
        self.skills = skills
        self.worker = worker
        self.state = OnlineSkillStatus()
        self.task: asyncio.Task[None] | None = None
        self.temporary: tempfile.TemporaryDirectory[str] | None = None
        self.archive: Path | None = None
        self.archive_root = ""
        self.max_unpacked = 0
        self.transport: httpx.AsyncBaseTransport | None = None

    def client(self, timeout: float) -> httpx.AsyncClient:
        """独立公共 HTTP 客户端，不继承模型认证头。

        Public HTTP without model authentication headers.
        """
        return httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": f"my-coding-agent/{__version__}"},
            transport=self.transport,
        )

    def status(self) -> OnlineSkillStatus:
        """返回快照，避免边界序列化时读到后续更新。

        Return a stable snapshot for serialization.
        """
        return self.state.model_copy(deep=True)

    def _start(self, action: str, work: Callable[[], Awaitable[None]]) -> OnlineSkillStatus:
        """由短 RPC 接纳后台操作，实际结果通过 status 查看。

        Accept work without a long RPC wait.
        """
        self.state.operation_id = uuid4().hex
        self.state.status = "running"
        self.state.error_code = None
        self.state.installed = None
        self.task = asyncio.create_task(self._run(work), name="online-skill-" + action)
        return self.status()

    def _available(self) -> None:
        """避免同一管理页相互覆盖快照；可取消下载后再换来源。

        Keep concurrent actions from replacing previews.
        """
        if self.task and not self.task.done():
            raise AgentError("SKILL_ONLINE_BUSY", "在线操作仍在进行，可取消搜索 / 下载后再操作。")

    def search(self, params: OnlineSkillSearch) -> OnlineSkillStatus:
        """启动目录搜索。 Start a catalog search."""
        self._available()
        self.state = OnlineSkillStatus(
            action="search", query=params.query, message="正在搜索 skills.sh"
        )
        return self._start("search", lambda: self._search(params))

    async def _search(self, params: OnlineSkillSearch) -> None:
        """用官方 CLI 所用公开接口搜索，不触发遥测或安装。

        Use the public CLI endpoint without telemetry.
        """
        await self._discard()
        async with self.client(params.timeout_seconds) as client:
            async with asyncio.timeout(params.timeout_seconds):
                response = await client.get(
                    ONLINE_DEFAULTS["search_url"], params={"q": params.query, "limit": params.limit}
                )
        check_response(response)
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
            raise AgentError(
                "SKILL_SOURCE_FORMAT", "skills.sh 响应格式已变化，仍可通过 GitHub 链接导入。"
            )
        hits: list[OnlineSkillHit] = []
        for item in data["skills"]:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(key), str) for key in ("name", "source", "id")
            ):
                raise AgentError("SKILL_SOURCE_FORMAT", "网站条目缺少名称或来源，无法展示。")
            hits.append(
                OnlineSkillHit(
                    name=item["name"],
                    source=item["source"],
                    url="https://skills.sh/" + quote(item["id"], safe="/"),
                    installs=item.get("installs") if type(item.get("installs")) is int else None,
                )
            )
        self.state.hits = hits[: params.limit]
        self.state.message = f"找到 {len(self.state.hits)} 项，来自 skills.sh。"

    def inspect(self, params: OnlineSkillInspect) -> OnlineSkillStatus:
        """下载公开快照，尚不写入项目或资源库。

        Download a preview without installing it.
        """
        self._available()
        slug = skillhub_source(params.source)
        if slug is not None:
            self.state.action = "inspect"
            self.state.preview = None
            self.state.message = f"正在读取 SkillHub：{slug}"
            return self._start("inspect", lambda: self._inspect_skillhub(params, slug))
        repository, ref, directory = github_source(params.source)
        self.state.action = "inspect"
        self.state.preview = None
        self.state.message = f"正在下载 {repository}"
        return self._start("inspect", lambda: self._inspect(params, repository, ref, directory))

    async def _inspect(
        self, params: OnlineSkillInspect, repository: str, ref: str, directory: str
    ) -> None:
        """在数据根下载 ZIP，以同一快照完成预览和安装。

        Download one ZIP for both preview and installation.
        """
        await self._discard()
        ref = params.ref.strip() or ref
        directory = params.directory.strip().strip("/") or directory
        self.max_unpacked = params.max_archive_mb * 1024 * 1024 * 4
        await self.worker.call(self._create_temporary)
        assert (
            self.archive is not None
        )  # _create_temporary 创建此路径。 Created by _create_temporary.
        url = f"{ONLINE_DEFAULTS['archive_base_url']}/{repository}/zip/{quote(ref, safe='')}"
        await self._download(url, repository, params)
        origin = SkillOrigin(
            repository=repository,
            ref=ref,
            directory=directory,
            downloaded_at=datetime.now(UTC).isoformat(),
        )
        self.state.message = "正在读取仓库中的 Skill"
        self.state.preview = await self.worker.call(self._scan, origin)
        self.state.message = f"发现 {self.state.preview.total} 项 Skill；选择后安装。"

    async def _inspect_skillhub(self, params: OnlineSkillInspect, slug: str) -> None:
        """下载 SkillHub 官方包并适配其非标准 Markdown 元信息。

        Download the official SkillHub archive and adapt non-standard Markdown metadata.
        """
        await self._discard()
        base = ONLINE_DEFAULTS["skillhub_api_base_url"]
        async with self.client(params.timeout_seconds) as client:
            async with asyncio.timeout(params.timeout_seconds):
                response = await client.get(f"{base}/api/v1/skills/{quote(slug, safe='')}")
        check_response(response)
        detail = response.json()
        if not isinstance(detail, dict) or not isinstance(detail.get("skill"), dict):
            raise AgentError("SKILL_SOURCE_FORMAT", "SkillHub 详情格式已变化，无法确定下载对象。")
        skill = detail["skill"]
        if skill.get("slug") != slug:
            raise AgentError("SKILL_SOURCE_FORMAT", "SkillHub 详情与所选条目不一致。")
        latest = detail.get("latestVersion")
        latest_version = latest.get("version") if isinstance(latest, dict) else None
        version = params.ref.strip() or latest_version
        if not isinstance(version, str) or not version:
            raise AgentError("SKILL_SOURCE_FORMAT", "SkillHub 详情没有可下载版本。")
        summary = skill.get("summary_zh") or skill.get("summary") or skill.get("displayName")
        description = summary if isinstance(summary, str) else slug
        self.max_unpacked = params.max_archive_mb * 1024 * 1024 * 4
        await self.worker.call(self._create_temporary)
        await self._download(
            f"{base}/api/v1/download",
            f"SkillHub {slug}",
            params,
            query={"slug": slug, "version": version},
        )
        await self.worker.call(self._normalize_skillhub_archive, slug, description)
        origin = SkillOrigin(
            repository=f"skillhub.cn/{slug}",
            ref=version,
            directory="",
            downloaded_at=datetime.now(UTC).isoformat(),
        )
        self.state.message = "正在读取 SkillHub 下载包"
        self.state.preview = await self.worker.call(self._scan, origin, "")
        self.state.message = f"发现 {self.state.preview.total} 项 Skill；选择后导入。"

    async def _download(
        self,
        url: str,
        label: str,
        params: OnlineSkillInspect,
        query: dict[str, str] | None = None,
    ) -> None:
        """将来源响应流写入同一受限快照，不缓存账号凭据。

        Stream either public source into the bounded preview snapshot without credentials.
        """
        # _create_temporary 创建此路径。 Created by _create_temporary.
        assert self.archive is not None
        async with self.client(params.timeout_seconds) as client:
            async with asyncio.timeout(params.timeout_seconds):
                async with client.stream("GET", url, params=query) as response:
                    check_response(response)
                    downloaded = 0
                    with self.archive.open("wb") as stream:
                        async for chunk in response.aiter_bytes(262144):
                            downloaded += len(chunk)
                            if downloaded > params.max_archive_mb * 1024 * 1024:
                                raise AgentError(
                                    "SKILL_DOWNLOAD_SIZE",
                                    "下载包超过上限，可提高高级参数后重试。",
                                )
                            await self.worker.call(stream.write, chunk)
                            self.state.message = f"下载 {label} · {downloaded / 1048576:.1f} MiB"

    def _normalize_skillhub_archive(self, slug: str, description: str) -> None:
        """仅在缺少标准头部时改写快照，预览和安装共享转换结果。

        Rewrite the snapshot only when metadata is missing, so preview and install match.
        """
        assert self.archive is not None
        try:
            with zipfile.ZipFile(self.archive) as source:
                entry = source.getinfo("SKILL.md")
                if entry.file_size > self.max_unpacked:
                    raise AgentError("SKILL_DOWNLOAD_SIZE", "Skill 正文超过解压预算。")
                original = source.read(entry).decode("utf-8-sig")
                try:
                    parse_skill(original)
                    return
                except AgentError:
                    pass
                # SkillHub 用户上传可能没有 YAML 头，正文中的 Description 可补齐用途。
                # User uploads may omit YAML; their Description section can supply the purpose.
                match = re.search(r"(?im)^##\s+Description\s*$\n\s*([^\n#]+)", original)
                purpose = (match.group(1).strip() if match else "") or description.strip() or slug
                normalized = (
                    f"---\nname: {json.dumps(slug)}\n"
                    f"description: {json.dumps(purpose, ensure_ascii=False)}\n---\n\n{original}"
                ).encode()
                members = source.infolist()
                if sum(member.file_size for member in members) > self.max_unpacked:
                    raise AgentError("SKILL_DOWNLOAD_SIZE", "SkillHub 附属文件超过解压预算。")
                target_path = self.archive.with_name("normalized.zip")
                with zipfile.ZipFile(target_path, "w") as target:
                    target.comment = source.comment
                    for member in members:
                        if member.filename == "SKILL.md":
                            target.writestr(copy.copy(member), normalized)
                        elif member.is_dir():
                            target.writestr(copy.copy(member), b"")
                        else:
                            with source.open(member) as input_file:
                                with target.open(copy.copy(member), "w") as output:
                                    shutil.copyfileobj(input_file, output)
        except (KeyError, zipfile.BadZipFile, UnicodeError) as exc:
            raise AgentError(
                "SKILL_SOURCE_FORMAT", "SkillHub 下载包缺少可读取的 SKILL.md。"
            ) from exc
        self.archive = target_path

    def _create_temporary(self) -> None:
        """仅创建应用自有缓存目录。 Create an app-owned download directory."""
        root = self.skills.root.parent / "skill-downloads"
        root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="preview-", dir=root)
        self.archive = Path(self.temporary.name) / "repository.zip"

    def _scan(self, origin: SkillOrigin, archive_root: str | None = None) -> OnlineSkillPreview:
        """按真实 SKILL.md 发现方法，坏条目逐项报告。

        Discover actual SKILL.md files and report bad entries.
        """
        assert self.archive is not None  # 下载后调用。 Called after download.
        candidates: list[OnlineSkillCandidate] = []
        issues: list[str] = []
        with zipfile.ZipFile(self.archive) as archive:
            members = archive.infolist()
            self.archive_root = (
                archive_root
                if archive_root is not None
                else (members[0].filename.split("/")[0] + "/" if members else "")
            )
            revision = archive.comment.decode("ascii", errors="replace")
            origin.revision = revision if re.fullmatch(r"[0-9a-f]{40,64}", revision) else None
            for entry in members:
                if entry.filename != "SKILL.md" and not entry.filename.endswith("/SKILL.md"):
                    continue
                path = (
                    entry.filename.removeprefix(self.archive_root)
                    .removesuffix("SKILL.md")
                    .rstrip("/")
                )
                if origin.directory not in {"", "."} and not (
                    path == origin.directory or path.startswith(origin.directory + "/")
                ):
                    continue
                try:
                    if entry.file_size > self.max_unpacked:
                        raise AgentError("SKILL_DOWNLOAD_SIZE", "Skill 正文超过解压预算。")
                    name, description = parse_skill(archive.read(entry).decode("utf-8-sig"))
                    prefix = self.archive_root + (path + "/" if path else "")
                    files = [m for m in members if m.filename.startswith(prefix) and not m.is_dir()]
                    candidates.append(
                        OnlineSkillCandidate(
                            name=name,
                            description=description[:1000],
                            path=path,
                            file_count=len(files),
                            bytes=sum(f.file_size for f in files),
                        )
                    )
                except (AgentError, UnicodeError) as exc:
                    issues.append(
                        f"{path}: "
                        + (exc.message if isinstance(exc, AgentError) else "正文不是 UTF-8")
                    )
        return OnlineSkillPreview(
            preview_id=uuid4().hex,
            origin=origin,
            skills=candidates[: ONLINE_DEFAULTS["preview_items"]],
            total=len(candidates),
            issues=issues[: ONLINE_DEFAULTS["preview_items"]],
        )

    def _candidate(
        self, params: OnlineSkillRead
    ) -> tuple[OnlineSkillPreview, OnlineSkillCandidate]:
        """按保留的预览身份定位资源，旧页面不会安装新快照。

        Resolve the retained snapshot, not a newer selection.
        """
        preview = self.state.preview
        if not preview or preview.preview_id != params.preview_id or not self.archive:
            raise AgentError("SKILL_PREVIEW_EXPIRED", "预览已关闭或被新来源替换，请重新查看。")
        item = next((s for s in preview.skills if s.path == params.path), None)
        if item is None:
            raise AgentError("SKILL_NOT_FOUND", "预览中未找到此 Skill。")
        return preview, item

    def read(self, params: OnlineSkillRead) -> OnlineSkillDocument:
        """按需读取有限正文与文件清单，不在状态轮询反复发送正文。

        Read bounded details outside polling.
        """
        self._candidate(params)
        assert self.archive is not None
        prefix = self.archive_root + (params.path + "/" if params.path else "")
        with zipfile.ZipFile(self.archive) as archive:
            with archive.open(prefix + "SKILL.md") as stream:
                # UTF-8 最多四字节，截断预览不影响安装文件。
                # Preview truncation never changes installed bytes.
                data = stream.read(ONLINE_DEFAULTS["preview_characters"] * 4 + 1)
            content = data.decode("utf-8-sig", errors="replace")
            files = [
                n.removeprefix(prefix)
                for n in archive.namelist()
                if n.startswith(prefix) and not n.endswith("/")
            ]
        limit = ONLINE_DEFAULTS["preview_characters"]
        return OnlineSkillDocument(
            content=content[:limit],
            truncated=len(content) > limit,
            files=files[: ONLINE_DEFAULTS["preview_items"]],
            file_count=len(files),
        )

    def install(self, params: OnlineSkillInstall) -> OnlineSkillStatus:
        """安装按钮是明确写入动作，同名资源不覆盖。

        The install action explicitly writes, without overwrites.
        """
        self._available()
        self._candidate(params)
        self.state.action = "install"
        self.state.message = "正在保存 Skill 与附属文件"
        return self._start("install", lambda: self._install(params))

    async def _install(self, params: OnlineSkillInstall) -> None:
        """在单写者内解包并发布资源，完成前不报告安装成功。

        Publish through the single writer before reporting success.
        """
        self.state.installed = await self.worker.call(self._install_files, params)
        self.state.status = "installed"
        target = "导入项目" if params.scope == "project" else "安装到资源库"
        self.state.message = f"{self.state.installed.name} 已{target}。"

    def _install_files(self, params: OnlineSkillInstall) -> SkillItem:
        """只解包所选目录，真实路径边界在此检查一次。

        Extract only the selected directory with one path boundary.
        """
        preview, item = self._candidate(params)
        assert self.archive is not None and self.temporary is not None
        prefix = self.archive_root + (params.path + "/" if params.path else "")
        with tempfile.TemporaryDirectory(prefix="install-", dir=self.temporary.name) as staging:
            root = Path(staging).resolve()
            with zipfile.ZipFile(self.archive) as archive:
                files = [
                    m
                    for m in archive.infolist()
                    if m.filename.startswith(prefix) and not m.is_dir()
                ]
                if sum(m.file_size for m in files) > self.max_unpacked:
                    raise AgentError(
                        "SKILL_DOWNLOAD_SIZE",
                        "附属文件超过解压预算，可提高下载大小参数后重新查看。",
                    )
                for member in files:
                    relative = member.filename.removeprefix(prefix)
                    destination = (root / relative).resolve()
                    if not destination.is_relative_to(root) or stat.S_ISLNK(
                        member.external_attr >> 16
                    ):
                        raise AgentError(
                            "SKILL_ARCHIVE_PATH",
                            "此目录含越界路径或符号链接，请改用整理后的本地目录导入。",
                        )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
            origin = preview.origin.model_copy(update={"directory": params.path})
            write_document(root / ".my-agent-source.json", origin)
            catalog = self.skills.save(
                SaveSkillParams(
                    project_id=params.project_id,
                    name=item.name,
                    content="",
                    scope=params.scope,
                    import_directory=str(root),
                )
            )
        return next(s for s in catalog.items if s.source == params.scope and s.name == item.name)

    async def cancel(self, params: OnlineSkillCancel) -> OnlineSkillStatus:
        """取消网络操作；本地提交已开始时完成写入并显示真实结果。

        Cancel networking; finish an already-started commit.
        """
        if params.operation_id == self.state.operation_id and self.task and not self.task.done():
            if self.state.action != "install":
                self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            # 在协程首次调度前取消时，运行包装器尚未接到取消。
            # Cancellation before first scheduling has not reached the job wrapper yet.
            if self.task.cancelled():
                self.state.status, self.state.message = "cancelled", "已取消，未安装资源。"
                await self._discard()
        return self.status()

    async def _run(self, work: Callable[[], Awaitable[None]]) -> None:
        """把后台失败留在管理页，不传播到普通模型运行。

        Keep background failures local to resource management.
        """
        try:
            await work()
            if self.state.status == "running":
                self.state.status = "ready"
        except asyncio.CancelledError:
            self.state.status, self.state.message = "cancelled", "已取消，未安装资源。"
            await self._discard()
        except Exception as exc:
            # 后台操作的边界保留可见失败，不让意外错误留下永久 running。
            # Expose unexpected failures instead of leaving the operation running forever.
            self.state.status = "failed"
            if isinstance(exc, AgentError):
                self.state.error_code, self.state.message = exc.code, exc.message
            else:
                self.state.error_code = "SKILL_ONLINE_FAILED"
                self.state.message = (
                    f"操作失败（{type(exc).__name__}），可检查网络 / 来源或调整高级参数后重试。"
                )
            if self.state.action != "install":
                await self._discard()

    async def _discard(self) -> None:
        """只清理本实例拥有的临时目录。

        Clean only this instance's owned temporary directory.
        """
        if self.temporary:
            await self.worker.call(self.temporary.cleanup)
        self.temporary, self.archive = None, None

    async def close(self) -> None:
        """退出时取消下载，收回提交并清理缓存。

        Cancel downloads, reap commits and clean previews on shutdown.
        """
        await self.cancel(OnlineSkillCancel(operation_id=self.state.operation_id))
        await self._discard()
