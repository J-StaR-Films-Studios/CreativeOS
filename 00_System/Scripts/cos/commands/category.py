"""Category management commands.

This module provides CLI commands for managing project categories:
- list: Show all categories
- add: Create a new category with optional template
- edit: Modify category settings
- remove: Delete a category
"""

import os
import json
import shutil
import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box

from ..config import TEMPLATES_PATH, CONFIG_PATH
from ..console import console
from ..security import sanitize_path_input
from ..category_config import (
    load_categories,
    save_categories,
    get_categories_path,
    get_default_category,
)

# Setup logger
logger = logging.getLogger('creativeos')


def _get_safe_icon(icon: str) -> str:
    """Get a terminal-safe icon, converting emoji to ASCII on Windows.
    
    Args:
        icon: The icon string (may contain emoji).
        
    Returns:
        A terminal-safe icon string.
    """
    # Emoji to ASCII mapping for Windows compatibility
    emoji_map = {
        "🎬": "[V]",  # Video
        "💻": "[C]",  # Code
        "🎵": "[A]",  # Audio/Music
        "🤖": "[AI]", # AI
        "🎨": "[D]",  # Design
        "📷": "[P]",  # Photo
        "✍️": "[W]",  # Writing
        "🎙️": "[P]",  # Podcast
        "📚": "[L]",  # Course/Learning
        "👥": "[CL]", # Client
        "🎮": "[G]",  # Game
        "📱": "[M]",  # Mobile
        "🔧": "[T]",  # Tool
        "📊": "[B]",  # Business
        "🎯": "[X]",  # Custom
        "📁": "[ ]",  # Default/Generic
    }
    
    # Check if we're on Windows with legacy console (emoji issues)
    if sys.platform == 'win32':
        return emoji_map.get(icon, "[ ]")
    return icon


def add_parser(subparsers: Any) -> None:
    """Add category command parsers.
    
    Args:
        subparsers: argparse subparsers object.
    """
    from ..help_formatter import RichHelpAction
    
    # Main category command
    p_cat = subparsers.add_parser(
        "category",
        help="Manage project categories",
        description="Manage project categories - add, edit, list, or remove categories.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    
    # Subcommands for category
    cat_subparsers = p_cat.add_subparsers(dest="category_action", title="Actions")
    
    # category list
    p_list = cat_subparsers.add_parser(
        "list",
        help="List all categories",
        description="Display all configured categories with their settings.",
    )
    p_list.add_argument("--enabled", action="store_true", help="Show only enabled categories")
    p_list.add_argument("-v", "--verbose", action="store_true", help="Show full details")
    
    # category add
    p_add = cat_subparsers.add_parser(
        "add",
        help="Add a new category",
        description="Add a new project category with optional template creation.",
    )
    p_add.add_argument("name", help="Category name (e.g., '3D', 'Animation')")
    p_add.add_argument("--template", help="Template name (default: <name>_project)")
    p_add.add_argument("--folder", help="Physical folder name (default: category name)")
    p_add.add_argument("--icon", default="📁", help="Emoji icon for the category")
    p_add.add_argument("--description", help="Category description")
    p_add.add_argument("--aliases", nargs="+", help="Alternative names for this category")
    p_add.add_argument("--create-template", action="store_true", help="Create template folder")
    
    # category edit
    p_edit = cat_subparsers.add_parser(
        "edit",
        help="Edit a category",
        description="Modify an existing category's settings.",
    )
    p_edit.add_argument("name", help="Category to edit")
    p_edit.add_argument("--template", help="New template name")
    p_edit.add_argument("--folder", help="New physical folder name")
    p_edit.add_argument("--icon", help="New icon")
    p_edit.add_argument("--description", help="New category description")
    p_edit.add_argument("--enable", dest="enabled", action="store_true", default=None, help="Enable category")
    p_edit.add_argument("--disable", dest="enabled", action="store_false", help="Disable category")
    p_edit.add_argument("--default", action="store_true", help="Set as default category")
    
    # category remove
    p_remove = cat_subparsers.add_parser(
        "remove",
        help="Remove a category",
        description="Remove a category from configuration.",
    )
    p_remove.add_argument("name", help="Category to remove")
    p_remove.add_argument("--force", action="store_true", help="Skip confirmation")
    p_remove.add_argument("--keep-template", action="store_true", help="Don't delete template folder")
    
    # Add help flag
    p_cat.add_argument("-h", "--help", action=RichHelpAction, help="Show help")


def cmd_category(args: argparse.Namespace) -> None:
    """Handle category commands.
    
    Args:
        args: Parsed command line arguments.
    """
    if args.category_action == "list":
        cmd_category_list(args)
    elif args.category_action == "add":
        cmd_category_add(args)
    elif args.category_action == "edit":
        cmd_category_edit(args)
    elif args.category_action == "remove":
        cmd_category_remove(args)
    elif args.category_action is None:
        # No action specified - show helpful guidance
        console.print(Panel(
            "[bold]No action specified for 'cos category'[/bold]\n\n"
            "Available actions:\n"
            "  [cyan]cos category list[/cyan]   - Show all categories\n"
            "  [cyan]cos category add[/cyan]    - Add a new category\n"
            "  [cyan]cos category edit[/cyan]   - Edit a category\n"
            "  [cyan]cos category remove[/cyan] - Remove a category\n\n"
            "Run '[cyan]cos category list -h[/cyan]' for more options.",
            title="[yellow]Category Command Help[/yellow]",
            border_style="yellow",
        ))
    else:
        # Default to list
        cmd_category_list(args)


def cmd_category_list(args: argparse.Namespace) -> None:
    """List all categories.
    
    Args:
        args: Parsed command line arguments.
    """
    config = load_categories()
    categories = config.get("categories", {})
    default_cat = config.get("default_category", "Video")
    
    if not categories:
        console.print("[warning]No categories configured. Run 'cos setup' to get started.[/warning]")
        return
    
    table = Table(title="Project Categories", box=box.ROUNDED)
    table.add_column("Icon", style="white", width=4)
    table.add_column("Category", style="cyan bold")
    table.add_column("Template", style="dim")
    table.add_column("Folder", style="dim")
    table.add_column("Status", style="green")
    table.add_column("Default", style="yellow")
    
    # Use getattr to safely access optional arguments that may not exist
    # when no subcommand is explicitly provided
    show_enabled_only = getattr(args, 'enabled', False)
    verbose = getattr(args, 'verbose', False)
    
    for name, cat in categories.items():
        if show_enabled_only and not cat.get("enabled", True):
            continue
        
        status = "OK" if cat.get("enabled", True) else "--"
        status_style = "green" if cat.get("enabled", True) else "red"
        is_default = "*" if name == default_cat else ""
        
        table.add_row(
            _get_safe_icon(cat.get("icon", "📁")),
            name,
            cat.get("template", f"{name.lower()}_project"),
            cat.get("physical_folder", name),
            f"[{status_style}]{status}[/{status_style}]",
            is_default,
        )
    
    console.print(table)
    
    if verbose:
        console.print()
        for name, cat in categories.items():
            if cat.get("aliases"):
                console.print(f"[dim]{name} aliases: {', '.join(cat['aliases'])}[/dim]")
            if cat.get("description"):
                console.print(f"[dim]{name}: {cat['description']}[/dim]")


def cmd_category_add(args: argparse.Namespace) -> None:
    """Add a new category.
    
    Args:
        args: Parsed command line arguments.
    """
    try:
        safe_name = sanitize_path_input(args.name)
    except ValueError as e:
        console.print(f"[error]❌ Invalid category name: {e}[/error]")
        return
    
    config = load_categories()
    categories = config.get("categories", {})
    
    if safe_name in categories:
        console.print(f"[warning]⚠️  Category '{safe_name}' already exists.[/warning]")
        return
    
    # Create category config
    new_cat = {
        "template": args.template or f"{safe_name.lower()}_project",
        "physical_folder": args.folder or safe_name,
        "aliases": args.aliases or [],
        "description": args.description or f"{safe_name} projects",
        "icon": args.icon,
        "enabled": True,
        "folder_structure": ["00_Notes", "01_Work", "02_Exports"],
    }
    
    categories[safe_name] = new_cat
    config["categories"] = categories
    save_categories(config)
    
    logger.info(f"Added category: {safe_name}")
    console.print(f"[success]✅ Added category '{safe_name}'[/success]")
    
    # Create template folder if requested
    if args.create_template:
        template_path = Path(TEMPLATES_PATH) / new_cat["template"]
        if not template_path.exists():
            template_path.mkdir(parents=True)
            
            # Create structure.json
            structure = {folder: [] for folder in new_cat["folder_structure"]}
            with open(template_path / "structure.json", "w", encoding="utf-8") as f:
                json.dump(structure, f, indent=2, ensure_ascii=False)
            
            # Create 00_Notes with Idea.md
            notes_dir = template_path / "00_Notes"
            notes_dir.mkdir(exist_ok=True)
            with open(notes_dir / "Idea.md", "w", encoding="utf-8") as f:
                f.write(f"# {{PROJECT_NAME}}\n\nType: {safe_name}\nCreated: {{DATE}}\n")
            
            logger.info(f"Created template: {new_cat['template']}")
            console.print(f"[success]✅ Created template: {new_cat['template']}[/success]")
        else:
            console.print(f"[dim]Template folder already exists: {new_cat['template']}[/dim]")


def cmd_category_edit(args: argparse.Namespace) -> None:
    """Edit an existing category.
    
    Args:
        args: Parsed command line arguments.
    """
    config = load_categories()
    categories = config.get("categories", {})
    
    if args.name not in categories:
        console.print(f"[error]❌ Category '{args.name}' not found.[/error]")
        return
    
    cat = categories[args.name]
    
    if args.template:
        cat["template"] = args.template
    if args.folder:
        cat["physical_folder"] = args.folder
    if args.icon:
        cat["icon"] = args.icon
    if args.description:
        cat["description"] = args.description
    if args.enabled is not None:
        cat["enabled"] = args.enabled
    
    if args.default:
        config["default_category"] = args.name
    
    config["categories"] = categories
    save_categories(config)
    
    logger.info(f"Updated category: {args.name}")
    console.print(f"[success]✅ Updated category '{args.name}'[/success]")
    
    if args.default:
        console.print(f"[success]✅ Set '{args.name}' as default category[/success]")


def cmd_category_remove(args: argparse.Namespace) -> None:
    """Remove a category.
    
    Args:
        args: Parsed command line arguments.
    """
    config = load_categories()
    categories = config.get("categories", {})
    
    if args.name not in categories:
        console.print(f"[error]❌ Category '{args.name}' not found.[/error]")
        return
    
    # Check if it's the default category
    if config.get("default_category") == args.name:
        console.print("[warning]⚠️  This is the default category. Set another default first.[/warning]")
        return
    
    # Confirm deletion
    if not args.force:
        if not Confirm.ask(f"Remove category '{args.name}'?"):
            console.print("[dim]Cancelled.[/dim]")
            return
    
    cat = categories[args.name]
    del categories[args.name]
    config["categories"] = categories
    save_categories(config)
    
    logger.info(f"Removed category: {args.name}")
    console.print(f"[success]✅ Removed category '{args.name}'[/success]")
    
    # Optionally remove template folder
    if not args.keep_template:
        template_path = Path(TEMPLATES_PATH) / cat.get("template", "")
        if template_path.exists():
            if args.force or Confirm.ask(f"Also delete template folder '{cat.get('template')}'?"):
                shutil.rmtree(template_path)
                logger.info(f"Deleted template folder: {cat.get('template')}")
                console.print(f"[success]✅ Deleted template folder[/success]")
