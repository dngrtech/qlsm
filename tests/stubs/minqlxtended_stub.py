"""A fake `minqlxtended` module, enough to import and exercise a ported plugin.

Mirrors the pinned engine at 1e2f307: StrEnum team/state/gametype, a Plugin base
with add_hook/get_cvar/players/db/logger, and a pass-through @thread decorator.
Event arities are taken from _events.py so a handler with a stale signature
raises here exactly as the engine would raise at plugin load.
"""
import enum
import sys
import types


if hasattr(enum, "StrEnum"):
    StrEnum = enum.StrEnum
else:
    # The engine needs Python 3.12+ (README.md), where every enum below is a real
    # enum.StrEnum. CI runs 3.10, which has no StrEnum, so stand in with what
    # CPython 3.11's StrEnum reduces to: a str mixin whose __str__ is str's, not
    # Enum's. That keeps the semantics the port depends on — json.dumps emits the
    # bare value, `member == "in_progress"` holds, str(member) is the value.
    class StrEnum(str, enum.Enum):
        __str__ = str.__str__


class Team(StrEnum):
    FREE = "free"
    RED = "red"
    BLUE = "blue"
    SPECTATOR = "spectator"

    @property
    def index(self):
        return {"free": 0, "red": 1, "blue": 2, "spectator": 3}[self.value]


class GameState(StrEnum):
    WARMUP = "warmup"
    COUNTDOWN = "countdown"
    IN_PROGRESS = "in_progress"


class Gametype(StrEnum):
    FFA = "ffa"
    DUEL = "duel"
    CA = "ca"
    CTF = "ctf"
    TDM = "tdm"


# Handler arity per event, excluding `self`. From _events.py at the pinned commit.
EVENT_ARITIES = {
    "game_start": 0,
    "game_end": 1,
    "player_connect": 2,
    "player_disconnect": 2,
    "map": 2,
    "player_loaded": 1,
    "player_spawn": 1,
}


class SignatureMismatch(Exception):
    """What the engine raises at registration for a bad handler signature."""


def thread(func=None, force=False):
    """Pass-through stand-in for @minqlxtended.thread: run inline, synchronously."""
    def decorate(target):
        return target
    return decorate(func) if func is not None else decorate


class Plugin:
    """Minimal Plugin base. Tests assign `game`, `_players`, `db` and `cvars`."""

    def __init__(self):
        self.hooks = []
        self.cvars = {}
        self._players = []
        self.game = None
        self.db = None

    def add_hook(self, event, handler, priority=0):
        import inspect
        if event not in EVENT_ARITIES:
            raise KeyError(event)
        params = [
            p for name, p in inspect.signature(handler).parameters.items()
            if name != "self"
        ]
        required = len([
            p for p in params
            if p.default is inspect.Parameter.empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ])
        if required != EVENT_ARITIES[event]:
            raise SignatureMismatch(
                f"{event} dispatches {EVENT_ARITIES[event]} argument(s); "
                f"handler {handler.__name__} takes {required}"
            )
        self.hooks.append((event, handler, priority))

    def get_cvar(self, name, return_type=str, default=None):
        return self.cvars.get(name, default)

    def players(self):
        return list(self._players)

    @property
    def logger(self):
        import logging
        return logging.getLogger("stub.minqlxtended")


def install_stub():
    """Register the fake module in sys.modules and return it.

    Idempotent: calling twice returns the module already installed, so a second
    import in the same session does not get a fresh Plugin class that breaks
    isinstance checks.
    """
    existing = sys.modules.get("minqlxtended")
    if existing is not None and getattr(existing, "_qlsm_stub", False):
        return existing

    module = types.ModuleType("minqlxtended")
    module._qlsm_stub = True
    # These classes are defined in this file, so their __module__ names this
    # stub. On the engine they belong to `minqlxtended`, and a ported plugin is
    # checked against that, so hand them the identity they are impersonating.
    for impersonator in (Plugin, Team, GameState, Gametype, SignatureMismatch):
        impersonator.__module__ = "minqlxtended"
    module.Plugin = Plugin
    module.Team = Team
    module.GameState = GameState
    module.Gametype = Gametype
    module.thread = thread
    module.SignatureMismatch = SignatureMismatch
    sys.modules["minqlxtended"] = module
    return module
