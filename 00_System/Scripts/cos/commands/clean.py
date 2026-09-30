"""Clean command."""

import os
import argparse
import shutil
from typing import Any

from rich.table import Table
from rich import box

from ..console import console
from ..config import DOWNLOADS_PATH
from ..file_utils import format_path

DOWNLOADS_MAPPING = {
    "_Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".tiff", ".bmp"],
    "_Video": [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"],
    "_Audio": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"],
    "_Docs": [".pdf", ".docx", ".txt", ".xlsx", ".pptx", ".csv", ".md"],
    "_Installers": [".exe", ".msi", ".iso", ".dmg"],
    "_Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "_Fonts": [".ttf", ".otf", ".woff", ".woff2"],
    "_3D": [".blend", ".fbx", ".obj", ".stl", ".gltf"],
}

def add_parser(subparsers: Any) -> None:
    from ..help_formatter import RichHelpAction

    p_clean = subparsers.add_parser(
        "clean",
        help="Sort and categorise the Downloads folder",
        description="""\
Sort loose files in your Downloads folder into categorised subfolders.
Files are moved (not copied) based on their extension:

  _Images      .jpg .jpeg .png .gif .webp .svg .tiff .bmp
  _Video       .mp4 .mov .avi .mkv .webm .flv .wmv
  _Audio       .mp3 .wav .aac .flac .ogg .m4a
  _Docs        .pdf .docx .txt .xlsx .pptx .csv .md
  _Installers  .exe .msi .iso .dmg
  _Archives    .zip .rar .7z .tar .gz
  _Fonts       .ttf .otf .woff .woff2
  _3D          .blend .fbx .obj .stl .gltf
  _Other       (everything else)

Hidden files (starting with .) are always left untouched.\
""",
        epilog="""\
Examples:
  cos clean          Sort the Downloads folder\
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_clean.add_argument(
        "-h", "--help",
        action=RichHelpAction,
        help="Show this help message and exit.",
    )

def cmd_clean(args: argparse.Namespace) -> None:
    """Sort a specified folder (usually Downloads) into categorized subfolders."""
    target_path = getattr(args, 'target', DOWNLOADS_PATH) if hasattr(args, 'target') and args.target else DOWNLOADS_PATH

    console.print(f"[bold cyan]🧹 Cleaning: {format_path(target_path)}...[/bold cyan]")
    if not os.path.exists(target_path):
        console.print(f"[error]❌ Error: Path not found: {target_path}[/error]")
        return

    results_table = Table(title="Cleanup Summary", box=box.SIMPLE)
    results_table.add_column("File", style="white")
    results_table.add_column("Moved To", style="cyan")

    count = 0
    for item in os.listdir(target_path):
        if item.startswith("."): continue 

        item_path = os.path.join(target_path, item)

        if os.path.isfile(item_path):
            ext = os.path.splitext(item)[1].lower()
            target_folder = None

            for folder, extensions in DOWNLOADS_MAPPING.items():
                if ext in extensions:
                    target_folder = folder
                    break

            if not target_folder:
                target_folder = "_Other"

            if target_folder:
                dest_dir = os.path.join(target_path, target_folder)
                if not os.path.exists(dest_dir): os.makedirs(dest_dir)

                try:
                    shutil.move(item_path, os.path.join(dest_dir, item))
                    count += 1
                    results_table.add_row(item, target_folder)
                except Exception as e:
                    console.print(f"[error]⚠️ Could not move {item}: {e}[/error]")

    if count > 0:
        console.print(results_table)
        console.print(f"[success]✨ Cleanup Complete. {count} files moved.[/success]")
    else:
        console.print("[info]No files needed moving.[/info]")

    os.startfile(target_path)
