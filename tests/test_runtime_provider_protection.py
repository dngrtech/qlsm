"""A referenced provider cannot disappear, including during host creation."""
import io
import json
import shutil
import zipfile

import pytest
from flask_jwt_extended import create_access_token

from tests.test_custom_runtime_hosts import hosted_runtime  # noqa: F401
from tests.test_custom_runtime_release import PROVIDER, activate, runtime_package
from ui import db
from ui.addons.install import install_addon_zip, uninstall_addon
from ui.addons.registry import get_addon
from ui.models import AddonState, Host, HostStatus, PluginRepository


def plain_package():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("qlsm-addon.json", json.dumps({
            "id": PROVIDER, "name": "Fixture runtime", "version": "3.0",
        }))
    return buffer.getvalue()


@pytest.fixture
def provider(app, tmp_path):
    packages = tmp_path / "packages"
    package, digest = runtime_package()
    install_addon_zip(package, packages)
    activate(app, packages)
    with app.app_context():
        headers = {"Authorization": f"Bearer {create_access_token(identity='operator')}"}
    return packages, digest, headers


def add_dependent_host(status=HostStatus.ACTIVE):
    host = Host(name="dependent", provider="standalone", runtime="custom",
                runtime_provider_id=PROVIDER, runtime_release_sha256="a" * 64,
                runtime_plugin_api="minqlx", status=status)
    db.session.add(host)
    db.session.commit()
    return host.id


@pytest.mark.parametrize("status", [HostStatus.ACTIVE, HostStatus.ERROR, HostStatus.PENDING])
def test_global_disable_refuses_every_referenced_host(app, provider, status):
    with app.app_context():
        add_dependent_host(status)
        settings = get_addon(PROVIDER).ctx.settings
        with pytest.raises(ValueError, match="dependent"):
            settings.set_enabled("global", 0, False)
        assert settings.is_layer_enabled("global", 0) is True


def test_scoped_disable_does_not_disable_the_runtime_provider(app, provider):
    with app.app_context():
        host_id = add_dependent_host()
        settings = get_addon(PROVIDER).ctx.settings
        settings.set_enabled("host", host_id, True)
        settings.set_enabled("host", host_id, False)
        assert settings.is_layer_enabled("host", host_id) is False
        assert settings.is_layer_enabled("global", 0) is True


def test_disable_api_reports_dependency_and_rolls_back_settings(app, client, provider):
    _, _, headers = provider
    with app.app_context():
        host_id = add_dependent_host()
        get_addon(PROVIDER).ctx.settings._manifest["settings"] = {
            "global": [{"key": "label", "type": "string"}],
        }
        get_addon(PROVIDER).ctx.settings.set(values={"label": "original"})
    response = client.put(f"/api/addons/{PROVIDER}/state", headers=headers,
                          json={"enabled": False, "settings": {"label": "changed"}})
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["dependent_hosts"] == [{"id": host_id, "name": "dependent"}]
    with app.app_context():
        assert get_addon(PROVIDER).ctx.settings.get()["label"] == "original"
        assert get_addon(PROVIDER).globally_enabled is True


@pytest.mark.parametrize("operation", ["uninstall", "replace"])
def test_shared_install_service_keeps_referenced_package(app, provider, operation):
    packages, digest, _ = provider
    with app.app_context():
        add_dependent_host()
        with pytest.raises(ValueError, match="dependent"):
            if operation == "uninstall":
                uninstall_addon(PROVIDER, packages)
            else:
                install_addon_zip(plain_package(), packages)
    manifest = json.loads((packages / PROVIDER / "qlsm-addon.json").read_text())
    assert manifest["custom_runtime"]["sha256"] == digest
    assert (packages / ".runtime-releases" / PROVIDER / digest / "bundle.tar.gz").is_file()


def test_upload_and_uninstall_report_in_use_conflict(app, client, provider):
    packages, _, headers = provider
    with app.app_context():
        host_id = add_dependent_host()
    responses = [
        client.delete(f"/api/addons/{PROVIDER}", headers=headers),
        client.post("/api/addons/install", headers=headers,
                    data={"file": (io.BytesIO(plain_package()), "replacement.zip")}),
    ]
    for response in responses:
        assert response.status_code == 409, response.get_json()
        assert response.get_json()["error"]["dependent_hosts"] == [{"id": host_id, "name": "dependent"}]
    assert (packages / PROVIDER).is_dir()


@pytest.mark.parametrize('referenced,expected_status', [(True, 409), (False, 404)])
def test_missing_provider_uninstall_preserves_state_and_reports_dependencies(
        app, client, provider, referenced, expected_status):
    packages, digest, headers = provider
    with app.app_context():
        host_id = add_dependent_host(HostStatus.ERROR) if referenced else None
    retained_bundle = packages / '.runtime-releases' / PROVIDER / digest / 'bundle.tar.gz'
    original_bundle = retained_bundle.read_bytes()
    shutil.rmtree(packages / PROVIDER)  # The package was removed outside QLSM.

    response = client.delete(f'/api/addons/{PROVIDER}', headers=headers)

    assert response.status_code == expected_status
    if referenced:
        error = response.get_json()['error']
        assert error['code'] == 'runtime_provider_in_use'
        assert error['dependent_hosts'] == [{'id': host_id, 'name': 'dependent'}]
    assert not (packages / PROVIDER).exists()
    assert retained_bundle.read_bytes() == original_bundle
    with app.app_context():
        assert get_addon(PROVIDER).globally_enabled is True
        assert Host.query.count() == int(referenced)
        if referenced:
            assert db.session.get(Host, host_id).runtime_provider_id == PROVIDER


def test_repository_replacement_cannot_remove_runtime(app, client, provider, monkeypatch):
    from ui import plugin_repositories

    packages, _, headers = provider
    with app.app_context():
        add_dependent_host()
        repo = PluginRepository(name="runtime repo", url="https://example.invalid/runtime")
        repo.manifest_json = json.dumps({"addons": [{"id": PROVIDER, "name": "Fixture runtime",
                                                    "version": "3.0", "zip": "runtime.zip"}]})
        db.session.add(repo)
        db.session.commit()
        repo_id = repo.id
    monkeypatch.setattr(plugin_repositories, "_fetch", lambda *_args: plain_package())
    response = client.post(f"/api/plugin-repositories/{repo_id}/install-addon", headers=headers,
                           json={"id": PROVIDER})
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"]["dependent_hosts"][0]["name"] == "dependent"
    assert "custom_runtime" in json.loads((packages / PROVIDER / "qlsm-addon.json").read_text())


def test_runtime_update_keeps_all_retained_releases(app, provider):
    packages, previous, _ = provider
    newer, digest = runtime_package("2.0")
    with app.app_context():
        host_id = add_dependent_host()
        install_addon_zip(newer, packages)
        assert db.session.get(Host, host_id).runtime_release_sha256 == "a" * 64
    for sha in (previous, digest):
        assert (packages / ".runtime-releases" / PROVIDER / sha / "bundle.tar.gz").is_file()


@pytest.mark.parametrize("mutation", ["disable", "uninstall", "replace"])
def test_creation_rechecks_provider_after_ssh_probe(app, client, hosted_runtime, monkeypatch, mutation):
    from ui.routes import host_routes

    headers, payload, detected, queued = hosted_runtime

    def probe(**_kwargs):
        packages = app.config["ADDON_PACKAGES_DIR"]
        if mutation == "disable":
            get_addon(PROVIDER).ctx.settings.set_enabled("global", 0, False)
        elif mutation == "uninstall":
            uninstall_addon(PROVIDER, packages)
        else:
            install_addon_zip(plain_package(), packages)
        return detected

    monkeypatch.setattr(host_routes, "detect_remote_os", probe)
    response = client.post("/api/hosts/", headers=headers, json=payload)
    assert response.status_code == 409, response.get_json()
    assert queued == []
    with app.app_context():
        assert Host.query.count() == 0


def test_removing_last_dependent_host_allows_lifecycle_changes(app, provider):
    packages, _, _ = provider
    with app.app_context():
        host_id = add_dependent_host()
        db.session.delete(db.session.get(Host, host_id))
        db.session.commit()
        get_addon(PROVIDER).ctx.settings.set_enabled("global", 0, False)
        assert AddonState.query.filter_by(addon_id=PROVIDER, scope="global").one().enabled is False
        assert uninstall_addon(PROVIDER, packages) is True


@pytest.mark.parametrize("finish", ["commit", "rollback"])
def test_deferred_settings_hold_provider_lock_until_transaction_finishes(app, provider, monkeypatch, finish):
    from ui.addons import runtime_protection

    packages, _, _ = provider
    monkeypatch.setattr(runtime_protection, "LOCK_TIMEOUT_SECONDS", 0)
    with app.app_context():
        settings = get_addon(PROVIDER).ctx.settings
        settings.set_enabled("global", 0, False, commit=False)
        with pytest.raises(runtime_protection.RuntimeProviderConflict):
            with runtime_protection.provider_lifecycle_lock(PROVIDER, packages):
                pytest.fail("A host could be pinned before the disable transaction finished")
        getattr(db.session, finish)()
        with runtime_protection.provider_lifecycle_lock(PROVIDER, packages):
            assert settings.is_layer_enabled("global", 0) is (finish == "rollback")


def test_archive_maintenance_excludes_packages_and_settings(app, provider, monkeypatch):
    from ui.addons import runtime_protection

    packages, digest, _ = provider
    monkeypatch.setattr(runtime_protection, "LOCK_TIMEOUT_SECONDS", 0)
    with app.app_context():
        with runtime_protection.addon_lifecycle_maintenance_lock(packages):
            with pytest.raises(runtime_protection.RuntimeProviderConflict):
                install_addon_zip(plain_package(), packages)
            with pytest.raises(runtime_protection.RuntimeProviderConflict):
                get_addon(PROVIDER).ctx.settings.set_enabled("global", 0, False)
        assert get_addon(PROVIDER).globally_enabled is True
        manifest = json.loads((packages / PROVIDER / "qlsm-addon.json").read_text())
        assert manifest["custom_runtime"]["sha256"] == digest


def test_package_tree_swap_cannot_replace_the_provider_lock(tmp_path, monkeypatch):
    import shutil
    from ui.addons import runtime_protection

    packages = tmp_path / "packages"
    packages.mkdir()
    monkeypatch.setattr(runtime_protection, "LOCK_TIMEOUT_SECONDS", 0)
    with runtime_protection.provider_lifecycle_lock(PROVIDER, packages):
        shutil.rmtree(packages)
        packages.mkdir()
        with pytest.raises(runtime_protection.RuntimeProviderConflict):
            with runtime_protection.provider_lifecycle_lock(PROVIDER, packages):
                pytest.fail("Replacing packages must not bypass the live lock")
    with runtime_protection.provider_lifecycle_lock(PROVIDER, packages):
        pass


@pytest.mark.parametrize("lock_error", [False, True])
def test_creation_keeps_restore_out_until_initial_entity_lock_is_decided(app, client, hosted_runtime, monkeypatch, lock_error):
    from ui.addons import runtime_protection
    from ui.routes import host_routes

    headers, payload, _, queued = hosted_runtime
    restore_could_overlap = []
    monkeypatch.setattr(runtime_protection, "LOCK_TIMEOUT_SECONDS", 0)
    delete = db.session.delete

    def deny_entity_lock(*_args, **_kwargs):
        if lock_error:
            raise RuntimeError("Redis connection failed")
        return False

    def check_cleanup_fence(host):
        try:
            with runtime_protection.addon_lifecycle_maintenance_lock():
                restore_could_overlap.append(True)
        except runtime_protection.RuntimeProviderConflict:
            restore_could_overlap.append(False)
        delete(host)

    monkeypatch.setattr(host_routes, "acquire_lock", deny_entity_lock)
    monkeypatch.setattr(db.session, "delete", check_cleanup_fence)
    response = client.post("/api/hosts/", headers=headers, json=payload)
    assert response.status_code == (500 if lock_error else 409)
    assert restore_could_overlap == [False]
    assert queued == []
    with app.app_context():
        assert Host.query.count() == 0


@pytest.mark.parametrize("operation", ["uninstall", "replace", "update"])
def test_destructive_package_change_requires_database_context(app, provider, operation):
    from ui.addons.runtime_protection import RuntimeProviderConflict

    packages, digest, _ = provider
    with app.app_context():
        add_dependent_host()
    with pytest.raises(RuntimeProviderConflict, match="database"):
        if operation == "uninstall":
            uninstall_addon(PROVIDER, packages)
        else:
            blob = runtime_package("2.0")[0] if operation == "update" else plain_package()
            install_addon_zip(blob, packages)
    manifest = json.loads((packages / PROVIDER / "qlsm-addon.json").read_text())
    assert manifest["custom_runtime"]["sha256"] == digest


def test_maintenance_is_available_as_a_provider_id(tmp_path, monkeypatch):
    from ui.addons import runtime_protection as protection

    monkeypatch.setattr(protection, "LOCK_TIMEOUT_SECONDS", 0)
    with protection.provider_lifecycle_lock("maintenance", tmp_path):
        with pytest.raises(protection.RuntimeProviderConflict):
            with protection.addon_lifecycle_maintenance_lock(tmp_path):
                pytest.fail("backup overlapped the provider lock")


def test_bundled_provider_uninstall_reports_dependent_hosts(app, client, provider, monkeypatch):
    _, _, headers = provider
    with app.app_context():
        monkeypatch.setattr(get_addon(PROVIDER), "source", "bundled")
        host_id = add_dependent_host()
    response = client.delete(f"/api/addons/{PROVIDER}", headers=headers)
    assert response.status_code == 409
    assert response.get_json()["error"]["dependent_hosts"] == [{"id": host_id, "name": "dependent"}]


def test_scope_lookup_is_fenced_before_writing(app, client, provider, monkeypatch):
    from ui.addons import runtime_protection as protection
    from ui.routes import addon_routes

    _, _, headers = provider
    with app.app_context():
        host_id = add_dependent_host()
    monkeypatch.setattr(protection, "LOCK_TIMEOUT_SECONDS", 0)
    parse = addon_routes._scope_args
    overlaps = []

    def check_lookup():
        try:
            with protection.addon_lifecycle_maintenance_lock():
                overlaps.append(True)
        except protection.RuntimeProviderConflict:
            overlaps.append(False)
        return parse()

    monkeypatch.setattr(addon_routes, "_scope_args", check_lookup)
    response = client.put(f"/api/addons/{PROVIDER}/state?scope=host&scope_id={host_id}",
                          headers=headers, json={"enabled": True})
    assert response.status_code == 200
    assert overlaps == [False]


def test_global_state_is_outside_scope_cleanup(app, provider):
    from ui.addons.settings import AddonSettingsError, delete_scope_rows

    with app.app_context():
        add_dependent_host()
        with pytest.raises(AddonSettingsError):
            delete_scope_rows("global", 0, commit=True)
        assert get_addon(PROVIDER).globally_enabled


@pytest.mark.parametrize("finish", ["commit", "rollback"])
def test_scope_cleanup_fences_archive_through_transaction(app, provider, monkeypatch, finish):
    from ui.addons import runtime_protection as protection
    from ui.addons.settings import delete_scope_rows

    monkeypatch.setattr(protection, "LOCK_TIMEOUT_SECONDS", 0)
    with app.app_context():
        host_id = add_dependent_host()
        settings = get_addon(PROVIDER).ctx.settings
        settings.set_enabled("host", host_id, True)
        assert delete_scope_rows("host", host_id) == 1
        with pytest.raises(protection.RuntimeProviderConflict):
            with protection.addon_lifecycle_maintenance_lock():
                pytest.fail("backup overlapped uncommitted scope cleanup")
        getattr(db.session, finish)()
        with protection.addon_lifecycle_maintenance_lock():
            assert settings.is_layer_enabled("host", host_id) == (finish == "rollback")


def test_credential_work_excludes_restore_even_on_provider_rejection(app, client, hosted_runtime, monkeypatch):
    from ui.addons import runtime_protection as protection
    from ui.routes import host_routes

    headers, payload, detected, queued = hosted_runtime
    monkeypatch.setattr(protection, "LOCK_TIMEOUT_SECONDS", 0)
    overlap = []

    def observe(stage):
        try:
            with protection.addon_lifecycle_maintenance_lock():
                overlap.append((stage, True))
        except protection.RuntimeProviderConflict:
            overlap.append((stage, False))

    def write(*_args):
        observe("write")
        return "fixture-key"

    def probe(**_kwargs):
        observe("probe")
        get_addon(PROVIDER).ctx.settings.set_enabled("global", 0, False)
        return detected

    monkeypatch.setattr(host_routes, "_write_standalone_private_key", write)
    monkeypatch.setattr(host_routes, "detect_remote_os", probe)
    monkeypatch.setattr(host_routes, "_cleanup_local_key_material", lambda *_: observe("cleanup"))
    response = client.post("/api/hosts/", headers=headers, json=payload)
    assert response.status_code == 409
    assert overlap == [("write", False), ("probe", False), ("cleanup", False)]
    assert queued == []


def test_creation_revalidates_name_before_touching_keys(app, client, hosted_runtime, monkeypatch):
    from ui.routes import host_routes

    headers, payload, _, queued = hosted_runtime
    approve = host_routes.approved_release

    def approve_after_name_taken(provider_id):
        release = approve(provider_id)
        if Host.query.count() == 0:
            db.session.add(Host(name=payload["name"], provider="standalone"))
            db.session.commit()
        return release

    writes = []
    monkeypatch.setattr(host_routes, "approved_release", approve_after_name_taken)
    monkeypatch.setattr(host_routes, "_write_standalone_private_key", lambda *_: writes.append(True))
    response = client.post("/api/hosts/", headers=headers, json=payload)
    assert response.status_code == 409
    assert writes == []
    assert queued == []


def test_lock_directory_can_be_checked_without_creating_it(tmp_path):
    from pathlib import Path
    from ui.addons import runtime_protection as protection

    packages = tmp_path / "data" / "packages"
    directory = protection.addon_lifecycle_lock_directory(packages)
    assert isinstance(directory, Path)
    assert not directory.exists()
    with protection.provider_lifecycle_lock(PROVIDER, packages):
        assert directory.is_dir()


@pytest.mark.parametrize("outer_runtime", ["custom", "minqlx"])
def test_same_name_standalone_creations_serialize_before_key_work(
        app, client, hosted_runtime, monkeypatch, outer_runtime):
    from ui.addons import runtime_protection as protection
    from ui.routes import host_routes

    headers, payload, _, queued = hosted_runtime
    monkeypatch.setattr(protection, "LOCK_TIMEOUT_SECONDS", 0)
    inner_runtime = "minqlx" if outer_runtime == "custom" else "custom"
    nested_status = []
    writes = []

    def write(name, _credential):
        writes.append(name)
        if len(writes) == 1:
            inner = dict(payload, runtime=inner_runtime, name=name.upper())
            nested = client.post("/api/hosts/", headers=headers, json=inner)
            nested_status.append(nested.status_code)
        return "fixture-key"

    monkeypatch.setattr(host_routes, "_write_standalone_private_key", write)
    response = client.post("/api/hosts/", headers=headers, json=dict(payload, runtime=outer_runtime))
    assert nested_status == [409]
    assert writes == [payload["name"]]
    assert response.status_code == 201
    assert len(queued) == 1
    with app.app_context():
        assert Host.query.one().runtime == outer_runtime
