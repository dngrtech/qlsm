"""specqueue changes on six hooks, one Game property, and two module functions.

Every one of them is a registration-time or first-use failure on a live server, so each
gets an assertion here. See the P3 plan, Findings 3, 4 and 7.
"""
import importlib.util
import inspect
import os
import re
import sys
import tokenize

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from stubs.minqlxtended_stub import install_stub  # noqa: E402

PLUGIN_PATH = os.path.join('ql-assets', 'data', 'minqlxtended-plugins', 'specqueue.py')


@pytest.fixture(scope='module')
def source():
    with open(PLUGIN_PATH, 'r', encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture(scope='module')
def module():
    install_stub()
    spec = importlib.util.spec_from_file_location('mxt_specqueue', PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_bare_minqlx_attribute_access_survives(source):
    offenders = [
        f"line {i}: {line.strip()}"
        for i, line in enumerate(source.splitlines(), 1)
        if re.search(r'\bminqlx\.(?!\w*tended)', line)
    ]
    assert offenders == [], f"un-ported minqlx references: {offenders}"


def test_no_bare_minqlx_token_survives_in_code():
    """Only a NAME token is a module reference; the Redis keys and prose are not."""
    with tokenize.open(PLUGIN_PATH) as handle:
        offenders = [
            f"line {token.start[0]}"
            for token in tokenize.generate_tokens(handle.readline)
            if token.type == tokenize.NAME and token.string == 'minqlx'
        ]
    assert offenders == []


def test_no_ret_or_pri_constant_survives(source):
    offenders = [
        f"line {i}: {line.strip()}" for i, line in enumerate(source.splitlines(), 1)
        if re.search(r'\b(RET|PRI)_[A-Z_]+', line)
    ]
    assert offenders == [], f"stale constants: {offenders}"


@pytest.mark.parametrize('handler,expected', [
    ('handle_game_start', ['self']),
    ('handle_game_end', ['self', 'aborted']),
    ('handle_player_connect', ['self', 'player', 'is_bot']),
    ('handle_round_end', ['self', 'round_number', 'winning_team', 'time']),
    ('handle_team_switch_attempt',
     ['self', 'player', 'old_team', 'new_team', 'target']),
    ('death_monitor', ['self', 'victim', 'killer', 'mod']),
])
def test_changed_handler_signatures(module, handler, expected):
    """_events.py fixes these arities; _plugin.py:241 checks them at registration."""
    assert list(inspect.signature(
        getattr(module.specqueue, handler)).parameters) == expected


class FakeGame:
    """Enough of Game for specqueue's constructor, which reads it immediately."""
    type_short = 'ca'
    state = 'warmup'
    map = 'campgrounds'
    team_scores = (0, 0, 0, 0)


class FakeDb(dict):
    """Redis stand-in. specqueue's __init__ sweeps clan tags via db.keys()."""

    def keys(self, pattern='*'):
        return []

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def set(self, key, value):
        self[key] = value

    def delete(self, *keys):
        for key in keys:
            self.pop(key, None)


@pytest.fixture
def constructed(module, tmp_path):
    """A live specqueue, with the two pieces of global state its __init__ reads.

    __init__ opens a RotatingFileHandler under fs_homepath/logs (specqueue.py:367)
    and reads self.game.type_short on its first line of real work.
    """
    import minqlxtended
    minqlxtended.cvars['fs_homepath'] = str(tmp_path)
    minqlxtended.Plugin.game = FakeGame()
    minqlxtended.Plugin.db = FakeDb()
    try:
        yield module.specqueue()
    finally:
        minqlxtended.Plugin.game = None
        minqlxtended.Plugin.db = None
        minqlxtended.cvars.pop('fs_homepath', None)


def test_every_hook_registers(constructed):
    """If any signature is stale the constructor raises, so reaching here is the test."""
    plugin = constructed
    events = {event for event, _handler, _priority in plugin.hooks}
    assert events == {
        'new_game', 'game_start', 'game_end', 'round_countdown', 'round_start',
        'round_end', 'death', 'player_connect', 'player_loaded', 'player_disconnect',
        'team_switch', 'team_switch_attempt', 'set_configstring', 'client_command',
        'vote_ended', 'console_print', 'map',
    }


def test_scores_come_from_team_scores_not_red_score(source):
    """Game.red_score / Game.blue_score do not exist on this runtime (_game.py:190)."""
    code_only = '\n'.join(
        re.sub(r'#.*', '', line) for line in source.splitlines()
    )
    assert '.red_score' not in code_only
    assert '.blue_score' not in code_only
    assert 'team_scores' in code_only


def test_game_end_reads_the_aborted_flag_directly(source):
    """The minqlx original read data["ABORTED"] out of the stats dict it was passed.

    Scoped to code: the port explains the change in a comment, and that explanation
    quotes the expression it replaced.
    """
    code_only = '\n'.join(
        line for line in source.splitlines() if not line.lstrip().startswith('#')
    )
    assert 'ABORTED' not in code_only


def test_parse_infostring_replaces_parse_variables(source):
    assert 'parse_variables' not in source
    assert 'parse_infostring' in source


def test_the_afk_sweep_only_moves_a_player_who_stopped_moving(source):
    """The default preset's copy of this file has this block dedented out of its elif,
    which spectates every player on every sweep. Port from the baseline, not that.
    See the P3 plan, Finding 7."""
    lines = source.splitlines()
    marker = next(
        i for i, line in enumerate(lines)
        if 'was moved to spectator for being AFK' in line
    )
    name_line = next(
        i for i in range(marker, 0, -1)
        if 'clean_name' in lines[i] and 'name =' in lines[i]
    )
    elif_line = next(
        i for i in range(name_line, 0, -1) if lines[i].lstrip().startswith('elif ')
    )

    def indent(text):
        return len(text) - len(text.lstrip())

    assert indent(lines[name_line]) > indent(lines[elif_line]), (
        "the AFK move is not nested inside its elif; it will spectate everyone"
    )
