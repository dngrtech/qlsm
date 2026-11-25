"""Installing an addon package from a .zip.

The interesting half is what gets *rejected*. An addon is trusted code once
installed (addons/TRUST.md), but the install path itself must not be
exploitable by a malformed archive from anyone who can reach the upload
endpoint.
"""
import io
import json
import os
import zipfile

import pytest

from ui.addons.install import (
    AddonInstallError, install_addon_zip, scan_installed_ids, uninstall_addon,
)

MANIFEST = {'id': 'uploaded-addon', 'version': '1.0.0', 'name': 'Uploaded'}


def build_zip(files, *, symlinks=(), compress=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compress) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        for name, target in symlinks:
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o120777 << 16)  # S_IFLNK | 0777
            zf.writestr(info, target)
    return buf.getvalue()


def good_zip(manifest=None, extra=None, prefix=''):
    files = {f'{prefix}qlsm-addon.json': json.dumps(manifest or MANIFEST)}
    files.update({f'{prefix}{k}': v for k, v in (extra or {}).items()})
    return build_zip(files)


@pytest.fixture
def packages(tmp_path):
    d = tmp_path / 'addon-packages'
    d.mkdir()
    return str(d)


# ---- the happy path ----------------------------------------------------

def test_installs_a_flat_archive(packages):
    manifest = install_addon_zip(good_zip(extra={'backend.py': 'def register(ctx): pass\n'}), packages)
    assert manifest['id'] == 'uploaded-addon'
    assert os.path.isfile(os.path.join(packages, 'uploaded-addon', 'qlsm-addon.json'))
    assert os.path.isfile(os.path.join(packages, 'uploaded-addon', 'backend.py'))


def test_installs_an_archive_nested_in_one_folder(packages):
    """What "Compress this folder" produces on both macOS and Windows."""
    install_addon_zip(good_zip(prefix='uploaded-addon/', extra={'ui/panel.js': 'x'}), packages)
    assert os.path.isfile(os.path.join(packages, 'uploaded-addon', 'qlsm-addon.json'))
    assert os.path.isfile(os.path.join(packages, 'uploaded-addon', 'ui', 'panel.js'))


def test_directory_is_named_after_the_manifest_id_not_the_folder(packages):
    """The id decides where it lands, so two archives of the same addon
    cannot install side by side under different folder names."""
    install_addon_zip(good_zip(prefix='some-random-folder-name/'), packages)
    assert os.path.isdir(os.path.join(packages, 'uploaded-addon'))
    assert not os.path.isdir(os.path.join(packages, 'some-random-folder-name'))


def test_reinstall_replaces_the_previous_copy(packages, app_context):
    install_addon_zip(good_zip(extra={'old.txt': 'old'}), packages)
    install_addon_zip(good_zip(extra={'new.txt': 'new'}), packages)
    installed = os.path.join(packages, 'uploaded-addon')
    assert os.path.isfile(os.path.join(installed, 'new.txt'))
    assert not os.path.isfile(os.path.join(installed, 'old.txt'))


def test_no_staging_leftovers(packages):
    install_addon_zip(good_zip(), packages)
    assert os.listdir(packages) == ['uploaded-addon']


# ---- malformed archives ------------------------------------------------

def test_rejects_a_non_zip(packages):
    with pytest.raises(AddonInstallError, match='not a valid .zip'):
        install_addon_zip(b'this is not a zip', packages)


def test_rejects_an_empty_upload(packages):
    with pytest.raises(AddonInstallError):
        install_addon_zip(b'', packages)


def test_rejects_an_archive_with_no_manifest(packages):
    with pytest.raises(AddonInstallError, match='no qlsm-addon.json'):
        install_addon_zip(build_zip({'backend.py': 'x'}), packages)


def test_rejects_an_invalid_manifest(packages):
    with pytest.raises(AddonInstallError, match='Manifest is invalid'):
        install_addon_zip(good_zip(manifest={'id': 'Bad Id', 'version': '1.0'}), packages)


def test_rejects_unparseable_manifest_json(packages):
    with pytest.raises(AddonInstallError, match='not valid JSON'):
        install_addon_zip(build_zip({'qlsm-addon.json': '{nope'}), packages)


def test_rejects_a_manifest_buried_too_deep(packages):
    with pytest.raises(AddonInstallError, match='at the archive root or one folder deep'):
        install_addon_zip(good_zip(prefix='a/b/'), packages)


# ---- path traversal ("zip slip") ---------------------------------------

@pytest.mark.parametrize('evil', [
    '../escaped.txt',
    'pkg/../../escaped.txt',
    '/etc/escaped.txt',
    '..\\escaped.txt',
])
def test_rejects_paths_that_escape_the_package(packages, evil):
    """The whole archive is refused rather than the member skipped: an
    archive with a `..` member is not a package with a typo."""
    blob = build_zip({'qlsm-addon.json': json.dumps(MANIFEST), evil: 'pwned'})
    with pytest.raises(AddonInstallError):
        install_addon_zip(blob, packages)
    assert not os.path.exists(os.path.join(os.path.dirname(packages), 'escaped.txt'))


def test_rejects_symlink_members(packages):
    """A symlink is how an archive reads a file it was never given."""
    blob = build_zip({'qlsm-addon.json': json.dumps(MANIFEST)},
                     symlinks=[('link', '/etc/passwd')])
    with pytest.raises(AddonInstallError, match='symlink'):
        install_addon_zip(blob, packages)


def test_a_rejected_upload_leaves_the_previous_install_untouched(packages):
    install_addon_zip(good_zip(extra={'keep.txt': 'original'}), packages)
    blob = build_zip({'qlsm-addon.json': json.dumps(MANIFEST), '../evil.txt': 'x'})
    with pytest.raises(AddonInstallError):
        install_addon_zip(blob, packages)

    installed = os.path.join(packages, 'uploaded-addon')
    with open(os.path.join(installed, 'keep.txt'), encoding='utf-8') as f:
        assert f.read() == 'original'


# ---- resource bounds ---------------------------------------------------

def test_rejects_an_oversized_archive(packages, monkeypatch):
    import ui.addons.install as install_mod

    monkeypatch.setattr(install_mod, 'MAX_ARCHIVE_BYTES', 10)
    with pytest.raises(AddonInstallError, match='larger than the allowed size'):
        install_addon_zip(good_zip(), packages)


def test_rejects_too_many_entries(packages, monkeypatch):
    import ui.addons.install as install_mod

    monkeypatch.setattr(install_mod, 'MAX_ENTRIES', 2)
    blob = build_zip({'qlsm-addon.json': json.dumps(MANIFEST),
                      'a': '1', 'b': '2', 'c': '3'})
    with pytest.raises(AddonInstallError, match='more than 2 entries'):
        install_addon_zip(blob, packages)


def test_rejects_a_zip_bomb_by_total_size(packages, monkeypatch):
    import ui.addons.install as install_mod

    monkeypatch.setattr(install_mod, 'MAX_UNCOMPRESSED_BYTES', 1024)
    monkeypatch.setattr(install_mod, 'MAX_COMPRESSION_RATIO', 10 ** 9)
    blob = build_zip({'qlsm-addon.json': json.dumps(MANIFEST), 'big': 'A' * 10_000})
    with pytest.raises(AddonInstallError, match='expands to more than'):
        install_addon_zip(blob, packages)


def test_rejects_a_suspicious_compression_ratio(packages):
    """A single member that expands enormously, which the total-size check
    alone would still allow if the limit were generous."""
    blob = build_zip({'qlsm-addon.json': json.dumps(MANIFEST), 'big': 'A' * 5_000_000})
    with pytest.raises(AddonInstallError, match='compression ratio'):
        install_addon_zip(blob, packages)


# ---- uninstall + scan --------------------------------------------------

def test_uninstall_removes_the_directory(packages, app_context):
    install_addon_zip(good_zip(), packages)
    assert uninstall_addon('uploaded-addon', packages) is True
    assert not os.path.exists(os.path.join(packages, 'uploaded-addon'))


def test_uninstall_of_an_absent_addon_is_false_not_an_error(packages):
    assert uninstall_addon('never-installed', packages) is False


@pytest.mark.parametrize('evil_id', ['../outside', '..', 'a/../../b', '/abs'])
def test_uninstall_refuses_to_escape_the_packages_directory(packages, evil_id):
    with pytest.raises(AddonInstallError, match='Invalid addon id'):
        uninstall_addon(evil_id, packages)


def test_scan_lists_installed_ids(packages):
    assert scan_installed_ids(packages) == set()
    install_addon_zip(good_zip(), packages)
    assert scan_installed_ids(packages) == {'uploaded-addon'}


def test_scan_ignores_leftover_dot_directories(packages):
    install_addon_zip(good_zip(), packages)
    os.makedirs(os.path.join(packages, '.uploaded-addon.previous-1'), exist_ok=True)
    assert scan_installed_ids(packages) == {'uploaded-addon'}


def test_scan_ignores_a_directory_without_a_manifest(packages):
    os.makedirs(os.path.join(packages, 'just-a-folder'), exist_ok=True)
    assert scan_installed_ids(packages) == set()


def test_scan_of_a_missing_directory_is_empty(tmp_path):
    assert scan_installed_ids(str(tmp_path / 'nope')) == set()


def test_duplicate_normalized_asset_paths_are_rejected(packages):
    blob = good_zip(extra={'docs/readme.txt': 'readme', 'docs/./readme.txt': 'readme'})
    with pytest.raises(AddonInstallError, match='duplicate'):
        install_addon_zip(blob, packages)
    assert not os.listdir(packages)


def test_validates_staged_manifest_before_publishing(packages, monkeypatch):
    from ui.addons import install

    # Simulate a mismatch reported by the independent staged-manifest reader.
    read = install.read_manifest

    def changed_manifest(directory):
        manifest, errors = read(directory)
        return dict(manifest, id='another-addon'), errors

    monkeypatch.setattr(install, 'read_manifest', changed_manifest)
    with pytest.raises(AddonInstallError, match='[Mm]anifest'):
        install_addon_zip(good_zip(), packages)
    assert not os.listdir(packages)
