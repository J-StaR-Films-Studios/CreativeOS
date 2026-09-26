"""Git operations."""

import os
import sys
import shutil
import subprocess
from rich.prompt import Confirm
from .console import console
from .config import TEMPLATES_PATH

def setup_git(project_path: str, category: str, interactive: bool = False) -> None:
    """
    Initialize a Git repository, add .gitignore, and make initial commit safely without blocking on stdin.
    """
    console.print("   [info]🔧 Initializing Git Repository...[/info]")

    # 1. Run git init
    try:
        subprocess.run(["git", "init"], cwd=project_path, check=True, stdout=subprocess.DEVNULL)
    except FileNotFoundError:
        console.print("   [warning]⚠️  Git is not installed or not in PATH. Skipping.[/warning]")
        return
    except Exception as e:
        console.print(f"   [error]❌ Git init failed: {e}[/error]")
        return

    # 2. Copy .gitignore
    gitignore_src = os.path.join(TEMPLATES_PATH, "universal.gitignore")
    gitignore_dest = os.path.join(project_path, ".gitignore")

    if os.path.exists(gitignore_src):
        shutil.copy2(gitignore_src, gitignore_dest)
    else:
        with open(gitignore_dest, "w") as f:
            f.write("# CreativeOS Auto-Gitignore\nnode_modules/\n__pycache__/\n.env\n")

    console.print("   [success]✅ Git initialized & .gitignore added.[/success]")

    # 3. Initial Commit (Non-blocking by default in GUI/API mode)
    make_commit = True
    if interactive and sys.stdin.isatty():
        try:
            make_commit = Confirm.ask("   Make initial commit now?", default=True)
        except Exception:
            make_commit = True

    if make_commit:
        try:
            subprocess.run(["git", "add", "."], cwd=project_path, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "commit", "-m", "Initial commit via CreativeOS Genesis"], cwd=project_path, check=True, stdout=subprocess.DEVNULL)
            console.print("   [success]✅ Initial commit complete.[/success]")
        except Exception as e:
            console.print(f"   [warning]⚠️  Initial commit skipped/failed: {e}[/warning]")
    else:
        console.print("   [dim]Skipped initial commit.[/dim]")

