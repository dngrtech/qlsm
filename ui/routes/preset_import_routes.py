"""Import endpoint: turn an exported preset ZIP back into a ConfigPreset."""
import os
import shutil
import tempfile

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename

from ui import db
from ui.database import create_preset, get_preset, get_preset_by_name, update_preset
from ui.models import BinaryMetadata
from ui.preset_support import PRESETS_DIR, validate_user_preset_name
from ui.routes.preset_api_routes import (
    _read_preset_checked_factories,
    _read_preset_checked_plugins,
    _read_preset_configs,
    _read_preset_factories,
    _read_preset_scripts,
    _resolve_export_root,
    _write_preset_checked_factories,
    _write_preset_checked_plugins,
    _write_preset_configs,
    _write_preset_factories,
    _write_preset_scripts,
)
from ui.routes.preset_import_validation import (
    MAX_IMPORT_ZIP_BYTES,
    PresetImportError,
    parse_import_archive,
)

preset_import_bp = Blueprint('preset_import_routes', __name__)


def _conflict_response(conflict_type, name, preset_id=None, message=None):
    conflict = {'type': conflict_type, 'name': name}
    if preset_id is not None:
        conflict['preset_id'] = preset_id
    return jsonify({
        'error': {'message': message or f"A preset named '{name}' already exists."},
        'conflict': conflict,
    }), 409


def _resolve_import_target(bundle):
    """Return (mode, name, existing_preset, error_response)."""
    overwrite_raw = (request.form.get('overwrite_preset_id') or '').strip()
    if overwrite_raw:
        if not overwrite_raw.isdigit():
            return None, None, None, (
                jsonify({'error': {'message': 'overwrite_preset_id must be an integer.'}}), 400
            )
        existing = get_preset(int(overwrite_raw))
        if not existing:
            return None, None, None, (
                jsonify({'error': {'message': 'Preset to overwrite not found.'}}), 404
            )
        if existing.is_builtin:
            return None, None, None, (
                jsonify({'error': {'message': 'Cannot overwrite a built-in preset.'}}), 403
            )
        return 'overwrite', existing.name, existing, None

    explicit_name = (request.form.get('name') or '').strip()
    candidate = explicit_name or bundle['manifest']['preset']['name'].strip()
    is_valid, error, reason = validate_user_preset_name(candidate)
    if is_valid:
        return 'create', candidate, None, None
    if reason == 'duplicate':
        existing = get_preset_by_name(candidate)
        return None, None, None, _conflict_response(
            'duplicate', candidate, preset_id=existing.id, message=error
        )
    if reason in ('builtin', 'internal'):
        return None, None, None, _conflict_response('builtin', candidate, message=error)
    if explicit_name:
        return None, None, None, (jsonify({'error': {'message': error}}), 400)
    return None, None, None, _conflict_response('invalid', candidate, message=error)


def _write_user_hooks(preset_path, hooks):
    if not hooks:
        return
    hooks_dir = os.path.join(preset_path, 'user-hooks')
    os.makedirs(hooks_dir, exist_ok=True)
    for filename, content in hooks.items():
        with open(os.path.join(hooks_dir, filename), 'wb') as handle:
            handle.write(content)


def _write_import_bundle(preset_path, bundle):
    _write_preset_configs(preset_path, {'configs': bundle['configs']})
    if bundle['factories']:
        _write_preset_factories(preset_path, bundle['factories'])
    if bundle['scripts']:
        _write_preset_scripts(preset_path, bundle['scripts'])
    _write_user_hooks(preset_path, bundle['user_hooks'])
    if bundle['checked_plugins'] is not None:
        _write_preset_checked_plugins(preset_path, bundle['checked_plugins'])
    if bundle['checked_factories'] is not None:
        _write_preset_checked_factories(preset_path, bundle['checked_factories'])


def _replace_binary_metadata(preset_name, entries):
    BinaryMetadata.query.filter_by(
        context_type='preset', context_key=preset_name,
    ).delete()
    for entry in entries:
        db.session.add(BinaryMetadata(
            context_type='preset',
            context_key=preset_name,
            file_path=entry['file_path'],
            description=entry['description'][:1000],
        ))


def _preset_response(preset):
    data = preset.to_dict()
    data.update(_read_preset_configs(preset.path))
    data['scripts'] = _read_preset_scripts(preset.path)
    data['factories'] = _read_preset_factories(preset.path)
    data['checked_plugins'] = _read_preset_checked_plugins(preset.path)
    data['checked_factories'] = _read_preset_checked_factories(preset.path)
    return data


def _cleanup_after_failure(mode, staging_dir, target_path, old_dir, existing):
    shutil.rmtree(staging_dir, ignore_errors=True)
    if mode == 'create' and target_path and os.path.isdir(target_path):
        shutil.rmtree(target_path, ignore_errors=True)
    if mode == 'overwrite' and old_dir and os.path.isdir(old_dir):
        if target_path and os.path.isdir(target_path):
            shutil.rmtree(target_path, ignore_errors=True)
        os.rename(old_dir, existing.path)


@preset_import_bp.route('/import', methods=['POST'], endpoint='import_preset_api')
@jwt_required()
def import_preset_api():
    if 'file' not in request.files:
        return jsonify({'error': {'message': 'No file provided'}}), 400
    upload = request.files['file']
    if not upload.filename:
        return jsonify({'error': {'message': 'No file selected'}}), 400
    if not secure_filename(upload.filename).lower().endswith('.zip'):
        return jsonify({'error': {'message': 'Only .zip archives can be imported.'}}), 400

    upload.seek(0, 2)
    size = upload.tell()
    upload.seek(0)
    if size == 0:
        return jsonify({'error': {'message': 'Empty file.'}}), 400
    if size > MAX_IMPORT_ZIP_BYTES:
        limit_mb = MAX_IMPORT_ZIP_BYTES // (1024 * 1024)
        return jsonify({'error': {'message': f'Archive exceeds {limit_mb}MB.'}}), 400

    try:
        bundle = parse_import_archive(upload.read())
    except PresetImportError as e:
        return jsonify({'error': {'message': str(e)}}), 400

    mode, name, existing, error_response = _resolve_import_target(bundle)
    if error_response:
        return error_response

    description = bundle['manifest']['preset'].get('description') or ''

    os.makedirs(PRESETS_DIR, exist_ok=True)
    staging_dir = tempfile.mkdtemp(prefix='.qlsm-import-', dir=PRESETS_DIR)
    target_path = None
    old_dir = None
    try:
        _write_import_bundle(staging_dir, bundle)

        if mode == 'overwrite':
            target_path = _resolve_export_root(existing.path)
            old_dir = target_path + '.import-old'
            if os.path.exists(target_path):
                os.rename(target_path, old_dir)
            os.rename(staging_dir, target_path)
            preset = update_preset(existing.id, description=description, path=target_path)
        else:
            target_path = os.path.join(PRESETS_DIR, name)
            os.rename(staging_dir, target_path)
            preset = create_preset(name=name, description=description, path=target_path)

        _replace_binary_metadata(name, bundle['binary_metadata'])
        db.session.commit()

        if old_dir and os.path.isdir(old_dir):
            shutil.rmtree(old_dir, ignore_errors=True)

        current_app.logger.info("Imported preset '%s' (%s) from archive.", name, mode)
        status = 200 if mode == 'overwrite' else 201
        return jsonify({
            'data': _preset_response(preset),
            'message': 'Preset imported successfully.',
        }), status

    except ValueError as e:
        _cleanup_after_failure(mode, staging_dir, target_path, old_dir, existing)
        db.session.rollback()
        return jsonify({'error': {'message': str(e)}}), 400
    except Exception as e:
        _cleanup_after_failure(mode, staging_dir, target_path, old_dir, existing)
        db.session.rollback()
        current_app.logger.error('Error importing preset: %s', e, exc_info=True)
        return jsonify({'error': {'message': 'Failed to import preset archive.'}}), 500
