"""The ported serverchecker must satisfy the minqlxtended API and keep the
Redis contract QLSM's live status polling depends on.

Live status reads `minqlx:server_status:<port>` at
ui/task_logic/service_runtime.py:97. If this plugin stops writing that key in
that shape, every instance on a minqlxtended host shows as dead in the UI.
"""
import importlib.util
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from stubs.minqlxtended_stub import (  # noqa: E402
    GameState, Gametype, NonexistentGameError, Team, install_stub,
)

PLUGIN_PATH = os.path.join(
    'ql-assets', 'data', 'minqlxtended-plugins', 'serverchecker.py'
)


@pytest.fixture(scope='module')
def module():
    install_stub()
    spec = importlib.util.spec_from_file_location('mxt_serverchecker', PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expiries = {}

    def set(self, key, value):
        self.values[key] = value

    def expire(self, key, seconds):
        self.expiries[key] = seconds


class FakeGame:
    def __init__(self, **overrides):
        self.map = 'campgrounds'
        self.type_short = Gametype.CA
        self.factory = 'ca'
        self.state = GameState.IN_PROGRESS
        self.team_scores = (0, 5, 3, 0)
        self.workshop_items = []
        self.__dict__.update(overrides)


class FakePlayer:
    def __init__(self, name='sarge', steam_id=76561198000000001, team=Team.RED,
                 score=7, ping=23, ip='203.0.113.9:29070'):
        self.name = name
        self.steam_id = steam_id
        self.team = team
        self.score = score
        self.ping = ping
        self._userinfo = {'ip': ip} if ip else {}

    def __contains__(self, key):
        return key in self._userinfo

    def __getitem__(self, key):
        return self._userinfo[key]


class DeadGame:
    """A game that disappeared mid-cycle.

    Game holds no per-instance state and re-reads the engine on every access
    (_game.py:72-73), so once the game is gone every property raises, not just
    the ones touched before it went. `self.game` having handed back an object a
    moment earlier is no protection.
    """

    def __getattr__(self, name):
        raise NonexistentGameError("Tried to read the level when no game is active.")


def _build(module, game=None, players=()):
    """Construct the plugin without starting its background thread."""
    plugin = object.__new__(module.serverchecker)
    plugin.hooks = []
    plugin.cvars = {'net_port': '27960', 'sv_hostname': 'QLSM Test',
                    'sv_maxclients': '16', 'fs_basepath': '/home/ql/steamcmd/steamapps'}
    plugin.connected_players = list(players)
    plugin.game = game
    plugin.db = FakeRedis()
    plugin._match_start_time = None
    plugin._current_workshop_item = None
    plugin._resolved_map = None
    plugin._map_workshop_cache = {}
    return plugin


def test_the_module_targets_minqlxtended(module):
    assert module.serverchecker.__mro__[1].__module__ == 'minqlxtended'


def test_every_hook_registers_against_the_real_event_arities(module):
    """The engine validates handler signatures at registration, not dispatch.

    The stub enforces the same arities, so a stale `on_game_start(self, data)`
    fails here instead of on a live server.
    """
    plugin = _build(module)
    module.serverchecker._register_hooks(plugin)
    assert {event for event, _, _ in plugin.hooks} == {
        'game_start', 'game_end', 'player_connect', 'player_disconnect', 'map'
    }


def test_status_is_written_to_the_qlsm_redis_key(module):
    plugin = _build(module, game=FakeGame(), players=[FakePlayer()])
    plugin.update_status()
    assert 'minqlx:server_status:27960' in plugin.db.values


def test_status_key_expires_so_a_dead_server_disappears(module):
    plugin = _build(module, game=FakeGame(), players=[])
    plugin.update_status()
    assert plugin.db.expiries['minqlx:server_status:27960'] == module.EXPIRE_INTERVAL


def test_team_scores_replace_the_removed_red_score_and_blue_score(module):
    """minqlxtended has no Game.red_score/blue_score; it exposes team_scores
    indexed by Team.index (_game.py:190). Reading the old attributes would
    raise and blank the whole payload."""
    plugin = _build(module, game=FakeGame(team_scores=(0, 5, 3, 0)), players=[])
    plugin.update_status()
    status = json.loads(plugin.db.values['minqlx:server_status:27960'])
    assert status['red_score'] == 5
    assert status['blue_score'] == 3


def test_enum_valued_fields_serialise_as_plain_strings(module):
    plugin = _build(module, game=FakeGame(), players=[FakePlayer()])
    plugin.update_status()
    status = json.loads(plugin.db.values['minqlx:server_status:27960'])
    assert status['state'] == 'in_progress'
    assert status['gametype'] == 'ca'
    assert status['players'][0]['team'] == 'red'


def test_player_udp_port_comes_from_raw_userinfo(module):
    """The packet-fragmentation collector maps players by their client UDP
    port. Player.ip drops the port, so the raw userinfo field is the source."""
    plugin = _build(module, game=FakeGame(), players=[FakePlayer(ip='203.0.113.9:29070')])
    plugin.update_status()
    status = json.loads(plugin.db.values['minqlx:server_status:27960'])
    assert status['players'][0]['udp_port'] == 29070


def test_a_player_without_an_ip_field_yields_a_null_port(module):
    plugin = _build(module, game=FakeGame(), players=[FakePlayer(ip=None)])
    plugin.update_status()
    status = json.loads(plugin.db.values['minqlx:server_status:27960'])
    assert status['players'][0]['udp_port'] is None


def test_no_game_still_writes_a_usable_payload(module):
    """Between map loads self.game is None. The UI must still see the server."""
    plugin = _build(module, game=None, players=[])
    plugin.update_status()
    status = json.loads(plugin.db.values['minqlx:server_status:27960'])
    assert status['map'] == '?'
    assert status['state'] == 'warmup'


def test_a_game_that_vanishes_mid_cycle_still_writes_a_payload(module):
    """A map change between `self.game` and the reads must not cost the write.

    NonexistentGameError is a bare Exception subclass (_game.py:55), so guards
    for ValueError/TypeError/IndexError/AttributeError do not stop it. Unguarded
    it reaches update_status's own `except Exception`, which logs and returns
    without writing — the key then expires and every instance on the host shows
    as dead in the UI, which is the exact failure this plugin exists to prevent.
    Degrade to the same payload as no game at all instead.
    """
    plugin = _build(module, game=DeadGame(), players=[FakePlayer()])
    plugin.update_status()
    status = json.loads(plugin.db.values['minqlx:server_status:27960'])
    assert status['map'] == '?'
    assert status['state'] == 'warmup'
    assert status['gametype'] == '?'
    assert status['factory'] == '?'
    assert status['red_score'] == 0
    assert status['blue_score'] == 0
    assert status['match_start_time'] is None
    # The players are read before the game is touched, so they must survive.
    assert status['players'][0]['name'] == 'sarge'


def test_a_vanished_game_still_expires_the_key(module):
    """The write must be a complete cycle, not just a set with no expiry."""
    plugin = _build(module, game=DeadGame(), players=[])
    plugin.update_status()
    assert plugin.db.expiries['minqlx:server_status:27960'] == module.EXPIRE_INTERVAL


def test_workshop_id_normalisation_accepts_ints_and_trailing_text(module):
    """Game.workshop_items is list[int] on minqlxtended, and workshop.txt lines
    carry trailing comments."""
    assert module._normalize_workshop_id(1234567890) == '1234567890'
    assert module._normalize_workshop_id('1234567890 # blood run') == '1234567890'
    assert module._normalize_workshop_id('  ') is None
    assert module._normalize_workshop_id(None) is None


def test_a_map_resolves_to_its_workshop_item_once_and_is_cached(module, tmp_path):
    plugin = _build(module, game=FakeGame(map='bloodrun'), players=[])
    plugin._map_workshop_cache['bloodrun'] = '778402425'
    plugin._refresh_workshop_item_for_map('bloodrun')
    assert plugin._current_workshop_item == '778402425'
    assert plugin._resolved_map == 'bloodrun'
