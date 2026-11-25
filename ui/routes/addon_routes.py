"""Core-owned addon endpoints: the catalog, per-scope state, and tier-2 assets.

Everything here is about addons; an addon's *own* endpoints live in its own
blueprint, mounted by the registry at /api/addons/<id>/. This module owns
/api/addons (no id) plus the /state and /ui sub-resources of an addon, which
core must own because an addon cannot be trusted to report its own enable
state or to serve its own files safely.
"""
import os

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from ui import db
from ui.addons import catalog, get_addon, get_addons
from ui.addons.manifest import IMAGE_EXTENSIONS
from ui.addons.settings import AddonSettingsError
from ui.addons.runtime_protection import (
    RuntimeProviderConflict, check_provider_dependencies, lock_provider_state, provider_lifecycle_lock,
)
from ui.models import Host, QLInstance

addon_api_bp = Blueprint('addon_routes', __name__)

_SCOPES = ('global', 'host', 'instance')

# .js/.css/.map are tier-2 component bundles. .svg/.png/.webp are icons an
# addon's manifest points at (a select option, a live_status_columns entry,
# the addon's own icon) -- everything else in the addon directory (backend.py,
# playbooks, plugin sources) must never be reachable over this route.
_CODE_EXTENSIONS = ('.js', '.css', '.map')
# One list, shared with the manifest validator so "what a manifest may declare"
# and "what this route will serve" cannot drift apart.
_IMAGE_EXTENSIONS = IMAGE_EXTENSIONS


def _resolve(addon_id):
    """(addon, error_response) -- error is None when the addon is usable."""
    addon = get_addon(addon_id)
    if addon is None:
        return None, (jsonify({"error": {"message": f'Addon "{addon_id}" is not installed'}}), 404)
    if not addon.loaded:
        return None, (jsonify({"error": {
            "message": f'Addon "{addon_id}" failed to load',
            "details": addon.errors,
        }}), 409)
    return addon, None


def _scope_args():
    scope = (request.args.get('scope') or 'global').strip().lower()
    if scope not in _SCOPES:
        return None, None, (jsonify({"error": {"message": f'Unknown scope "{scope}"'}}), 400)
    raw_id = request.args.get('scope_id', '0')
    try:
        scope_id = int(raw_id)
    except (TypeError, ValueError):
        return None, None, (jsonify({"error": {"message": 'scope_id must be an integer'}}), 400)
    if scope == 'host' and db.session.get(Host, scope_id, populate_existing=True) is None:
        return None, None, (jsonify({"error": {"message": f'Host {scope_id} not found'}}), 404)
    if scope == 'instance' and db.session.get(QLInstance, scope_id, populate_existing=True) is None:
        return None, None, (jsonify({"error": {"message": f'Instance {scope_id} not found'}}), 404)
    return scope, scope_id, None


@addon_api_bp.route('', methods=['GET'], endpoint='list_addons_api')
@addon_api_bp.route('/', methods=['GET'], endpoint='list_addons_slash_api')
@jwt_required()
def list_addons_api():
    """Every discovered addon, including the broken ones.

    Broken addons are listed on purpose: an addon that silently vanished from
    the UI because its manifest has a typo is far harder to diagnose than one
    shown with its error attached.

    The list is what this *process* loaded at startup, reconciled against
    what is on the volume right now. An addon installed, removed, or updated
    in place since then shows up as `pending_restart` rather than silently
    looking active -- the alternative is an entry whose endpoints 404, or
    whose code the operator wrongly believes is already live, with no
    explanation either way.
    """
    from ui.addons.install import package_stamp, scan_installed_ids, scan_installed_versions

    entries = catalog()
    loaded_ids = {entry['id'] for entry in entries}
    loaded = get_addons()
    packages_dir = current_app.config.get('ADDON_PACKAGES_DIR')
    on_disk = scan_installed_ids(packages_dir)
    on_disk_versions = scan_installed_versions(packages_dir)

    for entry in entries:
        installed = entry['source'] == 'installed'
        # Loaded, but its package is gone from the volume -> uninstalled since boot.
        removed = installed and entry['id'] not in on_disk
        # Present both before and after, but the package on disk is not the
        # one this process imported -> an in-place update it hasn't picked up
        # yet. The stamp catches a reinstall at an unchanged version, which
        # the version comparison alone would report as nothing to do.
        updated = installed and not removed and (
            on_disk_versions.get(entry['id']) != entry['version']
            or package_stamp(os.path.join(packages_dir, entry['id'])) != loaded[entry['id']].stamp
        )
        entry['pending_restart'] = removed or updated
        if removed:
            entry['pending_action'] = 'uninstall'
        elif updated:
            entry['pending_action'] = 'update'
        else:
            entry['pending_action'] = None

    for addon_id in sorted(on_disk - loaded_ids):
        entries.append({
            'id': addon_id, 'name': addon_id, 'version': '', 'description': '',
            'scopes': [], 'ui': {}, 'ui_api': None, 'settings_schema': {},
            'source': 'installed', 'loaded': False, 'ui_mountable': False,
            'errors': [], 'pending_restart': True, 'pending_action': 'install',
        })

    return jsonify({"data": {"addons": entries}})


@addon_api_bp.route('/install', methods=['POST'], endpoint='install_addon_api')
@jwt_required()
def install_addon_api():
    """Install an addon package from an uploaded .zip.

    The addon is **not** live until QLSM restarts: Flask cannot unregister or
    hot-add a blueprint on a running app, and pretending otherwise would give
    the operator an addon that is listed but whose endpoints 404. The catalog
    marks it `pending_restart` instead, and the UI says so.
    """
    from ui.addons.install import AddonInstallError, install_addon_zip

    upload = request.files.get('file')
    if upload is None:
        return jsonify({"error": {"message": "No file uploaded (field name: 'file')."}}), 400

    packages_dir = current_app.config.get('ADDON_PACKAGES_DIR')
    if not packages_dir:
        return jsonify({"error": {"message": "ADDON_PACKAGES_DIR is not configured."}}), 500

    try:
        manifest = install_addon_zip(upload.read(), packages_dir)
    except RuntimeProviderConflict as e:
        return jsonify({"error": e.to_error()}), 409
    except AddonInstallError as e:
        return jsonify({"error": {"message": str(e)}}), 400
    except Exception as e:
        current_app.logger.error(f'Addon install failed: {e}', exc_info=True)
        return jsonify({"error": {"message": "Failed to install the addon."}}), 500

    current_app.logger.info(f'Addon "{manifest["id"]}" v{manifest["version"]} installed.')
    return jsonify({"data": {
        "id": manifest['id'],
        "name": manifest['name'],
        "version": manifest['version'],
        "pending_restart": True,
    }, "message": f'"{manifest["name"]}" installed. Restart QLSM to activate it.'}), 201


@addon_api_bp.route('/<addon_id>', methods=['DELETE'], endpoint='uninstall_addon_api')
@jwt_required()
def uninstall_addon_api(addon_id):
    """Remove an installed addon package.

    Refuses bundled addons: they live in the image, so deleting the directory
    would leave this container inconsistent and the addon would reappear on
    the next deploy anyway.

    AddonState rows are kept on purpose -- reinstalling the same addon should
    find its settings again. See addons/TRUST.md for what uninstalling does
    *not* undo.
    """
    from ui.addons.install import AddonInstallError, uninstall_addon

    addon = get_addon(addon_id)
    packages_dir = current_app.config.get('ADDON_PACKAGES_DIR')
    if not packages_dir:
        return jsonify({"error": {"message": "ADDON_PACKAGES_DIR is not configured."}}), 500

    try:
        if addon is not None and addon.source == 'bundled':
            with provider_lifecycle_lock(addon_id, packages_dir):
                check_provider_dependencies(addon_id, 'uninstall')
            return jsonify({"error": {
                "message": "This addon ships with QLSM and cannot be uninstalled."
            }}), 400
        removed = uninstall_addon(addon_id, packages_dir)
    except RuntimeProviderConflict as e:
        return jsonify({"error": e.to_error()}), 409
    except AddonInstallError as e:
        return jsonify({"error": {"message": str(e)}}), 400

    if not removed:
        return jsonify({"error": {"message": f'Addon "{addon_id}" is not installed.'}}), 404

    current_app.logger.info(f'Addon "{addon_id}" uninstalled.')
    return jsonify({"data": {"id": addon_id, "pending_restart": True},
                    "message": f'"{addon_id}" removed. Restart QLSM to unload it.'})


@addon_api_bp.route('/<addon_id>/state', methods=['GET'], endpoint='get_addon_state_api')
@jwt_required()
def get_addon_state_api(addon_id):
    addon, error = _resolve(addon_id)
    if error:
        return error
    scope, scope_id, error = _scope_args()
    if error:
        return error
    settings = addon.ctx.settings
    return jsonify({"data": {
        "addon_id": addon_id,
        "scope": scope,
        "scope_id": scope_id,
        # `enabled` is this layer's own switch; `effective` is it after the
        # layers above are taken into account. The UI needs both to render
        # "on, but blocked by host" rather than a misleading single toggle.
        "enabled": settings.is_layer_enabled(scope, scope_id),
        "effective": settings.is_enabled(scope, scope_id),
        "settings": settings.get(scope, scope_id),
        "schema": settings.fields(scope),
    }})


@addon_api_bp.route('/<addon_id>/state', methods=['PUT'], endpoint='update_addon_state_api')
@jwt_required()
def update_addon_state_api(addon_id):
    addon, error = _resolve(addon_id)
    if error:
        return error
    body = request.get_json(silent=True) or {}
    settings = addon.ctx.settings
    try:
        lock_provider_state(addon_id)
        scope, scope_id, error = _scope_args()
        if error:
            db.session.rollback()
            return error
        if 'settings' in body:
            settings.set(scope, scope_id, body['settings'], commit=False)
        if 'enabled' in body:
            settings.set_enabled(scope, scope_id, bool(body['enabled']), commit=False)
        db.session.commit()
    except RuntimeProviderConflict as e:
        db.session.rollback()
        return jsonify({"error": e.to_error()}), 409
    except AddonSettingsError as e:
        db.session.rollback()
        return jsonify({"error": {"message": str(e)}}), 400
    except Exception:
        db.session.rollback()
        # Database exceptions may include the submitted settings as SQL parameters.
        current_app.logger.error('Addon %s state update failed.', addon_id)
        return jsonify({"error": {"message": 'Failed to update addon state'}}), 500

    return jsonify({"data": {
        "addon_id": addon_id,
        "scope": scope,
        "scope_id": scope_id,
        "effective": settings.is_enabled(scope, scope_id),
        "settings": settings.get(scope, scope_id),
    }})


@addon_api_bp.route('/<addon_id>/ui/<path:filename>', methods=['GET'], endpoint='get_addon_ui_asset_api')
@jwt_required()
def get_addon_ui_asset_api(addon_id, filename):
    """Serve a tier-2 component or an icon from the addon's own ui/ directory.

    Only .js/.css/.map/.svg/.png/.webp are served: the addon directory also
    holds backend.py, playbooks and assets, and this route must never become
    a way to read them over HTTP. The path is resolved and re-checked against
    the ui/ root, so a traversal attempt fails even if Flask's own converter
    ever changes.
    """
    addon, error = _resolve(addon_id)
    if error:
        return error
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _CODE_EXTENSIONS and ext not in _IMAGE_EXTENSIONS:
        return jsonify({"error": {"message": 'Only .js, .css, .map, .svg, .png and .webp assets are served'}}), 403

    ui_root = os.path.abspath(addon.ctx.ui_dir)
    target = os.path.abspath(os.path.join(ui_root, filename))
    if target != ui_root and not target.startswith(ui_root + os.sep):
        return jsonify({"error": {"message": 'Invalid asset path'}}), 400
    if not os.path.isfile(target):
        return jsonify({"error": {"message": 'Asset not found'}}), 404

    response = send_file(target)
    if ext == '.svg':
        # An SVG can carry a <script>; it is served from the same origin as
        # the rest of the app, so it must not be allowed to run one or load
        # styles from elsewhere.
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'"
    return response
