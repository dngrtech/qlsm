"""
Factory management API routes.

Provides endpoints for browsing and reading factory files (.factories).
"""

import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

# Create blueprint
factory_api_bp = Blueprint('factory_api_routes', __name__)

# Constants
CONFIGS_BASE = 'configs'
PRESETS_DIR = 'presets'
FACTORIES_DIR = 'factories' # Directory name for factory files


def _get_factories_base_path(preset=None, host=None, instance_id=None):
    """
    Determine the base path for factories based on context.

    Args:
        preset: Preset name (e.g., 'default')
        host: Host name
        instance_id: Instance ID

    Returns:
        Absolute path to the factories directory
    """
    base = os.path.abspath(CONFIGS_BASE)

    if preset:
        # For presets, factories are stored in a 'factories' subdirectory
        return os.path.join(base, PRESETS_DIR, preset, FACTORIES_DIR)
    elif host and instance_id:
        return os.path.join(base, host, str(instance_id), FACTORIES_DIR)
    else:
        # Default to default preset
        return os.path.join(base, PRESETS_DIR, 'default', FACTORIES_DIR)


def _is_safe_path(base_path, requested_path):
    """Check if the requested path is within the base path (prevent directory traversal)."""
    base = os.path.abspath(base_path)
    requested = os.path.abspath(os.path.join(base_path, requested_path))
    return requested.startswith(base + os.sep) or requested == base


@factory_api_bp.route('/tree', methods=['GET'])
@jwt_required()
def get_factory_tree():
    """
    Get the list of available factory files.
    
    Query params:
        preset: Preset name (e.g., 'default')
        host: Host name (used with instance_id)
        instance_id: Instance ID (used with host)

    Returns:
        { data: [{ name, type: 'file', path }] } 
    """
    preset = request.args.get('preset')
    host = request.args.get('host')
    instance_id = request.args.get('instance_id')

    factories_path = _get_factories_base_path(preset, host, instance_id)

    if not os.path.exists(factories_path):
        return jsonify({'data': []})

    items = []
    try:
        entries = sorted(os.listdir(factories_path))
        for entry in entries:
            full_path = os.path.join(factories_path, entry)
            
            # Skip hidden files and directories for now
            if entry.startswith('.'):
                continue
                
            if os.path.isfile(full_path) and entry.endswith('.factories'):
                 items.append({
                    'name': entry,
                    'type': 'file',
                    'path': entry # Path is just the filename relative to the factories dir
                })
    except PermissionError:
        return jsonify({'data': []})

    return jsonify({'data': items})


@factory_api_bp.route('/content', methods=['GET'])
@jwt_required()
def get_factory_content():
    """
    Get the content of a specific factory file.

    Query params:
        path: Relative path to the factory file (filename)
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

    factories_path = _get_factories_base_path(preset, host, instance_id)

    # Security check
    if not _is_safe_path(factories_path, file_path):
        return jsonify({'error': {'message': 'Invalid path'}}), 400

    full_path = os.path.join(factories_path, file_path)

    if not os.path.exists(full_path):
        return jsonify({'error': {'message': 'File not found'}}), 404

    if not os.path.isfile(full_path):
        return jsonify({'error': {'message': 'Path is not a file'}}), 400

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'data': {'path': file_path, 'content': content}})
    except Exception as e:
        return jsonify({'error': {'message': f'Failed to read file: {str(e)}'}}), 500
