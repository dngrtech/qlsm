"""
Redis listener for RCON responses.

Background thread that subscribes to Redis rcon:response:* and rcon:status:*
channels and emits messages to appropriate SocketIO rooms.
"""

import json
import logging
import threading
import time
import os

import redis

REDIS_PREFIX = os.environ.get('REDIS_PREFIX', 'rcon')

log = logging.getLogger(__name__)


class RedisListener:
    """Background listener for RCON Redis channels."""
    
    def __init__(self, socketio, redis_url: str):
        """Initialize Redis listener.
        
        Args:
            socketio: Flask-SocketIO instance
            redis_url: Redis connection URL
        """
        self.socketio = socketio
        self.redis_url = redis_url
        self._thread = None
        self._running = False
        self._stop_event = threading.Event()
    
    def start(self):
        """Start the listener thread."""
        if self._thread and self._thread.is_alive():
            log.warning("Redis listener already running")
            return
        
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        log.info("Redis listener started")
    
    def stop(self):
        """Stop the listener thread."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("Redis listener stopped")
    
    def _listen(self):
        """Main listener loop - runs in background thread."""
        import os
        redis_password = os.environ.get('REDIS_PASSWORD')
        
        while self._running and not self._stop_event.is_set():
            r = None
            pubsub = None
            try:
                kwargs = {'decode_responses': True}
                if redis_password:
                    kwargs['password'] = redis_password
                    
                r = redis.from_url(self.redis_url, **kwargs)
                pubsub = r.pubsub()
                
                # Subscribe to RCON response and status channels
                pubsub.psubscribe(f'{REDIS_PREFIX}:response:*', f'{REDIS_PREFIX}:status:*', f'{REDIS_PREFIX}:stats:*')
                log.info(f"Subscribed to {REDIS_PREFIX}:response:*, {REDIS_PREFIX}:status:*, {REDIS_PREFIX}:stats:*")
                
                while not self._stop_event.is_set():
                    message = pubsub.get_message(ignore_subscribe_messages=False, timeout=1.0)
                    if not message:
                        continue
                    
                    if message['type'] != 'pmessage':
                        continue
                    
                    try:
                        self._handle_message(message['channel'], message['data'])
                    except Exception as e:
                        log.error(f"Error handling message: {e}")
            
            except Exception as e:
                log.error(f"Redis listener error: {e}")
                if not self._stop_event.is_set():
                    log.info("Attempting to reconnect in 5 seconds...")
                    self._stop_event.wait(timeout=5.0)
            finally:
                if pubsub:
                    try:
                        pubsub.close()
                    except Exception:
                        pass
                if r:
                    try:
                        r.close()
                    except Exception:
                        pass
                
        log.info("Redis listener exiting")
    
    def _handle_message(self, channel: str, data: str):
        """Handle a message from Redis.
        
        Args:
            channel: Redis channel (e.g., 'rcon:response:2:5')
            data: JSON message data
        """
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            log.error(f"Invalid JSON from {channel}: {data}")
            return
        
        # Parse channel to get host_id and instance_id
        # Format: rcon:{type}:{host_id}:{instance_id}
        parts = channel.split(':')
        if len(parts) < 4:
            log.warning(f"Invalid channel format: {channel}")
            return
        
        msg_type = parts[1]  # response, status, or stats
        host_id = parts[2]
        instance_id = parts[3]
        
        # Determine room and event
        room = f"rcon:{host_id}:{instance_id}"
        
        
        log.debug(f"Redis listener routing {msg_type} to room {room}")
        if msg_type == 'response':
            event = 'rcon:message'
            emit_data = {
                'host_id': int(host_id),
                'instance_id': int(instance_id),
                'content': payload.get('content', '')
            }
        elif msg_type == 'status':
            event = 'rcon:status'
            emit_data = {
                'host_id': int(host_id),
                'instance_id': int(instance_id),
                'status': payload.get('status', '')
            }
        elif msg_type == 'stats':
            # Stats go to stats-specific room
            room = f"rcon:stats:{host_id}:{instance_id}"
            event = 'rcon:stats'
            emit_data = {
                'host_id': int(host_id),
                'instance_id': int(instance_id),
                'event': payload
            }
        else:
            log.warning(f"Unknown message type: {msg_type}")
            return
        
        # Use Flask-SocketIO's emit (not server.emit) so that cross-thread
        # emission works correctly with eventlet green threading
        # log.debug(f"Emitting {event} to room={room}")
        self.socketio.emit(event, emit_data, room=room)
