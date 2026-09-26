"""Non-destructive project storage review and scheduled cache commands."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich import box
from rich.panel import Panel
from rich.table import Table

from .. import storage as storage_index
from ..config import SCRIPT_DIR
from ..console import console
from ..help_formatter import RichHelpAction

TASK_NAME = "CreativeOS Storage Scan"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _valid_time(value: str) -> str:
    try:
        dt.datetime.strptime(value, "%H:%M")
    except ValueError as error:
        raise argparse.ArgumentTypeError("use 24-hour HH:MM time, e.g. 03:00") from error
    return value


def add_parser(subparsers: Any) -> None:
    """Register the ``cos storage`` command group."""
    parser = subparsers.add_parser(
        "storage",
        help="Review project storage from a cached, user-authorized inventory",
        description=(
            "Inspect CreativeOS projects without deleting or moving anything. "
            "Scans record size, media usage, regenerable code folders, created date, "
            "and the last meaningful update while ignoring noisy folders such as "
            "node_modules and .git for activity dates."
        ),
        epilog="""\
Examples:
  cos storage                              Open the saved storage report
  cos storage review --sort media          Find media-heavy projects
  cos storage review --sort reclaimable    Find dependency/cache-heavy projects
  cos storage review --refresh --path Code/Clones/gemini-cli
                                           Rescan just one project (fast)
  cos storage review --refresh             Rescan all projects
  cos storage schedule --time 01:00        Run a quiet weekly scan at 1:00 AM
  cos storage help                         Show this help from either direction

The report is read-only. It never archives or deletes a project.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("-h", "--help", action=RichHelpAction, help="Show this help message and exit.")
    commands = parser.add_subparsers(dest="storage_command", title="Storage commands")

    review = commands.add_parser(
        "review",
        help="Scan and display project size, activity, and reclaimable space",
        epilog="""\
Examples:
  cos storage review                       Show the saved report instantly
  cos storage review --sort media          Put media-heavy projects first
  cos storage review --sort reclaimable    Put node_modules/cache-heavy projects first
  cos storage review --stale-days 180      Mark 180+ day projects as stale
  cos storage review --limit 159           Show every indexed project
  cos storage review --refresh             Deliberately scan all projects now
  cos storage review --refresh --path Code/Clones/gemini-cli
                                           Rescan only one project (fast)""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    review.add_argument("-h", "--help", action=RichHelpAction, help="Show this help message and exit.")
    review.add_argument(
        "--refresh",
        action="store_true",
        help="Run a foreground scan now. Without this flag, show the saved index instantly.",
    )
    review.add_argument(
        "--stale-days",
        type=_positive_int,
        default=storage_index.DEFAULT_STALE_DAYS,
        help="Mark projects inactive for this many days as stale (default: 90).",
    )
    review.add_argument(
        "--sort",
        type=str.lower,
        choices=("size", "updated", "created", "reclaimable", "media"),
        default="size",
        help="Sort the table by this field (default: size).",
    )
    review.add_argument(
        "--limit",
        type=_positive_int,
        default=50,
        help="Maximum projects to show in the table (default: 50).",
    )
    review.add_argument(
        "--path",
        default=None,
        help="Rescan only projects under this subdirectory (relative to 01_Projects or absolute). Requires --refresh.",
    )

    scan = commands.add_parser(
        "scan",
        help="Refresh the local storage index without showing the review table",
        add_help=False,
    )
    scan.add_argument("-h", "--help", action=RichHelpAction, help="Show this help message and exit.")
    scan.add_argument("--quiet", action="store_true", help="Suppress success output (for Task Scheduler).")
    scan.add_argument(
        "--background",
        action="store_true",
        help="Lower this scanner's process priority when the platform supports it.",
    )

    schedule = commands.add_parser(
        "schedule",
        help="Manage the weekly background scan used by optional reminders",
        epilog="""\
Examples:
  cos storage schedule --time 01:00  Schedule the quiet Sunday scan for 1:00 AM
  cos storage schedule --status      Check its next run and last result
  cos storage schedule --remove      Remove the task and turn off reminders""",
        add_help=False,
    )
    schedule.add_argument("-h", "--help", action=RichHelpAction, help="Show this help message and exit.")
    schedule.add_argument(
        "--time",
        type=_valid_time,
        default="03:00",
        help="Sunday local start time in 24-hour HH:MM format (default: 03:00).",
    )
    schedule.add_argument("--status", action="store_true", help="Show the Windows Task Scheduler entry.")
    schedule.add_argument("--remove", action="store_true", help="Remove the scheduled scan and disable reminders.")


def _age_label(project: dict[str, Any], stale_days: int) -> str:
    activity = storage_index._parse_iso(project.get("last_meaningful_update"))
    if activity is None:
        return "unknown"
    days = (_now() - activity).days
    return f"{days}d stale" if days >= stale_days else f"{days}d ago"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _sort_projects(projects: list[dict[str, Any]], sort_by: str) -> list[dict[str, Any]]:
    if sort_by == "updated":
        return sorted(projects, key=lambda project: project.get("last_meaningful_update") or "", reverse=False)
    if sort_by == "created":
        return sorted(projects, key=lambda project: project.get("created") or "", reverse=False)
    field = {"size": "total_size", "reclaimable": "reclaimable_size", "media": "media_size"}[sort_by]
    return sorted(projects, key=lambda project: project.get(field, 0), reverse=True)


def _render_review(index: dict[str, Any], args: argparse.Namespace) -> None:
    scanned_at = storage_index._parse_iso(index.get("scanned_at"))
    scan_label = scanned_at.astimezone().strftime("%Y-%m-%d %H:%M") if scanned_at else "unknown"
    stale = {project["path"] for project in storage_index.stale_projects(index, args.stale_days)}

    console.print(Panel(
        "[bold]Read-only inventory[/bold] — no project, media file, or dependency folder was moved or deleted.\n"
        f"Last scan: [cyan]{scan_label}[/cyan]  •  "
        f"Projects: [cyan]{index.get('project_count', 0)}[/cyan]  •  "
        f"Total: [cyan]{storage_index.format_bytes(index.get('total_size', 0))}[/cyan]  •  "
        f"Regenerable code/cache: [cyan]{storage_index.format_bytes(index.get('reclaimable_size', 0))}[/cyan]  •  "
        f"Media: [cyan]{storage_index.format_bytes(index.get('media_size', 0))}[/cyan]",
        title="Storage Review",
        border_style="cyan",
    ))

    table = Table(box=box.ROUNDED, header_style="bold magenta", show_lines=False)
    table.add_column("Project", style="bold white", max_width=28)
    table.add_column("Created", style="cyan", no_wrap=True)
    table.add_column("Meaningful update", no_wrap=True)
    table.add_column("Total", justify="right", style="bold")
    table.add_column("Media", justify="right")
    table.add_column("Regenerable", justify="right", style="yellow")
    table.add_column("Status", no_wrap=True)

    projects = _sort_projects(index.get("projects", []), args.sort)[:args.limit]
    for project in projects:
        update = storage_index._parse_iso(project.get("last_meaningful_update"))
        update_label = update.astimezone().strftime("%Y-%m-%d") if update else "Unknown"
        is_stale = project.get("path") in stale
        status = f"[yellow]{_age_label(project, args.stale_days)}[/yellow]" if is_stale else "[green]active[/green]"
        project_name = project.get("name", "Unknown")
        project_path = project.get("path", "")
        if project_path:
            name_cell = f"[link=file:///{project_path.replace(os.sep, '/')}]{project_name}[/link]"
        else:
            name_cell = project_name
        table.add_row(
            name_cell,
            project.get("created", "Unknown"),
            update_label,
            storage_index.format_bytes(project.get("total_size", 0)),
            storage_index.format_bytes(project.get("media_size", 0)),
            storage_index.format_bytes(project.get("reclaimable_size", 0)),
            status,
        )

    console.print(table)
    if len(index.get("projects", [])) > len(projects):
        console.print(f"[dim]Showing {len(projects)} of {len(index['projects'])} projects; use --limit to show more.[/dim]")

    console.print(Panel(
        "[bold]How to read this[/bold]\n"
        "• [cyan]Total[/cyan] is all disk space inside the project.\n"
        "• [cyan]Media[/cyan] is video, audio, image, and camera-media files.\n"
        "• [yellow]Regenerable[/yellow] is node_modules and build/cache data; it is included in Total, not extra.\n"
        "• [cyan]Meaningful update[/cyan] ignores generated folders, so dependency installs do not make old work look active.\n\n"
        "[bold]Try next[/bold]\n"
        "• [cyan]cos storage review --sort media[/cyan]  Find projects with the most media.\n"
        "• [cyan]cos storage review --sort reclaimable[/cyan]  Find projects with the most code/cache savings.\n"
        "• [cyan]cos storage review --refresh --path Code/Clones/gemini-cli[/cyan]  Rescan one project fast.\n"
        "• [cyan]cos storage review --stale-days 180[/cyan]  Use a six-month inactivity threshold.\n"
        "• [cyan]cos storage review --limit 159[/cyan]  Show every indexed project.\n"
        "• [cyan]cos storage help[/cyan]  See all flags and examples.\n\n"
        "[dim]This report is read-only. It cannot archive or delete anything.[/dim]",
        title="Use this report",
        border_style="dim",
    ))


def cmd_review(args: argparse.Namespace) -> None:
    """Render the saved index by default; only --refresh traverses the disk."""
    scope_path = getattr(args, "path", None)
    if scope_path and not args.refresh:
        console.print("[warning]--path requires --refresh (nothing to filter without a scan).[/warning]")
        return
    if args.refresh:
        if scope_path:
            with console.status(f"Rescanning projects under [cyan]{scope_path}[/cyan]..."):
                index, count = storage_index.refresh_partial(scope_path)
            if count == 0:
                console.print(f"[warning]No projects found under [cyan]{scope_path}[/cyan].[/warning]")
                return
            label = "1 project" if count == 1 else f"{count} projects"
            console.print(f"[success]Rescanned {label} under [cyan]{scope_path}[/cyan].[/success]")
        else:
            with console.status("Scanning all project storage (nothing will be changed)..."):
                index = storage_index.refresh_storage_index()
    else:
        index = storage_index.load_storage_index()
        if index is None:
            console.print(Panel(
                "No storage index exists yet, so CreativeOS will not start a slow scan while you work.\n\n"
                "Set up the low-priority weekly background scan with:\n"
                "[cyan]cos storage schedule --time 03:00[/cyan]\n\n"
                "Or deliberately scan now with:\n"
                "[cyan]cos storage review --refresh[/cyan]",
                title="Storage Review",
                border_style="yellow",
            ))
            return
    _render_review(index, args)


def _lower_process_priority() -> None:
    """Make scheduled scans yield to interactive work whenever possible."""
    try:
        if platform.system() == "Windows":
            import ctypes
            idle_priority_class = 0x00000040
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(), idle_priority_class
            )
        else:
            import os
            os.nice(10)
    except (AttributeError, OSError):
        # Priority adjustment is an optimization, never a requirement.
        pass


def cmd_scan(args: argparse.Namespace) -> None:
    """Refresh cache for direct or scheduled invocation."""
    if args.background:
        _lower_process_priority()
    if args.quiet:
        index = storage_index.refresh_storage_index()
    else:
        with console.status("Scanning project storage (nothing will be changed)..."):
            index = storage_index.refresh_storage_index()
    if not args.quiet:
        console.print(
            f"[success]Storage index updated: {index['project_count']} projects, "
            f"{storage_index.format_bytes(index['total_size'])} measured.[/success]"
        )


def _run_schtasks(arguments: list[str]) -> subprocess.CompletedProcess[str] | None:
    if platform.system() != "Windows":
        console.print("[warning]Scheduled storage scans use Windows Task Scheduler and are unavailable on this platform.[/warning]")
        return None
    return subprocess.run(
        ["schtasks.exe", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def _show_task_result(result: subprocess.CompletedProcess[str]) -> None:
    message = (result.stdout or result.stderr).strip()
    if result.returncode == 0:
        console.print(f"[success]{message or 'Task Scheduler updated.'}[/success]")
    else:
        console.print(f"[error]{message or 'Task Scheduler operation failed.'}[/error]")


def cmd_schedule(args: argparse.Namespace) -> None:
    """Create, inspect, or remove an opt-in weekly Windows scan."""
    if args.remove:
        result = _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
        if result is not None:
            _show_task_result(result)
            if result.returncode == 0:
                storage_index.set_reminders_enabled(False)
        return

    if args.status:
        result = _run_schtasks(["/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"])
        if result is not None:
            _show_task_result(result)
        return

    # Use pythonw.exe when available so Task Scheduler does not open a console
    # window for its quiet, low-priority background scan.
    python_executable = Path(sys.executable)
    pythonw_executable = python_executable.with_name("pythonw.exe")
    scheduler_python = (
        str(pythonw_executable)
        if platform.system() == "Windows" and pythonw_executable.is_file()
        else sys.executable
    )
    task_command = subprocess.list2cmdline([
        scheduler_python,
        str(Path(SCRIPT_DIR).parent / "manage.py"),
        "storage",
        "scan",
        "--quiet",
        "--background",
    ])
    result = _run_schtasks([
        "/Create", "/F", "/TN", TASK_NAME, "/SC", "WEEKLY", "/D", "SUN",
        "/ST", args.time, "/TR", task_command,
    ])
    if result is not None:
        _show_task_result(result)
        if result.returncode == 0:
            storage_index.set_reminders_enabled(True)
            console.print("[dim]The task only measures storage. It cannot archive or delete your files.[/dim]")


def cmd_storage(args: argparse.Namespace) -> None:
    """Route the storage command group."""
    if args.storage_command is None:
        # `cos storage` is a convenient alias for an instant cached review.
        args.refresh = False
        args.stale_days = storage_index.DEFAULT_STALE_DAYS
        args.sort = "size"
        args.limit = 50
        cmd_review(args)
    elif args.storage_command == "review":
        cmd_review(args)
    elif args.storage_command == "scan":
        cmd_scan(args)
    elif args.storage_command == "schedule":
        cmd_schedule(args)


def show_reminder_if_due() -> None:
    """Show a cheap, at-most-weekly reminder after normal COS commands."""
    try:
        index = storage_index.load_storage_index()
        if index is None or not storage_index.reminder_is_due(index):
            return
        stale = storage_index.stale_projects(index)
        if stale:
            console.print(
                f"[dim]Storage reminder: {len(stale)} cached project(s) are inactive for "
                f"{storage_index.DEFAULT_STALE_DAYS}+ days. Run [cyan]cos storage review[/cyan].[/dim]"
            )
        storage_index.mark_reminded(index)
    except OSError:
        # Reminders must never interfere with the command the user actually ran.
        return
