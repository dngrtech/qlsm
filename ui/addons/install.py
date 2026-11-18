"""Install and uninstall addon packages from an uploaded .zip.

Every check here is about not being trivially exploitable by a malformed
archive. None of it is a judgement about whether the addon's code is safe to
run -- that is impossible, and `addons/TRUST.md` says so plainly. Read that
before changing anything in this file.

Nothing touches the real addon directory until the whole archive has been
validated and staged, so a rejected upload leaves the previous state exactly
as it was.
"""
import io
import json
import os
import shutil
import tempfile
import zipfile

from ui.addons.manifest import MANIFEST_FILENAME, read_manifest, validate_manifest

# Bounds, all deliberately generous for a metadata + small-payload package and
# still far below anything that could exhaust the container.
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024        # the .zip itself
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024  # sum of members, i.e. the bomb guard
MAX_ENTRIES = 2000
MAX_COMPRESSION_RATIO = 200                 # per-member, catches a single huge member


class AddonInstallError(ValueError):
    """Rejected upload. Always surfaces as a 400, never a 500."""


def _is_symlink(info):
    """zipfile has no API for this; the mode lives in the high bits."""
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def _safe_member_path(name):
    """Normalized relative path for a zip member, or raise.

    This is the zip-slip guard. Rejecting rather than sanitizing is
    deliberate: an archive containing `../../etc/whatever` is not a package
    with a typo, and silently rewriting it would hide that.
    """
    if not name or name.startswith('/') or name.startswith('\\'):
        raise AddonInstallError(f'Archive contains an absolute path: {name!r}')
    if ':' in name.split('/')[0] and len(name.split('/')[0]) == 2:
        raise AddonInstallError(f'Archive contains a drive-qualified path: {name!r}')
    parts = [p for p in name.replace('\\', '/').split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        raise AddonInstallError(f'Archive contains a parent-directory path: {name!r}')
    return '/'.join(parts)


def _inspect(zf):
    """Validate every member up front and return (root_prefix, members).

    `root_prefix` handles both archive shapes people actually produce: the
    manifest at the top level, and everything nested under a single folder
    (what "Compress" on a directory gives you).
    """
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise AddonInstallError(f'Archive has more than {MAX_ENTRIES} entries.')

    total = 0
    members = []
    for info in infos:
        if _is_symlink(info):
            raise AddonInstallError(f'Archive contains a symlink: {info.filename!r}')
        path = _safe_member_path(info.filename)
        if not path:
            continue
        if info.is_dir() or info.filename.endswith('/'):
            continue
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise AddonInstallError('Archive expands to more than the allowed size.')
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise AddonInstallError(f'Archive member {path!r} has a suspicious compression ratio.')
        members.append((info, path))

    manifests = [p for _, p in members if p.split('/')[-1] == MANIFEST_FILENAME]
    if not manifests:
        raise AddonInstallError(f'Archive has no {MANIFEST_FILENAME}.')

    # Prefer the shallowest manifest; deeper ones belong to nested examples.
    manifests.sort(key=lambda p: p.count('/'))
    manifest_path = manifests[0]
    depth = manifest_path.count('/')
    if depth > 1:
        raise AddonInstallError(
            f'{MANIFEST_FILENAME} must be at the archive root or one folder deep.')
    root_prefix = manifest_path[:-len(MANIFEST_FILENAME)]  # '' or 'folder/'
    return root_prefix, members, manifest_path


def read_manifest_from_zip(zf, manifest_path):
    try:
        raw = zf.read(manifest_path)
    except KeyError:
        raise AddonInstallError(f'Could not read {MANIFEST_FILENAME} from the archive.')
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as e:
        raise AddonInstallError(f'{MANIFEST_FILENAME} is not valid JSON: {e}')

    manifest, errors = validate_manifest(data)
    if errors:
        raise AddonInstallError('Manifest is invalid: ' + '; '.join(errors))
    return manifest


def read_manifest_from_blob(blob):
    """Validate the archive's shape and return its parsed manifest without
    installing anything -- the same member checks _inspect applies during a
    real install. Lets a caller (e.g. a repository install) verify what the
    package claims to be before the packages dir is touched."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise AddonInstallError('The file is not a valid .zip archive.')
    with zf:
        _root_prefix, _members, manifest_path = _inspect(zf)
        return read_manifest_from_zip(zf, manifest_path)


def install_addon_zip(blob, packages_dir):
    """Validate and install an addon package.

    Returns the parsed manifest. Raises AddonInstallError for anything the
    operator can fix; never raises for a merely-unknown addon id.
    """
    if not blob:
        raise AddonInstallError('No file was uploaded.')
    if len(blob) > MAX_ARCHIVE_BYTES:
        raise AddonInstallError('Archive is larger than the allowed size.')

    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise AddonInstallError('The uploaded file is not a valid .zip archive.')

    with zf:
        root_prefix, members, manifest_path = _inspect(zf)
        manifest = read_manifest_from_zip(zf, manifest_path)
        addon_id = manifest['id']

        os.makedirs(packages_dir, exist_ok=True)
        target = os.path.join(packages_dir, addon_id)

        # Stage a sibling of the target so the final move stays on one
        # filesystem, then swap. Same pattern as the global backup restore.
        staging = tempfile.mkdtemp(prefix=f'.{addon_id}.staging-', dir=packages_dir)
        try:
            extracted = 0
            for info, path in members:
                if root_prefix and not path.startswith(root_prefix):
                    continue  # stray file outside the package folder
                relative = path[len(root_prefix):] if root_prefix else path
                if not relative:
                    continue
                destination = os.path.join(staging, *relative.split('/'))
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                with zf.open(info) as source, open(destination, 'wb') as out:
                    shutil.copyfileobj(source, out, length=64 * 1024)
                extracted += 1

            if not extracted:
                raise AddonInstallError('Archive contained no files to install.')
            if not os.path.isfile(os.path.join(staging, MANIFEST_FILENAME)):
                raise AddonInstallError(f'{MANIFEST_FILENAME} did not survive extraction.')

            if 'custom_runtime' in manifest:
                from ui.custom_runtime import retain_release
                try:
                    retain_release(packages_dir, staging, manifest)
                except ValueError as error:
                    raise AddonInstallError(str(error)) from error

            # Move the old copy aside rather than deleting it, so a failed
            # swap can put it back -- an upgrade must never be able to leave
            # the operator with no addon at all.
            previous = None
            if os.path.exists(target):
                previous = os.path.join(packages_dir, f'.{addon_id}.previous-{os.getpid()}')
                shutil.rmtree(previous, ignore_errors=True)
                os.rename(target, previous)
            try:
                os.rename(staging, target)
            except OSError:
                if previous is not None:
                    os.rename(previous, target)
                raise
            staging = None
            if previous is not None:
                shutil.rmtree(previous, ignore_errors=True)
        finally:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)

    return manifest


def uninstall_addon(addon_id, packages_dir):
    """Remove an installed package directory. Returns True if it existed.

    Only ever touches `packages_dir` -- a bundled addon lives in the image and
    is refused by the caller, since deleting it would only come back on the
    next deploy while leaving the running container inconsistent.
    """
    root = os.path.abspath(packages_dir)
    target = os.path.abspath(os.path.join(root, addon_id))
    if target == root or not target.startswith(root + os.sep):
        raise AddonInstallError('Invalid addon id.')
    if not os.path.isdir(target):
        return False
    shutil.rmtree(target)
    return True


def scan_installed_ids(packages_dir):
    """Addon ids present on the volume right now, regardless of what this
    process loaded at startup. The difference between this and the loaded set
    is what the UI shows as "pending restart"."""
    if not packages_dir or not os.path.isdir(packages_dir):
        return set()
    found = set()
    for entry in os.listdir(packages_dir):
        if entry.startswith('.'):
            continue  # staging/previous leftovers
        if os.path.isfile(os.path.join(packages_dir, entry, MANIFEST_FILENAME)):
            found.add(entry)
    return found


def scan_installed_versions(packages_dir):
    """Addon id -> on-disk manifest version, for every id scan_installed_ids
    would return.

    An in-place update (same id, present on the volume before and after,
    just newer bytes written by install_addon_zip) never changes set
    membership, so a caller that only has scan_installed_ids cannot tell it
    apart from a no-op. This carries the version needed to make that
    distinction.
    """
    if not packages_dir or not os.path.isdir(packages_dir):
        return {}
    versions = {}
    for entry in os.listdir(packages_dir):
        if entry.startswith('.'):
            continue  # staging/previous leftovers
        manifest, _errors = read_manifest(os.path.join(packages_dir, entry))
        if manifest is not None:
            versions[entry] = manifest.get('version') or ''
    return versions


def package_stamp(root_dir):
    """Identity of the package sitting at `root_dir`, or None if there is none.

    install_addon_zip always writes a fresh tree and swaps it in, so the
    manifest file is a new file after every install, including a reinstall of
    the very same version. Comparing this at boot and now is what tells "the
    package this process imported" from "one written since", which a version
    comparison alone cannot do.
    """
    try:
        st = os.stat(os.path.join(root_dir, MANIFEST_FILENAME))
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)
