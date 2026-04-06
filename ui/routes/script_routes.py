"""
Script management API routes for minqlx plugins.

Provides endpoints for browsing, reading, editing, validating, and uploading
Python scripts used by QLDS instances.
"""

import os
import shutil
import subprocess
import tempfile
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename

# Create blueprint
script_api_bp = Blueprint('script_api_routes', __name__)

# Constants
ALLOWED_EXTENSIONS = {'.py'}
MAX_FILE_SIZE = 256 * 1024  # 256KB
CONFIGS_BASE = 'configs'
PRESETS_DIR = 'presets'
SCRIPTS_DIR = 'scripts'


def _get_scripts_base_path(preset=None, host=None, instance_id=None):
    """
    Determine the base path for scripts based on context.

    Args:
        preset: Preset name (e.g., 'default')
        host: Host name
        instance_id: Instance ID

    Returns:
        Absolute path to the scripts directory
    """
    base = os.path.abspath(CONFIGS_BASE)

    if preset:
        return os.path.join(base, PRESETS_DIR, preset, SCRIPTS_DIR)
    elif host and instance_id:
        return os.path.join(base, host, str(instance_id), SCRIPTS_DIR)
    else:
        # Default to default preset
        return os.path.join(base, PRESETS_DIR, 'default', SCRIPTS_DIR)


def _build_file_tree(path, base_path=None, filter_py=True):
    """
    Recursively build a file tree structure.

    Args:
        path: Current path to scan
        base_path: Root path for calculating relative paths (defaults to path if not provided)
        filter_py: If True, only include .py files (folders are included if they contain .py files)

    Returns:
        List of file/folder objects with structure:
        [{ name, type: 'file'|'folder', path, children? }]
    """
    # Use provided base_path or default to current path for root-level call
    if base_path is None:
        base_path = path

    if not os.path.exists(path):
        return []

    items = []
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return []

    for entry in entries:
        full_path = os.path.join(path, entry)
        relative_path = os.path.relpath(full_path, base_path)

        # Skip hidden files and __pycache__
        if entry.startswith('.') or entry == '__pycache__':
            continue

        if os.path.isdir(full_path):
            children = _build_file_tree(full_path, base_path, filter_py)
            # Only include folder if it has children (after filtering)
            if children or not filter_py:
                items.append({
                    'name': entry,
                    'type': 'folder',
                    'path': relative_path,
                    'children': children
                })
        elif os.path.isfile(full_path):
            if filter_py:
                if entry.endswith('.py'):
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'path': relative_path
                    })
            else:
                items.append({
                    'name': entry,
                    'type': 'file',
                    'path': relative_path
                })

    return items


def _validate_python_content(content):
    """
    Validate Python script syntax using ruff (preferred) or py_compile fallback.

    Args:
        content: Python source code as string

    Returns:
        dict with { valid: bool, errors: [{ line, column, message, severity }] }
    """
    errors = []

    # Use a temporary directory to isolate the validation process
    # This prevents permission issues with shared /tmp/__pycache__ in multi-user environments
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = os.path.join(temp_dir, 'script_validation.py')
        
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            return {
                'valid': False,
                'errors': [{
                    'line': 1,
                    'column': 1,
                    'message': 'Failed to create temporary file for validation',
                    'severity': 'error'
                }]
            }

        # Try ruff first (better error messages)
        try:
            # Try ruff check with JSON output
            result = subprocess.run(
                ['ruff', 'check', '--output-format=json', '--select=E,F', temp_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                # No errors
                return {'valid': True, 'errors': []}

            # Parse ruff JSON output
            import json
            try:
                ruff_errors = json.loads(result.stdout)
                for err in ruff_errors:
                    errors.append({
                        'line': err.get('location', {}).get('row', 1),
                        'column': err.get('location', {}).get('column', 1),
                        'message': err.get('message', 'Unknown error'),
                        'severity': 'error' if err.get('code', '').startswith('F') else 'warning'
                    })
                return {'valid': len([e for e in errors if e['severity'] == 'error']) == 0, 'errors': errors}
            except json.JSONDecodeError:
                # Ruff output not parseable, fall through to py_compile
                pass

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Ruff not available or timed out, fall through to py_compile
            pass

        # Fallback to py_compile
        try:
            result = subprocess.run(
                ['python3', '-m', 'py_compile', temp_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return {'valid': True, 'errors': []}

            # Parse py_compile error output
            error_output = result.stderr or result.stdout
            if error_output:
                # Try to extract line number from error message
                import re
                match = re.search(r'line (\d+)', error_output)
                line_num = int(match.group(1)) if match else 1

                errors.append({
                    'line': line_num,
                    'column': 1,
                    'message': error_output.strip().split('\n')[-1],
                    'severity': 'error'
                })

            return {'valid': False, 'errors': errors}

        except Exception as e:
            return {
                'valid': False,
                'errors': [{
                    'line': 1,
                    'column': 1,
                    'message': f'Validation failed: {str(e)}',
                    'severity': 'error'
                }]
            }


def _is_safe_path(base_path, requested_path):
    """Check if the requested path is within the base path (prevent directory traversal)."""
    base = os.path.abspath(base_path)
    requested = os.path.abspath(os.path.join(base_path, requested_path))
    return requested.startswith(base + os.sep) or requested == base


@script_api_bp.route('/tree', methods=['GET'])
@jwt_required()
def get_script_tree():
    """
    Get the file tree structure for scripts.

    Query params:
        preset: Preset name (e.g., 'default')
        host: Host name (used with instance_id)
        instance_id: Instance ID (used with host)

    Returns:
        { data: [{ name, type, path, children? }] }
    """
    preset = request.args.get('preset')
    host = request.args.get('host')
    instance_id = request.args.get('instance_id')

    scripts_path = _get_scripts_base_path(preset, host, instance_id)

    if not os.path.exists(scripts_path):
        return jsonify({'data': []})

    tree = _build_file_tree(scripts_path, filter_py=True)
    return jsonify({'data': tree})


@script_api_bp.route('/content', methods=['GET'])
@jwt_required()
def get_script_content():
    """
    Get the content of a specific script file.

    Query params:
        path: Relative path to the script (e.g., 'branding.py' or 'discord_extensions/bot.py')
        preset: Preset name (optional)
        host: Host name (optional, used with instance_id)
        instance_id: Instance ID (optional, used with host)

    Returns:
        { data: { path, content } }
    """
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': {'message': 'Path parameter is required'}}), 400

    preset = request.args.get('preset')
    host = request.args.get('host')
    instance_id = request.args.get('instance_id')

    scripts_path = _get_scripts_base_path(preset, host, instance_id)

    # Security check
    if not _is_safe_path(scripts_path, file_path):
        return jsonify({'error': {'message': 'Invalid path'}}), 400

    full_path = os.path.join(scripts_path, file_path)

    if not os.path.exists(full_path):
        return jsonify({'error': {'message': 'File not found'}}), 404

    if not os.path.isfile(full_path):
        return jsonify({'error': {'message': 'Path is not a file'}}), 400

    if not file_path.endswith('.py'):
        return jsonify({'error': {'message': 'Only .py files can be read'}}), 400

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'data': {'path': file_path, 'content': content}})
    except Exception as e:
        return jsonify({'error': {'message': f'Failed to read file: {str(e)}'}}), 500


@script_api_bp.route('/content', methods=['PUT'])
@jwt_required()
def save_script_content():
    """
    Save content to a script file (instance scripts only).

    Body:
        { host, instance_id, path, content }

    Returns:
        { data: { path, message } }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': 'Request body must be JSON'}}), 400

    host = data.get('host')
    instance_id = data.get('instance_id')
    file_path = data.get('path')
    content = data.get('content')

    if not all([host, instance_id, file_path]):
        return jsonify({'error': {'message': 'host, instance_id, and path are required'}}), 400

    if content is None:
        return jsonify({'error': {'message': 'content is required'}}), 400

    if not file_path.endswith('.py'):
        return jsonify({'error': {'message': 'Only .py files can be saved'}}), 400

    scripts_path = _get_scripts_base_path(host=host, instance_id=instance_id)

    # Security check
    if not _is_safe_path(scripts_path, file_path):
        return jsonify({'error': {'message': 'Invalid path'}}), 400

    full_path = os.path.join(scripts_path, file_path)

    # Create directory if it doesn't exist (for new files in existing folders)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'data': {'path': file_path, 'message': 'File saved successfully'}})
    except Exception as e:
        return jsonify({'error': {'message': f'Failed to save file: {str(e)}'}}), 500


@script_api_bp.route('/validate', methods=['POST'])
@jwt_required()
def validate_script():
    """
    Validate Python script syntax.

    Body:
        { content }

    Returns:
        { data: { valid, errors: [{ line, column, message, severity }] } }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': 'Request body must be JSON'}}), 400

    content = data.get('content')
    if content is None:
        return jsonify({'error': {'message': 'content is required'}}), 400

    result = _validate_python_content(content)
    return jsonify({'data': result})


@script_api_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_script():
    """
    Upload a Python script file.

    Form data:
        file: The .py file to upload
        host: Host name
        instance_id: Instance ID
        target_path: Optional subfolder path (e.g., 'discord_extensions')

    Returns:
        { data: { path, message } }
    """
    if 'file' not in request.files:
        return jsonify({'error': {'message': 'No file provided'}}), 400

    file = request.files['file']
    host = request.form.get('host')
    instance_id = request.form.get('instance_id')
    target_path = request.form.get('target_path', '')

    if not all([host, instance_id]):
        return jsonify({'error': {'message': 'host and instance_id are required'}}), 400

    if file.filename == '':
        return jsonify({'error': {'message': 'No file selected'}}), 400

    # Validate extension
    filename = secure_filename(file.filename)
    if not filename.endswith('.py'):
        return jsonify({'error': {'message': 'Only .py files can be uploaded'}}), 400

    # Check file size
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Seek back to start

    if file_size > MAX_FILE_SIZE:
        return jsonify({'error': {'message': f'File too large. Maximum size is {MAX_FILE_SIZE // 1024}KB'}}), 400

    scripts_path = _get_scripts_base_path(host=host, instance_id=instance_id)

    # Build target path
    if target_path:
        if not _is_safe_path(scripts_path, target_path):
            return jsonify({'error': {'message': 'Invalid target path'}}), 400
        save_dir = os.path.join(scripts_path, target_path)
    else:
        save_dir = scripts_path

    os.makedirs(save_dir, exist_ok=True)

    full_path = os.path.join(save_dir, filename)
    relative_path = os.path.relpath(full_path, scripts_path)

    try:
        file.save(full_path)
        return jsonify({'data': {'path': relative_path, 'message': f'File {filename} uploaded successfully'}})
    except Exception as e:
        return jsonify({'error': {'message': f'Failed to save file: {str(e)}'}}), 500
