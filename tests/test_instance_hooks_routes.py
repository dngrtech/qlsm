import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.helpers import auth_headers
from ui import db
from ui.models import BinaryMetadata, Host, InstanceStatus, QLInstance


@pytest.fixture
def headers(app):
    return auth_headers(app, "testuser")


@pytest.fixture
def instance_with_scripts(app, tmp_path, monkeypatch):
    with app.app_context():
        host = Host(name="h1", provider="vultr", ip_address="1.1.1.1")
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(
            name="i1",
            port=27960,
            hostname="hn",
            host_id=host.id,
            qlx_plugins="",
            ld_preload_hooks="a.so,b.so",
            status=InstanceStatus.RUNNING,
            zmq_rcon_port=28888,
            zmq_rcon_password="x",
            zmq_stats_port=29999,
            zmq_stats_password="y",
        )
        db.session.add(inst)
        db.session.commit()

        scripts = tmp_path / "configs" / host.name / str(inst.id) / "scripts"
        scripts.mkdir(parents=True)
        for filename in ("a.so", "b.so", "c.so"):
            (scripts / filename).write_bytes(b"\x7fELF" + b"\x00" * 32)
        monkeypatch.setattr(
            "ui.routes.instance_hooks_routes.CONFIGS_BASE",
            str(tmp_path / "configs"),
        )
        yield inst


def _put(client, headers, instance_id, body):
    return client.put(
        f"/api/instances/{instance_id}/hooks",
        data=json.dumps(body),
        headers={**headers, "Content-Type": "application/json"},
    )


def test_get_lists_available_with_enabled_and_order(client, headers, instance_with_scripts):
    response = client.get(f"/api/instances/{instance_with_scripts.id}/hooks", headers=headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    by_name = {hook["filename"]: hook for hook in data["available"]}
    assert by_name["a.so"]["enabled"] is True
    assert by_name["a.so"]["order"] == 1
    assert by_name["b.so"]["enabled"] is True
    assert by_name["b.so"]["order"] == 2
    assert by_name["c.so"]["enabled"] is False
    assert by_name["c.so"]["order"] is None
    assert data["system_hooks_active"] == []


def test_get_includes_binary_metadata_description(app, client, headers, instance_with_scripts):
    with app.app_context():
        db.session.add(BinaryMetadata(
            context_type="instance",
            context_key=str(instance_with_scripts.id),
            file_path="a.so",
            description="Speed hook",
        ))
        db.session.commit()

    response = client.get(f"/api/instances/{instance_with_scripts.id}/hooks", headers=headers)
    by_name = {hook["filename"]: hook for hook in response.get_json()["data"]["available"]}
    assert by_name["a.so"]["description"] == "Speed hook"
    assert by_name["b.so"]["description"] == ""


def test_get_excludes_orphaned_enabled_entries(client, headers, instance_with_scripts, tmp_path):
    os.remove(tmp_path / "configs" / "h1" / str(instance_with_scripts.id) / "scripts" / "a.so")
    response = client.get(f"/api/instances/{instance_with_scripts.id}/hooks", headers=headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert all(hook["filename"] != "a.so" for hook in data["available"])


def test_get_404_when_instance_missing(client, headers):
    response = client.get("/api/instances/99999/hooks", headers=headers)
    assert response.status_code == 404


def test_get_requires_auth(client, instance_with_scripts):
    response = client.get(f"/api/instances/{instance_with_scripts.id}/hooks")
    assert response.status_code == 401


def test_put_rejects_missing_body(client, headers, instance_with_scripts):
    response = client.put(
        f"/api/instances/{instance_with_scripts.id}/hooks",
        data="not json",
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_put_rejects_non_list(client, headers, instance_with_scripts):
    response = _put(client, headers, instance_with_scripts.id, {"enabled": "a.so"})
    assert response.status_code == 400


def test_put_rejects_path_traversal(client, headers, instance_with_scripts):
    response = _put(client, headers, instance_with_scripts.id, {"enabled": ["../etc/passwd.so"]})
    assert response.status_code == 400


def test_put_rejects_non_so_extension(client, headers, instance_with_scripts):
    response = _put(client, headers, instance_with_scripts.id, {"enabled": ["evil.txt"]})
    assert response.status_code == 400


def test_put_rejects_reserved_filename(client, headers, instance_with_scripts):
    response = _put(client, headers, instance_with_scripts.id, {"enabled": ["force_rate.so"]})
    assert response.status_code == 400
    assert "reserved" in response.get_json()["error"]["message"].lower()


def test_put_rejects_nonexistent_file(client, headers, instance_with_scripts):
    response = _put(client, headers, instance_with_scripts.id, {"enabled": ["nope.so"]})
    assert response.status_code == 400


def test_put_rejects_non_elf(client, headers, instance_with_scripts, tmp_path):
    bad = tmp_path / "configs" / "h1" / str(instance_with_scripts.id) / "scripts" / "bad.so"
    bad.write_bytes(b"NOT_ELF")
    response = _put(client, headers, instance_with_scripts.id, {"enabled": ["bad.so"]})
    assert response.status_code == 400


def test_put_rejects_duplicates(client, headers, instance_with_scripts):
    response = _put(client, headers, instance_with_scripts.id, {"enabled": ["a.so", "a.so"]})
    assert response.status_code == 400


def test_put_returns_409_when_instance_lock_held(client, headers, instance_with_scripts):
    with patch("ui.routes.instance_hooks_routes.acquire_lock", return_value=False):
        response = _put(client, headers, instance_with_scripts.id, {"enabled": ["a.so"]})
    assert response.status_code == 409


def test_put_enqueue_failure_reverts_hooks_and_marks_error(
    app,
    client,
    headers,
    instance_with_scripts,
):
    original = instance_with_scripts.ld_preload_hooks
    with patch("ui.routes.instance_hooks_routes.acquire_lock", return_value=True), \
            patch("ui.routes.instance_hooks_routes.release_lock") as release, \
            patch("ui.routes.instance_hooks_routes.enqueue_apply_hooks", return_value=None):
        response = _put(client, headers, instance_with_scripts.id, {"enabled": ["b.so"]})

    assert response.status_code == 500
    with app.app_context():
        fresh = db.session.get(QLInstance, instance_with_scripts.id)
        assert fresh.ld_preload_hooks == original
        assert fresh.status == InstanceStatus.ERROR
    release.assert_called_once()


def test_put_stopped_instance_enqueues_without_restart(app, client, headers, instance_with_scripts):
    with app.app_context():
        instance_with_scripts.status = InstanceStatus.STOPPED
        db.session.commit()

    with patch("ui.routes.instance_hooks_routes.acquire_lock", return_value=True), \
            patch("ui.routes.instance_hooks_routes.release_lock"), \
            patch("ui.routes.instance_hooks_routes.enqueue_apply_hooks") as enq:
        enq.return_value = SimpleNamespace(id="job-id-stopped")
        response = _put(client, headers, instance_with_scripts.id, {"enabled": ["a.so"]})

    assert response.status_code == 202
    assert enq.call_args.kwargs["restart_service"] is False


def test_put_happy_path_persists_and_enqueues(app, client, headers, instance_with_scripts):
    with patch("ui.routes.instance_hooks_routes.acquire_lock", return_value=True), \
            patch("ui.routes.instance_hooks_routes.release_lock"), \
            patch("ui.routes.instance_hooks_routes.enqueue_apply_hooks") as enq:
        enq.return_value = SimpleNamespace(id="job-id-123")
        response = _put(client, headers, instance_with_scripts.id, {"enabled": ["b.so", "a.so"]})

    assert response.status_code == 202
    assert response.get_json()["data"]["task_id"] == "job-id-123"
    with app.app_context():
        fresh = db.session.get(QLInstance, instance_with_scripts.id)
        assert fresh.ld_preload_hooks == "b.so,a.so"
        assert fresh.status == InstanceStatus.CONFIGURING
