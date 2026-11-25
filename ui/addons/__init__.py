"""qlsm addon system.

Public surface for core call sites. Core should import from here, not from the
submodules, so the internals can move without a repo-wide rename.
"""
from ui.addons.context import AddonContext
from ui.addons.hooks import HOOK_SCOPES, LIST_HOOKS, UnknownHookError
from ui.addons.install import (
    AddonInstallError,
    install_addon_zip,
    scan_installed_ids,
    scan_installed_versions,
    uninstall_addon,
)
from ui.addons.manifest import CURRENT_UI_API, MANIFEST_FILENAME, read_manifest, validate_manifest
from ui.addons.registry import (
    catalog,
    cleanup_scope,
    dispatch,
    dispatch_by_addon,
    dispatch_each,
    get_addon,
    get_addons,
    init_app,
)
from ui.addons.settings import AddonSettings, AddonSettingsError

__all__ = [
    'AddonContext',
    'AddonInstallError',
    'AddonSettings',
    'AddonSettingsError',
    'CURRENT_UI_API',
    'HOOK_SCOPES',
    'LIST_HOOKS',
    'MANIFEST_FILENAME',
    'UnknownHookError',
    'catalog',
    'cleanup_scope',
    'dispatch',
    'dispatch_by_addon',
    'dispatch_each',
    'get_addon',
    'get_addons',
    'init_app',
    'install_addon_zip',
    'read_manifest',
    'scan_installed_ids',
    'scan_installed_versions',
    'uninstall_addon',
    'validate_manifest',
]
