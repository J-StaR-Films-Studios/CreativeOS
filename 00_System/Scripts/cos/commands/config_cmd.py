"""Configuration management command.

This module provides the 'cos config' command for viewing and editing
CreativeOS configuration:
- show: Display current configuration
- edit: Open config in default editor
- paths: Show all configured paths
- validate: Check configuration validity
"""

import os
import json
import argparse
import subprocess
import logging
from pathlib import Path
from typing import Any, List

from rich.panel import Panel
from rich.table import Table
from rich import box

from ..config import CONFIG_PATH
from ..console import console
from ..category_config import get_categories_path

# Setup logger
logger = logging.getLogger('creativeos')


def add_parser(subparsers: Any) -> None:
    """Add config command parser.
    
    Args:
        subparsers: argparse subparsers object.
    """
    from ..help_formatter import RichHelpAction
    
    p_config = subparsers.add_parser(
        "config",
        help="View and edit configuration",
        description="View and edit CreativeOS configuration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    
    config_subparsers = p_config.add_subparsers(dest="config_action", title="Actions")
    
    # config show
    p_show = config_subparsers.add_parser("show", help="Show current configuration")
    p_show.add_argument("--full", action="store_true", help="Show all settings including defaults")
    
    # config edit
    p_edit = config_subparsers.add_parser("edit", help="Open config in editor")
    
    # config paths
    p_paths = config_subparsers.add_parser("paths", help="Show configured paths")
    
    # config validate
    p_validate = config_subparsers.add_parser("validate", help="Validate configuration")
    
    p_config.add_argument("-h", "--help", action=RichHelpAction, help="Show help")


def cmd_config(args: argparse.Namespace) -> None:
    """Handle config commands.
    
    Args:
        args: Parsed command line arguments.
    """
    if args.config_action == "show":
        cmd_config_show(args)
    elif args.config_action == "edit":
        cmd_config_edit(args)
    elif args.config_action == "paths":
        cmd_config_paths(args)
    elif args.config_action == "validate":
        cmd_config_validate(args)
    elif args.config_action is None:
        # No action specified - show helpful guidance
        console.print(Panel(
            "[bold]No action specified for 'cos config'[/bold]\n\n"
            "Available actions:\n"
            "  [cyan]cos config show[/cyan]     - Display current configuration\n"
            "  [cyan]cos config edit[/cyan]    - Open config in editor\n"
            "  [cyan]cos config paths[/cyan]   - Show configured paths\n"
            "  [cyan]cos config validate[/cyan] - Check configuration validity\n\n"
            "Run '[cyan]cos config show -h[/cyan]' for more options.",
            title="[yellow]Config Command Help[/yellow]",
            border_style="yellow",
        ))
    else:
        # Default to show
        cmd_config_show(args)


def cmd_config_show(args: argparse.Namespace) -> None:
    """Show current configuration.
    
    Args:
        args: Parsed command line arguments.
    """
    # Use getattr to safely access optional arguments
    show_full = getattr(args, 'full', False)
    
    config_path = Path(CONFIG_PATH)
    if not config_path.exists():
        console.print("[warning]No configuration found. Run 'cos setup' to create one.[/warning]")
        return
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[error]❌ Invalid JSON in config.json: {e}[/error]")
        return
    except IOError as e:
        console.print(f"[error]❌ Could not read config.json: {e}[/error]")
        return
    
    table = Table(title="CreativeOS Configuration", box=box.ROUNDED)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")
    
    for key, value in config.items():
        if not show_full and isinstance(value, str) and len(value) > 50:
            value = value[:47] + "..."
        table.add_row(key, str(value))
    
    console.print(table)


def cmd_config_edit(args: argparse.Namespace) -> None:
    """Open config in default editor.
    
    Args:
        args: Parsed command line arguments.
    """
    config_path = Path(CONFIG_PATH)
    if not config_path.exists():
        console.print("[warning]No configuration found. Run 'cos setup' to create one.[/warning]")
        return
    
    # Determine editor
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "notepad"
    
    console.print(f"[dim]Opening config in {editor}...[/dim]")
    logger.info(f"Opening config in editor: {editor}")
    
    try:
        subprocess.run([editor, str(config_path)])
    except FileNotFoundError:
        console.print(f"[error]❌ Editor '{editor}' not found. Set EDITOR environment variable.[/error]")
    except subprocess.SubprocessError as e:
        logger.error(f"Failed to open editor: {e}")
        console.print(f"[error]❌ Failed to open editor: {e}[/error]")


def cmd_config_paths(args: argparse.Namespace) -> None:
    """Show configured paths.
    
    Args:
        args: Parsed command line arguments.
    """
    config_path = Path(CONFIG_PATH)
    if not config_path.exists():
        console.print("[warning]No configuration found. Run 'cos setup' to create one.[/warning]")
        return
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[error]❌ Invalid JSON in config.json: {e}[/error]")
        return
    except IOError as e:
        console.print(f"[error]❌ Could not read config.json: {e}[/error]")
        return
    
    table = Table(title="Configured Paths", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="white")
    table.add_column("Exists", style="green")
    
    path_keys = ["projects_path", "vault_path", "archive_path", "shuttle_path", "exports_path", "templates_path"]
    
    for key in path_keys:
        path = config.get(key, "Not configured")
        exists = "OK" if os.path.exists(path) else "--"
        exists_style = "green" if os.path.exists(path) else "red"
        table.add_row(key, path, f"[{exists_style}]{exists}[/{exists_style}]")
    
    console.print(table)


def cmd_config_validate(args: argparse.Namespace) -> None:
    """Validate configuration.
    
    Args:
        args: Parsed command line arguments.
    """
    issues: List[str] = []
    
    # Check config.json exists
    config_path = Path(CONFIG_PATH)
    if not config_path.exists():
        console.print("[error]❌ config.json not found[/error]")
        raise SystemExit(1)
    
    # Load and validate config.json
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[error]❌ Invalid JSON in config.json: {e}[/error]")
        raise SystemExit(1) from e
    except IOError as e:
        console.print(f"[error]❌ Could not read config.json: {e}[/error]")
        raise SystemExit(1) from e
    
    # Check required keys
    required_keys = ["projects_path", "templates_path"]
    for key in required_keys:
        if key not in config:
            issues.append(f"Missing required key: {key}")
    
    # Check paths exist
    for key, path in config.items():
        if key.endswith("_path") and isinstance(path, str):
            if not os.path.exists(path):
                issues.append(f"{key} does not exist: {path}")
    
    # Check categories.json
    cat_path = Path(get_categories_path())
    if not cat_path.exists():
        issues.append("categories.json not found")
    else:
        try:
            with open(cat_path, "r", encoding="utf-8") as f:
                cat_config = json.load(f)
            if "categories" not in cat_config:
                issues.append("categories.json missing 'categories' key")
            elif not cat_config["categories"]:
                issues.append("categories.json has no categories defined")
        except json.JSONDecodeError as e:
            issues.append(f"Invalid JSON in categories.json: {e}")
        except IOError as e:
            issues.append(f"Could not read categories.json: {e}")
    
    # Report results
    if issues:
        console.print("[warning]Configuration issues found:[/warning]")
        for issue in issues:
            console.print(f"  [red]•[/red] {issue}")
        logger.warning(f"Configuration validation failed with {len(issues)} issues")
        raise SystemExit(1)
    else:
        console.print("[success]Configuration is valid![/success]")
        logger.info("Configuration validation passed")
