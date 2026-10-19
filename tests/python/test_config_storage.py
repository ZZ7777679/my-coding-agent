"""配置、凭据与项目存储的隔离行为用例，覆盖失败时保留数据。

Isolated config, credential and project-storage cases, including preservation on failure.
"""

import json
import sys

import pytest
from typer.testing import CliRunner

from my_agent.cli import app
from my_agent.config import load_config, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.errors import AgentError, http_error_code
from my_agent.projects import ProjectService
from my_agent.storage import Storage, atomic_write

runner = CliRunner()


def test_legacy_go_endpoint_is_adopted_without_rewriting_on_read(tmp_path):
    """兼容旧 Go 配置并保留模型、预算；只在显式保存时写回新地址。

    Migrate legacy Go settings in memory, preserving model/budget until an explicit save.
    """
    from my_agent.models.endpoints import GO_BASE_URL, GO_MESSAGES_URL, messages_url

    root = tmp_path / "data"
    root.mkdir()
    config_file = root / "config.toml"
    previous = (
        '[model]\nbase_url="https://opencode.ai/zen/go/v1"\n'
        'model_id="deepseek-v4.1-flash"\n[run]\nmax_requests=37\n'
    )
    config_file.write_text(previous, encoding="utf-8")
    location = resolve_data_dir(str(root))
    config = load_config(location)
    assert config.model.base_url == GO_BASE_URL
    assert config.run.max_requests == 37
    assert config_file.read_text(encoding="utf-8") == previous
    assert messages_url(config.model.base_url) == GO_MESSAGES_URL
    assert messages_url("https://api.deepseek.com") == "https://api.deepseek.com/messages"
    storage = Storage(location)
    with storage.writer():
        storage.save_model("deepseek-v4.1-flash")
    assert GO_BASE_URL in config_file.read_text(encoding="utf-8")
    assert load_config(location).run.max_requests == 37


def test_config_priority_and_redaction(tmp_path):
    """验证参数优先级、模型覆盖，以及非法配置错误不会泄露输入。

    Verify option priority, model overrides and redaction of invalid configuration input.
    """

    default_root = tmp_path / "data"
    default_root.mkdir()
    (default_root / "config.toml").write_text(
        '[model]\nmodel_id="deepseek-v4.1-flash"\n', encoding="utf-8"
    )
    location = resolve_data_dir(str(default_root), {"MY_AGENT_DATA_DIR": str(tmp_path / "other")})
    assert location.source == "cli"
    assert load_config(location).model.model_id == "deepseek-v4.1-flash"
    assert load_config(location, "glm-5.3-flash").model_source == "cli"
    sentinel = "test-only-secret-sentinel"
    (default_root / "config.toml").write_text(
        '[model]\napi_key="' + sentinel + '"', encoding="utf-8"
    )
    result = runner.invoke(app, ["--data-dir", str(default_root), "config", "show", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "CONFIG_INVALID"
    assert sentinel not in result.output


def test_allowed_models_accept_reordering_but_reject_changed_membership(tmp_path):
    """白名单顺序可调整并保存，但缺项、重复或新增模型仍拒绝。

    Allow reordered models to persist, but reject omissions, duplicates and new models.
    """
    root = tmp_path / "data"
    root.mkdir()
    config_file = root / "config.toml"
    models = ["deepseek-v4.1-flash", "glm-5.3-flash"]
    config_file.write_text("[model]\nallowed_models=" + json.dumps(models), encoding="utf-8")
    location = resolve_data_dir(str(root))
    assert load_config(location).model.allowed_models == models
    assert load_config(location).model.model_id == "glm-5.3-flash"
    storage = Storage(location)
    with storage.writer():
        storage.save_model("deepseek-v4.1-flash")
    assert load_config(location).model.allowed_models == models

    for invalid in (
        [models[0]],
        [models[0], models[0]],
        [*models, models[0]],
        [models[0], "other"],
    ):
        content = "[model]\nallowed_models=" + json.dumps(invalid)
        config_file.write_text(content, encoding="utf-8")
        with pytest.raises(AgentError) as error:
            load_config(location)
        assert error.value.code == "CONFIG_INVALID"
        assert config_file.read_text(encoding="utf-8") == content


def test_data_root_no_fallback(tmp_path, monkeypatch):
    """验证目录来源与非法输入；用替身模拟 E 盘，不依赖真实磁盘状态。

    Verify path sources and invalid input, simulating E-drive availability without real changes.
    """

    assert resolve_data_dir(None, {"MY_AGENT_DATA_DIR": str(tmp_path)}).source == "environment"
    for invalid in ("", ".", "relative/path"):
        with pytest.raises(AgentError, match="绝对路径"):
            resolve_data_dir(invalid, {})
    if sys.platform == "win32":
        from pathlib import Path

        original = Path.is_dir
        with monkeypatch.context() as patch:
            patch.setattr(Path, "is_dir", lambda p: True if str(p) == "E:\\" else original(p))
            assert str(resolve_data_dir(None, {}).root) == r"E:\MyCodingAgentData"
        with monkeypatch.context() as patch:
            patch.setattr(Path, "is_dir", lambda p: False if str(p) == "E:\\" else original(p))
            with pytest.raises(AgentError) as error:
                resolve_data_dir(None, {})
            assert error.value.code == "DATA_DIR_UNAVAILABLE"


def test_credential_sources_and_restriction():
    """区分进程、用户、缺失和受限来源，并验证秘密的字符串表示已保护。

    Distinguish process, user, absent and restricted sources and check protected secret repr.
    """

    def restricted(_):
        """模拟用户环境读取受限，不读取真实注册表。

        Simulate restricted user-environment access without reading the real registry.
        """

        raise PermissionError("not public")

    process = resolve_credential({"OPENCODE_API_KEY": "sentinel"}, restricted, "win32")
    assert process.info.source == "process"
    assert "sentinel" not in repr(process)
    user = resolve_credential({}, lambda _: "other-sentinel", "win32")
    assert user.info.source == "windows_user"
    assert resolve_credential({}, restricted, "win32").info.present is None
    assert resolve_credential({}, lambda _: None, "win32").info.present is False


def test_open_restart_duplicate_and_invalid_preserves_selection(tmp_path):
    """验证打开、重复选择和重启恢复，失败后仍保留原索引。

    Verify opening, deduplication and restart recovery, preserving the index after failure.
    """

    root = tmp_path / "data"
    project = tmp_path / "项目 with spaces"
    project.mkdir()
    storage = Storage(resolve_data_dir(str(root)))
    with storage.writer():
        service = ProjectService(storage)
        first = service.open(path=str(project))
        repeated = service.open(path=str(project / "."))
        assert first.active_project.project_id == repeated.active_project.project_id
        assert len(repeated.recent_projects) == 1
        baseline = (root / "projects.json").read_bytes()
        for invalid in (tmp_path / "missing", root, tmp_path):
            with pytest.raises(AgentError):
                service.open(path=str(invalid))
            assert (root / "projects.json").read_bytes() == baseline
    restored = ProjectService(Storage(resolve_data_dir(str(root)))).view()
    assert restored.active_project.project_id == first.active_project.project_id
    project.rmdir()
    unavailable = ProjectService(Storage(resolve_data_dir(str(root)))).view()
    assert not unavailable.active_project.available
    assert unavailable.active_project.project_id == first.active_project.project_id


def test_atomic_failure_and_corruption_keep_existing_records(tmp_path, monkeypatch):
    """模拟替换失败与记录损坏，确认已有文件未被覆盖。

    Simulate replacement failure and corruption, ensuring existing files are not overwritten.
    """

    root = tmp_path / "data"
    project = tmp_path / "project"
    project.mkdir()
    storage = Storage(resolve_data_dir(str(root)))
    with storage.writer():
        ProjectService(storage).open(path=str(project))
    baseline = (root / "projects.json").read_bytes()

    def fail_replace(*args):
        """在原子替换处注入失败，验证旧文件保护路径。

        Inject failure at atomic replacement to exercise old-file protection.
        """

        raise PermissionError("simulated")

    with monkeypatch.context() as patch:
        patch.setattr("my_agent.storage.os.replace", fail_replace)
        with pytest.raises(AgentError):
            atomic_write(root / "projects.json", "{}")
    assert (root / "projects.json").read_bytes() == baseline
    assert not list(root.glob("*.tmp"))
    (root / "projects.json").write_bytes(b"{broken")
    with storage.writer(), pytest.raises(AgentError):
        ProjectService(storage).initialize()
    assert (root / "projects.json").read_bytes() == b"{broken"


def test_single_writer_and_future_version(tmp_path):
    """验证写入锁互斥与未来数据版本保护。

    Verify exclusive writers and protection of future-version data.
    """

    location = resolve_data_dir(str(tmp_path / "data"))
    first, second = Storage(location), Storage(location)
    with first.writer():
        with pytest.raises(AgentError) as error, second.writer():
            raise AssertionError("second writer must not enter")
        assert error.value.code == "DATA_DIR_BUSY"
    with second.writer():
        second.initialize()
    metadata = second.metadata_path.read_text(encoding="utf-8")
    second.metadata_path.write_text(
        metadata.replace('"schema_version": 1', '"schema_version": 2'), encoding="utf-8"
    )
    preserved = second.metadata_path.read_bytes()
    with pytest.raises(AgentError) as error, second.writer():
        raise AssertionError("unsupported version must not initialize")
    assert error.value.code == "DATA_VERSION_UNSUPPORTED"
    assert second.metadata_path.read_bytes() == preserved


def test_saved_model_survives_restart_and_preserves_other_settings(tmp_path):
    """验证模型保存要求持锁、重启可读且不改其他配置。

    Verify locked model updates survive restart without changing other settings.
    """

    location = resolve_data_dir(str(tmp_path / "data"))
    storage = Storage(location)
    with pytest.raises(AgentError) as error:
        storage.save_model("deepseek-v4.1-flash")
    assert error.value.code == "WRITER_REQUIRED"
    with storage.writer():
        storage.initialize()
        before = load_config(location).model.model_dump()
        storage.save_model("deepseek-v4.1-flash")
    restored = load_config(location)
    assert restored.model.model_dump() == {**before, "model_id": "deepseek-v4.1-flash"}
    assert restored.model_source == "user"
    result = runner.invoke(app, ["--data-dir", str(storage.root), "config", "show", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["model_id"] == "deepseek-v4.1-flash"


def test_model_write_failure_and_later_corruption_preserve_file(tmp_path, monkeypatch):
    """验证模型写入失败或配置损坏时保留文件与失败原因。

    Verify model-write failure or corrupted configuration preserves the file and error.
    """

    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    with storage.writer():
        storage.initialize()
        config = storage.root / "config.toml"
        baseline = config.read_bytes()

        def denied(*args):
            """模拟权限错误，阻止真实原子替换。

            Simulate a permission error instead of performing the atomic replacement.
            """

            raise PermissionError("simulated write failure")

        with monkeypatch.context() as patch:
            patch.setattr("my_agent.storage.os.replace", denied)
            with pytest.raises(AgentError) as error:
                storage.save_model("deepseek-v4.1-flash")
            assert error.value.code == "DATA_DIR_NOT_WRITABLE"
        assert config.read_bytes() == baseline
        assert not list(storage.root.glob("*.tmp"))
        config.write_text("invalid=", encoding="utf-8")
        with pytest.raises(AgentError) as error:
            storage.save_model("deepseek-v4.1-flash")
        assert error.value.code == "CONFIG_INVALID"
        assert config.read_text(encoding="utf-8") == "invalid="


def test_junction_identity_and_overlap(tmp_path):
    """在隔离目录验证 junction 去重与数据边界，其他平台不创建 Windows 链接。

    Check isolated Windows junction identity and overlap without creating links elsewhere.
    """

    if sys.platform != "win32":
        return
    import _winapi

    project, link = tmp_path / "project", tmp_path / "junction"
    project.mkdir()
    _winapi.CreateJunction(str(project), str(link))
    storage = Storage(resolve_data_dir(str(tmp_path / "data")))
    with storage.writer():
        service = ProjectService(storage)
        first = service.open(path=str(project))
        alias = service.open(path=str(link))
        assert first.active_project.project_id == alias.active_project.project_id
        data_alias = tmp_path / "data-link"
        _winapi.CreateJunction(str(storage.root), str(data_alias))
        with pytest.raises(AgentError) as error:
            service.open(path=str(data_alias))
        assert error.value.code == "PROJECT_DATA_OVERLAP"


@pytest.mark.parametrize(
    "status,kind,expected",
    [
        (401, None, "AUTHENTICATION_FAILED"),
        (403, None, "ACCESS_DENIED"),
        (429, None, "SERVICE_RESTRICTED"),
        (429, "insufficient_quota", "QUOTA_EXCEEDED"),
        (429, "rate_limit_exceeded", "RATE_LIMITED"),
        (503, None, "SERVICE_ERROR"),
    ],
)
def test_http_failure_categories(status, kind, expected):
    """确认不同 HTTP 失败保留各自错误分类。

    Confirm distinct HTTP failures retain their intended categories.
    """

    assert http_error_code(status, kind) == expected
