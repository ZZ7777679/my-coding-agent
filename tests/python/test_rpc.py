"""验证实际 stdio 服务与恢复路径，数据和凭据使用隔离样本。

Check the real stdio service and recovery paths using isolated data and sentinel keys.
"""

import json
import subprocess
import sys
from io import BytesIO

from my_agent.config import MAX_FRAME_BYTES, resolve_data_dir
from my_agent.credentials import resolve_credential
from my_agent.diagnostics import diagnose
from my_agent.models.connections import ConnectionObservation
from my_agent.models.types import ModelProgress
from my_agent.processes import probe_environment
from my_agent.rpc.server import serve
from my_agent.storage import Storage


def frame(method, params, request_id="r1"):
    """构造带关联标识的一条 UTF-8 JSONL 测试请求。

    Build one UTF-8 JSONL test request with a correlation ID.
    """

    return (
        json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def initialize():
    """生成当前协议的最小有效初始化请求。

    Build a minimal valid initialization request for the current protocol.
    """

    return frame(
        "initialize",
        {
            "app_version": "0.0.0",
            "protocol_version": 3,
            "data_schema_version": 1,
        },
    )


def run_server(root, payload, *, bootstrap=False):
    """启动真实后端并发送测试帧，检查退出及哨兵凭据未泄露。

    Run the real backend with test frames, checking exit and sentinel-key redaction.
    """

    args = [sys.executable, "-m", "my_agent", "--data-dir", str(root), "serve"]
    env = probe_environment()
    env["OPENCODE_API_KEY"] = "rpc-test-only-sentinel"
    if bootstrap:
        args.append("--parent-credential")
        payload = b'{"key":"private-bootstrap-sentinel"}\n' + payload
    process = subprocess.run(args, input=payload, capture_output=True, env=env, timeout=8)
    assert process.returncode == 0, process.stderr.decode("utf-8", errors="replace")
    assert b"rpc-test-only-sentinel" not in process.stdout + process.stderr
    assert b"private-bootstrap-sentinel" not in process.stdout + process.stderr
    return [json.loads(line) for line in process.stdout.splitlines()]


def test_real_stdio_open_list_shutdown(tmp_path):
    """通过真实进程验证握手、项目打开、查询和关闭后释放锁。

    Verify handshake, project open/list and lock release through a real process.
    """

    root, project = tmp_path / "data", tmp_path / "中文 project"
    project.mkdir()
    replies = run_server(
        root,
        initialize()
        + frame("projects.open", {"path": str(project)}, "r2")
        + frame("projects.list", {}, "r3")
        + frame("shutdown", {}, "r4"),
        bootstrap=True,
    )
    assert [reply["id"] for reply in replies] == ["r1", "r2", "r3", "r4"]
    assert replies[0]["result"]["config"]["credential"]["source"] == "process"
    assert replies[1]["result"] == replies[2]["result"]
    assert replies[2]["result"]["active_project"]["name"] == "中文 project"
    assert replies[3]["result"] is None
    with Storage(resolve_data_dir(str(root))).writer():
        pass


def test_eof_releases_writer_and_protocol_mismatch_does_not_initialize(tmp_path):
    """确认 EOF 释放锁，版本不兼容时不创建业务数据。

    Confirm EOF releases the lock and version mismatch creates no business data.
    """

    root = tmp_path / "data"
    replies = run_server(root, initialize())
    assert "result" in replies[0]
    with Storage(resolve_data_dir(str(root))).writer():
        pass
    other = tmp_path / "unused"
    replies = run_server(
        other,
        frame(
            "initialize",
            {
                "app_version": "0.0.0",
                "protocol_version": 1,
                "data_schema_version": 1,
            },
        ),
    )
    assert replies[0]["error"]["data"]["code"] == "PROTOCOL_MISMATCH"
    assert not other.exists()


def test_bad_frames_and_invalid_methods_are_bounded(tmp_path):
    """确认坏编码、超限帧、未知方法与参数错误被分别识别。

    Check distinct handling of bad encoding, oversized frames, unknown methods and parameters.
    """

    raw = b"\xff\n" + b"x" * (MAX_FRAME_BYTES + 50) + b"\n"
    replies = run_server(
        tmp_path / "data",
        raw
        + initialize()
        + frame("unknown", {}, "r2")
        + frame("projects.open", {"path": "x", "project_id": "y"}, "r3"),
    )
    assert replies[0]["error"]["code"] == -32700
    assert replies[1]["error"]["data"]["code"] == "FRAME_TOO_LARGE"
    assert "result" in replies[2]
    assert replies[3]["error"]["code"] == -32601
    assert replies[4]["error"]["code"] == -32602


def test_notification_has_no_response(tmp_path):
    """确认通知不产生回复，后续正常请求仍可处理。

    Confirm notifications produce no response and subsequent requests still work.
    """

    notification = b'{"jsonrpc":"2.0","method":"unknown","params":{}}\n'
    replies = run_server(tmp_path / "data", notification + initialize())
    assert len(replies) == 1
    assert replies[0]["id"] == "r1"


def test_config_update_validation_and_restart(tmp_path):
    """验证模型保存边界与真实服务重启后读取的一致性。

    Verify model-update boundaries and consistency after restarting the real service.
    """

    root = tmp_path / "data"
    replies = run_server(
        root,
        initialize()
        + frame("config.update", {"model_id": "other-model"}, "invalid-model")
        + frame("config.update", {"model_id": "glm-5.3-flash", "key": "secret"}, "extra")
        + frame("config.get", {}, "before")
        + frame("config.update", {"model_id": "deepseek-v4.1-flash"}, "save")
        + frame("config.get", {}, "after"),
    )
    assert replies[1]["error"]["code"] == -32602
    assert replies[2]["error"]["code"] == -32602
    assert replies[3]["result"]["model_id"] == "glm-5.3-flash"
    assert replies[4]["result"] == replies[5]["result"]
    assert replies[4]["result"]["model_id"] == "deepseek-v4.1-flash"
    restarted = run_server(root, initialize())
    assert restarted[0]["result"]["config"] == replies[4]["result"]


def test_failed_initialize_keeps_read_only_diagnostics_available(tmp_path):
    """确认配置损坏时诊断仍可用，写操作拒绝且原文件保留。

    Confirm diagnostics survive invalid config while writes fail and the original file remains.
    """

    root = tmp_path / "data"
    root.mkdir()
    config = root / "config.toml"
    config.write_text("invalid=", encoding="utf-8")
    replies = run_server(
        root,
        initialize()
        + frame("diagnostics.get", {"dev": False, "network": False, "write_probe": False}, "d")
        + frame("config.update", {"model_id": "glm-5.3-flash"}, "blocked"),
    )
    by_id = {reply["id"]: reply for reply in replies}
    assert by_id["r1"]["error"]["data"]["code"] == "CONFIG_INVALID"
    report = by_id["d"]["result"]
    assert any(check["code"] == "CONFIG_INVALID" for check in report["checks"])
    assert report["authentication_verified"] == "not_checked"
    assert by_id["blocked"]["error"]["data"]["code"] == "NOT_INITIALIZED"
    assert config.read_text(encoding="utf-8") == "invalid="
    assert sorted(file.name for file in root.iterdir()) == ["config.toml"]


def test_diagnostic_flags_are_explicit_and_credential_refresh_is_public(tmp_path, monkeypatch):
    """检查诊断选项显式传递与凭据元信息刷新，不输出秘密。

    Check explicit diagnostic options and refreshed credential metadata without exposing secrets.
    """

    location = resolve_data_dir(str(tmp_path / "data"))
    calls = []
    probes = []
    report = diagnose(str(location.root))

    def fake_diagnose(**kwargs):
        """捕获诊断选项并返回受控报告，不执行额外探测。

        Capture diagnostic flags and return a controlled report without extra probes.
        """

        calls.append((kwargs["dev"], kwargs["network"], kwargs["write_probe"]))
        return report

    monkeypatch.setattr("my_agent.rpc.application.diagnose", fake_diagnose)

    async def fake_probe(pool, timeout):
        """M1 连接探测已独立；替换真实网络并核对显式调用。

        Stub the separate M1 pool probe and verify explicit calls without networking.
        """
        probes.append(timeout)
        pool.last_probe = ConnectionObservation(
            finished_at="2026-09-17T00:00:00Z",
            code="OK",
            http_status=200,
            models_confirmed=True,
            progress=ModelProgress(phase="completed", elapsed_ms=1.0),
        )

    monkeypatch.setattr("my_agent.rpc.application.probe_connection", fake_probe)
    monkeypatch.setattr("my_agent.credentials.read_windows_user", lambda _: "user-sentinel")
    credential = resolve_credential({}, lambda _: None, "win32")
    writer = BytesIO()
    serve(
        location,
        BytesIO(
            initialize()
            + frame("diagnostics.get", {"dev": True, "network": True, "write_probe": True}, "d")
            + frame("config.get", {}, "refresh")
            + frame(
                "diagnostics.get",
                {"dev": "false", "network": False, "write_probe": False},
                "invalid",
            )
        ),
        writer,
        credential,
    )
    replies = [json.loads(line) for line in writer.getvalue().splitlines()]
    by_id = {reply["id"]: reply for reply in replies}
    assert calls == [(True, False, True)]
    assert len(probes) == 1
    assert by_id["d"]["result"]["catalog_reachable"] == "ok"
    assert by_id["refresh"]["result"]["credential"] == {
        "env_var": "OPENCODE_API_KEY",
        "source": "windows_user" if sys.platform == "win32" else "none",
        "present": sys.platform == "win32",
    }
    assert by_id["invalid"]["error"]["code"] == -32602
    assert b"user-sentinel" not in writer.getvalue()
