"""Setup must keep an existing COS installation's paths and categories."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from cos import category_config, config as cos_config, onboarding


def test_setup_prefills_and_preserves_existing_settings(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    categories_path = tmp_path / "categories.json"
    original = {
        "root_path": str(Path(onboarding.__file__).resolve().parents[3]),
        "projects_path": str(tmp_path / "01_Projects"),
        "vault_path": str(tmp_path / "03_Vault"),
        "exports_path": str(tmp_path / "02_Exports"),
        "archive_path": str(tmp_path / "Archive"),
        "shuttle_path": str(tmp_path / "Shuttle"),
        "downloads_path": "E:\\Downloads",
        "templates_path": str(tmp_path / "Custom Templates"),
        "other_setting": "keep me",
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")
    custom_category = {"template": "3d_project", "physical_folder": "Models", "enabled": True}
    existing_categories = {
        "default_category": "Video",
        "simple_template": "my_simple",
        "categories": {
            "Video": {**category_config.DEFAULT_CATEGORIES["Video"], "template": "custom_video"},
            "Code": {**category_config.DEFAULT_CATEGORIES["Code"], "enabled": False},
            "3D Models": custom_category,
        },
    }
    categories_path.write_text(json.dumps(existing_categories), encoding="utf-8")
    monkeypatch.setattr(onboarding, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(category_config, "CATEGORIES_PATH", str(categories_path))
    monkeypatch.setattr(cos_config, "reload_config", lambda: None)

    defaults_seen = []
    categories_seen = []
    defaults_for_select = []

    def fake_path(label, *, default, only_directories):
        defaults_seen.append(default)
        return SimpleNamespace(ask=lambda: default)

    def fake_checkbox(label, *, choices):
        categories_seen.extend((choice.value, choice.checked) for choice in choices)
        return SimpleNamespace(ask=lambda: [choice.value for choice in choices if choice.checked])

    def fake_select(label, *, choices, default):
        defaults_for_select.append(default)
        return SimpleNamespace(ask=lambda: default)

    monkeypatch.setitem(sys.modules, "questionary", SimpleNamespace(
        path=fake_path,
        checkbox=fake_checkbox,
        select=fake_select,
        confirm=lambda *args, **kwargs: SimpleNamespace(ask=lambda: True),
        Choice=lambda title, value, checked: SimpleNamespace(value=value, checked=checked),
    ))
    silent_console = SimpleNamespace(clear=lambda: None, print=lambda *args, **kwargs: None)

    choices = onboarding.run_onboarding_wizard(silent_console)

    assert defaults_seen == [original[key] for key in (
        "projects_path", "vault_path", "archive_path", "shuttle_path", "exports_path"
    )]
    assert ("Code", False) in categories_seen
    assert ("3D Models", True) in categories_seen
    assert defaults_for_select == ["Video"]
    assert onboarding.apply_configuration(choices)

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    for key, value in original.items():
        assert updated[key] == value
    updated_categories = json.loads(categories_path.read_text(encoding="utf-8"))
    assert updated_categories["categories"]["Video"]["template"] == "custom_video"
    assert updated_categories["categories"]["Code"]["enabled"] is False
    assert updated_categories["categories"]["3D Models"] == custom_category
    assert updated_categories["simple_template"] == "my_simple"


def test_setup_rebases_default_templates_path_after_checkout_moves(tmp_path, monkeypatch):
    old_root = tmp_path / "old checkout"
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "root_path": str(old_root),
        "templates_path": str(old_root / "00_System" / "Templates"),
    }), encoding="utf-8")
    monkeypatch.setattr(onboarding, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(category_config, "CATEGORIES_PATH", str(tmp_path / "categories.json"))
    monkeypatch.setattr(cos_config, "reload_config", lambda: None)

    assert onboarding.apply_configuration({
        "projects_path": str(tmp_path / "Projects"),
        "vault_path": str(tmp_path / "Vault"),
        "archive_path": str(tmp_path / "Archive"),
        "exports_path": str(tmp_path / "Exports"),
        "shuttle_path": str(tmp_path / "Shuttle"),
        "enabled_categories": ["Video"],
        "default_category": "Video",
    })

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["templates_path"] == str(Path(onboarding.__file__).resolve().parents[2] / "Templates")
