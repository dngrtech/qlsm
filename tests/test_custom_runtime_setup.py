import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_custom_runtime_release import PROVIDER, activate, runtime_package
from ui.addons.install import install_addon_zip
from ui.task_logic.standalone_host_setup import _setup_playbook_extra_vars


def test_custom_setup_uses_pinned_digest_after_new_release_is_approved(app, tmp_path):
    packages = tmp_path / "packages"
    original, digest = runtime_package()
    install_addon_zip(original, packages)
    install_addon_zip(runtime_package("2.0")[0], packages)
    activate(app, packages)
    host = SimpleNamespace(runtime="custom", runtime_provider_id=PROVIDER, runtime_plugin_api="minqlx",
                           runtime_release_sha256=digest, ssh_port=22, provider="standalone", timezone=None)
    with app.app_context():
        extra = _setup_playbook_extra_vars(host)
    assert extra["custom_release_digest"] == digest
    assert Path(extra["common_plugins_operator_src"]) == Path("data/shared-plugins/minqlx").resolve()
    assert extra["skip_pip_install"] is True
    assert extra["runtime_shared_dir"] == f"/var/lib/qlsm/custom-runtime/{digest}"


def test_builtin_setup_uses_original_playbook_vars():
    host = SimpleNamespace(runtime="minqlx", ssh_port=22, provider="standalone", timezone=None)
    extra = _setup_playbook_extra_vars(host)
    assert extra["runtime"] == "minqlx"
    assert not any(key.startswith("custom_") for key in extra)
    assert "skip_pip_install" not in extra


def test_invalid_or_interrupted_install_cannot_make_release_visible(tmp_path, monkeypatch):
    from zipfile import ZipFile
    from io import BytesIO

    path = Path(__file__).resolve().parents[1] / "ansible/files/install_custom_runtime.py"
    spec = importlib.util.spec_from_file_location("install_custom_runtime", path)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    package, digest = runtime_package()
    with ZipFile(BytesIO(package)) as source:
        good = source.read("assets/runtime.tar.gz")
    bundle = tmp_path / "bundle.tar.gz"
    root = tmp_path / "published"
    bundle.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="digest"):
        installer.install(bundle, digest, root, "requirements.txt", "launch.sh", [])
    assert not (root / digest).exists()

    bundle.write_bytes(good)

    def interrupted(*_args):
        raise RuntimeError("pip failed")

    monkeypatch.setattr(installer, "_install_dependencies", interrupted)
    with pytest.raises(RuntimeError, match="pip failed"):
        installer.install(bundle, digest, root, "requirements.txt", "launch.sh", [])
    assert not (root / digest).exists()
    monkeypatch.setattr(installer, "_install_dependencies", lambda *_args: None)
    installer.install(bundle, digest, root, "requirements.txt", "launch.sh", [])
    assert (root / digest / "engine.so").read_bytes() == b"1.0"
    assert (root / digest / "launch.sh").stat().st_mode & 0o100


def test_dependency_tree_is_sealed_before_publication(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "ansible/files/install_custom_runtime.py"
    spec = importlib.util.spec_from_file_location("install_custom_runtime", path)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    deps = tmp_path / "deps"
    deps.mkdir()
    package = deps / "wheel.py"
    package.write_text("value = 1")
    package.chmod(0o666)
    ownership = []
    monkeypatch.setattr(installer.os, "chown", lambda path, uid, gid, **kwargs: ownership.append((Path(path), uid, gid)))
    installer._seal_dependencies(deps)
    assert ownership == [(deps, 0, 0), (package, 0, 0)]
    assert package.stat().st_mode & 0o777 == 0o644


def test_custom_host_installs_system_redis_for_management_probes():
    import yaml

    playbook = Path(__file__).resolve().parents[1] / "ansible/playbooks/setup_host.yml"
    [play] = yaml.safe_load(playbook.read_text())
    [task] = [task for task in play["tasks"]
              if "python3-redis" in str(task.get("ansible.builtin.apt", {}))]
    assert task["when"] == "runtime == 'custom'"


def test_custom_platform_assert_uses_os_release_version_id():
    import json

    from jinja2.nativetypes import NativeEnvironment
    import yaml

    path = Path(__file__).resolve().parents[1] / "ansible/playbooks/setup_host.yml"
    [play] = yaml.safe_load(path.read_text())
    task = next(task for task in play["tasks"] if task["name"] == "Check that this host can run the pinned Custom release")
    env = NativeEnvironment()
    env.filters.update(bool=bool, from_json=json.loads)
    expected = {"os_id": "debian", "os_version": "12", "arch": "x86_64", "python": [3, 11]}
    actual = {"os": {"ID": "debian", "VERSION_ID": "12"}, "arch": "x86_64",
              "python": [3, 11], "safe_tar_filter": True}
    values = {
        "is_standalone": True, "custom_platform": expected,
        "ansible_facts": {"distribution": "Debian", "distribution_version": "12.5"},
    }
    decode_platform = env.from_string(task["vars"]["detected_platform"])
    conditions = [env.compile_expression(assertion) for assertion in task["ansible.builtin.assert"]["that"]]

    for safe_tar_filter in (True, False):
        actual["safe_tar_filter"] = safe_tar_filter
        values["detected_platform"] = decode_platform.render(
            custom_host_platform={"stdout": json.dumps(actual)}
        )
        assert all(condition(**values) for condition in conditions) is safe_tar_filter
