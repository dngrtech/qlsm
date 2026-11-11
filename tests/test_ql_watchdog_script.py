"""Unit tests for the ql-watchdog detection primitives.

The watchdog is a standalone stdlib-only script that runs on the game host
under the host's own python3, so it is loaded by path rather than imported as
a package. These cover the two parsers that decide whether a live game server
gets SIGKILLed: the /proc/net/udp Recv-Q reader and the /proc/<pid>/stat CPU
reader that corroborates it.
"""
import importlib.util
import os
import sys

import pytest

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ansible", "files", "ql-watchdog", "watchdog.py",
)


def _load():
    spec = importlib.util.spec_from_file_location("ql_watchdog_script", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ql_watchdog_script"] = mod
    spec.loader.exec_module(mod)
    return mod


watchdog = _load()


# /proc/net/udp layout: sl local_address rem_address st tx_queue:rx_queue ...
# 27960 == 0x6D38. rx_queue is the second half of field 4.
_UDP_TABLE = """  sl  local_address rem_address   st tx_queue:rx_queue tr tm->when retrnsmt   uid  timeout inode
  123: 00000000:6D38 00000000:0000 07 00000000:00002000 00:00000000 00000000     0        0 12345 2 0000000000000000 0
  124: 00000000:6D39 00000000:0000 07 00000000:00000000 00:00000000 00000000     0        0 12346 2 0000000000000000 0
"""


def test_recv_q_reads_rx_queue_for_the_matching_port(tmp_path):
    f = tmp_path / "udp"
    f.write_text(_UDP_TABLE)
    # 0x2000 == 8192, the default RECVQ_THRESHOLD.
    assert watchdog._recv_q_from(str(f), 27960) == 8192
    # 27961 (0x6D39) is idle.
    assert watchdog._recv_q_from(str(f), 27961) == 0
    # A port with no socket at all reads as 0, not an error.
    assert watchdog._recv_q_from(str(f), 29000) == 0


def test_recv_q_missing_file_is_zero_not_an_exception(tmp_path):
    assert watchdog._recv_q_from(str(tmp_path / "nope"), 27960) == 0


def test_recv_q_skips_malformed_lines(tmp_path):
    f = tmp_path / "udp"
    f.write_text(
        "header\n"
        "garbage\n"
        "  1: NOCOLON 00000000:0000 07 00000000:00001000\n"
        "  2: 00000000:ZZZZ 00000000:0000 07 00000000:00001000\n"
        "  3: 00000000:6D38 00000000:0000 07 badqueue\n"
        "  4: 00000000:6D38 00000000:0000 07 00000000:00000100 x\n"
    )
    # Only the last line is well-formed for 27960: 0x100 == 256.
    assert watchdog._recv_q_from(str(f), 27960) == 256


def test_recv_q_threshold_floor_is_one():
    """0 would make 'rq >= threshold' true on every check for every instance."""
    assert watchdog.RECVQ_THRESHOLD >= 1


@pytest.mark.parametrize(
    "comm", ["qzeroded.x64", "name with spaces", "weird)paren", "((nested))"]
)
def test_cpu_ticks_sums_utime_and_stime_despite_comm_content(tmp_path, monkeypatch, comm):
    # /proc/<pid>/stat: pid (comm) state ppid ... utime(14) stime(15) ...
    # After the closing paren, state is index 0, so utime/stime are 11 and 12.
    after = ["S"] + [str(i) for i in range(1, 11)] + ["400", "50"] + ["0"] * 30
    proc = tmp_path / "1234"
    proc.mkdir()
    (proc / "stat").write_text(f"1234 ({comm}) " + " ".join(after) + "\n")
    monkeypatch.setattr(watchdog, "cpu_ticks", watchdog.cpu_ticks)
    # Point the reader at our fixture tree.
    orig_open = open

    def fake_open(path, *a, **kw):
        if str(path) == "/proc/1234/stat":
            return orig_open(str(proc / "stat"), *a, **kw)
        return orig_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    assert watchdog.cpu_ticks("1234") == 450


def test_cpu_ticks_returns_none_for_a_dead_process():
    assert watchdog.cpu_ticks("0") is None
    assert watchdog.cpu_ticks("nonexistent-pid") is None


def test_cpu_ticks_returns_none_on_unparseable_stat(tmp_path, monkeypatch):
    proc = tmp_path / "stat"
    proc.write_text("no closing paren here\n")
    orig_open = open

    def fake_open(path, *a, **kw):
        if str(path) == "/proc/9/stat":
            return orig_open(str(proc), *a, **kw)
        return orig_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    assert watchdog.cpu_ticks("9") is None


# --- Dead-engine detector -------------------------------------------------

import socket
import socketserver
import threading


def _fake_cmdline(monkeypatch, tmp_path, pid, argv):
    cmdline = tmp_path / f"cmdline-{pid}"
    cmdline.write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    orig_open = open

    def fake_open(path, *a, **kw):
        if str(path) == f"/proc/{pid}/cmdline":
            return orig_open(str(cmdline), *a, **kw)
        return orig_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)


def test_engine_args_reads_set_pairs_including_empty_values(tmp_path, monkeypatch):
    _fake_cmdline(monkeypatch, tmp_path, "902", [
        "./qzeroded.x64", "+set", "net_ip", "", "+set", "qlx_redisAddress", "127.0.0.1:6379",
        "+set", "qlx_redisPassword", "s3 cret", "+set", "qlx_redisDatabase", "6",
    ])

    assert watchdog.engine_args("902") == {
        "net_ip": "", "qlx_redisAddress": "127.0.0.1:6379",
        "qlx_redisPassword": "s3 cret", "qlx_redisDatabase": "6",
    }


def test_engine_args_is_none_for_a_dead_process():
    assert watchdog.engine_args("nonexistent-pid") is None


def _udp_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    return sock, sock.getsockname()[1]


def test_probe_engine_true_when_the_engine_answers():
    engine, port = _udp_socket()
    received = []

    def serve():
        data, address = engine.recvfrom(2048)
        received.append(data)
        engine.sendto(b"\xff\xff\xff\xffprint\nServer uses protocol version 91.\n", address)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        assert watchdog.probe_engine(port, timeout=2.0) is True
    finally:
        thread.join(timeout=2)
        engine.close()
    assert received == [b'\xff\xff\xff\xffconnect ""']


def test_probe_engine_false_on_silence_with_or_without_a_socket():
    silent, port = _udp_socket()
    try:
        assert watchdog.probe_engine(port, timeout=0.2) is False
    finally:
        silent.close()
    # The crashed engine this detector targets has closed its game socket.
    assert watchdog.probe_engine(port, timeout=0.2) is False


class _FakeRedis(socketserver.ThreadingTCPServer):
    """Speaks just enough RESP for AUTH / SELECT / EXISTS."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, password="", keys=()):
        self.password = password
        self.keys = set(keys)  # (db, key)
        self.seen = []
        super().__init__(("127.0.0.1", 0), _FakeRedisHandler)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def address(self):
        return f"127.0.0.1:{self.server_address[1]}"


class _FakeRedisHandler(socketserver.StreamRequestHandler):
    def _read_command(self):
        header = self.rfile.readline()
        if not header.startswith(b"*"):
            return None
        parts = []
        for _ in range(int(header[1:])):
            length = int(self.rfile.readline()[1:])
            parts.append(self.rfile.read(length + 2)[:-2].decode())
        return parts

    def handle(self):
        db = 0
        authed = not self.server.password
        while True:
            command = self._read_command()
            if command is None:
                return
            self.server.seen.append(command)
            name = command[0].upper()
            if name == "AUTH":
                authed = command[1] == self.server.password
                self.wfile.write(b"+OK\r\n" if authed else b"-WRONGPASS invalid password\r\n")
            elif not authed:
                self.wfile.write(b"-NOAUTH Authentication required.\r\n")
            elif name == "SELECT":
                db = int(command[1])
                self.wfile.write(b"+OK\r\n")
            elif name == "EXISTS":
                self.wfile.write(b":1\r\n" if (db, command[1]) in self.server.keys else b":0\r\n")
            else:
                self.wfile.write(b"-ERR unknown\r\n")


def test_status_key_present_reads_the_instance_database_with_its_password():
    server = _FakeRedis(password="hunter2", keys={(6, "minqlx:server_status:27965")})
    args = {"qlx_redisAddress": server.address, "qlx_redisDatabase": "6", "qlx_redisPassword": "hunter2"}
    try:
        assert watchdog.status_key_present(args, 27965) is True
        assert watchdog.status_key_present(args, 27964) is False
        assert watchdog.status_key_present({**args, "qlx_redisDatabase": "5"}, 27965) is False
    finally:
        server.shutdown()
        server.server_close()
    assert ["SELECT", "6"] in server.seen


@pytest.mark.parametrize("args", [
    {},                                                           # no Redis settings at all
    {"qlx_redisAddress": "127.0.0.1:1"},                          # nothing listening
    {"qlx_redisAddress": "ADDR", "qlx_redisPassword": "wrong"},   # auth refused
    {"qlx_redisAddress": "ADDR"},                                 # auth required, none sent
    {"qlx_redisAddress": "ADDR", "qlx_redisPassword": "hunter2", "qlx_redisDatabase": "x"},
    {"qlx_redisAddress": "/var/run/redis/redis.sock", "qlx_redisUnixSocket": "1"},  # no such socket here
])
def test_status_key_present_is_unknown_never_absent_when_redis_cannot_be_read(args):
    server = _FakeRedis(password="hunter2")
    args = {k: (server.address if v == "ADDR" else v) for k, v in args.items()}
    try:
        assert watchdog.status_key_present(args, 27965, timeout=0.5) is None
    finally:
        server.shutdown()
        server.server_close()


def _steps(observations, step=10.0, watch=None):
    """Feed (reply, key_present) pairs one check apart; return the verdicts."""
    watch = watch or watchdog.new_dead_watch("902")
    return watch, [
        watchdog.dead_engine_step(watch, reply, key, 1000.0 + i * step, max_gap=60.0)
        for i, (reply, key) in enumerate(observations)
    ]


HEALTHY = (True, True)
DEAD = (False, False)


def test_dead_engine_confirmed_only_after_the_full_unbroken_window():
    _, verdicts = _steps([HEALTHY] + [DEAD] * 20)

    # Dead from t=10; DEAD_CONFIRM (180s) of evidence is complete at t=190.
    assert verdicts.index(True) == 19
    assert not any(verdicts[:19])


def test_instance_never_seen_healthy_is_never_restarted():
    _, verdicts = _steps([DEAD] * 60)

    assert not any(verdicts)


@pytest.mark.parametrize("blip", [
    HEALTHY,
    (False, True),    # flood: engine misses the probe, status still written
    (True, False),    # serverchecker broken: no status, engine answers
    (False, None),    # Redis unreadable
    (None, False),    # probe could not be made
    (None, None),
])
def test_any_check_that_is_not_clearly_dead_restarts_the_clock(blip):
    _, verdicts = _steps([HEALTHY] + [DEAD] * 15 + [blip] + [DEAD] * 17)

    assert not any(verdicts)


def test_one_signal_alone_never_confirms():
    assert not any(_steps([HEALTHY] + [(False, True)] * 60)[1])
    assert not any(_steps([HEALTHY] + [(True, False)] * 60)[1])


def test_a_stalled_watchdog_loop_does_not_count_as_evidence():
    watch, _ = _steps([HEALTHY] + [DEAD] * 5)

    # The loop was away for ten minutes (forensics, a slow restart elsewhere).
    assert watchdog.dead_engine_step(watch, False, False, 1000.0 + 50 + 600, max_gap=60.0) is False
    assert watch["checks"] == 1


def test_check_dead_engine_starts_unarmed_for_a_new_process(monkeypatch):
    monkeypatch.setattr(watchdog, "engine_args", lambda pid: {"qlx_redisAddress": "x"})
    monkeypatch.setattr(watchdog, "probe_engine", lambda port: False)
    monkeypatch.setattr(watchdog, "status_key_present", lambda args, port: False)
    monkeypatch.setattr(watchdog, "log_event", lambda *a, **kw: None)
    watches = {27965: {**watchdog.new_dead_watch("902"), "armed": True}}

    # Same port, new process: the arming of the old one must not carry over.
    verdicts = [watchdog.check_dead_engine(27965, "4242", watches, 1000.0 + i * 10) for i in range(40)]

    assert not any(verdicts)
    assert watches[27965]["pid"] == "4242" and watches[27965]["armed"] is False


def test_check_dead_engine_confirms_an_armed_process(monkeypatch):
    state = {"alive": True}
    monkeypatch.setattr(watchdog, "engine_args", lambda pid: {"qlx_redisAddress": "x"})
    monkeypatch.setattr(watchdog, "probe_engine", lambda port: state["alive"])
    monkeypatch.setattr(watchdog, "status_key_present", lambda args, port: state["alive"])
    monkeypatch.setattr(watchdog, "log_event", lambda *a, **kw: None)
    watches = {}

    assert watchdog.check_dead_engine(27965, "902", watches, 1000.0) is False
    state["alive"] = False
    verdicts = [watchdog.check_dead_engine(27965, "902", watches, 1010.0 + i * 10) for i in range(19)]

    assert verdicts[-1] is True and not any(verdicts[:-1])


def test_check_dead_engine_is_unknown_when_the_process_cannot_be_read(monkeypatch):
    monkeypatch.setattr(watchdog, "engine_args", lambda pid: None)
    monkeypatch.setattr(watchdog, "log_event", lambda *a, **kw: None)
    watches = {27965: {**watchdog.new_dead_watch("902"), "armed": True}}

    assert not any(watchdog.check_dead_engine(27965, "902", watches, 1000.0 + i * 10) for i in range(40))


class _StopLoop(BaseException):
    pass


def _run_main(monkeypatch, checks, recv_q=0, ticks=None, dead=lambda n: False):
    """Run the watchdog loop for `checks` passes over one active instance."""
    events, restarts, passes = [], [], {"n": 0}
    ticks = ticks or (lambda n: n)  # CPU advancing by default

    def sleep(_):
        passes["n"] += 1
        if passes["n"] >= checks:
            raise _StopLoop

    monkeypatch.setattr(watchdog, "discover_instances",
                        lambda: {27965: {"state": "active", "uptime_sec": 10_000}})
    monkeypatch.setattr(watchdog, "instance_pid", lambda port: "902")
    monkeypatch.setattr(watchdog, "recv_q", lambda port: recv_q)
    monkeypatch.setattr(watchdog, "cpu_ticks", lambda pid: ticks(passes["n"]))
    monkeypatch.setattr(watchdog, "check_dead_engine",
                        lambda port, pid, watches, now: watches.setdefault(port, watchdog.new_dead_watch(pid))
                        and dead(passes["n"]))
    monkeypatch.setattr(watchdog, "capture_hang_forensics", lambda port, rq: "")
    monkeypatch.setattr(watchdog, "restart_instance", lambda port: restarts.append(port) or (True, ""))
    monkeypatch.setattr(watchdog, "log_event", lambda event, **fields: events.append((event, fields)))
    monkeypatch.setattr(watchdog, "DRYRUN", False)
    monkeypatch.setattr(watchdog.time, "sleep", sleep)
    with pytest.raises(_StopLoop):
        watchdog.main()
    return events, restarts


def test_loop_restarts_a_dead_engine_that_the_recv_q_detector_cannot_see(monkeypatch):
    # Recv-Q 0 and CPU still advancing: exactly the crashed-engine signature.
    events, restarts = _run_main(monkeypatch, checks=3, dead=lambda n: n == 1)

    assert restarts == [27965]
    assert [f["reason"] for e, f in events if e == "restart"] == ["engine_dead"]


def test_loop_leaves_a_healthy_instance_alone(monkeypatch):
    events, restarts = _run_main(monkeypatch, checks=10)

    assert restarts == []
    assert [e for e, _ in events if e != "start"] == []


def test_loop_still_restarts_a_frozen_frame_loop_after_strikes(monkeypatch):
    monkeypatch.setattr(watchdog, "STRIKES", 3)
    events, restarts = _run_main(monkeypatch, checks=5, recv_q=100_000, ticks=lambda n: 7)

    # First pass has no previous CPU sample; strikes on passes 2-4.
    assert restarts == [27965]
    assert [f["reason"] for e, f in events if e == "restart"] == ["frozen_loop"]
    assert [f["strike"] for e, f in events if e == "hang_suspected"][:3] == [1, 2, 3]


def test_loop_dead_engine_respects_the_restart_rate_limit(monkeypatch):
    monkeypatch.setattr(watchdog, "RATE_MAX", 2)
    events, restarts = _run_main(monkeypatch, checks=6, dead=lambda n: True)

    assert restarts == [27965, 27965]
    assert [f["reason"] for e, f in events if e == "restart_giveup"][0] == "engine_dead"


@pytest.mark.parametrize("args", [
    # The command line belongs to the unprivileged engine user; root must not
    # follow it to another machine or to an arbitrary local socket.
    {"qlx_redisAddress": "ADDR_REMOTE"},
    {"qlx_redisAddress": "/var/run/docker.sock", "qlx_redisUnixSocket": "1"},
    {"qlx_redisAddress": "6379"},
])
def test_status_key_present_refuses_targets_qlsm_never_configures(monkeypatch, args):
    connects = []
    monkeypatch.setattr(watchdog.socket, "create_connection", lambda *a, **kw: connects.append(a) or 1 / 0)
    monkeypatch.setattr(watchdog.socket, "socket", lambda *a, **kw: connects.append(a) or 1 / 0)
    args = {k: ("10.1.2.3:6379" if v == "ADDR_REMOTE" else v) for k, v in args.items()}

    assert watchdog.status_key_present(args, 27965) is None
    assert connects == []


@pytest.mark.parametrize("env, expected", [(None, 180), ("300", 300), ("5", 60), ("junk", 180)])
def test_dead_confirm_comes_from_the_environment_with_a_floor(monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("QL_WATCHDOG_DEAD_CONFIRM", raising=False)
    else:
        monkeypatch.setenv("QL_WATCHDOG_DEAD_CONFIRM", env)
    try:
        assert _load().DEAD_CONFIRM == expected
    finally:
        monkeypatch.undo()
        globals()["watchdog"] = _load()
