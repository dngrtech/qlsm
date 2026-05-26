import os
import pytest
from ui.task_logic.hook_paths import resolve_user_hook


@pytest.fixture
def layout(tmp_path):
    configs = tmp_path / "configs"
    inst_dir = configs / "h1" / "7"
    (inst_dir / "user-hooks").mkdir(parents=True)
    (inst_dir / "scripts").mkdir(parents=True)
    return configs, inst_dir


def test_resolves_to_user_hooks_when_present(layout):
    configs, inst_dir = layout
    (inst_dir / "user-hooks" / "x.so").write_bytes(b"\x7fELF")
    res = resolve_user_hook(str(configs), "h1", 7, "x.so")
    assert res == {
        "source": str(inst_dir / "user-hooks" / "x.so"),
        "host_subdir": "user-hooks",
    }


def test_falls_back_to_scripts_when_only_legacy_present(layout):
    configs, inst_dir = layout
    (inst_dir / "scripts" / "legacy.so").write_bytes(b"\x7fELF")
    res = resolve_user_hook(str(configs), "h1", 7, "legacy.so")
    assert res == {
        "source": str(inst_dir / "scripts" / "legacy.so"),
        "host_subdir": "minqlx-plugins",
    }


def test_returns_none_when_missing(layout):
    configs, _ = layout
    assert resolve_user_hook(str(configs), "h1", 7, "gone.so") is None


def test_prefers_user_hooks_over_scripts(layout):
    configs, inst_dir = layout
    (inst_dir / "user-hooks" / "dup.so").write_bytes(b"\x7fELF")
    (inst_dir / "scripts" / "dup.so").write_bytes(b"\x7fELF")
    res = resolve_user_hook(str(configs), "h1", 7, "dup.so")
    assert res["host_subdir"] == "user-hooks"
