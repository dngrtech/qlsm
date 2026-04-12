"""
ConnectionManager - Manages all active RCON connections.

Provides a central point for managing multiple InstanceConnection objects,
routing commands to the correct instance, and coordinating shutdown.
"""

import asyncio
import logging
from typing import Callable, Dict, Optional, Tuple

import zmq.asyncio

from .instance_connection import InstanceConnection

log = logging.getLogger(__name__)

# Type alias for connection key (host_id, instance_id)
ConnectionKey = Tuple[int, int]


class ConnectionManager:
    """Manages all active RCON connections.
    
    This class:
    - Maintains a registry of active connections
    - Routes commands to the correct InstanceConnection
    - Handles connection/disconnection requests
    - Provides callbacks for message and status updates
    """
    
    def __init__(
        self,
        on_message: Optional[Callable[[int, int, str], None]] = None,
        on_status_change: Optional[Callable[[int, int, str], None]] = None,
        on_stats: Optional[Callable[[int, int, dict], None]] = None
    ):
        """Initialize connection manager.
        
        Args:
            on_message: Callback for received messages (host_id, instance_id, message)
            on_status_change: Callback for status changes (host_id, instance_id, status)
            on_stats: Callback for stats events (host_id, instance_id, event_dict)
        """
        self._connections: Dict[ConnectionKey, InstanceConnection] = {}
        self._on_message = on_message
        self._on_status_change = on_status_change
        self._on_stats = on_stats
        self._lock = asyncio.Lock()
        self._zmq_context = zmq.asyncio.Context()
    
    def _get_key(self, host_id: int, instance_id: int) -> ConnectionKey:
        """Generate connection key from host and instance IDs."""
        return (host_id, instance_id)
    
    def get_connection(self, host_id: int, instance_id: int) -> Optional[InstanceConnection]:
        """Get an existing connection.
        
        Args:
            host_id: Host database ID
            instance_id: Instance database ID
            
        Returns:
            InstanceConnection if exists, None otherwise
        """
        key = self._get_key(host_id, instance_id)
        return self._connections.get(key)
    
    def is_connected(self, host_id: int, instance_id: int) -> bool:
        """Check if an instance is connected.
        
        Args:
            host_id: Host database ID
            instance_id: Instance database ID
            
        Returns:
            True if connected, False otherwise
        """
        conn = self.get_connection(host_id, instance_id)
        return conn is not None and conn.connected
    
    async def connect(
        self,
        host_id: int,
        instance_id: int,
        ip: str,
        rcon_port: int,
        rcon_password: str,
        self_host: bool = False,
    ) -> bool:
        """Connect to a QLDS instance.
        
        If already connected, returns True without reconnecting.
        
        Args:
            host_id: Host database ID
            instance_id: Instance database ID
            ip: Server IP address
            rcon_port: RCON port
            rcon_password: RCON password
            self_host: Whether this is a self-host deployment target
            
        Returns:
            True if connection successful or already connected
        """
        key = self._get_key(host_id, instance_id)
        
        async with self._lock:
            # Check if already connected
            existing = self._connections.get(key)
            if existing:
                if existing.connected:
                    log.debug(f"Already connected to {host_id}:{instance_id}")
                    return True
                else:
                    log.info(f"[{host_id}:{instance_id}] Found stale connection object. Disconnecting before replacing.")
                    try:
                        await existing.disconnect()
                    except Exception as e:
                        log.warning(f"[{host_id}:{instance_id}] Error cleaning up stale connection: {e}")
            
            # Ensure shared ZMQ context exists (may have been terminated by disconnect_all)
            if self._zmq_context is None:
                self._zmq_context = zmq.asyncio.Context()
                log.info("Re-created shared ZMQ context")

            # Create new connection with shared ZMQ context
            conn = InstanceConnection(
                host_id=host_id,
                instance_id=instance_id,
                zmq_context=self._zmq_context,
                on_message=self._on_message,
                on_status_change=self._on_status_change,
                on_stats=self._on_stats
            )
            
            # Attempt connection
            success = await conn.connect(ip, rcon_port, rcon_password, self_host=self_host)
            
            if success:
                self._connections[key] = conn
                log.debug(f"Connection established for {host_id}:{instance_id}")
            else:
                log.error(f"Failed to connect to {host_id}:{instance_id}")
            
            return success
    
    async def disconnect(self, host_id: int, instance_id: int) -> None:
        """Disconnect from a specific instance.
        
        Args:
            host_id: Host database ID
            instance_id: Instance database ID
        """
        key = self._get_key(host_id, instance_id)
        
        async with self._lock:
            conn = self._connections.pop(key, None)
            if conn:
                await conn.disconnect()
                log.debug(f"Disconnected from {host_id}:{instance_id}")
    
    def get_instances_for_host(self, host_id: int) -> list[int]:
        """Get all known instance IDs for a host.
        
        Args:
            host_id: Host database ID
            
        Returns:
            List of instance IDs currently tracked for this host
        """
        # safe dict list copy due to GIL, keys are tuples (host_id, instance_id)
        return [key[1] for key in list(self._connections.keys()) if key[0] == host_id]

    async def disconnect_host(self, host_id: int) -> None:
        """Disconnect all instances on a host.
        
        Args:
            host_id: Host database ID
        """
        async with self._lock:
            keys_to_remove = [
                key for key in self._connections 
                if key[0] == host_id
            ]
            conns_to_remove = [self._connections.pop(key) for key in keys_to_remove]
            
        # Disconnect outside the lock to prevent blocking concurrent tasks
        for key, conn in zip(keys_to_remove, conns_to_remove):
            await conn.disconnect()
            log.debug(f"Disconnected from {key[0]}:{key[1]}")
    
    async def disconnect_all(self) -> None:
        """Disconnect all connections and terminate shared ZMQ context."""
        async with self._lock:
            conns = list(self._connections.items())
            self._connections.clear()

        # Disconnect outside the lock
        for key, conn in conns:
            await conn.disconnect()
            log.debug(f"Disconnected from {key[0]}:{key[1]}")

        if self._zmq_context:
            try:
                self._zmq_context.term()
            except Exception as e:
                log.warning(f"Error terminating shared ZMQ context: {e}")
            self._zmq_context = None
    
    async def send_command(
        self,
        host_id: int,
        instance_id: int,
        command: str
    ) -> bool:
        """Send an RCON command to an instance.
        
        Args:
            host_id: Host database ID
            instance_id: Instance database ID
            command: The command to send
            
        Returns:
            True if command was sent successfully
            
        NOTE: send_command and async I/O are coordinated safely via RconService's 
        per-instance locks. We explicitly avoid holding ConnectionManager._lock 
        across async ZMQ I/O here to prevent starving other instances.
        """
        conn = self.get_connection(host_id, instance_id)
        
        if not conn or not conn.connected:
            log.error(f"Cannot send command: {host_id}:{instance_id} not connected")
            return False
        
        return await conn.send(command)
    
    async def subscribe_stats(
        self,
        host_id: int,
        instance_id: int,
        ip: str,
        stats_port: int,
        stats_password: Optional[str] = None
    ) -> None:
        """Subscribe to stats events for an instance.
        
        Args:
            host_id: Host database ID
            instance_id: Instance database ID
            ip: Server IP address
            stats_port: ZMQ stats port
            stats_password: Stats socket password
        """
        conn = self.get_connection(host_id, instance_id)
        if conn:
            await conn.subscribe_stats(ip, stats_port, stats_password)
            log.debug(f"Subscribed to stats for {host_id}:{instance_id}")
        else:
            log.warning(f"Cannot subscribe stats: {host_id}:{instance_id} not connected")
    
    async def unsubscribe_stats(self, host_id: int, instance_id: int) -> None:
        """Unsubscribe from stats events for an instance.
        
        Args:
            host_id: Host database ID
            instance_id: Instance database ID
        """
        conn = self.get_connection(host_id, instance_id)
        if conn:
            await conn.unsubscribe_stats()
            log.debug(f"Unsubscribed from stats for {host_id}:{instance_id}")
    
    def get_all_connections(self) -> Dict[ConnectionKey, InstanceConnection]:
        """Get all active connections.
        
        Returns:
            Dict mapping (host_id, instance_id) to InstanceConnection
        """
        return dict(self._connections)
    
    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self._connections)
