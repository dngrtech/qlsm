import json
import os
import re

import click
from flask.cli import with_appcontext

from ui import db
from ui.models import BinaryMetadata, ConfigPreset
from ui.preset_support import (
    BUILTIN_PRESETS_DIR,
    builtin_preset_path,
    is_internal_preset_name,
    validate_preset_name_format,
)


_DESCRIPTION_MAX_LEN = 100
_DESCRIPTION_RE = re.compile(r'^[^<>{}"]*$')


class BuiltinPresetError(ValueError):
    pass


def _validate_binary_descriptions(binary_descriptions, preset_dir, manifest_path):
    """Validate binary_descriptions dict from preset.json. Returns the dict on success."""
    if not isinstance(binary_descriptions, dict):
        raise BuiltinPresetError(
            f"{manifest_path}: binary_descriptions must be an object."
        )
    for key, value in binary_descriptions.items():
        if not isinstance(key, str) or not key.endswith('.so'):
            raise BuiltinPresetError(
                f"{manifest_path}: binary_descriptions key {key!r} must be a string ending in .so"
            )
        if key.startswith('/') or '..' in key:
            raise BuiltinPresetError(
                f"{manifest_path}: binary_descriptions key {key!r} must be a relative path with no '..'."
            )
        if not isinstance(value, str):
            raise BuiltinPresetError(
                f"{manifest_path}: binary_descriptions[{key!r}] must be a string."
            )
        if len(value) > _DESCRIPTION_MAX_LEN:
            raise BuiltinPresetError(
                f"{manifest_path}: binary_descriptions[{key!r}] exceeds {_DESCRIPTION_MAX_LEN} characters."
            )
        if not _DESCRIPTION_RE.match(value):
            raise BuiltinPresetError(
                f"{manifest_path}: binary_descriptions[{key!r}] contains invalid characters."
            )
        full_path = os.path.join(preset_dir, key)
        if not os.path.isfile(full_path):
            raise BuiltinPresetError(
                f"{manifest_path}: binary_descriptions key {key!r} does not exist at {full_path}."
            )
    return binary_descriptions


def _load_manifest(preset_dir):
    manifest_path = os.path.join(preset_dir, 'preset.json')
    with open(manifest_path, 'r', encoding='utf-8') as handle:
        manifest = json.load(handle)

    description = manifest.get('description')
    if not isinstance(description, str) or not description.strip():
        raise BuiltinPresetError(f"{manifest_path}: description must be a non-empty string.")
    if manifest.get('builtin') is not True:
        raise BuiltinPresetError(f"{manifest_path}: builtin must be true.")

    binary_descriptions = manifest.get('binary_descriptions', {})
    validated = _validate_binary_descriptions(binary_descriptions, preset_dir, manifest_path)

    return {'description': description.strip(), 'binary_descriptions': validated}


def _iter_builtin_dirs():
    if not os.path.isdir(BUILTIN_PRESETS_DIR):
        return
    for name in sorted(os.listdir(BUILTIN_PRESETS_DIR)):
        preset_dir = os.path.join(BUILTIN_PRESETS_DIR, name)
        if os.path.isdir(preset_dir):
            yield name, preset_dir


def _sync_binary_metadata(preset_name, desired):
    """Upsert BinaryMetadata rows for a builtin preset and delete stale ones."""
    existing_rows = BinaryMetadata.query.filter_by(
        context_type='preset',
        context_key=preset_name,
    ).all()

    existing_by_path = {row.file_path: row for row in existing_rows}

    for file_path, description in desired.items():
        if file_path in existing_by_path:
            existing_by_path[file_path].description = description
        else:
            db.session.add(BinaryMetadata(
                context_type='preset',
                context_key=preset_name,
                file_path=file_path,
                description=description,
            ))

    for file_path, row in existing_by_path.items():
        if file_path not in desired:
            db.session.delete(row)


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
        if is_internal_preset_name(name):
            raise BuiltinPresetError(
                f"Invalid built-in preset name '{name}': name is reserved for internal preset storage."
            )

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

        _sync_binary_metadata(name, manifest['binary_descriptions'])

    for row in ConfigPreset.query.filter_by(is_builtin=True).all():
        if row.name in seen_names:
            continue
        if os.path.isdir(row.path):
            continue
        if remove_orphaned:
            BinaryMetadata.query.filter_by(
                context_type='preset',
                context_key=row.name,
            ).delete()
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
