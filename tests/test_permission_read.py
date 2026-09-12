import json
import shlex
import subprocess
from types import SimpleNamespace

import pytest

MODULE = "ui.task_logic.permission_read"


def _host():
    return SimpleNamespace(id=1, name="germany-1", provider="standalone",
                           ip_address="91.99.3.72", ssh_key_path="/keys/germany.pem",
                           ssh_port=22, ssh_user="root")


def _instance(host=None):
    return SimpleNamespace(id=99, port=27965, redis_db=2, host=host)


def test_build_read_command_targets_the_host_over_ssh():
    import importlib
    mod = importlib.import_module(MODULE)
    command = mod.build_read_command(_host(), 2, 99)
    assert command[0] == "ssh"
    assert command[-2] == "91.99.3.72"
    assert "scan_iter" in shlex.split(command[-1])[2]


def test_read_live_permissions_parses_output(monkeypatch):
    import importlib
    mod = importlib.import_module(MODULE)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"levels": {"76561198012345678": 5}, "managed": ["76561198012345678"]}),
        stderr=""))
    levels, managed, error = mod.read_live_permissions(_instance(host=_host()))
    assert levels == {"76561198012345678": 5}
    assert managed == ["76561198012345678"]
    assert error is None


def test_read_live_permissions_keeps_zero_levels(monkeypatch):
    """A stored level-0 row has to be able to settle as managed."""
    import importlib
    mod = importlib.import_module(MODULE)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps({"levels": {"76561198012345678": 0}, "managed": []}), stderr=""))
    levels, _, error = mod.read_live_permissions(_instance(host=_host()))
    assert levels == {"76561198012345678": 0}
    assert error is None


def test_read_live_permissions_drops_keys_that_are_not_steamids(monkeypatch):
    """One junk key must not be able to 400 the whole config save."""
    import importlib
    mod = importlib.import_module(MODULE)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"levels": {"76561198012345678": 5, "bot-17": 5, "1234": 3},
                           "managed": ["bot-17"]}),
        stderr=""))
    levels, managed, error = mod.read_live_permissions(_instance(host=_host()))
    assert levels == {"76561198012345678": 5}
    assert managed == []
    assert error is None


def test_read_live_permissions_reports_ssh_failure(monkeypatch):
    import importlib
    mod = importlib.import_module(MODULE)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=255, stdout="", stderr="ssh: connect to host port 22: No route to host"))
    levels, managed, error = mod.read_live_permissions(_instance(host=_host()))
    assert levels is None
    assert managed is None
    assert "unreachable" in error.lower()


def test_read_live_permissions_reports_timeout(monkeypatch):
    import importlib
    mod = importlib.import_module(MODULE)

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=10)

    monkeypatch.setattr(mod.subprocess, "run", boom)
    levels, managed, error = mod.read_live_permissions(_instance(host=_host()))
    assert levels is None
    assert managed is None
    assert error


def test_no_host_is_not_an_error():
    import importlib
    mod = importlib.import_module(MODULE)
    assert mod.read_live_permissions(_instance(host=None)) == (None, None, None)
