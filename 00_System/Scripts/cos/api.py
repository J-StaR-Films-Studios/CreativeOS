"""FastAPI backend API wrapper for CreativeOS GUI."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import string
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .category_config import (
    get_categories,
    get_category_folder,
    get_category_icon,
    get_default_category,
    get_enabled_categories,
    get_simple_template,
    resolve_category_name,
)
from .commands.clean import DOWNLOADS_MAPPING
from .commands.new import create_project_structure
from .commands.sync import run_sync, stream_sync
from .config import (
    ARCHIVE_PATH,
    CONFIG_PATH,
    DOWNLOADS_PATH,
    EXPORTS_PATH,
    PROJECTS_PATH,
    ROOT_PATH,
    SHUTTLE_PATH,
    TEMPLATES_PATH,
    VAULT_PATH,
    _load_config,
    logger,
    reload_config,
)
from .file_utils import get_date_slug, get_smart_date, robust_rmtree
from .security import (
    sanitize_path_input,
    validate_client_name,
    validate_git_url,
    validate_date,
    validate_path_component,
)
from .storage import (
    DEFAULT_STALE_DAYS,
    _created_date,
    _recalculate_totals,
    discover_projects,
    external_project_paths,
    find_project_reclaimable_dirs,
    load_storage_index,
    reclaim_bulk_space,
    reclaim_project_space,
    refresh_storage_index,
    remove_project_from_storage_index,
    save_storage_index,
    stale_projects,
    stream_reclaim_bulk,
    stream_reclaim_project,
    update_project_in_storage_index,
)
from .system_storage import (
    clear_windows_cleanup,
    load_windows_cleanup_index,
    refresh_windows_cleanup_index,
    validate_windows_cleanup_ids,
)

app = FastAPI(
    title="CreativeOS API",
    description="Lightweight API backend for CreativeOS GUI",
    version=__version__,
)

# ──────────────────────────────────────────────────────────────────────────────
# Security Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_allowed_roots() -> list[Path]:
    """Return all permitted filesystem roots for CreativeOS operations."""
    roots: list[Path] = []
    candidates = [
        ROOT_PATH,
        PROJECTS_PATH,
        EXPORTS_PATH,
        VAULT_PATH,
        DOWNLOADS_PATH,
        SHUTTLE_PATH,
        ARCHIVE_PATH,
    ]
    candidates.extend(external_project_paths())
    for p in candidates:
        if p and isinstance(p, (str, Path)):
            try:
                roots.append(Path(p).resolve())
            except Exception:
                pass

    # Standard User Folders
    user_home = Path.home()
    user_candidates = [
        user_home / "Desktop",
        user_home / "Downloads",
        user_home / "Documents",
        user_home / "Videos",
        user_home / "Music",
        user_home / "Pictures",
    ]
    userprofile_env = os.environ.get("USERPROFILE")
    if userprofile_env:
        for folder_name in ["Desktop", "Downloads", "Documents", "Videos", "Music", "Pictures"]:
            try:
                user_candidates.append(Path(userprofile_env) / folder_name)
            except Exception:
                pass

    for p in user_candidates:
        try:
            resolved = p.resolve()
            if resolved.exists():
                roots.append(resolved)
        except Exception:
            pass

    # Non-system drives (e.g. D:\, E:\, etc., excluding system drive root C:\ to protect OS directories like C:\Windows)
    system_drive = os.environ.get("SystemDrive", "C:").upper()
    for letter in string.ascii_uppercase:
        drive_str = f"{letter}:"
        if drive_str != system_drive:
            try:
                drive = Path(f"{letter}:\\")
                if drive.exists():
                    roots.append(drive.resolve())
            except Exception:
                pass

    # Configured External Storage Mounts
    try:
        raw_cfg = _load_config()
        for m in raw_cfg.get("external_mounts", []):
            if isinstance(m, dict) and "path" in m:
                mp = Path(m["path"]).resolve()
                if mp.exists():
                    roots.append(mp)
    except Exception:
        pass

    seen: set[Path] = set()
    deduped_roots: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            deduped_roots.append(r)

    return deduped_roots


def _check_path_allowed(target_path: str | Path) -> Path:
    """Verify that a path is strictly inside allowed workspace boundaries."""
    try:
        resolved = Path(target_path).resolve()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid path: {e}",
        )

    allowed = _get_allowed_roots()
    is_safe = any(
        resolved == root or root in resolved.parents
        for root in allowed
    )
    if not is_safe:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Target path is outside permitted workspace roots: {resolved}",
        )
    return resolved


def _is_allowed_root(path: Path) -> bool:
    """Return whether a path is one of the protected filesystem roots."""
    resolved = path.resolve()
    registered = set(external_project_paths())
    for root in _get_allowed_roots():
        try:
            if resolved == root.resolve() and root not in registered:
                return True
        except OSError:
            continue
    return False


def _find_project_dir(project_name: str, search_root: str | None = None) -> tuple[Path, dict[str, Any]]:
    """Locate a project directory and its metadata by slug, name, or relative path."""
    root = search_root or PROJECTS_PATH
    search_name = project_name.lower().strip().replace("/", "\\")

    # 1. Exact path check, including explicitly registered outside projects.
    candidate = (Path(root) / project_name).resolve()
    is_registered = not search_root and candidate in external_project_paths()
    if (candidate.is_relative_to(Path(root).resolve()) or is_registered) and candidate.is_dir() and (candidate / ".project_meta.json").is_file():
        try:
            with open(candidate / ".project_meta.json", "r", encoding="utf-8-sig") as f:
                return candidate, json.load(f)
        except Exception:
            pass

    # 2. Fast lookup from in-memory storage index (sub-millisecond)
    index = load_storage_index(projects_path=root)
    if index:
        for p in index.get("projects", []):
            p_name = (p.get("name") or "").lower()
            p_slug = (p.get("slug") or "").lower()
            p_path = str(p.get("path") or "").lower().replace("/", "\\")
            p_rel = str(p.get("relative_path") or "").lower().replace("/", "\\")
            p_dir = Path(p.get("path") or "").name.lower()

            if (
                search_name == p_name
                or search_name == p_slug
                or search_name == p_dir
                or search_name == p_rel
                or search_name in p_path
                or search_name in p_rel
                or search_name in p_name
                or p_name in search_name
                or (search_name.replace("-", "_") in p_slug.replace("-", "_"))
            ):
                proj_path = Path(p["path"])
                meta = {
                    "name": p.get("name", proj_path.name),
                    "slug": p.get("slug", proj_path.name),
                    "type": p.get("type", "Unknown"),
                    "path": str(proj_path),
                }
                meta_file = proj_path / ".project_meta.json"
                if meta_file.is_file():
                    try:
                        with open(meta_file, "r", encoding="utf-8-sig") as f:
                            meta = json.load(f)
                    except Exception:
                        pass
                return proj_path, meta

    # 3. Search through discovered projects
    discovered = discover_projects(root)
    for proj_path, meta in discovered:
        p_name = (meta.get("name") or "").lower()
        p_slug = (meta.get("slug") or "").lower()
        p_dir = proj_path.name.lower()
        try:
            p_rel = proj_path.relative_to(Path(root)).as_posix().lower()
        except Exception:
            p_rel = ""

        if search_name in (p_name, p_slug, p_dir, p_rel):
            return proj_path, meta

    # 4. Partial match fallback
    for proj_path, meta in discovered:
        p_name = (meta.get("name") or "").lower()
        p_slug = (meta.get("slug") or "").lower()
        p_dir = proj_path.name.lower()
        if search_name in p_name or search_name in p_slug or search_name in p_dir:
            return proj_path, meta

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Project '{project_name}' not found",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Request Models
# ──────────────────────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    category: str = Field(default="Video", description="Project category")
    client: Optional[str] = Field(default=None, max_length=50, description="Optional client name")
    destination_subpath: Optional[str] = Field(default=None, description="Optional custom subfolder path relative to projects root")
    date: Optional[str] = Field(default=None, description="Optional creation date (YYYY-MM-DD)")
    simple: bool = Field(default=False, description="Use minimal template")
    git: bool = Field(default=False, description="Initialize Git repository")


class CloneProjectRequest(BaseModel):
    url: str = Field(..., description="Git repository URL")
    category: str = Field(default="Code", description="Project category")
    client: Optional[str] = Field(default=None, description="Optional client name")
    name: Optional[str] = Field(default=None, description="Optional project name override")
    date: Optional[str] = Field(default=None, description="Optional YYYY-MM-DD date prefix")
    destination_subpath: Optional[str] = Field(default=None, description="Folder relative to the Projects root")


class InitProjectRequest(BaseModel):
    path: str = Field(..., description="Target directory path to initialize as a project")
    name: Optional[str] = Field(default=None, description="Optional project name override")
    category: Optional[str] = Field(default=None, description="Optional project category")
    client: Optional[str] = Field(default=None, description="Optional client name")
    confirm_external: bool = Field(default=False, description="Confirm adoption in place outside Projects")


class UpdatePathsRequest(BaseModel):
    paths: dict[str, str] = Field(..., description="Dictionary of path keys and new filesystem paths")
    move_files: bool = Field(default=False, description="Whether to migrate files to new location")


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="Updated project name")
    client: Optional[str] = Field(default=None, max_length=50, description="Updated client name")
    category: Optional[str] = Field(default=None, description="Updated category/type")
    description: Optional[str] = Field(default=None, description="Project summary description")
    tags: Optional[list[str]] = Field(default=None, description="Project tags")
    status: Optional[str] = Field(default=None, description="Project workflow status")
    custom_meta: Optional[dict[str, Any]] = Field(default=None, description="Additional custom metadata")
    sync_filesystem: bool = Field(default=False, description="Rename or move the physical project folder on disk")


class OpenPathRequest(BaseModel):
    path: Optional[str] = Field(default="", description="Path or project name to open with native OS handler")


class WindowsCleanupRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1, description="Selected Windows cleanup location IDs")


class WindowsCleanupToolRequest(BaseModel):
    tool: Literal["disk-cleanup", "storage-settings"]


class ReclaimProjectRequest(BaseModel):
    project: str = Field(..., description="Project name, slug, or relative path")
    targets: Optional[list[str]] = Field(default=None, description="Optional list of specific folder names or subpaths to reclaim")


class ReclaimBulkRequest(BaseModel):
    stale_only: bool = Field(default=False, description="Whether to restrict to stale projects (>90 days inactive)")
    days: int = Field(default=DEFAULT_STALE_DAYS, description="Threshold for stale inactivity in days")
    project_slugs: Optional[list[str]] = Field(default=None, description="Optional explicit list of project slugs or paths")


class CleanDownloadsRequest(BaseModel):
    folder: Optional[str] = Field(default=None, description="Optional target folder path to clean")


class SortExportsRequest(BaseModel):
    inbox_path: Optional[str] = Field(default=None, description="Optional custom inbox path")


class TransferRequest(BaseModel):
    source: str = Field(..., description="Source file or directory path")
    destination: str = Field(..., description="Destination directory or target path")
    move: bool = Field(default=False, description="Move if True, copy if False")
    overwrite: bool = Field(default=False, description="Whether to overwrite existing destination files")


class UpdateMountsRequest(BaseModel):
    mounts: list[dict[str, Any]] = Field(..., description="List of external drive or directory mounts")


class UpdateCategoriesRequest(BaseModel):
    categories: dict[str, Any] = Field(..., description="Full categories configuration dictionary")
    default_category: Optional[str] = Field(default=None, description="Default category name")


class DeletePathRequest(BaseModel):
    path: str = Field(..., description="Filesystem path of file or folder to delete")
    permanent: bool = Field(default=False, description="If True, delete permanently without Recycle Bin")
    recycle_bin: bool = Field(default=True, description="If True on Windows, move to Recycle Bin")


# ──────────────────────────────────────────────────────────────────────────────
# Core API Endpoints & Managed Lifecycle
# ──────────────────────────────────────────────────────────────────────────────

_LAST_HEARTBEAT_TIME = time.time()
_LEAVE_SIGNAL_TIME = 0.0
_MANAGED_MODE = os.environ.get("CREATIVEOS_MANAGED", "").strip().lower() in ("1", "true", "yes")
_WATCHDOG_STARTED = False

def _start_managed_watchdog():
    """Starts a background daemon thread that shuts down the server ONLY when the client window is explicitly closed."""
    global _WATCHDOG_STARTED
    if not _MANAGED_MODE or _WATCHDOG_STARTED:
        return
    _WATCHDOG_STARTED = True

    def _watchdog_loop():
        # Allow 30s initial grace period for browser window to launch
        time.sleep(30.0)
        while True:
            time.sleep(1.0)
            now = time.time()
            
            # ONLY exit if the browser window explicitly sent the leave beacon (on window close/page unload)
            # AND no new heartbeat arrived to contradict it
            if _LEAVE_SIGNAL_TIME > 0 and (now - _LEAVE_SIGNAL_TIME) >= 4.0 and _LAST_HEARTBEAT_TIME <= _LEAVE_SIGNAL_TIME:
                logger.info("CreativeOS GUI window was closed by user. Cleanly shutting down background server.")
                os._exit(0)

    t = threading.Thread(target=_watchdog_loop, daemon=True)
    t.start()

# Initialize watchdog on module load if managed mode is active
_start_managed_watchdog()


@app.get("/api/health")
def get_health() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": __version__,
        "projects_path": PROJECTS_PATH,
        "vault_path": VAULT_PATH,
        "exports_path": EXPORTS_PATH,
        "archive_path": ARCHIVE_PATH,
        "shuttle_path": SHUTTLE_PATH,
        "managed": _MANAGED_MODE,
        "windows_cleanup_cached": True,
        "windows_cleanup_jobs": True,
    }


@app.post("/api/system/heartbeat")
def post_heartbeat() -> dict[str, Any]:
    """Record alive ping from active GUI web client."""
    global _LAST_HEARTBEAT_TIME, _LEAVE_SIGNAL_TIME
    _LAST_HEARTBEAT_TIME = time.time()
    _LEAVE_SIGNAL_TIME = 0.0  # Clear any leave signal
    return {"status": "ok", "managed": _MANAGED_MODE}


@app.post("/api/system/leave")
def post_leave() -> dict[str, Any]:
    """Signal from client closing window to prompt clean shutdown in managed mode."""
    global _LEAVE_SIGNAL_TIME
    _LEAVE_SIGNAL_TIME = time.time()
    return {"status": "ok", "managed": _MANAGED_MODE}


# Server in-memory caching
_PROJECTS_CACHE: dict[str, Any] = {"data": None, "time": 0.0}
_CACHE_TTL_SECONDS = 5.0

def _invalidate_server_cache() -> None:
    """Clear memory caches when projects are mutated."""
    _PROJECTS_CACHE["data"] = None
    _PROJECTS_CACHE["time"] = 0.0


def _save_external_projects(paths: list[Path]) -> None:
    """Persist outside projects so GUI discovery and storage scans can find them."""
    config = _load_config().copy()
    config["external_projects"] = list(dict.fromkeys(str(path.resolve()) for path in paths))
    fd, temp_path = tempfile.mkstemp(dir=Path(CONFIG_PATH).parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        os.replace(temp_path, CONFIG_PATH)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    reload_config()


@app.get("/api/projects")
def get_projects(nocache: bool = False) -> list[dict[str, Any]]:
    """List all CreativeOS projects with metadata, status, and size metrics."""
    now = datetime.datetime.now().timestamp()
    if not nocache and _PROJECTS_CACHE["data"] is not None and (now - _PROJECTS_CACHE["time"]) < _CACHE_TTL_SECONDS:
        return _PROJECTS_CACHE["data"]

    cached_index = load_storage_index(projects_path=PROJECTS_PATH)
    cached_map: dict[str, Any] = {}
    stale_set = set()

    if cached_index:
        cached_map = {p["path"]: p for p in cached_index.get("projects", [])}
        stale_set = {p["path"] for p in stale_projects(cached_index, DEFAULT_STALE_DAYS)}

    discovered = discover_projects(PROJECTS_PATH)
    project_list: list[dict[str, Any]] = []

    for proj_path, metadata in discovered:
        path_str = str(proj_path)
        cat = metadata.get("type") or "Video"
        cached = cached_map.get(path_str)

        try:
            rel_path = proj_path.relative_to(Path(PROJECTS_PATH)).as_posix()
        except Exception:
            rel_path = path_str

        if cached:
            item = {
                **cached,
                "name": metadata.get("name") or cached.get("name") or proj_path.name,
                "type": cat,
                "client": metadata.get("client") or cached.get("client") or "None",
                "description": metadata.get("description") or cached.get("description") or "",
                "tags": metadata.get("tags") or cached.get("tags") or [],
                "relative_path": rel_path,
                "icon": get_category_icon(cat),
                "is_stale": path_str in stale_set,
                "status": "stale" if path_str in stale_set else "active",
            }
        else:
            created, created_source = _created_date(proj_path, metadata)
            item = {
                "name": metadata.get("name") or proj_path.name,
                "slug": metadata.get("slug") or proj_path.name,
                "type": cat,
                "client": metadata.get("client") or "None",
                "description": metadata.get("description") or "",
                "tags": metadata.get("tags") or [],
                "path": path_str,
                "relative_path": rel_path,
                "created": created,
                "created_source": created_source,
                "last_meaningful_update": None,
                "total_size": 0,
                "reclaimable_size": 0,
                "media_size": 0,
                "file_count": 0,
                "icon": get_category_icon(cat),
                "is_stale": False,
                "status": "active",
            }
        project_list.append(item)

    project_list.sort(key=lambda p: p.get("created") or "", reverse=True)
    _PROJECTS_CACHE["data"] = project_list
    _PROJECTS_CACHE["time"] = now
    return project_list



@app.post("/api/projects", status_code=status.HTTP_201_CREATED)
def create_project(req: CreateProjectRequest) -> dict[str, Any]:
    """Create a new CreativeOS project via existing logic."""
    try:
        meta = create_project_structure(
            name=req.name,
            category=req.category,
            client=req.client,
            destination_subpath=req.destination_subpath,
            date=req.date,
            simple=req.simple,
            git=req.git,
        )
        try:
            update_project_in_storage_index(meta["root"], metadata=meta, projects_path=PROJECTS_PATH)
        except Exception:
            pass
        _invalidate_server_cache()
        return {
            "status": "success",
            "message": f"Project '{req.name}' created successfully",
            "project": meta,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except FileExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Error creating project from GUI: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {e}",
        ) from e


@app.post("/api/projects/clone", status_code=status.HTTP_201_CREATED)
def clone_project(req: CloneProjectRequest) -> dict[str, Any]:
    """Clone an external Git repository into CreativeOS projects tree and adopt it."""
    url = req.url.strip()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository URL cannot be empty",
        )

    # Derive repository / project name
    if req.name and req.name.strip():
        repo_name_raw = req.name.strip()
    else:
        clean_url = url.rstrip("/\\")
        base_name = clean_url.split("/")[-1].split("\\")[-1]
        if base_name.endswith(".git"):
            base_name = base_name[:-4]
        repo_name_raw = base_name

    try:
        repo_name = sanitize_path_input(repo_name_raw, max_length=100)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid repository/project name: {e}",
        )

    try:
        url = validate_git_url(url)
        category = resolve_category_name(req.category or "Code")
        category_config = get_enabled_categories().get(category)
        if category_config is None:
            raise ValueError(f"Unknown or disabled category: {req.category}")
        phys_cat = validate_path_component(
            str(category_config.get("physical_folder") or get_category_folder(category)),
            max_length=100,
        )

        if req.client and req.client.strip() and req.client.strip().lower() not in ("none", "internal"):
            client_clean = validate_client_name(req.client.strip())
            target_parent = Path(PROJECTS_PATH) / "Clients" / client_clean
        else:
            target_parent = Path(PROJECTS_PATH) / phys_cat
        if req.destination_subpath:
            relative = Path(req.destination_subpath.strip().replace("\\", "/"))
            if relative.is_absolute() or not relative.parts or any(
                part in (".", "..") for part in relative.parts
            ):
                raise ValueError("Clone destination must be a folder relative to Projects")
            target_parent = Path(PROJECTS_PATH).joinpath(
                *(validate_path_component(part) for part in relative.parts)
            )
        date_str = validate_date(req.date) if req.date else get_date_slug()
    except (ValueError, argparse.ArgumentTypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    projects_root = Path(PROJECTS_PATH).resolve()
    slug = f"{date_str}_{repo_name.replace(' ', '_')}"
    dest_resolved = (target_parent / slug).resolve()
    if not dest_resolved.is_relative_to(projects_root):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clone destination must remain inside the projects directory",
        )
    if any((parent / ".project_meta.json").exists() for parent in dest_resolved.parents if parent.is_relative_to(projects_root)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clone destination cannot be nested inside another project",
        )

    if dest_resolved.exists() and any(dest_resolved.iterdir()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Target directory already exists and is not empty: {dest_resolved}",
        )

    dest_resolved.parent.mkdir(parents=True, exist_ok=True)

    try:
        proc = subprocess.run(
            ["git", "clone", "--", url, str(dest_resolved)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            err_msg = proc.stderr.strip() or proc.stdout.strip() or f"Process exited with code {proc.returncode}"
            logger.error(f"Git clone failed: {err_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Git clone failed: {err_msg}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Git clone command failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Git clone execution error: {e}",
        ) from e

    # Create 00_Notes / Idea.md if not present
    notes_dir = dest_resolved / "00_Notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    idea_file = notes_dir / "Idea.md"
    meta_client = req.client.strip() if req.client and req.client.strip().lower() not in ("none", "internal") else "None"

    if not idea_file.exists():
        try:
            with open(idea_file, "w", encoding="utf-8") as f:
                f.write(
                    f"---\n"
                    f"type: project\n"
                    f"category: {category}\n"
                    f"client: {meta_client}\n"
                    f"status: active\n"
                    f"created: {date_str}\n"
                    f"tags: [creativeos, git]\n"
                    f"---\n\n"
                    f"# {repo_name}\n\n"
                    f"Type: Cloned Repository\n"
                    f"Source: {url}\n"
                    f"Date: {date_str}\n"
                )
        except Exception as e:
            logger.warning(f"Could not create Idea.md: {e}")

    # Create .project_meta.json if not present
    meta_file = dest_resolved / ".project_meta.json"
    if not meta_file.exists():
        meta = {
            "name": repo_name,
            "slug": slug,
            "type": category,
            "created": date_str,
            "client": meta_client,
            "template": "git_clone",
            "repo_url": url,
            "root": str(dest_resolved),
            "status": "active",
            "last_updated": datetime.datetime.now().isoformat(),
        }
        try:
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=4)
        except Exception as e:
            logger.warning(f"Could not create .project_meta.json: {e}")
    else:
        try:
            with open(meta_file, "r", encoding="utf-8-sig") as f:
                meta = json.load(f)
        except Exception:
            meta = {
                "name": repo_name,
                "slug": repo_name,
                "type": category,
                "root": str(dest_resolved),
            }

    try:
        update_project_in_storage_index(dest_resolved, metadata=meta, projects_path=PROJECTS_PATH)
    except Exception:
        pass

    _invalidate_server_cache()

    return {
        "status": "success",
        "message": f"Cloned repository '{repo_name}' successfully",
        "project": meta,
        "path": str(dest_resolved),
    }


@app.post("/api/projects/init")
def init_project(req: InitProjectRequest) -> dict[str, Any]:
    """Adopt an existing folder as a CreativeOS project."""
    submitted = Path(req.path.strip())
    if submitted.is_absolute():
        target_path = submitted.resolve()
    else:
        relative = Path(req.path.strip().replace("\\", "/"))
        if relative.parts and relative.parts[0].casefold() in ("01_projects", Path(PROJECTS_PATH).name.casefold()):
            relative = Path(*relative.parts[1:])
        target_path = (Path(PROJECTS_PATH) / relative).resolve()
    outside_projects = not target_path.is_relative_to(Path(PROJECTS_PATH).resolve())
    if outside_projects:
        # Validate the resolved target, including relative paths through allowed mounts.
        system_dirs = [Path(os.environ[key]).resolve() for key in (
            "SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"
        ) if os.environ.get(key)]
        if target_path == Path(target_path.anchor) or target_path == Path.home().resolve() or any(
            target_path.is_relative_to(directory) or directory.is_relative_to(target_path)
            for directory in system_dirs
        ):
            raise HTTPException(status_code=403, detail="Cannot adopt a protected system directory")
    if not (outside_projects and req.confirm_external and submitted.is_absolute()):
        target_path = _check_path_allowed(target_path)

    if _is_allowed_root(target_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot initialize a filesystem root as a project",
        )
    if outside_projects and not req.confirm_external:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm adoption in place outside the Projects directory",
        )

    if outside_projects and any(
        target_path != registered and (
            target_path.is_relative_to(registered) or registered.is_relative_to(target_path)
        ) for registered in external_project_paths()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An adopted outside project cannot contain or be inside another adopted project",
        )

    if not target_path.exists() or not target_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target directory does not exist or is not a directory: {req.path}",
        )

    meta_file = target_path / ".project_meta.json"
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8-sig") as f:
                existing_meta = json.load(f)
        except (OSError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Cannot read existing project metadata: {e}") from e
        if not isinstance(existing_meta, dict):
            raise HTTPException(status_code=400, detail="Existing project metadata must be an object")
        if outside_projects:
            try:
                _save_external_projects([*external_project_paths(), target_path])
            except OSError as e:
                raise HTTPException(status_code=500, detail=f"Could not register existing project: {e}") from e
            try:
                update_project_in_storage_index(target_path, metadata=existing_meta, projects_path=PROJECTS_PATH)
            except Exception:
                pass
            _invalidate_server_cache()
        return {
            "status": "success",
            "message": f"Folder is already an initialized project: '{existing_meta.get('name', target_path.name)}'",
            "project": existing_meta,
            "path": str(target_path),
        }

    smart_ts = get_smart_date(str(target_path))
    date_str = datetime.datetime.fromtimestamp(smart_ts).strftime("%Y-%m-%d")

    try:
        project_name = sanitize_path_input(
            req.name.strip() if req.name and req.name.strip() else target_path.name,
            max_length=100,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid project name: {e}",
        ) from e

    norm_path = str(target_path).replace("\\", "/")
    parts = norm_path.split("/")

    # Infer client
    if req.client and req.client.strip() and req.client.strip().lower() not in ("none", "internal"):
        try:
            meta_client = validate_client_name(req.client.strip())
        except argparse.ArgumentTypeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e
    else:
        meta_client = "None"
        if "Clients" in parts:
            try:
                meta_client = parts[parts.index("Clients") + 1]
            except Exception:
                pass

    # Infer category
    if req.category and req.category.strip():
        category = resolve_category_name(req.category.strip())
        if category not in get_enabled_categories():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown or disabled category: {req.category}",
            )
    else:
        category = "Video"
        for cat_key in ["Code", "Music", "Audio", "AI", "Design", "Photo", "Writing", "Podcast", "Course"]:
            if cat_key in parts:
                category = resolve_category_name(cat_key)
                break

    slug = f"{date_str}_{project_name.replace(' ', '_')}"

    # Create 00_Notes / Idea.md
    notes_dir = target_path / "00_Notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    idea_file = notes_dir / "Idea.md"
    if not idea_file.exists():
        try:
            with open(idea_file, "w", encoding="utf-8") as f:
                f.write(
                    f"---\n"
                    f"type: project\n"
                    f"category: {category}\n"
                    f"client: {meta_client}\n"
                    f"status: active\n"
                    f"created: {date_str}\n"
                    f"tags: [creativeos]\n"
                    f"---\n\n"
                    f"# {project_name}\n"
                )
        except Exception as e:
            logger.warning(f"Could not create Idea.md: {e}")

    meta = {
        "name": project_name,
        "slug": slug,
        "type": category,
        "created": date_str,
        "client": meta_client,
        "template": "adopted_existing",
        "root": str(target_path),
        "status": "active",
        "last_updated": datetime.datetime.now().isoformat(),
    }

    try:
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write metadata file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create .project_meta.json: {e}",
        ) from e

    if outside_projects:
        _save_external_projects([*external_project_paths(), target_path])

    try:
        update_project_in_storage_index(target_path, metadata=meta, projects_path=PROJECTS_PATH)
    except Exception:
        pass

    _invalidate_server_cache()

    return {
        "status": "success",
        "message": f"Project '{project_name}' adopted successfully",
        "project": meta,
        "path": str(target_path),
    }


def _compute_new_project_path(current_proj_path: Path, new_name: str, new_client: str, new_category: str) -> tuple[Path, str]:
    """Compute target project directory and slug based on updated name, client, and category."""
    original_dirname = current_proj_path.name
    date_prefix = ""
    if len(original_dirname) >= 11 and original_dirname[4] == "-" and original_dirname[7] == "-" and original_dirname[10] == "_":
        date_prefix = original_dirname[:11]

    clean_name = sanitize_path_input(new_name, max_length=100)
    slugified_name = clean_name.replace(" ", "_")
    new_dir_name = f"{date_prefix}{slugified_name}" if date_prefix else slugified_name

    # Extract any intermediate subfolders relative to the old client/category parent
    intermediate_parts: list[str] = []
    try:
        rel_parts = list(current_proj_path.relative_to(Path(PROJECTS_PATH)).parts)
        if len(rel_parts) > 1 and rel_parts[0] == "Clients":
            if len(rel_parts) > 3:
                intermediate_parts = list(rel_parts[2:-1])
        elif len(rel_parts) > 2:
            intermediate_parts = list(rel_parts[1:-1])
    except Exception:
        intermediate_parts = []

    if new_client and new_client.lower() != "none" and new_client.lower() != "internal":
        clean_client = validate_client_name(new_client.strip())
        target_parent = Path(PROJECTS_PATH) / "Clients" / clean_client
    else:
        category = resolve_category_name(new_category.strip() or "Video")
        category_config = get_enabled_categories().get(category)
        if category_config is None:
            raise ValueError(f"Unknown or disabled category: {new_category}")
        physical_folder = validate_path_component(
            str(category_config.get("physical_folder") or get_category_folder(category)),
            max_length=100,
        )
        target_parent = Path(PROJECTS_PATH) / physical_folder

    if intermediate_parts:
        target_parent = target_parent.joinpath(*intermediate_parts)

    target_path = target_parent / new_dir_name
    return target_path, slugified_name


@app.put("/api/projects/{project_name:path}")
def update_project(project_name: str, req: UpdateProjectRequest) -> dict[str, Any]:
    """Update project metadata (.project_meta.json) and optionally sync filesystem on disk."""
    proj_path, meta = _find_project_dir(project_name)
    meta_file = proj_path / ".project_meta.json"

    try:
        if req.name is not None:
            meta["name"] = sanitize_path_input(req.name, max_length=100)

        if req.client is not None:
            client_clean = req.client.strip()
            if client_clean and client_clean.lower() not in ("none", "internal"):
                meta["client"] = validate_client_name(client_clean)
            else:
                meta["client"] = "None"

        if req.category is not None:
            category = resolve_category_name(req.category.strip())
            if category not in get_enabled_categories():
                raise ValueError(f"Unknown or disabled category: {req.category}")
            meta["type"] = category
    except (ValueError, argparse.ArgumentTypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    if req.description is not None:
        meta["description"] = req.description.strip()

    if req.tags is not None:
        meta["tags"] = [str(t).strip() for t in req.tags if str(t).strip()]

    if req.status is not None:
        meta["status"] = req.status.strip()

    if req.custom_meta is not None and isinstance(req.custom_meta, dict):
        for k, v in req.custom_meta.items():
            meta[k] = v

    meta["last_updated"] = datetime.datetime.now().isoformat()

    # Move or rename directory on disk if requested
    moved_disk = False
    external_project = proj_path in external_project_paths()
    if req.sync_filesystem:
        try:
            if external_project:
                prefix = proj_path.name[:11] if len(proj_path.name) >= 11 and proj_path.name[4:5] == "-" and proj_path.name[10:11] == "_" else ""
                name_slug = sanitize_path_input(meta.get("name", project_name)).replace(" ", "_")
                target_path = proj_path.with_name(f"{prefix}{name_slug}")
                new_slug = f"{meta.get('created')}_{name_slug}" if meta.get("created") else name_slug
            else:
                target_path, new_slug = _compute_new_project_path(
                    proj_path,
                    new_name=meta.get("name", project_name),
                    new_client=meta.get("client", "None"),
                    new_category=meta.get("type", "Video"),
                )
        except (ValueError, argparse.ArgumentTypeError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e
        target_resolved = target_path.resolve()
        current_resolved = proj_path.resolve()
        projects_root = Path(PROJECTS_PATH).resolve()
        if not external_project and not target_resolved.is_relative_to(projects_root):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Updated project path must remain inside the projects directory",
            )

        if target_resolved != current_resolved:
            if target_resolved.exists():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Target folder already exists on disk: {target_resolved}",
                )

            target_resolved.parent.mkdir(parents=True, exist_ok=True)
            old_parent = current_resolved.parent
            try:
                shutil.move(str(current_resolved), str(target_resolved))
                proj_path = target_resolved
                meta_file = target_resolved / ".project_meta.json"
                meta["slug"] = new_slug
                moved_disk = True

                # Clean up empty parent hierarchy left behind
                try:
                    curr_p = old_parent
                    while not external_project and curr_p != Path(PROJECTS_PATH) and curr_p != (Path(PROJECTS_PATH) / "Clients") and curr_p.exists():
                        if not any(curr_p.iterdir()):
                            curr_p.rmdir()
                            curr_p = curr_p.parent
                        else:
                            break
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to move project on disk: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to move project folder on disk: {e}",
                ) from e

    try:
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to write metadata for {project_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update metadata file: {e}",
        ) from e

    if external_project and moved_disk:
        _save_external_projects([
            proj_path if path == current_resolved else path for path in external_project_paths()
        ])

    try:
        rel_path = proj_path.relative_to(Path(PROJECTS_PATH)).as_posix()
    except ValueError:
        rel_path = str(proj_path)

    try:
        if moved_disk:
            remove_project_from_storage_index(current_resolved, projects_path=PROJECTS_PATH)
        update_project_in_storage_index(proj_path, metadata=meta, projects_path=PROJECTS_PATH)
    except Exception:
        pass

    _invalidate_server_cache()

    return {
        "status": "success",
        "message": f"Project '{meta.get('name', project_name)}' updated{' and moved on disk' if moved_disk else ''} successfully",
        "project": {
            **meta,
            "path": str(proj_path),
            "relative_path": rel_path,
        },
        "moved": moved_disk,
        "new_path": str(proj_path),
    }


@app.post("/api/projects/{name:path}/export-folder")
def create_project_export_folder(name: str) -> dict[str, Any]:
    """Resolve project directory and locate/create 02_Exports/YYYY/MM/<project_name> with Video/, Thumbnail/, and Audio/ subfolders based on project creation date."""
    proj_path, meta = _find_project_dir(name)
    try:
        project_slug = validate_path_component(
            str(meta.get("slug") or meta.get("name") or proj_path.name),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid project export name: {e}",
        ) from e

    base_exports = Path(EXPORTS_PATH).resolve()

    # 1. Check if an export folder already exists for this project under 02_Exports/
    existing_export = None
    if base_exports.exists():
        try:
            for month_dir in base_exports.glob("*/*"):
                candidate = month_dir / project_slug
                if candidate.is_dir():
                    existing_export = candidate
                    break
            if not existing_export:
                for month_dir in base_exports.glob("*/*/*"):
                    candidate = month_dir / project_slug
                    if candidate.is_dir():
                        existing_export = candidate
                        break
        except Exception:
            existing_export = None

    if existing_export:
        export_dir = existing_export
    else:
        # 2. Determine target year/month from project creation date
        created_str, _ = _created_date(proj_path, meta)
        target_year = None
        target_month_num = None
        target_month_name = None

        if created_str and created_str != "Unknown":
            try:
                parts = created_str.split("-")
                if len(parts) >= 2:
                    y = int(parts[0])
                    m = int(parts[1])
                    d_obj = datetime.date(y, m, 1)
                    target_year = d_obj.strftime("%Y")
                    target_month_num = d_obj.strftime("%m")
                    target_month_name = d_obj.strftime("%B")
            except Exception:
                pass

        if not target_year:
            now = datetime.datetime.now()
            target_year = now.strftime("%Y")
            target_month_num = now.strftime("%m")
            target_month_name = now.strftime("%B")

        month_full = f"{target_month_num} - {target_month_name}"

        candidate_named = base_exports / target_year / month_full / project_slug
        candidate_num = base_exports / target_year / target_month_num / project_slug

        if (base_exports / target_year / month_full).exists():
            export_dir = candidate_named
        elif (base_exports / target_year / target_month_num).exists():
            export_dir = candidate_num
        else:
            export_dir = candidate_named

    export_dir = export_dir.resolve()
    if not export_dir.is_relative_to(base_exports):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Export destination must remain inside the exports directory",
        )

    subfolders = ["Video", "Thumbnail", "Audio"]
    for sub in subfolders:
        (export_dir / sub).mkdir(parents=True, exist_ok=True)

    return {
        "status": "success",
        "message": f"Export folder ready for project '{meta.get('name', name)}'",
        "project": meta.get("name", name),
        "export_path": str(export_dir),
        "subfolders": subfolders,
    }


# ──────────────────────────────────────────────────────────────────────────────
# File Explorer Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/fs/list")
def list_fs(path: Optional[str] = None) -> dict[str, Any]:
    """List directory contents with security boundary checks, folders first."""
    if not path or path.strip() in ("", "."):
        target_dir = Path(PROJECTS_PATH).resolve()
    else:
        p_str = path.strip()
        p_lower = p_str.lower()
        if p_lower == "desktop":
            target_dir = (Path.home() / "Desktop").resolve()
        elif p_lower == "downloads":
            if DOWNLOADS_PATH and Path(DOWNLOADS_PATH).exists():
                target_dir = Path(DOWNLOADS_PATH).resolve()
            else:
                target_dir = (Path.home() / "Downloads").resolve()
        elif p_lower == "documents":
            target_dir = (Path.home() / "Documents").resolve()
        elif p_lower == "videos":
            target_dir = (Path.home() / "Videos").resolve()
        elif p_lower == "pictures":
            target_dir = (Path.home() / "Pictures").resolve()
        elif p_lower in ("00_notes", "00-notes"):
            target_dir = Path(VAULT_PATH).resolve()
        elif p_lower in ("02_exports", "02-exports"):
            target_dir = Path(EXPORTS_PATH).resolve()
        else:
            p = Path(p_str)
            if not p.is_absolute():
                target_dir = (Path(PROJECTS_PATH) / p).resolve()
            else:
                target_dir = p.resolve()

    target_dir = _check_path_allowed(target_dir)

    if not target_dir.exists():
        try:
            rel = target_dir.relative_to(Path(PROJECTS_PATH)).as_posix()
            return {
                "current_path": str(target_dir),
                "relative_path": rel,
                "parent_path": str(target_dir.parent) if target_dir != Path(PROJECTS_PATH) else None,
                "is_root": False,
                "entries": [],
                "count": 0,
                "exists": False,
            }
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Path not found: {path}")

    if not target_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Path is not a directory: {path}")

    entries = []
    try:
        with os.scandir(target_dir) as it:
            for entry in it:
                if entry.name.startswith(".") and entry.name != ".project_meta.json":
                    continue
                try:
                    stat_res = entry.stat()
                    is_dir = entry.is_dir(follow_symlinks=False)
                    ext = Path(entry.name).suffix.lower() if not is_dir else ""
                    mtime_iso = datetime.datetime.fromtimestamp(stat_res.st_mtime).isoformat()
                    size_bytes = stat_res.st_size if not is_dir else 0

                    entries.append({
                        "name": entry.name,
                        "path": str(Path(entry.path).resolve()),
                        "is_dir": is_dir,
                        "size": size_bytes,
                        "type": "directory" if is_dir else (ext[1:] if ext else "file"),
                        "extension": ext,
                        "modified": mtime_iso,
                    })
                except (OSError, PermissionError):
                    continue
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission denied: {e}")

    # Sort folders first (alphabetical), then files (alphabetical)
    entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

    # Determine parent path if within allowed bounds
    parent_path = None
    if target_dir.parent != target_dir:
        try:
            _check_path_allowed(target_dir.parent)
            parent_path = str(target_dir.parent)
        except HTTPException:
            parent_path = None

    # Calculate friendly relative path
    rel_display = target_dir.name
    for root in _get_allowed_roots():
        try:
            rel = target_dir.relative_to(root)
            rel_display = rel.as_posix() if str(rel) != "." else root.name
            break
        except Exception:
            pass

    return {
        "current_path": str(target_dir),
        "name": target_dir.name or str(target_dir),
        "relative_display": rel_display,
        "parent_path": parent_path,
        "entries": entries,
    }


@app.post("/api/fs/open")
def open_fs_path(req: OpenPathRequest) -> dict[str, Any]:
    """Open a file or directory using the OS native handler."""
    p_str = (req.path or "").strip()
    if not p_str:
        target = Path(PROJECTS_PATH).resolve()
    else:
        p = Path(p_str)
        if p.is_absolute():
            target = p.resolve()
        else:
            # 1. Try relative to PROJECTS_PATH
            candidate1 = (Path(PROJECTS_PATH) / p).resolve()
            # 2. Try relative to ROOT_PATH
            candidate2 = (Path(ROOT_PATH) / p).resolve()
            if candidate1.exists():
                target = candidate1
            elif candidate2.exists():
                target = candidate2
            else:
                # 3. Try project name/slug lookup
                try:
                    proj_dir, _ = _find_project_dir(p_str)
                    target = proj_dir.resolve()
                except Exception:
                    target = candidate1

    target = _check_path_allowed(target)

    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Path does not exist: {req.path}")

    norm_target = os.path.normpath(str(target))

    try:
        if sys.platform == "win32":
            try:
                os.startfile(norm_target)
            except Exception as win_err:
                logger.warning(f"os.startfile fallback for {norm_target}: {win_err}")
                if target.is_dir():
                    subprocess.Popen(["explorer", norm_target])
                else:
                    subprocess.Popen(["explorer", f"/select,{norm_target}"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", norm_target])
        else:
            subprocess.Popen(["xdg-open", norm_target])

        return {
            "status": "success",
            "message": f"Opened '{target.name}' natively",
            "path": norm_target,
        }
    except Exception as e:
        logger.error(f"Failed to open native handler for {target}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not open path natively: {e}",
        ) from e


def _resolve_file_target(path: str) -> Path:
    """Helper to resolve and validate a file path strictly within allowed boundaries."""
    if not path or path.strip() in ("", "."):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path parameter is required")
    p_str = path.strip()
    p = Path(p_str)
    if p.is_absolute():
        target = p.resolve()
    else:
        candidate1 = (Path(PROJECTS_PATH) / p).resolve()
        candidate2 = (Path(ROOT_PATH) / p).resolve()
        if candidate1.exists():
            target = candidate1
        elif candidate2.exists():
            target = candidate2
        else:
            target = candidate1

    target = _check_path_allowed(target)
    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Path not found: {path}")
    return target


@app.get("/api/fs/raw")
def get_fs_raw(path: str) -> FileResponse:
    """Serve raw file content for media streaming (video/audio) and image preview."""
    target = _resolve_file_target(path)
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Target is not a file: {path}")
    return FileResponse(target)


@app.get("/api/fs/content")
def get_fs_content(path: str, max_bytes: int = 1_000_000) -> dict[str, Any]:
    """Retrieve text/markdown/json/code content for inline previewing."""
    target = _resolve_file_target(path)
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Target is not a file: {path}")

    stat_res = target.stat()
    size = stat_res.st_size
    mtime_iso = datetime.datetime.fromtimestamp(stat_res.st_mtime).isoformat()

    try:
        if size > max_bytes:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_bytes)
            truncated = True
        else:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            truncated = False
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Could not read text content: {e}")

    return {
        "path": str(target),
        "name": target.name,
        "size": size,
        "type": target.suffix.lower().lstrip(".") or "txt",
        "extension": target.suffix.lower(),
        "modified": mtime_iso,
        "content": content,
        "lines": content.count("\n") + 1 if content else 0,
        "truncated": truncated,
    }


@app.post("/api/fs/transfer")
def transfer_fs(req: TransferRequest) -> dict[str, Any]:
    """Copy or move files safely across allowed filesystem locations."""
    if not req.source.strip() or not req.destination.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination paths are required",
        )

    src_resolved = Path(req.source.strip()).resolve()
    dst_resolved = Path(req.destination.strip()).resolve()

    src_safe = _check_path_allowed(src_resolved)
    dst_safe = _check_path_allowed(dst_resolved)

    if not src_safe.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source path does not exist: {src_safe}",
        )
    if _is_allowed_root(src_safe):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer a root system/storage directory",
        )

    # Determine final destination target
    if dst_safe.is_dir():
        final_dest = dst_safe / src_safe.name
    else:
        final_dest = dst_safe

    if final_dest.resolve() == src_safe.resolve():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination cannot be identical",
        )

    # Handle collisions if not overwriting
    if final_dest.exists() and not req.overwrite:
        stem = final_dest.stem if final_dest.is_file() else final_dest.name
        suffix = final_dest.suffix if final_dest.is_file() else ""
        counter = 1
        while final_dest.exists():
            counter += 1
            final_dest = final_dest.parent / f"{stem}_copy_{counter}{suffix}"

    final_dest = _check_path_allowed(final_dest)
    if src_safe.is_dir() and src_safe in final_dest.parents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer a directory into itself",
        )
    if req.move and req.overwrite and src_safe.is_dir() and final_dest.is_dir():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot move onto an existing directory; choose copy with overwrite or another destination",
        )

    try:
        final_dest.parent.mkdir(parents=True, exist_ok=True)
        if req.move:
            registered = external_project_paths()
            relocated = {
                path: final_dest / path.relative_to(src_safe)
                for path in registered if path.is_relative_to(src_safe)
            }
            shutil.move(str(src_safe), str(final_dest))
            if relocated:
                try:
                    updated_paths = [relocated.get(path, path) for path in registered]
                    _save_external_projects([
                        path for path in updated_paths
                        if not path.is_relative_to(Path(PROJECTS_PATH).resolve())
                    ])
                except Exception:
                    shutil.move(str(final_dest), str(src_safe))
                    raise
                try:
                    for path, new_path in relocated.items():
                        remove_project_from_storage_index(path, projects_path=PROJECTS_PATH)
                        update_project_in_storage_index(new_path, projects_path=PROJECTS_PATH)
                except OSError as e:
                    logger.warning("Transferred project but could not refresh storage index: %s", e)
            action = "moved"
        else:
            if src_safe.is_dir():
                shutil.copytree(str(src_safe), str(final_dest), dirs_exist_ok=req.overwrite)
            else:
                shutil.copy2(str(src_safe), str(final_dest))
            action = "copied"

        _invalidate_server_cache()

        return {
            "status": "success",
            "message": f"Successfully {action} '{src_safe.name}' to '{final_dest}'",
            "action": action,
            "source": str(src_safe),
            "destination": str(final_dest),
        }
    except Exception as e:
        logger.error(f"Transfer error from {src_safe} to {final_dest}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transfer failed: {e}",
        ) from e


@app.post("/api/fs/delete")
def delete_filesystem_item(req: DeletePathRequest) -> dict[str, Any]:
    """Delete a file or folder safely (default sends to Windows Recycle Bin)."""
    target = _check_path_allowed(req.path)
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target path does not exist: {target}",
        )

    resolved = target.resolve()
    if _is_allowed_root(resolved):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete root system/storage directory",
        )

    is_dir = target.is_dir()
    name = target.name
    path_str = str(resolved)

    try:
        recycled = False
        if not req.permanent and req.recycle_bin:
            if sys.platform != "win32":
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="Recycle Bin deletion is only supported on Windows",
                )
            method = "DeleteDirectory" if is_dir else "DeleteFile"
            escaped_path = path_str.replace("'", "''")
            cmd = f"Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::{method}('{escaped_path}', 'OnlyErrorDialogs', 'SendToRecycleBin')"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                error = res.stderr.strip() or res.stdout.strip() or "Unknown PowerShell error"
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Could not move '{name}' to the Recycle Bin: {error}",
                )
            recycled = True
        else:
            if is_dir:
                if not robust_rmtree(path_str):
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Could not completely delete directory: {path_str}",
                    )
            else:
                os.remove(path_str)

        # If it was a project in storage index, remove it
        try:
            remove_project_from_storage_index(path_str)
        except Exception:
            pass

        return {
            "status": "success",
            "message": f"Successfully deleted '{name}'",
            "path": path_str,
            "is_dir": is_dir,
            "recycled": recycled,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete '{name}' at {path_str}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete '{name}': {e}",
        ) from e


# ──────────────────────────────────────────────────────────────────────────────
# Travel, Archive & Resurrect Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/projects/archived")
def get_archived_projects() -> list[dict[str, Any]]:
    """List all archived projects located in ARCHIVE_PATH."""
    archive_root = ARCHIVE_PATH
    if not archive_root or not os.path.exists(archive_root):
        return []

    discovered = discover_projects(archive_root)
    archived_list: list[dict[str, Any]] = []

    for proj_path, metadata in discovered:
        path_str = str(proj_path)
        cat = metadata.get("type") or "Video"
        try:
            rel_path = proj_path.relative_to(Path(archive_root)).as_posix()
        except Exception:
            rel_path = proj_path.name

        created, created_source = _created_date(proj_path, metadata)
        archived_list.append({
            "name": metadata.get("name") or proj_path.name,
            "slug": metadata.get("slug") or proj_path.name,
            "type": cat,
            "client": metadata.get("client") or "None",
            "description": metadata.get("description") or "",
            "path": path_str,
            "relative_path": rel_path,
            "created": created,
            "created_source": created_source,
            "icon": get_category_icon(cat),
            "is_archived": True,
        })

    archived_list.sort(key=lambda p: p.get("created") or "", reverse=True)
    return archived_list


@app.post("/api/projects/{project_name:path}/travel")
def travel_project(project_name: str) -> dict[str, Any]:
    """Copy active project to configured Shuttle Drive."""
    proj_path, meta = _find_project_dir(project_name)
    shuttle_root = SHUTTLE_PATH
    if not shuttle_root:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shuttle path is not configured in config.json",
        )

    if not os.path.exists(shuttle_root):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shuttle Drive path not found at: {shuttle_root}. Please connect the external drive.",
        )

    try:
        rel_path = proj_path.relative_to(Path(PROJECTS_PATH)).as_posix()
    except ValueError:
        path_id = hashlib.sha256(str(proj_path).encode("utf-8")).hexdigest()[:10]
        rel_path = f"External/{proj_path.name}-{path_id}"

    dest_path = Path(shuttle_root) / "Projects" / rel_path
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copytree(proj_path, dest_path, dirs_exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = dest_path / "_TRAVEL_LOG.txt"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"Synced from Desktop at: {timestamp}\n")
        return {
            "status": "success",
            "message": f"Project ready for travel at {dest_path}",
            "dest_path": str(dest_path),
            "project": meta,
        }
    except Exception as e:
        logger.error(f"Error copying to shuttle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to copy project to Shuttle: {e}",
        ) from e


@app.post("/api/projects/{project_name:path}/archive")
def archive_project(project_name: str) -> dict[str, Any]:
    """Move active project from Projects tree to Cold Archive."""
    proj_path, meta = _find_project_dir(project_name)
    archive_root = ARCHIVE_PATH
    if not archive_root:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archive path is not configured in config.json",
        )

    try:
        os.makedirs(archive_root, exist_ok=True)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cannot access or create Archive directory: {e}",
        ) from e

    category = meta.get("type", "Video")
    client = meta.get("client")
    try:
        if client and client != "None":
            dest_dir = Path(archive_root) / "Clients" / validate_path_component(client) / proj_path.name
        else:
            dest_dir = Path(archive_root) / validate_path_component(category) / proj_path.name
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    dest_dir.parent.mkdir(parents=True, exist_ok=True)

    if dest_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project already exists in Archive at: {dest_dir}",
        )

    try:
        shutil.copytree(proj_path, dest_dir)
        removed_source = robust_rmtree(str(proj_path))
        if not removed_source:
            logger.warning(f"Could not cleanly remove source project {proj_path} after copy to archive.")
        elif proj_path in external_project_paths():
            _save_external_projects([p for p in external_project_paths() if p != proj_path])

        try:
            if removed_source:
                remove_project_from_storage_index(proj_path, projects_path=PROJECTS_PATH)
        except Exception:
            pass

        _invalidate_server_cache()
        return {
            "status": "success",
            "message": f"Project '{meta.get('name', project_name)}' moved to Archive",
            "archive_path": str(dest_dir),
            "project": meta,
        }
    except Exception as e:
        logger.error(f"Error archiving project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Archiving failed: {e}",
        ) from e


@app.post("/api/projects/{project_name:path}/resurrect")
def resurrect_project(project_name: str) -> dict[str, Any]:
    """Restore an archived project from Archive back to active Projects tree."""
    archive_root = ARCHIVE_PATH
    if not archive_root or not os.path.exists(archive_root):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Archive path not found at: {archive_root}",
        )

    proj_path, meta = _find_project_dir(project_name, search_root=archive_root)

    category = meta.get("type", "Video")
    client = meta.get("client")
    if client and client != "None":
        try:
            dest_root = Path(PROJECTS_PATH) / "Clients" / validate_path_component(client)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    else:
        cat_lower = category.lower()
        if cat_lower in ["web", "code", "dev"]:
            dest_cat = "Code"
        elif cat_lower in ["music", "audio"]:
            dest_cat = "Music"
        elif cat_lower == "ai":
            dest_cat = "AI"
        elif cat_lower == "design":
            dest_cat = "Design"
        elif cat_lower == "photo":
            dest_cat = "Photo"
        elif cat_lower == "writing":
            dest_cat = "Writing"
        elif cat_lower == "podcast":
            dest_cat = "Podcast"
        elif cat_lower == "course":
            dest_cat = "Course"
        else:
            dest_cat = "Video"
        dest_root = Path(PROJECTS_PATH) / dest_cat

    dest_root.mkdir(parents=True, exist_ok=True)
    final_dest = dest_root / proj_path.name

    if final_dest.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project already exists in Active Projects at: {final_dest}",
        )

    try:
        shutil.copytree(proj_path, final_dest)
        if not robust_rmtree(str(proj_path)):
            logger.warning(f"Could not completely remove {proj_path} from archive after restoring.")

        try:
            update_project_in_storage_index(final_dest, metadata=meta, projects_path=PROJECTS_PATH)
        except Exception:
            pass

        _invalidate_server_cache()
        return {
            "status": "success",
            "message": f"Project '{meta.get('name', project_name)}' resurrected successfully to {final_dest}",
            "path": str(final_dest),
            "project": meta,
        }
    except Exception as e:
        logger.error(f"Error resurrecting project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resurrection failed: {e}",
        ) from e


# ──────────────────────────────────────────────────────────────────────────────
# Storage & Config Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/storage")
def get_storage() -> dict[str, Any]:
    """Retrieve current storage inventory and statistics."""
    index = load_storage_index(projects_path=PROJECTS_PATH)
    if index is None:
        projects = get_projects()
        index = {
            "version": 1,
            "scanned_at": None,
            "projects_path": PROJECTS_PATH,
            "project_count": len(projects),
            "total_size": sum(p.get("total_size", 0) for p in projects),
            "reclaimable_size": sum(p.get("reclaimable_size", 0) for p in projects),
            "media_size": sum(p.get("media_size", 0) for p in projects),
            "projects": projects,
        }

    stale_list = stale_projects(index, DEFAULT_STALE_DAYS)
    return {
        **index,
        "stale_count": len(stale_list),
        "stale_days_threshold": DEFAULT_STALE_DAYS,
        "windows_cleanup": load_windows_cleanup_index(),
    }


@app.post("/api/storage/refresh")
def refresh_storage() -> dict[str, Any]:
    """Trigger a full rescan of project storage and return updated inventory."""
    updated = refresh_storage_index()
    stale_list = stale_projects(updated, DEFAULT_STALE_DAYS)
    try:
        windows_cleanup = refresh_windows_cleanup_index()
        windows_error = None
    except OSError as exc:
        logger.warning("Windows cleanup inventory could not be refreshed: %s", exc)
        windows_cleanup = load_windows_cleanup_index()
        windows_error = "Windows cleanup scan failed; showing the previous snapshot."
    return {
        **updated,
        "stale_count": len(stale_list),
        "stale_days_threshold": DEFAULT_STALE_DAYS,
        "windows_cleanup": windows_cleanup,
        "windows_cleanup_warning": windows_error,
    }


@app.get("/api/storage/windows-cleanup")
def get_windows_cleanup() -> dict[str, Any]:
    """Return the last saved scan instantly; use /refresh for a live scan."""
    return load_windows_cleanup_index()


@app.post("/api/storage/windows-cleanup/refresh")
def refresh_windows_cleanup() -> dict[str, Any]:
    """Update the Windows cleanup snapshot on demand."""
    return refresh_windows_cleanup_index()


@app.post("/api/storage/windows-cleanup/clear")
def clear_windows_cleanup_endpoint(req: WindowsCleanupRequest) -> dict[str, Any]:
    """Keep the original synchronous route for existing clients."""
    global _WINDOWS_CLEANUP_DIRECT_RUNNING
    with _WINDOWS_CLEANUP_JOB_LOCK:
        if _WINDOWS_CLEANUP_DIRECT_RUNNING or (
            _WINDOWS_CLEANUP_JOB and _WINDOWS_CLEANUP_JOB["status"] == "running"
        ):
            raise HTTPException(status_code=409, detail="Windows cleanup is already running")
        _WINDOWS_CLEANUP_DIRECT_RUNNING = True
    try:
        try:
            result = clear_windows_cleanup(req.ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # Do not turn a completed deletion into an HTTP error if saving fails.
        try:
            result["inventory"] = refresh_windows_cleanup_index()
        except OSError as exc:
            logger.warning("Windows cleanup inventory could not be saved after deletion: %s", exc)
            result["cache_error"] = "Could not save updated sizes; scan again to refresh them."
        return result
    finally:
        with _WINDOWS_CLEANUP_JOB_LOCK:
            _WINDOWS_CLEANUP_DIRECT_RUNNING = False


_WINDOWS_CLEANUP_JOB_LOCK = threading.Lock()
_WINDOWS_CLEANUP_JOB: dict[str, Any] | None = None
_WINDOWS_CLEANUP_DIRECT_RUNNING = False


def _update_windows_cleanup_job(job_id: str, **changes: Any) -> None:
    with _WINDOWS_CLEANUP_JOB_LOCK:
        if _WINDOWS_CLEANUP_JOB and _WINDOWS_CLEANUP_JOB["id"] == job_id:
            _WINDOWS_CLEANUP_JOB.update(changes)


def _run_windows_cleanup_job(job_id: str, ids: list[str]) -> None:
    def on_progress(progress: dict[str, Any]) -> None:
        _update_windows_cleanup_job(job_id, **progress)

    try:
        result = clear_windows_cleanup(ids, on_progress=on_progress)
        _update_windows_cleanup_job(job_id, phase="indexing", results=result["results"])
        try:
            result["inventory"] = refresh_windows_cleanup_index()
        except OSError as exc:
            logger.warning("Windows cleanup inventory could not be saved after deletion: %s", exc)
            result["cache_error"] = "Could not save updated sizes; scan again to refresh them."
        _update_windows_cleanup_job(job_id, status="complete", phase="complete", **result)
    except Exception:
        logger.exception("Windows cleanup job stopped unexpectedly")
        _update_windows_cleanup_job(
            job_id, status="error", phase="error",
            message="Cleanup stopped unexpectedly. Rescan before trying again.",
        )


@app.post("/api/storage/windows-cleanup/job", status_code=status.HTTP_202_ACCEPTED)
def start_windows_cleanup_job(req: WindowsCleanupRequest) -> dict[str, Any]:
    """Start one managed cleanup job; the client can poll progress independently."""
    global _WINDOWS_CLEANUP_JOB
    try:
        validate_windows_cleanup_ids(req.ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    snapshot = load_windows_cleanup_index()
    estimated_files = sum(
        item.get("file_count") or 0 for item in snapshot.get("locations", [])
        if item.get("id") in req.ids
    )
    with _WINDOWS_CLEANUP_JOB_LOCK:
        if _WINDOWS_CLEANUP_DIRECT_RUNNING or (
            _WINDOWS_CLEANUP_JOB and _WINDOWS_CLEANUP_JOB["status"] == "running"
        ):
            raise HTTPException(status_code=409, detail="Windows cleanup is already running")
        job_id = uuid4().hex
        _WINDOWS_CLEANUP_JOB = {
            "id": job_id, "status": "running", "phase": "deleting", "location": "Starting cleanup",
            "current": 0, "total": len(req.ids), "processed_files": 0,
            "estimated_files": estimated_files, "removed_bytes": 0, "removed_files": 0,
        }
        try:
            threading.Thread(
                target=_run_windows_cleanup_job, args=(job_id, req.ids.copy()),
                daemon=True, name="creativeos-windows-cleanup",
            ).start()
        except RuntimeError as exc:
            _WINDOWS_CLEANUP_JOB = None
            raise HTTPException(status_code=500, detail="Could not start cleanup job") from exc
        return dict(_WINDOWS_CLEANUP_JOB)


@app.get("/api/storage/windows-cleanup/job")
def get_windows_cleanup_job() -> dict[str, Any]:
    with _WINDOWS_CLEANUP_JOB_LOCK:
        return dict(_WINDOWS_CLEANUP_JOB) if _WINDOWS_CLEANUP_JOB else {"status": "idle"}


@app.post("/api/storage/windows-cleanup/tool")
def open_windows_cleanup_tool(req: WindowsCleanupToolRequest) -> dict[str, str]:
    """Open a built-in Windows cleanup UI; do not select or delete files there."""
    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Windows tools are only available on Windows")
    try:
        if req.tool == "disk-cleanup":
            subprocess.Popen(["cleanmgr.exe"])
        else:
            os.startfile("ms-settings:storagesense")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not open Windows cleanup tool: {exc}") from exc
    return {"status": "opened"}


@app.get("/api/storage/reclaimable")
def get_reclaimable(project: str, force_refresh: bool = False) -> dict[str, Any]:
    """Inspect detailed reclaimable cache and dependency folders for a project with 0ms instant cached fallback."""
    proj_path, meta = _find_project_dir(project)

    # 1. Fast precomputed cache lookup from storage index if non-empty items exist
    if not force_refresh:
        index = load_storage_index(projects_path=PROJECTS_PATH)
        if index:
            proj_str = str(proj_path.resolve()).lower().replace("/", "\\")
            proj_name = meta.get("name", proj_path.name).lower()
            proj_slug = meta.get("slug", proj_path.name).lower()
            matched = next(
                (
                    p for p in index.get("projects", [])
                    if str(Path(p.get("path", "")).resolve()).lower().replace("/", "\\") == proj_str
                    or p.get("slug", "").lower() == proj_slug
                    or p.get("name", "").lower() == proj_name
                ),
                None,
            )
            if matched and matched.get("reclaimable_items"):
                items = matched["reclaimable_items"]
                total_reclaimable = sum(it.get("size", 0) for it in items)
                total_files = sum(it.get("file_count", 0) for it in items)
                return {
                    "status": "success",
                    "project": meta.get("name", proj_path.name),
                    "slug": meta.get("slug", proj_path.name),
                    "path": str(proj_path),
                    "total_reclaimable": total_reclaimable,
                    "total_files": total_files,
                    "items": items,
                    "cached": True,
                }

    # 2. Live fast scan fallback
    items = find_project_reclaimable_dirs(proj_path)
    total_reclaimable = sum(it.get("size", 0) for it in items)
    total_files = sum(it.get("file_count", 0) for it in items)

    # Update index cache in-memory for next time
    index = load_storage_index(projects_path=PROJECTS_PATH)
    if index:
        proj_str = str(proj_path.resolve()).lower().replace("/", "\\")
        proj_name = meta.get("name", proj_path.name).lower()
        proj_slug = meta.get("slug", proj_path.name).lower()
        for p in index.get("projects", []):
            if (
                str(Path(p.get("path", "")).resolve()).lower().replace("/", "\\") == proj_str
                or p.get("slug", "").lower() == proj_slug
                or p.get("name", "").lower() == proj_name
            ):
                if p.get("reclaimable_items") != items:
                    p["reclaimable_items"] = items
                    p["reclaimable_size"] = total_reclaimable
                    _recalculate_totals(index)
                    save_storage_index(index)
                break

    return {
        "status": "success",
        "project": meta.get("name", proj_path.name),
        "slug": meta.get("slug", proj_path.name),
        "path": str(proj_path),
        "total_reclaimable": total_reclaimable,
        "total_files": total_files,
        "items": items,
        "cached": False,
    }


@app.post("/api/storage/reclaim")
def reclaim_project(req: ReclaimProjectRequest) -> dict[str, Any]:
    """Purge regenerable dependencies and caches for a single project."""
    proj_path, meta = _find_project_dir(req.project)
    result = reclaim_project_space(proj_path, target_subdirs=req.targets)
    _invalidate_server_cache()
    return {
        "status": "success",
        "project": meta.get("name", proj_path.name),
        "slug": meta.get("slug", proj_path.name),
        "path": str(proj_path),
        **result,
    }


@app.post("/api/storage/reclaim-bulk")
def reclaim_bulk(req: ReclaimBulkRequest) -> dict[str, Any]:
    """Bulk reclaim regenerable caches and dependencies across multiple or stale projects."""
    result = reclaim_bulk_space(
        stale_only=req.stale_only,
        days=req.days,
        project_paths=req.project_slugs,
    )
    _invalidate_server_cache()
    return result


@app.get("/api/storage/reclaim/stream")
def reclaim_stream_endpoint(
    project: str | None = None,
    targets: str | None = None,
    slugs: str | None = None,
    stale_only: bool = False,
    days: int = DEFAULT_STALE_DAYS,
) -> StreamingResponse:
    """Stream real-time Server-Sent Events (SSE) for single or bulk project reclaim."""
    def sse_generator():
        try:
            if project:
                proj_path, _ = _find_project_dir(project)
                target_list = [t.strip() for t in targets.split(",")] if targets else None
                for event in stream_reclaim_project(proj_path, target_subdirs=target_list):
                    yield f"data: {json.dumps(event)}\n\n"
            else:
                slug_list = [s.strip() for s in slugs.split(",")] if slugs else None
                for event in stream_reclaim_bulk(stale_only=stale_only, days=days, project_paths=slug_list):
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as err:
            logger.error(f"Error during SSE reclaim stream: {err}")
            yield f"data: {json.dumps({'event': 'error', 'message': str(err)})}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _load_template_structures() -> dict[str, Any]:
    """Load structure.json for all templates."""
    structures: dict[str, Any] = {}
    templates_dir = Path(TEMPLATES_PATH)
    if templates_dir.exists():
        for item in templates_dir.iterdir():
            if item.is_dir():
                s_file = item / "structure.json"
                if s_file.exists():
                    try:
                        with open(s_file, "r", encoding="utf-8") as f:
                            structures[item.name] = json.load(f)
                    except Exception:
                        pass
    return structures


@app.get("/api/categories")
def get_categories_endpoint() -> dict[str, Any]:
    """Get all dynamic categories, enabled list, icons, and real template structures."""
    all_cats = get_categories()
    enabled_cats = get_enabled_categories()
    templates = _load_template_structures()

    enriched_cats = {}
    for cat_name, cat_data in all_cats.items():
        t_name = cat_data.get("template", "")
        t_struct = templates.get(t_name, {})
        enriched_cats[cat_name] = {
            **cat_data,
            "template_structure": t_struct,
        }

    return {
        "categories": enriched_cats,
        "enabled": enabled_cats,
        "default_category": get_default_category(),
        "simple_template": get_simple_template(),
        "simple_structure": templates.get(get_simple_template(), {"00_Notes": ["Notes.md", "Client_Links.md"]}),
        "template_structures": templates,
    }


@app.get("/api/config")
def get_config_endpoint() -> dict[str, Any]:
    """Get system configuration and path statuses."""
    raw_config = _load_config()
    paths_status: dict[str, Any] = {}

    for key, val in raw_config.items():
        if key.endswith("_path") and isinstance(val, str):
            paths_status[key] = {
                "path": val,
                "exists": os.path.exists(val),
            }

    return {
        "config": raw_config,
        "paths": paths_status,
        "version": __version__,
    }


@app.put("/api/config/paths")
def update_config_paths(req: UpdatePathsRequest) -> dict[str, Any]:
    """Update configured system directory paths with optional migration."""
    config = _load_config().copy()
    allowed_keys = {
        "vault_path", "exports_path", "archive_path", "shuttle_path", "downloads_path", "projects_path"
    }

    unsupported = set(req.paths) - allowed_keys
    if unsupported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Paths cannot be changed here: {', '.join(sorted(unsupported))}",
        )

    migrated = []
    for key, new_path_str in req.paths.items():
        new_path_str = new_path_str.strip()
        if not new_path_str:
            continue

        old_path_str = config.get(key)
        new_path = Path(new_path_str)

        if req.move_files and old_path_str and old_path_str != new_path_str and os.path.exists(old_path_str):
            try:
                new_path.mkdir(parents=True, exist_ok=True)
                for item in Path(old_path_str).iterdir():
                    dest = new_path / item.name
                    if not dest.exists():
                        if item.is_dir():
                            shutil.copytree(item, dest)
                        else:
                            shutil.copy2(item, dest)
                migrated.append(f"{key}: {old_path_str} -> {new_path_str}")
            except Exception as e:
                logger.warning(f"Could not migrate files for {key}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Migration failed for {key}; paths were not saved. Copied files may remain at {new_path}: {e}",
                ) from e
        else:
            try:
                new_path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise HTTPException(status_code=400, detail=f"Cannot use {key} destination: {e}") from e

        config[key] = str(new_path)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    reload_config()
    _invalidate_server_cache()

    return {
        "status": "success",
        "message": "System paths updated successfully",
        "config": config,
        "migrated": migrated,
    }


@app.get("/api/config/drives")
def get_drives_endpoint() -> dict[str, Any]:
    """Get all connected Windows drives and configured external mounts."""
    drives = []
    # Discover available drive letters on Windows
    for letter in string.ascii_uppercase:
        drive_path = f"{letter}:\\"
        try:
            p = Path(drive_path)
            if p.exists():
                drives.append({
                    "name": f"Drive ({letter}:)",
                    "path": drive_path,
                    "is_system": (letter == "C"),
                    "exists": True,
                })
        except Exception:
            pass

    config = _load_config()
    configured_mounts = config.get("external_mounts", [])
    return {
        "drives": drives,
        "external_mounts": configured_mounts,
    }


@app.put("/api/config/mounts")
def update_config_mounts(req: UpdateMountsRequest) -> dict[str, Any]:
    """Update configured external storage mounts."""
    config = _load_config()
    valid_mounts = []
    for m in req.mounts:
        if isinstance(m, dict) and "path" in m and m["path"].strip():
            p_str = m["path"].strip()
            name_str = m.get("name", "").strip() or Path(p_str).name or p_str
            valid_mounts.append({
                "name": name_str,
                "path": str(Path(p_str)),
            })

    config["external_mounts"] = valid_mounts
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    reload_config()
    _invalidate_server_cache()
    return {
        "status": "success",
        "message": "External mounts updated successfully",
        "external_mounts": valid_mounts,
    }


@app.put("/api/categories")
def update_categories_endpoint(req: UpdateCategoriesRequest) -> dict[str, Any]:
    """Update categories configuration."""
    from .category_config import load_categories, save_categories
    cats_config = load_categories()
    cats_config["categories"] = req.categories
    if req.default_category:
        cats_config["default_category"] = req.default_category

    ok = save_categories(cats_config)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save categories configuration")

    _invalidate_server_cache()
    return {
        "status": "success",
        "message": "Categories updated successfully",
        "categories": req.categories,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Note Sync (JSON & SSE Stream)
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/sync")
def trigger_sync() -> dict[str, Any]:
    """Trigger bidirectional sync between projects and Obsidian vault."""
    try:
        res = run_sync()
        return {
            "status": "success",
            **res,
        }
    except Exception as e:
        logger.error(f"Error executing sync from API: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {e}",
        ) from e


@app.get("/api/sync/stream")
def sync_stream_endpoint() -> StreamingResponse:
    """Stream real-time Server-Sent Events (SSE) for note sync operations."""
    def sse_generator():
        try:
            for event_data in stream_sync():
                payload = json.dumps(event_data)
                yield f"data: {payload}\n\n"
        except Exception as err:
            logger.error(f"Error during SSE sync stream: {err}")
            err_payload = json.dumps({"event": "error", "message": str(err)})
            yield f"data: {err_payload}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Studio & System Automations
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/system/clean-downloads")
def clean_downloads(req: CleanDownloadsRequest = CleanDownloadsRequest()) -> dict[str, Any]:
    """Sort loose files in Downloads or target directory into categorized subfolders."""
    if req.folder and req.folder.strip():
        target_dir = Path(req.folder.strip()).resolve()
    else:
        if DOWNLOADS_PATH and Path(DOWNLOADS_PATH).exists():
            target_dir = Path(DOWNLOADS_PATH).resolve()
        else:
            target_dir = (Path.home() / "Downloads").resolve()

    target_dir = _check_path_allowed(target_dir)

    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target directory not found: {target_dir}",
        )

    count = 0
    errors: list[str] = []

    try:
        items = list(target_dir.iterdir())
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied accessing directory: {e}",
        )

    for item_path in items:
        if item_path.name.startswith("."):
            continue
        if not item_path.is_file():
            continue

        ext = item_path.suffix.lower()
        target_folder_name = None

        for folder_name, extensions in DOWNLOADS_MAPPING.items():
            if ext in extensions:
                target_folder_name = folder_name
                break

        if not target_folder_name:
            target_folder_name = "_Other"

        dest_dir = target_dir / target_folder_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_file = dest_dir / item_path.name
        if dest_file.exists():
            stem = item_path.stem
            suffix = item_path.suffix
            counter = 2
            while dest_file.exists():
                dest_file = dest_dir / f"{stem}_v{counter}{suffix}"
                counter += 1

        try:
            shutil.move(str(item_path), str(dest_file))
            count += 1
        except Exception as e:
            logger.warning(f"Could not move {item_path.name}: {e}")
            errors.append(f"{item_path.name}: {e}")

    return {
        "status": "success",
        "message": f"Cleaned downloads: {count} files organized",
        "folder": str(target_dir),
        "moved_count": count,
        "errors": errors,
    }


@app.post("/api/exports/month-folder")
def create_current_export_month() -> dict[str, str]:
    """Open the same current-month destination as cos export --simple."""
    now = datetime.datetime.now()
    month_dir = Path(EXPORTS_PATH) / now.strftime("%Y") / now.strftime("%m - %B")
    month_dir.mkdir(parents=True, exist_ok=True)
    return {"path": str(month_dir)}


@app.post("/api/exports/sort-inbox")
def sort_exports_inbox(req: SortExportsRequest = SortExportsRequest()) -> dict[str, Any]:
    """Sort unfiled export renders into 02_Exports/YYYY/MM - Month/ based on file timestamps."""
    if req.inbox_path and req.inbox_path.strip():
        inbox_path = Path(req.inbox_path.strip()).resolve()
    else:
        inbox_path = (Path(EXPORTS_PATH) / "_Inbox").resolve()

    inbox_path = _check_path_allowed(inbox_path)
    if (inbox_path / ".project_meta.json").exists():
        raise HTTPException(status_code=400, detail="Cannot sort a project root as an export inbox")

    if not inbox_path.exists():
        inbox_path.mkdir(parents=True, exist_ok=True)
        return {
            "status": "success",
            "message": f"Created Inbox at {inbox_path}",
            "moved_count": 0,
            "errors": [],
        }

    count = 0
    errors: list[str] = []

    try:
        items = list(inbox_path.iterdir())
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied reading Inbox: {e}",
        )

    for item_path in items:
        smart_ts = get_smart_date(str(item_path))
        date_obj = datetime.datetime.fromtimestamp(smart_ts)
        year = date_obj.strftime("%Y")
        month_folder = date_obj.strftime("%m - %B")

        dest_dir = Path(EXPORTS_PATH) / year / month_folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_path = dest_dir / item_path.name
        if dest_path.exists():
            stem = item_path.stem if item_path.is_file() else item_path.name
            suffix = item_path.suffix if item_path.is_file() else ""
            counter = 2
            while dest_path.exists():
                dest_path = dest_dir / f"{stem}_v{counter}{suffix}"
                counter += 1

        try:
            shutil.move(str(item_path), str(dest_path))
            count += 1
        except Exception as e:
            logger.warning(f"Could not move export item {item_path.name}: {e}")
            errors.append(f"{item_path.name}: {e}")

    return {
        "status": "success",
        "message": f"Sorted {count} items into monthly export directories",
        "moved_count": count,
        "errors": errors,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Static files & Single-Page Application (SPA) Serving
# ──────────────────────────────────────────────────────────────────────────────

GUI_DIST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "GUI", "dist")
)

def _setup_spa_routes():
    if os.path.isdir(GUI_DIST_DIR):
        assets_dir = os.path.join(GUI_DIST_DIR, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")
            target_file = os.path.join(GUI_DIST_DIR, full_path)
            if full_path and os.path.isfile(target_file):
                return FileResponse(target_file)
            index_file = os.path.join(GUI_DIST_DIR, "index.html")
            if os.path.isfile(index_file):
                return FileResponse(index_file)
            return HTMLResponse("<h1>CreativeOS GUI</h1><p>index.html not found in dist</p>")
    else:
        @app.get("/")
        def serve_dev_placeholder():
            return HTMLResponse("""<!DOCTYPE html>
<html>
<head>
    <title>CreativeOS GUI (Dev Mode)</title>
    <style>
        body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .box { background: #1e293b; padding: 2rem; border-radius: 8px; border: 1px solid #334155; max-width: 500px; text-align: center; }
        h1 { margin-top: 0; color: #38bdf8; }
        code { background: #0f172a; padding: 0.2rem 0.5rem; border-radius: 4px; color: #a5f3fc; }
    </style>
</head>
<body>
    <div class="box">
        <h1>CreativeOS GUI</h1>
        <p>Frontend production bundle is building.</p>
        <p>Run <code>cd 00_System/GUI && npm run build</code> to generate the bundle.</p>
        <p><a href="/docs" style="color: #38bdf8;">View Swagger API Docs &rarr;</a></p>
    </div>
</body>
</html>""")

_setup_spa_routes()
