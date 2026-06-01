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
