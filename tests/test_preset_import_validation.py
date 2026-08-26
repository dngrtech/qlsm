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
        'scripts/highfps_hook.so': b'\x7fELFfake',
        'user-hooks/custom_hook.so': b'\x7fELFfake',
        'checked_plugins.json': json.dumps(['balance.py']),
        'checked_factories.json': json.dumps(['ca.factories']),
        'enabled_hooks.json': json.dumps(['custom_hook.so']),
        'lan_rate_enabled.json': json.dumps(True),
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
        'highfps_hook.so': b'\x7fELFfake',
    }
    assert bundle['user_hooks'] == {'custom_hook.so': b'\x7fELFfake'}
    assert bundle['checked_plugins'] == ['balance.py']
    assert bundle['checked_factories'] == ['ca.factories']
    assert bundle['enabled_hooks'] == ['custom_hook.so']
    assert bundle['lan_rate_enabled'] is True
    assert bundle['binary_metadata'] == [
        {'file_path': 'custom_hook.so', 'description': '99k hook'},
    ]


def test_deduplicates_binary_metadata_entries():
    raw = build_zip(extra={
        'user-hooks/custom_hook.so': b'\x7fELFfake',
        'binary_metadata.json': json.dumps({'format_version': 1, 'metadata': [
            {'file_path': 'custom_hook.so', 'description': 'first'},
            {'file_path': 'custom_hook.so', 'description': 'second'},
        ]}),
    })

    bundle = parse_import_archive(raw)

    assert bundle['binary_metadata'] == [
        {'file_path': 'custom_hook.so', 'description': 'first'},
    ]


def test_skips_known_junk_files():
    raw = build_zip(extra={
        '.DS_Store': b'junk',
        'scripts/temp.tmp': 'junk',
        'scripts/.gitkeep': '',
        'scripts/empty_dir/.gitkeep': '',
    })
    bundle = parse_import_archive(raw)
    assert '.DS_Store' not in bundle['configs']
    assert 'temp.tmp' not in bundle['scripts']
    assert '.gitkeep' not in bundle['scripts']
    assert 'empty_dir/.gitkeep' not in bundle['scripts']


def test_rejects_non_zip_bytes():
    with pytest.raises(PresetImportError, match='not a valid ZIP'):
        parse_import_archive(b'this is not a zip file')


def test_rejects_corrupt_zip_entry():
    raw = bytearray(build_zip(extra={'motd.cfg': 'SENTINEL-CONTENT\n'}))
    offset = raw.find(b'SENTINEL-CONTENT')
    assert offset != -1
    raw[offset] = ord('X')

    with pytest.raises(PresetImportError, match='could not be read'):
        parse_import_archive(bytes(raw))


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


def test_rejects_non_elf_script_binary():
    raw = build_zip(extra={'scripts/fake.so': b'not-an-elf'})
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


def test_rejects_invalid_enabled_hooks():
    raw = build_zip(extra={'enabled_hooks.json': json.dumps(['not_a_hook.py'])})
    with pytest.raises(PresetImportError, match='enabled_hooks'):
        parse_import_archive(raw)


def test_enabled_hooks_filtered_to_hooks_present_in_archive():
    raw = build_zip(extra={
        'user-hooks/custom_hook.so': b'\x7fELFfake',
        'enabled_hooks.json': json.dumps(['custom_hook.so', 'ghost_hook.so']),
    })
    bundle = parse_import_archive(raw)
    assert bundle['enabled_hooks'] == ['custom_hook.so']


def test_enabled_hooks_none_when_absent():
    raw = build_zip()
    bundle = parse_import_archive(raw)
    assert bundle['enabled_hooks'] is None


def test_rejects_invalid_lan_rate_enabled():
    raw = build_zip(extra={'lan_rate_enabled.json': json.dumps('yes')})
    with pytest.raises(PresetImportError, match='must contain a boolean'):
        parse_import_archive(raw)


def test_parses_lan_rate_enabled_false():
    raw = build_zip(extra={'lan_rate_enabled.json': json.dumps(False)})
    bundle = parse_import_archive(raw)
    assert bundle['lan_rate_enabled'] is False


def test_lan_rate_enabled_none_when_absent():
    raw = build_zip()
    bundle = parse_import_archive(raw)
    assert bundle['lan_rate_enabled'] is None


TTF_CONTENT = b'\x00\x01\x00\x00' + b'\x00' * 20


def test_parses_font_file_in_scripts():
    raw = build_zip(extra={'scripts/stats.ttf': TTF_CONTENT})
    bundle = parse_import_archive(raw)
    assert bundle['scripts']['stats.ttf'] == TTF_CONTENT


def test_rejects_invalid_signature_font_in_scripts():
    raw = build_zip(extra={'scripts/fake.ttf': b'not a font'})
    with pytest.raises(PresetImportError, match='signature'):
        parse_import_archive(raw)


def test_accepts_pfa_without_signature_check():
    raw = build_zip(extra={'scripts/legacy.pfa': b'%!PS-AdobeFont-1.0\n'})
    bundle = parse_import_archive(raw)
    assert bundle['scripts']['legacy.pfa'] == b'%!PS-AdobeFont-1.0\n'


def test_rejects_oversized_font_in_scripts():
    oversized = TTF_CONTENT + b'\x00' * (25 * 1024 * 1024 + 1 - len(TTF_CONTENT))
    raw = build_zip(extra={'scripts/huge.ttf': oversized})
    with pytest.raises(PresetImportError, match='25MB'):
        parse_import_archive(raw)


def test_unwraps_single_top_level_export_folder():
    # Extracting an export and re-zipping the folder (a common file-manager
    # "Compress" action) nests everything under e.g. ffv5/manifest.json.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('ffv5/manifest.json', json.dumps(make_manifest(name='ffv5')))
        for path, content in BASE_CONFIGS.items():
            archive.writestr(f'ffv5/{path}', content)
        archive.writestr('ffv5/factories/ca.factories', '{"id": "ca"}\n')
        archive.writestr('ffv5/user-hooks/custom_hook.so', b'\x7fELFfake')
        archive.writestr(
            'ffv5/binary_metadata.json',
            json.dumps({'format_version': 1, 'metadata': [
                {'file_path': 'custom_hook.so', 'description': '99k hook'},
            ]}),
        )

    bundle = parse_import_archive(buffer.getvalue())

    assert bundle['manifest']['preset']['name'] == 'ffv5'
    assert set(BASE_CONFIGS) <= set(bundle['configs'])
    assert bundle['factories'] == {'ca.factories': '{"id": "ca"}\n'}
    # Confirms binary_metadata.json under the wrapper folder was actually
    # parsed, not silently dropped (both cases would otherwise read as []).
    assert bundle['binary_metadata'] == [
        {'file_path': 'custom_hook.so', 'description': '99k hook'},
    ]


def test_does_not_unwrap_when_manifest_already_at_root():
    raw = build_zip(extra={'notes/readme.txt': 'note\n'})
    bundle = parse_import_archive(raw)
    assert bundle['configs']['notes/readme.txt'] == 'note\n'


def test_skips_backup_files_left_beside_scripts():
    """A stray editor/tooling backup must not fail the whole import."""
    raw = build_zip(extra={
        'scripts/ranked.py': 'class ranked: pass\n',
        'scripts/ranked.py.bak-pre-player-ip-connected-20260704-222233': 'old\n',
        'scripts/ranked.py.bak': 'older\n',
        'scripts/ranked.py.bak.1': 'oldest\n',
        'scripts/ranked.py.orig': 'pre-merge\n',
        'scripts/ranked.py.rej': 'rejected hunk\n',
        'server.cfg.bak': 'set sv_hostname "Old"\n',
    })
    bundle = parse_import_archive(raw)
    assert set(bundle['scripts']) == {'ranked.py'}
    assert 'server.cfg.bak' not in bundle['configs']


def test_keeps_scripts_whose_name_merely_contains_bak():
    """The backup filter must not swallow legitimately named files."""
    raw = build_zip(extra={
        'scripts/bakery.py': 'class bakery: pass\n',
        'notes/bakery.txt': 'not a backup\n',
    })
    bundle = parse_import_archive(raw)
    assert 'bakery.py' in bundle['scripts']
    assert 'notes/bakery.txt' in bundle['configs']
