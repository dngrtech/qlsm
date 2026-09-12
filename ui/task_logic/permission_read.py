"""Read the live minqlx permission levels out of an instance's Redis database.

The mirror image of access_permission_sync's write path: one bounded SSH
command running a small python script on the host. SCAN, not KEYS, so a large
database cannot block Redis. Every level comes back, 0 included -- a stored
level-0 row has to be able to match live state -- along with the contents of
the instance's managed-admins set, which is what tells a !setperm grant apart
from a level QLSM pushed and then lost the row for.
"""

import base64
import json
import logging
import os
import re
import shlex
import subprocess

from ui.constants import resolve_redis_db
from ui.task_logic.access_permission_sync import (
    SSH_CONNECT_TIMEOUT,
    _ssh_target_for_host,
    managed_set_key,
)

logger = logging.getLogger(__name__)

READ_TIMEOUT = SSH_CONNECT_TIMEOUT + 5
UNREACHABLE_MESSAGE = "The server is unreachable, so in-game levels could not be read."
STEAMID64_RE = re.compile(r'^7656119\d{10}$')


def _remote_read_script(db, managed_key, redis_password):
    password_b64 = (
        base64.b64encode(redis_password.encode()).decode() if redis_password is not None else None
    )
    return f'''import base64
import json
import redis

password_b64 = {password_b64!r}
password = base64.b64decode(password_b64).decode() if password_b64 is not None else None
client = redis.Redis(db={db}, password=password, socket_connect_timeout=3, socket_timeout=3)

levels = {{}}
for key in client.scan_iter(match="minqlx:players:*:permission", count=500):
    key_text = key.decode() if isinstance(key, bytes) else key
    parts = key_text.split(":")
    if len(parts) != 4:
        continue
    steam_id = parts[2]
    raw = client.get(key_text)
    if raw is None:
        continue
    raw_text = raw.decode() if isinstance(raw, bytes) else raw
    try:
        level = int(raw_text)
    except (TypeError, ValueError):
        continue
    levels[steam_id] = level

managed = []
for member in client.smembers({managed_key!r}):
    managed.append(member.decode() if isinstance(member, bytes) else member)

print(json.dumps({{"levels": levels, "managed": managed}}))
'''


def build_read_command(host, db, instance_id, redis_password=None):
    # managed_set_key is access_permission_sync's own key builder -- import it
    # rather than re-spelling "minqlx:qlsm:managed_admins:<id>" here.
    script = _remote_read_script(db, managed_set_key(instance_id), redis_password)
    return [
        "ssh",
        "-i", os.path.abspath(host.ssh_key_path),
        "-p", str(host.ssh_port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        "-l", host.ssh_user,
        _ssh_target_for_host(host),
        f"python3 -c {shlex.quote(script)}",
    ]


def read_live_permissions(instance):
    """(levels, managed, error). (None, None, None) when there is no host."""
    host = getattr(instance, "host", None)
    if host is None:
        return None, None, None

    redis_password = (
        os.environ.get("REDIS_PASSWORD") if getattr(host, "provider", None) == "self" else None
    )
    command = build_read_command(
        host, resolve_redis_db(instance), instance.id, redis_password=redis_password
    )
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=READ_TIMEOUT)
    except subprocess.TimeoutExpired:
        logger.warning("Timed out reading permissions for instance %s", getattr(instance, "id", "?"))
        return None, None, UNREACHABLE_MESSAGE
    except Exception:
        logger.exception("Failed to read permissions for instance %s", getattr(instance, "id", "?"))
        return None, None, UNREACHABLE_MESSAGE

    if result.returncode != 0:
        logger.warning("Permission read failed for instance %s: %s",
                       getattr(instance, "id", "?"), (result.stderr or "")[:200])
        return None, None, UNREACHABLE_MESSAGE

    try:
        payload = json.loads(result.stdout)
        # A key that is not a SteamID must never reach the client: it would render
        # as an adoptable row and then 400 the entire config save on validation.
        levels = {
            str(k): int(v) for k, v in (payload.get("levels") or {}).items()
            if STEAMID64_RE.match(str(k))
        }
        managed = [str(m) for m in (payload.get("managed") or []) if STEAMID64_RE.match(str(m))]
        return levels, managed, None
    except (AttributeError, json.JSONDecodeError, TypeError, ValueError):
        logger.warning("Permission read returned unparseable output for instance %s",
                       getattr(instance, "id", "?"))
        return None, None, UNREACHABLE_MESSAGE
