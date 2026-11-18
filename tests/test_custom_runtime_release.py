import gzip
import hashlib
import io
import json
import tarfile
import zipfile

import pytest

from ui.addons.install import AddonInstallError, install_addon_zip


PROVIDER = "fixture-runtime"


def runtime_package(version="1.0", *, metadata=None, wrong_digest=False, extra_members=()):
    files = {
        "engine.so": version.encode(),
        "engine.zip": b"python package",
        "launch.sh": b"#!/bin/sh\n",
        "requirements.txt": b"redis>=5.1\n",
        "plugins/example.py": b"class example: pass\n",
    }
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, value in [*files.items(), *extra_members]:
            member = tarfile.TarInfo(name)
            member.size = len(value)
            tar.addfile(member, io.BytesIO(value))
    bundle = gzip.compress(raw.getvalue(), mtime=0)
    digest = hashlib.sha256(bundle).hexdigest()
    release = {
        "plugin_api": "minqlx",
        "source_commit": "a" * 40,
        "platform": {"os_id": "ubuntu", "os_version": "24.04", "arch": "x86_64", "python": [3, 12]},
        "bundle_path": "assets/runtime.tar.gz",
        "sha256": "0" * 64 if wrong_digest else digest,
        "engine_so": "engine.so",
        "python_runtime_files": ["engine.zip"],
        "launch_script": "launch.sh",
        "log_filename": "engine.log",
        "requirements_file": "requirements.txt",
        "required_plugins": ["example"],
        "excluded_preloads": ["incompatible.so"],
    }
    release.update(metadata or {})
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as archive:
        archive.writestr("qlsm-addon.json", json.dumps({
            "id": PROVIDER, "name": "Fixture runtime", "version": version, "custom_runtime": release,
        }))
        archive.writestr("assets/runtime.tar.gz", bundle)
    return blob.getvalue(), digest


def activate(addon_app, packages):
    from ui.addons.registry import init_app, get_addon

    addon_app.config["ADDON_PACKAGES_DIR"] = str(packages)
    with addon_app.app_context():
        init_app(addon_app)
        get_addon(PROVIDER).ctx.settings.set_enabled("global", 0)


def test_replacing_addon_retains_old_release(app, tmp_path):
    from ui.custom_runtime import approved_release, pinned_release

    packages = tmp_path / "packages"
    first, old_digest = runtime_package()
    second, new_digest = runtime_package("2.0")
    install_addon_zip(first, packages)
    install_addon_zip(second, packages)
    activate(app, packages)
    with app.app_context():
        assert approved_release(PROVIDER).sha256 == new_digest
        old = pinned_release(PROVIDER, old_digest)
        assert old.sha256 == old_digest
        assert hashlib.sha256(old.bundle_path.read_bytes()).hexdigest() == old_digest


def test_invalid_runtime_bundle_keeps_previous_package(tmp_path):
    packages = tmp_path / "packages"
    first, old_digest = runtime_package()
    install_addon_zip(first, packages)
    invalid, _ = runtime_package("2.0", wrong_digest=True)
    with pytest.raises(AddonInstallError, match="digest"):
        install_addon_zip(invalid, packages)
    conflicting, _ = runtime_package(metadata={"plugin_api": "minqlxtended"})
    with pytest.raises(AddonInstallError, match="metadata"):
        install_addon_zip(conflicting, packages)
    manifest = json.loads((packages / PROVIDER / "qlsm-addon.json").read_text())
    assert manifest["custom_runtime"]["sha256"] == old_digest


@pytest.mark.parametrize("name", ["../escape", "/absolute", "engine.so"])
def test_invalid_runtime_members_are_rejected(tmp_path, name):
    invalid, _ = runtime_package(extra_members=[(name, b"bad")])
    with pytest.raises(AddonInstallError, match="bundle member"):
        install_addon_zip(invalid, tmp_path / "packages")


def test_provider_visibility_follows_addon_activation(app, tmp_path):
    from ui.addons.registry import get_addon, init_app
    from ui.custom_runtime import RuntimeUnavailable, approved_release

    packages = tmp_path / "packages"
    install_addon_zip(runtime_package()[0], packages)
    app.config["ADDON_PACKAGES_DIR"] = str(packages)
    with app.app_context():
        init_app(app)
        with pytest.raises(RuntimeUnavailable, match="disabled"):
            approved_release(PROVIDER)
        get_addon(PROVIDER).ctx.settings.set_enabled("global", 0)
        assert approved_release(PROVIDER).provider_id == PROVIDER
        (packages / PROVIDER / "qlsm-addon.json").write_text("{")
        init_app(app)
        with pytest.raises(RuntimeUnavailable, match="broken"):
            approved_release(PROVIDER)


def test_retained_release_is_part_of_addon_backups(tmp_path, monkeypatch):
    from ui.task_logic import backup_files

    packages = tmp_path / "packages"
    package, digest = runtime_package()
    install_addon_zip(package, packages)
    monkeypatch.setattr(backup_files, "ADDON_PACKAGES_DIR", str(packages))
    tree = next(tree for tree in backup_files.backup_file_trees() if tree[0] == "addon-packages")
    _, root, skip = tree
    backed_up = {path for path, _ in backup_files.walk_tree(root, skip)}
    assert f".runtime-releases/{PROVIDER}/{digest}/bundle.tar.gz" in backed_up
    assert f".runtime-releases/{PROVIDER}/{digest}/release.json" in backed_up
