"""Cvar catalog route.

Serves ui/data/ql_cvar_catalog.json - the list of server cvars and console
commands the config editor's autocomplete is built from, with the source of
every description attached (see tools/gen_cvar_catalog.py).

It lives on the backend rather than inside the frontend bundle because the
catalog is generated from files in this repo and is expected to be
regenerated against a newer QLDS dump without rebuilding the UI. qlx_* cvars
are not here on purpose: those come from the plugin manifests of the server
being edited (ui/plugin_manifest.py).
"""

import hashlib
import json
import os

from flask import Blueprint, jsonify, current_app, request
from flask_jwt_extended import jwt_required

cvar_catalog_bp = Blueprint('cvar_catalog_routes', __name__)

CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'ql_cvar_catalog.json')

# Parsed once per process: the file only changes when the repo does.
_cache = {'mtime': None, 'payload': None, 'etag': None}


def load_catalog():
    """Return (payload, etag). Falls back to an empty catalog if the file is
    missing or unreadable - autocomplete degrades to plugin cvars only rather
    than breaking the editor."""
    try:
        mtime = os.path.getmtime(CATALOG_PATH)
    except OSError:
        return {'version': 0, 'cvars': [], 'commands': [], 'groups': [], 'sources': {}}, 'empty'

    if _cache['mtime'] != mtime:
        try:
            with open(CATALOG_PATH, 'r', encoding='utf-8') as handle:
                raw = handle.read()
            payload = json.loads(raw)
        except (OSError, ValueError) as exc:
            current_app.logger.warning(f'Failed to read cvar catalog {CATALOG_PATH}: {exc}')
            return {'version': 0, 'cvars': [], 'commands': [], 'groups': [], 'sources': {}}, 'empty'
        _cache.update({
            'mtime': mtime,
            'payload': payload,
            'etag': hashlib.sha1(raw.encode('utf-8')).hexdigest(),
        })
    return _cache['payload'], _cache['etag']


@cvar_catalog_bp.route('', methods=['GET'])
@jwt_required()
def get_cvar_catalog():
    """Returns { data: { version, sources, groups, gametypes, commands, cvars } }."""
    payload, etag = load_catalog()
    if request.headers.get('If-None-Match') == etag:
        return '', 304
    response = jsonify({'data': payload})
    response.headers['ETag'] = etag
    response.headers['Cache-Control'] = 'no-cache'
    return response
