"""Mode config loading (stdlib tomllib, no third-party toml dependency)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.mode_manager import ModeManager


def test_shipped_mode_configs_load():
    manager = ModeManager()
    modes = sorted(str(m) for m in manager._mode_configs)
    assert modes == ["agent", "controlled", "plan", "smart"]


def test_mode_config_loads_from_toml_dir(tmp_path):
    (tmp_path / "plan.toml").write_text(
        '[mode]\nname = "plan"\n', encoding="utf-8"
    )
    manager = ModeManager(config_dir=tmp_path)
    assert "plan" in [str(m) for m in manager._mode_configs]


def test_no_third_party_toml_import():
    import subprocess

    code = (
        "import sys; import core.mode_manager; "
        "print('toml' in sys.modules)"
    )
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"
