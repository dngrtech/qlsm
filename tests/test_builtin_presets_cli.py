import json
import os

from ui import db
from ui.models import BinaryMetadata, ConfigPreset
from ui.preset_support import builtin_preset_path


def write_manifest(name, description='Built-in preset', builtin=True, binary_descriptions=None):
    preset_dir = builtin_preset_path(name)
    os.makedirs(preset_dir, exist_ok=True)
    manifest = {'description': description, 'builtin': builtin}
    if binary_descriptions is not None:
        manifest['binary_descriptions'] = binary_descriptions
    with open(os.path.join(preset_dir, 'preset.json'), 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle)


def write_so_file(preset_name, relative_path):
    preset_dir = builtin_preset_path(preset_name)
    full_path = os.path.join(preset_dir, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'wb') as fh:
        fh.write(b'\x7fELF')


def test_sync_builtin_presets_inserts_valid_manifest(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('clan-arena', 'Clan Arena')

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code == 0
    with app.app_context():
        preset = ConfigPreset.query.filter_by(name='clan-arena').first()
        assert preset is not None
        assert preset.description == 'Clan Arena'
        assert preset.path == builtin_preset_path('clan-arena')
        assert preset.is_builtin is True


def test_sync_builtin_presets_updates_builtin_idempotently(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Old description')
    assert runner.invoke(args=['sync-builtin-presets']).exit_code == 0

    write_manifest('duel', 'New description')
    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code == 0
    with app.app_context():
        presets = ConfigPreset.query.filter_by(name='duel').all()
        assert len(presets) == 1
        assert presets[0].description == 'New description'


def test_sync_builtin_presets_rejects_user_collision(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('ctf-classic', 'CTF Classic')
    with app.app_context():
        db.session.add(ConfigPreset(
            name='ctf-classic',
            description='User CTF',
            path='configs/presets/ctf-classic',
            is_builtin=False,
        ))
        db.session.commit()

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code != 0
    assert "a user preset with that name already exists" in result.output
    with app.app_context():
        preset = ConfigPreset.query.filter_by(name='ctf-classic').one()
        assert preset.is_builtin is False
        assert preset.path == 'configs/presets/ctf-classic'


def test_sync_builtin_presets_rejects_invalid_manifest(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('bad', '', True)

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code != 0
    assert 'description must be a non-empty string' in result.output


def test_sync_builtin_presets_rejects_internal_namespace_name(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('_builtin', 'Bad internal name')

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code != 0
    assert 'reserved for internal preset storage' in result.output


def test_sync_builtin_presets_remove_orphaned_deletes_missing_builtin_row(
    runner, app, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        db.session.add(ConfigPreset(
            name='old-builtin',
            description='Old',
            path=builtin_preset_path('old-builtin'),
            is_builtin=True,
        ))
        db.session.commit()

    keep_result = runner.invoke(args=['sync-builtin-presets'])
    assert keep_result.exit_code == 0
    with app.app_context():
        assert ConfigPreset.query.filter_by(name='old-builtin').first() is not None

    remove_result = runner.invoke(args=['sync-builtin-presets', '--remove-orphaned'])
    assert remove_result.exit_code == 0
    with app.app_context():
        assert ConfigPreset.query.filter_by(name='old-builtin').first() is None


def test_add_preset_rejects_builtin_name(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        db.session.add(ConfigPreset(
            name='duel',
            description='Duel',
            path=builtin_preset_path('duel'),
            is_builtin=True,
        ))
        db.session.commit()

    result = runner.invoke(args=['add-preset', '--name', 'duel'])

    assert result.exit_code == 0
    assert 'reserved by a built-in preset' in result.output


def test_add_preset_rejects_internal_namespace(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(args=['add-preset', '--name', '_builtin'])

    assert result.exit_code == 0
    assert 'reserved for internal preset storage' in result.output
    assert not os.path.exists(os.path.join('configs', 'presets', '_builtin'))


def test_delete_preset_rejects_builtin(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        db.session.add(ConfigPreset(
            name='default',
            description='Default',
            path=builtin_preset_path('default'),
            is_builtin=True,
        ))
        db.session.commit()

    result = runner.invoke(args=['delete-preset', '--name', 'default'])

    assert result.exit_code == 0
    assert "Cannot delete built-in preset 'default'" in result.output


def test_delete_preset_rejects_internal_namespace(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    marker = os.path.join('configs', 'presets', '_builtin', 'default', 'server.cfg')
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, 'w') as handle:
        handle.write('set sv_hostname "default"\n')
    with app.app_context():
        db.session.add(ConfigPreset(
            name='_builtin',
            description='Internal namespace row',
            path=os.path.join('configs', 'presets', '_builtin'),
            is_builtin=False,
        ))
        db.session.commit()

    result = runner.invoke(args=['delete-preset', '--name', '_builtin'])

    assert result.exit_code == 0
    assert "Cannot delete internal preset namespace '_builtin'" in result.output
    assert os.path.exists(marker)


def test_sync_rejects_binary_description_too_long(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions={'scripts/hook.so': 'x' * 101})
    write_so_file('duel', 'scripts/hook.so')

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code != 0
    assert 'binary_descriptions' in result.output


def test_sync_rejects_binary_description_bad_chars(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions={'scripts/hook.so': '<script>'})
    write_so_file('duel', 'scripts/hook.so')

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code != 0
    assert 'binary_descriptions' in result.output


def test_sync_rejects_binary_descriptions_non_so_key(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions={'scripts/hook.py': 'A description'})

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code != 0
    assert 'binary_descriptions' in result.output


def test_sync_rejects_binary_descriptions_path_traversal(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions={'../hook.so': 'A description'})

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code != 0
    assert 'binary_descriptions' in result.output


def test_sync_rejects_binary_descriptions_missing_file(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions={'scripts/missing.so': 'A description'})
    # intentionally do NOT create the .so file

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code != 0
    assert 'binary_descriptions' in result.output


def test_sync_rejects_binary_descriptions_not_dict(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions=['hook.so'])

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code != 0
    assert 'binary_descriptions' in result.output


def test_sync_seeds_binary_metadata_row(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions={'scripts/hook.so': 'My hook'})
    write_so_file('duel', 'scripts/hook.so')

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code == 0
    with app.app_context():
        row = BinaryMetadata.query.filter_by(
            context_type='preset',
            context_key='duel',
            file_path='scripts/hook.so',
        ).first()
        assert row is not None
        assert row.description == 'My hook'


def test_sync_overwrites_binary_metadata_on_resync(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions={'scripts/hook.so': 'Old desc'})
    write_so_file('duel', 'scripts/hook.so')
    assert runner.invoke(args=['sync-builtin-presets']).exit_code == 0

    write_manifest('duel', 'Duel', binary_descriptions={'scripts/hook.so': 'New desc'})
    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code == 0
    with app.app_context():
        row = BinaryMetadata.query.filter_by(
            context_type='preset',
            context_key='duel',
            file_path='scripts/hook.so',
        ).one()
        assert row.description == 'New desc'


def test_sync_deletes_stale_binary_metadata_row(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions={'scripts/hook.so': 'My hook'})
    write_so_file('duel', 'scripts/hook.so')
    assert runner.invoke(args=['sync-builtin-presets']).exit_code == 0

    write_manifest('duel', 'Duel')
    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code == 0
    with app.app_context():
        row = BinaryMetadata.query.filter_by(
            context_type='preset',
            context_key='duel',
            file_path='scripts/hook.so',
        ).first()
        assert row is None


def test_sync_no_binary_metadata_when_field_absent(runner, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel')

    result = runner.invoke(args=['sync-builtin-presets'])

    assert result.exit_code == 0
    with app.app_context():
        rows = BinaryMetadata.query.filter_by(
            context_type='preset',
            context_key='duel',
        ).all()
        assert rows == []


def test_remove_orphaned_deletes_binary_metadata(runner, app, tmp_path, monkeypatch):
    import shutil
    monkeypatch.chdir(tmp_path)
    write_manifest('duel', 'Duel', binary_descriptions={'scripts/hook.so': 'My hook'})
    write_so_file('duel', 'scripts/hook.so')
    assert runner.invoke(args=['sync-builtin-presets']).exit_code == 0

    shutil.rmtree(builtin_preset_path('duel'))

    result = runner.invoke(args=['sync-builtin-presets', '--remove-orphaned'])

    assert result.exit_code == 0
    with app.app_context():
        rows = BinaryMetadata.query.filter_by(
            context_type='preset',
            context_key='duel',
        ).all()
        assert rows == []
