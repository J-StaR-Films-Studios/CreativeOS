"""Tests for the cached, non-destructive storage inventory."""

import argparse
import json
import os
import time
from pathlib import Path

import pytest

from cos import storage, system_storage
from cos.commands import storage as storage_command


def _create_project(root: Path, name: str = "Storage Project") -> Path:
    project = root / "Video" / "2024-01-01_Storage_Project"
    project.mkdir(parents=True)
    (project / ".project_meta.json").write_text(
        json.dumps({
            "name": name,
            "slug": "2024-01-01_Storage_Project",
            "type": "Video",
            "created": "2024-01-01",
        }),
        encoding="utf-8",
    )
    return project


def test_windows_cleanup_scan_is_read_only_and_skips_links(temp_dir, monkeypatch):
    monkeypatch.setattr(system_storage.sys, "platform", "win32")
    local = temp_dir / "local"
    windows = temp_dir / "windows"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("TEMP", str(local / "Temp"))
    monkeypatch.setenv("SystemRoot", str(windows))
    user_temp = local / "Temp"
    user_temp.mkdir(parents=True)
    (user_temp / "nested").mkdir()
    (user_temp / "nested" / "cache.bin").write_bytes(b"12345")
    outside = temp_dir / "outside"
    outside.mkdir()
    (outside / "keep.bin").write_bytes(b"outside")
    (user_temp / "link").symlink_to(outside, target_is_directory=True)

    result = system_storage.scan_windows_cleanup()
    by_id = {item["id"]: item for item in result["locations"]}

    assert result["supported"] is True
    assert len(by_id) == 8
    assert by_id["user-temp"]["size_bytes"] == 5
    assert by_id["user-temp"]["file_count"] == 1
    assert by_id["user-temp"]["status"] == "partial"
    assert by_id["user-temp"]["skipped"] == 1
    assert by_id["updates"]["status"] == "missing"
    assert (outside / "keep.bin").read_bytes() == b"outside"
    assert (user_temp / "nested" / "cache.bin").exists()


def test_windows_cleanup_reports_unreadable_folder(temp_dir, monkeypatch):
    monkeypatch.setattr(system_storage.sys, "platform", "win32")
    monkeypatch.setenv("TEMP", str(temp_dir))
    original_scandir = system_storage.os.scandir

    def denied(path):
        if Path(path) == temp_dir:
            raise PermissionError("denied")
        return original_scandir(path)

    monkeypatch.setattr(system_storage.os, "scandir", denied)
    result = system_storage.scan_windows_cleanup()
    assert result["locations"][0]["status"] == "inaccessible"
    assert result["locations"][0]["size_bytes"] is None


def test_clear_windows_cleanup_removes_only_selected_contents(temp_dir, monkeypatch):
    monkeypatch.setattr(system_storage.sys, "platform", "win32")
    local = temp_dir / "local"
    windows = temp_dir / "windows"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("TEMP", str(local / "Temp"))
    monkeypatch.setenv("SystemRoot", str(windows))
    user_temp = local / "Temp"
    shader = local / "D3DSCache"
    (user_temp / "nested").mkdir(parents=True)
    shader.mkdir(parents=True)
    (user_temp / "nested" / "cache.bin").write_bytes(b"cache")
    (shader / "keep.bin").write_bytes(b"shader")
    outside = temp_dir / "outside"
    outside.mkdir()
    (outside / "keep.bin").write_bytes(b"outside")
    (user_temp / "link").symlink_to(outside, target_is_directory=True)

    result = system_storage.clear_windows_cleanup(["user-temp"])["results"][0]

    assert result["status"] == "partial"
    assert result["removed_bytes"] == 5
    assert result["removed_files"] == 1
    assert result["skipped"] >= 1
    assert user_temp.exists()
    assert not (user_temp / "nested").exists()
    assert (user_temp / "link").is_symlink()
    assert (outside / "keep.bin").read_bytes() == b"outside"
    assert (shader / "keep.bin").read_bytes() == b"shader"


def test_clear_windows_cleanup_reports_file_progress(temp_dir, monkeypatch):
    monkeypatch.setattr(system_storage.sys, "platform", "win32")
    target = temp_dir / "Temp"
    target.mkdir()
    monkeypatch.setenv("TEMP", str(target))
    for index in range(300):
        (target / f"{index}.tmp").write_bytes(b"x")

    updates = []
    result = system_storage.clear_windows_cleanup(["user-temp"], on_progress=updates.append)

    assert any(update["processed_files"] == 256 for update in updates)
    assert updates[-1]["processed_files"] == 300
    assert updates[-1]["removed_bytes"] == 300
    assert result["results"][0]["processed_files"] == 300
    assert not list(target.iterdir())


def test_clear_windows_cleanup_skips_locked_files(temp_dir, monkeypatch):
    monkeypatch.setattr(system_storage.sys, "platform", "win32")
    monkeypatch.setenv("TEMP", str(temp_dir / "Temp"))
    target = temp_dir / "Temp"
    target.mkdir()
    (target / "locked.bin").write_bytes(b"keep")
    (target / "free.bin").write_bytes(b"remove")
    original_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path.name == "locked.bin":
            raise PermissionError("locked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    result = system_storage.clear_windows_cleanup(["user-temp"])["results"][0]
    assert result["status"] == "partial"
    assert result["removed_bytes"] == 6
    assert result["skipped"] == 1
    assert (target / "locked.bin").exists()


def test_clear_windows_cleanup_rejects_unknown_and_redirected_locations(temp_dir, monkeypatch):
    monkeypatch.setattr(system_storage.sys, "platform", "win32")
    other = temp_dir / "other"
    other.mkdir()
    (other / "keep.bin").write_bytes(b"keep")
    monkeypatch.setenv("TEMP", str(temp_dir / "temp-link"))
    (temp_dir / "temp-link").symlink_to(other, target_is_directory=True)

    for ids in (["user-temp", "unknown"], ["user-temp", "user-temp"], []):
        with pytest.raises(ValueError):
            system_storage.clear_windows_cleanup(ids)

    result = system_storage.clear_windows_cleanup(["user-temp"])["results"][0]
    assert result["status"] == "inaccessible"
    assert (other / "keep.bin").read_bytes() == b"keep"


def test_windows_cleanup_unsupported(monkeypatch):
    monkeypatch.setattr(system_storage.sys, "platform", "linux")
    assert system_storage.scan_windows_cleanup() == {
        "supported": False, "scanned_at": None, "locations": []
    }
    with pytest.raises(ValueError):
        system_storage.clear_windows_cleanup(["user-temp"])


def test_windows_cleanup_index_persists_and_invalidates_changed_paths(temp_dir, monkeypatch):
    monkeypatch.setattr(system_storage.sys, "platform", "win32")
    local = temp_dir / "local"
    target = local / "Temp"
    target.mkdir(parents=True)
    (target / "cache.bin").write_bytes(b"12345")
    monkeypatch.setenv("TEMP", str(target))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("SystemRoot", str(temp_dir / "windows"))
    index_path = temp_dir / "windows_index.json"

    assert system_storage.load_windows_cleanup_index(index_path)["scanned_at"] is None
    first = system_storage.refresh_windows_cleanup_index(index_path)
    assert first["locations"][0]["size_bytes"] == 5
    assert system_storage.load_windows_cleanup_index(index_path) == first

    (target / "cache.bin").write_bytes(b"larger file")
    assert system_storage.load_windows_cleanup_index(index_path)["locations"][0]["size_bytes"] == 5
    second = system_storage.refresh_windows_cleanup_index(index_path)
    assert second["locations"][0]["size_bytes"] == 11
    monkeypatch.setenv("TEMP", str(local / "different-temp"))
    assert system_storage.load_windows_cleanup_index(index_path)["scanned_at"] is None


def test_scheduled_scan_refreshes_project_and_windows_indexes(monkeypatch):
    calls = []
    monkeypatch.setattr(storage_command.storage_index, "refresh_storage_index",
                        lambda: calls.append("projects") or {"project_count": 0, "total_size": 0})
    monkeypatch.setattr(storage_command, "refresh_windows_cleanup_index",
                        lambda: calls.append("windows"))
    storage_command.cmd_scan(argparse.Namespace(background=False, quiet=True))
    assert calls == ["projects", "windows"]


def test_inventory_measures_media_and_regenerable_folders(temp_projects_dir):
    """Node modules count toward space but not last meaningful activity."""
    project = _create_project(temp_projects_dir)
    source = project / "00_Notes" / "idea.md"
    source.parent.mkdir()
    source.write_bytes(b"note")

    footage = project / "01_Footage" / "clip.mp4"
    footage.parent.mkdir()
    footage.write_bytes(b"video-data")

    modules = project / "node_modules" / "package" / "index.js"
    modules.parent.mkdir(parents=True)
    modules.write_bytes(b"dependency")

    old_time = time.time() - 10 * 24 * 60 * 60
    newer_generated_time = time.time() - 60
    for file_path in (project / ".project_meta.json", source, footage):
        os.utime(file_path, (old_time, old_time))
    os.utime(modules, (newer_generated_time, newer_generated_time))

    index = storage.build_storage_index(temp_projects_dir)

    assert index["project_count"] == 1
    record = index["projects"][0]
    assert record["created"] == "2024-01-01"
    assert record["total_size"] == len(b"notevideo-datadependency") + (project / ".project_meta.json").stat().st_size
    assert record["media_size"] == len(b"video-data")
    assert record["reclaimable_size"] == len(b"dependency")
    assert record["last_meaningful_update"] != storage._iso(newer_generated_time)
    assert record["relative_path"] == "Video/2024-01-01_Storage_Project"


def test_discovery_does_not_count_nested_metadata_as_a_second_project(temp_projects_dir):
    project = _create_project(temp_projects_dir)
    nested = project / "reference" / ".project_meta.json"
    nested.parent.mkdir()
    nested.write_text("{}", encoding="utf-8")

    discovered = storage.discover_projects(temp_projects_dir)

    assert [path for path, _ in discovered] == [project]


def test_refresh_persists_index_and_reminder_consent(temp_projects_dir, temp_dir):
    _create_project(temp_projects_dir)
    index_path = temp_dir / "storage_index.json"

    first = storage.refresh_storage_index(temp_projects_dir, index_path)
    storage.set_reminders_enabled(True, index_path)
    second = storage.refresh_storage_index(temp_projects_dir, index_path)

    loaded = storage.load_storage_index(index_path)
    assert first["project_count"] == 1
    assert second["reminders_enabled"] is True
    assert loaded is not None
    assert loaded["projects_path"] == str(temp_projects_dir)
    assert loaded["reminders_enabled"] is True


def test_stale_projects_uses_meaningful_activity_date():
    index = {
        "projects": [
            {"name": "old", "last_meaningful_update": "2020-01-01T00:00:00+00:00"},
            {"name": "new", "last_meaningful_update": storage._utc_now().isoformat()},
            {"name": "unknown", "last_meaningful_update": None},
        ]
    }

    assert [project["name"] for project in storage.stale_projects(index, 90)] == ["old"]


def test_load_invalid_index_returns_none(temp_dir):
    index_path = temp_dir / "bad-index.json"
    index_path.write_text("not-json", encoding="utf-8")

    assert storage.load_storage_index(index_path) is None


def test_find_and_reclaim_project_space(temp_projects_dir, temp_dir):
    project = _create_project(temp_projects_dir, "Reclaim Demo")
    source = project / "00_Notes" / "idea.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"# Source Note")

    modules = project / "node_modules" / "pkg" / "index.js"
    modules.parent.mkdir(parents=True, exist_ok=True)
    modules.write_bytes(b"var x = 1;")

    next_cache = project / ".next" / "cache" / "data.json"
    next_cache.parent.mkdir(parents=True, exist_ok=True)
    next_cache.write_bytes(b'{"cache": true}')

    index_path = temp_dir / "storage_index.json"
    storage.refresh_storage_index(temp_projects_dir, index_path)

    # 1. Find reclaimable items
    items = storage.find_project_reclaimable_dirs(project)
    names = {it["name"] for it in items}
    assert "node_modules" in names
    assert ".next" in names

    # 2. Reclaim specific target (.next only)
    res_partial = storage.reclaim_project_space(
        project,
        target_subdirs=[".next"],
        projects_path=temp_projects_dir,
        index_path=index_path,
    )
    assert res_partial["status"] == "success"
    assert not (project / ".next").exists()
    assert (project / "node_modules").exists()
    assert (project / "00_Notes" / "idea.md").exists()

    # 3. Reclaim remaining target (all)
    res_all = storage.reclaim_project_space(
        project,
        projects_path=temp_projects_dir,
        index_path=index_path,
    )
    assert res_all["status"] == "success"
    assert not (project / "node_modules").exists()
    assert (project / "00_Notes" / "idea.md").exists()


def test_reclaim_bulk_space(temp_projects_dir, temp_dir):
    p1 = _create_project(temp_projects_dir, "Project 1")
    mod1 = p1 / "node_modules" / "index.js"
    mod1.parent.mkdir(parents=True, exist_ok=True)
    mod1.write_bytes(b"console.log('mod1');")

    index_path = temp_dir / "storage_index.json"
    storage.refresh_storage_index(temp_projects_dir, index_path)

    bulk_res = storage.reclaim_bulk_space(
        stale_only=False,
        projects_path=temp_projects_dir,
        index_path=index_path,
    )
    assert bulk_res["status"] == "success"
    assert bulk_res["total_freed_bytes"] > 0
    assert not (p1 / "node_modules").exists()

