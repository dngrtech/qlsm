"""Resolve user LD_PRELOAD hook filenames to their on-disk source path
plus the matching host runtime subdirectory.

A user hook may live in two places during the cutover:
  * configs/<host>/<id>/user-hooks/  -> /home/ql/qlds-<port>/user-hooks/
  * configs/<host>/<id>/scripts/     -> /home/ql/qlds-<port>/<runtime plugins dir>/  (legacy)
"""
import os

from ui.runtime import DEFAULT_RUNTIME, runtime_paths


CONFIGS_BASE = "configs"


def resolve_user_hook(configs_base, host_name, instance_id, filename,
                      runtime=DEFAULT_RUNTIME):
    inst_dir = os.path.join(configs_base, host_name, str(instance_id))
    legacy_subdir = runtime_paths(runtime)['plugins_dirname']
    candidates = (
        (os.path.join(inst_dir, "user-hooks", filename), "user-hooks"),
        (os.path.join(inst_dir, "scripts", filename), legacy_subdir),
    )
    for source, host_subdir in candidates:
        if os.path.isfile(source):
            return {"source": source, "host_subdir": host_subdir}
    return None


def user_hooks_dir(instance, configs_base=None):
    base = configs_base or CONFIGS_BASE
    return os.path.join(base, instance.host.name, str(instance.id), "user-hooks")


def draft_user_hooks_dir(draft_id):
    from flask import current_app
    drafts_base = current_app.config.get("DRAFTS_BASE", "/tmp/qlds-drafts")
    return os.path.join(drafts_base, draft_id, "user-hooks")
