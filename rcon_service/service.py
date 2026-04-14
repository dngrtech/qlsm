"""
RconService - Main service orchestrator.

Coordinates Redis Pub/Sub communication with ConnectionManager
to handle RCON commands from the Flask backend.
"""

import asyncio
import logging
import re
import os
import weakref
from datetime import datetime, timezone
from typing import Optional

REDIS_PREFIX = os.environ.get('REDIS_PREFIX', 'rcon')

from .connection_manager import ConnectionManager
from .redis_client import RedisClient

log = logging.getLogger(__name__)


class RconService:
    """Main RCON service orchestrator.
    
    This service:
    - Subscribes to Redis `rcon:cmd:*` channels for commands
    - Routes commands to ConnectionManager
    - Publishes responses and status updates to Redis
    """
    
    # Redis channel patterns
    CMD_PATTERN = f"{REDIS_PREFIX}:cmd:*"
    HOST_SHUTDOWN_PATTERN = f"{REDIS_PREFIX}:host:*:shutdown"
    RESPONSE_CHANNEL = f"{REDIS_PREFIX}:response:{{host_id}}:{{instance_id}}"
    STATUS_CHANNEL = f"{REDIS_PREFIX}:status:{{host_id}}:{{instance_id}}"
    STATS_CHANNEL = f"{REDIS_PREFIX}:stats:{{host_id}}:{{instance_id}}"
    
    def __init__(self, redis_url: Optional[str] = None):
        """Initialize RCON service.
        
        Args:
            redis_url: Redis connection URL (defaults to env var or localhost)
        """
        self._redis = RedisClient(redis_url)
        self._manager = ConnectionManager(
            on_message=self._handle_message,
            on_status_change=self._handle_status,
            on_stats=self._handle_stats
        )
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._instance_locks = weakref.WeakValueDictionary()
    
    def _get_lock(self, host_id: int, instance_id: int) -> asyncio.Lock:
        key = (host_id, instance_id)
        lock = self._instance_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._instance_locks[key] = lock
        return lock

    def _task_error_logger(self, task: asyncio.Task) -> None:
        try:
            exc = task.exception()
            if exc:
                log.error(f"Background task failed: {exc}", exc_info=exc)
        except asyncio.CancelledError:
            pass

    def _handle_message(self, host_id: int, instance_id: int, message: str) -> None:
        """Handle a message received from an RCON connection.
        
        Publishes to Redis rcon:response:{host_id}:{instance_id} channel.
        """
        task = asyncio.create_task(self._publish_message(host_id, instance_id, message))
        task.add_done_callback(self._task_error_logger)
    
    def _handle_status(self, host_id: int, instance_id: int, status: str) -> None:
        """Handle a status change from an RCON connection.
        
        Publishes to Redis rcon:status:{host_id}:{instance_id} channel.
        """
        task = asyncio.create_task(self._publish_status(host_id, instance_id, status))
        task.add_done_callback(self._task_error_logger)
    
    def _handle_stats(self, host_id: int, instance_id: int, event: dict) -> None:
        """Handle a stats event from the game server.
        
        Publishes to Redis rcon:stats:{host_id}:{instance_id} channel.
        """
        task = asyncio.create_task(self._publish_stats(host_id, instance_id, event))
        task.add_done_callback(self._task_error_logger)
    
    @staticmethod
    def _now_iso() -> str:
        """Return current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat()

    async def _publish_message(self, host_id: int, instance_id: int, message: str) -> None:
        """Publish a message response to Redis."""
        try:
            channel = self.RESPONSE_CHANNEL.format(host_id=host_id, instance_id=instance_id)
            await self._redis.publish(channel, {
                "type": "message",
                "host_id": host_id,
                "instance_id": instance_id,
                "content": message,
                "timestamp": self._now_iso()
            })
        except Exception as e:
            log.error(f"Failed to publish message: {e}")

    async def _publish_status(self, host_id: int, instance_id: int, status: str) -> None:
        """Publish a status update to Redis."""
        try:
            channel = self.STATUS_CHANNEL.format(host_id=host_id, instance_id=instance_id)
            await self._redis.publish(channel, {
                "type": "status",
                "host_id": host_id,
                "instance_id": instance_id,
                "status": status,
                "timestamp": self._now_iso()
            })
        except Exception as e:
            log.error(f"Failed to publish status: {e}")

    async def _publish_stats(self, host_id: int, instance_id: int, event: dict) -> None:
        """Publish a stats event to Redis."""
        try:
            channel = self.STATS_CHANNEL.format(host_id=host_id, instance_id=instance_id)
            payload = {**event, "timestamp": self._now_iso()}
            await self._redis.publish(channel, payload)
        except Exception as e:
            log.error(f"Failed to publish stats: {e}")
    
    def _parse_cmd_channel(self, channel: str) -> Optional[tuple[int, int]]:
        """Parse host_id and instance_id from command channel name.

        Channel format: {REDIS_PREFIX}:cmd:{host_id}:{instance_id}

        Returns:
            Tuple of (host_id, instance_id) or None if parse fails
        """
        match = re.match(rf'{REDIS_PREFIX}:cmd:(\d+):(\d+)', channel)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None

    def _parse_host_shutdown_channel(self, channel: str) -> Optional[int]:
        """Parse host_id from host shutdown channel name.

        Channel format: {REDIS_PREFIX}:host:{host_id}:shutdown

        Returns:
            host_id or None if parse fails
        """
        match = re.match(rf'{REDIS_PREFIX}:host:(\d+):shutdown', channel)
        if match:
            return int(match.group(1))
        return None
    
    async def _process_command_queued(self, channel: str, data: dict) -> None:
        parsed = self._parse_cmd_channel(channel)
        if not parsed:
            log.error(f"Invalid channel format: {channel}")
            return
            
        host_id, instance_id = parsed
        action = data.get("action", "unknown")
        
        lock = self._get_lock(host_id, instance_id)
        
        # We explicitly log here to help debugging concurrency
        log.debug(f"[{host_id}:{instance_id}] Waiting for lock to process action: {action}")
        
        async with lock:
            log.debug(f"[{host_id}:{instance_id}] Acquired lock for action: {action}")
            try:
                await self._process_command(host_id, instance_id, data)
            except Exception as e:
                log.exception(f"[{host_id}:{instance_id}] Error processing action '{action}': {e}")
            finally:
                log.debug(f"[{host_id}:{instance_id}] Released lock after action: {action}")

    async def _process_command(self, host_id: int, instance_id: int, data: dict) -> None:
        """Process a command received from Redis.
        
        Commands:
        - connect: {action: "connect", ip, rcon_port, rcon_password}
        - disconnect: {action: "disconnect"}
        - command: {action: "command", cmd: "..."}
        """
        action = data.get("action")
        
        log.debug(f"Processing {action} for {host_id}:{instance_id}")
        
        if action == "connect":
            ip = data.get("ip")
            rcon_port = data.get("rcon_port")
            rcon_password = data.get("rcon_password")
            self_host = bool(data.get("self_host"))
            
            if not all([ip, rcon_port, rcon_password]):
                log.error(f"Missing connection details for {host_id}:{instance_id}")
                await self._publish_status(host_id, instance_id, "error")
                return
            
            await self._manager.connect(
                host_id, instance_id, ip, int(rcon_port), rcon_password, self_host
            )
        
        elif action == "disconnect":
            await self._manager.disconnect(host_id, instance_id)
        
        elif action == "command":
            cmd = data.get("cmd")
            if cmd:
                await self._manager.send_command(host_id, instance_id, cmd)
            else:
                log.error(f"No command provided for {host_id}:{instance_id}")
        
        elif action == "disconnect_host":
            instances = self._manager.get_instances_for_host(host_id)
            for inst_id in instances:
                # The lock for (host_id, instance_id) is already held by _process_command_queued —
                # re-acquiring it here would deadlock (asyncio.Lock is not re-entrant).
                if inst_id == instance_id:
                    await self._manager.disconnect(host_id, inst_id)
                else:
                    async with self._get_lock(host_id, inst_id):
                        await self._manager.disconnect(host_id, inst_id)
        
        elif action == "subscribe_stats":
            ip = data.get("ip")
            stats_port = data.get("stats_port")
            stats_password = data.get("stats_password")
            if stats_port:
                await self._manager.subscribe_stats(
                    host_id, instance_id, ip, int(stats_port), stats_password
                )
            else:
                log.error(f"No stats_port provided for {host_id}:{instance_id}")
        
        elif action == "unsubscribe_stats":
            await self._manager.unsubscribe_stats(host_id, instance_id)
        
        else:
            log.warning(f"Unknown action: {action}")
    
    async def _process_host_shutdown(self, channel: str, data: dict) -> None:
        """Process a host shutdown signal.

        Disconnects all RCON connections for the specified host.
        """
        host_id = self._parse_host_shutdown_channel(channel)
        if host_id is None:
            log.error(f"Invalid host shutdown channel format: {channel}")
            return

        reason = data.get("reason", "unknown")
        log.info(f"Host shutdown signal for host {host_id} (reason: {reason})")
        
        instances = self._manager.get_instances_for_host(host_id)
        for inst_id in instances:
            lock = self._get_lock(host_id, inst_id)
            async with lock:
                try:
                    await self._manager.disconnect(host_id, inst_id)
                except Exception as e:
                    log.error(f"Error disconnecting {host_id}:{inst_id}: {e}")

    async def run(self) -> None:
        """Run the RCON service main loop."""
        self._running = True
        log.info("RCON Service starting...")

        try:
            # Connect to Redis
            await self._redis.connect()
            log.info("Connected to Redis, starting command listener...")

            # Subscribe to command and host shutdown channels
            async for message in self._redis.subscribe_pattern(
                self.CMD_PATTERN, self.HOST_SHUTDOWN_PATTERN
            ):
                if not self._running:
                    break

                channel = message['channel']
                pattern = message.get('pattern', '')
                data = message['data']

                # Route based on matched subscription pattern
                if pattern == self.HOST_SHUTDOWN_PATTERN:
                    task = asyncio.create_task(self._process_host_shutdown(channel, data))
                    task.add_done_callback(self._task_error_logger)
                else:
                    task = asyncio.create_task(self._process_command_queued(channel, data))
                    task.add_done_callback(self._task_error_logger)

        except asyncio.CancelledError:
            log.info("RCON Service cancelled")
        except Exception as e:
            log.exception(f"RCON Service error: {e}")
        finally:
            self._running = False
    
    async def shutdown(self) -> None:
        """Shutdown the RCON service gracefully."""
        if not self._running:
            return
        log.info("Shutting down RCON Service...")
        self._running = False
        
        # Disconnect all RCON connections
        await self._manager.disconnect_all()
        
        # Disconnect from Redis
        await self._redis.disconnect()
        
        log.info("RCON Service shutdown complete")
