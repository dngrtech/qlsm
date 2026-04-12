"""
InstanceConnection - Manages ZMQ sockets for a single QLDS instance.

Ported from C++ Quake-Live-Rcon QLRcon.cpp connectToServer function.
Uses ZMQ DEALER socket with PLAIN authentication for RCON commands.
"""

import asyncio
import logging
import uuid
from typing import Callable, Optional

import zmq
import zmq.asyncio

from .message_parser import parse_rcon_message
from .stats_connection import StatsConnection

log = logging.getLogger(__name__)


class InstanceConnection:
    """Manages ZMQ RCON connection to a single QLDS instance.
    
    This class handles:
    - ZMQ DEALER socket setup with PLAIN authentication
    - Connection lifecycle (connect, register, disconnect)
    - Sending commands and receiving responses
    - Publishing responses via callback
    """
    
    def __init__(
        self,
        host_id: int,
        instance_id: int,
        zmq_context: Optional[zmq.asyncio.Context] = None,
        on_message: Optional[Callable[[int, int, str], None]] = None,
        on_status_change: Optional[Callable[[int, int, str], None]] = None,
        on_stats: Optional[Callable[[int, int, dict], None]] = None
    ):
        """Initialize connection.

        Args:
            host_id: Database ID of the host
            instance_id: Database ID of the instance
            zmq_context: Shared ZMQ context (if None, creates its own)
            on_message: Callback for received messages (host_id, instance_id, message)
            on_status_change: Callback for status changes (host_id, instance_id, status)
            on_stats: Callback for stats events (host_id, instance_id, event_dict)
        """
        self.host_id = host_id
        self.instance_id = instance_id
        self.on_message = on_message
        self.on_status_change = on_status_change
        self.on_stats = on_stats

        self._shared_context = zmq_context is not None
        self._context: Optional[zmq.asyncio.Context] = zmq_context
        self._socket: Optional[zmq.asyncio.Socket] = None
        self._identity: str = ""
        self._connected: bool = False
        self._recv_task: Optional[asyncio.Task] = None
        self._shutdown: bool = False
        
        # Stats connection (optional)
        self._stats_connection: Optional[StatsConnection] = None
    
    @property
    def connected(self) -> bool:
        """Return connection status."""
        return self._connected
    
    def _emit_status(self, status: str) -> None:
        """Emit a status change event."""
        log.debug(f"[{self.host_id}:{self.instance_id}] Status: {status}")
        if self.on_status_change:
            try:
                self.on_status_change(self.host_id, self.instance_id, status)
            except Exception as e:
                log.error(f"Error in status callback: {e}")
    
    def _emit_message(self, message: str) -> None:
        """Emit a received message event."""
        log.debug(f"[{self.host_id}:{self.instance_id}] Message: {message[:100]}...")
        if self.on_message:
            try:
                self.on_message(self.host_id, self.instance_id, message)
            except Exception as e:
                log.error(f"Error in message callback: {e}")
    
    async def connect(self, ip: str, rcon_port: int, rcon_password: str) -> bool:
        """Connect to QLDS instance via ZMQ DEALER socket.
        
        Based on C++ QLRcon.cpp connectToServer():
        - Creates ZMQ DEALER socket
        - Sets PLAIN authentication (username="rcon", password from config)
        - Sets ZAP domain to "rcon"
        - Sets identity to UUID
        - Connects to tcp://{ip}:{port}
        - Sends "register" command after connection
        
        Args:
            ip: Server IP address
            rcon_port: RCON port (typically 28960+)
            rcon_password: RCON password for PLAIN auth
            
        Returns:
            True if connection successful, False otherwise
        """
        if self._connected:
            log.warning(f"[{self.host_id}:{self.instance_id}] Already connected")
            return True
        
        try:
            self._emit_status("connecting")
            
            # Use shared context or create one
            if not self._context:
                self._context = zmq.asyncio.Context()
            self._socket = self._context.socket(zmq.DEALER)
            
            # Set socket options (from C++ connectToServer)
            # PLAIN authentication
            self._socket.plain_username = b"rcon"
            self._socket.plain_password = rcon_password.encode('utf-8')
            self._socket.zap_domain = b"rcon"
            
            # Fresh UUID identity per connection — QLDS ignores reconnections
            # with the same identity, so we must use a new one each time
            self._identity = str(uuid.uuid4())
            self._socket.identity = self._identity.encode('utf-8')
            
            # Connection settings - no receive timeout, we'll use poll instead
            self._socket.setsockopt(zmq.LINGER, 0)
            self._socket.setsockopt(zmq.SNDTIMEO, 5000)
            self._socket.setsockopt(zmq.IMMEDIATE, 1)
            
            # Connect to server
            endpoint = f"tcp://{ip}:{rcon_port}"
            log.debug(f"[{self.host_id}:{self.instance_id}] Connecting to {endpoint}")
            self._socket.connect(endpoint)

            # Give the event loop time to complete the TCP+ZMTP+PLAIN handshake
            # before sending "register". IMMEDIATE=1 returns EAGAIN if no peer
            # is confirmed yet — on loopback the TCP connect is instant but the
            # ZMQ state machine still needs several event loop cycles.
            await asyncio.sleep(0.1)

            # Send "register" command (required by QLDS RCON protocol)
            # With `zmq.IMMEDIATE = 1`, this will instantly fail with EAGAIN if the target is offline
            try:
                await self._socket.send_string("register")
                log.debug(f"[{self.host_id}:{self.instance_id}] Sent register command")
            except zmq.error.ZMQError as e:
                log.error(f"[{self.host_id}:{self.instance_id}] Server offline or unreachable: {e}")
                raise Exception("Server is offline or unreachable")
            
            # QLDS doesn't always respond to register - just proceed
            # The C++ version doesn't wait for a response either
            self._connected = True
            self._shutdown = False
            self._emit_status("connected")
            
            # Start receive loop in background
            self._recv_task = asyncio.create_task(self._recv_loop())
            
            return True
            
        except Exception as e:
            log.error(f"[{self.host_id}:{self.instance_id}] Connection failed: {e}")
            self._emit_status("error")
            await self.disconnect()
            return False

    
    async def disconnect(self) -> None:
        """Disconnect from the QLDS instance."""
        self._shutdown = True
        self._connected = False
        
        # Disconnect stats if active
        if self._stats_connection:
            await self._stats_connection.disconnect()
            self._stats_connection = None
        
        # Cancel receive task
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None
        
        # Close socket
        if self._socket:
            try:
                self._socket.close()
            except Exception as e:
                log.warning(f"Error closing socket: {e}")
            self._socket = None
        
        # Only terminate context if we own it (not shared)
        if self._context and not self._shared_context:
            try:
                self._context.term()
            except Exception as e:
                log.warning(f"Error terminating context: {e}")
            self._context = None
        
        self._emit_status("disconnected")
        log.debug(f"[{self.host_id}:{self.instance_id}] Disconnected")
    
    async def send(self, command: str) -> bool:
        """Send an RCON command to the server.
        
        Args:
            command: The command to send (e.g., "status", "say Hello")
            
        Returns:
            True if command was sent, False otherwise
        """
        if not self._connected or not self._socket:
            log.error(f"[{self.host_id}:{self.instance_id}] Cannot send: not connected")
            return False
        
        try:
            log.debug(f"[{self.host_id}:{self.instance_id}] Sending: {command}")
            await self._socket.send_string(command)
            return True
        except Exception as e:
            log.error(f"[{self.host_id}:{self.instance_id}] Error sending command: {e}")
            self._emit_status("error")
            # Create disconnected task so we don't block
            task = asyncio.create_task(self.disconnect())
            task.add_done_callback(
                lambda t: log.error(f"[{self.host_id}:{self.instance_id}] Error in disconnect callback: {t.exception()}") if t.exception() else None
            )
            return False
    
    async def _recv_loop(self) -> None:
        """Background task that receives messages from the QLDS instance.
        
        Implements line buffering matching the reference Windows app's
        buildDisplayLine() approach. ZMQ messages without trailing \\n are
        buffered and concatenated until a complete line is ready.
        
        When the buffer has pending data, uses a short poll timeout (200ms)
        to flush orphaned fragments (e.g., qport/rate/steamid that arrive
        without a trailing newline from the server).
        """
        log.debug(f"[{self.host_id}:{self.instance_id}] Starting receive loop")
        line_buffer = []  # Buffer for incomplete lines
        MAX_BUFFER_FRAGMENTS = 64  # Safety flush threshold (status uses ~30 frames/player)
        IDLE_POLL_MS = 1000        # Poll timeout when buffer is empty
        BUFFERED_POLL_MS = 200     # Shorter poll when buffer has data (flush timeout)
        
        while not self._shutdown and self._socket:
            try:
                # Use shorter poll timeout when buffer has pending data
                poll_timeout = BUFFERED_POLL_MS if line_buffer else IDLE_POLL_MS
                
                if await self._socket.poll(timeout=poll_timeout):
                    raw = await self._socket.recv()
                    log.debug(f"[{self.host_id}:{self.instance_id}] Received {len(raw)}b")
                    message = parse_rcon_message(raw)
                    
                    # Line buffering: aggregate fragments until we get a newline
                    if message.endswith('\n') or message.endswith('\r'):
                        line_buffer.append(message)
                        complete_line = ''.join(line_buffer).replace('\n', '').replace('\r', '')
                        line_buffer.clear()
                        if not complete_line.startswith("zmq RCON command") and complete_line:
                            self._emit_message(complete_line)
                    elif len(line_buffer) >= MAX_BUFFER_FRAGMENTS:
                        # Safety flush
                        line_buffer.append(message)
                        complete_line = ''.join(line_buffer).replace('\n', '').replace('\r', '')
                        line_buffer.clear()
                        if not complete_line.startswith("zmq RCON command") and complete_line:
                            self._emit_message(complete_line)
                    else:
                        # Fragment without newline — buffer it
                        line_buffer.append(message)
                else:
                    # Poll timeout with no new data — flush any stale buffer
                    if line_buffer:
                        complete_line = ''.join(line_buffer).replace('\n', '').replace('\r', '')
                        line_buffer.clear()
                        if not complete_line.startswith("zmq RCON command") and complete_line:
                            self._emit_message(complete_line)
            except zmq.ZMQError as e:
                self._connected = False
                if not self._shutdown:
                    log.error(f"[{self.host_id}:{self.instance_id}] ZMQ error: {e}")
                    self._emit_status("error")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                if not self._shutdown:
                    log.error(f"[{self.host_id}:{self.instance_id}] Receive error: {e}")
                    self._emit_status("error")
                break

        log.debug(f"[{self.host_id}:{self.instance_id}] Receive loop ended")
    
    def _handle_stats_event(self, host_id: int, instance_id: int, event: dict) -> None:
        """Callback for received stats events."""
        if self.on_stats:
            try:
                self.on_stats(host_id, instance_id, event)
            except Exception as e:
                log.error(f"Error in stats callback: {e}")
    
    async def subscribe_stats(self, ip: str, stats_port: int, stats_password: Optional[str] = None) -> None:
        """Subscribe to game stats events.
        
        Args:
            ip: Server IP address
            stats_port: ZMQ stats port
            stats_password: Stats socket password (optional)
        """
        if self._stats_connection:
            log.debug(f"[{self.host_id}:{self.instance_id}] Already subscribed to stats")
            return
        
        log.debug(f"[{self.host_id}:{self.instance_id}] Subscribing to stats on port {stats_port}")
        self._stats_connection = StatsConnection(
            host_id=self.host_id,
            instance_id=self.instance_id,
            zmq_context=self._context,
            on_event=self._handle_stats_event
        )
        await self._stats_connection.connect(ip, stats_port, stats_password)
    
    async def unsubscribe_stats(self) -> None:
        """Unsubscribe from game stats events."""
        if self._stats_connection:
            log.debug(f"[{self.host_id}:{self.instance_id}] Unsubscribing from stats")
            await self._stats_connection.disconnect()
            self._stats_connection = None
