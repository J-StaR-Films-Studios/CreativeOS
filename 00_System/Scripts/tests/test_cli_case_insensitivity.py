"""Tests for case-insensitivity and argument normalization in CreativeOS CLI."""

import pytest
from cos.help_formatter import RichArgumentParser, normalize_cli_args
from cos.commands import (
    new, clone, init, export, sync, thumbs, clean, sort_exports,
    travel, resurrect, storage, gui, app, category, setup, config_cmd
)


def _build_test_cli_parser() -> RichArgumentParser:
    """Build the complete CLI parser tree for testing."""
    parser = RichArgumentParser(prog="cos", add_help=False)
    parser.add_argument("-h", "--help", action="store_true", default=False)
    subparsers = parser.add_subparsers(dest="command", parser_class=RichArgumentParser)

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

    return parser


class TestCliNormalization:
    """Test unit normalization of arguments."""

    def test_powershell_single_dash_long_flag(self):
        parser = _build_test_cli_parser()
        args = ["new", "AI Facial Data Collection", "-Client", "Micro1.ai", "-c", "Photo", "-s"]
        parsed = parser.parse_args(args)
        assert parsed.command == "new"
        assert parsed.name == "AI Facial Data Collection"
        assert parsed.client == "Micro1.ai"
        assert parsed.category == "Photo"
        assert parsed.simple is True

    def test_double_dash_case_insensitive_flag(self):
        parser = _build_test_cli_parser()
        args = ["new", "AI Facial Data Collection", "--Client", "Micro1.ai", "-c", "Photo", "-s"]
        parsed = parser.parse_args(args)
        assert parsed.command == "new"
        assert parsed.name == "AI Facial Data Collection"
        assert parsed.client == "Micro1.ai"
        assert parsed.category == "Photo"
        assert parsed.simple is True

    def test_uppercase_short_flags(self):
        parser = _build_test_cli_parser()
        args = ["new", "Test Project", "-C", "Photo", "-S", "-G"]
        parsed = parser.parse_args(args)
        assert parsed.command == "new"
        assert parsed.category == "Photo"
        assert parsed.simple is True
        assert parsed.git is True

    def test_flag_with_equal_sign(self):
        parser = _build_test_cli_parser()
        args = ["new", "Test Project", "-Client=Micro1.ai", "-c=Photo"]
        parsed = parser.parse_args(args)
        assert parsed.client == "Micro1.ai"
        assert parsed.category == "Photo"

    def test_case_insensitive_subcommands(self):
        parser = _build_test_cli_parser()
        args = ["NEW", "Uppercase Command Project", "-c", "Code"]
        parsed = parser.parse_args(args)
        assert parsed.command == "new"
        assert parsed.name == "Uppercase Command Project"
        assert parsed.category == "Code"

    def test_nested_subcommands_and_flags(self):
        parser = _build_test_cli_parser()
        args = ["category", "LIST", "--Enabled", "-V"]
        parsed = parser.parse_args(args)
        assert parsed.command == "category"
        assert parsed.category_action == "list"
        assert parsed.enabled is True
        assert parsed.verbose is True

    def test_storage_review_case_insensitive_sort(self):
        parser = _build_test_cli_parser()
        args = ["storage", "review", "--Sort", "Media"]
        parsed = parser.parse_args(args)
        assert parsed.command == "storage"
        assert parsed.storage_command == "review"
        assert parsed.sort == "media"

    def test_preserves_positional_exact_case_and_spaces(self):
        parser = _build_test_cli_parser()
        args = ["new", "Keep Exact CaSe & SpAcInG", "--client", "MyClient Inc."]
        parsed = parser.parse_args(args)
        assert parsed.name == "Keep Exact CaSe & SpAcInG"
        assert parsed.client == "MyClient Inc."

    def test_end_of_options_delimiter(self):
        parser = _build_test_cli_parser()
        # After '--', tokens should not be treated as flags
        args = ["new", "--", "-NotAFlag-"]
        parsed = parser.parse_args(args)
        assert parsed.name == "-NotAFlag-"

    def test_windows_help_aliases(self):
        parser = _build_test_cli_parser()
        normalized = normalize_cli_args(["/help"], parser)
        assert normalized == ["--help"]
        normalized_q = normalize_cli_args(["/?"], parser)
        assert normalized_q == ["--help"]

    def test_smart_error_suggestions_and_tips(self):
        from cos.help_formatter import format_cli_error
        parser = _build_test_cli_parser()

        # Test misspelled flag with single dash
        err_msg = "unrecognized arguments: -clinet Micro1.ai"
        formatted = format_cli_error(parser, err_msg)
        assert "Did you mean:" in formatted
        assert "--client" in formatted
        assert "💡" in formatted
        assert "Full-word flags use double dashes" in formatted

        # Test misspelled choice
        err_choice = "argument --sort: invalid choice: 'meda' (choose from 'size', 'updated', 'created', 'reclaimable', 'media')"
        formatted_choice = format_cli_error(parser, err_choice)
        assert "Did you mean:" in formatted_choice
        assert "media" in formatted_choice

        # Test misspelled subcommand
        err_subcmd = "invalid choice: 'neew' (choose from 'new', 'clone', 'storage')"
        formatted_subcmd = format_cli_error(parser, err_subcmd)
        assert "Did you mean:" in formatted_subcmd
        assert "new" in formatted_subcmd
