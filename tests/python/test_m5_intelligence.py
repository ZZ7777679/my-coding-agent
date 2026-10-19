"""真实 Pyright / TypeScript LSP 的隔离验收，不调用模型。

Isolated acceptance of actual Pyright and TypeScript LSP servers without model calls.
"""

import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import pytest

from my_agent.config import load_config
from my_agent.documents.types import SaveDocumentParams
from my_agent.errors import AgentError
from my_agent.intelligence.service import LspConnection
from my_agent.intelligence.types import (
    IntelligenceParams,
    LanguageQuery,
    LanguageServer,
    SaveLanguageServers,
)
from my_agent.models.types import ToolCall
from my_agent.runtime.loop import recoverable_tool_error
from my_agent.runtime.tools import ToolContext
from tests.python.test_goal_controller import app_at, create_session
from tests.python.test_tasks import ContextModel


def renamed_text(content, edits):
    """按 LSP 范围应用 ASCII 样本的编辑建议，保留原基线供保存核对。

    Apply LSP edits to ASCII fixtures while retaining the base text for save validation.
    """
    lines = content.splitlines(keepends=True)

    def offset(position):
        """转换本场景 ASCII 的零基位置。

        Convert zero-based positions in this ASCII fixture.
        """
        return sum(len(line) for line in lines[: position["line"]]) + position["character"]

    spans = sorted(
        (
            (offset(edit["range"]["start"]), offset(edit["range"]["end"]), edit["newText"])
            for edit in edits
        ),
        reverse=True,
    )
    result = content
    for start, end, text in spans:
        result = result[:start] + text + result[end:]
    return result


@pytest.mark.parametrize(
    "language,filename,source,line,character",
    [
        (
            "python",
            "sample.py",
            "def add(left: int, right: int) -> int:\n"
            "    return left + right\n\n"
            'total = add(1, 2)\nbad: int = "wrong"\n',
            3,
            9,
        ),
        (
            "typescript",
            "sample.ts",
            "function add(left: number, right: number): number {\n"
            "  return left + right;\n}\n"
            'const total = add(1, 2);\nconst bad: number = "wrong";\n',
            3,
            15,
        ),
    ],
)
def test_actual_lsp_queries_and_rename_save(tmp_path, language, filename, source, line, character):
    """查询真实服务的六种结果并用正式编辑器保存重命名建议。

    Query six actual server capabilities and save rename suggestions through the production
    editor.
    """

    async def scenario():
        """真实子进程、项目环境、LSP 和文件记录，模型请求为零。

        Use actual processes, environments, LSP and file records with zero model requests.
        """
        project = tmp_path / "project"
        model = ContextModel()
        evidence = {}
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, project)
            path = project / filename
            path.write_text(source, encoding="utf-8", newline="\n")
            project_id = created.task.project_id
            initial = await app.intelligence.catalog(IntelligenceParams(project_id=project_id))
            assert all(item.status == "not_started" for item in initial.states)
            for action in [
                "definition",
                "references",
                "symbols",
                "hover",
                "completion",
                "diagnostics",
                "rename",
            ]:
                result = await app.intelligence.query(
                    LanguageQuery(
                        project_id=project_id,
                        path=filename,
                        language=language,
                        action=action,
                        line=line,
                        character=character,
                        new_name="sum_values" if action == "rename" else None,
                    )
                )
                assert result.source == "disk" and result.content == source
                assert result.result is not None
                evidence[action] = result.model_dump(mode="json")
            assert evidence["definition"]["result"]
            assert len(evidence["references"]["result"]) >= 2
            assert evidence["hover"]["result"]["contents"]
            diagnostics = evidence["diagnostics"]["result"]
            entries = diagnostics.get("items", []) if isinstance(diagnostics, dict) else diagnostics
            assert entries, diagnostics
            rename = evidence["rename"]["result"]

            def matches(uri):
                """按 Windows 路径比较 URI，不依赖驱动器编码与大小写。

                Compare file URIs as Windows paths independent of drive encoding and case.
                """
                decoded = unquote(urlsplit(uri).path)
                if len(decoded) > 2 and decoded[0] == "/" and decoded[2] == ":":
                    decoded = decoded[1:]
                return Path(decoded).resolve() == path.resolve()

            edits = [
                edit
                for uri, values in rename.get("changes", {}).items()
                if matches(uri)
                for edit in values
            ]
            for change in rename.get("documentChanges", []):
                if matches(change.get("textDocument", {}).get("uri", "")):
                    edits.extend(change.get("edits", []))
            assert len(edits) >= 2, rename
            snapshots = evidence["rename"]["rename_documents"]
            assert snapshots[0]["path"] == filename and snapshots[0]["content"] == source
            content = renamed_text(source, edits)
            saved = await app.documents.save(
                SaveDocumentParams(
                    session_id=created.session.session_id,
                    path=filename,
                    base_content=source,
                    content=content,
                )
            )
            assert saved.change_id and path.read_text(encoding="utf-8") == content
            assert "sum_values" in content and "add(" not in content
            with pytest.raises(AgentError) as stale:
                await app.documents.save(
                    SaveDocumentParams(
                        session_id=created.session.session_id,
                        path=filename,
                        base_content=snapshots[0]["content"],
                        content=content + "\n",
                    )
                )
            assert stale.value.code == "DOCUMENT_CONFLICT"
            assert path.read_text(encoding="utf-8") == content
            if language == "python":
                alpha = "def alpha(value: int) -> int:\n    return value\n"
                beta = "def beta(value: str) -> str:\n    return value\n"
                results = await asyncio.gather(
                    *(
                        app.intelligence.query(
                            LanguageQuery(
                                project_id=project_id,
                                path=filename,
                                language=language,
                                action="hover",
                                line=0,
                                character=5,
                                content=text,
                                version=10,
                            )
                        )
                        for text in [alpha, beta]
                    )
                )
                assert "alpha" in json.dumps(results[0].result)
                assert "beta" in json.dumps(results[1].result)
                assert results[0].content == alpha and results[1].content == beta
                assert path.read_text(encoding="utf-8") == content
                evidence["concurrent_drafts"] = [
                    result.model_dump(mode="json") for result in results
                ]
            state = await app.intelligence.catalog(IntelligenceParams(project_id=project_id))
            assert any(item.status == "running" for item in state.states)
            processes = [connection.process for connection in app.intelligence.connections.values()]
            assert not model.inputs
        assert all(process.returncode is not None for process in processes)
        (tmp_path / "lsp-results.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8", newline="\n"
        )

    asyncio.run(scenario())


def test_cancelled_initialization_cleans_owned_server(tmp_path, monkeypatch):
    """初始化被用户取消后清理真实进程，不留半初始化连接。

    Clean the actual owned process after cancellation without leaving a partial connection.
    """

    async def scenario():
        """仅控制协议请求时机，子进程与清理均为真实实现。

        Control only request timing while retaining the actual subprocess and cleanup.
        """
        entered = asyncio.Event()
        processes = []
        original = LspConnection.request

        async def pause_initialize(connection, method, params):
            """在真实进程初始化前提供可确定的取消时机。

            Provide a deterministic cancellation point before actual process initialization.
            """
            if method == "initialize":
                processes.append(connection.process)
                entered.set()
                await asyncio.Event().wait()
            return await original(connection, method, params)

        monkeypatch.setattr(LspConnection, "request", pause_initialize)
        async with app_at(tmp_path / "data", ContextModel()) as app:
            project = tmp_path / "project"
            created = await create_session(app, project)
            (project / "source.py").write_text("value = 1\n", encoding="utf-8")
            task = asyncio.create_task(
                app.intelligence.query(
                    LanguageQuery(
                        project_id=created.task.project_id,
                        path="source.py",
                        language="python",
                        action="hover",
                    )
                )
            )
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not app.intelligence.connections
            assert processes and all(process.returncode is not None for process in processes)

    asyncio.run(scenario())


def test_missing_lsp_keeps_file_tools_available(tmp_path, monkeypatch):
    """服务未安装是工具反馈，后续正常文件读取仍可执行。

    Missing servers produce tool feedback while normal file reading remains available.
    """

    async def scenario():
        """真实配置和原工具装配，缺失不触发安装或程序。

        Use actual settings and tool composition without installation or processes.
        """
        async with app_at(tmp_path / "data", ContextModel()) as app:
            project = tmp_path / "project"
            created = await create_session(app, project)
            (project / "source.py").write_text("value = 1\n", encoding="utf-8")
            await app.intelligence.configure(
                SaveLanguageServers(
                    project_id=created.task.project_id,
                    servers=[
                        LanguageServer(
                            server_id="missing",
                            languages=["python"],
                            program=str(project / "absent-server.exe"),
                        )
                    ],
                )
            )
            context = ToolContext(
                root=project,
                limits=load_config(app.storage.location).run,
                stop=threading.Event(),
                project_id=created.task.project_id,
                session_id=created.session.session_id,
                run_id=str(uuid4()),
                mode="plan",
                plan_document=None,
            )
            tools = app.sessions.tool_factory(context)
            query = ToolCall(
                tool_call_id="missing",
                name="code_insight",
                arguments={"path": "source.py", "language": "python", "action": "hover"},
            )
            missing = await tools.execute(query)
            assert missing.is_error and json.loads(missing.content)["code"] == "LSP_NOT_INSTALLED"
            assert recoverable_tool_error(query, missing)
            read = await tools.execute(
                ToolCall(tool_call_id="file", name="read_file", arguments={"path": "source.py"})
            )
            assert not read.is_error and "value = 1" in read.content
            assert not app.intelligence.connections

            async def connected(project_id, language):
                """文件读取发生在协议通知前，此处只替换无需使用的连接。

                File reads precede protocol notifications; replace the unused connection only.
                """
                return (
                    LanguageServer(server_id="fixture", languages=[language], program="unused"),
                    SimpleNamespace(document_lock=asyncio.Lock()),
                    project,
                )

            monkeypatch.setattr(app.intelligence, "_connect", connected)
            absent_call = query.model_copy(
                update={"arguments": {"path": "absent.py", "language": "python", "action": "hover"}}
            )
            absent = await tools.execute(absent_call)
            assert absent.is_error and json.loads(absent.content)["code"] == "FILE_NOT_FOUND"
            assert recoverable_tool_error(absent_call, absent)

    asyncio.run(scenario())
