"""Gunicorn configuration for QLDS UI.

Solves the pre-fork deadlock: gunicorn master calls create_app() which
would start background threads (SocketIO Redis manager, RCON Redis listener).
When master then forks the worker, threads don't survive but their locks
may be inherited in a locked state, causing an intermittent deadlock.

Fix: post_fork sets _GUNICORN_WORKER=1 before the worker calls load_wsgi()
(which calls create_app()). create_app() checks this env var and runs the
full SocketIO + RedisListener init only in workers, not in the master.
"""

import os
import logging


def post_fork(server, worker):
    """Signal to create_app() that this process is a gunicorn worker.

    post_fork fires before load_wsgi() / create_app(), so worker.app.callable
    is None here — do NOT access it. Just set the env var so that when the
    worker calls create_app() it takes the worker path (full SocketIO init).
    """
    os.environ['_GUNICORN_WORKER'] = '1'


def worker_exit(server, worker):
    """Log worker exit details for debugging exit code 255 crashes."""
    log = logging.getLogger('gunicorn.error')
    log.info("Worker (pid:%s) exiting. Exit code: %s", worker.pid, worker.exitcode)
