"""A fake `minqlxtended` module, enough to import and exercise a ported plugin.

Mirrors the pinned engine at 1e2f307: StrEnum team/state/gametype, a Plugin base
with add_hook/get_cvar/players/db/logger, and a pass-through @thread decorator.
Event arities are taken from _events.py so a handler with a stale signature
raises here exactly as the engine would raise at plugin load.
"""
import enum
import functools
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


class Return(enum.Enum):
    """_enums.py:115. Values are arbitrary here; identity is what handlers compare."""
    NONE = 0
    STOP = 1
    STOP_EVENT = 2
    STOP_ALL = 3
    USAGE = 4


class Priority(enum.IntEnum):
    """_enums.py:135. Ordering matters — add_hook sorts on it."""
    LOWEST = 0
    LOW = 1
    NORMAL = 2
    HIGH = 3
    HIGHEST = 4


def next_frame(func):
    """_core.py:586. Runs inline here; the engine defers one server frame.

    functools.wraps is load-bearing, not tidiness: add_hook checks a handler's
    signature at registration, and the engine's own decorator wraps (_core.py:598)
    so a decorated handler still reports the arity it was written with. A stub
    wrapper without it makes every decorated handler look like it takes no
    arguments, and every hook registration fail.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


def delay(time):
    """_core.py:605. Runs inline here; the engine schedules on a timer."""
    def decorate(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorate


def parse_infostring(infostring):
    """_core.py:97. Splits a backslash-delimited infostring into a dict.

    No `ordered` kwarg — dicts preserve insertion order, which is what minqlx's
    parse_variables(..., ordered=True) was asking for.
    """
    parts = [p for p in infostring.split("\\") if p != ""]
    return dict(zip(parts[::2], parts[1::2]))


class _Channel:
    """Stands in for _commands.py:560-563's channel singletons."""

    def __init__(self, name):
        self.name = name
        self.replies = []

    def reply(self, msg, **kwargs):
        self.replies.append(msg)

    def __str__(self):
        return self.name


# Handler arity per event, excluding `self`. From _events.py at the pinned commit.
# The line number is the dispatch() that fixes the arity.
EVENT_ARITIES = {
    "console_print": 1,        # :406  (text)
    "client_command": 2,       # :450  (player, cmd)
    "server_command": 2,       # :486  (player, cmd)
    "set_configstring": 2,     # :522  (index, value)
    "chat": 3,                 # :557  (player, msg, channel) — recipient is optional
    "player_connect": 2,       # :586  (player, is_bot)      — was 1 on minqlx
    "player_loaded": 1,        # :610  (player)
    "player_disconnect": 2,    # :618  (player, reason)
    "player_spawn": 1,         # :626  (player)
    "vote_ended": 4,           # :674  (votes, vote, args, passed)
    "game_countdown": 0,       # :690  ()
    "game_start": 0,           # :698  ()                     — was 1 on minqlx
    "game_end": 1,             # :711  (aborted)              — was a stats dict
    "round_countdown": 1,      # :719  (round_number)
    "round_start": 1,          # :727  (round_number)
    "round_end": 3,            # :738  (round_number, winning_team, time) — was 1
    "team_switch": 3,          # :750  (player, old_team, new_team)
    "team_switch_attempt": 4,  # :771  (player, old_team, new_team, target) — was 3
    "map": 2,                  # :779  (mapname, factory)
    "new_game": 0,             # :790  ()
    "kill": 3,                 # :801  (victim, killer, mod)  — mod, not a stats dict
    "death": 3,                # :812  (victim, killer, mod)  — mod, not a stats dict
}


class NonexistentGameError(Exception):
    """What Game raises once the game is gone (_game.py:55).

    A bare Exception subclass on the engine too, which is the whole point: it is
    not a ValueError or an AttributeError, so a plugin that guards only those
    lets it through.
    """


class NonexistentPlayerError(Exception):
    """_player.py:92. Raised when a client id no longer maps to a player."""


class SignatureMismatch(Exception):
    """What the engine raises at registration for a bad handler signature."""


class _ExpandedStats:
    """GameClient(n).expanded_stats — engine_fields.h:467.

    num_kills / num_deaths are INT fields with setters. shots_fired / shots_hit are
    WEAPONS fields, and python_objects.c:1156 defines QLX_SETTER_WEAPONS as NULL, so
    they are snapshots with no write path. Assigning raises here as it does there.
    """

    _READ_ONLY = ("shots_fired", "shots_hit", "num_weapon_kills", "num_weapon_deaths",
                  "damage_dealt", "damage_taken")

    def __init__(self):
        object.__setattr__(self, "num_kills", 0)
        object.__setattr__(self, "num_deaths", 0)
        for name in self._READ_ONLY:
            object.__setattr__(self, name, tuple([0] * 16))

    def __setattr__(self, name, value):
        if name in self._READ_ONLY:
            raise AttributeError(f"attribute '{name}' of 'ExpandedStats' is not writable")
        object.__setattr__(self, name, value)


class GameClient:
    """A stand-in for the engine's live gclient_t view (engine_fields.h:536).

    Instances are cached per client id so a plugin that constructs GameClient(id)
    twice sees the same memory, as it would on the engine.
    """

    _instances = {}

    def __new__(cls, client_id):
        if client_id not in cls._instances:
            instance = super().__new__(cls)
            instance.client_id = client_id
            instance.accuracy_shots = 0
            instance.accuracy_hits = 0
            instance.round_shots = 0
            instance.round_hits = 0
            instance.expanded_stats = _ExpandedStats()
            cls._instances[client_id] = instance
        return cls._instances[client_id]

    @classmethod
    def reset_all(cls):
        """Clear the per-id cache between tests."""
        cls._instances.clear()


def thread(func=None, force=False):
    """Pass-through stand-in for @minqlxtended.thread: run inline, synchronously."""
    def decorate(target):
        return target
    return decorate(func) if func is not None else decorate


class Plugin:
    """Minimal Plugin base. Tests assign `game`, `_players`, `db` and `cvars`."""

    def __new__(cls, *args, **kwargs):
        """Set instance state up here, not in __init__, exactly as _plugin.py:137 does.

        A plugin's own __init__ overrides this class's and almost never calls
        super().__init__() — on the engine it does not have to, because __new__ has
        already run. A stub that initialised in __init__ would raise AttributeError on
        the first add_hook of every plugin written the normal way.
        """
        instance = super().__new__(cls)
        instance.hooks = []
        instance.commands = []
        instance.cvars = {}
        instance.messages = []
        instance.center_prints = []
        instance.sounds = []
        instance._players = []
        instance._loaded_plugins = {cls.__name__: instance}
        instance.game = None
        instance.db = None
        return instance

    @property
    def plugins(self):
        """_plugin.py:203. A copy of the loaded-plugin registry, including this one.

        Both halves matter. myFun does
        `self.plugins.pop(self.__class__.__name__)` to skip itself while scanning for
        conflicting !sound commands: it needs its own name present or the pop raises,
        and it needs a copy or the pop would evict a live plugin from the registry.
        """
        return self._loaded_plugins.copy()

    @plugins.setter
    def plugins(self, value):
        self._loaded_plugins = dict(value)

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

    def add_command(self, name, handler, permission=0, channels=None,
                    exclude_channels=(), priority=None, client_cmd_pass=False,
                    client_cmd_perm=5, prefix=True, usage=""):
        """_plugin.py:281. Records rather than registers; tests call handlers directly."""
        names = (name,) if isinstance(name, str) else tuple(name)
        self.commands.append((names, handler, permission, usage))

    def set_cvar_once(self, name, value, flags=0):
        """_plugin.py:602. True if it set the cvar, False if it already existed."""
        if name in self.cvars:
            return False
        self.cvars[name] = value
        return True

    def set_cvar(self, name, value, flags=0):
        self.cvars[name] = value
        return True

    def get_cvar(self, name, return_type=str, default=None):
        return self.cvars.get(name, default)

    def players(self):
        return list(self._players)

    def msg(self, msg, chat_channel=None, **kwargs):
        self.messages.append(msg)

    def center_print(self, msg):
        self.center_prints.append(msg)

    def play_sound(self, sound_path, player=None):
        self.sounds.append((sound_path, player))

    @staticmethod
    def clean_text(text):
        """_plugin.py:701. Strips Quake colour codes."""
        import re
        return re.sub(r"\^[0-9]", "", text)

    def player(self, name, player_list=None):
        """_plugin.py:644. Accepts a client id or a Player; None when absent."""
        candidates = player_list if player_list is not None else self._players
        if isinstance(name, int):
            for candidate in candidates:
                if getattr(candidate, "id", None) == name:
                    return candidate
            return None
        return name if name in candidates else None

    def find_player(self, name, player_list=None):
        """_plugin.py:738. Every player whose cleaned name contains `name`."""
        candidates = player_list if player_list is not None else self._players
        needle = self.clean_text(name).lower()
        return [p for p in candidates
                if needle in self.clean_text(getattr(p, "name", "")).lower()]

    def teams(self, player_list=None):
        """_plugin.py:766. Players bucketed by team, keyed by the Team enum's value."""
        candidates = player_list if player_list is not None else self._players
        buckets = {team.value: [] for team in Team}
        for candidate in candidates:
            team = getattr(candidate, "team", Team.SPECTATOR)
            buckets[getattr(team, "value", team)].append(candidate)
        return buckets

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
    for impersonator in (Plugin, Team, GameState, Gametype, Return, Priority,
                         SignatureMismatch, NonexistentGameError,
                         NonexistentPlayerError, GameClient, _ExpandedStats):
        impersonator.__module__ = "minqlxtended"
    module.Plugin = Plugin
    module.Team = Team
    module.GameState = GameState
    module.Gametype = Gametype
    module.Return = Return
    module.Priority = Priority
    module.thread = thread
    module.next_frame = next_frame
    module.delay = delay
    module.parse_infostring = parse_infostring
    module.GameClient = GameClient
    module.SignatureMismatch = SignatureMismatch
    module.NonexistentGameError = NonexistentGameError
    module.NonexistentPlayerError = NonexistentPlayerError

    # Recorded side effects, so a test can assert what a plugin emitted.
    module.console_lines = []
    module.console_commands = []
    module.logged_exceptions = []
    module.cvars = {}
    module.configstrings = {}

    module.console_print = lambda text: module.console_lines.append(text)
    module.console_command = lambda cmd: module.console_commands.append(cmd)
    module.get_cvar = lambda name, return_type=str, default=None: module.cvars.get(
        name, default)
    module.configstring = lambda index, cached=True: module.configstrings.get(index, "")
    module.log_exception = lambda plugin=None: module.logged_exceptions.append(
        sys.exc_info())

    module.CHAT_CHANNEL = _Channel("chat")
    module.SPECTATOR_CHAT_CHANNEL = _Channel("spectator_chat")

    sys.modules["minqlxtended"] = module
    return module
