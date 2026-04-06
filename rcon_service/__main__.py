#!/usr/bin/env python3
"""
Entry point for running rcon_service as a module.

Usage:
    python -m rcon_service
"""

import asyncio
import logging
import signal
import sys

from .service import RconService

import os

# Configure logging
log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
log_format = os.environ.get("LOG_FORMAT", "text")

if log_format == "json":
    from pythonjsonlogger.json import JsonFormatter
    formatter = JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(module)s %(message)s',
        rename_fields={
            'levelname': 'level',
            'name': 'logger',
            'asctime': 'timestamp',
        },
    )
else:
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logging.basicConfig(level=log_level, handlers=[handler])

log = logging.getLogger(__name__)


def main():
    """Main entry point for the RCON service."""
    log.info("Starting QLDS RCON Service...")
    
    service = RconService()
    
    # Set up signal handlers for graceful shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def shutdown_handler():
        log.info("Received shutdown signal, stopping service...")
        loop.create_task(service.shutdown())
    
    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_handler)
    
    try:
        loop.run_until_complete(service.run())
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        loop.run_until_complete(service.shutdown())
        loop.close()
        log.info("RCON Service stopped.")


if __name__ == "__main__":
    main()
