"""The stub must impersonate the pinned engine closely enough to catch real breakage.

If the stub is more permissive than minqlxtended, a port passes CI and fails at plugin
load on a live server — which is the exact failure mode P3's tests exist to prevent.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from stubs.minqlxtended_stub import install_stub  # noqa: E402


@pytest.fixture(scope='module')
def mxt():
    return install_stub()


def test_return_and_priority_replace_the_ret_and_pri_constants(mxt):
    assert mxt.Return.STOP_ALL is not None
    assert mxt.Return.NONE is not None
    assert mxt.Return.USAGE is not None
    assert mxt.Return.STOP_EVENT is not None
    assert mxt.Priority.LOWEST < mxt.Priority.NORMAL < mxt.Priority.HIGHEST


def test_the_old_spellings_are_absent(mxt):
    """_enums.py:591-602 keeps RET_*/PRI_* out of the engine namespace on purpose.

    A stub that still answered to them would let a half-ported plugin pass.
    """
    for gone in ('RET_STOP_ALL', 'RET_NONE', 'RET_USAGE', 'RET_STOP_EVENT',
                 'PRI_LOWEST', 'PRI_HIGH', 'PRI_HIGHEST'):
        assert not hasattr(mxt, gone), gone


def test_parse_infostring_replaces_parse_variables(mxt):
    assert not hasattr(mxt, 'parse_variables')
    assert mxt.parse_infostring(r'\name\sarge\team\red') == {'name': 'sarge', 'team': 'red'}


def test_parse_infostring_preserves_order(mxt):
    """specqueue.py:647 used parse_variables(..., ordered=True); dicts are ordered now."""
    parsed = mxt.parse_infostring(r'\c\1\b\2\a\3')
    assert list(parsed) == ['c', 'b', 'a']


def test_gameclient_int_fields_are_writable(mxt):
    mxt.GameClient.reset_all()
    client = mxt.GameClient(3)
    client.accuracy_shots = 41
    client.expanded_stats.num_kills = 7
    assert mxt.GameClient(3).accuracy_shots == 41
    assert mxt.GameClient(3).expanded_stats.num_kills == 7


def test_per_weapon_arrays_reject_writes(mxt):
    """python_objects.c:1156 — QLX_SETTER_WEAPONS is NULL, so WEAPONS fields are
    snapshots. A port that tries to zero them must fail here, not on a live server."""
    mxt.GameClient.reset_all()
    with pytest.raises(AttributeError):
        mxt.GameClient(1).expanded_stats.shots_fired = (0,) * 16


def test_a_stale_minqlx_signature_is_refused_at_registration(mxt):
    """_plugin.py:241-242 validates at registration, so this is where it must fail."""

    class StalePlugin(mxt.Plugin):
        def handle_game_start(self, data):  # minqlx arity, wrong here
            pass

    plugin = StalePlugin()
    with pytest.raises(mxt.SignatureMismatch):
        plugin.add_hook("game_start", plugin.handle_game_start)


def test_chat_accepts_the_optional_recipient(mxt):
    """_events.py:557 dispatches recipient=None, so both arities must register."""

    class ChatPlugin(mxt.Plugin):
        def three(self, player, msg, channel):
            pass

        def four(self, player, msg, channel, recipient=None):
            pass

    plugin = ChatPlugin()
    plugin.add_hook("chat", plugin.three)
    plugin.add_hook("chat", plugin.four)
    assert len(plugin.hooks) == 2


def test_plugin_records_commands_and_messages(mxt):
    class Chatty(mxt.Plugin):
        def cmd_hello(self, player, msg, channel):
            self.msg("^2hi")

    plugin = Chatty()
    plugin.add_command(("hello", "hi"), plugin.cmd_hello, 2, usage="<name>")
    assert plugin.commands == [(("hello", "hi"), plugin.cmd_hello, 2, "<name>")]

    plugin.cmd_hello(None, ["hello"], None)
    assert plugin.messages == ["^2hi"]


def test_set_cvar_once_does_not_overwrite(mxt):
    plugin = mxt.Plugin()
    assert plugin.set_cvar_once("qlx_thing", "1") is True
    assert plugin.set_cvar_once("qlx_thing", "2") is False
    assert plugin.get_cvar("qlx_thing") == "1"


def test_clean_text_strips_colour_codes(mxt):
    assert mxt.Plugin.clean_text("^1red ^7white") == "red white"
