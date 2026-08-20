"""The ported commands.py lists loaded plugins and their commands.

Upstream ships votecommands.py, which is a different plugin entirely (/pass and /veto),
so this port drops nothing — see the P3 plan, Finding 6.
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from stubs.minqlxtended_stub import install_stub  # noqa: E402

PLUGIN_PATH = os.path.join('ql-assets', 'data', 'minqlxtended-plugins', 'commands.py')


@pytest.fixture(scope='module')
def module():
    install_stub()
    spec = importlib.util.spec_from_file_location('mxt_commands', PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeCommand:
    def __init__(self, names, permission):
        self.name = names
        self.permission = permission


class FakePlugin:
    def __init__(self, commands):
        self.commands = commands


class FakeDb:
    def __init__(self, permission=5):
        self._permission = permission

    def get_permission(self, player):
        return self._permission


class FakePlayer:
    def __init__(self):
        self.told = []

    def tell(self, msg):
        self.told.append(msg)


@pytest.fixture
def plugin(module):
    instance = module.commands()
    instance.db = FakeDb()
    instance.plugins = {
        'essentials': FakePlugin([FakeCommand(['map'], 2), FakeCommand(['kick'], 3)]),
        'balance': FakePlugin([FakeCommand(['teams'], 0)]),
    }
    return instance


def test_it_registers_its_commands(plugin):
    registered = [names for names, _h, _p, _u in plugin.commands]
    assert ('plugins',) in registered
    assert ('lc', 'listcmds', 'listcommands') in registered


def test_list_plugins_reports_the_count(plugin):
    player = FakePlayer()
    plugin.list_plugins(player, ['plugins'], None)
    assert player.told[0] == '^12 ^3Plugins found:'
    assert 'balance' in player.told[1] and 'essentials' in player.told[1]


def test_cmd_list_hides_commands_above_the_callers_permission(plugin):
    plugin.db = FakeDb(permission=0)
    plugin.cvars['qlx_commandsOnlyEligible'] = True
    player = FakePlayer()
    plugin.cmd_list(player, ['lc'], None)
    joined = '\n'.join(player.told)
    assert 'teams' in joined
    assert 'kick' not in joined


def test_cmd_list_narrows_by_plugin_name(plugin):
    plugin.cvars['qlx_commandsOnlyEligible'] = False
    player = FakePlayer()
    plugin.cmd_list(player, ['lc', 'balance'], None)
    joined = '\n'.join(player.told)
    assert 'balance' in joined
    assert 'essentials' not in joined


def test_cmd_list_says_so_when_nothing_matches(plugin):
    plugin.cvars['qlx_commandsOnlyEligible'] = False
    player = FakePlayer()
    plugin.cmd_list(player, ['lc', 'nosuchplugin'], None)
    assert player.told == ['^3No Plugin matches ^4nosuchplugin']
