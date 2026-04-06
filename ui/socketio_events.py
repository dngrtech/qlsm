"""
Flask-SocketIO event handlers for RCON communication.

Handles WebSocket events from the React frontend and bridges
them to Redis channels for the rcon_service to process.
"""

import json
import logging
import os
import threading
from functools import wraps

import redis
from flask import request
from flask_jwt_extended import decode_token, get_jwt_identity
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect, rooms

REDIS_PREFIX = os.environ.get('REDIS_PREFIX', 'rcon')

log = logging.getLogger(__name__)

# SocketIO instance - initialized in create_app
socketio = SocketIO()

# Redis client cache and lock for thread safety
_redis_client = None
_redis_lock = threading.Lock()


def _stats_stream_enabled() -> bool:
    """Allow live stats stream only when running at DEBUG log level."""
    return logging.getLogger().isEnabledFor(logging.DEBUG)


def get_redis_client():
    """Get or create a Redis client with password authentication."""
    global _redis_client
    with _redis_lock:
        if _redis_client is None:
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            redis_password = os.environ.get('REDIS_PASSWORD')
            
            kwargs = {'decode_responses': True}
            if redis_password:
                kwargs['password'] = redis_password
                
            _redis_client = redis.from_url(redis_url, **kwargs)
    return _redis_client

def publish_to_redis(channel: str, message: str) -> None:
    """Safely publish to Redis and reset stale connections on failure."""
    global _redis_client
    try:
        client = get_redis_client()
        client.publish(channel, message)
    except redis.RedisError as e:
        log.error(f"Redis publish failed on {channel}: {e}")
        with _redis_lock:
            _redis_client = None
        emit('rcon:error', {'error': 'Communication service temporarily unavailable.'})


def authenticated_only(f):
    """Decorator to require JWT authentication for SocketIO events."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        # Auth token is in HttpOnly cookie 'access_token_cookie'
        auth = request.cookies.get('access_token_cookie')

        if not auth:
            log.warning("SocketIO connection rejected: No auth cookie")
            disconnect()
            return

        try:
            decode_token(auth)
        except Exception as e:
            log.warning(f"SocketIO connection rejected: Invalid token - {e}")
            disconnect()
            return

        return f(*args, **kwargs)
    return wrapped


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    emit('connected', {'status': 'ok', 'sid': request.sid})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    pass


@socketio.on('rcon:join')
@authenticated_only
def handle_rcon_join(data):
    """Join an RCON room for an instance and trigger connection.

    Credentials are resolved server-side from the database — never
    accepted from the client.

    Data:
        host_id: int
        instance_id: int
    """
    from .models import QLInstance

    host_id = data.get('host_id')
    instance_id = data.get('instance_id')

    if not all([host_id, instance_id]):
        emit('rcon:error', {'error': 'Missing required fields (host_id, instance_id)'})
        return

    # Resolve connection details server-side
    instance = QLInstance.query.get(instance_id)
    if not instance or instance.host_id != host_id:
        emit('rcon:error', {'error': f'Instance {instance_id} not found on host {host_id}'})
        return

    ip = instance.host.ip_address
    rcon_port = instance.zmq_rcon_port
    rcon_password = instance.zmq_rcon_password

    if not all([ip, rcon_port, rcon_password]):
        emit('rcon:error', {'error': 'RCON not configured for this instance'})
        return

    room = f"rcon:{host_id}:{instance_id}"
    join_room(room)

    # Publish connect command to Redis for rcon_service
    redis_client = get_redis_client()
    channel = f"{REDIS_PREFIX}:cmd:{host_id}:{instance_id}"
    message = json.dumps({
        'action': 'connect',
        'ip': ip,
        'rcon_port': rcon_port,
        'rcon_password': rcon_password
    })
    publish_to_redis(channel, message)

    emit('rcon:joined', {'room': room, 'host_id': host_id, 'instance_id': instance_id})


@socketio.on('rcon:leave')
@authenticated_only
def handle_rcon_leave(data):
    """Leave an RCON room and trigger disconnection.

    Data:
        host_id: int
        instance_id: int
    """
    host_id = data.get('host_id')
    instance_id = data.get('instance_id')
    if host_id is None or instance_id is None:
        return

    room = f"rcon:{host_id}:{instance_id}"
    
    # Verify sender has joined the room before executing commands
    if room not in rooms(sid=request.sid, namespace='/'):
        return
        
    leave_room(room)

    # Check if any clients are left in the room
    try:
        participants = socketio.server.manager.get_participants('/', room)
        participant_count = len(list(participants))
    except Exception as e:
        log.warning(f"Failed to check room participants for {room}: {e}")
        participant_count = 1  # Assume someone is still there to prevent false disconnects

    if participant_count == 0:
        # Publish disconnect command to Redis
        channel = f"{REDIS_PREFIX}:cmd:{host_id}:{instance_id}"
        message = json.dumps({'action': 'disconnect'})
        publish_to_redis(channel, message)

    emit('rcon:left', {'room': room})


@socketio.on('rcon:command')
@authenticated_only
def handle_rcon_command(data):
    """Send an RCON command to an instance.

    Data:
        host_id: int
        instance_id: int
        cmd: str
    """
    host_id = data.get('host_id')
    instance_id = data.get('instance_id')
    cmd = data.get('cmd')

    if not all([host_id, instance_id, cmd]):
        emit('rcon:error', {'error': 'Missing required fields'})
        return

    room = f"rcon:{host_id}:{instance_id}"
    
    # Verify sender has joined the room before executing commands
    if room not in rooms(sid=request.sid, namespace='/'):
        emit('rcon:error', {'error': 'Not authorized for this instance'})
        return

    # Publish command to Redis
    channel = f"{REDIS_PREFIX}:cmd:{host_id}:{instance_id}"
    message = json.dumps({
        'action': 'command',
        'cmd': cmd
    })
    publish_to_redis(channel, message)


@socketio.on('rcon:subscribe_stats')
@authenticated_only
def handle_subscribe_stats(data):
    """Enable real-time game events for an instance.

    Data:
        host_id: int
        instance_id: int
    """
    from .models import QLInstance

    host_id = data.get('host_id')
    instance_id = data.get('instance_id')

    # Treat raw event streaming as debug-only output.
    if not _stats_stream_enabled():
        return

    # Lookup instance to get IP, stats port, and password
    instance = QLInstance.query.get(instance_id)
    if not instance or instance.host_id != host_id:
        emit('rcon:error', {'error': f'Instance {instance_id} not found on host {host_id}'})
        return

    ip = instance.host.ip_address
    stats_password = instance.zmq_stats_password
    stats_port = instance.zmq_stats_port

    if not stats_port:
        return

    # Join stats room
    room = f"rcon:stats:{host_id}:{instance_id}"
    join_room(room)

    # Publish subscribe command to Redis
    channel = f"{REDIS_PREFIX}:cmd:{host_id}:{instance_id}"
    message = json.dumps({
        'action': 'subscribe_stats',
        'ip': ip,
        'stats_port': stats_port,
        'stats_password': stats_password
    })
    publish_to_redis(channel, message)


@socketio.on('rcon:unsubscribe_stats')
@authenticated_only
def handle_unsubscribe_stats(data):
    """Disable real-time game events for an instance."""
    host_id = data.get('host_id')
    instance_id = data.get('instance_id')
    if host_id is None or instance_id is None:
        return

    room = f"rcon:stats:{host_id}:{instance_id}"
    
    if room not in rooms(sid=request.sid, namespace='/'):
        return
        
    leave_room(room)

    # Publish unsubscribe command
    channel = f"{REDIS_PREFIX}:cmd:{host_id}:{instance_id}"
    message = json.dumps({'action': 'unsubscribe_stats'})
    publish_to_redis(channel, message)
