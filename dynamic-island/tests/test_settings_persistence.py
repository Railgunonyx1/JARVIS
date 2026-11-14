"""Settings-path and atomic-save regression tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _load_settings_module(module_name: str):
    module_path = Path(__file__).resolve().parents[1] / "app" / "settings.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_environment_override_is_a_directory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    config_dir = tmp_path / "custom-jarvis-config"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("JARVIS_DESKTOP_HOME", str(config_dir))

    settings = _load_settings_module("jarvis_settings_env_test")

    assert settings.SETTINGS_DIR == config_dir
    assert settings.SETTINGS_FILE == config_dir / "settings.json"
    result = settings.save({"schema_version": "1.0", "model": "test-model"})
    assert result.success is True
    assert settings.SETTINGS_FILE.is_file()
    assert settings.load()["model"] == "test-model"


def test_default_settings_directory_is_created(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("JARVIS_DESKTOP_HOME", raising=False)

    settings = _load_settings_module("jarvis_settings_default_test")

    expected_dir = home / ".jarvis-desktop"
    assert settings.SETTINGS_DIR == expected_dir
    assert settings.SETTINGS_FILE == expected_dir / "settings.json"

    result = settings.save({"schema_version": "1.0", "voice_enabled": False})
    assert result.success is True
    assert json.loads(settings.SETTINGS_FILE.read_text())["voice_enabled"] is False


def test_save_uses_unique_temporary_files_for_concurrent_writes(tmp_path, monkeypatch):
    settings = _load_settings_module("jarvis_settings_concurrent_test")
    target = tmp_path / "nested" / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_FILE", target)
    monkeypatch.setattr(settings, "JARVIS_DESKTOP_HOME", tmp_path / "unused-home")

    payloads = [
        {"schema_version": "1.0", "model": f"model-{index}"}
        for index in range(8)
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(settings.save, payloads))

    assert all(result.success for result in results)
    stored = json.loads(target.read_text(encoding="utf-8"))
    assert stored in payloads
    assert list(target.parent.glob(".jarvis-settings-tmp*")) == []
