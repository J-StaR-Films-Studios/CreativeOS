"""Cleanup must reject temp paths that resolve to valuable data."""

from pathlib import Path

import pytest

from cos import system_storage


@pytest.mark.parametrize("target_kind", ["workspace", "workspace-child", "parent", "drive-root", "project"])
def test_cleanup_rejects_protected_temp_targets(tmp_path, monkeypatch, target_kind):
    workspace = tmp_path / "Workspace"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("keep", encoding="utf-8")
    child = workspace / "Temp"
    child.mkdir()
    project = tmp_path / "OutsideProject"
    project.mkdir()
    (project / ".project_meta.json").write_text("{}", encoding="utf-8")
    choices = {
        "workspace": workspace,
        "workspace-child": child,
        "parent": workspace / "..",
        "drive-root": Path(tmp_path.anchor) / "..",
        "project": project,
    }
    monkeypatch.setattr(system_storage.sys, "platform", "win32")
    monkeypatch.setattr(system_storage, "_load_config", lambda: {"root_path": str(workspace)})
    monkeypatch.setenv("TEMP", str(choices[target_kind]))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))

    def must_not_delete(*args, **kwargs):
        pytest.fail("Rejected target reached the deletion function")

    monkeypatch.setattr(system_storage, "_clear_contents", must_not_delete)
    assert system_storage.scan_windows_cleanup()["locations"][0]["status"] == "inaccessible"
    assert system_storage.clear_windows_cleanup(["user-temp"])["results"][0]["status"] == "inaccessible"
    assert (workspace / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_cleanup_rejects_user_data_and_external_project_paths(tmp_path, monkeypatch):
    home = tmp_path / "Home"
    documents = home / "Documents"
    documents.mkdir(parents=True)
    external = tmp_path / "External"
    external.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(system_storage, "_load_config", lambda: {"external_projects": [str(external)]})
    assert not system_storage._safe_cleanup_root(home)
    assert not system_storage._safe_cleanup_root(documents)
    assert not system_storage._safe_cleanup_root(external)
