#!/usr/bin/env python3
"""ql-watchdog — detect a hung QLDS main-thread and auto-restart the instance.

Background
----------
QLDS can deadlock its main game-loop (observed root cause on ql-server-core:
the built-in ZeroMQ stats/rcon publisher). The process stays alive but the
game frame-loop stops: the UDP game port is no longer drained, so the kernel
Recv-Q for the port climbs without bound. Plain process supervision (systemd
Restart=on-failure) cannot detect this because the process never exits. This
watchdog turns that infinite hang into an automatic restart of just the
affected instance.

qlsm runs each QLDS instance as its own systemd unit `qlds@<port>.service`
(the game port doubles as the systemd instance name — see
ansible/templates/qlds@.service.j2), unlike ql-server-core's supervisord
`quakelive:ql_N` groups. Discovery/restart here go through systemctl instead
of supervisorctl, and the game port is read directly off the unit name.

Detection (per instance, every INTERVAL) requires TWO signals to agree:
  1. kernel Recv-Q for the UDP game port (from /proc/net/udp[6]) is at or above
     RECVQ_THRESHOLD, and
  2. the instance's CPU time (utime+stime from /proc/<pid>/stat) has NOT
     advanced since the previous check.
  Both for STRIKES consecutive checks -> restart.

  Recv-Q alone is not sufficient. It rises whenever inbound rate exceeds drain
  rate, which a healthy server does during a slow workshop map load, while a
  plugin blocks the main thread, when the shared Redis stalls, or simply when
  someone points traffic at the public game port. GRACE only covers unit
  startup, so it never re-arms mid-session. A frozen frame loop, by contrast,
  stops burning CPU -- QLDS otherwise runs its loop continuously -- so the CPU
  delta is what separates "stuck" from "busy".

  Deliberate trade-off: a busy-spin hang keeps consuming CPU and is NOT caught.
  Restarting a healthy server mid-match is worse than missing a rare spin.

Second detector: dead engine
----------------------------
A crashed engine can deadlock inside its own crash handler. The process stays
alive (so systemd never restarts it) but has already closed its game socket,
so Recv-Q stays at 0, and leftover threads keep burning a little CPU: the
detector above sees nothing. This one restarts an instance when ALL hold:
  1. the engine does not answer a connectionless packet sent over loopback, and
  2. the status key that the serverchecker plugin refreshes every 10 seconds
     is absent from Redis (a failed read counts as unknown, never as absent), and
  3. both were seen good earlier for the same process, and
  4. 1 and 2 have held on every check for DEAD_CONFIRM seconds.

  The two signals fail independently on a healthy server: under a flood the
  engine may miss the probe but keeps writing its status, and a broken or
  removed serverchecker loses the key while the engine still answers. Rule 3
  keeps instances that never produce both signals (no serverchecker, engine
  bound to another address) out of this detector entirely. An instance that
  dies before the watchdog has seen it healthy is NOT caught.

Stdlib only. Runs as root (systemctl restart on a system unit + gdb attach to
another user's process both require it).
"""

from __future__ import annotations

import json
import os
import select
import socket
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, "")).strip() or default)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


DRYRUN = _env_bool("QL_WATCHDOG_DRYRUN", False)
INTERVAL = max(2, _env_int("QL_WATCHDOG_INTERVAL", 10))
# Sustained Recv-Q (bytes) above this for STRIKES checks => hung. Healthy idle
# server sits at 0-960B even under polling; a real hang reaches 100KB+.
# Floor of 1: a threshold of 0 would make "Recv-Q >= 0" true on every check,
# i.e. every instance permanently hung. The API validator rejects 0 too.
RECVQ_THRESHOLD = max(1, _env_int("QL_WATCHDOG_RECVQ_THRESHOLD", 8192))
STRIKES = max(1, _env_int("QL_WATCHDOG_STRIKES", 3))
# Skip an instance that has been active for less than GRACE seconds: covers
# systemd startup + map load + post-restart settle (no strikes during boot).
GRACE = max(30, _env_int("QL_WATCHDOG_GRACE", 90))
# Restart loop guard: at most RATE_MAX restarts per RATE_WINDOW per instance.
RATE_MAX = max(1, _env_int("QL_WATCHDOG_RATE_MAX", 3))
RATE_WINDOW = max(60, _env_int("QL_WATCHDOG_RATE_WINDOW", 900))
# Dead-engine detector: how long the engine must stay silent with no status
# key before a restart. Long enough to outlast any map load or plugin stall.
DEAD_CONFIRM = max(60, _env_int("QL_WATCHDOG_DEAD_CONFIRM", 180))
DEAD_MIN_CHECKS = 3
PROBE_TIMEOUT = 1.0
REDIS_TIMEOUT = 1.0
STATUS_KEY_PREFIX = "minqlx:server_status"
# qlds@<port>.service - the systemd template unit prefix qlsm uses for QLDS
# instances (ansible/templates/qlds@.service.j2). The game port is read
# directly from the unit's instance name (the part after '@').
UNIT_PREFIX = os.environ.get("QL_WATCHDOG_UNIT_PREFIX", "qlds").strip() or "qlds"
EVENTS_PATH = os.environ.get(
    "QL_WATCHDOG_EVENTS", "/var/lib/qlsm/watchdog/events.jsonl"
).strip()

# Forensics: on a detected hang, snapshot all-thread native backtraces with gdb
# (+ py-spy if present) BEFORE restarting, so a freeze is symbolized even
# though it produces no core. Best-effort, never blocks a restart.
FORENSICS = _env_bool("QL_WATCHDOG_FORENSICS", True)
GDB = os.environ.get("QL_WATCHDOG_GDB", "gdb").strip() or "gdb"
PYSPY = os.environ.get("QL_WATCHDOG_PYSPY", "py-spy").strip() or "py-spy"
FORENSICS_DIR = os.environ.get(
    "QL_WATCHDOG_FORENSICS_DIR", "/var/lib/qlsm/watchdog/forensics"
).strip()
GDB_TIMEOUT = max(10, _env_int("QL_WATCHDOG_GDB_TIMEOUT", 60))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(event: str, **fields: object) -> None:
    rec = {"ts": _utc_now(), "event": event}
    rec.update(fields)
    line = json.dumps(rec, ensure_ascii=False)
    print(line, flush=True)
    if EVENTS_PATH:
        try:
            os.makedirs(os.path.dirname(EVENTS_PATH), exist_ok=True)
            with open(EVENTS_PATH, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def _run(cmd: list[str], timeout: int) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return ((res.stdout or "") + (res.stderr or "")).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"<run failed: {str(exc)[:200]}>"


def _which(prog: str) -> str:
    if os.path.isabs(prog):
        return prog if os.access(prog, os.X_OK) else ""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(d, prog)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return ""


def _unit_name(port: int) -> str:
    return f"{UNIT_PREFIX}@{port}.service"


def discover_instances() -> dict[int, dict[str, object]]:
    """Return {port: {state, uptime_sec}} for every qlds@<port>.service unit.

    The game port is the systemd instance name itself (see
    ansible/templates/qlds@.service.j2 - ExecStart is keyed on %i == port),
    so no separate index->port mapping is needed here.
    """
    try:
        res = subprocess.run(
            [
                "systemctl", "list-units", "--all", "--type=service",
                "--no-legend", "--plain", "--full", f"{UNIT_PREFIX}@*.service",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_event("systemctl_error", action="list-units", error=str(exc)[:200])
        return {}

    units: list[str] = []
    prefix = f"{UNIT_PREFIX}@"
    for line in (res.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        name = line.split()[0]
        if name.startswith(prefix) and name.endswith(".service"):
            units.append(name)
    if not units:
        return {}

    try:
        res2 = subprocess.run(
            [
                "systemctl", "show", *units,
                "--property=Id,ActiveState,ActiveEnterTimestampMonotonic",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_event("systemctl_error", action="show", error=str(exc)[:200])
        return {}

    now_mono = time.clock_gettime(time.CLOCK_MONOTONIC)
    instances: dict[int, dict[str, object]] = {}
    for block in (res2.stdout or "").split("\n\n"):
        props: dict[str, str] = {}
        for line in block.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                props[k] = v
        unit_id = props.get("Id", "")
        if not (unit_id.startswith(prefix) and unit_id.endswith(".service")):
            continue
        port_str = unit_id[len(prefix):-len(".service")]
        try:
            port = int(port_str)
        except ValueError:
            continue
        enter_us = props.get("ActiveEnterTimestampMonotonic", "0")
        try:
            enter_mono = int(enter_us) / 1_000_000.0
        except ValueError:
            enter_mono = 0.0
        uptime_sec = max(0, int(now_mono - enter_mono)) if enter_mono > 0 else 0
        instances[port] = {
            "state": props.get("ActiveState", ""),
            "uptime_sec": uptime_sec,
        }
    return instances


def _recv_q_from(path: str, port: int) -> int:
    total = 0
    try:
        with open(path, encoding="ascii") as fh:
            next(fh, None)  # header
            for line in fh:
                f = line.split()
                if len(f) < 5:
                    continue
                local = f[1]
                if ":" not in local:
                    continue
                try:
                    lport = int(local.rsplit(":", 1)[1], 16)
                except ValueError:
                    continue
                if lport != port:
                    continue
                queues = f[4].split(":")
                if len(queues) != 2:
                    continue
                try:
                    total += int(queues[1], 16)  # rx_queue (Recv-Q)
                except ValueError:
                    continue
    except OSError:
        return 0
    return total


def recv_q(port: int) -> int:
    return max(_recv_q_from("/proc/net/udp", port), _recv_q_from("/proc/net/udp6", port))


def cpu_ticks(pid: str) -> int | None:
    """Total CPU time (utime+stime, in clock ticks) burned by pid so far.

    Returns None if the process is gone or /proc is unreadable. The comm field
    can contain spaces and parentheses, so fields are taken after the last
    ')' rather than by naive split.
    """
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as fh:
            data = fh.read()
    except OSError:
        return None
    try:
        fields = data[data.rindex(")") + 1:].split()
        # After comm, field 0 is state; utime/stime are fields 11 and 12.
        return int(fields[11]) + int(fields[12])
    except (ValueError, IndexError):
        return None


def engine_args(pid: str) -> dict[str, str] | None:
    """The `+set <name> <value>` pairs the engine process was started with.

    Returns None if the process is gone or /proc is unreadable.
    """
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            argv = [a.decode(errors="replace") for a in fh.read().split(b"\0")]
    except OSError:
        return None
    args: dict[str, str] = {}
    for i in range(len(argv) - 2):
        if argv[i] == "+set":
            args[argv[i + 1]] = argv[i + 2]
    return args


def probe_engine(port: int, host: str = "127.0.0.1", timeout: float = PROBE_TIMEOUT) -> bool | None:
    """Does the engine answer a connectionless packet on its game port?

    A live engine replies at once ("Server uses protocol version ..."). True on
    a reply, False on silence, None if the probe itself could not be made.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return None
    try:
        sock.sendto(b'\xff\xff\xff\xffconnect ""', (host, port))
        readable, _, _ = select.select([sock], [], [], timeout)
        if not readable:
            return False
        return True if sock.recv(2048).startswith(b"\xff\xff\xff\xff") else None
    except (OSError, ValueError):
        return None
    finally:
        sock.close()


def _resp_command(*parts: str) -> bytes:
    out = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        raw = part.encode()
        out.append(b"$%d\r\n%s\r\n" % (len(raw), raw))
    return b"".join(out)


def status_key_present(args: dict[str, str], port: int, timeout: float = REDIS_TIMEOUT) -> bool | None:
    """Is the instance's live-status key in the Redis it was started against?

    True/False only when Redis answered every command cleanly. None for
    anything else: no Redis settings on the command line, connection or auth
    failure, timeout, unexpected reply.
    """
    address = args.get("qlx_redisAddress", "")
    if not address:
        return None
    try:
        db = int(args.get("qlx_redisDatabase", "0"))
    except ValueError:
        return None
    password = args.get("qlx_redisPassword", "")
    commands = []
    if password:
        commands.append(_resp_command("AUTH", password))
    commands.append(_resp_command("SELECT", str(db)))
    commands.append(_resp_command("EXISTS", f"{STATUS_KEY_PREFIX}:{port}"))
    sock = None
    try:
        if args.get("qlx_redisUnixSocket") == "1":
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(address)
        else:
            host, _, redis_port = address.rpartition(":")
            sock = socket.create_connection((host or "127.0.0.1", int(redis_port)), timeout=timeout)
            sock.settimeout(timeout)
        sock.sendall(b"".join(commands))
        with sock.makefile("rb") as reader:
            for _ in commands[:-1]:
                if reader.readline().strip() != b"+OK":
                    return None
            reply = reader.readline().strip()
        if reply == b":1":
            return True
        if reply == b":0":
            return False
        return None
    except (OSError, ValueError):
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def new_dead_watch(pid: str) -> dict[str, object]:
    return {"pid": pid, "armed": False, "since": None, "checks": 0, "last": None}


def dead_engine_step(
    watch: dict[str, object],
    reply: bool | None,
    key_present: bool | None,
    now: float,
    max_gap: float,
) -> bool:
    """Fold one check into the watch; True once the engine is confirmed dead.

    Only clear-cut evidence moves it: reply and key both good arms it, both
    bad (after arming) extends the streak, anything else ends the streak.
    """
    healthy = reply is True and key_present is True
    dead = reply is False and key_present is False
    if healthy:
        watch["armed"] = True
    if not dead or not watch["armed"]:
        watch["since"] = None
        watch["checks"] = 0
    else:
        last = watch["last"]
        unbroken = watch["since"] is not None and last is not None and now - last <= max_gap  # type: ignore[operator]
        if unbroken:
            watch["checks"] = int(watch["checks"]) + 1  # type: ignore[arg-type]
        else:
            watch["since"] = now
            watch["checks"] = 1
    watch["last"] = now
    return (
        watch["since"] is not None
        and int(watch["checks"]) >= DEAD_MIN_CHECKS  # type: ignore[arg-type]
        and now - watch["since"] >= DEAD_CONFIRM  # type: ignore[operator]
    )


def check_dead_engine(port: int, pid: str, watches: dict[int, dict[str, object]], now: float) -> bool:
    """Probe one instance and advance its dead-engine watch."""
    if not pid:
        watches.pop(port, None)
        return False
    watch = watches.get(port)
    if watch is None or watch["pid"] != pid:
        watch = watches[port] = new_dead_watch(pid)
    args = engine_args(pid)
    if args is None:
        reply: bool | None = None
        key_present: bool | None = None
    else:
        reply = probe_engine(port, args.get("net_ip") or "127.0.0.1")
        # An armed instance that answers is healthy enough to end any streak;
        # the Redis read only matters for arming and for confirming silence.
        if reply is True and watch["armed"]:
            key_present = True
        else:
            key_present = status_key_present(args, port)
    was_streaking = watch["since"] is not None
    confirmed = dead_engine_step(watch, reply, key_present, now, max(60.0, 3.0 * INTERVAL))
    if watch["since"] is not None and not was_streaking:
        log_event("engine_silent", port=port, pid=pid, need_sec=DEAD_CONFIRM)
    elif was_streaking and watch["since"] is None:
        log_event("engine_answering", port=port, pid=pid, reply=reply, status_key=key_present)
    return confirmed


def restart_instance(port: int) -> tuple[bool, str]:
    unit = _unit_name(port)
    try:
        res = subprocess.run(
            ["systemctl", "restart", unit],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)[:200]
    out = ((res.stdout or "") + (res.stderr or "")).strip()
    return res.returncode == 0, out[:300]


def instance_pid(port: int) -> str:
    out = _run(["systemctl", "show", _unit_name(port), "--property=MainPID", "--value"], 15).strip()
    return out if out.isdigit() and out != "0" else ""


def capture_hang_forensics(port: int, rq: int) -> str:
    """Snapshot all-thread native backtraces (gdb) + py-spy of a hung instance.

    Returns the forensics file path, or "" if it could not be captured. Runs
    as root, so gdb can attach regardless of ptrace_scope. Best-effort only.
    """
    if not FORENSICS:
        return ""
    pid = instance_pid(port)
    if not pid:
        return ""
    try:
        # 0700/0600: a gdb "thread apply all bt" prints frame arguments,
        # including char* values, from a process holding the rcon password.
        os.makedirs(FORENSICS_DIR, mode=0o700, exist_ok=True)
        os.chmod(FORENSICS_DIR, 0o700)
    except OSError:
        return ""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(FORENSICS_DIR, f"hang-{UNIT_PREFIX}-{port}-{ts}.txt")
    parts = [
        f"# ql-watchdog hang forensics\n"
        f"port={port} pid={pid} recv_q={rq} ts={ts}\n"
    ]
    try:
        with open(f"/proc/{pid}/wchan", encoding="ascii") as fh:
            parts.append(f"wchan={fh.read().strip()}\n")
    except OSError:
        pass
    gdb = _which(GDB)
    if gdb:
        parts.append("\n=== gdb: thread apply all bt ===\n")
        parts.append(
            _run(
                [
                    gdb, "-p", pid, "-batch", "-nx",
                    "-ex", "set pagination off",
                    "-ex", "thread apply all bt",
                    "-ex", "detach", "-ex", "quit",
                ],
                GDB_TIMEOUT,
            )
        )
    else:
        parts.append("\n=== gdb not found; skipped native backtrace ===\n")
    pyspy = _which(PYSPY)
    if pyspy:
        parts.append("\n\n=== py-spy dump (python threads) ===\n")
        parts.append(_run([pyspy, "dump", "--pid", pid, "--nonblocking"], 30))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("".join(parts))
    except OSError:
        return ""
    return path


def main() -> int:
    log_event(
        "start",
        dryrun=DRYRUN,
        interval=INTERVAL,
        recvq_threshold=RECVQ_THRESHOLD,
        strikes=STRIKES,
        grace=GRACE,
        unit_prefix=UNIT_PREFIX,
        forensics=FORENSICS,
        gdb=bool(_which(GDB)),
        dead_confirm=DEAD_CONFIRM,
    )
    dead_watches: dict[int, dict[str, object]] = {}
    strikes: dict[int, int] = {}
    restarts: dict[int, deque[float]] = {}
    cpu: dict[int, int | None] = {}

    while True:
        try:
            instances = discover_instances()
            for port, info in instances.items():
                if info["state"] != "active" or int(info["uptime_sec"]) < GRACE:  # type: ignore[arg-type]
                    strikes[port] = 0
                    dead_watches.pop(port, None)
                    continue
                rq = recv_q(port)
                # Recv-Q alone cannot tell "frozen frame loop" from "inbound
                # rate > drain rate". A slow workshop map load, a blocking
                # plugin call, a stalled shared Redis, or plain UDP traffic
                # aimed at the public game port all back the socket up on a
                # perfectly healthy server -- and GRACE only covers unit
                # startup, so it never re-arms mid-session. Require a second,
                # non-network signal: the process must ALSO have stopped
                # burning CPU. QLDS runs its frame loop continuously, so
                # utime+stime always advances while the server is alive; the
                # blocking deadlock this addon targets flatlines it.
                #
                # Trade-off, deliberately this way round: a busy-spin hang
                # keeps burning CPU and is not caught. Restarting a healthy
                # server mid-match is worse than missing a rare spin.
                pid = instance_pid(port)
                ticks = cpu_ticks(pid) if pid else None
                prev_ticks = cpu.get(port)
                cpu[port] = ticks
                # No previous sample yet (first pass, or just restarted) --
                # no verdict until we have two points to compare.
                cpu_frozen = (
                    ticks is not None
                    and prev_ticks is not None
                    and ticks == prev_ticks
                )
                hung = rq >= RECVQ_THRESHOLD and cpu_frozen
                if hung:
                    strikes[port] = strikes.get(port, 0) + 1
                    log_event(
                        "hang_suspected",
                        port=port,
                        recv_q=rq,
                        cpu_ticks=ticks,
                        strike=strikes[port],
                        need=STRIKES,
                    )
                else:
                    if strikes.get(port):
                        log_event(
                            "recovered", port=port, recv_q=rq, cpu_ticks=ticks
                        )
                    strikes[port] = 0
                # Second detector (see module docstring): a crashed engine
                # that never exited shows neither Recv-Q nor a flat CPU.
                dead = check_dead_engine(port, pid, dead_watches, time.monotonic())
                if dead:
                    reason = "engine_dead"
                    # Start a fresh streak whatever happens next (restart,
                    # rate limit, dry-run), so this fires once per DEAD_CONFIRM.
                    dead_watches[port]["since"] = None
                    dead_watches[port]["checks"] = 0
                elif hung and strikes[port] >= STRIKES:
                    reason = "frozen_loop"
                else:
                    continue

                hist = restarts.setdefault(port, deque())
                now = time.monotonic()
                while hist and now - hist[0] > RATE_WINDOW:
                    hist.popleft()
                if len(hist) >= RATE_MAX:
                    log_event(
                        "restart_giveup",
                        port=port,
                        reason=reason,
                        recv_q=rq,
                        restarts_in_window=len(hist),
                        window_sec=RATE_WINDOW,
                        note="rate limit hit; alert only, not restarting",
                    )
                    strikes[port] = 0
                    continue

                if DRYRUN:
                    # No forensics in dry-run: the dry-run branch never appends
                    # to the rate-limit history, so capturing here would write a
                    # dump every STRIKES*INTERVAL seconds forever.
                    log_event("would_restart", port=port, reason=reason, recv_q=rq)
                    strikes[port] = 0
                    continue

                # Capture native+python backtraces of the frozen process BEFORE
                # touching it - a hang yields no core, so this is the only
                # record of WHERE the main thread is stuck.
                forensics = capture_hang_forensics(port, rq)
                if forensics:
                    log_event("hang_forensics", port=port, recv_q=rq, file=forensics)

                ok, out = restart_instance(port)
                hist.append(now)
                log_event(
                    "restart" if ok else "restart_failed",
                    port=port,
                    reason=reason,
                    recv_q=rq,
                    ok=ok,
                    output=out,
                    forensics=forensics,
                )
                strikes[port] = 0
        except Exception as exc:  # never let the watchdog die on a transient error
            log_event("loop_error", error=str(exc)[:300])
        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
