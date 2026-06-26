import signal
import threading
import logging
import click

logger = logging.getLogger(__name__)

POLL_INTERVAL = 15  # seconds


def register_cli_commands(app):
    @app.cli.command('run-status-poller')
    def run_status_poller():
        """Daemon: polls game server status from game host Redis via SSH every 15s."""
        from ui.task_logic.server_status_poll import poll_all_hosts

        stop_event = threading.Event()

        def _handle_signal(signum, frame):
            logger.info("Received signal %s — shutting down status poller", signum)
            stop_event.set()

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        logger.info("Status poller started (interval=%ds)", POLL_INTERVAL)
        while not stop_event.is_set():
            try:
                poll_all_hosts()
            except Exception as e:
                logger.error(f"Poll cycle failed: {e}", exc_info=True)
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
        import sys
        from ui import db
        from ui.models import QLInstance, InstanceStatus
        from ui.task_logic.ansible_instance_mgmt import stop_instance_logic

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
                # containing "stop successful" and leaves status STOPPED, on failure
                # it returns an "Error..." string and persists ERROR.
                ok = isinstance(result, str) and "stop successful" in result
            except Exception as e:
                logger.error(
                    "reconcile-service-enablement: exception for instance %s: %s",
                    inst.id, e, exc_info=True,
                )

            if ok:
                succeeded.append(inst.id)
            else:
                failed.append(inst.id)
                # Never leave a deliberately-stopped instance as ERROR.
                if inst.status != InstanceStatus.STOPPED:
                    inst.status = InstanceStatus.STOPPED
                    db.session.commit()
                logger.error(
                    "reconcile-service-enablement: instance %s could not be "
                    "reconciled; restored to STOPPED", inst.id,
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
