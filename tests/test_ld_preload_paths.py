from types import SimpleNamespace

from ui.task_logic.ansible_instance_mgmt import (
    RESERVED_HOOK_FILENAMES,
    _build_ld_preload_paths,
)


def _inst(port=27960, ld_preload_hooks=None, lan_rate_enabled=False):
    return SimpleNamespace(
        port=port,
        ld_preload_hooks=ld_preload_hooks,
        lan_rate_enabled=lan_rate_enabled,
    )


def test_empty_when_no_hooks():
    assert _build_ld_preload_paths(_inst()) == ""


def test_single_user_hook():
    inst = _inst(ld_preload_hooks="highfps_hook.so")
    assert _build_ld_preload_paths(inst) == (
        "/home/ql/qlds-27960/minqlx-plugins/highfps_hook.so"
    )


def test_multiple_user_hooks_colon_joined_in_order():
    inst = _inst(port=27961, ld_preload_hooks="a.so,b.so,c.so")
    assert _build_ld_preload_paths(inst) == ":".join([
        "/home/ql/qlds-27961/minqlx-plugins/a.so",
        "/home/ql/qlds-27961/minqlx-plugins/b.so",
        "/home/ql/qlds-27961/minqlx-plugins/c.so",
    ])


def test_whitespace_stripped_and_empty_entries_skipped():
    inst = _inst(ld_preload_hooks="  a.so , ,b.so  ,,")
    assert _build_ld_preload_paths(inst) == (
        "/home/ql/qlds-27960/minqlx-plugins/a.so:"
        "/home/ql/qlds-27960/minqlx-plugins/b.so"
    )


def test_force_rate_is_the_only_system_hook():
    from ui.task_logic import ansible_instance_mgmt

    filenames = [name for name, _, _ in ansible_instance_mgmt._SYSTEM_HOOKS]
    assert filenames == ["force_rate.so"]


def test_system_hook_prepended_when_predicate_true(monkeypatch):
    from ui.task_logic import ansible_instance_mgmt

    monkeypatch.setattr(
        ansible_instance_mgmt,
        "_SYSTEM_HOOKS",
        [("force_rate.so", lambda i: i.lan_rate_enabled, "baseq3")],
    )
    inst = _inst(ld_preload_hooks="user.so", lan_rate_enabled=True)
    assert _build_ld_preload_paths(inst) == (
        "/home/ql/qlds-27960/baseq3/force_rate.so:"
        "/home/ql/qlds-27960/minqlx-plugins/user.so"
    )


def test_system_hook_not_prepended_when_predicate_false(monkeypatch):
    from ui.task_logic import ansible_instance_mgmt

    monkeypatch.setattr(
        ansible_instance_mgmt,
        "_SYSTEM_HOOKS",
        [("force_rate.so", lambda i: i.lan_rate_enabled, "baseq3")],
    )
    inst = _inst(ld_preload_hooks="user.so")
    assert _build_ld_preload_paths(inst) == (
        "/home/ql/qlds-27960/minqlx-plugins/user.so"
    )


def test_reserved_hook_filenames_contains_force_rate():
    assert "force_rate.so" in RESERVED_HOOK_FILENAMES
