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
