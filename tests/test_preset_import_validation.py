import io
import json
import stat
import zipfile

import pytest

from ui.routes.preset_import_validation import (
    MAX_IMPORT_ENTRIES,
    PresetImportError,
    parse_import_archive,
)

BASE_CONFIGS = {
    'server.cfg': 'set sv_hostname "Imported"\n',
    'mappool.txt': 'campgrounds\n',
    'access.txt': '\n',
    'workshop.txt': '\n',
}


def make_manifest(name='imported', description='Imported preset', **overrides):
    manifest = {
        'type': 'qlsm-preset-export',
        'format_version': 1,
        'preset': {
            'id': 1, 'name': name, 'description': description,
            'is_builtin': False, 'created_at': None, 'last_updated': None,
        },
        'includes': {}, 'counts': {'binary_metadata': 0},
    }
    manifest.update(overrides)
    return manifest


def build_zip(extra=None, manifest=..., base_configs=True):
    """Build an export-shaped zip. manifest=None omits it; Ellipsis = default."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        if manifest is ...:
            manifest = make_manifest()
        if manifest is not None:
            archive.writestr('manifest.json', json.dumps(manifest))
        if base_configs:
            for path, content in BASE_CONFIGS.items():
                archive.writestr(path, content)
        for path, content in (extra or {}).items():
            archive.writestr(path, content)
    return buffer.getvalue()


def test_parses_full_valid_archive():
    raw = build_zip(extra={
        'motd.cfg': 'welcome\n',
        'notes/readme.txt': 'note\n',
        'factories/ca.factories': '{"id": "ca"}\n',
        'scripts/discord_extensions/balance.py': 'class balance: pass\n',
        'scripts/requirements.txt': 'redis==5.0.0\n',
        'user-hooks/custom_hook.so': b'\x7fELFfake',
        'checked_plugins.json': json.dumps(['balance.py']),
        'checked_factories.json': json.dumps(['ca.factories']),
        'binary_metadata.json': json.dumps({'format_version': 1, 'metadata': [
            {'file_path': 'custom_hook.so', 'description': '99k hook'},
            {'file_path': 'stale.so', 'description': 'dropped'},
        ]}),
    })
    bundle = parse_import_archive(raw)
    assert bundle['manifest']['preset']['name'] == 'imported'
    assert set(BASE_CONFIGS) <= set(bundle['configs'])
    assert bundle['configs']['notes/readme.txt'] == 'note\n'
    assert bundle['factories'] == {'ca.factories': '{"id": "ca"}\n'}
    assert bundle['scripts'] == {
        'discord_extensions/balance.py': 'class balance: pass\n',
        'requirements.txt': 'redis==5.0.0\n',
    }
    assert bundle['user_hooks'] == {'custom_hook.so': b'\x7fELFfake'}
    assert bundle['checked_plugins'] == ['balance.py']
    assert bundle['checked_factories'] == ['ca.factories']
    assert bundle['binary_metadata'] == [
        {'file_path': 'custom_hook.so', 'description': '99k hook'},
    ]


def test_skips_known_junk_files():
    raw = build_zip(extra={'.DS_Store': b'junk', 'scripts/temp.tmp': 'junk'})
    bundle = parse_import_archive(raw)
    assert '.DS_Store' not in bundle['configs']
    assert 'temp.tmp' not in bundle['scripts']


def test_rejects_non_zip_bytes():
    with pytest.raises(PresetImportError, match='not a valid ZIP'):
        parse_import_archive(b'this is not a zip file')


def test_rejects_missing_manifest():
    raw = build_zip(manifest=None)
    with pytest.raises(PresetImportError, match='manifest.json'):
        parse_import_archive(raw)


def test_rejects_wrong_manifest_type():
    raw = build_zip(manifest=make_manifest(type='something-else'))
    with pytest.raises(PresetImportError, match='not a QLSM preset export'):
        parse_import_archive(raw)


def test_rejects_newer_format_version():
    raw = build_zip(manifest=make_manifest(format_version=2))
    with pytest.raises(PresetImportError, match='format version'):
        parse_import_archive(raw)


def test_rejects_missing_required_configs():
    raw = build_zip(base_configs=False, extra={'server.cfg': 'x\n'})
    with pytest.raises(PresetImportError, match='missing required config files'):
        parse_import_archive(raw)


def test_rejects_path_traversal_entry():
    raw = build_zip(extra={'../evil.cfg': 'x\n'})
    with pytest.raises(PresetImportError, match='Unsafe path'):
        parse_import_archive(raw)


def test_rejects_unsupported_file_type():
    raw = build_zip(extra={'malware.exe': b'MZ'})
    with pytest.raises(PresetImportError, match='Unsupported file'):
        parse_import_archive(raw)


def test_rejects_non_elf_user_hook():
    raw = build_zip(extra={'user-hooks/fake.so': b'not-an-elf'})
    with pytest.raises(PresetImportError, match='not a valid ELF'):
        parse_import_archive(raw)


def test_rejects_nested_user_hook_path():
    raw = build_zip(extra={'user-hooks/sub/dir.so': b'\x7fELF'})
    with pytest.raises(PresetImportError, match='Invalid user hook'):
        parse_import_archive(raw)


def test_rejects_symlink_entry():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(make_manifest()))
        for path, content in BASE_CONFIGS.items():
            archive.writestr(path, content)
        info = zipfile.ZipInfo('user-hooks/evil.so')
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, '/etc/passwd')
    with pytest.raises(PresetImportError, match='symlink'):
        parse_import_archive(buffer.getvalue())


def test_rejects_too_many_entries():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(make_manifest()))
        for i in range(MAX_IMPORT_ENTRIES + 1):
            archive.writestr(f'f{i}.cfg', 'x')
    with pytest.raises(PresetImportError, match='too many entries'):
        parse_import_archive(buffer.getvalue())


def test_rejects_zip_bomb_ratio():
    # Must be deflated: build_zip uses the default ZIP_STORED, which would
    # give a 1:1 ratio and trip the per-entry size check instead.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(make_manifest()))
        for path, content in BASE_CONFIGS.items():
            archive.writestr(path, content)
        archive.writestr('big.cfg', b'\x00' * (5 * 1024 * 1024))
    with pytest.raises(PresetImportError, match='compression ratio'):
        parse_import_archive(buffer.getvalue())


def test_rejects_invalid_checked_factories():
    raw = build_zip(extra={'checked_factories.json': json.dumps(['notafactory.txt'])})
    with pytest.raises(PresetImportError, match='checked_factories'):
        parse_import_archive(raw)
