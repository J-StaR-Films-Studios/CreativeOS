"""Tests for the CLI clone command."""

import argparse
from unittest.mock import Mock

from cos.commands import clone


def test_clone_leaves_terminal_to_git_progress(temp_projects_dir, monkeypatch):
    target_root = temp_projects_dir / "Code"
    monkeypatch.setattr(clone, "PROJECTS_PATH", str(temp_projects_dir))
    monkeypatch.setattr(clone.os, "getcwd", lambda: str(target_root))
    monkeypatch.setattr(clone, "get_date_slug", lambda date: "2026-09-29")

    def fake_run(command, **kwargs):
        target_root.joinpath("2026-09-29_codex").mkdir()

    run = Mock(side_effect=fake_run)
    monkeypatch.setattr(clone.subprocess, "run", run)
    monkeypatch.setattr(clone.console, "status", Mock(side_effect=AssertionError("spinner hides Git progress")))

    clone.cmd_clone(argparse.Namespace(
        url="https://github.com/openai/codex.git",
        name=None,
        category="Code",
        date=None,
        client=None,
    ))

    run.assert_called_once_with(
        ["git", "clone", "--progress", "--", "https://github.com/openai/codex.git",
         str(target_root / "2026-09-29_codex")],
        check=True,
    )
