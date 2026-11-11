import json

from flask import current_app
from ui import db
from ui.models import Host, HostStatus
from rq import get_current_job
from ui.task_logic.ansible_runner import _run_host_ansible_playbook
from ui.task_logic.common import append_log

# Maps a key accepted in the `config` dict (host.watchdog_config JSON / API
# payload) to the ansible-playbook extra-var consumed by
# ansible/templates/ql-watchdog.service.j2. Keys not present here are ignored;
# keys present in `config` but not here are dropped before persisting.
_CONFIG_TO_EXTRAVAR = {
    'dryrun': 'watchdog_dryrun',
    'interval': 'watchdog_interval',
    'recvq_threshold': 'watchdog_recvq_threshold',
    'strikes': 'watchdog_strikes',
    'grace': 'watchdog_grace',
    'rate_max': 'watchdog_rate_max',
    'rate_window': 'watchdog_rate_window',
    'forensics': 'watchdog_forensics',
    'dead_confirm': 'watchdog_dead_confirm',
}


def enable_default_watchdog(host):
    """Turn ql-watchdog on with default settings as part of first-time host setup.

    A failure here never fails the setup: the host stays usable with the
    watchdog off and it can be enabled later from the host actions menu. The
    caller commits.
    """
    # Setup has uncommitted host changes by now. Reading the host's address for
    # the playbook would autoflush them and hold a SQLite write lock for the
    # whole SSH + apt run, so commit first (as _dispatch_addon_payload_sync does).
    db.session.commit()
    try:
        result = _run_host_ansible_playbook(
            host=host,
            playbook_name='configure_watchdog.yml',
            extravars={'watchdog_enabled': True},
        )
        success = bool(result and result[0])
    except Exception:
        current_app.logger.exception(f"Enabling ql-watchdog failed for host {host.name}.")
        success = False

    if success:
        host.watchdog_enabled = True
        host.watchdog_config = None
        append_log(host, "ql-watchdog enabled (on by default for new hosts).")
    else:
        current_app.logger.error(f"Could not enable ql-watchdog on new host {host.name}.")
        append_log(
            host,
            "Could not enable ql-watchdog. Host setup continues; enable it from "
            "Actions -> Configure Watchdog.",
        )
    return success


def configure_host_watchdog_logic(host_id, enabled, config=None):
    """
    Deploys/configures/removes the ql-watchdog addon on the host via Ansible.

    Args:
        host_id (int): The ID of the host.
        enabled (bool): Whether ql-watchdog should be running on this host.
        config (dict | None): Optional tunable overrides, see _CONFIG_TO_EXTRAVAR
            for accepted keys. Unknown keys are ignored.
    """
    host = db.session.get(Host, host_id)
    if not host:
        current_app.logger.error(f"Host {host_id} not found for watchdog configuration.")
        return False

    job = get_current_job()
    config = config or {}

    current_app.logger.info(
        f"Starting watchdog configuration for host: {host.name} (enabled={enabled}, config={config})"
    )

    extra_vars = {'watchdog_enabled': bool(enabled)}
    for key, extravar_name in _CONFIG_TO_EXTRAVAR.items():
        if key in config and config[key] is not None:
            extra_vars[extravar_name] = config[key]

    success, stdout_str, stderr_str = _run_host_ansible_playbook(
        host=host,
        playbook_name='configure_watchdog.yml',
        extravars=extra_vars
    )

    if success:
        current_app.logger.info(f"Successfully configured ql-watchdog for host {host.name}.")
        host.watchdog_enabled = bool(enabled)
        host.watchdog_config = json.dumps(config) if config else None
        host.status = HostStatus.ACTIVE
        host.logs = f"ql-watchdog configured successfully.\n{host.logs or ''}"
    else:
        current_app.logger.error(f"Failed to configure ql-watchdog for host {host.name}.")
        host.status = HostStatus.ERROR
        host.logs = f"ql-watchdog configuration failed.\n{host.logs or ''}"

    db.session.commit()
    return success
