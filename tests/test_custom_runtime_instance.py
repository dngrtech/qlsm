from pathlib import Path
from types import SimpleNamespace

from flask_jwt_extended import create_access_token

from tests.test_custom_runtime_release import PROVIDER, activate, runtime_package
from tests.test_instance_runtime_paths import _instance
from ui import db
from ui.addons.install import install_addon_zip
from ui.runtime import instance_runtime_extravars
from ui.task_logic import ansible_instance_mgmt as mgmt


def install_test_runtime(app, tmp_path):
    packages = tmp_path / "packages"
    package, digest = runtime_package(metadata={"forced_lan_rate": True})
    install_addon_zip(package, packages)
    activate(app, packages)
    inst = _instance(app, "custom", 27960, lan_rate=False)
    with app.app_context():
        instance = db.session.get(type(inst), inst.id)
        instance.host.runtime_provider_id = PROVIDER
        instance.host.runtime_release_sha256 = digest
        instance.host.runtime_plugin_api = "minqlx"
        instance.qlx_plugins = "example, example, ranked"
        db.session.commit()
    return inst, digest


def test_custom_deploy_uses_pinned_launcher_and_pool(app, tmp_path):
    inst, digest = install_test_runtime(app, tmp_path)
    with app.app_context():
        instance = db.session.get(type(inst), inst.id)
        extra = instance_runtime_extravars(instance)
        args = mgmt._build_qlds_args_string(instance)
    assert extra["runtime_launch_path"] == f"/var/lib/qlsm/custom-runtime/{digest}/launch.sh"
    assert extra["skip_pip_install"] is True
    assert extra["runtime_plugins_dirname"] == "minqlx-plugins"
    assert Path(extra["common_plugins_operator_src"]) == Path("data/shared-plugins/minqlx").resolve()
    assert '+set qlx_plugins "serverchecker, example, ranked"' in args
    assert '+set sv_lanForceRate 1' in args


def test_all_preload_sources_honor_provider_exclusions(app, tmp_path, monkeypatch):
    inst, _ = install_test_runtime(app, tmp_path)
    monkeypatch.setattr(mgmt, "_SYSTEM_HOOKS", [("incompatible.so", lambda _inst: True, "system-hooks")])
    monkeypatch.setattr(mgmt, "_addon_contributions", lambda *_args: [
        "/addon/incompatible.so:/addon/ok.so", "/addon/other.so",
    ])
    with app.app_context():
        instance = db.session.get(type(inst), inst.id)
        assert mgmt._build_ld_preload_paths(instance) == "/addon/ok.so:/addon/other.so"


def test_missing_provider_blocks_start_but_allows_stop_and_status(app, client, tmp_path, monkeypatch):
    from ui.routes import instance_routes

    inst, _ = install_test_runtime(app, tmp_path)
    monkeypatch.setattr(instance_routes, "acquire_lock", lambda *_a, **_kw: True)
    monkeypatch.setattr(instance_routes, "enqueue_task", lambda *_a, **_kw: SimpleNamespace(id="q"))
    with app.app_context():
        headers = {"Authorization": f"Bearer {create_access_token(identity='testuser')}"}
        provider = app.extensions["addons"].pop(PROVIDER)
    start = client.post(f"/api/instances/{inst.id}/start", headers=headers)
    assert start.status_code == 409
    assert "provider" in start.get_json()["error"]["message"]
    assert client.get(f"/api/instances/{inst.id}", headers=headers).status_code == 200
    assert client.post(f"/api/instances/{inst.id}/stop", headers=headers).status_code == 202
    assert provider.id == PROVIDER


def test_corrupt_retained_bundle_blocks_changes_but_preserves_inspection(app, client, tmp_path, monkeypatch):
    from ui.custom_runtime import pinned_release

    inst, digest = install_test_runtime(app, tmp_path)
    with app.app_context():
        headers = {"Authorization": f"Bearer {create_access_token(identity='testuser')}"}
        bundle = pinned_release(PROVIDER, digest).bundle_path
    monkeypatch.setattr("ui.routes.instance_routes.acquire_lock", lambda *_a, **_kw: False)
    value = bundle.read_bytes()
    bundle.write_bytes(bytes((value[0] ^ 1,)) + value[1:])
    response = client.post(f"/api/instances/{inst.id}/restart", headers=headers)
    assert response.status_code == 409
    assert "digest" in response.get_json()["error"]["message"]
    observed = client.get(f"/api/instances/{inst.id}", headers=headers)
    assert observed.status_code == 200
    assert observed.get_json()["data"]["host_runtime_log_filename"] == "engine.log"
