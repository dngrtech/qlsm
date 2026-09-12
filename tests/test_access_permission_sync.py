import json
import os
import shlex
import subprocess
import sys
import types
from types import SimpleNamespace

import pytest


MODULE = "ui.task_logic.access_permission_sync"


def _host(provider="standalone", name="germany-1"):
    return SimpleNamespace(
        id=1,
        name=name,
        provider=provider,
        ip_address="91.99.3.72",
        ssh_key_path="/keys/germany.pem",
        ssh_port=22,
        ssh_user="root",
    )


def _instance(port=27965, redis_db=2, host=None):
    return SimpleNamespace(id=99, port=port, redis_db=redis_db, host=host)


def _remote_script(command):
    return shlex.split(command[-1])[2]


class FakeRedis:
    """In-memory stand-in with just enough of the redis-py surface the
    remote sync script uses: get/set strings, and named SETs via
    smembers/srem/sadd/delete. sets is {db: {key: set()}}."""

    store = {}
    sets = {}

    def __init__(self, **kwargs):
        self.db = kwargs["db"]
        FakeRedis.last_kwargs = kwargs
        self.store.setdefault(self.db, {})
        self.sets.setdefault(self.db, {})

    def set(self, key, value):
        self.store[self.db][key] = value

    def smembers(self, key):
        return {v.encode() for v in self.sets[self.db].get(key, set())}

    def srem(self, key, *values):
        members = self.sets[self.db].get(key, set())
        for v in values:
            members.discard(v)
        if not members:
            self.sets[self.db].pop(key, None)  # Redis drops empty sets

    def sadd(self, key, *values):
        self.sets[self.db].setdefault(key, set()).update(values)

    def delete(self, key):
        self.sets[self.db].pop(key, None)


KEY_99 = "minqlx:qlsm:managed_admins:99"
LEGACY_KEY = "minqlx:qlsm:managed_admins"


def _install_fake_redis(monkeypatch):
    FakeRedis.store = {}
    FakeRedis.sets = {}
    fake_module = types.ModuleType("redis")
    fake_module.Redis = FakeRedis
    monkeypatch.setitem(sys.modules, "redis", fake_module)
    return FakeRedis


# --- build_sync_command ----------------------------------------------------

def test_build_sync_command_shape():
    from ui.task_logic.access_permission_sync import build_sync_command

    command = build_sync_command(_host(), 2, {"76561197999064274": 5}, 99)
    script = _remote_script(command)

    assert command[:2] == ["ssh", "-i"]
    assert command.count("91.99.3.72") == 1
    assert "ConnectTimeout=5" in command
    assert "db=2" in script
    assert repr(KEY_99) in script


# --- remote script behaviour (executed against FakeRedis) -----------------

def test_remote_script_upserts_then_resets_removed_admin(monkeypatch):
    from ui.task_logic.access_permission_sync import _remote_sync_script

    fake_redis = _install_fake_redis(monkeypatch)

    printed = []
    script_v1 = _remote_sync_script(
        {"76561197999064274": 5, "76561198257351377": 3}, db=2, redis_password=None, instance_id=99
    )
    exec(script_v1, {"__name__": "sync", "print": printed.append})

    assert fake_redis.store[2]["minqlx:players:76561197999064274:permission"] == "5"
    assert fake_redis.store[2]["minqlx:players:76561198257351377:permission"] == "3"
    assert fake_redis.sets[2][KEY_99] == {"76561197999064274", "76561198257351377"}
    result_v1 = json.loads(printed[0])
    assert sorted(result_v1["synced"]) == ["76561197999064274", "76561198257351377"]
    assert result_v1["reset"] == []

    # Second sync: one admin removed from access.txt -> must reset to 0,
    # the other's grant (potentially changed by hand via !setperm) untouched
    # except for the upsert this sync itself performs.
    printed.clear()
    script_v2 = _remote_sync_script(
        {"76561197999064274": 5}, db=2, redis_password=None, instance_id=99
    )
    exec(script_v2, {"__name__": "sync", "print": printed.append})

    assert fake_redis.store[2]["minqlx:players:76561197999064274:permission"] == "5"
    assert fake_redis.store[2]["minqlx:players:76561198257351377:permission"] == "0"
    assert fake_redis.sets[2][KEY_99] == {"76561197999064274"}
    result_v2 = json.loads(printed[0])
    assert result_v2["synced"] == ["76561197999064274"]
    assert result_v2["reset"] == ["76561198257351377"]


def test_remote_script_never_resets_ids_it_did_not_previously_manage(monkeypatch):
    """A permission granted by hand via !setperm, outside access.txt entirely,
    must never be reset just because it's not in the managed set."""
    from ui.task_logic.access_permission_sync import _remote_sync_script

    fake_redis = _install_fake_redis(monkeypatch)
    fake_redis.store[2] = {"minqlx:players:76561199000000000:permission": "5"}
    fake_redis.sets[2] = {}  # never synced via this mechanism

    printed = []
    script = _remote_sync_script(
        {"76561197999064274": 5}, db=2, redis_password=None, instance_id=99
    )
    exec(script, {"__name__": "sync", "print": printed.append})

    assert fake_redis.store[2]["minqlx:players:76561199000000000:permission"] == "5"
    assert json.loads(printed[0])["reset"] == []


def test_remote_script_instances_sharing_a_db_do_not_reset_each_others_admins(monkeypatch):
    """Two instances may deliberately share a Redis DB. Saving B, which
    doesn't list A's admin, must not reset that admin -- B never managed them."""
    from ui.task_logic.access_permission_sync import _remote_sync_script

    fake_redis = _install_fake_redis(monkeypatch)
    printed = []

    exec(_remote_sync_script({"76561197999064274": 5}, db=2, redis_password=None, instance_id=1),
         {"__name__": "sync", "print": printed.append})
    exec(_remote_sync_script({"76561198257351377": 3}, db=2, redis_password=None, instance_id=2),
         {"__name__": "sync", "print": printed.append})
    # B saved again with its admin removed: only B's own admin is reset.
    exec(_remote_sync_script({}, db=2, redis_password=None, instance_id=2),
         {"__name__": "sync", "print": printed.append})

    assert fake_redis.store[2]["minqlx:players:76561197999064274:permission"] == "5"
    assert fake_redis.store[2]["minqlx:players:76561198257351377:permission"] == "0"
    assert json.loads(printed[-1])["reset"] == ["76561198257351377"]


def test_remote_script_adopts_legacy_db_wide_set_once(monkeypatch):
    """Admins pushed before the set was keyed by instance live in the old
    DB-wide set. The first sync adopts it (so they can still be revoked)
    and deletes it, so a second instance doesn't adopt it again."""
    from ui.task_logic.access_permission_sync import _remote_sync_script

    fake_redis = _install_fake_redis(monkeypatch)
    fake_redis.store[2] = {"minqlx:players:76561198257351377:permission": "5"}
    fake_redis.sets[2] = {LEGACY_KEY: {"76561198257351377"}}

    printed = []
    exec(_remote_sync_script({"76561197999064274": 5}, db=2, redis_password=None, instance_id=99),
         {"__name__": "sync", "print": printed.append})

    assert fake_redis.store[2]["minqlx:players:76561198257351377:permission"] == "0"
    assert json.loads(printed[0])["reset"] == ["76561198257351377"]
    assert LEGACY_KEY not in fake_redis.sets[2]
    assert fake_redis.sets[2][KEY_99] == {"76561197999064274"}


# --- sync_access_permissions (subprocess boundary) --------------------------

def test_sync_access_permissions_returns_none_without_host():
    from ui.task_logic.access_permission_sync import sync_access_permissions

    assert sync_access_permissions(_instance(host=None), {"76561197999064274": 5}) is None


def test_sync_access_permissions_uses_self_host_redis_password(monkeypatch):
    from ui.task_logic import access_permission_sync as module

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout=json.dumps({"synced": [], "reset": []}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(module, "resolve_self_host_management_target", lambda: "10.0.0.5")
    monkeypatch.setenv("REDIS_PASSWORD", "secret-pw")

    instance = _instance(host=_host(provider="self"))
    result = module.sync_access_permissions(instance, {"76561197999064274": 5})

    assert result == {"synced": [], "reset": []}
    script = _remote_script(captured["command"])
    assert "secret-pw" not in script  # only present base64-encoded
    assert "password_b64" in script


def test_sync_access_permissions_returns_false_on_nonzero_exit(monkeypatch):
    """False (not None) distinguishes "we tried and it failed" from "there
    was nothing to sync" -- callers use this to decide whether to warn the
    operator that in-game permissions may be stale."""
    from ui.task_logic import access_permission_sync as module

    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="connection refused"),
    )
    result = module.sync_access_permissions(_instance(host=_host()), {"76561197999064274": 5})
    assert result is False


def test_sync_access_permissions_returns_false_on_timeout(monkeypatch):
    from ui.task_logic import access_permission_sync as module

    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=10)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    result = module.sync_access_permissions(_instance(host=_host()), {"76561197999064274": 5})
    assert result is False


# --- sync_instance_admin_permissions (row-reading wrapper) ------------------

def test_sync_instance_admin_permissions_uses_rows(monkeypatch):
    import ui.task_logic.access_permission_sync as mod

    captured = {}

    def fake_sync(instance, entries):
        captured['entries'] = entries
        return {"synced": sorted(entries), "reset": []}

    monkeypatch.setattr(mod, "sync_access_permissions", fake_sync)
    instance = _instance(host=_host())
    instance.admins = [
        SimpleNamespace(steam_id64="76561198012345678", level=3),
        SimpleNamespace(steam_id64="76561198087654321", level=0),
    ]

    result = mod.sync_instance_admin_permissions(instance)

    assert captured['entries'] == {"76561198012345678": 3, "76561198087654321": 0}
    assert result["synced"] == ["76561198012345678", "76561198087654321"]


def test_sync_instance_admin_permissions_without_host_is_a_noop(monkeypatch):
    import ui.task_logic.access_permission_sync as mod
    instance = _instance(host=None)
    instance.admins = []
    assert mod.sync_instance_admin_permissions(instance) is None


def test_no_admins_still_syncs_so_removals_apply(monkeypatch):
    import ui.task_logic.access_permission_sync as mod
    captured = {}
    monkeypatch.setattr(mod, "sync_access_permissions",
                        lambda instance, entries: captured.setdefault('entries', entries) or {"synced": [], "reset": []})
    instance = _instance(host=_host())
    instance.admins = []
    mod.sync_instance_admin_permissions(instance)
    assert captured['entries'] == {}


# --- sync_and_report_access_permissions never raises -----------------------

def test_report_wrapper_swallows_failure_in_log_and_commit_path(monkeypatch):
    """A failure while logging/committing the warning (e.g. flag_modified()
    blowing up on an unrealistic mock, or a real DB error) must not escape --
    the wrapper's docstring promises it never raises and never fails the
    calling task."""
    import ui.task_logic.access_permission_sync as mod

    monkeypatch.setattr(mod, "sync_instance_admin_permissions", lambda instance: False)

    def _boom(instance, message):
        raise RuntimeError("flag_modified explosion")

    monkeypatch.setattr(mod, "append_log", _boom)
    rollback_calls = []
    monkeypatch.setattr(mod.db.session, "rollback", lambda: rollback_calls.append(True))
    monkeypatch.setattr(mod.db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))

    instance = _instance(host=_host())
    instance.admins = []

    result = mod.sync_and_report_access_permissions(instance)

    assert result is False
    assert rollback_calls, "expected the wrapper to roll back the broken session"
