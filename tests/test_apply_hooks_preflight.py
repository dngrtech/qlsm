"""When the predicate for a system hook is True but the source binary is
missing on the UI server, _preflight returns a string mentioning the
filename. The caller (apply_instance_hooks_logic) translates that into
status=ERROR + return False."""
import os
from unittest.mock import MagicMock, patch

import pytest

from ui.task_logic import ansible_instance_hooks
from ui.task_logic.ansible_instance_hooks import _preflight


def _make_instance_with_lan_rate():
    instance = MagicMock()
    instance.id = 42
    instance.port = 27960
    instance.lan_rate_enabled = True
    instance.ld_preload_hooks = ""  # no user hooks
    instance.host = MagicMock()
    instance.host.name = "test-host"
    instance.host.lan_rate_uses_hook = True
    return instance


def test_preflight_returns_string_when_force_rate_so_missing(tmp_path):
    """When force_rate.so is required (predicate True) but absent on the
    UI server, _preflight must return a string mentioning the filename."""
    instance = _make_instance_with_lan_rate()

    with patch.object(ansible_instance_hooks, "_system_hook_source_path",
                      return_value=str(tmp_path / "definitely-missing" / "force_rate.so")):
        result = _preflight(instance)

    assert isinstance(result, str), "Expected an error string, got %r" % (result,)
    assert "force_rate.so" in result


def test_preflight_returns_none_when_force_rate_so_present(tmp_path):
    """When the source exists, _preflight passes through (returns None or falsy)."""
    instance = _make_instance_with_lan_rate()
    fake_so = tmp_path / "force_rate.so"
    fake_so.write_bytes(b"\x7fELF\x02\x01\x01")  # valid ELF magic prefix

    with patch.object(ansible_instance_hooks, "_system_hook_source_path",
                      return_value=str(fake_so)):
        result = _preflight(instance)

    assert not result, "Pre-flight should have passed; got %r" % (result,)


def test_apply_hooks_returns_false_when_system_hook_missing(app, tmp_path):
    """End-to-end: when _preflight returns a string, apply_instance_hooks_logic
    must return False (existing contract), set the instance to ERROR, and
    log the message."""
    from ui.models import Host, QLInstance, InstanceStatus, db
    with app.app_context():
        host = Host(
            name="preflight-host",
            provider="vultr",
            os_type="debian",
            ip_address="1.2.3.4",
            lan_rate_uses_hook=True,
        )
        db.session.add(host)
        db.session.commit()
        instance = QLInstance(
            host_id=host.id,
            name="i",
            hostname="test-ql-server",
            port=27960,
            lan_rate_enabled=True,
            status=InstanceStatus.RUNNING,
        )
        db.session.add(instance)
        db.session.commit()
        instance_id = instance.id

    with app.app_context():
        with patch.object(ansible_instance_hooks, "_system_hook_source_path",
                          return_value=str(tmp_path / "missing" / "force_rate.so")):
            result = ansible_instance_hooks.apply_instance_hooks_logic(
                instance_id, restart_service=True)

        assert result is False, "Existing contract is False on preflight failure"
        from ui.models import QLInstance, InstanceStatus
        updated = QLInstance.query.get(instance_id)
        assert updated.status == InstanceStatus.ERROR


def test_preflight_accepts_user_hooks_dir(tmp_path, monkeypatch):
    """A .so file in user-hooks/ should pass pre-flight even if scripts/ is empty."""
    from unittest.mock import MagicMock
    from ui.task_logic import ansible_instance_hooks
    from ui.task_logic.ansible_instance_hooks import _preflight

    inst = MagicMock()
    inst.id = 8
    inst.port = 27975
    inst.ld_preload_hooks = "ok.so"
    inst.lan_rate_enabled = False
    inst.host = MagicMock(); inst.host.name = "preh"; inst.host.lan_rate_uses_hook = False

    inst_dir = tmp_path / "configs" / "preh" / "8" / "user-hooks"
    inst_dir.mkdir(parents=True)
    (inst_dir / "ok.so").write_bytes(b"\x7fELF\x00\x00\x00")

    monkeypatch.setattr(ansible_instance_hooks, "CONFIGS_BASE", str(tmp_path / "configs"))
    assert _preflight(inst) is None
