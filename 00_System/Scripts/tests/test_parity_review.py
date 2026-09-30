"""Regressions found by the independent parity review."""

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from cos import api, config, storage


@pytest.fixture
def workspace(temp_config, temp_dir, temp_projects_dir, monkeypatch):
    settings = json.loads(temp_config.read_text(encoding="utf-8"))
    monkeypatch.setattr(config, "CONFIG_PATH", str(temp_config))
    monkeypatch.setattr(config, "_CONFIG", settings)
    monkeypatch.setattr(config, "_config_loaded", True)
    monkeypatch.setattr(api, "CONFIG_PATH", str(temp_config))
    for module in (api, storage):
        monkeypatch.setattr(module, "PROJECTS_PATH", str(temp_projects_dir))
    monkeypatch.setattr(api, "EXPORTS_PATH", settings["exports_path"])
    monkeypatch.setattr(api, "_PROJECTS_CACHE", {"data": None, "time": 0.0})
    monkeypatch.setattr(api, "_get_allowed_roots", lambda: [
        temp_projects_dir.resolve(), Path(settings["exports_path"]),
        *storage.external_project_paths(),
    ])
    return TestClient(api.app), temp_dir, temp_projects_dir, temp_config


def test_confirmed_adoption_grants_only_selected_outside_folder(workspace):
    client, root, _, _ = workspace
    target = root / "Unmanaged" / "Project"
    target.mkdir(parents=True)
    sibling = target.parent / "Sibling"
    sibling.mkdir()
    assert client.post("/api/projects/init", json={"path": str(target)}).status_code >= 400
    assert client.post("/api/projects/init", json={
        "path": str(target), "confirm_external": True,
    }).status_code == 200
    assert client.get("/api/fs/list", params={"path": str(target)}).status_code == 200
    assert client.get("/api/fs/list", params={"path": str(sibling)}).status_code == 403
    assert str(target) in {p["path"] for p in client.get("/api/projects").json()}


def test_adoption_confirmation_does_not_allow_system_folders(workspace, monkeypatch):
    client, root, projects, _ = workspace
    system = root / "Windows"
    system.mkdir()
    monkeypatch.setenv("SystemRoot", str(system))
    for path in (system, root, Path(root.anchor), projects):
        assert client.post("/api/projects/init", json={
            "path": str(path), "confirm_external": True,
        }).status_code >= 400
        assert not (path / ".project_meta.json").exists()


@pytest.mark.parametrize("inside_projects", [False, True])
def test_transfer_updates_adopted_project_registry(workspace, monkeypatch, inside_projects):
    client, root, projects, config_path = workspace
    project = root / "Outside" / "My Project"
    project.mkdir(parents=True)
    assert client.post("/api/projects/init", json={
        "path": str(project), "confirm_external": True,
    }).status_code == 200
    destination = projects / "Code" if inside_projects else root / "Other"
    destination.mkdir(exist_ok=True)
    monkeypatch.setattr(api, "_get_allowed_roots", lambda: [root.resolve()])
    response = client.post("/api/fs/transfer", json={
        "source": str(project), "destination": str(destination), "move": True,
    })
    assert response.status_code == 200
    moved = destination / project.name
    assert moved.exists() and not project.exists()
    registered = json.loads(config_path.read_text(encoding="utf-8"))["external_projects"]
    assert str(project) not in registered
    assert (str(moved) in registered) is not inside_projects
    assert str(moved) in {p["path"] for p in client.get("/api/projects").json()}
    assert str(moved) in {p["path"] for p in client.get("/api/storage").json()["projects"]}


def test_transfer_rolls_back_if_registry_cannot_be_saved(workspace, monkeypatch):
    client, root, _, _ = workspace
    project = root / "Outside" / "My Project"
    project.mkdir(parents=True)
    assert client.post("/api/projects/init", json={
        "path": str(project), "confirm_external": True,
    }).status_code == 200
    destination = root / "Other"
    destination.mkdir()
    monkeypatch.setattr(api, "_get_allowed_roots", lambda: [root.resolve()])

    def fail_save(paths):
        raise OSError("config is read-only")

    monkeypatch.setattr(api, "_save_external_projects", fail_save)
    response = client.post("/api/fs/transfer", json={
        "source": str(project), "destination": str(destination), "move": True,
    })
    assert response.status_code == 500
    assert project.exists() and not (destination / project.name).exists()
    assert project in storage.external_project_paths()


def test_export_sort_rejects_project_roots_and_keeps_metadata(workspace):
    client, _, projects, _ = workspace
    project = projects / "Code" / "Keep"
    project.mkdir()
    (project / ".project_meta.json").write_text("{}", encoding="utf-8")
    (project / ".render.txt").write_text("render", encoding="utf-8")
    response = client.post("/api/exports/sort-inbox", json={"inbox_path": str(project)})
    assert response.status_code == 400
    assert (project / ".project_meta.json").exists()
    assert (project / ".render.txt").exists()


def test_failed_migration_preserves_saved_and_loaded_configuration(workspace, monkeypatch):
    client, root, _, config_path = workspace
    old_vault = root / "OldVault"
    old_vault.mkdir()
    (old_vault / "note.md").write_text("keep", encoding="utf-8")
    settings = config._load_config()
    settings["vault_path"] = str(old_vault)
    config_path.write_text(json.dumps(settings), encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")

    def fail_copy(*args, **kwargs):
        raise PermissionError("copy denied")

    monkeypatch.setattr(api.shutil, "copy2", fail_copy)
    response = client.put("/api/config/paths", json={
        "paths": {"vault_path": str(root / "NewVault")}, "move_files": True,
    })
    assert response.status_code == 500
    assert "paths were not saved" in response.json()["detail"]
    assert config_path.read_text(encoding="utf-8") == before
    assert config._load_config()["vault_path"] == str(old_vault)
    assert (old_vault / "note.md").exists()


def test_registration_failure_preserves_existing_project_metadata(workspace, monkeypatch):
    client, root, _, _ = workspace
    project = root / "Outside" / "Existing"
    project.mkdir(parents=True)
    metadata = project / ".project_meta.json"
    original = json.dumps({"name": "Original", "description": "Keep this", "custom": {"key": 42}})
    metadata.write_text(original, encoding="utf-8")

    def fail_save(paths):
        raise PermissionError("config is read-only")

    monkeypatch.setattr(api, "_save_external_projects", fail_save)
    response = client.post("/api/projects/init", json={
        "path": str(project), "confirm_external": True, "name": "Must not overwrite",
    })
    assert response.status_code == 500
    assert metadata.read_text(encoding="utf-8") == original
    assert not (project / "00_Notes").exists()


@pytest.mark.parametrize("content", ["broken JSON", "[]"])
def test_adoption_does_not_overwrite_invalid_existing_metadata(workspace, content):
    client, root, _, _ = workspace
    project = root / "Outside" / "Existing"
    project.mkdir(parents=True)
    metadata = project / ".project_meta.json"
    metadata.write_text(content, encoding="utf-8")
    response = client.post("/api/projects/init", json={
        "path": str(project), "confirm_external": True,
    })
    assert response.status_code == 400
    assert metadata.read_text(encoding="utf-8") == content


def test_relative_adoption_cannot_bypass_system_directory_protection(workspace, monkeypatch):
    client, root, _, _ = workspace
    system = root / "Windows"
    target = system / "System32"
    target.mkdir(parents=True)
    monkeypatch.setenv("SystemRoot", str(system))
    monkeypatch.setattr(api, "_get_allowed_roots", lambda: [root.resolve()])
    for submitted in (str(target), "../Windows/System32"):
        response = client.post("/api/projects/init", json={
            "path": submitted, "confirm_external": True,
        })
        assert response.status_code == 403
    assert not (target / ".project_meta.json").exists()


def test_external_projects_stay_visible_without_projects_directory(workspace):
    client, root, projects, _ = workspace
    project = root / "Outside" / "Available"
    project.mkdir(parents=True)
    assert client.post("/api/projects/init", json={
        "path": str(project), "confirm_external": True,
    }).status_code == 200
    projects.rename(root / "DisconnectedProjects")
    response = client.get("/api/projects", params={"nocache": True})
    assert response.status_code == 200
    assert str(project) in {entry["path"] for entry in response.json()}
    assert project in {path for path, _ in storage.discover_projects()}
    # Archive or other explicit search roots must not include the external registry.
    assert storage.discover_projects(root / "MissingArchive") == []
