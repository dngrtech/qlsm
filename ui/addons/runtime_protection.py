"""Serialize provider lifecycle changes and protect releases referenced by hosts.

Locks live beside the package directory so a backup's directory swap cannot
replace a locked inode. A shared maintenance lock lets unrelated providers
change concurrently; archive export/restore takes its exclusive side. Settings
locks last through the database transaction, including callers using commit=False.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import time

from flask import current_app, has_app_context
from sqlalchemy import event

from ui.addons.manifest import ADDON_ID_MAX, ADDON_ID_RE

LOCK_TIMEOUT_SECONDS = 5
_SESSION_LOCKS = "addon_provider_lifecycle_locks"
_MAINTENANCE_FILE = ".maintenance.lock"
_BUSY_MESSAGE = "An add-on change or backup is already running. Try again when it finishes."


class RuntimeProviderConflict(ValueError):
    """A lifecycle conflict suitable for an HTTP 409 response."""

    def __init__(self, message, *, code="runtime_provider_busy", dependent_hosts=None):
        super().__init__(message)
        self.code = code
        self.dependent_hosts = dependent_hosts or []

    def to_error(self):
        return {"message": str(self), "code": self.code,
                "dependent_hosts": self.dependent_hosts}


class RuntimeProviderInUse(RuntimeProviderConflict):
    def __init__(self, provider_id, action, hosts):
        names = ", ".join(host["name"] for host in hosts)
        super().__init__(
            f'Cannot {action} runtime provider "{provider_id}"; it is used by hosts: {names}. '
            'Remove the dependent hosts before removing or disabling their provider.',
            code="runtime_provider_in_use", dependent_hosts=hosts)


def addon_lifecycle_lock_directory(packages_dir=None) -> Path:
    """Resolve the stable sibling directory without creating it."""
    if packages_dir is None:
        packages_dir = current_app.config.get("ADDON_PACKAGES_DIR") or "./data/addon-packages"
    root = Path(packages_dir).resolve()
    return root.parent / f".{root.name}.provider-locks"


def _lock_directory(packages_dir=None):
    directory = addon_lifecycle_lock_directory(packages_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextmanager
def _file_lock(path, mode, *, busy_message=_BUSY_MESSAGE):
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        while True:
            try:
                fcntl.flock(fd, mode | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeProviderConflict(busy_message) from None
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


@contextmanager
def provider_lifecycle_lock(provider_id, packages_dir=None):
    if (not isinstance(provider_id, str) or len(provider_id) > ADDON_ID_MAX
            or not ADDON_ID_RE.fullmatch(provider_id)):
        raise RuntimeProviderConflict("Invalid runtime provider id.", code="invalid_runtime_provider")
    directory = _lock_directory(packages_dir)
    with _file_lock(directory / _MAINTENANCE_FILE, fcntl.LOCK_SH):
        with _file_lock(directory / f"{provider_id}.lock", fcntl.LOCK_EX):
            yield


def addon_lifecycle_shared_lock(packages_dir=None):
    """Keep export/restore outside a mutation spanning packages or entities."""
    return _file_lock(_lock_directory(packages_dir) / _MAINTENANCE_FILE, fcntl.LOCK_SH)


@contextmanager
def standalone_creation_lock(name):
    """Exclude restore and other requests for the same case-insensitive name."""
    directory = _lock_directory()
    identifier = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()
    with _file_lock(directory / _MAINTENANCE_FILE, fcntl.LOCK_SH):
        with _file_lock(directory / f".standalone-{identifier}.lock", fcntl.LOCK_EX,
                        busy_message=f'Another Standalone host named "{name}" is being created.'):
            yield


@contextmanager
def addon_lifecycle_maintenance_lock(packages_dir=None):
    """Exclude package and settings mutations for the whole archive operation."""
    with _file_lock(_lock_directory(packages_dir) / _MAINTENANCE_FILE, fcntl.LOCK_EX):
        yield


def _release_transaction_locks(session, transaction):
    if transaction.parent is not None:
        return
    for lock in session.info.pop(_SESSION_LOCKS, {}).values():
        lock.__exit__(None, None, None)


def _lock_until_transaction_end(key, lock):
    from ui import db

    session = db.session()
    locks = session.info.setdefault(_SESSION_LOCKS, {})
    if key in locks:
        return
    lock.__enter__()
    try:
        if not session.in_transaction():
            session.begin()
        if not event.contains(session, "after_transaction_end", _release_transaction_locks):
            event.listen(session, "after_transaction_end", _release_transaction_locks)
        locks[key] = lock
    except Exception:
        lock.__exit__(None, None, None)
        raise


def lock_provider_state(provider_id):
    """Keep the provider locked until commit, rollback, or session close."""
    _lock_until_transaction_end(provider_id, provider_lifecycle_lock(provider_id))


def lock_scoped_state_cleanup():
    _lock_until_transaction_end(None, addon_lifecycle_shared_lock())


def check_provider_dependencies(provider_id, action, *, retains_runtime=False):
    if not has_app_context():
        raise RuntimeProviderConflict(
            "Changing an existing add-on requires an application database context.",
            code="runtime_provider_check_unavailable")
    from ui import db
    from ui.models import Host

    hosts = [{"id": row.id, "name": row.name} for row in
             db.session.query(Host.id, Host.name)
             .filter(Host.runtime == "custom", Host.runtime_provider_id == provider_id)
             .order_by(Host.id).all()]
    if hosts and not retains_runtime:
        raise RuntimeProviderInUse(provider_id, action, hosts)


def ensure_runtime_provider_present(provider_id):
    """Reject pending disk changes that remove the loaded provider capability.

    A normal provider update remains pending until restart. Its old approved
    metadata is still valid, but an override without custom_runtime must not
    accept new hosts just because this process imported the previous package.
    """
    from ui.addons.manifest import read_manifest
    from ui.addons.registry import get_addon

    addon = get_addon(provider_id)
    if addon is None:
        raise RuntimeProviderConflict("The selected runtime provider is unavailable.")
    installed = Path(current_app.config.get("ADDON_PACKAGES_DIR", "./data/addon-packages")) / provider_id
    root = installed if installed.exists() else Path(addon.root_dir)
    manifest, errors = read_manifest(str(root))
    if errors or not manifest or not manifest.get("custom_runtime"):
        raise RuntimeProviderConflict(
            "The runtime provider changed on disk. Restart QLSM and select an available provider.",
            code="stale_runtime")
