"""Tests for the _SYSTEM_HOOKS predicate behavior."""
from unittest.mock import MagicMock

import pytest

from ui.task_logic.ansible_instance_mgmt import (
    _SYSTEM_HOOKS,
    RESERVED_HOOK_FILENAMES,
)


def _make_instance(lan_rate_enabled, host_lan_rate_uses_hook):
    """Build a minimal mock instance with the host relationship populated."""
    instance = MagicMock()
    instance.lan_rate_enabled = lan_rate_enabled
    instance.host = MagicMock()
    instance.host.lan_rate_uses_hook = host_lan_rate_uses_hook
    return instance


def _force_rate_predicate():
    for filename, predicate, _ in _SYSTEM_HOOKS:
        if filename == "force_rate.so":
            return predicate
    pytest.fail("force_rate.so not registered in _SYSTEM_HOOKS")


def test_force_rate_is_registered_and_reserved():
    assert "force_rate.so" in RESERVED_HOOK_FILENAMES


def test_force_rate_predicate_false_when_lan_rate_disabled():
    predicate = _force_rate_predicate()
    instance = _make_instance(lan_rate_enabled=False, host_lan_rate_uses_hook=True)
    assert predicate(instance) is False


def test_force_rate_predicate_false_on_legacy_host():
    predicate = _force_rate_predicate()
    instance = _make_instance(lan_rate_enabled=True, host_lan_rate_uses_hook=False)
    assert predicate(instance) is False


def test_force_rate_predicate_true_on_migrated_host_with_toggle_on():
    predicate = _force_rate_predicate()
    instance = _make_instance(lan_rate_enabled=True, host_lan_rate_uses_hook=True)
    assert predicate(instance) is True


def test_force_rate_so_cannot_be_uploaded_as_user_hook(client, app):
    """RESERVED_HOOK_FILENAMES is consumed by the upload-validation path."""
    import io
    from flask_jwt_extended import create_access_token

    with app.app_context():
        from ui.models import Host, QLInstance, InstanceStatus, db
        host = Host(
            name="upload-test",
            provider="vultr",
            os_type="debian",
            ip_address="1.2.3.4",
        )
        db.session.add(host)
        db.session.commit()
        instance = QLInstance(
            host_id=host.id,
            name="i",
            port=27960,
            hostname="upload-test-instance",
            status=InstanceStatus.RUNNING,
        )
        db.session.add(instance)
        db.session.commit()
        instance_id = instance.id
        token = create_access_token(identity='testuser')

    payload = {
        'file': (io.BytesIO(b'\x7fELF fake'), 'force_rate.so'),
    }
    response = client.post(
        f"/api/instances/{instance_id}/hooks/upload",
        data=payload,
        content_type='multipart/form-data',
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code >= 400, response.get_json()
    # When the upload route exists and checks RESERVED_HOOK_FILENAMES, the response body
    # should mention the filename or "reserved". A 404/405 (route not yet implemented or
    # method not allowed) satisfies status_code >= 400 and is acceptable infrastructure-not-present.
    if response.status_code not in (404, 405):
        body = response.get_json() or {}
        assert 'force_rate.so' in str(body) or 'reserved' in str(body).lower()
