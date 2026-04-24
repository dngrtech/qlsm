import json
import os

from ui import db
from ui.models import ConfigPreset
from ui.preset_support import builtin_preset_path


def write_manifest(name, description='Built-in preset', builtin=True):
    preset_dir = builtin_preset_path(name)
    os.makedirs(preset_dir, exist_ok=True)
    with open(os.path.join(preset_dir, 'preset.json'), 'w', encoding='utf-8') as handle:
        json.dump({'description': description, 'builtin': builtin}, handle)


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
