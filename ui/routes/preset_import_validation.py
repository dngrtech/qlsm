"""Validation and parsing for preset ZIP imports (counterpart of preset export)."""
import io
import json
import stat
import zipfile

from ui.routes.draft_routes import MAX_BINARY_FILE_SIZE
from ui.routes.instance_hooks_routes import _validate_filename as _validate_hook_filename
from ui.routes.preset_api_routes import (
    ALLOWED_PRESET_FACTORY_EXTENSIONS,
    EXPORT_FORMAT_VERSION,
    PROTECTED_CONFIG_FILES,
    _should_skip_export_path,
    _validate_flat_filename,
    _validate_path_segment,
    _validate_relative_config_path,
)

MAX_IMPORT_ZIP_BYTES = 150 * 1024 * 1024
MAX_IMPORT_ENTRIES = 2000
MAX_TEXT_ENTRY_BYTES = 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_SCRIPT_PATH_DEPTH = 4
ELF_MAGIC = b'\x7fELF'


class PresetImportError(ValueError):
    """Raised when an uploaded preset archive fails validation."""


def _entry_is_symlink(info):
    return stat.S_ISLNK(info.external_attr >> 16)


def _validate_entry_name(name):
    if not name or '\x00' in name or '\\' in name or name.startswith('/'):
        raise PresetImportError(f"Unsafe path in archive: {name!r}")
    if any(part in ('', '.', '..') for part in name.rstrip('/').split('/')):
        raise PresetImportError(f"Unsafe path in archive: {name!r}")


def _check_archive_limits(infos):
    if len(infos) > MAX_IMPORT_ENTRIES:
        raise PresetImportError("Archive contains too many entries.")
    total = 0
    for info in infos:
        if info.is_dir():
            continue
        total += info.file_size
        ratio = info.file_size / max(info.compress_size, 1)
        if info.file_size > MAX_TEXT_ENTRY_BYTES and ratio > MAX_COMPRESSION_RATIO:
            raise PresetImportError(
                f"Archive entry {info.filename} has a suspicious compression ratio."
            )
    if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise PresetImportError("Archive uncompressed size exceeds the limit.")


def _read_text(archive, info, label):
    if info.file_size > MAX_TEXT_ENTRY_BYTES:
        raise PresetImportError(
            f"{label} file {info.filename} exceeds {MAX_TEXT_ENTRY_BYTES // 1024}KB."
        )
    try:
        return _read_entry(archive, info).decode('utf-8')
    except UnicodeDecodeError as exc:
        raise PresetImportError(
            f"{label} file {info.filename} is not valid UTF-8 text."
        ) from exc


def _read_entry(archive, info):
    try:
        return archive.read(info)
    except (RuntimeError, zipfile.BadZipFile) as exc:
        raise PresetImportError(
            f"Archive entry {info.filename} could not be read."
        ) from exc


def _read_json(archive, info, label):
    try:
        return json.loads(_read_text(archive, info, label))
    except json.JSONDecodeError as exc:
        raise PresetImportError(f"{label} file {info.filename} is not valid JSON.") from exc


def _validate_script_path(rel_path):
    segments = rel_path.split('/')
    if len(segments) > MAX_SCRIPT_PATH_DEPTH:
        raise PresetImportError(f"Script path too deep: scripts/{rel_path}")
    for segment in segments:
        try:
            _validate_path_segment(segment, None, 'script')
        except ValueError as exc:
            raise PresetImportError(str(exc)) from exc
    if not rel_path.lower().endswith(('.py', '.txt')):
        raise PresetImportError(f"Unsupported script file: scripts/{rel_path}")


def _read_user_hook(archive, info, filename):
    error = _validate_hook_filename(filename)
    if error:
        raise PresetImportError(f"Invalid user hook {info.filename}: {error}")
    if info.file_size > MAX_BINARY_FILE_SIZE:
        raise PresetImportError(
            f"User hook {filename} exceeds {MAX_BINARY_FILE_SIZE // (1024 * 1024)}MB."
        )
    content = _read_entry(archive, info)
    if not content.startswith(ELF_MAGIC):
        raise PresetImportError(f"User hook {filename} is not a valid ELF binary.")
    return content


def _validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise PresetImportError(
            "Archive is missing manifest.json — not a QLSM preset export."
        )
    if manifest.get('type') != 'qlsm-preset-export':
        raise PresetImportError("Archive is not a QLSM preset export.")
    version = manifest.get('format_version')
    if not isinstance(version, int) or not 1 <= version <= EXPORT_FORMAT_VERSION:
        raise PresetImportError("Unsupported preset export format version.")
    preset_info = manifest.get('preset')
    if not isinstance(preset_info, dict) or not isinstance(preset_info.get('name'), str):
        raise PresetImportError("Manifest is missing the preset name.")


def _validate_checked_lists(bundle):
    checked_plugins = bundle['checked_plugins']
    if checked_plugins is not None and (
        not isinstance(checked_plugins, list)
        or not all(isinstance(p, str) for p in checked_plugins)
    ):
        raise PresetImportError("checked_plugins.json must contain a list of strings.")
    checked_factories = bundle['checked_factories']
    if checked_factories is not None and (
        not isinstance(checked_factories, list)
        or not all(
            isinstance(f, str) and f.lower().endswith('.factories')
            for f in checked_factories
        )
    ):
        raise PresetImportError(
            "checked_factories.json must contain a list of .factories filenames."
        )


def _normalize_binary_metadata(payload, user_hooks):
    if payload is None:
        return []
    if not isinstance(payload, dict) or not isinstance(payload.get('metadata'), list):
        raise PresetImportError("binary_metadata.json has an unexpected structure.")
    entries = []
    seen_paths = set()
    for row in payload['metadata']:
        if not isinstance(row, dict):
            continue
        file_path = row.get('file_path')
        if (
            not isinstance(file_path, str)
            or file_path not in user_hooks
            or file_path in seen_paths
        ):
            continue
        seen_paths.add(file_path)
        description = row.get('description')
        entries.append({
            'file_path': file_path,
            'description': description if isinstance(description, str) else '',
        })
    return entries


def parse_import_archive(raw_bytes):
    """Parse and fully validate an uploaded preset export ZIP.

    Returns the classified bundle; raises PresetImportError on any problem.
    No filesystem access — everything happens on the in-memory archive.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except zipfile.BadZipFile as exc:
        raise PresetImportError("File is not a valid ZIP archive.") from exc

    bundle = {
        'configs': {}, 'factories': {}, 'scripts': {}, 'user_hooks': {},
        'checked_plugins': None, 'checked_factories': None,
        'manifest': None, 'binary_metadata': None,
    }

    with archive:
        infos = archive.infolist()
        _check_archive_limits(infos)

        for info in infos:
            name = info.filename
            _validate_entry_name(name)
            if info.is_dir():
                continue
            if _entry_is_symlink(info):
                raise PresetImportError(f"Archive contains a symlink: {name}")
            if _should_skip_export_path(name):
                continue
            if name == 'manifest.json':
                bundle['manifest'] = _read_json(archive, info, 'Manifest')
            elif name == 'binary_metadata.json':
                bundle['binary_metadata'] = _read_json(archive, info, 'Binary metadata')
            elif name == 'checked_plugins.json':
                bundle['checked_plugins'] = _read_json(archive, info, 'Checked plugins')
            elif name == 'checked_factories.json':
                bundle['checked_factories'] = _read_json(archive, info, 'Checked factories')
            elif name.startswith('factories/'):
                filename = name[len('factories/'):]
                try:
                    _validate_flat_filename(
                        filename, ALLOWED_PRESET_FACTORY_EXTENSIONS, 'factory'
                    )
                except ValueError as exc:
                    raise PresetImportError(str(exc)) from exc
                bundle['factories'][filename] = _read_text(archive, info, 'Factory')
            elif name.startswith('scripts/'):
                rel_path = name[len('scripts/'):]
                _validate_script_path(rel_path)
                bundle['scripts'][rel_path] = _read_text(archive, info, 'Script')
            elif name.startswith('user-hooks/'):
                filename = name[len('user-hooks/'):]
                if '/' in filename:
                    raise PresetImportError(f"Invalid user hook {name}: nested paths are not allowed")
                bundle['user_hooks'][filename] = _read_user_hook(archive, info, filename)
            else:
                try:
                    _validate_relative_config_path(name)
                except ValueError as exc:
                    raise PresetImportError(f"Unsupported file in archive: {name}") from exc
                bundle['configs'][name] = _read_text(archive, info, 'Config')

    _validate_manifest(bundle['manifest'])
    _validate_checked_lists(bundle)
    bundle['binary_metadata'] = _normalize_binary_metadata(
        bundle['binary_metadata'], bundle['user_hooks']
    )

    missing = PROTECTED_CONFIG_FILES - set(bundle['configs'])
    if missing:
        raise PresetImportError(
            "Archive is missing required config files: " + ', '.join(sorted(missing))
        )
    return bundle
