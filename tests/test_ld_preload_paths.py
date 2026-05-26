import os
from types import SimpleNamespace

import pytest

from ui.task_logic.ansible_instance_mgmt import (
    RESERVED_HOOK_FILENAMES,
    _build_ld_preload_paths,
)


def _inst(port=27960, ld_preload_hooks=None, lan_rate_enabled=False,
          host_name="testhost", instance_id=1):
    host = SimpleNamespace(name=host_name)
    return SimpleNamespace(
        port=port,
        ld_preload_hooks=ld_preload_hooks,
        lan_rate_enabled=lan_rate_enabled,
        host=host,
        id=instance_id,
    )


def _create_hook(configs_base, host_name, instance_id, filename, subdir="scripts"):
    path = os.path.join(configs_base, host_name, str(instance_id), subdir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    path = os.path.join(os.path.dirname(path), filename)
    with open(path, "wb") as f:
        f.write(b"\x7fELF" + b"\x00" * 10)


def test_empty_when_no_hooks():
    assert _build_ld_preload_paths(_inst()) == ""


def test_single_user_hook(tmp_path, monkeypatch):
    from ui.task_logic import ansible_instance_mgmt
    monkeypatch.setattr(ansible_instance_mgmt, "CONFIGS_BASE", str(tmp_path))
    _create_hook(str(tmp_path), "testhost", 1, "highfps_hook.so")
    inst = _inst(ld_preload_hooks="highfps_hook.so")
    assert _build_ld_preload_paths(inst) == (
        "/home/ql/qlds-27960/minqlx-plugins/highfps_hook.so"
    )


def test_multiple_user_hooks_colon_joined_in_order(tmp_path, monkeypatch):
    from ui.task_logic import ansible_instance_mgmt
    monkeypatch.setattr(ansible_instance_mgmt, "CONFIGS_BASE", str(tmp_path))
    for fn in ("a.so", "b.so", "c.so"):
        _create_hook(str(tmp_path), "testhost", 1, fn)
    inst = _inst(port=27961, ld_preload_hooks="a.so,b.so,c.so")
    assert _build_ld_preload_paths(inst) == ":".join([
        "/home/ql/qlds-27961/minqlx-plugins/a.so",
        "/home/ql/qlds-27961/minqlx-plugins/b.so",
        "/home/ql/qlds-27961/minqlx-plugins/c.so",
    ])


def test_whitespace_stripped_and_empty_entries_skipped(tmp_path, monkeypatch):
    from ui.task_logic import ansible_instance_mgmt
    monkeypatch.setattr(ansible_instance_mgmt, "CONFIGS_BASE", str(tmp_path))
    for fn in ("a.so", "b.so"):
        _create_hook(str(tmp_path), "testhost", 1, fn)
    inst = _inst(ld_preload_hooks="  a.so , ,b.so  ,,")
    assert _build_ld_preload_paths(inst) == (
        "/home/ql/qlds-27960/minqlx-plugins/a.so:"
        "/home/ql/qlds-27960/minqlx-plugins/b.so"
    )


def test_force_rate_is_the_only_system_hook():
    from ui.task_logic import ansible_instance_mgmt

    filenames = [name for name, _, _ in ansible_instance_mgmt._SYSTEM_HOOKS]
    assert filenames == ["force_rate.so"]


def test_system_hook_prepended_when_predicate_true(tmp_path, monkeypatch):
    from ui.task_logic import ansible_instance_mgmt

    monkeypatch.setattr(ansible_instance_mgmt, "CONFIGS_BASE", str(tmp_path))
    monkeypatch.setattr(
        ansible_instance_mgmt,
        "_SYSTEM_HOOKS",
        [("force_rate.so", lambda i: i.lan_rate_enabled, "baseq3")],
    )
    _create_hook(str(tmp_path), "testhost", 1, "user.so")
    inst = _inst(ld_preload_hooks="user.so", lan_rate_enabled=True)
    assert _build_ld_preload_paths(inst) == (
        "/home/ql/qlds-27960/baseq3/force_rate.so:"
        "/home/ql/qlds-27960/minqlx-plugins/user.so"
    )


def test_system_hook_not_prepended_when_predicate_false(tmp_path, monkeypatch):
    from ui.task_logic import ansible_instance_mgmt

    monkeypatch.setattr(ansible_instance_mgmt, "CONFIGS_BASE", str(tmp_path))
    monkeypatch.setattr(
        ansible_instance_mgmt,
        "_SYSTEM_HOOKS",
        [("force_rate.so", lambda i: i.lan_rate_enabled, "baseq3")],
    )
    _create_hook(str(tmp_path), "testhost", 1, "user.so")
    inst = _inst(ld_preload_hooks="user.so")
    assert _build_ld_preload_paths(inst) == (
        "/home/ql/qlds-27960/minqlx-plugins/user.so"
    )


def test_reserved_hook_filenames_contains_force_rate():
    assert "force_rate.so" in RESERVED_HOOK_FILENAMES
