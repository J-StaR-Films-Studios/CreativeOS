"""Custom Rich-powered help formatter for CreativeOS CLI.

Provides a drop-in argparse Action that renders --help output using Rich
panels, tables, and styled text instead of the default plain-text formatter.
"""

import argparse
import sys
from typing import Any, Optional, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box


class RichHelpAction(argparse.Action):
    """Custom argparse action that displays help using Rich formatting.

    Use this as ``action=RichHelpAction`` (or pass the class via
    ``add_argument``) instead of the built-in ``"help"`` action so that each
    command's ``-h / --help`` output is rendered with Rich panels and tables.
    """

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str = argparse.SUPPRESS,
        default: str = argparse.SUPPRESS,
        help: Optional[str] = None,
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    # ------------------------------------------------------------------
    # Core render
    # ------------------------------------------------------------------

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: Optional[str] = None,
    ) -> None:
        """Render richly-formatted help and exit."""
        console = Console()

        # ── Description ────────────────────────────────────────────────
        if parser.description:
            console.print(
                Panel(
                    parser.description.strip(),
                    title=f"[bold cyan]{parser.prog}[/bold cyan]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )
        else:
            console.print(f"\n[bold cyan]{parser.prog}[/bold cyan]\n")

        # ── Usage ──────────────────────────────────────────────────────
        console.print(f"[bold]Usage:[/bold]  [cyan]{parser.prog}[/cyan] [options]\n")

        # ── Options table ──────────────────────────────────────────────
        positional: list[tuple[str, str]] = []
        optional: list[tuple[str, str]] = []

        for action in parser._actions:
            # Skip the help action itself to avoid recursion in the table
            if isinstance(action, RichHelpAction):
                continue

            flags = ", ".join(action.option_strings) if action.option_strings else action.dest
            help_text = action.help or ""

            # Annotate choices
            if action.choices:
                help_text += f"  [dim]{{{'|'.join(str(c) for c in action.choices)}}}[/dim]"

            # Annotate defaults (only for optional flags, skip SUPPRESS and None)
            if action.option_strings and action.default is not None and action.default is not argparse.SUPPRESS:
                # Don't show True/False defaults for store_true/store_false as they are obvious
                if not isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
                    help_text += f"  [dim](default: {action.default})[/dim]"

            if action.option_strings:
                optional.append((flags, help_text))
            else:
                positional.append((flags, help_text))

        if positional:
            pos_table = Table(
                title="Arguments",
                box=box.ROUNDED,
                border_style="dim",
                show_header=True,
                header_style="bold magenta",
                padding=(0, 1),
            )
            pos_table.add_column("Argument", style="cyan bold", no_wrap=True)
            pos_table.add_column("Description", style="white")
            for flag, desc in positional:
                pos_table.add_row(flag, desc)
            console.print(pos_table)
            console.print()

        if optional:
            opt_table = Table(
                title="Options",
                box=box.ROUNDED,
                border_style="dim",
                show_header=True,
                header_style="bold magenta",
                padding=(0, 1),
            )
            opt_table.add_column("Flag", style="cyan bold", no_wrap=True)
            opt_table.add_column("Description", style="white")
            opt_table.add_row("-h, --help", "Show this help message and exit")
            for flag, desc in optional:
                opt_table.add_row(flag, desc)
            console.print(opt_table)

        # ── Epilog / Examples ──────────────────────────────────────────
        if parser.epilog:
            console.print()
            console.print(
                Panel(
                    parser.epilog.strip(),
                    title="[bold green]Examples[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )

        console.print()
        parser.exit()


class RichArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that uses Rich for errors and usage, and provides case-insensitive/PowerShell-tolerant argument normalization."""

    def parse_known_args(
        self,
        args: Optional[Sequence[str]] = None,
        namespace: Optional[argparse.Namespace] = None,
    ) -> tuple[argparse.Namespace, list[str]]:
        """Normalize arguments for case-insensitivity and PowerShell single-dash flags before parsing."""
        if args is None:
            raw_args = list(sys.argv[1:])
        else:
            raw_args = list(args)

        normalized_args = normalize_cli_args(raw_args, self)
        return super().parse_known_args(normalized_args, namespace)

    def error(self, message: str) -> None:
        """Override error to show a beautiful Rich panel with fuzzy suggestions and tips."""
        from rich.console import Console
        from rich.panel import Panel
        console = Console()
        
        formatted_error = format_cli_error(self, message)
        console.print(
            Panel(
                formatted_error,
                title="[bold red]Invalid Command[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
        )
        self.exit(2)

    def print_usage(self, file: Any = None) -> None:
        """Override usage to be cleaner."""
        from rich.console import Console
        console = Console()
        console.print(f"[bold]Usage:[/bold] [cyan]{self.prog}[/cyan] [options]")


def format_cli_error(parser: argparse.ArgumentParser, message: str) -> str:
    """Analyze argparse error message and append intelligent 'Did you mean?' suggestions and tips."""
    import difflib
    import re

    suggestions: list[str] = []
    tips: list[str] = []

    # Collect all known flags and subcommands for fuzzy matching
    all_info = _collect_all_options(parser)
    all_long_flags = list(all_info["long_opts"].values())
    all_short_flags = list(all_info["short_opts"].values())
    all_flags = sorted(set(all_long_flags + all_short_flags))

    # Collect subcommand names
    subcommand_names: list[str] = []
    def _collect_subcmds(p: argparse.ArgumentParser, visited: set[int]) -> None:
        if id(p) in visited:
            return
        visited.add(id(p))
        info = _collect_parser_info(p)
        for name, child in info["subparsers"].values():
            subcommand_names.append(name)
            _collect_subcmds(child, visited)
    _collect_subcmds(parser, set())

    # 1. Check for unrecognized arguments
    if "unrecognized argument" in message:
        match = re.search(r"unrecognized arguments?:\s*(.*)", message, re.IGNORECASE)
        if match:
            raw_tokens = match.group(1).split()
            for token in raw_tokens:
                if token.startswith("-"):
                    cleaned = token.lstrip("-").lower()
                    if token.startswith("-") and not token.startswith("--") and len(token) > 2:
                        tips.append(
                            "💡 [dim]Tip: Full-word flags use double dashes (e.g., [bold cyan]--client[/bold cyan]). "
                            "Single dash ([bold cyan]-[/bold cyan]) is reserved for single-letter flags (e.g., [bold cyan]-c[/bold cyan]).[/dim]"
                        )

                    flag_names_no_dash = {f.lstrip("-").lower(): f for f in all_flags}
                    closest = difflib.get_close_matches(cleaned, list(flag_names_no_dash.keys()), n=2, cutoff=0.6)
                    if closest:
                        matched_flags = [flag_names_no_dash[c] for c in closest]
                        suggestions.append(f"Did you mean: {', '.join(f'[bold yellow]{f}[/bold yellow]' for f in matched_flags)}?")
                    else:
                        closest_full = difflib.get_close_matches(token.lower(), [f.lower() for f in all_flags], n=2, cutoff=0.6)
                        if closest_full:
                            c_map = {f.lower(): f for f in all_flags}
                            matched_flags = [c_map[c] for c in closest_full if c in c_map]
                            suggestions.append(f"Did you mean: {', '.join(f'[bold yellow]{f}[/bold yellow]' for f in matched_flags)}?")
                else:
                    closest_cmds = difflib.get_close_matches(token.lower(), [s.lower() for s in subcommand_names], n=2, cutoff=0.6)
                    if closest_cmds:
                        c_map = {s.lower(): s for s in subcommand_names}
                        matched_cmds = [c_map[c] for c in closest_cmds if c in c_map]
                        suggestions.append(f"Did you mean command: {', '.join(f'[bold yellow]{c}[/bold yellow]' for c in matched_cmds)}?")

    # 2. Check for invalid choice
    if "invalid choice:" in message:
        choice_match = re.search(r"invalid choice:\s*'([^']+)'\s*\(choose from\s*(.+?)\)", message)
        if choice_match:
            invalid_val = choice_match.group(1)
            valid_raw = choice_match.group(2)
            valid_choices = [c.strip(" '\"") for c in valid_raw.split(",")]
            closest = difflib.get_close_matches(invalid_val.lower(), [v.lower() for v in valid_choices], n=2, cutoff=0.6)
            if closest:
                c_map = {v.lower(): v for v in valid_choices}
                matched_choices = [c_map[c] for c in closest if c in c_map]
                suggestions.append(f"Did you mean: {', '.join(f'[bold yellow]{c}[/bold yellow]' for c in matched_choices)}?")

    # 3. Also scan raw command line arguments in sys.argv for any misspelled flags
    raw_argv_tokens = [arg for arg in sys.argv[1:] if arg.startswith("-") and len(arg) > 1]
    for token in raw_argv_tokens:
        flag_no_val = token.split("=")[0]
        cleaned = flag_no_val.lstrip("-").lower()
        flag_names_no_dash = {f.lstrip("-").lower(): f for f in all_flags}
        # If this token is not directly recognized as a valid flag
        if cleaned not in flag_names_no_dash and flag_no_val.lower() not in [f.lower() for f in all_flags]:
            closest = difflib.get_close_matches(cleaned, list(flag_names_no_dash.keys()), n=2, cutoff=0.6)
            if closest:
                matched_flags = [flag_names_no_dash[c] for c in closest]
                suggestions.append(f"Did you mean: {', '.join(f'[bold yellow]{f}[/bold yellow]' for f in matched_flags)}?")
                if flag_no_val.startswith("-") and not flag_no_val.startswith("--") and len(flag_no_val) > 2:
                    tips.append(
                        "💡 [dim]Tip: Full-word flags use double dashes (e.g., [bold cyan]--client[/bold cyan]). "
                        "Single dash ([bold cyan]-[/bold cyan]) is reserved for single-letter flags (e.g., [bold cyan]-c[/bold cyan]).[/dim]"
                    )

    parts = [f"[bold red]Error:[/bold red] {message}"]
    if suggestions:
        seen_sug = set()
        unique_suggestions = [s for s in suggestions if not (s in seen_sug or seen_sug.add(s))]
        parts.append("\n" + "\n".join(unique_suggestions))
    if tips:
        seen_tips = set()
        unique_tips = [t for t in tips if not (t in seen_tips or seen_tips.add(t))]
        parts.append("\n" + "\n".join(unique_tips))

    parts.append(f"\n[dim]Run [bold cyan]{parser.prog} -h[/bold cyan] for full usage details.[/dim]")
    return "\n".join(parts)


def _collect_parser_info(parser: argparse.ArgumentParser) -> dict[str, Any]:
    """Extract flags and subparsers from an ArgumentParser."""
    long_opts: dict[str, str] = {}    # lower_name -> canonical_flag (e.g. 'client' -> '--client')
    short_opts: dict[str, str] = {}   # lower_char -> canonical_flag (e.g. 'c' -> '-c')
    subparsers: dict[str, tuple[str, argparse.ArgumentParser]] = {} # lower_cmd -> (canonical_name, child_parser)

    for action in getattr(parser, "_actions", []):
        if isinstance(action, argparse._SubParsersAction):
            for name, subp in action.choices.items():
                subparsers[name.lower()] = (name, subp)
        for opt in getattr(action, "option_strings", []):
            if opt.startswith("--"):
                long_opts[opt[2:].lower()] = opt
            elif opt.startswith("-"):
                if len(opt) == 2:
                    short_opts[opt[1].lower()] = opt
                else:
                    long_opts[opt[1:].lower()] = opt

    return {
        "long_opts": long_opts,
        "short_opts": short_opts,
        "subparsers": subparsers,
    }


def _collect_all_options(parser: argparse.ArgumentParser) -> dict[str, Any]:
    """Collect all known options across the entire parser tree."""
    all_long: dict[str, str] = {}
    all_short: dict[str, str] = {}

    def _walk(p: argparse.ArgumentParser, visited: set[int]) -> None:
        if id(p) in visited:
            return
        visited.add(id(p))
        info = _collect_parser_info(p)
        all_long.update(info["long_opts"])
        all_short.update(info["short_opts"])
        for _, child in info["subparsers"].values():
            _walk(child, visited)

    _walk(parser, set())
    return {
        "long_opts": all_long,
        "short_opts": all_short,
    }


def normalize_cli_args(args: Sequence[str], root_parser: argparse.ArgumentParser) -> list[str]:
    """Normalize CLI arguments to be case-insensitive and support PowerShell-style single-dash flags.

    Preserves exact casing for positional arguments and option values.
    """
    if not args:
        return []

    import re

    global_info = _collect_all_options(root_parser)
    current_parser = root_parser
    normalized: list[str] = []
    in_options = True

    for token in args:
        if not in_options:
            normalized.append(token)
            continue

        if token == "--":
            in_options = False
            normalized.append(token)
            continue

        # Common Windows help aliases
        if token.lower() in ("/?", "/h", "/help", "-help"):
            normalized.append("--help")
            continue

        # Check if token is a flag
        if token.startswith("-") and len(token) > 1:
            # Check if numeric (e.g. -1, -5.5)
            if re.match(r"^-\d+(\.\d+)?$", token):
                normalized.append(token)
                continue

            # Split on '=' if present
            if "=" in token:
                flag_part, val_part = token.split("=", 1)
            else:
                flag_part, val_part = token, None

            info = _collect_parser_info(current_parser)
            normalized_flag: Optional[str] = None

            if flag_part.startswith("--"):
                name = flag_part[2:].lower()
                if name in info["long_opts"]:
                    normalized_flag = info["long_opts"][name]
                elif name in global_info["long_opts"]:
                    normalized_flag = global_info["long_opts"][name]
                else:
                    normalized_flag = flag_part

            elif flag_part.startswith("-"):
                name = flag_part[1:]
                name_lower = name.lower()

                # Case 1: Single character short flag (-c, -C, -s, -S)
                if len(name) == 1:
                    if name_lower in info["short_opts"]:
                        normalized_flag = info["short_opts"][name_lower]
                    elif name_lower in global_info["short_opts"]:
                        normalized_flag = global_info["short_opts"][name_lower]
                    else:
                        normalized_flag = flag_part

                # Case 2: PowerShell style single-dash long flag (-Client, -client, -category)
                elif name_lower in info["long_opts"]:
                    normalized_flag = info["long_opts"][name_lower]
                elif name_lower in global_info["long_opts"]:
                    normalized_flag = global_info["long_opts"][name_lower]

                # Case 3: Clustered short flags (-sg, -SG, -sv)
                elif all(c.lower() in info["short_opts"] or c.lower() in global_info["short_opts"] for c in name):
                    normalized_chars = []
                    for c in name:
                        cl = c.lower()
                        if cl in info["short_opts"]:
                            normalized_chars.append(info["short_opts"][cl][1])
                        elif cl in global_info["short_opts"]:
                            normalized_chars.append(global_info["short_opts"][cl][1])
                        else:
                            normalized_chars.append(c)
                    normalized_flag = "-" + "".join(normalized_chars)
                else:
                    normalized_flag = flag_part

            if val_part is not None:
                normalized.append(f"{normalized_flag}={val_part}")
            else:
                normalized.append(normalized_flag if normalized_flag is not None else flag_part)

        else:
            # Does not start with '-'
            info = _collect_parser_info(current_parser)
            token_lower = token.lower()

            # Check if it matches a subcommand in the current parser
            if token_lower in info["subparsers"]:
                canonical_name, child_parser = info["subparsers"][token_lower]
                normalized.append(canonical_name)
                current_parser = child_parser
            else:
                # Positional argument or value: preserve exact casing
                normalized.append(token)

    return normalized
