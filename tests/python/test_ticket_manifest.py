"""实验来源指纹和阶段快照边界。 Experiment fingerprints and snapshot boundaries."""

import json

from tests.models import ticket_manifest


def test_manifest_tracks_dirty_source_without_raw_patch_or_private_inputs(tmp_path, monkeypatch):
    """源码变化可辨认，补丁与非源码文件不进入记录。

    Recognize source changes without recording patches or unrelated private files.
    """
    source = tmp_path / "src/my_agent/sample.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("not a source input", encoding="utf-8")

    def git(args, cwd):
        """只模拟 Git 元数据。 Simulate Git metadata without repository writes."""
        assert cwd == tmp_path
        if args[1] == "ls-files":
            assert ".env" not in args
            return b"src/my_agent/sample.py\0"
        if args[1] == "diff":
            return b"raw patch must not be saved"
        return b"head-id\n"

    monkeypatch.setattr(ticket_manifest.subprocess, "check_output", git)
    first = ticket_manifest.source_manifest(tmp_path)
    source.write_text("value = 2\n", encoding="utf-8")
    second = ticket_manifest.source_manifest(tmp_path)
    assert first["file_set_sha256"] != second["file_set_sha256"]
    assert "raw patch" not in json.dumps(second) and ".env" not in json.dumps(second)


def test_phase_manifest_preserves_both_configs(tmp_path, monkeypatch):
    """输出预算变化另存文件，不覆盖初始配置。 Preserve changed limits in a separate snapshot."""
    monkeypatch.setattr(ticket_manifest, "source_manifest", lambda: {"head": "example"})
    project = tmp_path / "project"
    project.mkdir()
    seed = project / "ticket_report.py"
    seed.write_text("synthetic agent seed", encoding="utf-8")
    first = ticket_manifest.save_manifest(
        tmp_path, "implementation", {"max_output_tokens": 8192}, "one"
    )
    second = ticket_manifest.save_manifest(
        tmp_path, "implementation", {"max_output_tokens": 16384}, "two"
    )
    assert first["path"] != second["path"]
    snapshots = [
        json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.glob("manifest-*.json")
    ]
    assert {s["config"]["max_output_tokens"] for s in snapshots} == {8192, 16384}
    assert all(s["at"].endswith("+00:00") for s in snapshots)
    assert all(
        s["project_inputs"]["ticket_report.py"] == ticket_manifest.digest(b"synthetic agent seed")
        for s in snapshots
    )
    assert "synthetic agent seed" not in json.dumps(snapshots)
