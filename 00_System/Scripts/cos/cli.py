"""Main CLI entry point for CreativeOS."""

import argparse
import sys
import datetime
import traceback
import os
from argparse import RawTextHelpFormatter

from . import __version__
from .console import console
from .config import SCRIPT_DIR
from .help_formatter import RichHelpAction, RichArgumentParser
from .onboarding import is_first_run, run_onboarding_wizard, apply_configuration
from rich.panel import Panel
from rich.table import Table
from rich import box


# ──────────────────────────────────────────────────────────────────────────────
# Exception handler
# ──────────────────────────────────────────────────────────────────────────────

def handle_exception(exc_type, exc_value, exc_traceback):
    """Custom exception handler for beautiful error display via Rich."""
    if issubclass(exc_type, KeyboardInterrupt):
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)

    console.print(Panel(
        f"[bold red]An unexpected error occurred:[/bold red]\n\n"
        f"[dim]{exc_type.__name__}:[/dim] {exc_value}\n\n"
        f"[dim]Full error logged to: 00_System/Config/error.log[/dim]",
        title=" Error ",
        border_style="red"
    ))

    log_path = os.path.join(SCRIPT_DIR, "..", "..", "Config", "error.log")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"Time: {datetime.datetime.now().isoformat()}\n")
            f.write(f"Command: {' '.join(sys.argv)}\n")
            f.write(f"Working Dir: {os.getcwd()}\n\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    except Exception:
        pass

    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Rich help overview  (shown for `cos` and `cos -h / --help`)
# ──────────────────────────────────────────────────────────────────────────────

def show_help_overview() -> None:
    """Show the full, richly-formatted help overview and exit."""

    banner = (
        "  ██████╗██████╗ ███████╗ █████╗ ████████╗██╗██╗   ██╗███████╗ ██████╗ ███████╗\n"
        " ██╔════╝██╔══██╗██╔════╝██╔══██╗╚══██╔══╝██║██║   ██║██╔════╝██╔═══██╗██╔════╝\n"
        " ██║     ██████╔╝█████╗  ███████║   ██║   ██║██║   ██║█████╗  ██║   ██║███████╗\n"
        " ██║     ██╔══██╗██╔══╝  ██╔══██║   ██║   ██║╚██╗ ██╔╝██╔══╝  ██║   ██║╚════██║\n"
        " ╚██████╗██║  ██║███████╗██║  ██║   ██║   ██║ ╚████╔╝ ███████╗╚██████╔╝███████║\n"
        "  ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═══╝  ╚══════╝ ╚═════╝ ╚══════╝"
    )
    console.print(
        Panel.fit(
            f"[bold purple]{banner}[/bold purple]",
            title=f"[bold white]CreativeOS CLI[/bold white]  [dim]v{__version__}[/dim]",
            border_style="purple",
            padding=(1, 2),
        )
    )

    # ── Creation commands ─────────────────────────────────────────────────────
    creation = Table(title="[bold]CREATION[/bold]", box=box.ROUNDED, border_style="cyan",
                     show_header=True, header_style="bold magenta", padding=(0, 1))
    creation.add_column("Command", style="cyan bold", no_wrap=True)
    creation.add_column("Description", style="white")
    creation.add_column("Example", style="dim")
    creation.add_row("new <name>",  "Create a new project from template",  'cos new "My Video" -c Video')
    creation.add_row("clone <url>", "Clone a Git repo and adopt it into OS", "cos clone https://github.com/u/repo")
    creation.add_row("init",        "Adopt current folder as a COS project", "cos init")

    # ── Maintenance commands ──────────────────────────────────────────────────
    maint = Table(title="[bold]MAINTENANCE[/bold]", box=box.ROUNDED, border_style="blue",
                  show_header=True, header_style="bold magenta", padding=(0, 1))
    maint.add_column("Command", style="cyan bold", no_wrap=True)
    maint.add_column("Description", style="white")
    maint.add_column("Example", style="dim")
    maint.add_row("sync",         "Sync project notes with Obsidian vault", "cos sync")
    maint.add_row("thumbs",       "Generate global thumbnail gallery",       "cos thumbs")
    maint.add_row("clean",        "Sort and categorise Downloads folder",    "cos clean")
    maint.add_row("sort-exports", "File Exports/_Inbox into Year/Month",      "cos sort-exports")
    maint.add_row("storage", "Review project storage safely (read-only)", "cos storage")

    # ── Workflow commands ─────────────────────────────────────────────────────
    workflow = Table(title="[bold]WORKFLOW[/bold]", box=box.ROUNDED, border_style="green",
                     show_header=True, header_style="bold magenta", padding=(0, 1))
    workflow.add_column("Command", style="cyan bold", no_wrap=True)
    workflow.add_column("Description", style="white")
    workflow.add_column("Example", style="dim")
    workflow.add_row("export",    "Open the project or month export folder", "cos export")
    workflow.add_row("travel",    "Copy active project to shuttle drive",     "cos travel")
    workflow.add_row("resurrect", "Restore an archived project to active",   "cos resurrect my-film")

    # ── Management commands ─────────────────────────────────────────────────────
    management = Table(title="[bold]MANAGEMENT[/bold]", box=box.ROUNDED, border_style="yellow",
                      show_header=True, header_style="bold magenta", padding=(0, 1))
    management.add_column("Command", style="cyan bold", no_wrap=True)
    management.add_column("Description", style="white")
    management.add_column("Example", style="dim")
    management.add_row("app",        "Launch self-contained desktop app window", "cos app")
    management.add_row("gui",        "Launch CreativeOS Web GUI in browser", "cos gui")
    management.add_row("category",   "Manage project categories (list/add/edit/remove)", "cos category list")
    management.add_row("setup",      "Configure CreativeOS (paths, categories, reset)", "cos setup")
    management.add_row("config",     "View and edit configuration (show/paths/validate)", "cos config show")

    console.print()
    console.print(creation)
    console.print()
    console.print(maint)
    console.print()
    console.print(workflow)
    console.print()
    console.print(management)

    console.print()
    console.print(Panel(
        "[bold]1.[/bold] Set up one low-priority weekly scan:  "
        "[cyan]cos storage schedule --time 01:00[/cyan]\n"
        "[bold]2.[/bold] After it completes, open your instant report:  "
        "[cyan]cos storage[/cyan]\n"
        "[bold]3.[/bold] Find the largest media or code/cache projects:  "
        "[cyan]cos storage review --sort media[/cyan]  /  "
        "[cyan]cos storage review --sort reclaimable[/cyan]\n"
        "[bold]4.[/bold] Rescan a single project instead of everything:  "
        "[cyan]cos storage review --refresh --path Code/Clones/gemini-cli[/cyan]\n\n"
        "Storage review is read-only: it will not archive or delete any file.",
        title="[bold]Storage Quick Start[/bold]",
        border_style="cyan",
        padding=(1, 2),
    ))

    # ── Quick reference footer ────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        "[bold]Usage:[/bold]  cos <command> [options]\n\n"
        "[bold]Command help:[/bold]  cos <command> [bold cyan]--help[/bold cyan]  "
        "or  cos [bold cyan]help[/bold cyan] <command>\n\n"
        "[bold]Examples:[/bold]\n"
        '  cos new "My Film" -c Video          Create video project\n'
        '  cos new "Web App" -c Code --git     Create code project with Git\n'
        "  cos sync                            Sync notes with Obsidian\n"
        "  cos travel                          Copy project to shuttle drive\n"
        "  cos resurrect my-old-film           Restore archived project\n"
        "  cos storage                          Open the saved storage review\n"
        "  cos storage review --refresh --path Code/Clones/gemini-cli\n"
        "                                       Rescan one project fast\n"
        "  cos help storage                     Show storage commands and examples",
        title="[bold]Quick Reference[/bold]",
        border_style="dim",
        padding=(1, 2),
    ))
    console.print()


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point for CreativeOS CLI."""
    sys.excepthook = handle_exception
    
    # First-run detection - check if setup or config command is being run
    # Skip onboarding if user is trying to run setup or config commands
    is_setup_cmd = len(sys.argv) > 1 and sys.argv[1].lower() in ("setup", "config", "category")
    
    # Global help must work before setup, even on a fresh checkout or without a TTY.
    is_help_cmd = any(arg.lower() in ("help", "-h", "--help", "-help", "/help", "/?") for arg in sys.argv[1:])
    if is_first_run() and not is_setup_cmd and not is_help_cmd:
        if not sys.stdin.isatty():
            console.print("[error]CreativeOS needs setup. Run 'cos setup' in a terminal first.[/error]")
            sys.exit(1)
        console.print("[cyan]First run detected! Let's set up CreativeOS...[/cyan]\n")
        config = run_onboarding_wizard(console)
        if not config or not apply_configuration(config):
            console.print("\n[yellow]Setup cancelled or failed. Run 'cos setup' to configure later.[/yellow]\n")
            sys.exit(1)
        console.print("\n[green]Setup complete! You're ready to use CreativeOS.[/green]\n")

    # Support both conventional help forms: `cos help storage` and
    # `cos storage help`. Convert them to argparse's normal `--help` route.
    if len(sys.argv) == 2 and sys.argv[1].lower() == "help":
        show_help_overview()
        sys.exit(0)
    if len(sys.argv) > 2 and sys.argv[1].lower() == "help":
        sys.argv = [sys.argv[0], *sys.argv[2:], "--help"]
    elif len(sys.argv) > 2 and sys.argv[-1].lower() == "help":
        sys.argv = [*sys.argv[:-1], "--help"]

    # Intercept `cos` (no args) or `cos -h` / `cos --help` BEFORE argparse
    # so we can show the full Rich overview instead of the terse argparse output.
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1].lower() in ("-h", "--help", "-help", "/help", "/?")):
        show_help_overview()
        sys.exit(0)

    # Setup and config inspection must remain available without config.json.
    first_run = is_first_run()
    from .commands import setup, config_cmd
    if first_run:
        if sys.argv[1].lower() not in ("setup", "config"):
            if is_help_cmd:
                show_help_overview()
                sys.exit(0)
            console.print("[error]CreativeOS needs setup. Run 'cos setup' first.[/error]")
            sys.exit(1)
    else:
        from .commands import new, clone, init, sync, export, thumbs, clean, sort_exports, travel, resurrect, storage
        from .commands import category, gui, app

    parser = RichArgumentParser(
        prog="cos",
        description="CreativeOS CLI",
        formatter_class=RawTextHelpFormatter,
        # Disable argparse's built-in help so our pre-check above handles it
        add_help=False,
    )
    # Re-add help manually so it appears in subparser listings but routes through
    # our overview function (handled by the pre-check above).
    parser.add_argument(
        "-h", "--help",
        action="store_true",
        default=False,
        help="Show this help message and exit",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="Commands",
        parser_class=RichArgumentParser
    )

    # Only config-independent parsers are loaded until setup is complete.
    if not first_run:
        new.add_parser(subparsers)
        clone.add_parser(subparsers)
        init.add_parser(subparsers)
        export.add_parser(subparsers)
        sync.add_parser(subparsers)
        thumbs.add_parser(subparsers)
        clean.add_parser(subparsers)
        sort_exports.add_parser(subparsers)
        travel.add_parser(subparsers)
        resurrect.add_parser(subparsers)
        storage.add_parser(subparsers)
        gui.add_parser(subparsers)
        app.add_parser(subparsers)
        category.add_parser(subparsers)
    setup.add_parser(subparsers)
    config_cmd.add_parser(subparsers)

    args = parser.parse_args()
    args.category_flag_passed = any(
        arg.lower() in ("-c", "--category", "-category", "--type", "-type")
        or arg.lower().startswith(("--category=", "-category=", "--type=", "-type="))
        for arg in sys.argv
    )

    # Route commands to their handlers
    if first_run:
        if args.command == "setup":
            setup.cmd_setup(args)
        else:
            config_cmd.cmd_config(args)
        return

    if args.command == "new":             new.cmd_new(args)
    elif args.command == "clone":         clone.cmd_clone(args)
    elif args.command == "init":          init.cmd_init(args)
    elif args.command == "export":        export.cmd_export(args)
    elif args.command == "sync":          sync.cmd_sync(args)
    elif args.command == "thumbs":        thumbs.cmd_thumbs(args)
    elif args.command == "clean":         clean.cmd_clean(args)
    elif args.command == "sort-exports":  sort_exports.cmd_sort_exports(args)
    elif args.command == "travel":        travel.cmd_travel(args)
    elif args.command == "resurrect":     resurrect.cmd_resurrect(args)
    elif args.command == "storage":       storage.cmd_storage(args)
    elif args.command == "gui":           gui.cmd_gui(args)
    elif args.command == "app":           app.cmd_app(args)
    elif args.command == "category":      category.cmd_category(args)
    elif args.command == "setup":         setup.cmd_setup(args)
    elif args.command == "config":        config_cmd.cmd_config(args)
    else:
        show_help_overview()
        return

    # This only reads the cached storage index. It never triggers disk traversal.
    if args.command != "storage":
        storage.show_reminder_if_due()


if __name__ == "__main__":
    main()
