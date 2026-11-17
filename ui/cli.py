import signal
import sys
import threading
import time
import logging
import click

logger = logging.getLogger(__name__)

POLL_INTERVAL = 15  # seconds
RUNTIME_UPGRADE_RECONCILE_INTERVAL = 60  # seconds; the first pass is the startup sweep
# A slow poller.tick handler is logged by addon id in ui.addons.registry.dispatch.


def register_cli_commands(app):
    @app.cli.command('run-status-poller')
    def run_status_poller():
        """Daemon: polls game server status from game host Redis via SSH every 15s."""
        from ui import db
        from ui.addons import dispatch
        from ui.task_logic.interrupted_job_recovery import reconcile_stale_instance_jobs
        from ui.task_logic.server_status_poll import poll_all_hosts
        from ui.task_logic.host_runtime_upgrade_recovery import reconcile_runtime_upgrades

        stop_event = threading.Event()

        def _handle_signal(signum, frame):
            logger.info("Received signal %s — shutting down status poller", signum)
            stop_event.set()

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        logger.info("Status poller started (interval=%ds)", POLL_INTERVAL)
        last_upgrade_reconcile = None
        while not stop_event.is_set():
            if (last_upgrade_reconcile is None
                    or time.monotonic() - last_upgrade_reconcile >= RUNTIME_UPGRADE_RECONCILE_INTERVAL):
                last_upgrade_reconcile = time.monotonic()
                try:
                    reconcile_runtime_upgrades()
                except Exception as e:
                    logger.error(f"Runtime upgrade reconcile failed: {e}", exc_info=True)
                    db.session.rollback()
            try:
                poll_all_hosts()
            except Exception as e:
                logger.error(f"Poll cycle failed: {e}", exc_info=True)
            try:
                reconcile_stale_instance_jobs()
            except Exception as e:
                logger.error(f"Stale instance job reconcile failed: {e}", exc_info=True)
            try:
                dispatch('poller.tick')
            except Exception as e:
                logger.error(f"poller.tick dispatch failed: {e}", exc_info=True)
            # dispatch() swallows handler errors, so a handler that left this
            # process's one session needing a rollback would otherwise break
            # every later poll cycle. Handlers commit their own work.
            try:
                db.session.rollback()
            except Exception as e:
                logger.error(f"Session rollback after poller.tick failed: {e}", exc_info=True)
            stop_event.wait(POLL_INTERVAL)
        logger.info("Status poller stopped")

    @app.cli.command('recover-rebooting-hosts')
    def recover_rebooting_hosts():
        """Transition REBOOTING hosts to ACTIVE on startup (self-host reboot recovery)."""
        from ui import db
        from ui.models import Host, HostStatus
        from ui.task_logic.common import append_log

        try:
            hosts = Host.query.filter_by(status=HostStatus.REBOOTING).all()
            if not hosts:
                logger.info("recover-rebooting-hosts: no hosts in REBOOTING state")
                return

            for host in hosts:
                host.status = HostStatus.ACTIVE
                append_log(host, "Recovered from interrupted reboot on startup.")
                logger.info("recover-rebooting-hosts: recovered host %s", host.name)

            db.session.commit()
            logger.info("recover-rebooting-hosts: recovered %d host(s)", len(hosts))
        except Exception as e:
            logger.error("recover-rebooting-hosts: failed: %s", e, exc_info=True)

    @app.cli.command('reconcile-service-enablement')
    def reconcile_service_enablement():
        """Disable systemd units for STOPPED instances so they stay down on reboot.

        Backfill for the stop-disables-unit fix. Idempotent; safe to re-run.

        Never worsens DB state: stop_instance_logic persists ERROR (and returns an
        error string rather than raising) on any failure, so a STOPPED instance on an
        unreachable/rebooting host would otherwise be silently downgraded. This loop
        treats a non-success return as a failure, restores the instance to STOPPED,
        tallies results, and exits non-zero if any instance could not be reconciled.

        Preconditions: run only after the updated manage_qlds_service.yml is live on
        this host, and ideally when target hosts are reachable.
        """
        from ui import db
        from ui.models import QLInstance, InstanceStatus
        from ui.task_logic.ansible_instance_mgmt import (
            stop_instance_logic,
            STOP_SUCCESS_MARKER,
        )

        stopped = QLInstance.query.filter_by(status=InstanceStatus.STOPPED).all()
        if not stopped:
            logger.info("reconcile-service-enablement: no STOPPED instances")
            return

        succeeded, failed = [], []
        for inst in stopped:
            logger.info(
                "reconcile-service-enablement: disabling unit for instance %s (port %s)",
                inst.id, inst.port,
            )
            ok = False
            try:
                result = stop_instance_logic(inst.id)
                # stop_instance_logic never raises; on success it returns a string
                # containing STOP_SUCCESS_MARKER and leaves status STOPPED, on failure
                # it returns an "Error..." string and persists ERROR.
                ok = isinstance(result, str) and STOP_SUCCESS_MARKER in result
            except Exception as e:
                logger.error(
                    "reconcile-service-enablement: exception for instance %s: %s",
                    inst.id, e, exc_info=True,
                )

            if ok:
                succeeded.append(inst.id)
            else:
                inst_id = inst.id
                failed.append(inst_id)
                # Never leave a deliberately-stopped instance as ERROR. Re-fetch so the
                # restore does not depend on the identity map reflecting a commit made
                # inside stop_instance_logic. The instance may be gone (deleted mid-run),
                # so log via the saved id, not inst.
                inst = db.session.get(QLInstance, inst_id)
                if inst is not None and inst.status != InstanceStatus.STOPPED:
                    inst.status = InstanceStatus.STOPPED
                    db.session.commit()
                logger.error(
                    "reconcile-service-enablement: instance %s could not be "
                    "reconciled; restored to STOPPED", inst_id,
                )

        logger.info(
            "reconcile-service-enablement: %d succeeded, %d failed (of %d STOPPED)",
            len(succeeded), len(failed), len(stopped),
        )
        if failed:
            logger.error(
                "reconcile-service-enablement: failed instances: %s", failed
            )
            sys.exit(1)
