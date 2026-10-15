"""AddonContext -- the only surface an addon's backend.py talks to.

An addon never imports core modules directly if it can help it: everything it
is allowed to do goes through this object, which means core can change its
internals without breaking every installed addon, and the set of things an
addon *can* do stays readable in one file.

Addons run in-process with qlsm's full authority (DB, SSH keys, cloud API
key). This context is an ergonomics and consistency boundary, not a security
one -- see addons/TRUST.md. Nothing here should be mistaken for a sandbox.
"""
import logging
import os
import sys
from functools import wraps

from ui.addons.hooks import validate_hook_name
from ui.addons.settings import AddonSettings


class AddonContext:
    """Handed to `register(ctx)` in an addon's backend.py."""

    def __init__(self, addon_id, manifest, root_dir, module_name=None):
        self.addon_id = addon_id
        self.manifest = manifest
        self.root_dir = root_dir
        # The synthetic module the addon's backend.py was loaded under. Needed
        # so registered tasks can be published as module attributes -- see
        # task() for why that is not optional.
        self.module_name = module_name
        self.settings = AddonSettings(addon_id, manifest)
        self.logger = logging.getLogger(f'qlsm.addon.{addon_id}')

        # Filled in by register(), consumed by the registry.
        self.blueprints = []
        self.tasks = {}
        self.handlers = {}   # hook name -> [callable]

    # ---- paths --------------------------------------------------------

    def path(self, *parts):
        """A path inside this addon's own directory.

        Refuses to escape it: an addon asking for '../../terraform/ssh-keys'
        is either buggy or hostile, and either way core should not help.
        """
        target = os.path.abspath(os.path.join(self.root_dir, *parts))
        root = os.path.abspath(self.root_dir)
        if target != root and not target.startswith(root + os.sep):
            raise ValueError(f'path escapes addon directory: {os.path.join(*parts)}')
        return target

    @property
    def playbooks_dir(self):
        return self.path('playbooks')

    @property
    def assets_dir(self):
        return self.path('assets')

    @property
    def plugins_dir(self):
        return self.path('plugins')

    @property
    def ui_dir(self):
        return self.path('ui')

    # ---- ansible --------------------------------------------------------

    def run_playbook(self, host, relative_path, extravars=None):
        """Run a playbook shipped in this addon's own playbooks/ directory
        against a host, e.g. ctx.run_playbook(host, 'sync_thing.yml').

        Delegates to core's own host-playbook runner, which already accepts
        an absolute path for exactly this purpose. Returns
        (success, stdout, stderr).
        """
        from ui.task_logic.ansible_runner import _run_host_ansible_playbook

        return _run_host_ansible_playbook(
            host, self.path('playbooks', relative_path), extravars=extravars,
        )

    # ---- notifications --------------------------------------------------

    def notify(self, severity, title, body='', link=None, key=None):
        """Store a notification under the navbar bell, from this addon.

        `severity` is 'info', 'warning' or 'critical'; `link` an in-app path
        such as '/addons/<id>'. With `key`, a repeat updates the open
        notification instead of adding another; resolve(key) closes it, and
        the next notify() with that key opens a new one. Keys are per addon.
        """
        from ui.notifications import notify

        return notify(self.addon_id, severity, title, body=body, link=link, key=key)

    def resolve(self, key):
        """Resolve this addon's open notification(s) with `key`; returns the count."""
        from ui.notifications import resolve

        return resolve(self.addon_id, key)

    # ---- registration -------------------------------------------------

    def blueprint(self, bp):
        """Register a Flask blueprint, mounted under /api/addons/<id>/.

        The prefix is applied by the registry, not by the addon, so an addon
        cannot mount itself anywhere else -- including on top of a core route.
        """
        self.blueprints.append(bp)
        return bp

    def task(self, func=None, *, timeout=300, lock_scope=None):
        """Register an RQ task.

        Wraps the addon's function the same way core's own tasks in
        ui/tasks.py are wrapped: app context, then a try/finally that releases
        the distributed lock. Doing it here rather than trusting the addon is
        deliberate -- a task that forgets to release its lock wedges every
        later operation on that host or instance until Redis expires the key.

        `lock_scope` is 'host' or 'instance'; when set, the wrapped task takes
        the matching id as its first positional argument and an optional
        `lock_token` kwarg, exactly like core's tasks do.
        """
        def decorator(fn):
            from ui import rq
            from ui.task_context import with_app_context

            @wraps(fn)
            def with_lock_release(*args, lock_token=None, **kwargs):
                try:
                    return fn(*args, **kwargs)
                finally:
                    if lock_token and lock_scope:
                        from ui.task_lock import release_lock
                        release_lock(lock_scope, args[0], lock_token)

            job = rq.job(timeout=timeout)(with_app_context(with_lock_release))

            # Publish the job as a module-level attribute of the addon's
            # backend module. This is load-bearing, not tidiness: RQ stores a
            # job as the dotted path "<module>.<function>" and re-imports it
            # in the worker. An addon registers its tasks *inside*
            # register(ctx), so the function is a closure whose qualname is
            # "register.<locals>.<name>" and which is not an attribute of the
            # module -- the worker would fail to resolve it and the job would
            # silently never run. Verified by experiment, not assumption; see
            # tests/test_addon_tasks_are_dequeuable.py.
            module = sys.modules.get(self.module_name) if self.module_name else None
            if module is not None:
                job.__qualname__ = fn.__name__
                setattr(module, fn.__name__, job)
            else:
                self.logger.error(
                    'Task %r registered without a resolvable module; it will '
                    'queue but never run.', fn.__name__,
                )

            self.tasks[fn.__name__] = job
            return job

        return decorator(func) if func is not None else decorator

    def on(self, hook, func=None):
        """Subscribe to a lifecycle hook. Unknown names raise immediately."""
        validate_hook_name(hook)

        def decorator(fn):
            self.handlers.setdefault(hook, []).append(fn)
            return fn

        return decorator(func) if func is not None else decorator
