"""CLI entry and preview behavior used by unattended callers."""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cos import cli
from cos.commands import category, config_cmd, sync


installer_spec = importlib.util.spec_from_file_location(
    "install_cos", Path(__file__).resolve().parents[3] / "install_cos.py"
)
assert installer_spec is not None and installer_spec.loader is not None
install_cos = importlib.util.module_from_spec(installer_spec)
installer_spec.loader.exec_module(install_cos)


def test_help_skips_first_run_wizard(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cos", "new", "--help"])
    monkeypatch.setattr(cli, "is_first_run", lambda: True)
    monkeypatch.setattr(cli, "run_onboarding_wizard", lambda *args: pytest.fail("help prompted for setup"))
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 0


def test_fresh_checkout_help_and_setup_help_work_without_config(tmp_path):
    scripts = tmp_path / "00_System" / "Scripts"
    scripts.mkdir(parents=True)
    (tmp_path / "00_System" / "Config").mkdir()
    shutil.copytree(Path(cli.__file__).parent, scripts / "cos", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    env = {**os.environ, "PYTHONPATH": str(scripts)}

    for arguments in (["--help"], ["setup", "--help"], ["new", "--help"]):
        result = subprocess.run(
            [sys.executable, "-m", "cos.cli", *arguments],
            cwd=tmp_path, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_unattended_first_run_fails_without_prompt(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cos", "new", "Example"])
    monkeypatch.setattr(cli, "is_first_run", lambda: True)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli, "run_onboarding_wizard", lambda *args: pytest.fail("unattended wizard"))
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 1


def test_category_edit_accepts_description_and_enable_flags(monkeypatch):
    parser = argparse.ArgumentParser()
    category.add_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["category", "edit", "Video", "--disable", "--description", "Archived projects"])
    saved = []
    monkeypatch.setattr(category, "load_categories", lambda: {"categories": {"Video": {"enabled": True}}})
    monkeypatch.setattr(category, "save_categories", lambda config: saved.append(config))

    category.cmd_category_edit(args)

    assert saved[0]["categories"]["Video"] == {"enabled": False, "description": "Archived projects"}


def test_config_validation_failure_returns_error(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"projects_path": str(tmp_path), "templates_path": str(tmp_path), "shuttle_path": str(tmp_path / "missing")}), encoding="utf-8")
    categories = tmp_path / "categories.json"
    categories.write_text(json.dumps({"categories": {"Video": {}}}), encoding="utf-8")
    monkeypatch.setattr(config_cmd, "CONFIG_PATH", str(config))
    monkeypatch.setattr(config_cmd, "get_categories_path", lambda: str(categories))
    with pytest.raises(SystemExit) as exit_info:
        config_cmd.cmd_config_validate(argparse.Namespace())
    assert exit_info.value.code == 1


def test_sync_preview_leaves_both_sides_and_state_untouched(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    project = projects / "Film"
    notes = project / "00_Notes"
    notes.mkdir(parents=True)
    (project / ".project_meta.json").write_text('{"slug": "Film"}', encoding="utf-8")
    (notes / "new.md").write_text("new note", encoding="utf-8")
    (notes / "update.md").write_text("project edit", encoding="utf-8")
    vault = tmp_path / "vault"
    vault_notes = vault / "01_Active_Projects" / "Film"
    vault_notes.mkdir(parents=True)
    (vault_notes / "pull.md").write_text("vault note", encoding="utf-8")
    update = vault_notes / "update.md"
    update.write_text("older vault edit", encoding="utf-8")
    os.utime(update, (1, 1))
    (notes / "pull-update.md").write_text("old project edit", encoding="utf-8")
    os.utime(notes / "pull-update.md", (1, 1))
    (vault_notes / "pull-update.md").write_text("new vault edit", encoding="utf-8")
    state = tmp_path / "sync_state.json"
    state.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sync, "SYNC_STATE_PATH", str(state))

    result = sync.run_sync(str(projects), str(vault), dry_run=True)

    assert {entry["type"] for entry in result["logs"]} == {"push", "pull", "update_vault", "update_project"}
    assert not (vault_notes / "new.md").exists()
    assert not (notes / "pull.md").exists()
    assert update.read_text(encoding="utf-8") == "older vault edit"
    assert (notes / "pull-update.md").read_text(encoding="utf-8") == "old project edit"
    assert state.read_text(encoding="utf-8") == "{}"
    assert not list(tmp_path.rglob("*.bak"))


@pytest.mark.skipif(os.name != "nt", reason="Windows installer")
def test_installer_skips_setup_and_path_without_consent(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(install_cos, "ENV", tmp_path / ".cos-venv")
    monkeypatch.setattr(install_cos, "CONFIG", tmp_path / "Config")
    monkeypatch.setattr(install_cos.venv, "create", lambda *args, **kwargs: calls.append("venv"))
    monkeypatch.setattr(install_cos.subprocess, "run", lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(install_cos, "ask", lambda *args, **kwargs: False)
    monkeypatch.setattr(install_cos, "add_user_path", lambda *args: pytest.fail("PATH changed"))

    assert install_cos.main() == 0
    assert calls[0] == "venv"
    assert len(calls) == 2
    assert calls[1][-2:] == ["-e", str(install_cos.ROOT)]


@pytest.mark.skipif(os.name != "nt", reason="Windows installer")
def test_installer_backs_up_config_before_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    config = tmp_path / "Config"
    config.mkdir()
    (config / "config.json").write_text("existing settings", encoding="utf-8")
    monkeypatch.setattr(install_cos, "ENV", tmp_path / ".cos-venv")
    monkeypatch.setattr(install_cos, "CONFIG", config)
    monkeypatch.setattr(install_cos.venv, "create", lambda *args, **kwargs: None)
    calls = []
    monkeypatch.setattr(install_cos.subprocess, "run", lambda args, **kwargs: calls.append(args))
    answers = iter([True, False])
    monkeypatch.setattr(install_cos, "ask", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(install_cos, "add_user_path", lambda *args: pytest.fail("PATH changed"))

    assert install_cos.main() == 0
    assert calls[1][-1] == "setup"
    assert (config / "config.json").read_text(encoding="utf-8") == "existing settings"
    backups = list(config.glob("config.json.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "existing settings"


@pytest.mark.skipif(os.name != "nt", reason="Windows installer")
def test_installer_refuses_unattended_changes(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(install_cos.venv, "create", lambda *args, **kwargs: pytest.fail("created environment"))
    assert install_cos.main() == 1


def test_sync_preview_does_not_create_missing_directories(tmp_path, monkeypatch):
    project = tmp_path / "projects" / "Film"
    project.mkdir(parents=True)
    (project / ".project_meta.json").write_text('{"slug": "Film"}', encoding="utf-8")
    vault = tmp_path / "vault"
    monkeypatch.setattr(sync, "SYNC_STATE_PATH", str(tmp_path / "state.json"))

    sync.run_sync(str(tmp_path / "projects"), str(vault), dry_run=True)

    assert not (project / "00_Notes").exists()
    assert not vault.exists()
    assert not (tmp_path / "state.json").exists()
