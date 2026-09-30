"""Focused checks for CLI-equivalent GUI workflows."""

import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

from cos.api import app


@pytest.fixture
def workspace(temp_dir, temp_projects_dir, temp_config, monkeypatch):
    config = json.loads(temp_config.read_text(encoding="utf-8"))
    monkeypatch.setattr("cos.config.CONFIG_PATH", str(temp_config))
    monkeypatch.setattr("cos.config._CONFIG", config)
    monkeypatch.setattr("cos.config._config_loaded", True)
    monkeypatch.setattr("cos.api.CONFIG_PATH", str(temp_config))
    monkeypatch.setattr("cos.api.PROJECTS_PATH", str(temp_projects_dir))
    monkeypatch.setattr("cos.storage.PROJECTS_PATH", str(temp_projects_dir))
    monkeypatch.setattr("cos.api.EXPORTS_PATH", config["exports_path"])
    monkeypatch.setattr("cos.api.ARCHIVE_PATH", config["archive_path"])
    monkeypatch.setattr("cos.api.SHUTTLE_PATH", config["shuttle_path"])
    monkeypatch.setattr("cos.api._get_allowed_roots", lambda: [temp_dir.resolve(), temp_projects_dir.resolve()])
    monkeypatch.setattr("cos.api._PROJECTS_CACHE", {"data": None, "time": 0.0})
    return TestClient(app), config, temp_dir, temp_projects_dir, temp_config


def test_gui_downloads_uses_cli_categories(workspace):
    client, _, temp_dir, _, _ = workspace
    downloads = temp_dir / "Downloads"
    downloads.mkdir()
    for name in ("font.ttf", "disk.iso", "unknown.xyz", "photo.ico", ".hidden.txt"):
        (downloads / name).write_text("test", encoding="utf-8")

    response = client.post("/api/system/clean-downloads", json={"folder": str(downloads)})

    assert response.status_code == 200
    assert response.json()["moved_count"] == 4
    assert (downloads / "_Fonts" / "font.ttf").exists()
    assert (downloads / "_Installers" / "disk.iso").exists()
    assert (downloads / "_Other" / "unknown.xyz").exists()
    assert (downloads / "_Other" / "photo.ico").exists()
    assert (downloads / ".hidden.txt").exists()


def test_gui_clone_uses_dated_name_and_selected_projects_subfolder(workspace, monkeypatch):
    client, _, _, projects, _ = workspace

    def fake_git(command, **kwargs):
        assert command[:3] == ["git", "clone", "--"]
        Path(command[-1]).mkdir()
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("cos.api.subprocess.run", fake_git)
    payload = {"url": "owner/sample", "name": "My Repo", "category": "Code",
               "date": "2025-04-12", "destination_subpath": "Code/Clones"}
    response = client.post("/api/projects/clone", json=payload)

    assert response.status_code == 201
    path = projects / "Code" / "Clones" / "2025-04-12_My_Repo"
    assert path == Path(response.json()["path"])
    assert response.json()["project"]["slug"] == path.name
    assert response.json()["project"]["created"] == "2025-04-12"
    assert client.post("/api/projects/clone", json={**payload, "destination_subpath": "../Other"}).status_code == 400
    assert client.post("/api/projects/clone", json={**payload, "date": "not-a-date"}).status_code == 400
    existing = projects / "Code" / "Existing"
    existing.mkdir()
    (existing / ".project_meta.json").write_text("{}", encoding="utf-8")
    assert client.post("/api/projects/clone", json={
        **payload, "destination_subpath": "Code/Existing/Clones",
    }).status_code == 400


def test_adopt_outside_projects_stays_visible_and_renames_in_place(workspace):
    client, _, temp_dir, projects, config_path = workspace
    external = temp_dir / "Unsorted" / "Old Project"
    external.mkdir(parents=True)
    (external / "existing.txt").write_text("keep", encoding="utf-8")
    endpoint = "/api/projects/init"
    assert client.post(endpoint, json={"path": str(external)}).status_code == 400

    response = client.post(endpoint, json={"path": str(external), "confirm_external": True})
    assert response.status_code == 200
    assert external.exists() and (external / "existing.txt").exists()
    assert str(external) in json.loads(config_path.read_text(encoding="utf-8"))["external_projects"]
    assert str(external) in {p["path"] for p in client.get("/api/projects").json()}
    assert str(external) in {p["path"] for p in client.get("/api/storage").json()["projects"]}

    renamed = client.put(f"/api/projects/{quote(str(external), safe='')}", json={
        "name": "New Project", "sync_filesystem": True,
    })
    assert renamed.status_code == 200
    destination = external.parent / "New_Project"
    assert destination.exists() and not external.exists()
    assert not destination.is_relative_to(projects)
    assert str(destination) in json.loads(config_path.read_text(encoding="utf-8"))["external_projects"]
    assert str(destination) in {p["path"] for p in client.get("/api/projects").json()}


def test_archiving_outside_project_removes_registry_entry(workspace):
    client, _, temp_dir, _, config_path = workspace
    external = temp_dir / "External" / "Archive Me"
    external.mkdir(parents=True)
    assert client.post("/api/projects/init", json={
        "path": str(external), "confirm_external": True,
    }).status_code == 200

    response = client.post(f"/api/projects/{quote(str(external), safe='')}/archive")
    assert response.status_code == 200
    assert not external.exists()
    assert str(external) not in json.loads(config_path.read_text(encoding="utf-8"))["external_projects"]
    assert str(external) not in {p["path"] for p in client.get("/api/projects").json()}


def test_resurrect_uses_exact_archived_path_when_names_repeat(workspace):
    client, config, temp_dir, projects, _ = workspace
    archive = Path(config["archive_path"])
    for category in ("Video", "Code"):
        folder = archive / category / "Same Name"
        folder.mkdir(parents=True)
        (folder / ".project_meta.json").write_text(json.dumps({
            "name": "Same Name", "slug": "Same Name", "type": category,
        }), encoding="utf-8")

    selected = archive / "Code" / "Same Name"
    response = client.post(f"/api/projects/{quote(str(selected), safe='')}/resurrect")

    assert response.status_code == 200
    assert (projects / "Code" / "Same Name").exists()
    assert (archive / "Video" / "Same Name").exists()
    assert not selected.exists()


def test_export_month_and_sort_dotfiles(workspace):
    client, config, _, _, _ = workspace
    exports = Path(config["exports_path"])
    response = client.post("/api/exports/month-folder")
    now = datetime.datetime.now()
    expected = exports / now.strftime("%Y") / now.strftime("%m - %B")
    assert response.status_code == 200
    assert Path(response.json()["path"]) == expected
    assert expected.is_dir()

    inbox = exports / "_Inbox"
    inbox.mkdir()
    (inbox / ".render.txt").write_text("export", encoding="utf-8")
    sorted_response = client.post("/api/exports/sort-inbox")
    assert sorted_response.status_code == 200
    assert sorted_response.json()["moved_count"] == 1
    assert not (inbox / ".render.txt").exists()


def test_gui_config_rejects_paths_it_does_not_manage(workspace):
    client, _, temp_dir, _, config_path = workspace
    original = config_path.read_text(encoding="utf-8")
    response = client.put("/api/config/paths", json={
        "paths": {"root_path": str(temp_dir / "changed")},
    })
    assert response.status_code == 400
    assert config_path.read_text(encoding="utf-8") == original
