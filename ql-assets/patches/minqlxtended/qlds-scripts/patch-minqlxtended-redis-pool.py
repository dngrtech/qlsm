#!/usr/bin/env python3
"""Bound minqlxtended's shared redis pool to a BlockingConnectionPool.

Why: minqlx shares one redis client (``Redis._conn`` / ``Redis._pool``) across all
plugins, accessed per-frame and from ``@minqlxtended.thread`` workers. redis-py>=8
lowered the default ``ConnectionPool`` ``max_connections`` from unlimited (2**31) to
100. During a frame hitch the queued tasks/threads burst past 100 concurrent ``self.db``
operations at once, the plain pool raises ``MaxConnectionsError`` for every op, and the
storm of logged exceptions freezes the qagame frame loop (server stays up but stops
sending gamestate -> clients stuck on "Awaiting connection").

Raising/uncapping the limit only masks the burst. A bounded ``BlockingConnectionPool``
fixes the root: connections are capped (no proliferation) and callers wait briefly for a
free connection and reuse it instead of erroring or growing unbounded. Works on any
redis-py (the pin to <6 becomes belt-and-suspenders, not the fix).

Idempotent. Edits ``python/minqlxtended/database.py`` in a build tree before ``make``.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "_qlhub_make_pool"
OLD_POOL_CALL = "redis.ConnectionPool(**connection_kwargs)"
NEW_POOL_CALL = "_qlhub_make_pool(redis, connection_kwargs)"
IMPORT_ANCHOR = "import minqlxtended\nimport redis\n"

HELPER = '''import minqlxtended
import redis


# ql-hub: bound the shared redis pool. redis-py>=8 lowered the default
# ConnectionPool max_connections to 100; minqlx's shared, threaded `self.db`
# access bursts past that during frame hitches and storms MaxConnectionsError,
# which freezes the qagame frame loop. A bounded BlockingConnectionPool makes
# callers wait for and reuse a free connection instead of erroring/growing.
_QLHUB_REDIS_MAX_CONNECTIONS = 64
_QLHUB_REDIS_POOL_TIMEOUT = 5


def _qlhub_make_pool(redis_mod, connection_kwargs):
    # minqlxtended always puts a `unix_socket_path` key in connection_kwargs (None for
    # the TCP path, which is the only path that reaches this pool). The pool's default
    # connection_class is the TCP Connection, whose __init__ rejects `unix_socket_path`
    # (redis-py>=4): every make_connection() would raise TypeError, the
    # BlockingConnectionPool would drain to empty, and callers would then block until
    # timeout and get "No connection available." -- a multi-second frame hitch on every
    # player connect (e.g. the reconnect storm right after a map change). Drop the key
    # for TCP; select the unix connection class if a real socket path is ever passed.
    kwargs = dict(connection_kwargs)
    kwargs.pop("max_connections", None)  # upstream v1.0.0 sets this too; ours (64) always wins
    unix_path = kwargs.get("unix_socket_path")
    if unix_path:
        unix_cls = getattr(redis_mod, "UnixDomainSocketConnection", None) or getattr(
            redis_mod.connection, "UnixDomainSocketConnection"
        )
        kwargs["connection_class"] = unix_cls
    else:
        kwargs.pop("unix_socket_path", None)
    return redis_mod.BlockingConnectionPool(
        max_connections=_QLHUB_REDIS_MAX_CONNECTIONS,
        timeout=_QLHUB_REDIS_POOL_TIMEOUT,
        **kwargs,
    )
'''


def _resolve_database_py(build_dir: Path) -> Path:
    db = build_dir / "python" / "minqlxtended" / "database.py"
    if not db.is_file():
        raise SystemExit(f"database.py not found: {db}")
    return db


def is_redis_pool_patched(build_dir: Path) -> bool:
    db = build_dir / "python" / "minqlxtended" / "database.py"
    if not db.is_file():
        return False
    text = db.read_text(encoding="utf-8")
    return MARKER in text and OLD_POOL_CALL not in text


def patch_database(build_dir: Path) -> bool:
    db = _resolve_database_py(build_dir)
    text = db.read_text(encoding="utf-8")
    original = text

    if MARKER not in text:
        if IMPORT_ANCHOR not in text:
            raise SystemExit(
                f"import anchor missing in {db}: {IMPORT_ANCHOR!r}"
            )
        text = text.replace(IMPORT_ANCHOR, HELPER, 1)

    if OLD_POOL_CALL in text:
        text = text.replace(OLD_POOL_CALL, NEW_POOL_CALL)

    if text == original:
        return False
    db.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    build_dir = Path(args[0]) if args else Path.home() / "minqlxtended-build"
    if not build_dir.is_dir():
        raise SystemExit(f"minqlxtended build dir not found: {build_dir}")
    if is_redis_pool_patched(build_dir):
        print(f"redis-pool already patched: {build_dir}")
        return
    if patch_database(build_dir):
        print(f"redis-pool patch applied (BlockingConnectionPool): {build_dir}")
    else:
        print(f"redis-pool patch: nothing to do: {build_dir}")


if __name__ == "__main__":
    main()
