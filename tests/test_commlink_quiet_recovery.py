import asyncio
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


class FakePlugin:
    @classmethod
    def clean_text(cls, text):
        return text

    def get_cvar(self, name, cast=None):
        return ""

    def msg(self, text):
        raise AssertionError("plugin must not print chat while disabling itself")


def _load_commlink_module(monkeypatch, filename="commlink.py"):
    fake_minqlx = types.SimpleNamespace(
        AbstractChannel=object,
        CHAT_CHANNEL=types.SimpleNamespace(reply=lambda msg: None),
        Plugin=FakePlugin,
        PRI_LOWEST=0,
        RET_STOP_ALL="RET_STOP_ALL",
        RET_USAGE="RET_USAGE",
        console_print=lambda msg: None,
        delay=_identity_decorator,
        get_logger=lambda name: types.SimpleNamespace(
            debug=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
        ),
        log_exception=lambda *args, **kwargs: None,
        thread=_identity_decorator,
        unload_plugin=lambda name: (_ for _ in ()).throw(
            AssertionError("plugin must not unload itself during __init__")
        ),
    )
    monkeypatch.setitem(sys.modules, "minqlx", fake_minqlx)

    module_path = (
        Path(__file__).resolve().parents[1]
        / "ql-assets"
        / "data"
        / "minqlx-plugins"
        / filename
    )
    monkeypatch.syspath_prepend(str(module_path.parent))
    module_name = filename.replace(".py", "_under_test")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_missing_identity_disables_without_unload_or_chat(monkeypatch):
    module = _load_commlink_module(monkeypatch)

    plugin = module.commlink()

    assert plugin.irc is None


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


def test_connect_event_is_silently_dropped_when_offline(monkeypatch):
    module = _load_commlink_module(monkeypatch)
    sent = []
    plugin = module.commlink.__new__(module.commlink)
    plugin.irc = types.SimpleNamespace(
        is_ready=lambda: False,
        msg=lambda *args: sent.append(args),
    )
    plugin.identity = "#test"
    plugin.get_cvar = lambda name, cast=None: True
    plugin.translate_colors = lambda text: text

    player = types.SimpleNamespace(name="Alice", steam_id=123)

    plugin.handle_player_connect(player)

    assert sent == []


def test_parse_data_ignores_malformed_privmsg(monkeypatch):
    module = _load_commlink_module(monkeypatch)
    irc = module.SimpleAsyncIrc(
        "irc.example.test",
        "nick",
        lambda *args: None,
        lambda *args: None,
    )

    asyncio.run(irc.parse_data(":broken PRIVMSG #channel :hello"))


def test_irc_channel_reply_uses_commlink_translation(monkeypatch):
    module = _load_commlink_module(monkeypatch)
    sent = []
    irc = types.SimpleNamespace(msg=lambda recipient, msg: sent.append((recipient, msg)))
    channel = module.IrcChannel(irc, "#test")

    channel.reply("^1hello")

    assert sent == [("#test", "^1hello")]


def test_irc_username_is_sanitized_from_server_name(monkeypatch):
    module = _load_commlink_module(monkeypatch)

    irc = module.SimpleAsyncIrc(
        "irc.example.test",
        "lg-nj-1-99k",
        lambda *args: None,
        lambda *args: None,
    )

    assert irc.username == "lgnj199k"


class ResettingWriter:
    def is_closing(self):
        return False

    def write(self, data):
        raise ConnectionResetError("reset")


def test_write_failure_marks_transport_offline(monkeypatch):
    module = _load_commlink_module(monkeypatch)
    irc = module.SimpleAsyncIrc(
        "irc.example.test",
        "nick",
        lambda *args: None,
        lambda *args: None,
    )
    irc.writer = ResettingWriter()
    irc.set_ready()

    assert irc.write("PRIVMSG #test :hello\r\n") is False
    assert irc.is_ready() is False


def test_auth_signature_round_trips_and_rejects_wrong_secret(monkeypatch):
    module = _load_commlink_module(monkeypatch, "commlink_secured.py")

    wire_text = module.sign_message("secret-one", "hello\r\nworld\x00", now=1000)

    assert wire_text.startswith(module.AUTH_MESSAGE_PREFIX)
    verified = module.verify_message("secret-one", wire_text, now=1000)
    assert verified["text"] == "helloworld"
    assert module.verify_message("secret-two", wire_text, now=1000) is None
    assert module.verify_message("secret-one", wire_text, now=2000) is None


def test_authenticated_outbound_messages_are_signed(monkeypatch):
    module = _load_commlink_module(monkeypatch, "commlink_secured.py")
    sent = []
    plugin = module.commlink_secured.__new__(module.commlink_secured)
    plugin.irc = types.SimpleNamespace(
        is_ready=lambda: True,
        msg=lambda recipient, msg: sent.append((recipient, msg)) or True,
    )
    plugin.get_cvar = lambda name, cast=None: (
        "shared-secret" if name == "qlx_commlinkAuthSecret" else ""
    )

    assert plugin.send_irc_message("#test", "hello") is True

    recipient, wire_text = sent[0]
    assert recipient == "#test"
    assert wire_text.startswith(module.AUTH_MESSAGE_PREFIX)
    verified = module.verify_message("shared-secret", wire_text)
    assert verified["text"] == "hello"


def test_authenticated_inbound_drops_plaintext(monkeypatch):
    module = _load_commlink_module(monkeypatch, "commlink_secured.py")
    plugin = module.commlink_secured.__new__(module.commlink_secured)
    plugin.identity = "#test"
    plugin.get_cvar = lambda name, cast=None: (
        "shared-secret" if name == "qlx_commlinkAuthSecret" else ""
    )
    plugin.players = lambda: (_ for _ in ()).throw(
        AssertionError("plaintext must be dropped")
    )

    plugin.handle_msg(None, ("nick", "user", "host"), "#test", ["hello"])


def test_authenticated_inbound_accepts_signed_message(monkeypatch):
    module = _load_commlink_module(monkeypatch, "commlink_secured.py")
    tells = []
    player = types.SimpleNamespace(tell=tells.append)
    plugin = module.commlink_secured.__new__(module.commlink_secured)
    plugin.identity = "#test"
    plugin.status_request = False
    plugin.get_cvar = lambda name, cast=None: (
        "shared-secret" if name == "qlx_commlinkAuthSecret" else True
    )
    plugin.db = types.SimpleNamespace(get_flag=lambda *args, **kwargs: True)
    plugin.game = types.SimpleNamespace(type_short="ca", state="warmup")
    plugin.players = lambda: [player]
    plugin.teams = lambda: {"free": []}
    plugin.auth_seen_nonces = {}
    wire_text = module.sign_message("shared-secret", "hello world")

    plugin.handle_msg(None, ("Remote", "user", "host"), "#test", [wire_text])

    assert tells == ["[CommLink] ^4Remote^7:^3 hello world"]


def test_authenticated_inbound_rejects_replayed_message(monkeypatch):
    module = _load_commlink_module(monkeypatch, "commlink_secured.py")
    tells = []
    player = types.SimpleNamespace(tell=tells.append)
    plugin = module.commlink_secured.__new__(module.commlink_secured)
    plugin.identity = "#test"
    plugin.status_request = False
    plugin.get_cvar = lambda name, cast=None: (
        "shared-secret" if name == "qlx_commlinkAuthSecret" else True
    )
    plugin.db = types.SimpleNamespace(get_flag=lambda *args, **kwargs: True)
    plugin.game = types.SimpleNamespace(type_short="ca", state="warmup")
    plugin.players = lambda: [player]
    plugin.teams = lambda: {"free": []}
    plugin.auth_seen_nonces = {}
    wire_text = module.sign_message("shared-secret", "hello world")

    plugin.handle_msg(None, ("Remote", "user", "host"), "#test", [wire_text])
    plugin.handle_msg(None, ("Remote", "user", "host"), "#test", [wire_text])

    assert tells == ["[CommLink] ^4Remote^7:^3 hello world"]


def test_commlink_ignores_messages_from_other_channels(monkeypatch):
    module = _load_commlink_module(monkeypatch, "commlink_secured.py")
    plugin = module.commlink_secured.__new__(module.commlink_secured)
    plugin.identity = "#test"
    plugin.get_cvar = lambda name, cast=None: ""
    plugin.players = lambda: (_ for _ in ()).throw(
        AssertionError("wrong channel must be dropped")
    )

    plugin.handle_msg(None, ("nick", "user", "host"), "#other", ["hello"])


def test_short_status_like_message_does_not_raise(monkeypatch):
    module = _load_commlink_module(monkeypatch, "commlink_secured.py")
    tells = []
    player = types.SimpleNamespace(tell=tells.append)
    plugin = module.commlink_secured.__new__(module.commlink_secured)
    plugin.identity = "#test"
    plugin.status_request = True
    plugin.get_cvar = lambda name, cast=None: ""
    plugin.db = types.SimpleNamespace(get_flag=lambda *args, **kwargs: True)
    plugin.game = types.SimpleNamespace(type_short="ca", state="warmup")
    plugin.players = lambda: [player]
    plugin.teams = lambda: {"free": []}

    plugin.handle_msg(None, ("Remote", "user", "host"), "#test", ["Red-"])

    assert tells == ["[CommLink] ^4Remote^7:^3 Red-"]


class CapturingWriter:
    def __init__(self):
        self.writes = []

    def is_closing(self):
        return False

    def write(self, data):
        self.writes.append(data)


def test_irc_write_strips_control_characters(monkeypatch):
    module = _load_commlink_module(monkeypatch, "commlink_secured.py")
    irc = module.SimpleAsyncIrc(
        "irc.example.test",
        "nick",
        lambda *args: None,
        lambda *args: None,
    )
    writer = CapturingWriter()
    irc.writer = writer
    irc.set_ready()

    assert irc.msg("#test\r\nJOIN #evil", "hello\r\nPONG :x\x00") is True

    assert writer.writes == [b"PRIVMSG #testJOIN #evil :helloPONG :x\r\n"]
