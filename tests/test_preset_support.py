import os

from ui import db
from ui.models import ConfigPreset
from ui.preset_support import (
    builtin_preset_path,
    resolve_preset_path,
    resolve_preset_subdir,
    user_preset_path,
    validate_preset_name_format,
    validate_user_preset_name,
)


def test_builtin_and_user_preset_paths_are_separate():
    assert user_preset_path('duel') == os.path.join('configs', 'presets', 'duel')
    assert builtin_preset_path('duel') == os.path.join(
        'configs', 'presets', '_builtin', 'duel'
    )


def test_validate_preset_name_format_rejects_bad_names():
    assert validate_preset_name_format('bad name!')[0] is False
    assert validate_preset_name_format('duel-2026')[0] is True


def test_validate_user_preset_name_rejects_builtin_collision(app_context):
    preset = ConfigPreset(
        name='duel',
        description='Duel',
        path=builtin_preset_path('duel'),
        is_builtin=True,
    )
    db.session.add(preset)
    db.session.commit()

    ok, error, reason = validate_user_preset_name('duel')

    assert ok is False
    assert reason == 'builtin'
    assert 'reserved by a built-in preset' in error


def test_resolve_preset_path_uses_database_path_for_builtin(app_context):
    preset = ConfigPreset(
        name='default',
        description='Default',
        path=builtin_preset_path('default'),
        is_builtin=True,
    )
    db.session.add(preset)
    db.session.commit()

    assert resolve_preset_path('default') == builtin_preset_path('default')
    assert resolve_preset_subdir('default', 'scripts') == os.path.join(
        builtin_preset_path('default'), 'scripts'
    )
