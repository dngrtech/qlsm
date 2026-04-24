import json
import os
import shutil
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from ui import db
from ui.database import get_presets, create_preset, get_preset, update_preset, delete_preset
from ui.preset_support import PRESETS_DIR, validate_user_preset_name

preset_api_bp = Blueprint('preset_api_routes', __name__)  # url_prefix will be /presets

# Config file mapping for API response keys
CONFIG_FILE_MAP = {
    'server.cfg': 'server_cfg',
    'mappool.txt': 'mappool_txt',
    'access.txt': 'access_txt',
    'workshop.txt': 'workshop_txt'
}

# Reverse mapping for writing files from API request
API_TO_FILE_MAP = {v: k for k, v in CONFIG_FILE_MAP.items()}

def _read_preset_configs(preset_path):
    """Read all config files from a preset folder."""
    configs = {}
    for filename, api_key in CONFIG_FILE_MAP.items():
        filepath = os.path.join(preset_path, filename)
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    configs[api_key] = f.read()
            else:
                configs[api_key] = ''
        except Exception as e:
            current_app.logger.error(f"Error reading preset config file {filepath}: {e}")
            configs[api_key] = ''
    return configs


def _read_preset_scripts(preset_path):
    """Read all .py scripts from a preset's scripts/ folder.

    For non-default presets that have their own scripts folder, the default
    preset's scripts are merged in first so they are not lost. Preset-specific
    files take priority over defaults with the same relative path.
    """
    scripts = {}
    scripts_dir = os.path.join(preset_path, 'scripts')
    if not os.path.exists(scripts_dir):
        return scripts

    # For non-default presets, merge default scripts first so the preset
    # only needs to store its customisations (new or overridden files).
    # Use the basename of preset_path (the preset name) rather than a
    # CWD-dependent os.path.abspath comparison for robustness.
    default_scripts_dir = os.path.join(PRESETS_DIR, 'default', 'scripts')
    if os.path.basename(preset_path) != 'default' and os.path.exists(default_scripts_dir):
        for root, _, files in os.walk(default_scripts_dir):
            for filename in files:
                if filename.endswith(('.py', '.txt')):
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, default_scripts_dir)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            scripts[rel_path] = f.read()
                    except Exception as e:
                        current_app.logger.error(f"Error reading default script {filepath}: {e}")

    for root, _, files in os.walk(scripts_dir):
        for filename in files:
            if filename.endswith(('.py', '.txt')):
                filepath = os.path.join(root, filename)
                # Get relative path from scripts_dir
                rel_path = os.path.relpath(filepath, scripts_dir)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        scripts[rel_path] = f.read()
                except Exception as e:
                    current_app.logger.error(f"Error reading script {filepath}: {e}")
    return scripts


def _write_preset_scripts(preset_path, scripts_data):
    """Write scripts to a preset's scripts/ folder."""
    if not scripts_data:
        return

    scripts_dir = os.path.join(preset_path, 'scripts')
    os.makedirs(scripts_dir, exist_ok=True)

    for rel_path, content in scripts_data.items():
        # Security: ensure path doesn't escape scripts directory
        full_path = os.path.normpath(os.path.join(scripts_dir, rel_path))
        if not full_path.startswith(os.path.normpath(scripts_dir)):
            current_app.logger.warning(f"Skipping script with invalid path: {rel_path}")
            continue

        # Create parent directories if needed
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        current_app.logger.info(f"Wrote preset script: {full_path}")


def _read_preset_factories(preset_path):
    """Read all .factories files from a preset's factories/ folder."""
    factories = {}
    factories_dir = os.path.join(preset_path, 'factories')
    if not os.path.exists(factories_dir):
        return factories

    for root, _, files in os.walk(factories_dir):
        for filename in files:
            if filename.endswith('.factories'):
                filepath = os.path.join(root, filename)
                # Get relative path from factories_dir (usually just filename)
                rel_path = os.path.relpath(filepath, factories_dir)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        factories[rel_path] = f.read()
                except Exception as e:
                    current_app.logger.error(f"Error reading factory {filepath}: {e}")
    return factories


def _write_preset_factories(preset_path, factories_data):
    """Write factories to a preset's factories/ folder."""
    if not factories_data:
        return

    factories_dir = os.path.join(preset_path, 'factories')
    os.makedirs(factories_dir, exist_ok=True)

    for rel_path, content in factories_data.items():
        if content is None: continue # Skip if no content

        # Security: ensure path doesn't escape factories directory
        full_path = os.path.normpath(os.path.join(factories_dir, rel_path))
        if not full_path.startswith(os.path.normpath(factories_dir)):
            current_app.logger.warning(f"Skipping factory with invalid path: {rel_path}")
            continue

        # Create parent directories if needed
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        current_app.logger.info(f"Wrote preset factory: {full_path}")


def _read_preset_checked_plugins(preset_path):
    """Read checked_plugins.json from a preset folder.
    Returns a list of plugin paths, or None if the file does not exist.
    """
    filepath = os.path.join(preset_path, 'checked_plugins.json')
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading checked_plugins.json from {filepath}: {e}")
        return None


def _write_preset_checked_plugins(preset_path, checked_plugins):
    """Write checked_plugins.json to a preset folder."""
    os.makedirs(preset_path, exist_ok=True)
    filepath = os.path.join(preset_path, 'checked_plugins.json')
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(checked_plugins, f)
        current_app.logger.info(f"Wrote checked_plugins.json: {filepath}")
    except Exception as e:
        current_app.logger.error(f"Error writing checked_plugins.json to {filepath}: {e}")


def _write_preset_configs(preset_path, config_data):
    """Write config files to a preset folder."""
    os.makedirs(preset_path, exist_ok=True)
    for api_key, filename in API_TO_FILE_MAP.items():
        content = config_data.get(api_key)
        if content is not None:
            filepath = os.path.join(preset_path, filename)
            with open(filepath, 'w') as f:
                f.write(content)
            current_app.logger.info(f"Wrote preset config file: {filepath}")


def _validation_status(reason):
    return 400 if reason == 'format' else 409


@preset_api_bp.route('/validate-name', methods=['GET'], endpoint='validate_preset_name_api')
@jwt_required()
def validate_preset_name_api():
    """Check if a preset name is valid and available."""
    name = request.args.get('name', '').strip()

    is_valid, error, _ = validate_user_preset_name(name)

    return jsonify({
        "data": {
            "is_valid": is_valid,
            "error": error
        }
    })


@preset_api_bp.route('/', methods=['GET'], endpoint='list_presets_api')
@jwt_required()
def list_presets_api():
    """Returns a list of all configuration presets (metadata only)."""
    presets = get_presets()
    preset_list = [preset.to_dict() for preset in presets]
    return jsonify({"data": preset_list})


@preset_api_bp.route('/', methods=['POST'], endpoint='create_preset_api')
@jwt_required()
def create_preset_api():
    """Creates a new configuration preset (saves to filesystem)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    name = data.get('name', '').strip()

    # Validate name
    is_valid, error, reason = validate_user_preset_name(name)
    if not is_valid:
        return jsonify({"error": {"message": error}}), _validation_status(reason)

    if 'checked_plugins' in data and not isinstance(data['checked_plugins'], list):
        return jsonify({"error": {"message": "checked_plugins must be a list"}}), 400

    description = data.get('description', '')
    preset_path = os.path.join(PRESETS_DIR, name)

    # Validate draft before any filesystem mutations
    draft_id = data.get('draft_id')
    if draft_id:
        from ui.routes.draft_routes import (
            _validate_draft_id, _draft_exists,
            _get_draft_scripts_path
        )
        if not _validate_draft_id(draft_id):
            return jsonify({"error": {"message": "Invalid draft_id"}}), 400
        if not _draft_exists(draft_id):
            return jsonify({"error": {"message": "Draft not found"}}), 400

    try:
        # Step 1: Create folder and write config files
        _write_preset_configs(preset_path, data)

        # Step 1b: Write scripts via draft or legacy
        if draft_id:

            draft_scripts = _get_draft_scripts_path(draft_id)
            preset_scripts_dir = os.path.join(preset_path, 'scripts')
            if os.path.exists(draft_scripts):
                if os.path.exists(preset_scripts_dir):
                    shutil.rmtree(preset_scripts_dir)
                shutil.copytree(draft_scripts, preset_scripts_dir)
            # Don't delete the draft — the form continues using it after preset save
        elif 'scripts' in data:
            _write_preset_scripts(preset_path, data['scripts'])

        # Step 1c: Write factories if provided
        if 'factories' in data:
            _write_preset_factories(preset_path, data['factories'])

        # Step 1d: Write checked plugins if provided
        if 'checked_plugins' in data:
            _write_preset_checked_plugins(preset_path, data['checked_plugins'])

        # Step 2: Create DB record
        preset_data = {
            'name': name,
            'description': description,
            'path': preset_path
        }
        new_preset = create_preset(**preset_data)
        current_app.logger.info(f"ConfigPreset '{new_preset.name}' created with ID {new_preset.id} at {preset_path}")

        # Return preset data with config content and scripts for immediate use
        response_data = new_preset.to_dict()
        response_data.update(_read_preset_configs(preset_path))
        response_data['scripts'] = _read_preset_scripts(preset_path)
        response_data['factories'] = _read_preset_factories(preset_path)
        response_data['checked_plugins'] = _read_preset_checked_plugins(preset_path)

        return jsonify({"data": response_data, "message": "Preset created successfully."}), 201

    except Exception as e:
        # Cleanup folder if DB creation fails
        if os.path.exists(preset_path):
            try:
                shutil.rmtree(preset_path)
            except Exception as cleanup_err:
                current_app.logger.error(f"Failed to cleanup preset folder {preset_path}: {cleanup_err}")
        db.session.rollback()
        current_app.logger.error(f"Error creating preset: {e}", exc_info=True)
        return jsonify({"error": {"message": f"Error creating preset: {str(e)}"}}), 500


@preset_api_bp.route('/<int:preset_id>', methods=['GET'], endpoint='get_preset_api')
@jwt_required()
def get_preset_api(preset_id):
    """Returns a specific configuration preset with config content (reads from filesystem)."""
    preset = get_preset(preset_id)
    if not preset:
        return jsonify({"error": {"message": "Preset not found."}}), 404

    # Check if preset folder exists
    if not os.path.exists(preset.path):
        current_app.logger.error(f"Preset folder missing for preset {preset_id}: {preset.path}")
        return jsonify({"error": {"message": "Preset configuration files not found."}}), 500

    # Build response with metadata, config content, and scripts
    response_data = preset.to_dict()
    response_data.update(_read_preset_configs(preset.path))
    response_data['scripts'] = _read_preset_scripts(preset.path)
    response_data['factories'] = _read_preset_factories(preset.path)
    response_data['checked_plugins'] = _read_preset_checked_plugins(preset.path)

    return jsonify({"data": response_data})


@preset_api_bp.route('/<int:preset_id>', methods=['PUT'], endpoint='update_preset_api')
@jwt_required()
def update_preset_api(preset_id):
    """Updates a specific configuration preset."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    preset = get_preset(preset_id)
    if not preset:
        return jsonify({"error": {"message": "Preset not found."}}), 404

    requested_name = data.get('name')
    new_name = requested_name.strip() if isinstance(requested_name, str) else requested_name
    if preset.is_builtin and new_name and new_name != preset.name:
        return jsonify({"error": {"message": "Cannot rename a built-in preset."}}), 403

    if 'checked_plugins' in data and not isinstance(data['checked_plugins'], list):
        return jsonify({"error": {"message": "checked_plugins must be a list"}}), 400

    # Check for name change
    if new_name and new_name != preset.name:
        is_valid, error, reason = validate_user_preset_name(
            new_name, current_preset_id=preset.id
        )
        if not is_valid:
            return jsonify({"error": {"message": error}}), _validation_status(reason)
        data['name'] = new_name

    # Validate draft before any filesystem mutations
    draft_id = data.get('draft_id')
    if draft_id:
        from ui.routes.draft_routes import (
            _validate_draft_id, _draft_exists,
            _get_draft_scripts_path
        )
        if not _validate_draft_id(draft_id):
            return jsonify({"error": {"message": "Invalid draft_id"}}), 400
        if not _draft_exists(draft_id):
            return jsonify({"error": {"message": "Draft not found"}}), 400

    try:
        # Update config files if provided
        has_config_updates = any(key in data for key in API_TO_FILE_MAP.keys())
        if has_config_updates:
            _write_preset_configs(preset.path, data)

        # Update scripts via draft or legacy
        if draft_id:
            draft_scripts = _get_draft_scripts_path(draft_id)
            preset_scripts_dir = os.path.join(preset.path, 'scripts')
            if os.path.exists(draft_scripts):
                if os.path.exists(preset_scripts_dir):
                    shutil.rmtree(preset_scripts_dir)
                shutil.copytree(draft_scripts, preset_scripts_dir)
            # Don't delete the draft — the form continues using it after preset save
        elif 'scripts' in data:
            _write_preset_scripts(preset.path, data['scripts'])

        # Update factories if provided
        if 'factories' in data:
            _write_preset_factories(preset.path, data['factories'])

        # Update checked plugins if provided
        if 'checked_plugins' in data:
            _write_preset_checked_plugins(preset.path, data['checked_plugins'])

        # Handle name change (rename folder)
        if new_name and new_name != preset.name:
            old_path = preset.path
            new_path = os.path.join(PRESETS_DIR, new_name)
            shutil.move(old_path, new_path)
            data['path'] = new_path
            current_app.logger.info(f"Renamed preset folder from {old_path} to {new_path}")

        # Update DB record
        update_data = {}
        if 'name' in data:
            update_data['name'] = data['name']
        if 'description' in data:
            update_data['description'] = data['description']
        if 'path' in data:
            update_data['path'] = data['path']

        if update_data:
            updated_preset = update_preset(preset_id, **update_data)
        else:
            updated_preset = preset

        if updated_preset:
            current_app.logger.info(f"ConfigPreset '{updated_preset.name}' (ID: {preset_id}) updated.")
            response_data = updated_preset.to_dict()
            response_data.update(_read_preset_configs(updated_preset.path))
            response_data['scripts'] = _read_preset_scripts(updated_preset.path)
            response_data['factories'] = _read_preset_factories(updated_preset.path)
            response_data['checked_plugins'] = _read_preset_checked_plugins(updated_preset.path)
            return jsonify({"data": response_data, "message": "Preset updated successfully."})
        else:
            return jsonify({"error": {"message": "Preset update failed."}}), 500

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating preset {preset_id}: {e}", exc_info=True)
        return jsonify({"error": {"message": f"Error updating preset: {str(e)}"}}), 500


@preset_api_bp.route('/<int:preset_id>', methods=['DELETE'], endpoint='delete_preset_api')
@jwt_required()
def delete_preset_api(preset_id):
    """Deletes a specific configuration preset (removes DB record + folder)."""
    preset = get_preset(preset_id)
    if not preset:
        return jsonify({"error": {"message": "Preset not found."}}), 404

    if preset.is_builtin:
        return jsonify({"error": {"message": "Cannot delete a built-in preset."}}), 403

    try:
        preset_name = preset.name
        preset_path = preset.path

        # Step 1: Delete DB record first
        if delete_preset(preset_id):
            current_app.logger.info(f"ConfigPreset '{preset_name}' (ID: {preset_id}) deleted from database.")

            # Step 2: Delete folder
            if os.path.exists(preset_path):
                shutil.rmtree(preset_path)
                current_app.logger.info(f"Deleted preset folder: {preset_path}")

            return jsonify({"message": f"Preset '{preset_name}' deleted successfully."}), 200
        else:
            return jsonify({"error": {"message": "Preset deletion failed."}}), 500

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting preset {preset_id}: {e}", exc_info=True)
        return jsonify({"error": {"message": f"Error deleting preset: {str(e)}"}}), 500
