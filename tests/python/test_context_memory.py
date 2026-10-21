"""M3 使用真实 RPC / 存储与可控模型验证窗口和记忆。

M3 checks use real RPC/storage and a controllable model for windows and memory.
"""

import asyncio
import copy
import json
import sys
from uuid import uuid4

import pytest

from my_agent.config import DEFAULTS
from my_agent.context.service import SUMMARY_PROMPT
from my_agent.context.tokens import estimate_tokens
from my_agent.context.types import ContextSettings, ContextState
from my_agent.context.window import (
    assemble,
    byte_size,
    externalize,
    groups,
    projected_records,
    trim_candidates,
)
from my_agent.errors import AgentError
from my_agent.memory.types import MemoryFields, MemoryQuery, MemorySettings
from my_agent.models.failures import ModelResponseError
from my_agent.models.types import TokenUsage
from my_agent.sessions.projection import summarize
from tests.python.test_goal_controller import app_at, call, create_session, turn


class KnowledgeModel:
    """摘要和提取使用相同模型对象，并记录实际请求输入。

    Summaries and extraction share one model object that records actual request inputs.
    """

    def __init__(self):
        """保留请求与可控制的输出模式。

        Keep requests and controllable response modes.
        """
        self.requests = []
        self.long = False
        self.publish = False

    def check_available(self):
        """离线检查不访问凭据。

        Offline checks never access credentials.
        """

    async def complete(self, **kwargs):
        """按请求用途响应，不伪造文件执行事实。

        Respond by request purpose without invented file effects.
        """
        self.requests.append({**kwargs, "messages": copy.deepcopy(kwargs["messages"])})
        if kwargs["messages"][0]["content"] == SUMMARY_PROMPT:
            return turn(
                text=(
                    "Preserve offline use and user corrections. Old details can be read "
                    "from history."
                )
            )
        if kwargs["messages"][0]["content"].startswith("Extract only reusable"):
            return turn(
                text=json.dumps(
                    {
                        "entries": [
                            {
                                "fields": {
                                    "title": "Offline page",
                                    "content": "The project works offline without CDN.",
                                }
                            }
                        ]
                    }
                )
            )
        if self.publish:
            self.publish = False
            return turn(
                call(
                    "publish_task_decision",
                    text="Use only the standard library",
                    status="user_confirmed",
                )
            )
        return turn(text=("old material " * 1800) if self.long else "Current request completed")


async def run(app, sid, prompt):
    """等待真实 Run 收尾。

    Await actual run finalization.
    """
    await app.dispatch(
        "runs.start",
        {
            "session_id": sid,
            "operation_id": str(uuid4()),
            "prompt": prompt,
            "limits": None,
            "mode": "normal",
        },
    )
    active = app.sessions.active_for(sid)
    assert active is not None
    await asyncio.wait_for(active.task, 15)
    return (await app.sessions.view(sid)).summary


def test_legacy_summary_budget_migrates_once_and_preserves_explicit_overrides():
    """升级旧默认但保留自定义值，新版本仍可显式设置 2048。

    Upgrade the legacy default, retain custom values and allow explicit 2048 in the new version.
    """
    assert (
        ContextState.model_validate(
            {"settings": {"summary_output_tokens": 2048}}
        ).settings.summary_output_tokens
        is None
    )
    assert (
        ContextState.model_validate(
            {"settings": {"summary_output_tokens": 4096}}
        ).settings.summary_output_tokens
        == 4096
    )
    assert (
        ContextState.model_validate(
            {"schema_version": 2, "settings": {"summary_output_tokens": 2048}}
        ).settings.summary_output_tokens
        == 2048
    )
    old = ContextState.model_validate(
        {
            "schema_version": 2,
            "settings": {
                "automatic": False,
                "recent_ratio": 0.2,
                "prepare_ratio": 0.75,
                "target_ratio": 0.55,
                "old_tool_preview_chars": 512,
            },
        }
    )
    assert old.settings == ContextSettings(automatic=False)
    assert old.migrated_from_bytes and old.schema_version == 3
    assert not ContextState().migrated_from_bytes
    assert ContextSettings().auto_trigger_tokens == 800000
    assert (
        ContextState.model_validate(
            {"schema_version": 3, "settings": {"auto_trigger_tokens": 128000}}
        ).settings.auto_trigger_tokens
        == 128000
    )


def test_tool_preview_preserves_tail_facts_and_pair_boundaries():
    """大结果保留头尾与来源；并发调用仅在全部结果配齐后切开。

    Preserve output endpoints/provenance and split parallel calls only after all results.
    """
    text = json.dumps(
        {"exit_code": 2, "stdout": "START " + "long log " * 8000, "stderr": "EXACT_ERROR_73"}
    )
    message = {"role": "tool", "tool_call_id": "a", "content": text}
    preview = externalize(9, message, 1000)
    assert "START" in preview["content"] and "EXACT_ERROR_73" in preview["content"]
    assert '"exit_code": 2' in preview["content"] and "entry_seq=9" in preview["content"]
    assert estimate_tokens(preview["content"]) <= 1000
    assert preview["tool_call_id"] == "a" and message["content"] == text
    items = [
        (1, {"role": "user", "content": "latest"}),
        (2, {"role": "assistant", "tool_calls": [{"id": "a"}, {"id": "b"}]}),
        (3, message),
        (4, {"role": "tool", "tool_call_id": "b", "content": "done"}),
    ]
    assert [len(group) for group in groups(items)] == [1, 3]
    assert [len(group) for group in groups(items[:-1])] == [1]


def test_manual_cut_releases_more_than_automatic_and_restores_once(tmp_path):
    """同一原历史对比两种切点，重启只采用一份摘要并保留最新要求一次。

    Compare cuts on the same history; restore one summary and one latest user instruction.
    """

    async def scenario():
        """用实际持久状态验证切点和 usage 基准失效。

        Exercise persisted cuts and usage baseline invalidation.
        """
        model = KnowledgeModel()
        model.long = True
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            contexts = app.sessions.contexts
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            for index in range(5):
                await run(app, sid, f"LATEST {index}")
                if index == 0:
                    await contexts.start(sid)
                    await contexts.wait(sid)
                    empty = await contexts.view(sid)
                    assert empty.job.outcome == "nothing" and empty.job.requests == 0
            raw = app.sessions.store.path(sid).read_bytes()
            log = await app.sessions._load(sid)
            original = contexts.store.read(sid)
            policy = ContextSettings(auto_trigger_tokens=1)
            await contexts.configure(sid, policy)
            from my_agent.runtime.settings import RunLimits

            await contexts._start(
                log, RunLimits.model_validate(DEFAULTS["run"]), None, None, automatic=True
            )
            await contexts.wait(sid)
            auto = await contexts.view(sid)
            assert auto.checkpoint and auto.job.retained_tokens >= 15000
            contexts.store.save(sid, original)
            await contexts.start(sid)
            await contexts.wait(sid)
            manual = await contexts.view(sid)
            assert manual.checkpoint.through_seq > auto.checkpoint.through_seq
            assert manual.job.history_after_tokens < auto.job.history_after_tokens
            assert manual.job.requests == auto.job.requests == 1
            restored = contexts.store.read(sid)
            window = assemble(log, restored.checkpoints[-1], restored.previews)
            assert sum(m.get("content") == "LATEST 4" for m in window) == 1
            assert sum("Earlier conversation summary" in str(m.get("content")) for m in window) == 1
            assert app.sessions.store.path(sid).read_bytes() == raw
            from my_agent.context.window import records

            sources = dict(records(log))
            payload = json.loads(model.requests[-1]["messages"][1]["content"])
            for group in payload["materials"]:
                for message in group["messages"]:
                    assert message["role"] == sources[message["source_seq"]]["role"]
                    assert message["source_seq"] <= group["history_through_seq"]
            assert all("source_seq" not in message for message in window)
            _, prior, definitions, _ = contexts.request_baselines[sid]
            appended = [{"role": "user", "content": "new increment"}]
            assert contexts._estimate(log, [*prior, *appended], definitions) == 1 + estimate_tokens(
                appended
            )
            assert contexts._estimate(log, window, definitions) == estimate_tokens(
                [window, definitions]
            )

    asyncio.run(scenario())


def test_context_token_display_uses_latest_main_usage_and_model_window(tmp_path):
    """单次真实用量与累计费用分开；切模型、缺用量和压缩后不复用旧值。

    Keep per-request usage separate from cost totals and invalidate stale or missing counts.
    """

    async def scenario():
        """模型只替换用量，保留实际会话、工具、摘要和 RPC 流程。

        Substitute model usage while retaining real session, tool, compaction and RPC flows.
        """

        class MeteredModel(KnowledgeModel):
            """提供明确输入量，也可模拟服务未返回用量。

            Supply explicit input counts or simulate unreported usage.
            """

            unknown = False

            async def complete(self, **kwargs):
                """在既有可控响应上覆盖 usage。 Override usage on controlled responses."""
                result = await super().complete(**kwargs)
                return result.model_copy(
                    update={
                        "usage": TokenUsage(
                            input_tokens=None if self.unknown else 123456, output_tokens=77
                        )
                    }
                )

        model = MeteredModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            view = await app.dispatch("context.get", {"session_id": sid})
            assert view.tokens.status == "not_measured" and view.tokens.input_tokens is None
            assert view.tokens.window_tokens == 1000000
            model.long = True
            await run(app, sid, "First turn")
            model.publish = True
            result = await run(app, sid, "Publish the shared decision")
            assert result.run.input_tokens == 246912
            view = await app.dispatch("context.get", {"session_id": sid})
            assert view.tokens.input_tokens == 123456 and view.tokens.status == "reported"
            model.long = False
            # 摘要的 usage 不混进上下文；压缩后等新主请求报告再显示占用。
            # Summary usage is not context occupancy; wait for a post-compaction main request.
            await app.sessions.contexts.start(sid)
            await app.sessions.contexts.wait(sid)
            view = await app.dispatch("context.get", {"session_id": sid})
            assert view.checkpoint and view.tokens.status == "compacted"
            assert view.tokens.input_tokens == 123456
            await run(app, sid, "Continue from summary")
            await app.sessions.select_model(sid, str(uuid4()), "deepseek-v4.1-flash")
            view = await app.dispatch("context.get", {"session_id": sid})
            assert view.tokens.model_id == "deepseek-v4.1-flash"
            assert view.tokens.status == "model_changed" and view.tokens.input_tokens is None
            model.unknown = True
            await run(app, sid, "Reply without usage")
            view = await app.dispatch("context.get", {"session_id": sid})
            assert view.tokens.status == "not_reported" and view.tokens.input_tokens is None
            app.sessions.last_log = None
            assert (await app.dispatch("context.get", {"session_id": sid})).tokens == view.tokens

    asyncio.run(scenario())


@pytest.mark.parametrize("owner", ["standalone", "run"])
def test_failed_compaction_retains_usage_history_and_failure_ownership(tmp_path, owner):
    """截断摘要保留统计和原历史；只影响所属运行，不毒化后续对话。

    Truncated summaries retain usage/history and fail only their owner, not later conversation.
    """

    async def scenario():
        """通过真实 RPC 和存储检查失败接续，模型仅提供确定响应。

        Check failure continuation through actual RPC/storage with deterministic model responses.
        """

        class TruncatedSummary(KnowledgeModel):
            """仅摘要返回已知用量的截断失败。

            Fail only summaries with known usage and a truncation reason.
            """

            async def complete(self, **kwargs):
                if kwargs["messages"][0]["content"] == SUMMARY_PROMPT:
                    self.requests.append(kwargs)
                    raise ModelResponseError(
                        "MODEL_OUTPUT_TRUNCATED",
                        "finish_reason=length",
                        TokenUsage(input_tokens=32000, output_tokens=2048),
                        "length",
                    )
                return await super().complete(**kwargs)

        model = TruncatedSummary()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            for index in range(3):
                await run(app, sid, f"Previous task {index}")
            original = app.sessions.store.path(sid).read_bytes()
            if owner == "standalone":
                await app.sessions.contexts.start(sid)
                with pytest.raises(ModelResponseError):
                    # 留在调度表中，复现下一次 prepare 遇到旧失败的路径。
                    # Leave the task registered to exercise prepare's stale failure path.
                    await app.sessions.contexts.jobs[sid]
            else:
                await app.sessions.contexts.configure(
                    sid, ContextSettings(auto_trigger_tokens=1, keep_recent_tokens=0)
                )
                failed = await run(app, sid, "Continue with background compaction")
                assert failed.run.status == "failed"
                assert failed.run.code == "MODEL_OUTPUT_TRUNCATED"
                assert failed.run.output_tokens >= 2048
            view = await app.sessions.contexts.view(sid)
            assert view.job.status == "failed" and view.job.requests == 1
            assert view.job.finish_reason == "length"
            assert view.job.output_token_limit == DEFAULTS["run"]["max_output_tokens"]
            assert view.job.usage == TokenUsage(input_tokens=32000, output_tokens=2048)
            assert view.totals.reported_output_tokens == 2048 and view.totals.unknown_jobs == 0
            assert view.checkpoint is None
            assert app.sessions.store.path(sid).read_bytes().startswith(original)
            await app.sessions.contexts.configure(sid, ContextSettings(automatic=False))
            assert (await run(app, sid, "Ordinary follow-up")).run.status == "completed"
            assert (
                len([r for r in model.requests if r["messages"][0]["content"] == SUMMARY_PROMPT])
                == 1
            )
            # 独立显式重试才发下一请求，并采用用户设置的输出上限。
            # Only an explicit retry sends another request, using the user's output override.
            await app.sessions.contexts.configure(
                sid, ContextSettings(automatic=False, summary_output_tokens=4096)
            )
            await app.sessions.contexts.start(sid)
            with pytest.raises(ModelResponseError):
                await app.sessions.contexts.wait(sid)
            assert model.requests[-1]["limits"].max_output_tokens == 4096

    asyncio.run(scenario())


def test_inflight_standalone_compaction_does_not_hold_or_cancel_normal_run(tmp_path):
    """独立整理等待中普通对话可以完成，运行收尾不取消该整理。

    Normal conversation completes while standalone compaction waits and leaves that job intact.
    """

    async def scenario():
        """用事件控制等待顺序，不依赖真实延迟。

        Control ordering with events instead of real delays.
        """
        started = asyncio.Event()
        release = asyncio.Event()

        class WaitingSummary(KnowledgeModel):
            """摘要等待显式释放，普通回答立即返回。

            Wait for explicit summary release while answering ordinary requests immediately.
            """

            async def complete(self, **kwargs):
                if kwargs["messages"][0]["content"] == SUMMARY_PROMPT:
                    started.set()
                    await release.wait()
                return await super().complete(**kwargs)

        model = WaitingSummary()
        model.long = True
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            for index in range(3):
                await run(app, sid, f"Old task {index}")
            model.long = False
            await app.sessions.contexts.start(sid)
            await asyncio.wait_for(started.wait(), 5)
            job = app.sessions.contexts.jobs[sid]
            assert (
                await run(app, sid, "Ordinary work while summary waits")
            ).run.status == "completed"
            assert not job.done()
            release.set()
            await app.sessions.contexts.wait(sid)
            assert (await app.sessions.contexts.view(sid)).checkpoint is not None

    asyncio.run(scenario())


async def scenario_oversized_history_compacts_and_keeps_original_and_latest_input(tmp_path):
    """旧历史已超窗仍分段整理，最新要求和原记录保留。

    Already oversized history compacts in bounded chunks while preserving latest input and
    raw facts.

    """
    model = KnowledgeModel()
    async with app_at(tmp_path / "data", model) as app:
        created = await create_session(app, tmp_path / "project")
        sid = created.session.session_id
        await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
        model.long = True
        for index in range(6):
            assert (await run(app, sid, f"Old work {index}")).run.status == "completed"
        original = (app.sessions.store.path(sid)).read_bytes()
        model.long = False
        await app.dispatch(
            "config.update",
            {"model_id": "glm-5.3-flash", "run": {**DEFAULTS["run"], "max_context_bytes": 4096}},
        )
        await app.sessions.contexts.configure(sid, ContextSettings(auto_trigger_tokens=24000))
        result = await run(app, sid, "LATEST correction: add reset to zero")
        assert result.run.status == "completed", result.run
        assert result.run.requests > 1
        summary_calls = [
            request
            for request in model.requests
            if request["messages"][0]["content"] == SUMMARY_PROMPT
        ]
        assert summary_calls
        assert len(summary_calls) == 1
        # 旧字节预算不再拆分能放入模型的正常请求。
        # Legacy byte limits no longer split requests that fit the model.
        assert byte_size([summary_calls[0]["messages"], []]) > 4096
        assert app.sessions.store.path(sid).read_bytes().startswith(original)
        view = await app.dispatch("context.get", {"session_id": sid})
        assert view.checkpoint and view.window_bytes < view.raw_bytes
        last = [
            request
            for request in model.requests
            if request["messages"][0]["content"] != SUMMARY_PROMPT
        ][-1]
        assert any(
            msg.get("content") == "LATEST correction: add reset to zero" for msg in last["messages"]
        )
        checkpoint = view.checkpoint
        app.sessions.last_log = None
        assert (await app.dispatch("context.get", {"session_id": sid})).checkpoint == checkpoint
        page = await app.dispatch(
            "context.history", {"session_id": sid, "query": "old material", "max_chars": 100}
        )
        assert page.items and page.items[0].next_offset == 100


async def scenario_memory_save_correct_forget_and_publish_task_decision(tmp_path):
    """改正与遗忘影响下一请求，任务决定不晋升为长期记忆。

    Corrections/forgetting affect the next input; task decisions do not become long-term memory.
    """
    model = KnowledgeModel()
    async with app_at(tmp_path / "data", model) as app:
        created = await create_session(app, tmp_path / "project")
        sid = created.session.session_id
        await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
        saved = await app.dispatch(
            "memory.save",
            {
                "session_id": sid,
                "fields": {"title": "Offline", "content": "Use CDN never", "pinned": True},
            },
        )
        entry = saved.entries[0]
        assert (await run(app, sid, "Describe offline requirements")).run.status == "completed"
        assert "Use CDN never" in model.requests[-1]["messages"][0]["content"]
        sent = (await app.sessions.contexts.view(sid)).last_request
        assert sent is not None
        first_manifest = sent.model_dump()
        actual = model.requests[-1]
        assert sent.manifest.message_count == len(actual["messages"])
        assert sent.manifest.request_bytes == byte_size([actual["messages"], actual["tools"]])
        adopted = next(item for item in sent.manifest.materials if item.kind == "memory")
        assert adopted.source_id == entry.memory_id and adopted.revision == entry.revision
        assert adopted.preview == "Use CDN never"
        assert any(item.kind == "task" for item in sent.manifest.materials)
        await app.dispatch(
            "memory.save",
            {
                "session_id": sid,
                "memory_id": entry.memory_id,
                "fields": {"title": "Offline", "content": "Use bundled files", "pinned": True},
            },
        )
        assert (await app.sessions.contexts.view(sid)).last_request.model_dump() == first_manifest
        await run(app, sid, "Describe offline requirements")
        assert "Use bundled files" in model.requests[-1]["messages"][0]["content"]
        assert "Use CDN never" not in model.requests[-1]["messages"][0]["content"]
        second = (await app.sessions.contexts.view(sid)).last_request
        assert (
            next(item for item in second.manifest.materials if item.kind == "memory").preview
            == "Use bundled files"
        )
        await app.dispatch("memory.forget", {"session_id": sid, "memory_id": entry.memory_id})
        count = len(model.requests)
        model.publish = True
        await run(app, sid, "Task-wide correction: use only the standard library")
        assert len(model.requests) == count + 2
        assert "Use bundled files" not in model.requests[-1]["messages"][0]["content"]
        assert not any(
            item.kind == "memory"
            for item in (await app.sessions.contexts.view(sid)).last_request.manifest.materials
        )
        task = await app.dispatch("tasks.get", {"task_id": created.task.task_id})
        assert task.work.decisions[-1].decision.text == "Use only the standard library"
        assert task.fields.constraints == ""
        assert (await app.sessions.memory.page(sid, MemoryQuery())).entries == []
        assert summarize(await app.sessions._load(sid)).can_continue


async def scenario_auto_memory_starts_after_enable_and_uses_new_material(tmp_path):
    """首次启用不回扫旧聊天，独立维护的费用和产物可查。

    First enablement skips old chat; independent maintenance exposes cost and saved output.
    """
    model = KnowledgeModel()
    async with app_at(tmp_path / "data", model) as app:
        created = await create_session(app, tmp_path / "project")
        sid = created.session.session_id
        await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
        await run(app, sid, "Old private task status")
        await app.sessions.memory.configure(sid, MemorySettings())
        model.publish = True
        await run(app, sid, "Remember this project works offline")
        pending = list(app.sessions.memory.jobs.values())
        await asyncio.gather(*pending)
        page = await app.sessions.memory.page(sid, MemoryQuery())
        assert page.entries[0].content == "The project works offline without CDN."
        assert page.state.job.status == "completed"
        assert page.state.job.requests == 1
        extraction = [
            request
            for request in model.requests
            if request["messages"][0]["content"].startswith("Extract only reusable")
        ]
        assert len(extraction) == 1
        assert "Old private task status" not in extraction[0]["messages"][1]["content"]


def test_oversized_history_compacts_and_keeps_original_and_latest_input(tmp_path):
    """在独立事件循环中验证场景。

    Run the scenario in an isolated event loop.
    """
    asyncio.run(scenario_oversized_history_compacts_and_keeps_original_and_latest_input(tmp_path))


def test_memory_save_correct_forget_and_publish_task_decision(tmp_path):
    """在独立事件循环中验证场景。

    Run the scenario in an isolated event loop.
    """
    asyncio.run(scenario_memory_save_correct_forget_and_publish_task_decision(tmp_path))


def test_context_tools_share_manifest_and_existing_compaction_job(tmp_path):
    """模型查看与桌面采用同份清单；工具压缩进入既有预算和下一请求窗口。

    Model and desktop share a manifest; tool compaction uses existing budgets and windows.
    """

    async def scenario():
        """保留生产工具链，仅替换模型响应。

        Keep production tools and replace only model responses.
        """

        class ContextModel(KnowledgeModel):
            """依次调用状态和压缩，避免测试引入轮询。

            Call status and compaction once without polling.
            """

            step = 0
            enabled = False

            async def complete(self, **kwargs):
                """辅助摘要继续使用原替身，主请求使用真实工具。

                Keep controlled auxiliary summaries and use real tools for main requests.
                """
                if not self.enabled or kwargs["messages"][0]["content"] == SUMMARY_PROMPT:
                    return await super().complete(**kwargs)
                self.requests.append({**kwargs, "messages": copy.deepcopy(kwargs["messages"])})
                self.step += 1
                if self.step == 1:
                    return turn(call("get_context_status", limit=1))
                if self.step == 2:
                    self.status = json.loads(kwargs["messages"][-1]["content"])
                    return turn(call("compact_context"))
                return turn(text="Done")

        model = ContextModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            model.long = True
            await run(app, sid, "Earlier detailed work")
            model.long = False
            model.enabled = True
            model.requests.clear()
            result = await run(app, sid, "Inspect supplied context and compact this conversation")
            assert result.run.status == "completed"
            assert model.status["total_materials"] >= 2
            assert model.status["next_offset"] == 1
            assert len(model.status["materials"]) == 1
            assert "preview" not in model.status["materials"][0]
            assert "preview_complete" not in model.status["materials"][0]
            assert "summary" in model.status["material_forms"]
            assert model.status["last_request"]["manifest"]["message_count"] == len(
                model.requests[0]["messages"]
            )
            view = await app.sessions.contexts.view(sid)
            assert view.checkpoint and view.job.requests == 1
            assert view.job.run_id == result.run.run_id
            assert result.run.requests == 4  # Three main requests plus one summary.
            await run(app, sid, "Continue using saved summary")
            view = await app.sessions.contexts.view(sid)
            assert any(item.kind == "summary" for item in view.last_request.manifest.materials)
            assert "get_context_status" in view.last_request.manifest.tool_names
            assert (
                "no context preflight is required" in model.requests[-1]["messages"][0]["content"]
            )

    asyncio.run(scenario())


def test_auto_memory_starts_after_enable_and_uses_new_material(tmp_path):
    """在独立事件循环中验证场景。

    Run the scenario in an isolated event loop.
    """
    asyncio.run(scenario_auto_memory_starts_after_enable_and_uses_new_material(tmp_path))


def test_knowledge_page_sources_and_project_relocation(tmp_path):
    """派生页失效不挡运行；重新定位保留项目知识身份。

    Derived-page invalidation never blocks runs; relocation preserves project memory identity.
    """

    async def scenario():
        model = KnowledgeModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            await app.sessions.memory.configure(sid, MemorySettings(automatic=False))
            saved = await app.dispatch(
                "memory.save",
                {
                    "session_id": sid,
                    "fields": {"title": "Run", "content": "Use Python standard library"},
                },
            )
            source = saved.entries[0]
            await app.dispatch(
                "memory.maintain",
                {"session_id": sid, "source_ids": [source.memory_id], "title": "Project knowledge"},
            )
            await asyncio.gather(*list(app.sessions.memory.jobs.values()))
            page = await app.sessions.memory.page(sid, MemoryQuery())
            derived = next(item for item in page.entries if item.category == "knowledge_page")
            assert derived.source_ids == [source.memory_id]
            await app.dispatch(
                "memory.save",
                {
                    "session_id": sid,
                    "memory_id": source.memory_id,
                    "fields": {"title": "Run", "content": "Use a different launch command"},
                },
            )
            assert derived.memory_id not in [
                item.memory_id
                for item in (await app.sessions.memory.page(sid, MemoryQuery())).entries
            ]
            full = await app.sessions.memory.page(sid, MemoryQuery(include_disabled=True))
            assert next(item for item in full.entries if item.memory_id == derived.memory_id).stale
            moved = tmp_path / "moved"
            (tmp_path / "project").rename(moved)
            relocated = await app.dispatch(
                "projects.relocate", {"project_id": created.task.project_id, "path": str(moved)}
            )
            assert relocated.active_project.project_id == created.task.project_id
            assert (await app.sessions.memory.page(sid, MemoryQuery())).entries[
                0
            ].memory_id == source.memory_id
            assert (await run(app, sid, "Continue after relocation")).run.status == "completed"

    asyncio.run(scenario())


def test_user_memory_changes_invalidate_other_project_derivatives(tmp_path):
    """全局来源纠错和遗忘传播到其他项目，召回仍按项目隔离。

    Global-source changes reach other projects while retrieval remains project-scoped.
    """

    async def scenario():
        """使用隔离存储核对直接、间接派生与无关条目。

        Check direct and indirect derivatives and unrelated entries in isolated storage.
        """
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            store = app.sessions.memory.store
            a, b = str(uuid4()), str(uuid4())
            source = store.save(a, MemoryFields(title="Global", content="Old", scope="user"))
            fields = MemoryFields(
                title="Derived", content="Old copy", source_ids=[source.memory_id]
            )
            derived = store.save(b, fields, source="maintenance")
            indirect = store.save(
                b,
                MemoryFields(
                    title="Indirect", content="Old detail", source_ids=[derived.memory_id]
                ),
            )
            unrelated = store.save(b, MemoryFields(title="Unrelated", content="Keep"))
            store.save(
                a,
                MemoryFields(title="Global", content="Corrected", scope="user"),
                identity=source.memory_id,
            )
            assert store.read(derived.memory_id, b).stale
            assert store.read(indirect.memory_id, b).stale
            assert not store.read(unrelated.memory_id, b).stale
            assert [item.memory_id for item in store.find(a, MemoryQuery())[0]] == [
                source.memory_id
            ]
            # 模拟来源纠正后的明确重建，再核对遗忘也能跨项目清理。
            # Explicitly rebuild from the correction, then check cross-project forgetting.
            store.save(
                b,
                fields.model_copy(update={"content": "Corrected copy"}),
                identity=derived.memory_id,
                source="maintenance",
                expected_revision=derived.revision,
            )
            store.forget(source.memory_id, a)
            assert not store.path(derived.memory_id).exists()
            assert store.read(indirect.memory_id, b).stale
            assert [item.memory_id for item in store.find(b, MemoryQuery())[0]] == [
                unrelated.memory_id
            ]

    asyncio.run(scenario())


def test_archive_readback_and_missing_material_are_local_feedback(tmp_path):
    """长材料分段读回；缺项只反馈，不停止代码任务。

    Read long archived material in chunks; missing items do not stop code work.
    """

    class Reader(KnowledgeModel):
        """只发一次无效材料读取。

        Issue one missing-material lookup.
        """

        async def complete(self, **kwargs):
            self.requests.append(kwargs)
            if len(self.requests) == 1:
                return turn(call("read_history", artifact_id=str(uuid4())))
            return turn(text="Continue without unavailable old material")

    async def scenario():
        model = Reader()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            content = "中文长材料\n" * 2000
            identity = await app.worker.call(app.sessions.contexts.store.archive, sid, content)
            restored = ""
            offset = 0
            while True:
                page = await app.dispatch(
                    "context.history",
                    {
                        "session_id": sid,
                        "artifact_id": identity,
                        "offset": offset,
                        "max_chars": 1000,
                    },
                )
                restored += page.items[0].text
                if page.items[0].next_offset is None:
                    break
                offset = page.items[0].next_offset
            assert restored == content
            matching = await app.dispatch(
                "context.history",
                {"session_id": sid, "artifact_id": identity, "query": "长材料", "max_chars": 4},
            )
            assert matching.matches == 2000 and matching.items[0].offset == 2
            assert matching.match_unit == "occurrences"
            assert (
                await run(app, sid, "Look up an old artifact if available")
            ).run.status == "completed"
            checkpoint_path = app.sessions.store.path(sid).with_name("context.json")
            checkpoint_path.write_text("broken optional summary", encoding="utf-8")
            assert (await run(app, sid, "Continue from the original log")).run.status == "completed"
            assert checkpoint_path.read_text(encoding="utf-8") == "broken optional summary"

    asyncio.run(scenario())


def test_memory_correction_uses_relevant_entries_and_actual_program_output(tmp_path):
    """纠错读到真实程序结果，相关旧记忆被修订，后续请求不再召回它。

    Correct a relevant old entry from actual program output and omit it from future recall.
    """

    class CorrectionModel(KnowledgeModel):
        """一次真实命令配合可控纠错输出，不模拟存储或工具。

        Pair a real command with controlled correction output, retaining storage and tools.
        """

        step = 0
        extraction = None

        async def complete(self, **kwargs):
            """按实际提取输入定位旧条目并返回停用修订。

            Locate the old entry in the actual extraction input and return a disabled revision.
            """
            self.requests.append({**kwargs, "messages": copy.deepcopy(kwargs["messages"])})
            if kwargs["messages"][0]["content"].startswith("Extract only reusable"):
                payload = json.loads(kwargs["messages"][1]["content"])
                self.extraction = payload
                assert len(payload["existing"]) == 1
                old = payload["existing"][0]
                assert old["title"] == "quartzruntime availability"
                results = [
                    i for i in payload["new_history"]["items"] if i["kind"] == "tool.completed"
                ]
                output = json.loads(results[0]["text"])
                assert output["summary"]["status"] == "exited"
                assert output["summary"]["exit_code"] == 0
                assert "quartzruntime is available" in output["output"][0]["text"]
                fields = MemoryFields(
                    title=old["title"],
                    content="Obsolete runtime claim; use current tools.",
                    enabled=False,
                )
                return turn(text=json.dumps({"entries": [{"fields": fields.model_dump()}]}))
            self.step += 1
            if self.step == 1:
                return turn(
                    call(
                        "run_command",
                        command={
                            "kind": "program",
                            "program": sys.executable,
                            "arguments": ["-c", "print('quartzruntime is available')"],
                        },
                    )
                )
            return turn(text="Current tool output corrects the old quartzruntime claim.")

    async def scenario():
        """使用隔离项目跑完提取和下一请求。

        Exercise extraction and the subsequent request in an isolated project.
        """
        model = CorrectionModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            project_id = created.session.project_id
            service = app.sessions.memory
            await service.configure(sid, MemorySettings(automatic=False, recall_limit=1))
            for index in range(10):
                await app.worker.call(
                    service.store.save,
                    project_id,
                    MemoryFields(title=f"unrelated {index}", content="calendar notebook"),
                )
            old = await app.worker.call(
                service.store.save,
                project_id,
                MemoryFields(
                    title="quartzruntime availability", content="quartzruntime is unavailable"
                ),
                source="maintenance",
            )
            before = len((await app.sessions._load(sid)).facts)
            assert (
                await run(app, sid, "Check quartzruntime and correct its old availability claim.")
            ).run.status == "completed"
            await service.start(sid, after_seq=before)
            await asyncio.gather(*list(service.jobs.values()))
            page = await service.page(
                sid, MemoryQuery(query="quartzruntime", include_disabled=True)
            )
            assert page.state.job.status == "completed", page.state.job.message
            assert len(page.entries) == 1
            assert page.entries[0].memory_id == old.memory_id
            assert page.entries[0].revision == 2 and not page.entries[0].enabled
            await run(app, sid, "Continue with quartzruntime")
            view = await app.sessions.contexts.view(sid)
            assert not any(
                m.source_id == old.memory_id for m in view.last_request.manifest.materials
            )
            assert model.extraction is not None

    asyncio.run(scenario())


def test_memory_followup_recall_and_complete_long_entry_reference(tmp_path):
    """短句接续使用近期用户话题，长知识不会被截成半条规则。

    Recall recent user topics for short follow-ups without injecting truncated rules.
    """

    async def scenario():
        """用真实请求装配核对关联、完整性和跨项目隔离。

        Check relevance, completeness and project isolation through real request assembly.
        """
        model = KnowledgeModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid, pid = created.session.session_id, created.session.project_id
            service = app.sessions.memory
            await service.configure(sid, MemorySettings(automatic=False, recall_chars=500))
            short = service.store.save(
                pid, MemoryFields(title="quartz", content="quartz uses local assets.")
            )
            long = service.store.save(
                pid,
                MemoryFields(
                    title="quartz deployment",
                    content="quartz deployment " * 80 + "ONLY when explicitly publishing.",
                ),
            )
            unrelated = service.store.save(
                str(uuid4()), MemoryFields(title="quartz", content="Other project facts")
            )
            await run(app, sid, "Discuss quartz deployment")
            await run(app, sid, "Continue")
            view = await app.sessions.contexts.view(sid)
            materials = {
                m.source_id: m for m in view.last_request.manifest.materials if m.kind == "memory"
            }
            assert short.memory_id in materials and unrelated.memory_id not in materials
            assert materials[short.memory_id].reason == "任务目标 / 近期用户话题相关 · fact · project"
            assert materials[long.memory_id].form == "reference"
            system = model.requests[-1]["messages"][0]["content"]
            assert "local assets" in system and "read_memory" in system
            assert "quartz deployment quartz deployment" not in system
            assert len(model.requests) == 2  # 召回没有额外模型路由 / No extra routing request.

    asyncio.run(scenario())


def test_memory_search_pinning_and_inactive_replacement(tmp_path):
    """搜索不混入固定项，自动召回优先固定项，失效替代不隐藏有效记忆。

    Keep pinned recall separate from search and ignore inactive superseding entries.
    """

    async def scenario():
        """复用存储验证查询、固定保护和替代状态。

        Use production storage for retrieval, pin protection and supersession.
        """
        async with app_at(tmp_path / "data", KnowledgeModel()) as app:
            created = await create_session(app, tmp_path / "project")
            store = app.sessions.memory.store
            pid = created.session.project_id
            pinned = store.save(
                pid,
                MemoryFields(title="Pinned", content="Use concise comments", pinned=True),
                source="agent",
            )
            old = store.save(
                pid, MemoryFields(title="quartz", content="quartz build steps"), source="agent"
            )
            replacement = store.save(
                pid,
                MemoryFields(
                    title="New quartz",
                    content="quartz alternate",
                    supersedes=[old.memory_id],
                    stale=True,
                ),
            )
            found, _ = store.find(pid, MemoryQuery(query="quartz"))
            assert [v.memory_id for v in found] == [old.memory_id]
            recalled, _ = store.find(pid, MemoryQuery(query="quartz"), include_pinned=True)
            assert [v.memory_id for v in recalled] == [pinned.memory_id, old.memory_id]
            with pytest.raises(AgentError) as protected:
                store.save(
                    pid,
                    MemoryFields(title="Changed", content="wrong"),
                    identity=pinned.memory_id,
                    source="maintenance",
                    expected_revision=pinned.revision,
                )
            assert protected.value.code == "MEMORY_EDITED"
            fields = MemoryFields.model_validate(
                replacement.model_dump(include=set(MemoryFields.model_fields))
            )
            fields.stale = False
            store.save(pid, fields, identity=replacement.memory_id)
            found, _ = store.find(pid, MemoryQuery(query="quartz"))
            assert [v.memory_id for v in found] == [replacement.memory_id]

    asyncio.run(scenario())


def test_old_lookup_outputs_retire_without_changing_current_chain_or_history(tmp_path):
    """新结果完整，按需减量后持续生效；检索不重复命中回查副本。

    Keep fresh output intact, persist on-demand reductions and avoid search echo matches.
    """

    class LookupModel(KnowledgeModel):
        """通过生产历史工具回查一次，保留请求快照。

        Perform one production history lookup and capture request snapshots.
        """

        async def complete(self, **kwargs):
            """仅发起一次查找，后续直接完成。

            Look up once, then complete subsequent requests.
            """
            self.requests.append({**kwargs, "messages": copy.deepcopy(kwargs["messages"])})
            if len(self.requests) == 1:
                return turn(call("read_history", query="needle-unique", max_chars=12000, limit=1))
            return turn(text="Read complete.")

    async def scenario():
        """验证真实归档、后续输入和可覆盖的预览参数。

        Check durable history, later input and configurable preview length.
        """
        model = LookupModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            prompt = "needle-unique " * 600
            await run(app, sid, prompt)
            current_result = next(m for m in model.requests[-1]["messages"] if m["role"] == "tool")
            assert prompt in current_result["content"]
            source = await app.dispatch(
                "context.history", {"session_id": sid, "query": "needle-unique"}
            )
            copies = await app.dispatch(
                "context.history",
                {
                    "session_id": sid,
                    "query": "needle-unique",
                    "include_lookup_results": True,
                },
            )
            assert source.matches == 1 and copies.matches > source.matches
            original = app.sessions.store.path(sid).read_bytes()
            await run(app, sid, "Next question")
            unchanged = next(m for m in model.requests[-1]["messages"] if m["role"] == "tool")
            assert unchanged == current_result
            log = await app.sessions._load(sid)
            previews = trim_candidates(log, None, [], 1000)
            before = estimate_tokens(assemble(log, None, []))
            after = estimate_tokens([m for _, m in projected_records(log, previews)])
            await app.sessions.contexts.configure(
                sid, ContextSettings(auto_trigger_tokens=(before + after) // 2)
            )
            from my_agent.runtime.settings import RunLimits

            await app.sessions.contexts._start(
                log, RunLimits.model_validate(DEFAULTS["run"]), None, None, automatic=True
            )
            await app.sessions.contexts.wait(sid)
            reduced = await app.sessions.contexts.view(sid)
            assert reduced.job.outcome == "trimmed" and reduced.job.requests == 0
            await run(app, sid, "Reduce only consumed output")
            later_result = next(m for m in model.requests[-1]["messages"] if m["role"] == "tool")
            assert len(later_result["content"]) < len(current_result["content"]) / 2
            assert "read_history(entry_seq=" in later_result["content"]
            assert app.sessions.store.path(sid).read_bytes().startswith(original)
            manifest = (await app.sessions.contexts.view(sid)).last_request.manifest
            reference = next(m for m in manifest.materials if m.form == "fragment")
            restored = await app.dispatch(
                "context.history",
                {
                    "session_id": sid,
                    **reference.read_arguments,
                    "max_chars": 12000,
                },
            )
            assert prompt in restored.items[0].text
            await app.sessions.contexts.configure(
                sid, ContextSettings(tool_result_preview_tokens=20000)
            )
            await run(app, sid, "Keep larger previews")
            larger_result = next(m for m in model.requests[-1]["messages"] if m["role"] == "tool")
            assert larger_result == later_result
            app.sessions.last_log = None
            state = app.sessions.contexts.store.read(sid)
            assert state.previews and state.previews[0].tokens == 1000
            await run(app, sid, "Restart-style restored projection")
            assert (
                next(m for m in model.requests[-1]["messages"] if m["role"] == "tool")
                == later_result
            )

    asyncio.run(scenario())


def test_larger_summary_keeps_previous_window_without_stopping_run(tmp_path):
    """反向膨胀的摘要不采用、不报执行失败，费用保留。

    Retain the previous window for a larger summary without failing the run or hiding cost.
    """

    class ExpandingModel(KnowledgeModel):
        """只在摘要请求返回过长正文。

        Return an oversized body only for summary requests.
        """

        async def complete(self, **kwargs):
            """普通回答维持短内容，摘要故意扩写。

            Keep ordinary answers short and deliberately expand summaries.
            """
            if kwargs["messages"][0]["content"] == SUMMARY_PROMPT:
                self.requests.append(kwargs)
                return turn(text="Verbose recap " * 1000)
            return await super().complete(**kwargs)

    async def scenario():
        """对比同一快照并继续正常提问。

        Compare the same snapshot and continue ordinary conversation.
        """
        model = ExpandingModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            for i in range(3):
                await run(app, sid, f"Short task {i}")
            await app.sessions.contexts.start(sid)
            await app.sessions.contexts.wait(sid)
            view = await app.sessions.contexts.view(sid)
            assert view.checkpoint is None and view.job.compression_applied is False
            assert view.job.history_before_bytes == view.job.history_after_bytes
            assert view.job.requests == 1 and view.totals.requests == 1
            await app.sessions.contexts.configure(sid, ContextSettings())
            assert (await run(app, sid, "Continue normally")).run.status == "completed"
            assert (await app.sessions.contexts.view(sid)).job.status == "ready"
            assert (
                len([r for r in model.requests if r["messages"][0]["content"] == SUMMARY_PROMPT])
                == 1
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("with_trim", [False, True])
def test_no_gain_prefix_skips_tail_only_growth_but_allows_manual_retry(tmp_path, with_trim):
    """尾部增长不重复总结旧前缀；手动、预算变化和新切点仍可整理。

    Tail-only growth skips redundant summaries; manual retries, limits and new cuts still work.
    """

    class Model(KnowledgeModel):
        """只让摘要膨胀，普通回答控制尾部边界。

        Expand summaries while controlling the ordinary tail boundary.
        """

        async def complete(self, **kwargs):
            """返回可识别的长尾部或无收益摘要。

            Return an identifiable long tail or unhelpful summary.
            """
            self.requests.append(kwargs)
            if kwargs["messages"][0]["content"] == SUMMARY_PROMPT:
                return turn(text="Verbose recap " * 5000)
            if with_trim and kwargs["messages"][-1].get("content") == "Old task":
                return turn(call("read_file", path="old.log"))
            return turn(text="tail " * 3000 if self.long else "done")

    async def scenario():
        """经生产作业比较请求数，不把跳过当失败。

        Compare production job request counts without treating a skip as failure.
        """
        from my_agent.runtime.settings import RunLimits

        model = Model()
        async with app_at(tmp_path / "data", model) as app:
            sid = (await create_session(app, tmp_path / "project")).session.session_id
            contexts = app.sessions.contexts
            (tmp_path / "project" / "old.log").write_text("old log " * 2000, encoding="utf-8")
            policy = ContextSettings(
                automatic=False, auto_trigger_tokens=1, keep_recent_tokens=1000
            )
            await contexts.configure(sid, policy)
            await run(app, sid, "Old task")
            model.long = True
            await run(app, sid, "Tail begins")
            limits = RunLimits.model_validate(DEFAULTS["run"])

            async def compact(output=8192):
                """固定实际切点路径，使用测试显式预算。

                Exercise the real cut selection with an explicit test budget.
                """
                await contexts._start(
                    await app.sessions._load(sid),
                    limits.model_copy(update={"max_output_tokens": output}),
                    None,
                    None,
                    automatic=True,
                )
                await contexts.wait(sid)
                return (await contexts.view(sid)).job

            first = await compact()
            assert first.outcome == ("trimmed" if with_trim else "not_smaller")
            assert first.requests == 1 and first.compression_applied is False
            model.long = False
            await run(app, sid, "A short extra question")
            skipped = await compact()
            assert skipped.requests == 0 and skipped.status == "ready"
            assert (await compact(4096)).requests == 1
            assert (await compact(4096)).requests == 0
            await contexts.start(sid)
            await contexts.wait(sid)
            assert (await contexts.view(sid)).job.requests == 1
            model.long = True
            await run(app, sid, "A new large tail moves the cut")
            assert (await compact()).requests == 1

    asyncio.run(scenario())


def test_history_hit_offsets_and_run_scoped_tool_links(tmp_path):
    """中部命中精确续读，同名 / 同 ID 跨运行不串联。

    Read middle hits precisely and never cross-link repeated call IDs between runs.
    """

    class Reader(KnowledgeModel):
        """重复调用 ID 的合法跨运行样本。

        A legal repeated call ID across separate runs.
        """

        async def complete(self, **kwargs):
            """每次读取当前项目文件，随后结束。

            Read a project file once per run, then finish.
            """
            if kwargs["messages"][-1]["role"] == "user":
                return turn(
                    call("read_file", path="notes.txt").model_copy(
                        update={"tool_call_id": "same-call-id"}
                    )
                )
            return turn(text="Finished")

    async def scenario():
        """验证 RPC 片段、分页和关联均来自原事件。

        Check RPC fragments, paging and links against original facts.
        """
        async with app_at(tmp_path / "data", Reader()) as app:
            sid = (await create_session(app, tmp_path / "project")).session.session_id
            text = "\u0130\U0001f642 prefix " * 100 + "Middle-Needle " + "rest " * 50
            (tmp_path / "project" / "notes.txt").write_text(text, encoding="utf-8")
            for index in range(2):
                await run(app, sid, f"Read sample {index}")
            result = await app.dispatch(
                "context.history",
                {
                    "session_id": sid,
                    "query": "middle-needle",
                    "max_chars": 30,
                },
            )
            assert result.matches == 2 and result.match_unit == "records"
            first = result.items[0]
            next_page = await app.dispatch(
                "context.history",
                {
                    "session_id": sid,
                    "query": "middle-needle",
                    "max_chars": 30,
                    "after_seq": result.next_after_seq,
                },
            )
            second = next_page.items[0]
            assert first.text.startswith("Middle-Needle") and first.offset > 100
            assert first.tool_name == "read_file" and first.result_seq == first.seq
            assert first.call_seq < first.seq < second.call_seq < second.seq
            assert first.tool_call_id == second.tool_call_id == "same-call-id"
            full = await app.dispatch(
                "context.history",
                {
                    "session_id": sid,
                    "entry_seq": first.seq,
                },
            )
            original = full.items[0].text
            assert original[first.offset : first.next_offset] == first.text
            continued = await app.dispatch(
                "context.history",
                {
                    "session_id": sid,
                    "entry_seq": first.seq,
                    "offset": first.next_offset,
                },
            )
            assert first.text + continued.items[0].text == original[first.offset :]
            linked = await app.dispatch(
                "context.history",
                {
                    "session_id": sid,
                    "entry_seq": first.call_seq,
                },
            )
            assert linked.items[0].result_seq == first.seq
            bounded = await app.dispatch(
                "context.history",
                {
                    "session_id": sid,
                    "entry_seq": first.call_seq,
                    "through_seq": first.call_seq,
                },
            )
            assert bounded.items[0].result_seq is None

    asyncio.run(scenario())


def test_summary_capacity_uses_effective_output_limit(tmp_path, monkeypatch):
    """较小摘要输出额度释放真实输入空间，避免无谓分批。

    A smaller summary output allowance releases input capacity and avoids needless batches.
    """

    async def scenario():
        """同一请求使用统一预算进行装箱和发送。

        Pack and send a summary using the same effective allowance.
        """
        model = KnowledgeModel()
        model.long = True
        async with app_at(tmp_path / "data", model) as app:
            sid = (await create_session(app, tmp_path / "project")).session.session_id
            for i in range(3):
                await run(app, sid, f"Inspect {i}")
            contexts = app.sessions.contexts
            await contexts.configure(sid, ContextSettings(summary_output_tokens=1024))
            monkeypatch.setitem(DEFAULTS["context_windows"]["models"], "glm-5.3-flash", 20000)
            await contexts.start(sid)
            await contexts.wait(sid)
            requests = [r for r in model.requests if r["messages"][0]["content"] == SUMMARY_PROMPT]
            assert len(requests) == 1 and requests[0]["limits"].max_output_tokens == 1024
            assert estimate_tokens([requests[0]["messages"], []]) > 20000 - 8192

    asyncio.run(scenario())


def test_work_status_pages_without_duplicating_or_omitting_references(tmp_path):
    """证据索引默认分页，显式续页遍历原引用且不重复。

    Page evidence by default and traverse original references without duplication.
    """

    class IndexModel(KnowledgeModel):
        """在准备好历史后，用真实工具读取两页。

        Read two pages through the real tool after preparing history.
        """

        lookup = False
        pages = []

        async def complete(self, **kwargs):
            """复制返回游标续读，不猜事件序号。

            Continue with the returned cursor instead of guessed sequence numbers.
            """
            if not self.lookup:
                return await super().complete(**kwargs)
            last = kwargs["messages"][-1]
            if last["role"] != "tool":
                return turn(call("read_work_status"))
            page = json.loads(last["content"])
            self.pages.append(page)
            if len(self.pages) == 1:
                return turn(call("read_work_status", before_seq=page["before_seq"]))
            return turn(text="Index inspected.")

    async def scenario():
        """造少量短历史，索引无需填满工具输出预算。

        Build short history without filling the tool-output budget.
        """
        model = IndexModel()
        async with app_at(tmp_path / "data", model) as app:
            created = await create_session(app, tmp_path / "project")
            sid = created.session.session_id
            for i in range(12):
                await run(app, sid, f"Small task {i}")
            model.lookup = True
            await run(app, sid, "Inspect references")
            first, second = model.pages
            assert len(first["evidence"]) == 20 and first["before_seq"] is not None
            assert second["evidence"] and second["before_seq"] is None
            assert not {e["seq"] for e in first["evidence"]} & {
                e["seq"] for e in second["evidence"]
            }
            assert len(first["evidence"]) + len(second["evidence"]) == 25

    asyncio.run(scenario())
