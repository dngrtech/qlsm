import pytest
from flask_jwt_extended import create_access_token

from tests.test_custom_runtime_release import PROVIDER, activate, runtime_package
from ui import db
from ui.addons.install import install_addon_zip
from ui.models import Host, HostStatus


@pytest.fixture
def hosted_runtime(app, tmp_path, monkeypatch):
    from ui.routes import host_routes

    package, digest = runtime_package()
    packages = tmp_path / "packages"
    install_addon_zip(package, packages)
    activate(app, packages)
    with app.app_context():
        headers = {"Authorization": f"Bearer {create_access_token(identity='testuser')}"}
    kwargs = {
        "name": "custom-host", "provider": "standalone", "runtime": "custom",
        "runtime_provider_id": PROVIDER, "runtime_release_sha256": digest,
        "ip_address": "192.0.2.42", "ssh_user": "root", "timezone": "UTC",
        "ssh_auth_method": "key", "ssh_key": "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----",
    }
    detected = {"id": "ubuntu", "os_type": "ubuntu", "version_id": "24.04",
                "pretty_name": "Ubuntu 24.04", "arch": "x86_64", "python_version": "3.12.3"}
    queued = []
    monkeypatch.setattr(host_routes, "detect_remote_os", lambda **_kwargs: detected)
    monkeypatch.setattr(host_routes, "_write_standalone_private_key", lambda *_args: str(tmp_path / "key"))
    monkeypatch.setattr(host_routes, "acquire_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(host_routes, "enqueue_task", lambda *args, **_kwargs: queued.append(args))
    return headers, kwargs, detected, queued


def test_custom_standalone_records_exact_displayed_pin(app, client, hosted_runtime):
    headers, payload, _, queued = hosted_runtime
    options = client.get("/api/hosts/runtime-options", headers=headers).get_json()["data"]["providers"]
    assert options[0]["provider_id"] == PROVIDER
    assert options[0]["sha256"] == payload["runtime_release_sha256"]
    result = client.post("/api/hosts/", headers=headers, json=payload)
    assert result.status_code == 201, result.get_json()
    data = result.get_json()["data"]
    assert data["runtime"] == "custom"
    assert data["runtime_provider_id"] == PROVIDER
    assert data["runtime_release_sha256"] == payload["runtime_release_sha256"]
    assert data["runtime_plugin_api"] == "minqlx"
    assert data["runtime_upgrade"]["visible"] is False
    assert len(queued) == 1


@pytest.mark.parametrize(("override", "status"), [
    ({"runtime_release_sha256": "b" * 64}, 409),
    ({"runtime_provider_id": "missing-addon"}, 400),
    ({"provider": "self"}, 400),
    ({"provider": "vultr"}, 400),
])
def test_stale_or_unsupported_custom_create_does_not_enqueue(client, hosted_runtime, override, status):
    headers, payload, _, queued = hosted_runtime
    result = client.post("/api/hosts/", headers=headers, json={**payload, **override})
    assert result.status_code == status
    assert queued == []


def test_wrong_platform_is_rejected_before_queue(client, hosted_runtime):
    headers, payload, platform, queued = hosted_runtime
    platform["arch"] = "aarch64"
    result = client.post("/api/hosts/", headers=headers, json=payload)
    assert result.status_code == 400
    assert "x86_64" in result.get_json()["error"]["message"]
    assert queued == []


def test_custom_runtime_cannot_be_set_on_existing_host(app, client, hosted_runtime):
    headers, _, _, _ = hosted_runtime
    with app.app_context():
        host = Host(name="existing", provider="standalone", status=HostStatus.ACTIVE)
        db.session.add(host)
        db.session.commit()
        host_id = host.id
    response = client.put(f"/api/hosts/{host_id}", headers=headers, json={"runtime": "custom"})
    assert response.status_code == 400
    assert "creation" in response.get_json()["error"]["message"]


def test_custom_host_pin_survives_backup_restore():
    from ui.task_logic.backup_db_export import _host_row
    from ui.task_logic.backup_db_import import _host_from_row

    host = Host(id=123, name="test", provider="standalone", runtime="custom",
                runtime_provider_id=PROVIDER, runtime_release_sha256="a" * 64, runtime_plugin_api="minqlx")
    restored = _host_from_row(_host_row(host))
    assert restored.runtime == "custom"
    assert restored.runtime_provider_id == PROVIDER
    assert restored.runtime_release_sha256 == "a" * 64
    assert restored.runtime_plugin_api == "minqlx"


def test_upgrade_endpoint_rejects_both_custom_conversion_directions(app, client, hosted_runtime):
    headers, payload, _, _ = hosted_runtime
    custom = client.post("/api/hosts/", headers=headers, json=payload).get_json()["data"]
    with app.app_context():
        standard = Host(name="standard", provider="standalone", status=HostStatus.ACTIVE)
        db.session.add(standard)
        db.session.commit()
        standard_id = standard.id
    for host_id, target in ((standard_id, "custom"), (custom["id"], "minqlxtended")):
        response = client.post(f"/api/hosts/{host_id}/runtime-upgrade", headers=headers,
                               json={"target_runtime": target, "fingerprint": "fixture"})
        assert response.status_code == 400
        assert "to or from Custom" in response.get_json()["error"]["message"]
