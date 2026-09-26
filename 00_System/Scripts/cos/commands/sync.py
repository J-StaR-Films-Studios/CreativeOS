"""Sync command."""

import os
import json
import argparse
import datetime
import shutil
import filecmp
from typing import Any, Tuple, List, Dict, Optional, Union

from rich.table import Table
from rich import box

from ..config import PROJECTS_PATH, VAULT_PATH, SYNC_STATE_PATH, EXCLUDED_DIRS, logger, SCRIPT_DIR
from ..console import console

FileFingerprint = Dict[str, Union[float, int]]
SyncState = Dict[str, Any]

def add_parser(subparsers: Any) -> None:
    from ..help_formatter import RichHelpAction

    p_sync = subparsers.add_parser(
        "sync",
        help="Sync project notes with Obsidian vault",
        description="""\
Bidirectional synchronisation between every project's 00_Notes folder
and your Obsidian vault (01_Active_Projects/).

How it works:
  1. Scans all projects for 00_Notes/ folders
  2. Compares files with vault counterparts using mtime + size
  3. The newer file always wins; identical files are skipped
  4. New files are copied in both directions
  5. Sync state is persisted so subsequent syncs are incremental

Safety:
  - No files are ever deleted — only copied
  - Backups are created (.bak) before overwriting a project file
  - All operations are logged\
""",
        epilog="""\
Examples:
  cos sync                     Sync all projects
  cos sync --dry-run           Preview changes without applying them
  cos sync -v                  Show verbose file-by-file output

Output legend:
  PUSH  — file copied from project to vault
  PULL  — file copied from vault to project
  SKIP  — files are identical, no action taken\
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )

    p_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview all changes that would be made without actually copying anything.",
    )
    p_sync.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show a detailed file-by-file list of every sync operation.",
    )
    p_sync.add_argument(
        "-h", "--help",
        action=RichHelpAction,
        help="Show this help message and exit.",
    )

def load_sync_state() -> SyncState:
    """Load the sync state database for incremental syncs."""
    if os.path.exists(SYNC_STATE_PATH):
        try:
            with open(SYNC_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_sync_state(state: SyncState) -> None:
    """Save the sync state database."""
    os.makedirs(os.path.dirname(SYNC_STATE_PATH), exist_ok=True)
    with open(SYNC_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def get_file_fingerprint(filepath: str) -> Optional[FileFingerprint]:
    """Get a fast fingerprint for a file using mtime and size."""
    try:
        stat_info = os.stat(filepath)
        return {
            "mtime": stat_info.st_mtime,
            "size": stat_info.st_size
        }
    except OSError:
        return None

def get_syncable_files(root_dir: str) -> Dict[str, Optional[FileFingerprint]]:
    """Recursively find all .md and .pdf files, returning relative paths."""
    ALLOWED_EXTENSIONS = {".md", ".pdf"}
    files = {}
    for root, dirs, filenames in os.walk(root_dir, topdown=True):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, root_dir)
                files[rel_path] = get_file_fingerprint(full_path)
    return files

def sync_two_folders(dir_a: str, dir_b: str, prev_state: Optional[SyncState] = None, dry_run: bool = False) -> Tuple[List[Dict[str, str]], SyncState]:
    """Bidirectional Sync: A (Project) <-> B (Vault). Recursively syncs .md and .pdf files."""
    if not dry_run:
        if not os.path.exists(dir_a): os.makedirs(dir_a)
        if not os.path.exists(dir_b): os.makedirs(dir_b)

    files_a = get_syncable_files(dir_a)
    files_b = get_syncable_files(dir_b)
    all_files = set(files_a.keys()).union(set(files_b.keys()))
    logs = []
    new_state = {}
    
    for rel_path in all_files:
        path_a = os.path.join(dir_a, rel_path)
        path_b = os.path.join(dir_b, rel_path)
        
        fp_a = files_a.get(rel_path)
        fp_b = files_b.get(rel_path)

        # Case 1: New in A
        if fp_a and not fp_b:
            try:
                if not dry_run:
                    os.makedirs(os.path.dirname(path_b), exist_ok=True)
                    shutil.copy2(path_a, path_b)
                logs.append({"type": "push", "file": rel_path, "msg": "Would push to Vault" if dry_run else "Pushed to Vault"})
                new_state[rel_path] = fp_a
            except Exception as e: logs.append({"type": "error", "file": rel_path, "msg": str(e)})

        # Case 2: New in B
        elif fp_b and not fp_a:
            try:
                if not dry_run:
                    os.makedirs(os.path.dirname(path_a), exist_ok=True)
                    shutil.copy2(path_b, path_a)
                logs.append({"type": "pull", "file": rel_path, "msg": "Would pull from Vault" if dry_run else "Pulled from Vault"})
                new_state[rel_path] = fp_b
            except Exception as e: logs.append({"type": "error", "file": rel_path, "msg": str(e)})

        # Case 3: File exists in both
        else:
            if fp_a and fp_b:
                if (fp_a["mtime"] == fp_b["mtime"] and fp_a["size"] == fp_b["size"]):
                    new_state[rel_path] = fp_a
                    continue
                
                if prev_state:
                    prev_fp = prev_state.get(rel_path)
                    if prev_fp:
                        if (fp_a["mtime"] == prev_fp["mtime"] and fp_a["size"] == prev_fp["size"] and
                            fp_b["mtime"] == prev_fp["mtime"] and fp_b["size"] == prev_fp["size"]):
                            new_state[rel_path] = prev_fp
                            continue
                
                try:
                    if fp_a["size"] != fp_b["size"]:
                        content_differs = True
                    elif fp_a["mtime"] == fp_b["mtime"]:
                        content_differs = False
                    else:
                        content_differs = not filecmp.cmp(path_a, path_b, shallow=False)
                    
                    if content_differs:
                        mtime_a = fp_a["mtime"]
                        mtime_b = fp_b["mtime"]
                        
                        if mtime_a > mtime_b:
                            if not dry_run:
                                shutil.copy2(path_a, path_b)
                            logs.append({"type": "update_vault", "file": rel_path, "msg": "Would update Vault" if dry_run else "Updated Vault"})
                            new_state[rel_path] = fp_a if dry_run else get_file_fingerprint(path_b)
                        elif mtime_b > mtime_a:
                            if not dry_run:
                                shutil.copy2(path_a, path_a + ".bak")
                                shutil.copy2(path_b, path_a)
                            logs.append({"type": "update_project", "file": rel_path, "msg": "Would update Project (with backup)" if dry_run else "Updated Project (Backup made)"})
                            new_state[rel_path] = fp_b if dry_run else get_file_fingerprint(path_a)
                        else:
                            if not dry_run:
                                shutil.copy2(path_a, path_b)
                            logs.append({"type": "conflict", "file": rel_path, "msg": "Content mismatch. Would push." if dry_run else "Content mismatch. Forced Push."})
                            new_state[rel_path] = fp_a if dry_run else get_file_fingerprint(path_b)
                    else:
                        new_state[rel_path] = fp_a
                except Exception as e: logs.append({"type": "error", "file": rel_path, "msg": str(e)})
    
    return logs, new_state

def run_sync(
    projects_path: str | None = None,
    vault_path: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute bidirectional note sync between projects and Obsidian vault.
    
    Returns:
        dict with projects_synced, total_changes, logs, and timestamp.
    """
    proj_root = projects_path or PROJECTS_PATH
    vault_root = vault_path or VAULT_PATH
    vault_projects_dir = os.path.join(vault_root, "01_Active_Projects")
    if not dry_run and not os.path.exists(vault_projects_dir):
        os.makedirs(vault_projects_dir, exist_ok=True)

    prev_sync_state = load_sync_state()
    new_sync_state: SyncState = {}
    all_logs: list[dict[str, Any]] = []
    total_changes = 0
    projects_synced = 0

    for root, dirs, files in os.walk(proj_root, topdown=True):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        if ".project_meta.json" in files:
            meta_path = os.path.join(root, ".project_meta.json")
            try:
                with open(meta_path, "r", encoding="utf-8-sig") as f:
                    meta = json.load(f)
            except Exception:
                continue

            project_name = meta.get("slug", "Unknown")
            notes_project = os.path.join(root, "00_Notes")
            notes_vault = os.path.join(vault_projects_dir, project_name)

            project_prev_state = prev_sync_state.get("projects", {}).get(project_name, {}).get("files", {})

            logs, project_state = sync_two_folders(notes_project, notes_vault, project_prev_state, dry_run=dry_run)

            if project_state:
                if "projects" not in new_sync_state:
                    new_sync_state["projects"] = {}
                new_sync_state["projects"][project_name] = {
                    "files": project_state,
                    "last_sync": datetime.datetime.now().isoformat(),
                }

            projects_synced += 1

            for log in logs:
                log_entry = {
                    "project": project_name,
                    "type": log.get("type", "unknown"),
                    "file": log.get("file", ""),
                    "msg": log.get("msg", ""),
                }
                all_logs.append(log_entry)
                total_changes += 1

    sync_timestamp = datetime.datetime.now().isoformat()
    new_sync_state["last_full_sync"] = sync_timestamp
    if not dry_run:
        save_sync_state(new_sync_state)

    logger.info(f"Sync complete: {total_changes} operations across {projects_synced} projects")
    return {
        "projects_synced": projects_synced,
        "total_changes": total_changes,
        "logs": all_logs,
        "last_sync": sync_timestamp,
    }


def stream_sync(
    projects_path: str | None = None,
    vault_path: str | None = None,
):
    """Generator executing bidirectional note sync and yielding SSE-ready event dictionaries."""
    proj_root = projects_path or PROJECTS_PATH
    vault_root = vault_path or VAULT_PATH
    vault_projects_dir = os.path.join(vault_root, "01_Active_Projects")
    if not os.path.exists(vault_projects_dir):
        os.makedirs(vault_projects_dir, exist_ok=True)

    yield {
        "event": "start",
        "message": "Initiating note synchronization with Obsidian Vault...",
        "timestamp": datetime.datetime.now().isoformat(),
    }

    prev_sync_state = load_sync_state()
    new_sync_state: SyncState = {}
    all_logs: list[dict[str, Any]] = []
    total_changes = 0
    projects_synced = 0

    for root, dirs, files in os.walk(proj_root, topdown=True):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        if ".project_meta.json" in files:
            meta_path = os.path.join(root, ".project_meta.json")
            try:
                with open(meta_path, "r", encoding="utf-8-sig") as f:
                    meta = json.load(f)
            except Exception:
                continue

            project_name = meta.get("slug", "Unknown")
            notes_project = os.path.join(root, "00_Notes")
            notes_vault = os.path.join(vault_projects_dir, project_name)

            yield {
                "event": "scanning_project",
                "project": project_name,
                "path": root,
            }

            project_prev_state = prev_sync_state.get("projects", {}).get(project_name, {}).get("files", {})
            logs, project_state = sync_two_folders(notes_project, notes_vault, project_prev_state)

            if project_state:
                if "projects" not in new_sync_state:
                    new_sync_state["projects"] = {}
                new_sync_state["projects"][project_name] = {
                    "files": project_state,
                    "last_sync": datetime.datetime.now().isoformat(),
                }

            projects_synced += 1

            for log in logs:
                log_entry = {
                    "project": project_name,
                    "type": log.get("type", "unknown"),
                    "file": log.get("file", ""),
                    "msg": log.get("msg", ""),
                }
                all_logs.append(log_entry)
                total_changes += 1

                yield {
                    "event": "file_sync",
                    **log_entry,
                }

    sync_timestamp = datetime.datetime.now().isoformat()
    new_sync_state["last_full_sync"] = sync_timestamp
    save_sync_state(new_sync_state)

    logger.info(f"Sync complete: {total_changes} operations across {projects_synced} projects")
    yield {
        "event": "complete",
        "projects_synced": projects_synced,
        "total_changes": total_changes,
        "logs": all_logs,
        "last_sync": sync_timestamp,
    }


def cmd_sync(args: argparse.Namespace) -> None:
    """Sync Notes between Projects and Obsidian Vault."""
    logger.info("Starting sync operation (dry run: %s)", args.dry_run)
    console.rule("[bold purple]Previewing CreativeOS Sync" if args.dry_run else "[bold purple]Syncing CreativeOS Brain")

    changes_table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
    changes_table.add_column("Project", style="cyan")
    changes_table.add_column("Action", style="white")
    changes_table.add_column("File", style="dim")

    with console.status("[bold cyan]Checking Notes...[/bold cyan]" if args.dry_run else "[bold cyan]Syncing Notes...[/bold cyan]"):
        result = run_sync(dry_run=args.dry_run)

    for log in result["logs"]:
        symbol = "✅"
        if log["type"] == "push":
            symbol = "→ [green]Push[/green]"
        elif log["type"] == "pull":
            symbol = "← [blue]Pull[/blue]"
        elif log["type"] == "error":
            symbol = "❌ [red]Error[/red]"
        elif log["type"] == "conflict":
            symbol = "⚠️ [yellow]Conflict[/yellow]"
        elif log["type"] == "update_vault":
            symbol = "→ [green]Update Vault[/green]"
        elif log["type"] == "update_project":
            symbol = "← [blue]Update Project[/blue]"

        changes_table.add_row(log["project"], symbol, log["file"])

    if result["total_changes"] == 0:
        console.print(f"[success]✅ Everything is up to date. ({result['projects_synced']} projects scanned)[/success]")
    else:
        console.print(changes_table)
        verb = "would change" if args.dry_run else "completed"
        console.print(f"[success]{result['total_changes']} operations {verb} across {result['projects_synced']} projects.[/success]")

