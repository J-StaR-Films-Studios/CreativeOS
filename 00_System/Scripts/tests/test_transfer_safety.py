"""Transfer must not move protected roots or recurse into the source directory."""

import pytest
from fastapi import HTTPException

from cos import api


def test_transfer_rejects_protected_root(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "work.txt").write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(api, "_get_allowed_roots", lambda: [projects.resolve()])

    with pytest.raises(HTTPException) as error:
        api.transfer_fs(api.TransferRequest(
            source=str(projects), destination=str(projects / "moved"), move=True
        ))

    assert error.value.status_code == 400
    assert (projects / "work.txt").read_text(encoding="utf-8") == "preserve"
    assert not (projects / "moved").exists()


@pytest.mark.parametrize("move", [False, True])
def test_transfer_rejects_own_descendant(tmp_path, monkeypatch, move):
    projects = tmp_path / "projects"
    source = projects / "Film"
    child = source / "nested"
    child.mkdir(parents=True)
    (source / "work.txt").write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(api, "_get_allowed_roots", lambda: [projects.resolve()])

    with pytest.raises(HTTPException) as error:
        api.transfer_fs(api.TransferRequest(
            source=str(source), destination=str(child), move=move
        ))

    assert error.value.status_code == 400
    assert (source / "work.txt").read_text(encoding="utf-8") == "preserve"
    assert not (child / "Film").exists()


def test_move_over_existing_directory_does_not_nest_source(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    source = projects / "From" / "Film"
    destination = projects / "To"
    source.mkdir(parents=True)
    (source / "new.txt").write_text("source", encoding="utf-8")
    (destination / "Film").mkdir(parents=True)
    (destination / "Film" / "old.txt").write_text("existing", encoding="utf-8")
    monkeypatch.setattr(api, "_get_allowed_roots", lambda: [projects.resolve()])

    with pytest.raises(HTTPException) as error:
        api.transfer_fs(api.TransferRequest(
            source=str(source), destination=str(destination), move=True, overwrite=True
        ))

    assert error.value.status_code == 409
    assert (source / "new.txt").read_text(encoding="utf-8") == "source"
    assert (destination / "Film" / "old.txt").read_text(encoding="utf-8") == "existing"
    assert not (destination / "Film" / "Film").exists()


def test_adoption_outside_projects_root_rejected_before_writing(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    external = tmp_path / "Desktop" / "Other Work"
    external.mkdir(parents=True)
    monkeypatch.setattr(api, "PROJECTS_PATH", str(projects))
    monkeypatch.setattr(api, "_get_allowed_roots", lambda: [tmp_path.resolve()])

    with pytest.raises(HTTPException) as error:
        api.init_project(api.InitProjectRequest(path=str(external)))

    assert error.value.status_code == 400
    assert not (external / ".project_meta.json").exists()
    assert not (external / "00_Notes").exists()


def test_music_category_browses_projects_music(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    music = projects / "Music"
    music.mkdir(parents=True)
    monkeypatch.setattr(api, "PROJECTS_PATH", str(projects))
    monkeypatch.setattr(api, "_get_allowed_roots", lambda: [projects.resolve()])

    listing = api.list_fs("Music")

    assert listing["current_path"] == str(music.resolve())
