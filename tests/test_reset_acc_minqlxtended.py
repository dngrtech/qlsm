"""reset_acc's C patch becomes pure Python on minqlxtended.

The engine exposes gclient_t as writable memory (engine_fields.h:536), so the three
patched functions QLSM added to minqlx are replaced by attribute writes. One thing the
patch did cannot be reproduced: the per-weapon shotsFired/shotsHit arrays are WEAPONS
fields, and python_objects.c:1156 gives WEAPONS no setter. See the P3 plan, Finding 5.
"""
import importlib.util
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from stubs.minqlxtended_stub import install_stub  # noqa: E402

PLUGIN_PATH = os.path.join('ql-assets', 'data', 'minqlxtended-plugins', 'reset_acc.py')


@pytest.fixture(scope='module')
def source():
    with open(PLUGIN_PATH, 'r', encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture(scope='module')
def module():
    install_stub()
    spec = importlib.util.spec_from_file_location('mxt_reset_acc', PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakePlayer:
    def __init__(self, client_id=0, steam_id=76561198000000001, name='sarge'):
        self.id = client_id
        self.steam_id = steam_id
        self.name = name
        self.clean_name = name
        self.score = 99
        self.told = []

    def tell(self, msg):
        self.told.append(msg)


class FakeDb(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)

    def set(self, key, value):
        self[key] = value

    def delete(self, *keys):
        for key in keys:
            self.pop(key, None)


@pytest.fixture
def plugin(module):
    import minqlxtended
    minqlxtended.GameClient.reset_all()
    instance = module.reset_acc()
    instance.db = FakeDb()
    return instance


def _dirty(client_id):
    """Put non-zero values everywhere the C patch used to zero."""
    import minqlxtended
    client = minqlxtended.GameClient(client_id)
    client.accuracy_shots = 120
    client.accuracy_hits = 44
    client.round_shots = 12
    client.round_hits = 5
    client.expanded_stats.num_kills = 9
    client.expanded_stats.num_deaths = 3
    return client


def test_the_patched_functions_are_gone(source):
    """minqlx.reset_player_stats / reset_player_accuracy / set_score do not exist here."""
    assert 'minqlxtended.reset_player_stats' not in source
    assert 'minqlxtended.reset_player_accuracy' not in source
    assert 'minqlxtended.set_score' not in source


def test_kill_hook_takes_mod_not_a_stats_dict(module):
    """_events.py:801 dispatches (victim, killer, mod). Same arity, different meaning."""
    params = list(inspect.signature(module.reset_acc.handle_kill).parameters)
    assert params == ['self', 'victim', 'killer', 'mod']


def test_it_registers_every_hook(plugin):
    events = sorted(event for event, _handler, _priority in plugin.hooks)
    assert events == ['kill', 'player_disconnect', 'player_loaded']


def test_zero_stats_clears_accuracy_kills_and_deaths(module):
    client = _dirty(2)
    assert module._zero_stats(2) is True
    assert client.accuracy_shots == 0
    assert client.accuracy_hits == 0
    assert client.round_shots == 0
    assert client.round_hits == 0
    assert client.expanded_stats.num_kills == 0
    assert client.expanded_stats.num_deaths == 0


def test_zero_accuracy_leaves_kills_and_deaths_alone(module):
    client = _dirty(3)
    assert module._zero_accuracy(3) is True
    assert client.accuracy_shots == 0
    assert client.accuracy_hits == 0
    assert client.expanded_stats.num_kills == 9
    assert client.expanded_stats.num_deaths == 3


def test_zero_stats_does_not_try_to_write_the_per_weapon_arrays(module):
    """Writing them raises (python_objects.c:1156). If the port tried, this would error
    rather than return True."""
    _dirty(4)
    assert module._zero_stats(4) is True


def test_reset_all_zeroes_the_score(plugin):
    player = FakePlayer(client_id=5)
    _dirty(5)
    plugin._reset_all(player, player)
    assert player.score == 0


def test_reset_all_tells_the_player_what_it_did(plugin):
    player = FakePlayer(client_id=6)
    _dirty(6)
    plugin._reset_all(player, player)
    said = ' '.join(player.told).lower()
    assert 'reset' in said


def test_no_message_promises_the_per_weapon_breakdown_was_cleared(source):
    """The minqlx original told the player "WEAP and +acc are now 0". WEAP no longer
    resets, so saying so would promise something the port does not deliver.

    Scoped to lines that talk to a player: the docstrings explain the WEAPONS field
    limitation at length, and should.
    """
    spoken = [line for line in source.splitlines()
              if '.tell(' in line or 'self.msg(' in line]
    offenders = [line.strip() for line in spoken if 'WEAP' in line]
    assert offenders == [], offenders


def test_silent_reset_says_nothing(plugin):
    player = FakePlayer(client_id=7)
    _dirty(7)
    plugin._reset_all(player, player, silent=True)
    assert player.told == []


def test_resetting_someone_else_tells_both_parties(plugin):
    admin = FakePlayer(client_id=8, name='admin')
    target = FakePlayer(client_id=9, name='sarge')
    _dirty(9)
    plugin._reset_all(admin, target)
    assert admin.told and target.told


class KillPlayer(FakePlayer):
    def __init__(self, client_id, steam_id, team):
        super().__init__(client_id=client_id, steam_id=steam_id)
        self.team = team


def _scheduled(plugin):
    """Record who the kill handler scheduled a reset for, without timers."""
    calls = []
    plugin._schedule_auto_reset = lambda player, trigger: calls.append(
        (player.steam_id, trigger))
    return calls


def test_a_normal_kill_schedules_for_both_killer_and_victim(plugin):
    import minqlxtended
    calls = _scheduled(plugin)
    killer = KillPlayer(1, 111, minqlxtended.Team.RED)
    victim = KillPlayer(2, 222, minqlxtended.Team.BLUE)
    plugin.handle_kill(victim, killer, None)
    assert calls == [(111, 'kill'), (222, 'death')]


def test_a_teamkill_credits_no_kill(plugin):
    import minqlxtended
    calls = _scheduled(plugin)
    killer = KillPlayer(1, 111, minqlxtended.Team.RED)
    victim = KillPlayer(2, 222, minqlxtended.Team.RED)
    plugin.handle_kill(victim, killer, None)
    assert calls == [(222, 'death')]


def test_an_ffa_kill_is_not_a_teamkill(plugin):
    """Everyone is on the free team in FFA, which is this plugin's main use case.

    Treating same-team as a teamkill without excluding `free` would suppress the
    killer's auto-reset on every FFA kill.
    """
    import minqlxtended
    calls = _scheduled(plugin)
    killer = KillPlayer(1, 111, minqlxtended.Team.FREE)
    victim = KillPlayer(2, 222, minqlxtended.Team.FREE)
    plugin.handle_kill(victim, killer, None)
    assert calls == [(111, 'kill'), (222, 'death')]


def test_a_suicide_credits_no_kill(plugin):
    import minqlxtended
    calls = _scheduled(plugin)
    player = KillPlayer(1, 111, minqlxtended.Team.FREE)
    plugin.handle_kill(player, player, None)
    assert calls == [(111, 'death')]
