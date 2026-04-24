import json
import os

import click
from flask.cli import with_appcontext

from ui import db
from ui.models import ConfigPreset
from ui.preset_support import (
    BUILTIN_PRESETS_DIR,
    builtin_preset_path,
    validate_preset_name_format,
)


class BuiltinPresetError(ValueError):
    pass


def _load_manifest(preset_dir):
    manifest_path = os.path.join(preset_dir, 'preset.json')
    with open(manifest_path, 'r', encoding='utf-8') as handle:
        manifest = json.load(handle)

    description = manifest.get('description')
    if not isinstance(description, str) or not description.strip():
        raise BuiltinPresetError(f"{manifest_path}: description must be a non-empty string.")
    if manifest.get('builtin') is not True:
        raise BuiltinPresetError(f"{manifest_path}: builtin must be true.")

    return {'description': description.strip()}


def _iter_builtin_dirs():
    if not os.path.isdir(BUILTIN_PRESETS_DIR):
        return
    for name in sorted(os.listdir(BUILTIN_PRESETS_DIR)):
        preset_dir = os.path.join(BUILTIN_PRESETS_DIR, name)
        if os.path.isdir(preset_dir):
            yield name, preset_dir


def sync_builtin_presets(remove_orphaned=False):
    seen_names = set()

    for name, preset_dir in _iter_builtin_dirs() or []:
        manifest_path = os.path.join(preset_dir, 'preset.json')
        if not os.path.exists(manifest_path):
            click.echo(f"Warning: skipping built-in preset '{name}' without preset.json.", err=True)
            continue

        is_valid, error = validate_preset_name_format(name)
        if not is_valid:
            raise BuiltinPresetError(f"Invalid built-in preset name '{name}': {error}")

        manifest = _load_manifest(preset_dir)
        expected_path = builtin_preset_path(name)
        seen_names.add(name)

        row = ConfigPreset.query.filter_by(name=name).first()
        if row is None:
            db.session.add(ConfigPreset(
                name=name,
                description=manifest['description'],
                path=expected_path,
                is_builtin=True,
            ))
        elif row.is_builtin:
            row.description = manifest['description']
            row.path = expected_path
        else:
            db.session.rollback()
            raise BuiltinPresetError(
                f"Cannot install built-in preset '{name}': "
                "a user preset with that name already exists. "
                "Rename or delete it via the UI, then re-run 'flask sync-builtin-presets'."
            )

    for row in ConfigPreset.query.filter_by(is_builtin=True).all():
        if row.name in seen_names:
            continue
        if os.path.isdir(row.path):
            continue
        if remove_orphaned:
            db.session.delete(row)
            click.echo(f"Removed orphaned built-in preset row: {row.name}")
        else:
            click.echo(f"Warning: built-in preset '{row.name}' has no folder at {row.path}.", err=True)

    db.session.commit()


@click.command('sync-builtin-presets')
@click.option('--remove-orphaned', is_flag=True, help='Delete built-in DB rows whose folders are missing.')
@with_appcontext
def sync_builtin_presets_command(remove_orphaned):
    try:
        sync_builtin_presets(remove_orphaned=remove_orphaned)
    except (OSError, json.JSONDecodeError, BuiltinPresetError) as exc:
        db.session.rollback()
        raise click.ClickException(str(exc)) from exc
    click.echo('Built-in presets synced.')
