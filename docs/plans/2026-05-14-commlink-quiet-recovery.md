# CommLink Quiet Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the CommLink minqlx plugin retry IRC/network failures quietly while preserving player connect/disconnect and cross-server messages when the transport is healthy.

**Architecture:** Keep the existing `commlink.py` plugin and `SimpleAsyncIrc` thread. Add explicit transport readiness state, safe write helpers, bounded reconnect backoff, timeouts, and command-level offline handling. Presence events are best-effort and are dropped silently while offline.

**Tech Stack:** Python 3, minqlx plugin API, asyncio streams, pytest with a fake `minqlx` module.

---

### Task 1: Add Focused CommLink Tests

**Files:**
- Create: `tests/test_commlink_quiet_recovery.py`
- Read: `tests/test_serverchecker_workshop_resolution.py`
- Modify later: `ql-assets/data/minqlx-plugins/commlink.py`

**Step 1: Write the fake minqlx loader**

Create a helper that injects a minimal `minqlx` module before importing
`ql-assets/data/minqlx-plugins/commlink.py`.

```python
import importlib.util
import sys
import types
from pathlib import Path


def _identity_decorator(*args, **kwargs):
    def decorate(func):
        return func
    if args and callable(args[0]) and not kwargs:
        return args[0]
    return decorate


def _load_commlink_module(monkeypatch):
    fake_minqlx = types.SimpleNamespace(
        AbstractChannel=object,
        CHAT_CHANNEL=types.SimpleNamespace(reply=lambda msg: None),
        Plugin=type("Plugin", (), {}),
        PRI_LOWEST=0,
        RET_STOP_ALL="RET_STOP_ALL",
        RET_USAGE="RET_USAGE",
        delay=_identity_decorator,
        thread=_identity_decorator,
        get_logger=lambda name: types.SimpleNamespace(
            debug=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
        ),
        log_exception=lambda *args, **kwargs: None,
        unload_plugin=lambda name: None,
        console_print=lambda msg: None,
    )
    monkeypatch.setitem(sys.modules, "minqlx", fake_minqlx)

    module_path = (
        Path(__file__).resolve().parents[1]
        / "ql-assets"
        / "data"
        / "minqlx-plugins"
        / "commlink.py"
    )
    spec = importlib.util.spec_from_file_location("commlink_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
```

**Step 2: Write the offline command test**

Assert that player commands report only to the caller and do not attempt an IRC
write when the transport is unavailable.

```python
def test_world_command_reports_unavailable_to_caller(monkeypatch):
    module = _load_commlink_module(monkeypatch)
    plugin = module.commlink.__new__(module.commlink)
    plugin.irc = types.SimpleNamespace(is_ready=lambda: False, msg=lambda *args: False)
    plugin.identity = "#test"
    plugin.translate_colors = lambda text: text

    player = types.SimpleNamespace(name="Alice", tells=[])
    player.tell = player.tells.append

    result = plugin.send_commlink_message(player, ["world", "hello"], None)

    assert result == module.minqlx.RET_STOP_ALL
    assert player.tells == ["^3CommLink^7 unavailable."]
```

**Step 3: Write the silent presence-drop test**

Assert that connect events do not send anything while IRC is not ready.

```python
def test_connect_event_is_silently_dropped_when_offline(monkeypatch):
    module = _load_commlink_module(monkeypatch)
    sent = []
    plugin = module.commlink.__new__(module.commlink)
    plugin.irc = types.SimpleNamespace(is_ready=lambda: False, msg=lambda *args: sent.append(args))
    plugin.identity = "#test"
    plugin.get_cvar = lambda name, cast=None: True
    plugin.translate_colors = lambda text: text

    player = types.SimpleNamespace(name="Alice", steam_id=123)

    plugin.handle_player_connect(player)

    assert sent == []
```

**Step 4: Write the malformed IRC line test**

Assert that malformed `PRIVMSG` lines do not raise.

```python
import asyncio


def test_parse_data_ignores_malformed_privmsg(monkeypatch):
    module = _load_commlink_module(monkeypatch)
    irc = module.SimpleAsyncIrc("irc.example.test", "nick", lambda *args: None, lambda *args: None)

    asyncio.run(irc.parse_data(":broken PRIVMSG #channel :hello"))
```

**Step 5: Write the safe write test**

Assert that a socket reset during write returns `False` and marks the transport
not ready.

```python
class ResettingWriter:
    def is_closing(self):
        return False

    def write(self, data):
        raise ConnectionResetError("reset")


def test_write_failure_marks_transport_offline(monkeypatch):
    module = _load_commlink_module(monkeypatch)
    irc = module.SimpleAsyncIrc("irc.example.test", "nick", lambda *args: None, lambda *args: None)
    irc.writer = ResettingWriter()
    irc.set_ready()

    assert irc.write("PRIVMSG #test :hello\r\n") is False
    assert irc.is_ready() is False
```

**Step 6: Run tests and verify they fail first**

Run: `pytest tests/test_commlink_quiet_recovery.py -v`

Expected: FAIL because `is_ready`, quiet command handling, parse guards, and
safe write handling do not exist yet.

### Task 2: Implement Quiet Transport State

**Files:**
- Modify: `ql-assets/data/minqlx-plugins/commlink.py:43-375`
- Test: `tests/test_commlink_quiet_recovery.py`

**Step 1: Add imports and constants**

Add `socket`, `urllib.error`, and bounded timeout/backoff constants near the top.

```python
import socket
import urllib.error

IRC_CONNECT_TIMEOUT = 10
PUBLIC_IP_TIMEOUT = 3
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 300
COMMLINK_UNAVAILABLE_MSG = "^3CommLink^7 unavailable."
EXPECTED_TRANSPORT_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
    socket.gaierror,
)
```

**Step 2: Remove lifecycle chat/log messages**

Delete the startup `logger.info(...)` and `self.msg("Connecting...")` lines from
`commlink.__init__`.

Change `handle_perform` so it only joins the identity channel:

```python
def handle_perform(self, irc):
    irc.join(self.identity)
```

**Step 3: Add plugin helpers**

Add helpers before the player hooks:

```python
def commlink_available(self):
    return bool(self.irc and self.irc.is_ready())

def tell_commlink_unavailable(self, player):
    player.tell(COMMLINK_UNAVAILABLE_MSG)

def send_irc_message(self, recipient, text):
    if not self.commlink_available():
        return False
    return self.irc.msg(recipient, text)
```

**Step 4: Drop presence events silently while offline**

Update `handle_player_connect` and `handle_player_disconnect` to return early if
connect/disconnect messages are disabled, the player is a bot, or CommLink is
offline. Do not tell players anything in these hooks.

```python
if not self.commlink_available():
    return
```

**Step 5: Make commands caller-visible only when offline**

Update `send_commlink_message`, `server_status`, and `need_player`:

- If CommLink is offline, call `tell_commlink_unavailable(player)` and return
  `minqlx.RET_STOP_ALL`.
- Only print success messages after `send_irc_message(...)` returns `True`.

**Step 6: Guard IRC responses**

Update `handle_msg` and `query_status` to use `send_irc_message(...)` for
outbound IRC messages instead of direct `self.irc.msg(...)`.

**Step 7: Add a timeout to public IP lookup**

Update `set_ip`:

```python
try:
    res = urllib.request.urlopen("http://checkip.amazonaws.com/", timeout=PUBLIC_IP_TIMEOUT).read()
except (urllib.error.URLError, TimeoutError, OSError):
    self.server_ip = ""
    return
```

**Step 8: Run the focused tests**

Run: `pytest tests/test_commlink_quiet_recovery.py -v`

Expected: command and presence tests still may fail until Task 3 updates
`SimpleAsyncIrc`, but syntax/import failures should be resolved.

### Task 3: Harden SimpleAsyncIrc

**Files:**
- Modify: `ql-assets/data/minqlx-plugins/commlink.py:263-375`
- Test: `tests/test_commlink_quiet_recovery.py`

**Step 1: Fix the shared Event default**

Change the constructor signature to `stop_event=None` and create a new event when
none is provided.

```python
self.stop_event = stop_event or threading.Event()
```

**Step 2: Add readiness state**

Initialize `_ready = False` and expose thread-safe helpers:

```python
def is_ready(self):
    with self._lock:
        return self._ready

def set_ready(self):
    with self._lock:
        self._ready = True

def set_offline(self):
    with self._lock:
        self._ready = False
```

**Step 3: Quiet expected network failures in `run`**

Replace traceback/chat reconnect handling with quiet bounded backoff:

```python
backoff = BACKOFF_BASE_SECONDS
while not self.stop_event.is_set():
    ready_seen = False
    try:
        ready_seen = loop.run_until_complete(self.connect())
    except EXPECTED_TRANSPORT_ERRORS:
        pass
    except Exception:
        minqlx.log_exception()
    finally:
        self.set_offline()

    if self.stop_event.is_set():
        break
    if ready_seen:
        backoff = BACKOFF_BASE_SECONDS
    self.stop_event.wait(backoff)
    backoff = min(backoff * 2, BACKOFF_MAX_SECONDS)
```

**Step 4: Add connection timeout and return readiness**

Wrap `asyncio.open_connection` with `asyncio.wait_for(..., IRC_CONNECT_TIMEOUT)`.
Track whether MOTD registration completed, and return that boolean when the
connection closes.

```python
self.reader, self.writer = await asyncio.wait_for(
    asyncio.open_connection(self.host, self.port),
    timeout=IRC_CONNECT_TIMEOUT,
)
```

**Step 5: Make writes safe**

Update `write` to return `True` on success, `False` on missing/closing writer or
expected transport errors. Call `set_offline()` on failed writes.

**Step 6: Make command helpers return booleans**

Update `msg`, `nick`, `join`, `part`, `mode`, `kick`, `quit`, and `pong` to
return the result of `write(...)`.

**Step 7: Guard IRC parsing**

In `parse_data`, ignore malformed messages instead of indexing missing tokens or
calling `.group()` on `None`.

```python
if not split_msg:
    return
...
r = re_msg.match(msg)
if not r:
    return
user_match = re_user.match(r.group(1))
if not user_match:
    return
```

On MOTD `376`/`422`, call `self.set_ready()` before `perform_handler(self)`.

**Step 8: Close writers defensively**

In `connect`, close the writer in a `finally` block when present. Suppress
expected transport errors during quit/close.

**Step 9: Run the focused tests**

Run: `pytest tests/test_commlink_quiet_recovery.py -v`

Expected: PASS.

### Task 4: Verify Syntax and Integration Surface

**Files:**
- Modify if needed: `tests/test_commlink_quiet_recovery.py`
- Modify if needed: `ql-assets/data/minqlx-plugins/commlink.py`

**Step 1: Compile the plugin**

Run: `python3 -m py_compile ql-assets/data/minqlx-plugins/commlink.py`

Expected: exits 0.

**Step 2: Run related plugin tests**

Run: `pytest tests/test_commlink_quiet_recovery.py tests/test_serverchecker_workshop_resolution.py -v`

Expected: PASS.

**Step 3: Inspect for forbidden lifecycle output**

Run: `rg -n "Connecting to|Connected to CommLink|Disconnected from|Reconnecting" ql-assets/data/minqlx-plugins/commlink.py tests/test_commlink_quiet_recovery.py`

Expected: no plugin lifecycle chat/log output remains; test strings are allowed
only if asserting absence.

**Step 4: Inspect git diff**

Run: `git diff -- ql-assets/data/minqlx-plugins/commlink.py tests/test_commlink_quiet_recovery.py`

Expected: only CommLink quiet recovery behavior and tests changed.

### Task 5: Commit the Implementation

**Files:**
- Commit: `ql-assets/data/minqlx-plugins/commlink.py`
- Commit: `tests/test_commlink_quiet_recovery.py`
- Commit if not already committed: `docs/plans/2026-05-14-commlink-quiet-recovery.md`

**Step 1: Check status**

Run: `git status --short`

Expected: only the plugin, focused tests, and this plan are modified/untracked.

**Step 2: Stage files**

Run:

```bash
git add ql-assets/data/minqlx-plugins/commlink.py tests/test_commlink_quiet_recovery.py
git add -f docs/plans/2026-05-14-commlink-quiet-recovery.md
```

**Step 3: Commit**

Run:

```bash
git commit -m "fix: quiet commlink transport failures"
```

Expected: commit succeeds on the current feature branch.
