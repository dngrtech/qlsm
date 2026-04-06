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
