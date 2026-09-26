"""Install this CreativeOS checkout for Windows shells.

Run with `python install_cos.py` from the repository root. The installer does
not edit the user PATH or replace configuration without asking first.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BIN = ROOT / "00_System" / "Bin"
ENV = ROOT / ".cos-venv"
CONFIG = ROOT / "00_System" / "Config"


def ask(message: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{message} {suffix} ").strip().lower()
    return default if not answer else answer in {"y", "yes"}


def add_user_path(directory: Path) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
        try:
            current, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, value_type = "", winreg.REG_EXPAND_SZ
        existing = [part for part in current.split(";") if part]
        target = os.path.normcase(os.path.normpath(str(directory)))
        if any(os.path.normcase(os.path.normpath(os.path.expandvars(part))) == target for part in existing):
            print("COS command directory is already on the user PATH.")
            return
        new_value = ";".join([*existing, str(directory)])
        winreg.SetValueEx(key, "Path", 0, value_type, new_value)
    import ctypes

    notify = ctypes.windll.user32.SendMessageTimeoutW
    notify.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_wchar_p,
                       ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t))
    notify.restype = ctypes.c_void_p
    result = ctypes.c_size_t()
    if not notify(0xFFFF, 0x1A, None, "Environment", 0x0002, 5000, ctypes.byref(result)):
        print("PATH saved, but Windows did not refresh it. Sign out and back in if a new terminal cannot find `cos`.")
    else:
        print("Added COS command directory to the user PATH. Open a new terminal to use `cos`.")


def main() -> int:
    if os.name != "nt":
        print("This installer supports Windows only. No changes made.", file=sys.stderr)
        return 1
    if not sys.stdin.isatty():
        print("Installation needs an interactive terminal for setup and PATH consent.", file=sys.stderr)
        return 1

    print(f"Installing CreativeOS from {ROOT}")
    python = ENV / "Scripts" / "python.exe"
    if not python.exists():
        venv.create(ENV, with_pip=True)
    command = ENV / "Scripts" / "cos.exe"
    subprocess.run([str(python), "-m", "pip", "install", "-e", str(ROOT)], check=True)

    print("\nSetup configures project and vault locations.")
    existing = [CONFIG / name for name in ("config.json", "categories.json") if (CONFIG / name).exists()]
    if existing:
        print("Existing configuration found. Setup will replace it only after you confirm in the wizard.")
    if ask("Run the setup wizard now?", default=True):
        if existing:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            for path in existing:
                backup = path.with_name(f"{path.name}.{stamp}.bak")
                if backup.exists():
                    raise FileExistsError(f"Backup already exists: {backup}")
                shutil.copy2(path, backup)
                print(f"Saved backup: {backup}")
        subprocess.run([str(command), "setup"], check=True)
    else:
        print("Skipped setup. Run `cos setup` before creating projects.")

    print(f"\nCommand directory: {BIN}")
    if ask("Add this directory to your user PATH for PowerShell, cmd and Git Bash?"):
        add_user_path(BIN)
    else:
        print("PATH unchanged. Use the launcher in 00_System/Bin or add that directory later.")
    print("Installation finished. Test with `cos --help` in a new terminal.")
    return 0


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
