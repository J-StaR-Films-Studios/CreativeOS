import argparse
import datetime
import os
from pathlib import Path
from typing import Any

from ..config import EXPORTS_PATH
from ..console import console
from ..file_utils import find_meta_in_cwd, format_path, get_export_month_path
from ..security import validate_path_component
from ..storage import _created_date


def add_parser(subparsers: Any) -> None:
    from ..help_formatter import RichHelpAction

    p_exp = subparsers.add_parser(
        "export",
        help="Open the project or monthly export folder",
        description="""\
Open the export destination for the current project (or the current
month's export root if not inside a project).

When run from inside an initialised project, creates the per-project
export structure (Video/, Thumbnail/, Audio/) based on the project's
creation date and opens it in Explorer.
Otherwise opens the current Year/Month export folder.\
""",
        epilog="""\
Examples:
  cos export               Open the project export folder (auto-detected)
  cos export --simple      Open the generic month folder only\
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_exp.add_argument(
        "-s", "--simple",
        action="store_true",
        help="Skip project detection and open the generic monthly export folder.",
    )
    p_exp.add_argument(
        "-h", "--help",
        action=RichHelpAction,
        help="Show this help message and exit.",
    )

def cmd_export(args: argparse.Namespace) -> None:
    """Open the export directory for the project or the current month."""
    meta, project_root = find_meta_in_cwd()
    
    if meta and not args.simple and project_root:
        slug = validate_path_component(
            str(meta.get("slug") or meta.get("name") or Path(project_root).name)
        )
        base_exports = Path(EXPORTS_PATH).resolve()

        # 1. Look for existing export folder
        existing_export = None
        if base_exports.exists():
            for month_dir in base_exports.glob("*/*"):
                candidate = month_dir / slug
                if candidate.is_dir():
                    existing_export = candidate
                    break
            if not existing_export:
                for month_dir in base_exports.glob("*/*/*"):
                    candidate = month_dir / slug
                    if candidate.is_dir():
                        existing_export = candidate
                        break

        if existing_export:
            export_dir = existing_export
        else:
            # 2. Determine target year/month from project creation date
            created_str, _ = _created_date(Path(project_root), meta)
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
            candidate_named = base_exports / target_year / month_full / slug
            candidate_num = base_exports / target_year / target_month_num / slug

            if (base_exports / target_year / month_full).exists():
                export_dir = candidate_named
            elif (base_exports / target_year / target_month_num).exists():
                export_dir = candidate_num
            else:
                export_dir = candidate_named

        export_dir = export_dir.resolve()
        if not export_dir.is_relative_to(base_exports):
            raise ValueError("Export destination must remain inside the exports directory")

        for s in ["Video", "Thumbnail", "Audio"]:
            (export_dir / s).mkdir(parents=True, exist_ok=True)

        console.print(f"📂 Opening Project Export: {format_path(str(export_dir))}")
        os.startfile(str(export_dir))
    else:
        month_path = get_export_month_path()
        console.print(f"📂 Opening Month Export: {format_path(month_path)}")
        os.startfile(month_path)
