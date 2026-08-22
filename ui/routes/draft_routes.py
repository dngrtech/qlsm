"""
Draft workspace API routes for plugin file management.

Provides server-side staging for plugin files during instance/preset editing.
Drafts live in /tmp/qlds-drafts/<uuid>/scripts/ and are ephemeral.
"""

import os
import shutil
import time
import uuid
import sqlalchemy
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
from ui import db
from ui.database import get_host_by_name, get_preset_by_name
from ui.models import BinaryMetadata
from ui.plugin_compat import VERDICT_COMPATIBLE, baseline_digest, classify
from ui.preset_compat import baseline_hashes, replacement_scripts
from ui.preset_support import (
    BUILTIN_PRESETS_DIR,
    DEFAULT_PRESET_NAME,
    default_preset_name_for_preset,
    default_preset_name_for_runtime,
    resolve_preset_subdir,
)
from ui.runtime import is_valid_runtime, normalize_runtime
from ui.font_files import FONT_EXTENSIONS, MAX_FONT_FILE_SIZE, validate_font_content

draft_api_bp = Blueprint('draft_api_routes', __name__)

DRAFTS_BASE = '/tmp/qlds-drafts'
DRAFT_TTL_SECONDS = 3600  # 1 hour
CONFIGS_BASE = 'configs'
PRESETS_DIR = 'presets'
SCRIPTS_DIR = 'scripts'
USER_HOOKS_DIR = 'user-hooks'
# Written beside scripts/ when the compatibility gate actually filtered this
# draft, naming the runtime it was filtered FOR. A filtered draft is a derived
# artefact -- it holds the target runtime's plugin set, not the source's -- so
# any caller about to write it back somewhere permanent has to be able to ask.
# Deliberately outside scripts/ and user-hooks/: those two are the only
# directories copied onto an instance or a preset, so the marker can never
# travel with the files it describes.
RUNTIME_MARKER_FILE = '.qlsm-filtered-for-runtime'


def _get_drafts_base():
    """Return the drafts base directory, overridable via app config for testing."""
    return current_app.config.get('DRAFTS_BASE', DRAFTS_BASE)


def _get_draft_scripts_path(draft_id):
    """Return the scripts directory path for a draft."""
    return os.path.join(_get_drafts_base(), draft_id, SCRIPTS_DIR)


def _get_draft_user_hooks_path(draft_id):
    """Return the user-hooks directory path for a draft."""
    return os.path.join(_get_drafts_base(), draft_id, USER_HOOKS_DIR)


def _get_draft_base_path(draft_id):
    """Return the base directory path for a draft."""
    return os.path.join(_get_drafts_base(), draft_id)


def _validate_draft_id(draft_id):
    """Validate that a draft_id is a valid UUID4."""
    try:
        uuid.UUID(draft_id, version=4)
        return True
    except ValueError:
        return False


def _draft_exists(draft_id):
    """Check if a draft directory exists."""
    return os.path.exists(_get_draft_base_path(draft_id))


def _cleanup_stale_drafts():
    """Remove draft directories older than DRAFT_TTL_SECONDS."""
    drafts_base = _get_drafts_base()
    if not os.path.exists(drafts_base):
        return
    now = time.time()
    try:
        for entry in os.listdir(drafts_base):
            draft_path = os.path.join(drafts_base, entry)
            if not os.path.isdir(draft_path):
                continue
            try:
                mtime = os.path.getmtime(draft_path)
                if now - mtime > DRAFT_TTL_SECONDS:
                    shutil.rmtree(draft_path, ignore_errors=True)
                    current_app.logger.info(f"Cleaned up stale draft: {entry}")
            except OSError:
                continue
    except OSError:
        pass


# What `source_runtime` is when the preset/host row could not be read at all.
# normalize_runtime() answers 'minqlx' for None, which is the right convention
# for reading a legacy runtime column but the wrong one for deciding whether to
# DELETE an operator's plugins: it makes "the row says minqlx" and "there is no
# row" indistinguishable, so an unknown source drives a real strip against a
# minqlxtended target. A distinct sentinel keeps the None convention intact for
# every other caller while letting create_draft say "I could not tell", and the
# filter declines to run rather than guessing in the deleting direction.
UNRESOLVED_RUNTIME = object()


def _record_filter_runtime(draft_base_path, target_runtime):
    """Mark the draft rooted at `draft_base_path` as filtered for a runtime.

    Best-effort: the marker exists so a later save can refuse to corrupt a
    preset, and failing to write it must never fail the draft creation the
    operator is waiting on. A missing marker reads as "not filtered", which
    only costs the refusal -- the behaviour QLSM had before it existed.
    """
    try:
        with open(os.path.join(draft_base_path, RUNTIME_MARKER_FILE),
                  'w', encoding='utf-8') as handle:
            handle.write(target_runtime)
    except OSError:
        pass


def draft_filtered_runtime(draft_id):
    """The runtime `draft_id`'s scripts were filtered for, or None.

    None means the draft was never filtered (a matched-runtime load, or no
    target runtime at all), so its scripts are the source's own files and
    writing them back where they came from is safe.
    """
    path = os.path.join(_get_draft_base_path(draft_id), RUNTIME_MARKER_FILE)
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            value = handle.read().strip()
    except (OSError, ValueError):
        return None
    return value if is_valid_runtime(value) else None


def _target_default_preset_files(target_runtime):
    """relpath -> file text for every .py the target runtime ships itself.

    Text rather than a digest because this map now has two jobs: recognising a file as
    the target's own (compare digests), and RESTORING one the source overlay wrote over
    (write the text back). See the subdirectory branch in _apply_runtime_filter.

    `_seed_draft` copies the TARGET runtime's own builtin default preset in
    before overlaying the source preset, so most of what the filter then walks
    is the target's own shipped baseline rather than anything the operator
    chose. 13 of those files have drifted from the ql-assets manifest, so they
    miss the hash allow-list, fall through to the scanner, land `unknown` and
    get deleted -- and the dialog cannot even list them, because it is computed
    from the SOURCE preset's files. A file that IS the target's own shipped
    baseline is never something the target cannot run.

    Keyed by relative path rather than by basename: extras/textart.py and a
    root-level textart.py are different files, and this map exists to prove a
    file IS the shipped one, not that it happens to share a name with it.

    Resolved through BUILTIN_PRESETS_DIR, the same way replacement_scripts()
    a few lines down resolves the very same directory, rather than through
    resolve_preset_subdir(): the DB-backed lookup answers with a path that does
    not exist whenever the builtin preset rows are absent, and a silently empty
    map here would put the over-strip straight back.
    """
    directory = os.path.join(
        BUILTIN_PRESETS_DIR,
        default_preset_name_for_runtime(target_runtime),
        SCRIPTS_DIR,
    )
    files = {}
    for root, _dirs, filenames in os.walk(directory):
        for filename in filenames:
            if not filename.lower().endswith('.py'):
                continue
            full_path = os.path.join(root, filename)
            try:
                with open(full_path, 'r', encoding='utf-8') as handle:
                    text = handle.read()
            except (OSError, ValueError):
                continue
            files[os.path.relpath(full_path, directory)] = text
    return files


def _apply_runtime_filter(draft_scripts_path, source_runtime, target_runtime, accepted_replacements):
    """Delete what cannot run on `target_runtime`; write accepted replacements.

    This is THE enforcement point for the compatibility gate. The preset GET
    response is filtered too, but only to drive the dialog's preview -- nothing
    consumes its `scripts` field. What lands on an instance is this directory,
    copied wholesale by instance_routes.py, so this is where stripping has to
    actually happen or the gate is decorative.

    Mirrors apply_compatibility()'s own early return line for line: a matched
    runtime must cost nothing and delete nothing, or the two halves of the
    gate -- what the operator is shown, and what actually lands on disk --
    can silently disagree, which is the exact failure class this rework
    exists to eliminate.

    Returns (relative paths removed, relative paths restored, the runtime filtered
    for). The third element is None when neither early return was taken -- this function's two
    guards are the only place that knows the difference between "filtered for
    minqlxtended" and "left alone", and re-deriving that condition at a second
    call site is how the two halves of this gate have already drifted apart
    twice. Callers that persist anything about the draft key off it.
    """
    if source_runtime is UNRESOLVED_RUNTIME:
        # See UNRESOLVED_RUNTIME: the source could not be identified, so
        # "the runtimes differ" is a guess, and this function's mistake costs
        # the operator files. Skipping keeps everything, which is the same
        # thing QLSM did before the gate existed.
        return [], [], None
    source = normalize_runtime(source_runtime)
    target = normalize_runtime(target_runtime)
    if source == target:
        return [], [], None

    hashes = baseline_hashes(target)
    candidates = replacement_scripts(target)
    shipped_by_target = _target_default_preset_files(target)
    shipped_digests = {rel: baseline_digest(text)
                       for rel, text in shipped_by_target.items()}
    removed = []
    restored = []

    for root, _dirs, filenames in os.walk(draft_scripts_path):
        for filename in filenames:
            if not filename.lower().endswith('.py'):
                continue  # .so hooks and .txt data are runtime-agnostic
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, draft_scripts_path)
            try:
                with open(full_path, 'r', encoding='utf-8') as handle:
                    text = handle.read()
            except (OSError, ValueError):
                # Unreadable, or not valid UTF-8 (ValueError covers
                # UnicodeDecodeError): _read_preset_scripts() on the GET path
                # hits this exact failure and silently omits the file from
                # what the operator is shown, instead of reporting it
                # stripped. Deleting a file the dialog never displayed as
                # incompatible would widen the strip past what was promised.
                continue
            if not text.strip():
                # An empty file (a bare __init__.py marking a package) cannot
                # be incompatible with anything, and removing it breaks
                # imports for every sibling module that did survive.
                continue
            if shipped_digests.get(rel_path) == baseline_digest(text):
                # This file is byte-for-byte the one the TARGET runtime's own
                # default preset ships at this path -- almost always because
                # _seed_draft laid it down itself moments ago. Deleting the
                # target's own baseline is never right, and the operator was
                # never shown it: the dialog lists the SOURCE preset's files.
                # Compared by content, not by name, so a source file that
                # merely reuses a shipped filename is still classified below.
                continue
            verdict, _reasons = classify(
                text, target, baseline_sha256=hashes.get(filename))
            if verdict == VERDICT_COMPATIBLE:
                continue
            if (os.sep in rel_path or '/' in rel_path) and rel_path in shipped_by_target:
                # A subdirectory file the TARGET runtime also ships at this exact path.
                # _seed_draft laid the target's copy down and the source overlay wrote
                # over it, so deleting now leaves nothing where the seed put something.
                #
                # Root-level files have a way out of that: _strip_entry offers the
                # target's version and the operator ticks it. Subdirectory files never
                # get the offer -- isEnableablePluginPath() rejects any path with a
                # separator, so they cannot appear in the dialog at all -- which left
                # mydiscordbot.py landing with an empty discord_extensions/ beside it
                # and failing at load_extension().
                #
                # Restoring is not the same act as offering a replacement, and the
                # reason _strip_entry declines to offer does not apply here: that
                # concern is about relocating a subdirectory file into the plugin root,
                # a path change. This writes the target's own file back to the path it
                # already occupied, which is what the seed did before the overlay.
                try:
                    with open(full_path, 'w', encoding='utf-8') as handle:
                        handle.write(shipped_by_target[rel_path])
                    restored.append(rel_path)
                except OSError:
                    pass
                continue
            try:
                os.remove(full_path)
                removed.append(rel_path)
            except OSError:
                continue

    for name in accepted_replacements or []:
        # Client-supplied. Membership in `candidates` is what actually stops
        # '../x.py' or any other traversal -- replacement_scripts() only ever
        # returns bare filenames read from a flat preset scripts/ directory,
        # so nothing containing a separator can pass this check in the first
        # place. The separator/suffix checks below are defence in depth, not
        # the live guard.
        if name not in candidates:
            continue
        if '/' in name or os.sep in name or not name.endswith('.py'):
            continue
        try:
            with open(os.path.join(draft_scripts_path, name), 'w',
                      encoding='utf-8') as handle:
                handle.write(candidates[name])
        except OSError:
            continue

    return removed, restored, target


def _seed_draft(draft_scripts_path, source_path, default_preset_name=DEFAULT_PRESET_NAME,
                target_runtime=None, accepted_replacements=None, source_runtime=None):
    """Copy source plugin files into a draft directory.

    For non-default presets, the runtime-matched default preset's scripts are
    copied first so the full plugin list is always visible.  Preset-specific
    files overlay on top.  This mirrors _read_preset_scripts() in
    preset_api_routes.py. `default_preset_name` is expected to already be
    chosen by the caller for the target's runtime when one is given.

    `target_runtime` and `source_runtime` together gate the compatibility
    filter at the end of this function: a matched runtime costs nothing and
    deletes nothing, same as `apply_compatibility()` on the GET side, and a
    `source_runtime` of UNRESOLVED_RUNTIME skips the filter outright.

    Returns the runtime the draft was filtered FOR, or None when it was left
    alone. A filtered draft is a derived artefact holding the target runtime's
    plugin set rather than the source's, so the caller that owns the draft
    directory records that before anything can write it back somewhere
    permanent.
    """
    default_scripts = os.path.abspath(
        resolve_preset_subdir(default_preset_name, SCRIPTS_DIR, CONFIGS_BASE)
    )
    presets_root = os.path.join(os.path.abspath(CONFIGS_BASE), PRESETS_DIR)
    is_non_default_preset = (
        source_path != default_scripts
        and _is_path_under(presets_root, source_path)
    )

    # Seed with default scripts first for non-default presets
    if is_non_default_preset and os.path.exists(default_scripts):
        shutil.copytree(default_scripts, draft_scripts_path, dirs_exist_ok=True)

    # Overlay source scripts (preset-specific or instance)
    if os.path.exists(source_path):
        shutil.copytree(source_path, draft_scripts_path, dirs_exist_ok=True)
    elif not os.path.exists(draft_scripts_path):
        os.makedirs(draft_scripts_path, exist_ok=True)

    # Seed user-hooks/ alongside scripts/ from the same source root
    source_root = os.path.dirname(source_path) if os.path.basename(source_path) == SCRIPTS_DIR else source_path
    source_user_hooks = os.path.join(source_root, USER_HOOKS_DIR)
    draft_user_hooks = os.path.join(os.path.dirname(draft_scripts_path), USER_HOOKS_DIR)
    if os.path.isdir(source_user_hooks):
        shutil.copytree(source_user_hooks, draft_user_hooks, dirs_exist_ok=True)
    elif not os.path.exists(draft_user_hooks):
        os.makedirs(draft_user_hooks, exist_ok=True)

    # Enforce the compatibility gate last, over everything seeded above -- the
    # default overlay and the source preset alike. Filtering the two copytree
    # calls separately would let an incompatible default overlay through.
    if not target_runtime:
        return None
    removed, restored, filtered_for = _apply_runtime_filter(
        draft_scripts_path, source_runtime, target_runtime,
        accepted_replacements)
    if removed:
        current_app.logger.info(
            f"Draft seeded for {target_runtime}: removed "
            f"{len(removed)} incompatible plugin(s): {', '.join(sorted(removed))}")
    if restored:
        # Logged separately from `removed` because it is a different outcome and the
        # operator was shown neither: these never reach the dialog. Silence here would
        # make an unexplained file swap look like the overlay never happened.
        current_app.logger.info(
            f"Draft seeded for {target_runtime}: restored "
            f"{len(restored)} subdirectory helper(s) the source overlay wrote over: "
            f"{', '.join(sorted(restored))}")
    return filtered_for


def _is_path_under(allowed_root, resolved_path):
    """Validate that resolved_path is strictly under allowed_root.

    Appends os.sep to avoid the startswith('configs') vs 'configs-evil'
    prefix-escape bug.
    """
    norm_root = os.path.normpath(allowed_root)
    norm_path = os.path.normpath(resolved_path)
    return norm_path.startswith(norm_root + os.sep)


def _is_safe_name(value):
    """Reject values that contain path separators or parent-directory refs.

    Host names, instance IDs, and preset names are simple identifiers —
    they must never contain '/', '\\', or '..' components.
    """
    if not value:
        return False
    return '/' not in value and '\\' not in value and '..' not in value


ALLOWED_EXTENSIONS = {'.py', '.txt', '.so'} | FONT_EXTENSIONS
FILE_TYPE_MAP = {'.py': 'python', '.txt': 'text', '.so': 'binary'}
FILE_TYPE_MAP.update({ext: 'font' for ext in FONT_EXTENSIONS})
VALID_BINARY_CONTEXT_TYPES = frozenset({'preset', 'instance'})
MAX_DRAFT_FOLDER_DEPTH = 3
MAX_DRAFT_FILE_DEPTH = 4


def _get_file_type(filename):
    """Return the file type category for a given filename."""
    ext = os.path.splitext(filename)[1].lower()
    return FILE_TYPE_MAP.get(ext)


def _build_draft_tree(path, base_path=None):
    """
    Recursively build a file tree with type metadata.

    Returns list of:
    - Files: { name, type: 'file', path, file_type, size, last_modified }
    - Folders: { name, type: 'folder', path, children }
    """
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

        if entry.startswith('.') or entry == '__pycache__':
            continue

        if os.path.isdir(full_path):
            children = _build_draft_tree(full_path, base_path)
            items.append({
                'name': entry,
                'type': 'folder',
                'path': relative_path,
                'children': children
            })
        elif os.path.isfile(full_path):
            ext = os.path.splitext(entry)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                stat = os.stat(full_path)
                items.append({
                    'name': entry,
                    'type': 'file',
                    'path': relative_path,
                    'file_type': FILE_TYPE_MAP.get(ext, 'unknown'),
                    'size': stat.st_size,
                    'last_modified': stat.st_mtime
                })

    return items


TEXT_EXTENSIONS = {'.py', '.txt'}
MAX_TEXT_FILE_SIZE = 256 * 1024      # 256KB for .py, .txt
MAX_BINARY_FILE_SIZE = 10 * 1024 * 1024  # 10MB for .so
ELF_MAGIC = b'\x7fELF'


def _is_safe_draft_path(draft_scripts_path, relative_path):
    """Validate that a relative path doesn't escape the draft directory."""
    root = os.path.realpath(draft_scripts_path)
    full_path = os.path.realpath(os.path.join(root, relative_path))
    try:
        return os.path.commonpath([root, full_path]) == root
    except ValueError:
        return False


def _normalize_draft_file_path(relative_path):
    """Return a canonical slash-separated draft path, or None if unsafe/ambiguous."""
    if not isinstance(relative_path, str):
        return None
    stripped = relative_path.strip().replace('\\', '/')
    if not stripped or os.path.isabs(stripped):
        return None
    parts = stripped.split('/')
    if len(parts) > MAX_DRAFT_FILE_DEPTH:
        return None
    if any(part in ('', '.', '..') for part in parts):
        return None
    return '/'.join(parts)


def _get_source_path(data):
    """Determine the source scripts path from request data. Returns None if invalid."""
    base = os.path.abspath(CONFIGS_BASE)
    source = data.get('source')

    if source == 'preset':
        preset = data.get('preset', 'default')
        if not _is_safe_name(preset):
            return None
        allowed_root = os.path.join(base, PRESETS_DIR)
        path = os.path.abspath(resolve_preset_subdir(preset, SCRIPTS_DIR, CONFIGS_BASE))
    elif source == 'instance':
        host = data.get('host')
        instance_id = data.get('instance_id')
        if not host or not instance_id:
            return None
        if not _is_safe_name(host) or not _is_safe_name(str(instance_id)):
            return None
        if host == PRESETS_DIR:
            return None
        allowed_root = os.path.join(base, host)
        path = os.path.join(base, host, str(instance_id), SCRIPTS_DIR)
    else:
        return None

    if not _is_path_under(allowed_root, path):
        return None
    return path


def _resolve_source_runtime(data):
    """The runtime of the content `_seed_draft` is about to copy from.

    Mirrors the values `apply_compatibility`'s caller already trusts for the
    GET-side comparison -- `preset.runtime`, a host's `runtime` column -- so
    the two halves of the gate agree on what "the source" is.

    Returns None when there is no row to read, which is NOT the same answer as
    a row whose runtime column is NULL: the caller turns None into
    UNRESOLVED_RUNTIME so the filter declines to delete on a guess. A row that
    exists but predates the runtime column still resolves to None here and gets
    the same treatment, which is the safe direction -- see UNRESOLVED_RUNTIME.
    """
    if data.get('source') == 'preset':
        preset = get_preset_by_name(data.get('preset')) if data.get('preset') else None
        return getattr(preset, 'runtime', None)
    if data.get('source') == 'instance':
        host = get_host_by_name(data.get('host')) if data.get('host') else None
        return getattr(host, 'runtime', None)
    return None


@draft_api_bp.route('/', methods=['POST'])
@jwt_required()
def create_draft():
    """Create a new draft workspace seeded from a preset or instance."""
    data = request.get_json()
    if not data or 'source' not in data:
        return jsonify({"error": {"message": "source is required (preset or instance)"}}), 400

    source_path = _get_source_path(data)
    if source_path is None:
        return jsonify({"error": {"message": "Invalid source. Provide preset name or host + instance_id."}}), 400

    target_runtime = data.get('target_runtime')
    if target_runtime is not None and not is_valid_runtime(target_runtime):
        return jsonify({"error": {"message": "Invalid target_runtime."}}), 400

    accepted = data.get('accepted_replacements')
    if accepted is not None and (
        not isinstance(accepted, list)
        or not all(isinstance(name, str) for name in accepted)
    ):
        return jsonify({"error": {"message": "accepted_replacements must be a list of strings."}}), 400

    _cleanup_stale_drafts()

    draft_id = str(uuid.uuid4())
    draft_scripts_path = _get_draft_scripts_path(draft_id)

    try:
        os.makedirs(os.path.dirname(draft_scripts_path), exist_ok=True)
        # The overlay follows the TARGET host's runtime, but only when it
        # actually differs from the source's -- mirroring apply_compatibility's
        # own preset==target early return. Using the target unconditionally is
        # what put minqlx defaults onto a minqlxtended host in the first place;
        # keying it on target_runtime alone (ignoring whether the source
        # already matches) reintroduces the same bug from the other side.
        source_runtime = _resolve_source_runtime(data) if target_runtime else None
        runtimes_differ = bool(target_runtime) and (
            normalize_runtime(source_runtime) != normalize_runtime(target_runtime)
        )
        if runtimes_differ:
            default_preset_name = default_preset_name_for_runtime(target_runtime)
        elif data.get('source') == 'preset':
            default_preset_name = default_preset_name_for_preset(data.get('preset'))
        else:
            default_preset_name = DEFAULT_PRESET_NAME
        # The overlay choice above may safely guess on an unresolvable source:
        # whichever default it picks, the operator gains files, never loses
        # them. The FILTER may not -- guessing there deletes plugins -- so it
        # is told explicitly that the source is unknown and skips.
        filtered_for = _seed_draft(
            draft_scripts_path, source_path, default_preset_name,
            target_runtime=target_runtime,
            accepted_replacements=accepted,
            source_runtime=(UNRESOLVED_RUNTIME if source_runtime is None
                            else source_runtime))
        if filtered_for:
            # Recorded here rather than inside the filter because this is the
            # only caller that owns a real draft root; _seed_draft is also
            # called with bare paths whose parent is not a draft directory.
            _record_filter_runtime(_get_draft_base_path(draft_id), filtered_for)
    except OSError as e:
        current_app.logger.error(f"Failed to create draft {draft_id}: {e}")
        return jsonify({"error": {"message": "Failed to create draft workspace"}}), 500

    current_app.logger.info(f"Created draft {draft_id} from {source_path}")
    return jsonify({"data": {"draft_id": draft_id}}), 201


@draft_api_bp.route('/<draft_id>', methods=['DELETE'])
@jwt_required()
def discard_draft(draft_id):
    """Discard a draft workspace and delete all its files."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400

    draft_path = _get_draft_base_path(draft_id)
    if not os.path.exists(draft_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    shutil.rmtree(draft_path, ignore_errors=True)
    current_app.logger.info(f"Discarded draft {draft_id}")
    return jsonify({"data": {"message": "Draft discarded"}}), 200


@draft_api_bp.route('/<draft_id>/touch', methods=['POST'])
@jwt_required()
def touch_draft(draft_id):
    """Update draft mtime to prevent cleanup during long editing sessions."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400

    draft_path = _get_draft_base_path(draft_id)
    if not os.path.exists(draft_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    os.utime(draft_path, None)  # Sets mtime to current time
    return jsonify({"data": {"message": "Draft touched"}}), 200


@draft_api_bp.route('/<draft_id>/tree', methods=['GET'])
@jwt_required()
def get_draft_tree(draft_id):
    """Return the file tree for a draft workspace with type metadata."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400

    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    scripts_path = _get_draft_scripts_path(draft_id)
    tree = _build_draft_tree(scripts_path)
    return jsonify({"data": tree}), 200


@draft_api_bp.route('/<draft_id>/content', methods=['GET'])
@jwt_required()
def get_draft_content(draft_id):
    """Read text content of a .py or .txt file from the draft."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    path = request.args.get('path')
    if not path:
        return jsonify({"error": {"message": "path parameter is required"}}), 400

    scripts_path = _get_draft_scripts_path(draft_id)
    if not _is_safe_draft_path(scripts_path, path):
        return jsonify({"error": {"message": "Invalid file path"}}), 400

    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXT_EXTENSIONS:
        return jsonify({"error": {"message": f"Cannot read {ext} files as text. Only .py and .txt are readable."}}), 400

    full_path = os.path.join(scripts_path, path)
    if not os.path.exists(full_path):
        return jsonify({"error": {"message": "File not found"}}), 404

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        return jsonify({"error": {"message": "File is not valid UTF-8 text"}}), 400

    return jsonify({"data": {"path": path, "content": content}}), 200


@draft_api_bp.route('/<draft_id>/file', methods=['GET'])
@jwt_required()
def download_draft_file(draft_id):
    """Download an allowed draft file without decoding or re-encoding it."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    path = _normalize_draft_file_path(request.args.get('path'))
    if path is None:
        return jsonify({"error": {"message": "Invalid file path"}}), 400
    if os.path.splitext(path)[1].lower() not in ALLOWED_EXTENSIONS:
        return jsonify({"error": {"message": "Unsupported file extension"}}), 400

    scripts_path = _get_draft_scripts_path(draft_id)
    full_path = os.path.realpath(os.path.join(scripts_path, *path.split('/')))
    if not _is_safe_draft_path(scripts_path, path):
        return jsonify({"error": {"message": "Invalid file path"}}), 400
    if not os.path.isfile(full_path):
        return jsonify({"error": {"message": "File not found"}}), 404

    return send_file(
        full_path,
        as_attachment=True,
        download_name=os.path.basename(path),
    )


@draft_api_bp.route('/<draft_id>/content', methods=['PUT'])
@jwt_required()
def save_draft_content(draft_id):
    """Write text content of a .py or .txt file to the draft."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    path = data.get('path')
    content = data.get('content')
    if not path or content is None:
        return jsonify({"error": {"message": "path and content are required"}}), 400

    scripts_path = _get_draft_scripts_path(draft_id)
    if not _is_safe_draft_path(scripts_path, path):
        return jsonify({"error": {"message": "Invalid file path"}}), 400
    if len(path.split('/')) > MAX_DRAFT_FILE_DEPTH:
        return jsonify({"error": {"message": f"Path too deep (max depth {MAX_DRAFT_FILE_DEPTH})"}}), 400

    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXT_EXTENSIONS:
        return jsonify({"error": {"message": f"Cannot write {ext} files as text. Only .py and .txt are writable."}}), 400

    if len(content.encode('utf-8')) > MAX_TEXT_FILE_SIZE:
        return jsonify({"error": {"message": f"Content exceeds maximum size of {MAX_TEXT_FILE_SIZE // 1024}KB"}}), 400

    full_path = os.path.join(scripts_path, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # Touch the draft directory to keep it alive
    os.utime(_get_draft_base_path(draft_id), None)

    return jsonify({"data": {"path": path, "message": "Content saved"}}), 200


def _get_max_size(ext):
    """Return the max file size for a given extension."""
    if ext == '.so':
        return MAX_BINARY_FILE_SIZE
    if ext in FONT_EXTENSIONS:
        return MAX_FONT_FILE_SIZE
    return MAX_TEXT_FILE_SIZE


@draft_api_bp.route('/<draft_id>/upload', methods=['POST'])
@jwt_required()
def upload_to_draft(draft_id):
    """Upload a file to the draft workspace. Supports .py, .txt, .so, and font files."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    if 'file' not in request.files:
        return jsonify({"error": {"message": "No file provided"}}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"error": {"message": "No filename"}}), 400

    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": {"message": (
            f"Unsupported extension {ext}. Allowed: .py, .txt, .so, or a font file "
            "(.ttf, .otf, .ttc, .otc, .woff, .woff2, .eot, .fon, .fnt, .pfb, .pfa, .pfm, .afm)"
        )}}), 400

    content = file.read()
    max_size = _get_max_size(ext)
    if len(content) > max_size:
        size_label = f"{max_size // (1024*1024)}MB" if max_size >= 1024*1024 else f"{max_size // 1024}KB"
        return jsonify({"error": {"message": f"File exceeds {size_label} size limit"}}), 400

    if ext == '.so':
        if len(content) < 4 or content[:4] != ELF_MAGIC:
            return jsonify({"error": {"message": "Invalid .so file: missing ELF header. Expected a compiled shared library."}}), 400
    elif ext in FONT_EXTENSIONS:
        font_error = validate_font_content(ext, content)
        if font_error:
            return jsonify({"error": {"message": font_error}}), 400

    target_path = request.form.get('target_path', '')
    scripts_path = _get_draft_scripts_path(draft_id)

    if target_path:
        dest_dir = os.path.join(scripts_path, target_path)
        if not _is_safe_draft_path(scripts_path, target_path):
            return jsonify({"error": {"message": "Invalid target path"}}), 400
    else:
        dest_dir = scripts_path

    full_relative_path = f"{target_path}/{filename}" if target_path else filename
    if len(full_relative_path.split('/')) > MAX_DRAFT_FILE_DEPTH:
        return jsonify({"error": {"message": f"Path too deep (max depth {MAX_DRAFT_FILE_DEPTH})"}}), 400

    os.makedirs(dest_dir, exist_ok=True)
    dest_file = os.path.join(dest_dir, filename)

    with open(dest_file, 'wb') as f:
        f.write(content)

    relative = os.path.relpath(dest_file, scripts_path)
    os.utime(_get_draft_base_path(draft_id), None)

    return jsonify({"data": {"path": relative, "message": f"Uploaded {filename}"}}), 200


@draft_api_bp.route('/<draft_id>/file', methods=['DELETE'])
@jwt_required()
def delete_draft_file(draft_id):
    """Delete a file from the draft workspace."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    path = request.args.get('path')
    if not path:
        return jsonify({"error": {"message": "path parameter is required"}}), 400

    scripts_path = _get_draft_scripts_path(draft_id)
    if not _is_safe_draft_path(scripts_path, path):
        return jsonify({"error": {"message": "Invalid file path"}}), 400

    full_path = os.path.join(scripts_path, path)
    if not os.path.exists(full_path):
        return jsonify({"error": {"message": "File not found"}}), 404

    os.remove(full_path)
    os.utime(_get_draft_base_path(draft_id), None)

    return jsonify({"data": {"message": f"Deleted {path}"}}), 200


@draft_api_bp.route('/<draft_id>/rename', methods=['PATCH'])
@jwt_required()
def rename_draft_file(draft_id):
    """Rename a file within the draft workspace."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    old_path = _normalize_draft_file_path(data.get('old_path'))
    new_path = _normalize_draft_file_path(data.get('new_path'))
    if old_path is None or new_path is None:
        return jsonify({"error": {"message": "old_path and new_path must be strings"}}), 400

    scripts_path = _get_draft_scripts_path(draft_id)
    if not (
        _is_safe_draft_path(scripts_path, old_path)
        and _is_safe_draft_path(scripts_path, new_path)
    ):
        return jsonify({"error": {"message": "Invalid file path"}}), 400

    root_path = os.path.normpath(scripts_path)
    old_full = os.path.normpath(os.path.join(scripts_path, old_path))
    new_full = os.path.normpath(os.path.join(scripts_path, new_path))
    if old_full == root_path or new_full == root_path:
        return jsonify({"error": {"message": "Path must reference a file"}}), 400
    if not os.path.isfile(old_full):
        return jsonify({"error": {"message": "old_path must reference an existing file"}}), 400

    old_ext = os.path.splitext(old_path)[1].lower()
    new_ext = os.path.splitext(new_path)[1].lower()
    if old_ext not in ALLOWED_EXTENSIONS or new_ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": {"message": "Unsupported file extension"}}), 400
    if old_ext != new_ext:
        return jsonify({"error": {"message": "Rename cannot change file extension"}}), 400
    if os.path.exists(new_full):
        return jsonify({"error": {"message": "File already exists at new_path"}}), 409
    new_parent = os.path.dirname(new_full)
    if not os.path.isdir(new_parent):
        return jsonify({"error": {"message": "new_path parent directory does not exist"}}), 400

    is_binary = old_ext == '.so'
    if is_binary:
        context_type = data.get('context_type')
        context_key = data.get('context_key')
        if not isinstance(context_type, str) or not isinstance(context_key, str):
            return jsonify({"error": {"message": "context_type and context_key must be strings"}}), 400
        context_type = context_type.strip()
        context_key = context_key.strip()
        error = _validate_binary_rename_context(context_type, context_key)
        if error:
            return jsonify({"error": {"message": error}}), 400
        if _binary_metadata_exists(context_type, context_key, new_path):
            return jsonify({"error": {"message": "Binary metadata already exists for new_path"}}), 409

    try:
        if is_binary:
            row = _get_binary_metadata(context_type, context_key, old_path)
            if row:
                row.file_path = new_path
                db.session.flush()
        os.rename(old_full, new_full)
        if is_binary:
            try:
                db.session.commit()
            except sqlalchemy.exc.SQLAlchemyError as e:
                db.session.rollback()
                try:
                    if os.path.exists(new_full) and not os.path.exists(old_full):
                        os.rename(new_full, old_full)
                except OSError as reverse_err:
                    current_app.logger.error(
                        f"Failed to reverse rename {new_path} to {old_path}: {reverse_err}"
                    )
                current_app.logger.error(f"Failed to commit binary metadata rename: {e}")
                return jsonify({"error": {"message": "Rename failed"}}), 500
    except (OSError, sqlalchemy.exc.SQLAlchemyError) as e:
        if is_binary:
            db.session.rollback()
        current_app.logger.error(f"Failed to rename {old_path} to {new_path}: {e}")
        return jsonify({"error": {"message": "Rename failed"}}), 500

    os.utime(_get_draft_base_path(draft_id), None)
    return jsonify({"data": {"old_path": old_path, "new_path": new_path}}), 200


def _validate_binary_rename_context(context_type, context_key):
    if not context_type or not context_key:
        return "context_type and context_key are required for .so rename"
    if context_type not in VALID_BINARY_CONTEXT_TYPES:
        return "context_type must be 'preset' or 'instance'"
    if '/' in context_key or '\\' in context_key or '..' in context_key:
        return "Invalid context_key"
    return None


def _get_binary_metadata(context_type, context_key, file_path):
    return BinaryMetadata.query.filter_by(
        context_type=context_type,
        context_key=context_key,
        file_path=file_path,
    ).first()


def _binary_metadata_exists(context_type, context_key, file_path):
    return _get_binary_metadata(context_type, context_key, file_path) is not None


def _get_commit_target_path(data):
    """Determine the target scripts directory for a commit. Returns None if invalid."""
    base = os.path.abspath(CONFIGS_BASE)
    target = data.get('target')

    if target == 'instance':
        host = data.get('host')
        instance_id = data.get('instance_id')
        if not host or not instance_id:
            return None
        if not _is_safe_name(host) or not _is_safe_name(str(instance_id)):
            return None
        if not str(instance_id).isdigit():
            return None
        if host == PRESETS_DIR:
            return None
        allowed_root = os.path.join(base, host)
        path = os.path.join(base, host, str(instance_id), SCRIPTS_DIR)
    elif target == 'preset':
        preset = data.get('preset')
        if not preset:
            return None
        if not _is_safe_name(preset):
            return None
        allowed_root = os.path.join(base, PRESETS_DIR)
        path = os.path.abspath(resolve_preset_subdir(preset, SCRIPTS_DIR, CONFIGS_BASE))
    else:
        return None

    if not _is_path_under(allowed_root, path):
        return None
    return path


@draft_api_bp.route('/<draft_id>/commit', methods=['POST'])
@jwt_required()
def commit_draft(draft_id):
    """Commit draft contents to an instance or preset directory, then delete the draft."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    data = request.get_json()
    if not data or 'target' not in data:
        return jsonify({"error": {"message": "target is required (instance or preset)"}}), 400

    target_path = _get_commit_target_path(data)
    if target_path is None:
        return jsonify({"error": {"message": "Invalid target. Provide host + instance_id or preset name."}}), 400

    draft_scripts_path = _get_draft_scripts_path(draft_id)
    draft_user_hooks_path = _get_draft_user_hooks_path(draft_id)

    if data.get("target") == "instance" and os.path.isdir(draft_scripts_path):
        from ui.task_logic.ansible_instance_mgmt import RESERVED_HOOK_FILENAMES
        for name in os.listdir(draft_scripts_path):
            if name in RESERVED_HOOK_FILENAMES:
                return jsonify({
                    "error": {
                        "message": f"Filename '{name}' is reserved for a system hook",
                    },
                }), 400

    try:
        if os.path.exists(target_path):
            shutil.rmtree(target_path)
        shutil.copytree(draft_scripts_path, target_path)
    except OSError as e:
        current_app.logger.error(f"Failed to commit draft {draft_id}: {e}")
        return jsonify({"error": {"message": "Failed to commit draft"}}), 500

    # Copy user-hooks/ alongside scripts/
    if data.get("target") == "instance":
        from ui.models import QLInstance
        from ui.task_logic.common import append_log

        inst_user_hooks = os.path.join(
            os.path.dirname(target_path), USER_HOOKS_DIR
        )
        if os.path.isdir(draft_user_hooks_path):
            shutil.copytree(draft_user_hooks_path, inst_user_hooks, dirs_exist_ok=True)

        instance = db.session.get(QLInstance, int(data["instance_id"]))
        if instance and instance.ld_preload_hooks:
            committed_hooks = (
                set(os.listdir(inst_user_hooks))
                if os.path.isdir(inst_user_hooks) else set()
            )
            on_disk = (
                {name for name in os.listdir(target_path) if name.endswith(".so")}
                if os.path.isdir(target_path)
                else set()
            )
            current_hooks = [
                item.strip()
                for item in instance.ld_preload_hooks.split(",")
                if item.strip()
            ]
            # Keep hooks that exist in committed user-hooks/ OR in scripts/ (legacy)
            kept_hooks = [name for name in current_hooks if name in committed_hooks or name in on_disk]
            if kept_hooks != current_hooks:
                removed = sorted(set(current_hooks) - set(kept_hooks))
                instance.ld_preload_hooks = ",".join(kept_hooks) if kept_hooks else None
                append_log(instance, f"Removed deleted hooks from LD_PRELOAD: {removed}")
                db.session.commit()

    shutil.rmtree(_get_draft_base_path(draft_id), ignore_errors=True)
    current_app.logger.info(f"Committed draft {draft_id} to {target_path}")

    return jsonify({"data": {"message": "Draft committed"}}), 200


# --- Draft folder endpoints ---

import re as _re

_DRAFT_FOLDER_SEGMENT_RE = _re.compile(r'^[A-Za-z0-9._-]+$')


def _normalize_draft_folder_path(rel_path):
    """Validate and normalize a draft folder path.

    Returns the normalized relative path (forward-slash separated) or None if invalid.
    Rules: non-empty, no leading/trailing slash, each segment matches [A-Za-z0-9._-]+
    and is ≤64 chars, reject '.' and '..' segments, reject segments starting with '.',
    and cap total depth at MAX_DRAFT_FOLDER_DEPTH.
    """
    if not isinstance(rel_path, str):
        return None
    rel_path = rel_path.strip()
    if not rel_path or rel_path.startswith('/') or rel_path.endswith('/'):
        return None
    segments = rel_path.split('/')
    if len(segments) > MAX_DRAFT_FOLDER_DEPTH:
        return None
    for seg in segments:
        if not seg or seg in ('.', '..') or seg.startswith('.'):
            return None
        if len(seg) > 64 or not _DRAFT_FOLDER_SEGMENT_RE.match(seg):
            return None
    return '/'.join(segments)


@draft_api_bp.route('/<draft_id>/folders', methods=['POST'])
@jwt_required()
def create_draft_folder(draft_id):
    """Create a new folder inside the draft scripts directory."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft_id"}}), 400
    scripts_path = _get_draft_scripts_path(draft_id)
    if not os.path.isdir(scripts_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404
    data = request.get_json() or {}
    rel_path = _normalize_draft_folder_path(data.get('path'))
    if rel_path is None:
        return jsonify({"error": {"message": "Invalid path"}}), 400
    if not _is_safe_draft_path(scripts_path, rel_path):
        return jsonify({"error": {"message": "Invalid path"}}), 400
    target = os.path.join(scripts_path, rel_path)
    if os.path.exists(target):
        return jsonify({"error": {"message": "Folder already exists"}}), 409
    os.makedirs(target, exist_ok=False)
    return jsonify({"data": {"path": rel_path}}), 201


@draft_api_bp.route('/<draft_id>/folders', methods=['DELETE'])
@jwt_required()
def delete_draft_folder(draft_id):
    """Delete a folder (recursive) inside the draft scripts directory."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft_id"}}), 400
    scripts_path = _get_draft_scripts_path(draft_id)
    if not os.path.isdir(scripts_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404
    rel_path = _normalize_draft_folder_path(request.args.get('path'))
    if rel_path is None:
        return jsonify({"error": {"message": "Invalid path"}}), 400
    if not _is_safe_draft_path(scripts_path, rel_path):
        return jsonify({"error": {"message": "Invalid path"}}), 400
    target = os.path.join(scripts_path, rel_path)
    if not os.path.isdir(target):
        return jsonify({"error": {"message": "Folder not found"}}), 404
    shutil.rmtree(target)
    return jsonify({"data": {"path": rel_path}}), 200


@draft_api_bp.route('/<draft_id>/folders', methods=['PATCH'])
@jwt_required()
def rename_draft_folder(draft_id):
    """Rename a folder inside the draft scripts directory."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft_id"}}), 400
    scripts_path = _get_draft_scripts_path(draft_id)
    if not os.path.isdir(scripts_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404
    data = request.get_json() or {}
    old_path = _normalize_draft_folder_path(data.get('old_path'))
    new_path = _normalize_draft_folder_path(data.get('new_path'))
    if old_path is None or new_path is None:
        return jsonify({"error": {"message": "Invalid path"}}), 400
    if not (_is_safe_draft_path(scripts_path, old_path) and _is_safe_draft_path(scripts_path, new_path)):
        return jsonify({"error": {"message": "Invalid path"}}), 400
    src = os.path.join(scripts_path, old_path)
    dst = os.path.join(scripts_path, new_path)
    if not os.path.isdir(src):
        return jsonify({"error": {"message": "Source folder not found"}}), 404
    if os.path.exists(dst):
        return jsonify({"error": {"message": "Target already exists"}}), 409
    os.rename(src, dst)
    return jsonify({"data": {"old_path": old_path, "new_path": new_path}}), 200
