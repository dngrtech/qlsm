"""Redis-based per-entity task locking.

Prevents conflicting operations on the same host or instance.
Uses SET NX EX for atomic lock acquisition and a Lua script
for owner-validated release.
"""
import logging

log = logging.getLogger(__name__)

# Lua script: delete key only if value matches (owner validation).
# Prevents releasing another task's lock after TTL expiry.
_RELEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""


def _get_redis():
    """Get the shared Redis client from the Flask app."""
    from flask import current_app
    return current_app.extensions['redis']


def acquire_lock(entity_type, entity_id, token, ttl):
    """Attempt to acquire a per-entity lock.

    Args:
        entity_type: 'host' or 'instance'
        entity_id: numeric entity ID
        token: unique lock token (UUID) for owner validation
        ttl: lock TTL in seconds

    Returns:
        True if lock acquired, False if already held.
    """
    redis_client = _get_redis()
    key = f"task_lock:{entity_type}:{entity_id}"
    result = redis_client.set(key, token, nx=True, ex=ttl)
    if result:
        log.info(f"Lock acquired: {key} (token={token}, ttl={ttl}s)")
    else:
        log.warning(f"Lock denied: {key} already held")
    return bool(result)


def release_lock(entity_type, entity_id, token):
    """Release a per-entity lock, only if we own it.

    Uses a Lua script for atomic GET+DEL to prevent releasing
    another task's lock after TTL expiry.

    Args:
        entity_type: 'host' or 'instance'
        entity_id: numeric entity ID
        token: the token used when acquiring

    Returns:
        True if lock was released, False if not owned or not found.
    """
    redis_client = _get_redis()
    key = f"task_lock:{entity_type}:{entity_id}"
    result = redis_client.execute_command(
        'EVAL', _RELEASE_SCRIPT, 1, key, token
    )
    if result:
        log.info(f"Lock released: {key} (token={token})")
    else:
        log.debug(f"Lock not released (not owner or expired): {key}")
    return bool(result)
