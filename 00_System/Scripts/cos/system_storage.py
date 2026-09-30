"""Inventory and deliberate cleanup of known Windows cache directories."""

from __future__ import annotations

import datetime as dt
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from .config import WINDOWS_CLEANUP_INDEX_PATH, _load_config

INDEX_VERSION = 1


def _locations() -> list[tuple[str, str, Path]]:
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    windows = Path(os.environ.get("SystemRoot") or "C:\\Windows")
    temp = Path(os.environ.get("TEMP") or local / "Temp")
    return [
        ("user-temp", "User temporary files", temp),
        ("windows-temp", "Windows temporary files", windows / "Temp"),
        ("prefetch", "Prefetch", windows / "Prefetch"),
        ("directx", "DirectX shader cache", local / "D3DSCache"),
        ("nvidia-dx", "NVIDIA DirectX cache", local / "NVIDIA" / "DXCache"),
        ("nvidia-gl", "NVIDIA OpenGL cache", local / "NVIDIA" / "GLCache"),
        ("amd-dx", "AMD shader cache", local / "AMD" / "DxCache"),
        ("updates", "Windows Update downloads", windows / "SoftwareDistribution" / "Download"),
    ]


def _is_junction(path: Path) -> bool:
    # Path.is_junction was added in Python 3.12; older Windows versions of
    # Python still expose the reparse-point flag through lstat.
    if hasattr(path, "is_junction"):
        return path.is_junction()
    return bool(
        getattr(path.lstat(), "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _safe_directory(path: Path) -> bool:
    """Do not descend through redirected directories, including ancestor junctions."""
    if not path.is_absolute() or path.resolve() == Path(path.anchor):
        return False
    for part in (path, *path.parents):
        if part.is_symlink() or _is_junction(part):
            return False
    return True


def _safe_cleanup_root(path: Path) -> bool:
    """Environment-derived cache paths must not contain workspace or user data."""
    if not _safe_directory(path):
        return False
    resolved = path.resolve()
    config = _load_config()
    protected = [Path(value).resolve() for key, value in config.items()
                 if key.endswith("_path") and isinstance(value, str) and value]
    protected.extend(Path(value).resolve() for value in config.get("external_projects", [])
                     if isinstance(value, str))
    home = Path.home().resolve()
    protected.extend(home / name for name in (
        "Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", ".ssh"
    ))
    if home == resolved or home.is_relative_to(resolved):
        return False
    if any(resolved.is_relative_to(root) or root.is_relative_to(resolved) for root in protected):
        return False
    return not any((parent / ".project_meta.json").exists() for parent in (resolved, *resolved.parents))


def _measure(path: Path) -> dict[str, Any]:
    size = 0
    files = 0
    skipped = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink() or _is_junction(Path(entry.path)):
                            skipped += 1
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            size += entry.stat(follow_symlinks=False).st_size
                            files += 1
                    except OSError:
                        skipped += 1
        except OSError:
            if current == path:
                return {"status": "inaccessible", "size_bytes": None, "file_count": None, "skipped": 1}
            skipped += 1
    return {
        "status": "partial" if skipped else "available",
        "size_bytes": size,
        "file_count": files,
        "skipped": skipped,
    }


def scan_windows_cleanup() -> dict[str, Any]:
    """Measure only known directories; never follow links or remove files."""
    if sys.platform != "win32":
        return {"supported": False, "scanned_at": None, "locations": []}

    locations = []
    for identifier, name, path in _locations():
        try:
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or not _safe_cleanup_root(path):
                result = {"status": "inaccessible", "size_bytes": None, "file_count": None, "skipped": 1}
            else:
                result = _measure(path)
        except FileNotFoundError:
            result = {"status": "missing", "size_bytes": None, "file_count": None, "skipped": 0}
        except OSError:
            result = {"status": "inaccessible", "size_bytes": None, "file_count": None, "skipped": 1}
        locations.append({"id": identifier, "name": name, "path": str(path), **result})

    return {
        "supported": True,
        "scanned_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "locations": locations,
    }


def load_windows_cleanup_index(index_path: str | Path | None = None) -> dict[str, Any]:
    """Return a saved snapshot without walking any cleanup directory."""
    if sys.platform != "win32":
        return {"supported": False, "scanned_at": None, "locations": []}
    empty = {"supported": True, "scanned_at": None, "locations": []}
    try:
        data = json.loads(Path(index_path or WINDOWS_CLEANUP_INDEX_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    expected = {identifier: str(path) for identifier, _, path in _locations()}
    if (not isinstance(data, dict) or data.get("version") != INDEX_VERSION
            or not isinstance(data.get("scanned_at"), str)
            or not isinstance(data.get("locations"), list)
            or len(data["locations"]) != len(expected)):
        return empty
    try:
        if {item["id"]: item["path"] for item in data["locations"]} != expected:
            return empty
        if any(item["status"] not in ("available", "partial", "missing", "inaccessible")
               or (item["size_bytes"] is not None and
                   (not isinstance(item["size_bytes"], int) or item["size_bytes"] < 0))
               for item in data["locations"]):
            return empty
    except (KeyError, TypeError):
        return empty
    return data


def refresh_windows_cleanup_index(index_path: str | Path | None = None) -> dict[str, Any]:
    """Scan Windows caches and atomically save the result for GUI and scheduled use."""
    snapshot = scan_windows_cleanup()
    if not snapshot["supported"]:
        return snapshot
    snapshot["version"] = INDEX_VERSION
    path = Path(index_path or WINDOWS_CLEANUP_INDEX_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return snapshot


def _clear_contents(
    path: Path, on_progress: Callable[[int, int, int], None] | None = None
) -> dict[str, Any]:
    """Remove contents, not the cache root. Leave locked items and links alone."""
    freed = 0
    removed = 0
    skipped = 0
    processed = 0
    stack = [(path, False)]
    while stack:
        current, after_children = stack.pop()
        if after_children:
            try:
                if _safe_directory(current):
                    current.rmdir()
                else:
                    skipped += 1
            except OSError:
                skipped += 1
            continue
        try:
            if not _safe_directory(current):
                skipped += 1
                continue
            with os.scandir(current) as entries:
                children = list(entries)
        except OSError:
            skipped += 1
            continue
        for entry in children:
            child = Path(entry.path)
            try:
                if entry.is_symlink() or _is_junction(child):
                    skipped += 1
                elif entry.is_dir(follow_symlinks=False):
                    stack.append((child, True))
                    stack.append((child, False))
                elif entry.is_file(follow_symlinks=False):
                    processed += 1
                    try:
                        size = entry.stat(follow_symlinks=False).st_size
                        if child.is_symlink() or _is_junction(child):
                            skipped += 1
                        else:
                            child.unlink()
                            freed += size
                            removed += 1
                    except OSError:
                        skipped += 1
                    if on_progress and processed % 256 == 0:
                        on_progress(processed, freed, removed)
                else:
                    skipped += 1
            except OSError:
                skipped += 1
    if on_progress:
        on_progress(processed, freed, removed)
    return {"status": "partial" if skipped else "cleared", "removed_bytes": freed,
            "removed_files": removed, "processed_files": processed, "skipped": skipped}


def validate_windows_cleanup_ids(ids: list[str]) -> dict[str, tuple[str, Path]]:
    """Resolve only the fixed cleanup locations, never paths supplied by the client."""
    locations = {identifier: (name, path) for identifier, name, path in _locations()}
    if sys.platform != "win32" or not ids or len(set(ids)) != len(ids) or any(
        identifier not in locations for identifier in ids
    ):
        raise ValueError("Select valid, distinct Windows cleanup locations")
    return locations


def clear_windows_cleanup(
    ids: list[str], on_progress: Callable[[dict[str, Any]], None] | None = None
) -> dict[str, Any]:
    """Clear only explicitly selected, allowlisted folder contents."""
    locations = validate_windows_cleanup_ids(ids)
    results = []
    total_processed = 0
    total_freed = 0
    total_removed = 0
    for index, identifier in enumerate(ids, start=1):
        name, path = locations[identifier]

        def report(processed: int, freed: int, removed: int) -> None:
            if on_progress:
                on_progress({
                    "location": name, "current": index, "total": len(ids),
                    "processed_files": total_processed + processed,
                    "removed_bytes": total_freed + freed,
                    "removed_files": total_removed + removed,
                })

        report(0, 0, 0)
        try:
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or not _safe_cleanup_root(path):
                outcome = {"status": "inaccessible", "removed_bytes": 0,
                           "removed_files": 0, "skipped": 1}
            else:
                outcome = _clear_contents(path, report)
        except FileNotFoundError:
            outcome = {"status": "missing", "removed_bytes": 0,
                       "removed_files": 0, "skipped": 0}
        except OSError:
            outcome = {"status": "inaccessible", "removed_bytes": 0,
                       "removed_files": 0, "skipped": 1}
        results.append({"id": identifier, "name": name, **outcome})
        total_freed += outcome["removed_bytes"]
        total_removed += outcome["removed_files"]
        total_processed += outcome.get("processed_files", 0)
        # For a missing/inaccessible folder or the final batch, report the
        # completed folder even when no file could be removed.
        if on_progress:
            on_progress({
                "location": name, "current": index, "total": len(ids),
                "processed_files": total_processed,
                "removed_bytes": total_freed, "removed_files": total_removed,
            })
    return {"results": results}
