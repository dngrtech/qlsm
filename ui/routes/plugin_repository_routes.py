import datetime
import json
import os

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required

from ui import db
from ui.models import PluginRepository
from ui.addons.runtime_protection import RuntimeProviderConflict
from ui.plugin_pool import resolve_pool_file
from ui.plugin_push import push_pool_to_hosts
from ui.plugin_repositories import (
    PLUGIN_FILE_MAX_SIZE,
    STATUS_UP_TO_DATE,
    PluginRepositoryError,
    addon_update_status,
    build_inline_manifest,
    download_addon,
    download_plugin,
    expand_with_dependencies,
    fetch_manifest,
    fetch_plugin_source,
    github_raw_bases,
    is_safe_plugin_filename,
    plugin_update_status,
    plugin_update_status_with_dependencies,
    resolve_manifest_source,
    version_risk,
)
from ui.runtime import is_valid_runtime, normalize_runtime

plugin_repository_api_bp = Blueprint('plugin_repository_routes', __name__)


def _validate_name(name):
    if not isinstance(name, str):
        return None, 'Name is required.'
    name = name.strip()
    if not name:
        return None, 'Name is required.'
    if len(name) > 100:
        return None, 'Name must be at most 100 characters.'
    return name, None


def _validate_url(url):
    if not isinstance(url, str):
        return None, 'URL is required.'
    url = url.strip()
    if not url:
        return None, 'URL must start with http:// or https://.'
    if len(url) > 500:
        return None, 'URL must be at most 500 characters.'
    if not (url.startswith('http://') or url.startswith('https://')):
        return None, 'URL must start with http:// or https://.'
    return url, None


def _repo_urls(repo):
    """Both addresses a repository answers to: what qlsm fetches, and what
    the operator typed if that was rewritten."""
    return {u.rstrip('/') for u in (repo.url, repo.display_url) if u}


def _resolve_runtime(entry, picked):
    """The pool a repo file belongs to: the runtime its manifest entry
    declares, else the operator's pick, else None. Download and diff both go
    through here, so they can never compare against a different pool than
    the one a download writes to."""
    declared = (entry or {}).get('runtime')
    if is_valid_runtime(declared):
        return normalize_runtime(declared)
    if is_valid_runtime(picked):
        return normalize_runtime(picked)
    return None


def _sync(repo, resolve=False):
    """Fetch the manifest, annotate each entry with its version risk, and
    persist the result. Returns (ok, error_message).

    `resolve` is for the first sync of a newly added repository: the operator
    may have typed a github.com repo URL, which has to be resolved to a raw
    base (and a branch found) before anything can be fetched. Later syncs go
    straight to the resolved `repo.url`.
    """
    try:
        if resolve:
            repo.url, manifest = resolve_manifest_source(repo.url, fetch_manifest)
        else:
            manifest = fetch_manifest(repo.url)
    except PluginRepositoryError as e:
        repo.last_sync_error = str(e)
        return False, str(e)

    for entry in manifest['plugins'] + manifest['addons']:
        entry['version_risk'] = version_risk(entry.get('requires_qlsm_version'))

    repo.manifest_json = json.dumps(manifest)
    repo.last_synced_at = datetime.datetime.utcnow()
    repo.last_sync_error = None
    return True, None


@plugin_repository_api_bp.route('/', methods=['GET'])
@jwt_required()
def list_plugin_repositories():
    repos = PluginRepository.query.order_by(PluginRepository.name).all()
    return jsonify({'data': [r.to_dict() for r in repos]}), 200


@plugin_repository_api_bp.route('/', methods=['POST'])
@jwt_required()
def create_plugin_repository():
    """Add a repository and sync it immediately, so the operator sees its
    plugin list (or the reason it failed) without a second action."""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': 'Request body must be JSON.'}}), 400

    name, name_error = _validate_name(data.get('name', ''))
    if name_error:
        return jsonify({'error': {'message': name_error}}), 400

    url, url_error = _validate_url(data.get('url', ''))
    if url_error:
        return jsonify({'error': {'message': url_error}}), 400

    # Names compare case-insensitively and URLs ignore a trailing slash, so
    # 'Test' vs 'test' or '.../repo' vs '.../repo/' don't add a second card
    # for the same repository.
    existing = PluginRepository.query.all()
    if any(r.name.lower() == name.lower() for r in existing):
        return jsonify({'error': {'message': f"Repository '{name}' already exists."}}), 409
    same_url = next((r for r in existing if url.rstrip('/') in _repo_urls(r)), None)
    if same_url:
        return jsonify({'error': {'message': f"This URL is already added as '{same_url.name}'."}}), 409

    repo = PluginRepository(name=name, url=url)
    _sync(repo, resolve=True)
    # Only worth keeping when resolution actually rewrote it (a github.com
    # URL -> its raw base); otherwise the card would repeat the same string.
    repo.display_url = url if repo.url != url else None

    try:
        db.session.add(repo)
        db.session.commit()
        current_app.logger.info(f"Plugin repository '{name}' ({url}) added.")
        return jsonify({'data': repo.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating plugin repository '{name}': {e}")
        return jsonify({'error': {'message': 'Failed to create repository.'}}), 500


@plugin_repository_api_bp.route('/<int:repo_id>/sync', methods=['POST'])
@jwt_required()
def sync_plugin_repository(repo_id):
    """Re-fetch the manifest for an existing repository."""
    repo = db.session.get(PluginRepository, repo_id)
    if not repo:
        return jsonify({'error': {'message': 'Repository not found.'}}), 404

    # A repository whose very first sync failed still holds the github.com URL
    # the operator typed -- resolution happens inside _sync(resolve=True) and
    # never ran. Syncing that URL fetches GitHub's HTML 404 forever, so retry
    # the resolution here instead of leaving the repo permanently unsyncable.
    original_url = repo.url
    needs_resolve = bool(github_raw_bases(repo.url))
    ok, error = _sync(repo, resolve=needs_resolve)
    if needs_resolve and ok and repo.url != original_url:
        repo.display_url = original_url
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving sync result for repository {repo_id}: {e}")
        return jsonify({'error': {'message': 'Failed to save sync result.'}}), 500

    # Never 502/504 here or below: Cloudflare replaces those bodies with its
    # own error page, so the operator would never see why a fetch failed.
    if not ok:
        return jsonify({'error': {'message': error}, 'data': repo.to_dict()}), 422
    return jsonify({'data': repo.to_dict()}), 200


@plugin_repository_api_bp.route('/<int:repo_id>', methods=['DELETE'])
@jwt_required()
def delete_plugin_repository(repo_id):
    repo = db.session.get(PluginRepository, repo_id)
    if not repo:
        return jsonify({'error': {'message': 'Repository not found.'}}), 404

    try:
        name = repo.name
        db.session.delete(repo)
        db.session.commit()
        current_app.logger.info(f"Plugin repository '{name}' deleted.")
        return jsonify({'message': f"Repository '{name}' deleted."}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting plugin repository {repo_id}: {e}")
        return jsonify({'error': {'message': 'Failed to delete repository.'}}), 500


@plugin_repository_api_bp.route('/<int:repo_id>/download', methods=['POST'])
@jwt_required()
def download_plugin_repository_plugins(repo_id):
    """Download the operator's selected filenames from this repo into the
    local pool. Each entry in `filenames` needs a `runtime` to resolve which
    pool it lands in -- the manifest's own declared runtime (looked up from
    the last synced list) when it has one, else the operator's pick for that
    file in `runtimes` ({filename: runtime}), since a repo entry may leave
    `runtime` unset. A pick never overrides a declared runtime.

    The repo manifest is re-fetched once per request so each plugin's inline
    metadata (label/description/cvars/commands) matches the file downloaded;
    that fresh list feeds metadata only, and a plugin missing from it (or a
    failed fetch) falls back to the last-synced entry.

    A selected plugin brings its declared `depends_on` helpers along
    automatically (transitively, dependencies written first), because those
    are files a plugin is made of rather than things to pick: the UI does not
    even list them. A helper with no runtime of its own inherits the runtime
    of whatever pulled it in -- it has to land in the same pool to be
    importable at all. An auto-added helper already in the pool at this
    repository's own version is skipped rather than raised as an overwrite
    conflict: nothing would change, and making the operator confirm an
    overwrite for a file they never picked is noise.

    `overwrite: true` in the body is required to replace a pool file that
    already exists -- see download_plugin().

    When at least one file landed, every ACTIVE host of that file's runtime
    gets a common-pool refresh job queued (`push` in the response lists
    queued and skipped hosts). `auto_added` and `skipped` in the response say
    which helpers came along and which needed nothing."""
    repo = db.session.get(PluginRepository, repo_id)
    if not repo:
        return jsonify({'error': {'message': 'Repository not found.'}}), 404

    data = request.get_json()
    if not data or not isinstance(data.get('filenames'), list) or not data['filenames']:
        return jsonify({'error': {'message': 'filenames must be a non-empty list of strings.'}}), 400

    picked_runtimes = data.get('runtimes') or {}
    if not isinstance(picked_runtimes, dict):
        return jsonify({'error': {'message': 'runtimes must be an object of filename -> runtime.'}}), 400
    for picked in picked_runtimes.values():
        if not is_valid_runtime(picked):
            return jsonify({'error': {'message': f"Unknown runtime: {picked!r}"}}), 400

    overwrite = bool(data.get('overwrite'))

    plugins = repo.to_dict()['plugins']
    known_by_filename = {entry['filename']: entry for entry in plugins}

    # Re-read the repo manifest so the cvars written next to each .py match
    # the .py being downloaded right now, not whatever the last sync saw.
    # Metadata only: runtime resolution stays on the stored entry above (the
    # list the UI showed and the operator acted on). Not persisted -- _sync()
    # stays the one writer of manifest_json.
    try:
        fresh_by_filename = {fresh['filename']: fresh for fresh in fetch_manifest(repo.url)['plugins']}
    except PluginRepositoryError:
        fresh_by_filename = {}

    downloaded, errors, skipped = [], [], []
    downloaded_runtimes = set()
    selected = []
    for filename in data['filenames']:
        if isinstance(filename, str):
            selected.append(filename)
        else:
            errors.append({'filename': filename, 'error': 'Not a string.'})

    ordered, pulled_by = expand_with_dependencies(plugins, selected)

    def runtime_for(filename):
        """A file's own runtime, else the one its puller resolved to -- a
        helper has to land in the same pool as the plugin importing it."""
        seen = set()
        while filename and filename not in seen:
            seen.add(filename)
            runtime = _resolve_runtime(known_by_filename.get(filename),
                                      picked_runtimes.get(filename))
            if runtime is not None:
                return runtime
            filename = pulled_by.get(filename)
        return None

    for filename in ordered:
        entry = known_by_filename.get(filename)
        runtime = runtime_for(filename)
        if runtime is None:
            errors.append({
                'filename': filename,
                'error': 'No runtime declared for this plugin. Pick one for it before downloading.',
            })
            continue
        if filename in pulled_by and plugin_update_status(entry) == STATUS_UP_TO_DATE:
            skipped.append(filename)
            continue
        source_entry = fresh_by_filename.get(filename) or entry
        try:
            download_plugin(
                repo.url, filename, runtime, overwrite=overwrite,
                inline_manifest=build_inline_manifest(source_entry),
                package_files=(source_entry or {}).get('package_files') or {},
            )
            downloaded.append(filename)
            downloaded_runtimes.add(runtime)
        except PluginRepositoryError as e:
            errors.append({'filename': filename, 'error': str(e), 'code': e.code})

    # This is the one route that writes remote executable Python into the pool,
    # which ansible then ships to every host -- so record what landed, from
    # where, and whether it replaced a file that was already there.
    if downloaded:
        current_app.logger.info(
            f"Downloaded {len(downloaded)} plugin(s) from repository '{repo.name}' ({repo.url}) "
            f"into the local pool (overwrite={overwrite}): {', '.join(downloaded)}"
        )

    body = {
        'downloaded': downloaded,
        'errors': errors,
        'auto_added': sorted(pulled_by),
        'skipped': skipped,
    }
    if downloaded:
        # A file in the pool is invisible to a host until its common pool is
        # refreshed, so push right away to every ACTIVE host of that runtime.
        # Hosts that can't take the job now come back as skipped; the UI
        # tells the operator to run Check for Updates on those later.
        body['push'] = push_pool_to_hosts(downloaded_runtimes)
        status = 207 if errors else 200
    elif not errors:
        # Guard, not a real path: a picked file is never skipped, so something
        # always downloads or errors. Without this, `all([])` below would turn
        # an empty error list into a 409 overwrite prompt with nothing in it.
        status = 200
    elif all(e.get('code') == 'exists' for e in errors):
        status = 409  # the UI turns this body into an overwrite prompt
    else:
        status = 422
    return jsonify(body), status


@plugin_repository_api_bp.route('/<int:repo_id>/diff', methods=['GET'])
@jwt_required()
def diff_plugin_repository_plugin(repo_id):
    """Local pool copy vs. repository copy of one plugin, for the overwrite
    prompt's Diff window. Read-only. Never 502: Cloudflare replaces those
    bodies with its own page, hiding the reason."""
    repo = db.session.get(PluginRepository, repo_id)
    if not repo:
        return jsonify({'error': {'message': 'Repository not found.'}}), 404

    filename = (request.args.get('filename') or '').strip()
    if not is_safe_plugin_filename(filename):
        return jsonify({'error': {'message': f"Refusing to diff unsafe filename: {filename!r}"}}), 400

    # Same check and message as the download route, so a malformed pick is
    # reported as unknown rather than as "no runtime declared".
    picked = request.args.get('runtime') or None
    if picked is not None and not is_valid_runtime(picked):
        return jsonify({'error': {'message': f"Unknown runtime: {picked!r}"}}), 400

    entry = next((p for p in repo.to_dict()['plugins'] if p['filename'] == filename), None)
    runtime = _resolve_runtime(entry, picked)
    if runtime is None:
        return jsonify({'error': {'message': 'No runtime declared for this plugin. Pick one for it first.'}}), 400

    local_path = resolve_pool_file(runtime, filename)
    if local_path is None:
        return jsonify({'error': {'message': f"{filename} is not in the local pool."}}), 404
    # The file can vanish between isfile() and the read (an overwrite download
    # in another tab, a pool sync) or be unreadable; both are "not in the pool"
    # to the caller, never a 500.
    try:
        if os.path.getsize(local_path) > PLUGIN_FILE_MAX_SIZE:
            return jsonify({'error': {'message': (
                f"{filename} in the local pool is larger than the {PLUGIN_FILE_MAX_SIZE} byte limit"
            )}}), 422
        with open(local_path, 'rb') as f:
            local = f.read()
    except OSError:
        return jsonify({'error': {'message': f"{filename} is not in the local pool."}}), 404

    try:
        remote = fetch_plugin_source(repo.url, filename)
    except PluginRepositoryError as e:
        return jsonify({'error': {'message': str(e)}}), 422

    return jsonify({'data': {
        'filename': filename,
        'runtime': runtime,
        'local': local.decode('utf-8', errors='replace'),
        'remote': remote.decode('utf-8', errors='replace'),
    }}), 200


@plugin_repository_api_bp.route('/<int:repo_id>/install-addon', methods=['POST'])
@jwt_required()
def install_plugin_repository_addon(repo_id):
    """Download one addon .zip this repo's manifest declares and install it
    via the standard installer -- installing over an existing copy is the
    update path (atomic replace with rollback). Same restart contract as the
    upload route: the addon is pending_restart, not live. Never 502: see the
    Cloudflare note on the sync route."""
    repo = db.session.get(PluginRepository, repo_id)
    if not repo:
        return jsonify({'error': {'message': 'Repository not found.'}}), 404

    data = request.get_json()
    addon_id = (data or {}).get('id')
    if not isinstance(addon_id, str) or not addon_id.strip():
        return jsonify({'error': {'message': 'id must be a non-empty string.'}}), 400

    entry = next((a for a in repo.to_dict()['addons'] if a.get('id') == addon_id), None)
    if entry is None:
        return jsonify({'error': {'message': f'Addon "{addon_id}" is not in this repository\'s manifest.'}}), 404

    packages_dir = current_app.config.get('ADDON_PACKAGES_DIR')
    if not packages_dir:
        return jsonify({'error': {'message': 'ADDON_PACKAGES_DIR is not configured.'}}), 500

    try:
        manifest = download_addon(repo.url, entry, packages_dir)
    except RuntimeProviderConflict as e:
        return jsonify({'error': e.to_error()}), 409
    except PluginRepositoryError as e:
        return jsonify({'error': {'message': str(e)}}), 422

    # This route writes remote code onto the addon volume -- record what
    # landed and from where, same as the plugin download route does.
    current_app.logger.info(
        f'Addon "{manifest["id"]}" v{manifest["version"]} installed from repository "{repo.name}" ({repo.url}).')
    return jsonify({'data': {
        'id': manifest['id'],
        'name': manifest['name'],
        'version': manifest['version'],
        'pending_restart': True,
    }, 'message': f'"{manifest["name"]}" installed. Restart QLSM to activate it.'}), 201


@plugin_repository_api_bp.route('/updates', methods=['GET'])
@jwt_required()
def plugin_repository_updates():
    """Update status of every synced manifest entry against what's installed
    locally. Purely local (pool hashes, installed addon manifests) -- no
    network; "Sync" is what refreshes the remote side of the comparison.

    A plugin's status folds in its `depends_on` helpers, which have no row of
    their own to show a badge on -- see
    plugin_update_status_with_dependencies()."""
    packages_dir = current_app.config.get('ADDON_PACKAGES_DIR')
    payload = []
    for repo in PluginRepository.query.order_by(PluginRepository.name).all():
        cached = repo.to_dict()
        payload.append({
            'repo_id': repo.id,
            'plugins': [{
                'filename': entry['filename'],
                'runtime': entry.get('runtime'),
                'status': plugin_update_status_with_dependencies(cached['plugins'], entry),
            } for entry in cached['plugins']],
            'addons': [addon_update_status(entry, packages_dir) for entry in cached['addons']],
        })
    return jsonify({'data': payload}), 200
