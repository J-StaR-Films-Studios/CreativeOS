"""Setup and configuration wizard command.

This module provides the 'cos setup' command for configuring CreativeOS:
- Full setup wizard
- Path-only configuration
- Category-only configuration
- Reset to defaults
"""

import os
import json
import argparse
import logging
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.prompt import Confirm

from ..onboarding import run_onboarding_wizard, apply_configuration
from ..console import console
from ..config import CONFIG_PATH

# Setup logger
logger = logging.getLogger('creativeos')


def add_parser(subparsers: Any) -> None:
    """Add setup command parser.
    
    Args:
        subparsers: argparse subparsers object.
    """
    from ..help_formatter import RichHelpAction
    
    p_setup = subparsers.add_parser(
        "setup",
        help="Configure CreativeOS",
        description="""\
Run the CreativeOS setup wizard to configure paths, categories, and preferences.

This command can be used to:
- Set up CreativeOS for the first time
- Reconfigure paths after moving folders
- Enable or disable categories
- Reset to default configuration\
""",
        epilog="""\
Examples:
  cos setup              Run full setup wizard
  cos setup --paths      Configure only paths
  cos setup --categories Configure only categories
  cos setup --reset      Reset to defaults\
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    
    p_setup.add_argument("--paths", action="store_true", help="Configure only paths")
    p_setup.add_argument("--categories", action="store_true", help="Configure only categories")
    p_setup.add_argument("--reset", action="store_true", help="Reset to default configuration")
    p_setup.add_argument("-h", "--help", action=RichHelpAction, help="Show help")


def cmd_setup(args: argparse.Namespace) -> None:
    """Handle setup command.
    
    Args:
        args: Parsed command line arguments.
    """
    if args.reset:
        cmd_setup_reset()
    elif args.paths:
        cmd_setup_paths()
    elif args.categories:
        cmd_setup_categories()
    else:
        cmd_setup_full()


def cmd_setup_full() -> None:
    """Run full setup wizard."""
    console.print(Panel(
        "[bold cyan]CreativeOS Setup Wizard[/bold cyan]\n\n"
        "This will guide you through configuring CreativeOS.",
        border_style="cyan",
    ))
    
    config = run_onboarding_wizard(console)
    if not config or not apply_configuration(config):
        raise SystemExit(1)
    logger.info("Setup wizard completed successfully")


def cmd_setup_paths() -> None:
    """Configure only paths."""
    try:
        import questionary
    except ImportError:
        console.print("[error]❌ questionary not installed. Run: pip install questionary[/error]")
        return
    
    console.print("[bold cyan]Configure Paths[/bold cyan]\n")
    
    # Load current config
    current: dict = {}
    config_path = Path(CONFIG_PATH)
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                current = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load current config: {e}")
    
    paths: dict = {}
    for key in ["projects_path", "vault_path", "archive_path", "shuttle_path", "exports_path"]:
        current_val = current.get(key, str(Path.home() / "CreativeOS" / key.replace("_path", "").title()))
        new_val = questionary.path(
            f"{key.replace('_', ' ').title()}:",
            default=current_val,
            only_directories=True,
        ).ask()
        if new_val:
            paths[key] = os.path.abspath(new_val)
    
    current.update(paths)
    
    try:
        # Ensure config directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=4)
        
        logger.info("Updated paths configuration")
        console.print("[success]✅ Paths updated![/success]")
    except (IOError, OSError) as e:
        logger.error(f"Failed to save config: {e}")
        console.print(f"[error]❌ Failed to save configuration: {e}[/error]")


def cmd_setup_categories() -> None:
    """Configure only categories."""
    console.print("[bold cyan]Configure Categories[/bold cyan]\n")
    console.print("[dim]Use 'cos category list' to see current categories[/dim]")
    console.print("[dim]Use 'cos category add' to add new categories[/dim]")
    console.print("[dim]Use 'cos category edit' to modify categories[/dim]")
    console.print("[dim]Use 'cos category remove' to remove categories[/dim]")


def cmd_setup_reset() -> None:
    """Reset to defaults."""
    if not Confirm.ask("Reset all configuration to defaults?"):
        console.print("[dim]Cancelled.[/dim]")
        return
    
    config_dir = os.path.dirname(CONFIG_PATH)
    
    for filename in ["config.json", "categories.json"]:
        path = os.path.join(config_dir, filename)
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"Deleted {filename}")
            except OSError as e:
                logger.warning(f"Could not delete {filename}: {e}")
    
    console.print("[success]✅ Configuration reset. Run 'cos setup' to reconfigure.[/success]")
