"""A product rename must not orphan existing settings or project folders."""

import importlib.util
import json
from pathlib import Path

from wholeboard import config


def load_settings_module(monkeypatch, home):
    monkeypatch.setattr(Path, "home", lambda: home)
    spec = importlib.util.spec_from_file_location("isolated_settings", config.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clear_locations(monkeypatch):
    monkeypatch.delenv("OPENFABRO_HOME", raising=False)
    monkeypatch.delenv("WHOLEBOARD_HOME", raising=False)


def test_fresh_install_saves_and_reopens_settings_in_the_new_app_folder(tmp_path, monkeypatch):
    clear_locations(monkeypatch)
    settings = load_settings_module(monkeypatch, tmp_path)
    settings.update({"port": 9123})
    assert (tmp_path / ".openfabro" / "config.json").is_file()
    reopened = load_settings_module(monkeypatch, tmp_path)
    assert reopened.load()["port"] == 9123
    assert reopened.load()["projects_dir"] == str(tmp_path / "OpenFabroProjects")


def test_existing_settings_and_project_folder_remain_accessible_after_rename(tmp_path, monkeypatch):
    clear_locations(monkeypatch)
    legacy = tmp_path / ".wholeboard"
    legacy.mkdir()
    original = {"port": 9001, "projects_dir": str(tmp_path / "existing-designs")}
    (legacy / "config.json").write_text(json.dumps(original))
    settings = load_settings_module(monkeypatch, tmp_path)
    assert settings.load()["port"] == 9001
    assert settings.load()["projects_dir"] == original["projects_dir"]
    settings.update({"port": 9002})
    assert json.loads((legacy / "config.json").read_text())["port"] == 9002
    assert not (tmp_path / ".openfabro" / "config.json").exists()


def test_legacy_default_projects_are_not_hidden_by_the_new_default(tmp_path, monkeypatch):
    clear_locations(monkeypatch)
    (tmp_path / "WholeBoardProjects").mkdir()
    settings = load_settings_module(monkeypatch, tmp_path)
    assert settings.load()["projects_dir"] == str(tmp_path / "WholeBoardProjects")


def test_new_home_override_takes_precedence_over_the_legacy_override(tmp_path, monkeypatch):
    clear_locations(monkeypatch)
    monkeypatch.setenv("OPENFABRO_HOME", str(tmp_path / "new-settings"))
    monkeypatch.setenv("WHOLEBOARD_HOME", str(tmp_path / "old-settings"))
    settings = load_settings_module(monkeypatch, tmp_path)
    settings.update({"port": 9124})
    assert (tmp_path / "new-settings" / "config.json").is_file()
    assert not (tmp_path / "old-settings" / "config.json").exists()


def test_legacy_home_override_still_controls_where_settings_are_saved(tmp_path, monkeypatch):
    clear_locations(monkeypatch)
    monkeypatch.setenv("WHOLEBOARD_HOME", str(tmp_path / "old-settings"))
    settings = load_settings_module(monkeypatch, tmp_path)
    settings.update({"port": 9125})
    assert json.loads((tmp_path / "old-settings" / "config.json").read_text())["port"] == 9125


def test_an_existing_new_config_is_preferred_over_legacy_settings(tmp_path, monkeypatch):
    clear_locations(monkeypatch)
    for folder, port in ((".openfabro", 9222), (".wholeboard", 9111)):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "config.json").write_text(json.dumps({"port": port}))
    settings = load_settings_module(monkeypatch, tmp_path)
    assert settings.load()["port"] == 9222


def test_an_empty_new_cache_folder_does_not_hide_existing_settings(tmp_path, monkeypatch):
    clear_locations(monkeypatch)
    (tmp_path / ".openfabro").mkdir()
    (tmp_path / ".wholeboard").mkdir()
    (tmp_path / ".wholeboard" / "config.json").write_text(json.dumps({"port": 9333}))
    settings = load_settings_module(monkeypatch, tmp_path)
    assert settings.load()["port"] == 9333
