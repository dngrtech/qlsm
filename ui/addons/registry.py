"""Discover, load, and dispatch to addons.

Two sources, in this order (spec decision C):
  1. bundled  -- `addons/` shipped inside the image
  2. installed -- an operator-writable volume (ADDON_PACKAGES_DIR)
An id present in both resolves to the installed copy, so an operator can
override a bundled addon without rebuilding the image.

Everything here is failure-isolated. A broken manifest, an import that raises,
a register() that throws, a hook handler that blows up mid-deploy -- each is
logged and recorded against that addon, and the rest of qlsm carries on. The
alternative (one bad addon takes the control plane down) is unacceptable for a
system whose whole point is that features can be dropped in.
"""
import importlib.util
import logging
import os
import sys
import time
import traceback

from ui.addons.context import AddonContext
from ui.addons.hooks import HOOK_SCOPES, LIST_HOOKS
from ui.addons.install import package_stamp
from ui.addons.manifest import CURRENT_UI_API, MANIFEST_FILENAME, read_manifest

log = logging.getLogger(__name__)

# Hooks that run inline in a latency-sensitive loop, and the seconds after which
# a handler is logged by addon id. poller.tick handlers run in the poll loop, so
# a slow one delays the next status poll.
SLOW_HANDLER_SECONDS = {'poller.tick': 10}

BUNDLED_ADDONS_DIRNAME = 'addons'
EXTENSION_KEY = 'addons'


class LoadedAddon:
    """One addon and whatever we managed to learn about it."""

    def __init__(self, addon_id, manifest, root_dir, source):
        self.id = addon_id
        self.manifest = manifest
        self.root_dir = root_dir
        self.source = source           # 'bundled' | 'installed'
        self.stamp = package_stamp(root_dir)   # the package as it was at boot
        self.ctx = None
        self.errors = []               # manifest errors + load traceback summary
        self.loaded = False

    @property
    def mountable_ui(self):
        """False when the addon's UI needs a newer core than this one.

        The addon still loads -- its backend and API are fine; only the
        components are withheld, with the reason visible in the catalog.
        """
        return (self.manifest or {}).get('ui_api', CURRENT_UI_API) <= CURRENT_UI_API

    @property
    def globally_enabled(self):
        """Whole-addon on/off switch, distinct from any scoped setting a
        panel writes to its own AppSetting-backed store.

        Bundled addons ship in the image and would otherwise always be
        active; this is what lets an operator turn one off without
        uninstalling it (which bundled addons cannot be anyway). Backed by
        the same AddonState('global', 0) row the generic managed-panel
        checkbox already used -- no new storage. Defaults to False (no row
        yet), so a freshly deployed addon starts hidden until switched on.
        """
        if self.ctx is None:
            return False
        try:
            return self.ctx.settings.is_enabled('global', 0)
        except Exception as e:
            log.warning('Addon %s global enable check failed: %s', self.id, e)
            return False

    def to_dict(self):
        m = self.manifest or {}
        return {
            'id': self.id,
            'name': m.get('name') or self.id,
            'version': m.get('version') or '',
            'description': m.get('description') or '',
            'scopes': m.get('scopes') or [],
            'ui': m.get('ui') or {},
            'ui_api': m.get('ui_api', CURRENT_UI_API),
            'settings_schema': m.get('settings') or {},
            'source': self.source,
            'loaded': self.loaded,
            'ui_mountable': self.mountable_ui,
            'enabled': self.globally_enabled,
            'errors': list(self.errors),
        }


def _candidate_dirs(app):
    """(directory, source) pairs to scan, lowest precedence first."""
    dirs = []
    bundled = os.path.join(app.root_path, os.pardir, BUNDLED_ADDONS_DIRNAME)
    dirs.append((os.path.abspath(bundled), 'bundled'))
    installed = app.config.get('ADDON_PACKAGES_DIR')
    if installed:
        dirs.append((os.path.abspath(installed), 'installed'))
    return dirs


def _scan(app):
    """Return {addon_id: LoadedAddon} with manifests read but nothing imported."""
    found = {}
    for base, source in _candidate_dirs(app):
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            root = os.path.join(base, entry)
            if not os.path.isdir(root):
                continue
            if not os.path.isfile(os.path.join(root, MANIFEST_FILENAME)):
                continue  # not an addon directory at all, not an error
            try:
                manifest, errors = read_manifest(root)
            except Exception as e:
                # read_manifest() is contracted never to raise -- a bad
                # manifest is supposed to come back as an error list. It is
                # called from init_app(), i.e. during create_app(), so a bug
                # in the validator would otherwise stop qlsm from starting at
                # all over one malformed third-party addon. Belt and braces.
                manifest, errors = None, [f'manifest could not be read -- {type(e).__name__}: {e}']
                log.error('Addon manifest at %s raised during validation: %s\n%s',
                          root, e, traceback.format_exc())
            addon_id = (manifest or {}).get('id') or entry
            addon = LoadedAddon(addon_id, manifest, root, source)
            addon.errors = list(errors)
            if errors:
                log.warning('Addon %s at %s has manifest errors: %s', addon_id, root, '; '.join(errors))
            if addon_id in found:
                log.info('Addon %s from %s overrides the %s copy',
                         addon_id, source, found[addon_id].source)
            found[addon_id] = addon
    return found


def _import_backend(addon):
    """Import the addon's backend.py and run register(ctx). Never raises."""
    backend_path = os.path.join(addon.root_dir, 'backend.py')
    module_name = f'qlsm_addon_{addon.id.replace("-", "_")}'
    ctx = AddonContext(addon.id, addon.manifest, addon.root_dir, module_name=module_name)
    if not os.path.isfile(backend_path):
        # A UI-only addon is legitimate: declarative panels against another
        # addon's API, or a page that only reads core endpoints.
        addon.ctx = ctx
        addon.loaded = True
        return

    try:
        # Loaded as a *package*, not a lone module: submodule_search_locations
        # makes the addon's own directory importable, so backend.py can do
        # `from . import settings` and an addon can be more than one file.
        # Without it a multi-file addon is impossible -- its siblings are not
        # on any search path and `import settings` would either fail or, worse,
        # pick up an unrelated top-level module with the same common name.
        spec = importlib.util.spec_from_file_location(
            module_name, backend_path, submodule_search_locations=[addon.root_dir],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        register = getattr(module, 'register', None)
        if callable(register):
            register(ctx)
        addon.ctx = ctx
        addon.loaded = True
    except Exception as e:
        sys.modules.pop(module_name, None)
        summary = f'{type(e).__name__}: {e}'
        addon.errors.append(f'backend.py failed to load -- {summary}')
        addon.loaded = False
        log.error('Addon %s failed to load: %s\n%s', addon.id, summary, traceback.format_exc())


def _mount_blueprints(app, addon):
    for bp in addon.ctx.blueprints:
        try:
            app.register_blueprint(bp, url_prefix=f'/api/addons/{addon.id}')
        except Exception as e:
            addon.errors.append(f'blueprint "{bp.name}" could not be mounted -- {e}')
            log.error('Addon %s blueprint mount failed: %s', addon.id, e)


def init_app(app):
    """Discover + load every addon. Called once from the app factory."""
    addons = {}
    for addon_id, addon in _scan(app).items():
        if addon.errors and addon.manifest is None:
            addons[addon_id] = addon      # unusable, but still visible in the catalog
            continue
        _import_backend(addon)
        if addon.loaded and addon.ctx is not None:
            _mount_blueprints(app, addon)
        addons[addon_id] = addon
    app.extensions[EXTENSION_KEY] = addons
    loaded = [a.id for a in addons.values() if a.loaded]
    broken = [a.id for a in addons.values() if not a.loaded]
    log.info('Addons loaded: %s%s',
             ', '.join(loaded) or 'none',
             f' (broken: {", ".join(broken)})' if broken else '')
    return addons


def get_addons(app=None):
    from flask import current_app
    app = app or current_app
    return app.extensions.get(EXTENSION_KEY, {})


def get_addon(addon_id, app=None):
    return get_addons(app).get(addon_id)


def catalog(app=None):
    return [a.to_dict() for a in sorted(get_addons(app).values(), key=lambda a: a.id)]


def _gates_open(addon, hook, scope_id):
    scope = HOOK_SCOPES[hook]
    if scope is None:
        return True
    try:
        return addon.ctx.settings.is_enabled(scope, scope_id)
    except Exception as e:
        log.warning('Addon %s enable check failed for %s: %s', addon.id, hook, e)
        return False


def dispatch(hook, scope_id=0, *args, **kwargs):
    """Call every enabled addon's handlers for `hook`.

    Returns a flat list for contribution hooks (LIST_HOOKS) and a list of
    per-addon return values otherwise. A handler that raises is logged and
    skipped: an addon must not be able to abort a deploy it merely decorates.
    """
    return dispatch_each(hook, scope_id, lambda addon_id: (args, kwargs))


def dispatch_each(hook, scope_id, args_for, on_error=None):
    """dispatch(), but every addon's handlers get arguments of their own.

    `args_for(addon_id)` returns the `(args, kwargs)` that addon's handlers
    are called with. For a hook that carries per-addon input -- the values an
    addon's own add-instance tab collected, say -- where handing every addon
    everyone's input would leak one addon's form data (a secret field
    included) into another's handler.

    `on_error(addon_id, exc)` runs after a handler raised and was logged, so
    the caller can undo what it left half done (e.g. roll back a session the
    handler broke) before the next addon runs. Its own failure is logged and
    swallowed.
    """
    if hook not in HOOK_SCOPES:
        raise ValueError(f'unknown hook "{hook}"')
    results = []
    for addon in sorted(get_addons().values(), key=lambda a: a.id):
        if not addon.loaded or addon.ctx is None:
            continue
        handlers = addon.ctx.handlers.get(hook) or []
        if not handlers:
            continue
        if not _gates_open(addon, hook, scope_id):
            continue
        slow_after = SLOW_HANDLER_SECONDS.get(hook)
        args, kwargs = args_for(addon.id)
        for handler in handlers:
            started = time.monotonic()
            try:
                value = handler(*args, **kwargs)
            except Exception as e:
                log.error('Addon %s hook %s failed: %s\n%s',
                          addon.id, hook, e, traceback.format_exc())
                if on_error is not None:
                    try:
                        on_error(addon.id, e)
                    except Exception as cleanup_error:
                        log.error('Addon %s hook %s cleanup failed: %s',
                                  addon.id, hook, cleanup_error)
                continue
            finally:
                elapsed = time.monotonic() - started
                if slow_after is not None and elapsed > slow_after:
                    log.warning('Addon %s hook %s handler took %.1fs (warn threshold %ds)',
                                addon.id, hook, elapsed, slow_after)
            if hook in LIST_HOOKS:
                if value:
                    results.extend(value if isinstance(value, (list, tuple)) else [value])
            else:
                results.append(value)
    return results


def dispatch_by_addon(hook, scope_id, *args):
    """dispatch_each() for a caller that needs to know which addon said what.

    Returns `(addon_id, value)` pairs in alphabetical addon order, one per
    handler call that did not raise. Unlike dispatch(), list values are not
    flattened into one list: the pairing is the point. Same gates, same
    logging of a raising handler (skipped, never propagated).
    """
    if hook not in HOOK_SCOPES:
        raise ValueError(f'unknown hook "{hook}"')
    pairs = []
    for addon in sorted(get_addons().values(), key=lambda a: a.id):
        if not addon.loaded or addon.ctx is None:
            continue
        handlers = addon.ctx.handlers.get(hook) or []
        if not handlers:
            continue
        if not _gates_open(addon, hook, scope_id):
            continue
        for handler in handlers:
            try:
                value = handler(*args)
            except Exception as e:
                log.error('Addon %s hook %s failed: %s\n%s',
                          addon.id, hook, e, traceback.format_exc())
                continue
            pairs.append((addon.id, value))
    return pairs


def cleanup_scope(scope, scope_id, commit=False):
    """Drop every addon's state for a host/instance that is being deleted."""
    from ui.addons.settings import delete_scope_rows
    dispatch(f'{scope}.delete', scope_id, scope_id)
    return delete_scope_rows(scope, scope_id, commit=commit)
