"""
StatsConnection - Manages ZMQ SUB socket for game statistics.

Connects to the QLDS stats socket and receives real-time game events
like player deaths, team switches, round ends, etc.
"""

import asyncio
import json
import logging
from typing import Callable, Optional

import zmq
import zmq.asyncio

log = logging.getLogger(__name__)


class StatsConnection:
    """Manages ZMQ SUB socket for game statistics from a QLDS instance.
    
    This class handles:
    - ZMQ SUB socket with PLAIN authentication
    - Subscribing to all game event topics
    - Parsing JSON event messages
    - Publishing events via callback
    """
    
    def __init__(
        self,
        host_id: int,
        instance_id: int,
        zmq_context: Optional[zmq.asyncio.Context] = None,
        on_event: Optional[Callable[[int, int, dict], None]] = None
    ):
        """Initialize stats connection.

        Args:
            host_id: Database ID of the host
            instance_id: Database ID of the instance
            zmq_context: Shared ZMQ context (if None, creates its own)
            on_event: Callback for events (host_id, instance_id, event_data)
        """
        self.host_id = host_id
        self.instance_id = instance_id
        self.on_event = on_event

        self._shared_context = zmq_context is not None
        self._context: Optional[zmq.asyncio.Context] = zmq_context
        self._socket: Optional[zmq.asyncio.Socket] = None
        self._connected: bool = False
        self._recv_task: Optional[asyncio.Task] = None
        self._shutdown: bool = False
    
    @property
    def connected(self) -> bool:
        """Return connection status."""
        return self._connected
    
    async def connect(self, ip: str, stats_port: int, stats_password: str) -> bool:
        """Connect to QLDS stats socket.
        
        From C++ QLRcon.cpp (lines 2690-2778):
        - ZMQ SUB socket
        - PLAIN auth with username="stats"
        - ZAP domain="stats"
        - Subscribe to all topics (empty prefix)
        
        Args:
            ip: Server IP address
            stats_port: Stats port (typically rcon_port + 1000)
            stats_password: Stats password (same as RCON password for QLDS)
            
        Returns:
            True if connection successful
        """
        if self._connected:
            log.warning(f"[{self.host_id}:{self.instance_id}] Stats already connected")
            return True
        
        try:
            log.debug(f"[{self.host_id}:{self.instance_id}] Connecting stats to {ip}:{stats_port}")
            
            # Use shared context or create one
            if not self._context:
                self._context = zmq.asyncio.Context()
            self._socket = self._context.socket(zmq.SUB)
            
            # PLAIN authentication
            self._socket.plain_username = b"stats"
            pass_bytes = stats_password.encode('utf-8') if stats_password else b""
            self._socket.plain_password = pass_bytes
            # self._socket.zap_domain = b"stats"  # Removed: caused Invalid argument on client side
            
            # Socket settings
            self._socket.setsockopt(zmq.LINGER, 0)
            
            # Subscribe to all topics
            self._socket.subscribe(b"")
            
            # Connect
            endpoint = f"tcp://{ip}:{stats_port}"
            self._socket.connect(endpoint)
            
            self._connected = True
            self._shutdown = False
            
            # Start receive loop
            self._recv_task = asyncio.create_task(self._recv_loop())
            
            log.debug(f"[{self.host_id}:{self.instance_id}] Stats connected")
            return True
            
        except Exception as e:
            log.error(f"[{self.host_id}:{self.instance_id}] Stats connection failed: {e}")
            await self.disconnect()
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from stats socket."""
        self._shutdown = True
        self._connected = False
        
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None
        
        if self._socket:
            try:
                self._socket.close()
            except Exception as e:
                log.warning(f"Error closing stats socket: {e}")
            self._socket = None
        
        # Only terminate context if we own it (not shared)
        if self._context and not self._shared_context:
            try:
                self._context.term()
            except Exception as e:
                log.warning(f"Error terminating stats context: {e}")
            self._context = None
        
        log.debug(f"[{self.host_id}:{self.instance_id}] Stats disconnected")
    
    async def _recv_loop(self) -> None:
        """Background task to receive stats events."""
        log.debug(f"[{self.host_id}:{self.instance_id}] Starting stats receive loop")
        
        while not self._shutdown and self._socket:
            try:
                if await self._socket.poll(timeout=1000):
                    raw = await self._socket.recv()
                    self._handle_event(raw)
            except zmq.ZMQError as e:
                self._connected = False
                if not self._shutdown:
                    log.error(f"[{self.host_id}:{self.instance_id}] Stats ZMQ error: {e}")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                if not self._shutdown:
                    log.error(f"[{self.host_id}:{self.instance_id}] Stats receive error: {e}")
                break

        log.debug(f"[{self.host_id}:{self.instance_id}] Stats receive loop ended")
    
    def _handle_event(self, raw: bytes) -> None:
        """Parse and emit a stats event.
        
        QLDS sends stats events as JSON with a type field.
        Common events: PLAYER_DEATH, PLAYER_SWITCHTEAM, ROUND_OVER, etc.
        """
        try:
            text = raw.decode('utf-8', errors='replace')
            event = json.loads(text)
            
            log.debug(f"[{self.host_id}:{self.instance_id}] Stats event: {event.get('TYPE', 'unknown')}")
            
            if self.on_event:
                self.on_event(self.host_id, self.instance_id, event)
                
        except json.JSONDecodeError:
            log.warning(f"[{self.host_id}:{self.instance_id}] Invalid stats JSON: {raw[:100]}")
        except Exception as e:
            log.error(f"[{self.host_id}:{self.instance_id}] Error handling stats event: {e}")
