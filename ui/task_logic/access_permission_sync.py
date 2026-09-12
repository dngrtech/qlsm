"""Push stored admin rows into the target instance's minqlx permission DB.

The Owner & Admins editor (frontend-react/src/components/operators/OwnerAdminEditor.jsx)
writes qlx_owner into server.cfg -- picked up for free on the next server.cfg exec,
no extra step needed -- and the admin list into `instance_admin` rows (see
ui.models.InstanceAdmin). access.txt now holds only Quake Live's own roles
(|admin, |mod, |ban); QLSM's admin levels live in the database, not on disk. No
shipped minqlx-plugin actually reads access.txt for permission levels, though:
permission.py / chat_rcon.py only ever consult minqlx's own Redis permission
keys, normally set one at a time via the in-game "!setperm <id> <level>" chat
command. Without this module, an admin added through the UI still has
permission level 0 in the running instance and chat_rcon's !rcon silently
denies them ("permission denied"), even though the admin list looks right.

Call sync_instance_admin_permissions(instance) from apply_instance_config_logic
after every successful config apply and from deploy_instance_logic after a
successful deploy, mirroring telemetry_relay_instance.py's
sync_instance_server_id_from_config -- same "config on disk is the source of truth,
reconcile the running instance's external state after every apply" shape.

Removed entries are reset to permission 0 rather than left stale, tracked via a
"minqlx:qlsm:managed_admins:<instance_id>" Redis SET: only steamids this
instance's sync itself previously wrote get reset, so a permission granted by
hand via !setperm outside the UI is never touched. The set is keyed by instance,
not just by Redis DB, because instances may deliberately share a DB -- a
DB-wide set let saving one instance reset admins that only the other instance
lists. The pre-scoping DB-wide set is adopted once by the first instance to
sync and then deleted, so admins pushed before the change can still be revoked.

Caveat: minqlxtended caches permission reads for qlx_permissionCacheTime seconds
(default 30, see minqlxtended/database.py Redis._permission_ttl) inside its own
process. A write made here from outside that process cannot invalidate that
cache, so a permission change can take up to ~30s to take effect in-game. There
is no remote way to poke the cache sooner: '!'-prefixed minqlx commands (which
is how a live admin would normally trigger cache eviction by re-running a
command) are not reachable over zmq_rcon on this build -- confirmed live against
91.99.3.72:27965, where "!rcon status" sent over zmq_rcon produced no reply and
no chat-rcon log line at all.
"""

import base64
import json
import logging
import os
import shlex
import subprocess

from ui import db
from ui.admin_permissions import entries_from_rows
from ui.constants import resolve_redis_db
from ui.task_logic.common import append_log
from ui.task_logic.self_host_network import resolve_self_host_management_target

logger = logging.getLogger(__name__)

SSH_CONNECT_TIMEOUT = 5
SYNC_TIMEOUT = SSH_CONNECT_TIMEOUT + 5
LEGACY_MANAGED_SET_KEY = "minqlx:qlsm:managed_admins"


def managed_set_key(instance_id):
    return f"{LEGACY_MANAGED_SET_KEY}:{int(instance_id)}"


def _ssh_target_for_host(host):
    if getattr(host, "provider", None) == "self":
        return resolve_self_host_management_target()
    return host.ip_address


def _remote_sync_script(entries, db, redis_password, instance_id):
    entries_b64 = base64.b64encode(json.dumps(entries).encode()).decode()
    managed_key = managed_set_key(instance_id)
    password_b64 = (
        base64.b64encode(redis_password.encode()).decode() if redis_password is not None else None
    )
    return f'''import base64
import json
import redis

entries = json.loads(base64.b64decode({entries_b64!r}).decode())
password_b64 = {password_b64!r}
password = base64.b64decode(password_b64).decode() if password_b64 is not None else None

client = redis.Redis(db={db}, password=password, socket_connect_timeout=3, socket_timeout=3)

def members(key):
    return {{m.decode() if isinstance(m, bytes) else m for m in client.smembers(key)}}

managed_key = {managed_key!r}
legacy_key = {LEGACY_MANAGED_SET_KEY!r}
previously_managed = members(managed_key)
if not previously_managed:
    legacy = members(legacy_key)
    if legacy:
        previously_managed = legacy
        client.delete(legacy_key)
new_ids = set(entries.keys())

for steam_id, level in entries.items():
    client.set(f"minqlx:players:{{steam_id}}:permission", str(level))

removed = previously_managed - new_ids
for steam_id in removed:
    client.set(f"minqlx:players:{{steam_id}}:permission", "0")

if previously_managed:
    client.srem(managed_key, *previously_managed)
if new_ids:
    client.sadd(managed_key, *new_ids)

print(json.dumps({{"synced": sorted(new_ids), "reset": sorted(removed)}}))
'''


def build_sync_command(host, db, entries, instance_id, redis_password=None):
    """One bounded SSH command that reconciles a single instance's permission
    keys, mirroring service_runtime.py's build_runtime_probe_command shape."""
    script = _remote_sync_script(entries, db, redis_password, instance_id)
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


def sync_access_permissions(instance, entries):
    """Best-effort push of {steam_id: level} entries into the instance's
    minqlx permission DB. Returns {"synced": [...], "reset": [...]} on
    success, False if the round-trip actually failed (SSH/Redis unreachable,
    bad output) -- callers should surface that to the operator, since the
    admin list was saved but in-game permissions did not follow -- or None if
    there was no host to sync against at all (a structural no-op, not a
    failure)."""
    host = getattr(instance, "host", None)
    if host is None:
        return None

    db = resolve_redis_db(instance)
    redis_password = (
        os.environ.get("REDIS_PASSWORD") if getattr(host, "provider", None) == "self" else None
    )

    command = build_sync_command(host, db, entries, instance.id, redis_password=redis_password)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=SYNC_TIMEOUT)
    except subprocess.TimeoutExpired:
        logger.warning(
            "Timed out syncing admin permissions for instance %s", getattr(instance, "id", "?")
        )
        return False
    except Exception:
        logger.exception(
            "Failed to sync admin permissions for instance %s", getattr(instance, "id", "?")
        )
        return False

    if result.returncode != 0:
        logger.warning(
            "admin permission sync failed for instance %s: %s",
            getattr(instance, "id", "?"), (result.stderr or "")[:200],
        )
        return False

    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "admin permission sync returned unparseable output for instance %s",
            getattr(instance, "id", "?"),
        )
        return False

    return payload


def sync_instance_admin_permissions(instance):
    """Reconcile the instance's stored admin rows into Redis.

    No-op (returns None) if the instance has no host -- matches
    sync_instance_server_id_from_config's "nothing to sync against" handling
    in telemetry_relay_instance.py. Otherwise always syncs, even with an
    empty admin list: an empty push is how the last remaining admin gets
    reset to level 0 via the managed-admins set. Defers to
    sync_access_permissions's return value: a payload dict on success, False
    if the sync actually ran and failed (callers should surface this -- see
    sync_and_report_access_permissions).
    """
    if not instance.host:
        return None
    return sync_access_permissions(instance, entries_from_rows(instance.admins or []))


SYNC_FAILED_LOG_MESSAGE = (
    "Warning: admin permissions could not be synced to the running instance "
    "(SSH/Redis unreachable). The admin list was saved, but in-game levels may "
    "be stale until the next successful apply."
)


def sync_and_report_access_permissions(instance):
    """Run the permission sync after a successful deploy or config apply.

    Never raises and never fails the calling task. Any failure -- a failed
    round trip, or an unexpected error before it (self-host target
    detection) -- appends a warning to the instance log, so a revocation that
    did not happen is visible to the operator."""
    try:
        result = sync_instance_admin_permissions(instance)
    except Exception:
        logger.warning(
            "admin permission sync raised for instance %s", getattr(instance, "id", "?"),
            exc_info=True,
        )
        result = False
    if result is False:
        append_log(instance, SYNC_FAILED_LOG_MESSAGE)
        db.session.commit()
    return result
