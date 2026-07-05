import os

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

        user_hooks = tmp_path / "configs" / host.name / str(inst.id) / "user-hooks"
        user_hooks.mkdir(parents=True)
        for filename in ("a.so", "b.so", "c.so"):
            (user_hooks / filename).write_bytes(b"\x7fELF" + b"\x00" * 32)

        monkeypatch.setattr(
            "ui.task_logic.hook_paths.CONFIGS_BASE",
            str(tmp_path / "configs"),
        )
        yield inst


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
    os.remove(tmp_path / "configs" / "h1" / str(instance_with_scripts.id) / "user-hooks" / "a.so")
    response = client.get(f"/api/instances/{instance_with_scripts.id}/hooks", headers=headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    # a.so is still in ld_preload_hooks but absent from disk — shown with missing=True
    missing = [h for h in data["available"] if h["filename"] == "a.so"]
    assert len(missing) == 1
    assert missing[0]["missing"] is True


def test_get_ignores_legacy_scripts_so_files(client, headers, instance_with_scripts, tmp_path):
    legacy = tmp_path / "configs" / "h1" / str(instance_with_scripts.id) / "scripts"
    legacy.mkdir(parents=True)
    (legacy / "legacy.so").write_bytes(b"\x7fELF")
    response = client.get(f"/api/instances/{instance_with_scripts.id}/hooks", headers=headers)
    filenames = {h["filename"] for h in response.get_json()["data"]["available"]}
    assert "legacy.so" not in filenames


def test_legacy_hook_in_scripts_still_applies_but_not_listed(
    app, client, headers, instance_with_scripts, tmp_path, monkeypatch
):
    """Pre-existing instances with a .so only in scripts/ must continue to resolve
    through the LD_PRELOAD fallback but must NOT appear in GET /hooks."""
    from ui.task_logic import ansible_instance_mgmt

    scripts = tmp_path / "configs" / "h1" / str(instance_with_scripts.id) / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "legacy.so").write_bytes(b"\x7fELF" + b"\x00" * 32)

    monkeypatch.setattr(ansible_instance_mgmt, "CONFIGS_BASE", str(tmp_path / "configs"), raising=False)

    with app.app_context():
        from ui.models import QLInstance, db
        inst = db.session.get(QLInstance, instance_with_scripts.id)
        inst.ld_preload_hooks = "legacy.so"
        db.session.commit()

        from ui.task_logic.ansible_instance_mgmt import _build_ld_preload_paths
        result = _build_ld_preload_paths(inst)

    assert "minqlx-plugins/legacy.so" in result

    response = client.get(f"/api/instances/{instance_with_scripts.id}/hooks", headers=headers)
    filenames = {h["filename"] for h in response.get_json()["data"]["available"]}
    assert "legacy.so" not in filenames


def test_get_404_when_instance_missing(client, headers):
    response = client.get("/api/instances/99999/hooks", headers=headers)
    assert response.status_code == 404


def test_get_requires_auth(client, instance_with_scripts):
    response = client.get(f"/api/instances/{instance_with_scripts.id}/hooks")
    assert response.status_code == 401


def test_put_hooks_route_removed(client):
    resp = client.put('/api/instances/1/hooks', json={'enabled': []})
    assert resp.status_code == 405


def test_apply_instance_hooks_task_still_importable():
    from ui.tasks import apply_instance_hooks
    assert callable(apply_instance_hooks)
