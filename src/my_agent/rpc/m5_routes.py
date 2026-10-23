"""M5 显式服务路由，不建立独立运行时。 Explicit M5 service routes without another runtime."""

from typing import TYPE_CHECKING

from pydantic import BaseModel

from my_agent.attachments.types import (
    AttachmentParams,
    ImageChunk,
    ImportAttachment,
)
from my_agent.documents.types import (
    DocumentChangeParams,
    DocumentListParams,
    DocumentOperationParams,
    DocumentParams,
    DocumentSearchParams,
    DocumentSessionParams,
    PatchDocumentsParams,
    SaveDocumentParams,
)
from my_agent.intelligence.types import (
    IntelligenceParams,
    LanguageQuery,
    SaveLanguageServers,
)
from my_agent.local_git.types import (
    ConfigureGitParams,
    GitCommitParams,
    GitDiffParams,
    GitHistoryParams,
    GitPathsParams,
    GitProjectParams,
)
from my_agent.rpc.dto import EmptyParams
from my_agent.spaces.design_types import (
    OpenTeamDesignParams,
    SaveTeamDesignParams,
    SendTeamDesignParams,
    StartTeamDesignParams,
)
from my_agent.spaces.team_types import (
    CopyTeamTemplateParams,
    GenerateTeamParams,
    ImportTeamTemplateParams,
    SaveTeamTemplateParams,
    SpaceChatPageParams,
    SpaceChatParams,
    StartSpaceRoundParams,
    StopSpaceRoundParams,
    TeamTemplateParams,
    UpdateSpaceWorkParams,
)
from my_agent.spaces.types import SpaceParams
from my_agent.spaces.work_types import SaveWorkGraphParams, StartWorkGraphParams
from my_agent.terminals.types import (
    ListTerminalsParams,
    OpenTerminalParams,
    ReadTerminalParams,
    ResizeTerminalParams,
    TerminalControlParams,
    TerminalParams,
    WriteTerminalParams,
)

if TYPE_CHECKING:
    from my_agent.rpc.application import RpcApplication

M5_METHODS = (
    "spaces.work",
    "spaces.work_graph",
    "spaces.work_graph_save",
    "spaces.work_graph_start",
    "spaces.generate",
    "spaces.design_open",
    "spaces.design_get",
    "spaces.design_save",
    "spaces.design_send",
    "spaces.design_start",
    "spaces.chat_view",
    "spaces.chat",
    "spaces.start_round",
    "spaces.stop",
    "spaces.templates",
    "spaces.template_save",
    "spaces.template_copy",
    "spaces.template_import",
    "spaces.template_export",
    "documents.list",
    "documents.read",
    "documents.search",
    "documents.save",
    "documents.drafts",
    "documents.draft",
    "documents.operate",
    "documents.patch",
    "documents.diff",
    "documents.restore",
    "terminals.list",
    "terminals.open",
    "terminals.read",
    "terminals.write",
    "terminals.resize",
    "terminals.control",
    "terminals.interrupt",
    "terminals.stop",
    "git.status",
    "git.settings",
    "git.configure",
    "git.diff",
    "git.stage",
    "git.unstage",
    "git.init",
    "git.commit",
    "git.history",
    "intelligence.list",
    "intelligence.configure",
    "intelligence.query",
    "attachments.import",
    "attachments.chunk",
    "attachments.read",
)


async def dispatch_m5(app: "RpcApplication", method: str, params: dict[str, object]) -> BaseModel:
    """边界校验一次后调用业务服务。 Validate once at the boundary then call the business service."""
    if method == "spaces.work":
        return await app.team.update_work(UpdateSpaceWorkParams.model_validate(params))
    if method == "spaces.work_graph":
        return await app.team.work_graph.get(SpaceParams.model_validate(params))
    if method == "spaces.work_graph_save":
        return await app.team.work_graph.save(SaveWorkGraphParams.model_validate(params))
    if method == "spaces.work_graph_start":
        return await app.team.work_graph.start(StartWorkGraphParams.model_validate(params))
    if method == "spaces.generate":
        return await app.team.generate(GenerateTeamParams.model_validate(params))
    if method == "spaces.design_open":
        return await app.team.design.open(OpenTeamDesignParams.model_validate(params))
    if method == "spaces.design_get":
        return await app.team.design.get(SpaceParams.model_validate(params))
    if method == "spaces.design_save":
        return await app.team.design.save(SaveTeamDesignParams.model_validate(params))
    if method == "spaces.design_send":
        return await app.team.design.send(SendTeamDesignParams.model_validate(params))
    if method == "spaces.design_start":
        return await app.team.design.start(StartTeamDesignParams.model_validate(params))
    if method == "spaces.chat_view":
        return await app.team.chat_view(SpaceChatPageParams.model_validate(params))
    if method == "spaces.chat":
        return await app.team.chat(SpaceChatParams.model_validate(params))
    if method == "spaces.start_round":
        return await app.team.start_round(StartSpaceRoundParams.model_validate(params))
    if method == "spaces.stop":
        return await app.team.stop(StopSpaceRoundParams.model_validate(params))
    if method == "spaces.templates":
        EmptyParams.model_validate(params)
        return await app.team.templates()
    if method == "spaces.template_save":
        return await app.team.save_template(SaveTeamTemplateParams.model_validate(params))
    if method == "spaces.template_copy":
        return await app.team.copy_template(CopyTeamTemplateParams.model_validate(params))
    if method == "spaces.template_import":
        return await app.team.import_template(ImportTeamTemplateParams.model_validate(params))
    if method == "spaces.template_export":
        return await app.team.export_template(TeamTemplateParams.model_validate(params))
    if method == "documents.list":
        return await app.documents.list(DocumentListParams.model_validate(params))
    if method == "documents.read":
        return await app.documents.read(DocumentParams.model_validate(params))
    if method == "documents.search":
        return await app.documents.search(DocumentSearchParams.model_validate(params))
    if method == "documents.save":
        return await app.documents.save(SaveDocumentParams.model_validate(params))
    if method == "documents.drafts":
        return await app.documents.drafts(DocumentSessionParams.model_validate(params))
    if method == "documents.draft":
        return await app.documents.draft(SaveDocumentParams.model_validate(params))
    if method == "documents.operate":
        return await app.documents.operate(DocumentOperationParams.model_validate(params))
    if method == "documents.patch":
        return await app.documents.patch(PatchDocumentsParams.model_validate(params))
    if method == "documents.diff":
        return await app.documents.diff(DocumentChangeParams.model_validate(params))
    if method == "documents.restore":
        return await app.documents.restore(DocumentChangeParams.model_validate(params))
    if method == "terminals.list":
        return await app.terminals.list(ListTerminalsParams.model_validate(params))
    if method == "terminals.open":
        return await app.terminals.open(OpenTerminalParams.model_validate(params))
    if method == "terminals.read":
        return await app.terminals.read(ReadTerminalParams.model_validate(params))
    if method == "terminals.write":
        return await app.terminals.write(WriteTerminalParams.model_validate(params))
    if method == "terminals.resize":
        return await app.terminals.resize(ResizeTerminalParams.model_validate(params))
    if method == "terminals.control":
        return await app.terminals.control(TerminalControlParams.model_validate(params))
    if method == "terminals.interrupt":
        return await app.terminals.interrupt(TerminalParams.model_validate(params))
    if method == "terminals.stop":
        return await app.terminals.stop(TerminalParams.model_validate(params))
    if method == "git.settings":
        return await app.local_git.settings(GitProjectParams.model_validate(params))
    if method == "git.configure":
        return await app.local_git.configure(ConfigureGitParams.model_validate(params))
    if method == "git.status":
        return await app.local_git.status(GitProjectParams.model_validate(params))
    if method == "git.diff":
        return await app.local_git.diff(GitDiffParams.model_validate(params))
    if method == "git.stage":
        return await app.local_git.stage(GitPathsParams.model_validate(params))
    if method == "git.unstage":
        return await app.local_git.unstage(GitPathsParams.model_validate(params))
    if method == "git.init":
        return await app.local_git.init(GitProjectParams.model_validate(params))
    if method == "git.commit":
        return await app.local_git.commit(GitCommitParams.model_validate(params))
    if method == "git.history":
        return await app.local_git.history(GitHistoryParams.model_validate(params))
    if method == "intelligence.list":
        return await app.intelligence.catalog(IntelligenceParams.model_validate(params))
    if method == "intelligence.configure":
        return await app.intelligence.configure(SaveLanguageServers.model_validate(params))
    if method == "intelligence.query":
        return await app.intelligence.query(LanguageQuery.model_validate(params))
    if method == "attachments.import":
        return await app.attachments.import_file(ImportAttachment.model_validate(params))
    if method == "attachments.chunk":
        return await app.attachments.chunk(ImageChunk.model_validate(params))
    if method == "attachments.read":
        return await app.attachments.read(AttachmentParams.model_validate(params))
    raise ValueError("Unknown M5 method")
