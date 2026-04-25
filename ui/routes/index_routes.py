from flask import Blueprint, current_app, send_from_directory, jsonify
import os
from ui.preset_support import resolve_preset_path

# Create a Blueprint for index routes
index_bp = Blueprint('index_routes', __name__, url_prefix='/')

def _frontend_dist_dir():
    """Absolute path to built frontend assets."""
    return os.path.join(current_app.root_path, '..', 'frontend-react', 'dist')

@index_bp.route('/')
def spa_index():
    """Serve the SPA entrypoint."""
    return send_from_directory(_frontend_dist_dir(), 'index.html')

@index_bp.route('/<path:path>')
def spa_assets(path):
    """Serve built frontend assets, fallback to SPA entrypoint for client routes."""
    # Let API routes return 404 instead of serving the SPA shell.
    if path.startswith('api/'):
        return jsonify({"error": {"message": "Not found"}}), 404

    dist_dir = _frontend_dist_dir()
    file_path = os.path.join(dist_dir, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(dist_dir, path)
    return send_from_directory(dist_dir, 'index.html')

@index_bp.route('/api/default-config/<path:filename>')
def get_default_config_file(filename):
    """Serves a default configuration file from the registered default preset."""
    config_dir = os.path.abspath(resolve_preset_path('default'))
    try:
        # Attempt to send the file directly. 
        # For text files, we might want to read and return as JSON with content.
        # For now, let's read and return its content as plain text.
        file_path = os.path.abspath(os.path.join(config_dir, filename))
        if not file_path.startswith(config_dir + os.sep):
            return jsonify({"error": "File not found"}), 404
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return jsonify({"error": "File not found"}), 404
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Return as plain text, or could wrap in JSON: e.g., jsonify({"content": content})
        # For CodeMirror, plain text is usually fine if fetched directly.
        response = current_app.response_class(
            response=content,
            status=200,
            mimetype='text/plain'
        )
        return response
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Error serving default config {filename}: {e}")
        return jsonify({"error": "An error occurred"}), 500
