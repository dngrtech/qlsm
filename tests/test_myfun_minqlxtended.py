"""myFun's hook arities are unchanged; its constants are not.

38 of the 45 constant substitutions in this file are RET_STOP_ALL. A missed one is an
AttributeError at the moment a player types the command that reaches it — long after
plugin load, and only on that code path. Hence the source-level sweep below.
"""
import importlib.util
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from stubs.minqlxtended_stub import install_stub  # noqa: E402

PLUGIN_PATH = os.path.join('ql-assets', 'data', 'minqlxtended-plugins', 'myFun.py')


@pytest.fixture(scope='module')
def source():
    with open(PLUGIN_PATH, 'r', encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture(scope='module')
def module():
    install_stub()
    spec = importlib.util.spec_from_file_location('mxt_myfun', PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bare_minqlx_identifiers(path):
    """Every place `minqlx` is used as a Python name, ignoring strings and comments.

    Tokenising rather than grepping matters here. This file legitimately contains the
    word in three kinds of place a text search cannot tell apart from code:

      - Steam Workshop item titles in SOUND_PACKS, matched against the workshop by
        exact name ("Duke Nukem Voice Sound Pack for minqlx");
      - Redis key prefixes like "minqlx:myFun:addedTriggers:{}", which are a QLSM
        contract rather than a minqlx API, exactly as serverchecker's key is;
      - prose in the module docstring.

    Only a NAME token is a reference to the module.
    """
    import tokenize
    with tokenize.open(path) as handle:
        return [
            f"line {token.start[0]}"
            for token in tokenize.generate_tokens(handle.readline)
            if token.type == tokenize.NAME and token.string == 'minqlx'
        ]


def test_no_bare_minqlx_attribute_access_survives(source):
    """`minqlxtended` contains `minqlx`, so match the module name at a word boundary
    followed by a dot — `minqlx.` but never `minqlxtended.`."""
    offenders = [
        f"line {i}: {line.strip()}"
        for i, line in enumerate(source.splitlines(), 1)
        if re.search(r'\bminqlx\.(?!\w*tended)', line)
    ]
    assert offenders == [], f"un-ported minqlx references: {offenders}"


def test_no_bare_minqlx_token_survives_in_code():
    """Attribute access is not the only way to name the module.

    reset_acc.py reached it as `hasattr(minqlx, "...")`, which a dot-anchored sweep
    walks straight past.
    """
    assert bare_minqlx_identifiers(PLUGIN_PATH) == []


def test_no_ret_or_pri_constant_survives(source):
    """_enums.py:591-602 keeps these out of the namespace; they raise AttributeError."""
    offenders = [
        f"line {i}: {line.strip()}" for i, line in enumerate(source.splitlines(), 1)
        if re.search(r'\b(RET|PRI)_[A-Z_]+', line)
    ]
    assert offenders == [], f"stale constants: {offenders}"


def test_every_referenced_engine_attribute_exists(source):
    """Whatever the substitution produced has to be something the engine actually has.

    The set is pinned rather than sampled: a new name appearing here means the sweep
    rewrote something nobody checked against __init__.py.
    """
    referenced = set(re.findall(r'minqlxtended\.[A-Za-z_][A-Za-z_.]*', source))
    allowed = {
        'minqlxtended.Plugin',
        'minqlxtended.Return.NONE',
        'minqlxtended.Return.STOP_ALL',
        'minqlxtended.Priority.LOWEST',
        'minqlxtended.thread',
        'minqlxtended.delay',
        'minqlxtended.next_frame',
        'minqlxtended.console_print',
        'minqlxtended.console_command',
        'minqlxtended.log_exception',
    }
    assert referenced <= allowed, f"unverified engine attributes: {referenced - allowed}"


def test_it_registers_every_hook(module):
    plugin = module.myFun()
    events = sorted(event for event, _handler, _priority in plugin.hooks)
    assert events == sorted([
        'chat', 'console_print', 'server_command', 'player_disconnect', 'player_loaded',
    ])


def test_player_loaded_hooks_at_lowest_priority(module):
    import minqlxtended
    plugin = module.myFun()
    priorities = {event: priority for event, _h, priority in plugin.hooks}
    assert priorities['player_loaded'] == minqlxtended.Priority.LOWEST


def test_sound_paths_are_validated_before_reaching_the_console(module):
    """`!sound <path>` reaches console_command("fdir {}"), and the engine console
    treats ';' as a command separator — so an unfiltered argument hands the caller
    the rest of the console. Permission 3 gates who can try it, which makes this a
    moderator-scope hole rather than an open one, but a moderator asking for a sound
    should not get the console.

    Fixed on the minqlx copy in `8f4c8e3` on main. The port predates that fix, so it
    is applied here too — otherwise the same input is safe on one runtime and not the
    other.
    """
    assert module.is_safe_sound_path('sound/vo/crash.ogg')
    assert module.is_safe_sound_path('doompack/hi-there_1.wav')
    assert module.is_safe_sound_path('a-b_c.d/e')

    assert not module.is_safe_sound_path('')
    assert not module.is_safe_sound_path('x; quit')
    assert not module.is_safe_sound_path('sound/a b.ogg')
    assert not module.is_safe_sound_path('"; rcon')
    # re's `$` also matches just before a trailing newline, so the anchor has to be
    # `\Z`. Unreachable via chat (args arrive whitespace-split) but free to get right.
    assert not module.is_safe_sound_path('sound/ok.ogg\n')


def test_the_fdir_call_is_guarded_by_that_check(source):
    """A helper nothing calls is not a fix. Assert the guard precedes the call."""
    code_only = [re.sub(r'#.*', '', line) for line in source.splitlines()]
    guard = next(i for i, line in enumerate(code_only) if 'is_safe_sound_path(msg[1])' in line)
    call = next(i for i, line in enumerate(code_only) if 'console_command("fdir' in line)
    assert guard < call, "the fdir call is not gated by the path check"
