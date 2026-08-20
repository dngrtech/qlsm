"""The ported player_info must accept player_connect's new arity, and must not carry
the iouonegirl abstract base across.

Two independent things are checked here:

1. _events.py:586 dispatches (player, is_bot); minqlx passed (player) alone.
   minqlxtended validates at registration (_plugin.py:241), so a stale signature stops
   the whole plugin from loading rather than failing on the first connect.

2. On minqlx this plugin subclasses iouonegirlPlugin, an abstract base that downloads
   itself from github.com/dsverdlo/minqlx-plugins at import time and ships an
   auto-updater for *minqlx* plugins. That base is not in the minqlxtended baseline,
   and pulling it in would fetch minqlx-API code onto a minqlxtended host. The port
   subclasses minqlxtended.Plugin and inlines the one helper it actually used.
"""
import importlib.util
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from stubs.minqlxtended_stub import install_stub  # noqa: E402

PLUGIN_PATH = os.path.join('ql-assets', 'data', 'minqlxtended-plugins', 'player_info.py')


@pytest.fixture(scope='module')
def source():
    with open(PLUGIN_PATH, 'r', encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture(scope='module')
def module():
    install_stub()
    spec = importlib.util.spec_from_file_location('mxt_player_info', PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakePlayer:
    def __init__(self, client_id=0, steam_id=76561198000000001, name='sarge'):
        self.id = client_id
        self.steam_id = steam_id
        self.name = name
        self.clean_name = name
        self.told = []

    def tell(self, msg):
        self.told.append(msg)


def test_the_module_imports_without_a_minqlx_module(module):
    """Importing at all proves nothing in the file reaches for bare `minqlx`."""
    assert hasattr(module, 'player_info')


def test_it_does_not_import_the_iouonegirl_base(source):
    """The name still appears in the file — in the original author's copyright header,
    in the comment explaining why the base was dropped, and in a user-facing "Contact
    iouonegirl" string. None of those pulls the base in. What must not survive is an
    import of it or a reference to the class itself.
    """
    assert 'iouonegirlPlugin' not in source
    assert 'import iouonegirl' not in source
    assert 'from .iouonegirl' not in source


def test_it_subclasses_the_engine_plugin_directly(module):
    import minqlxtended
    assert module.player_info.__bases__ == (minqlxtended.Plugin,)


def test_it_makes_no_network_call_at_import(source):
    """The minqlx original does requests.get() at module scope to self-install its base.

    Anything that runs at import runs on every plugin load, on a game server with no
    guarantee of outbound access.
    """
    module_level = [
        line for line in source.splitlines()
        if line and not line[0].isspace() and 'requests.get' in line
    ]
    assert module_level == []


def test_player_connect_registers_with_the_new_arity(module):
    """Registration is where the engine checks, so registration is where we check."""
    plugin = module.player_info()
    events = [event for event, _handler, _priority in plugin.hooks]
    assert 'player_connect' in events


def test_player_connect_handler_takes_player_and_is_bot(module):
    params = list(
        inspect.signature(module.player_info.handle_player_connect).parameters
    )
    assert params == ['self', 'player', 'is_bot']


def test_it_hooks_at_lowest_priority(module):
    import minqlxtended
    plugin = module.player_info()
    priorities = {event: priority for event, _handler, priority in plugin.hooks}
    assert priorities['player_connect'] == minqlxtended.Priority.LOWEST


def test_a_bot_connecting_triggers_no_lookup(module):
    """is_bot is authoritative here, where minqlx had to guess from the steam id."""
    plugin = module.player_info()
    plugin.fetched = []
    plugin.fetch = lambda *args, **kwargs: plugin.fetched.append(args)
    plugin.cvars['qlx_pinfo_display_auto'] = 1

    plugin.handle_player_connect(FakePlayer(steam_id=90000000000000001), True)
    assert plugin.fetched == []


def test_find_by_name_or_id_is_available_on_the_plugin(module):
    """The one helper the dropped base class actually provided."""
    assert callable(module.player_info.find_by_name_or_id)


def test_find_by_name_or_id_reports_when_nothing_matches(module):
    plugin = module.player_info()
    plugin._players = []
    asker = FakePlayer()
    assert plugin.find_by_name_or_id(asker, 'nobody') is None
    assert 'no players matched' in asker.told[0]


def test_find_by_name_or_id_returns_a_single_match(module):
    plugin = module.player_info()
    target = FakePlayer(client_id=4, name='sarge')
    plugin._players = [target]
    asker = FakePlayer(client_id=1, name='doom')
    assert plugin.find_by_name_or_id(asker, 'sarge') is target


def test_find_by_name_or_id_refuses_an_ambiguous_match(module):
    plugin = module.player_info()
    plugin._players = [FakePlayer(client_id=4, name='sarge'),
                       FakePlayer(client_id=5, name='sarge2')]
    asker = FakePlayer(client_id=1, name='doom')
    assert plugin.find_by_name_or_id(asker, 'sarge') is None
    assert 'players matched' in asker.told[0]


def test_it_does_not_call_a_nonexistent_plugin_kick(source):
    """`self.kick(...)` is not a Plugin method on either runtime.

    The minqlx original calls it in the deactivated-account path, where it would have
    raised AttributeError. The port uses Player.kick(reason) (_player.py:926), which
    exists and takes the reason directly rather than an id plus a reason.
    """
    assert 'self.kick(' not in source
