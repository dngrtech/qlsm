"""The scanner proves incompatibility, never compatibility.

Both directions matter: a minqlx plugin must be rejected for a minqlxtended
host, and a minqlxtended plugin must be rejected for a minqlx host. The second
direction is the one nobody exercises by hand, so it is tested first-class here
rather than as an afterthought.
"""
import hashlib

import pytest

from ui.plugin_compat import (
    VERDICT_COMPATIBLE,
    VERDICT_INCOMPATIBLE,
    VERDICT_UNKNOWN,
    classify,
    code_only,
    scan_incompatibilities,
)
from ui.runtime import MINQLX, MINQLXTENDED


# --- code_only ------------------------------------------------------------

def test_code_only_blanks_a_trailing_comment_but_keeps_the_code():
    masked = code_only('x = 1  # RET_STOP_ALL\n')
    assert 'RET_STOP_ALL' not in masked
    assert 'x = 1' in masked


def test_code_only_blanks_a_docstring():
    masked = code_only('"""mentions import minqlx in prose"""\nx = 1\n')
    assert 'import minqlx' not in masked


def test_code_only_preserves_line_numbers_across_a_multiline_string():
    source = '"""a\nb\nc"""\nimport minqlx\n'
    masked = code_only(source)
    assert masked.splitlines()[3] == 'import minqlx'


def test_code_only_returns_the_text_unchanged_when_it_cannot_tokenize():
    """A file that does not tokenize still has to be scannable — falling back to
    the raw text keeps a broken file scannable rather than silently clean."""
    broken = 'def f(:\n    import minqlx\n'
    assert 'import minqlx' in code_only(broken)


def test_code_only_blanks_an_fstring_body_on_any_python_version():
    """PEP 701 (3.12) retokenizes an f-string as FSTRING_START/MIDDLE/END
    instead of one STRING token. The dev venv here is 3.10, where this masks
    correctly either way — but CI and production both run 3.12, where a mask
    that only knows about STRING lets an f-string's literal text straight
    through unmasked."""
    masked = code_only('x = f"note: import minqlx and RET_STOP_ALL"\n')
    assert 'import minqlx' not in masked
    assert 'RET_STOP_ALL' not in masked


def test_an_fstring_body_is_not_flagged_as_a_minqlx_reference():
    """Same false positive as above, exercised through the public scanning
    entry point rather than `code_only()` directly."""
    source = 'x = f"note: import minqlx and RET_STOP_ALL"\n'
    assert scan_incompatibilities(source, MINQLXTENDED) == []


# --- minqlx source, minqlxtended target -----------------------------------

def test_a_bare_minqlx_import_is_incompatible_with_minqlxtended():
    reasons = scan_incompatibilities('import minqlx\n', MINQLXTENDED)
    assert reasons
    assert 'line 1' in reasons[0]


def test_minqlxtended_import_is_not_flagged_as_a_minqlx_import():
    """`minqlx` is a prefix of `minqlxtended`; a substring match would strip
    every correctly-ported file."""
    assert scan_incompatibilities('import minqlxtended\n', MINQLXTENDED) == []


def test_a_dotted_minqlxtended_reference_is_not_flagged_for_minqlxtended():
    assert scan_incompatibilities('minqlxtended.console_print("x")\n', MINQLXTENDED) == []


@pytest.mark.parametrize('snippet', [
    'return minqlx.RET_STOP_ALL\n',
    'self.add_hook("chat", self.h, priority=minqlx.PRI_LOWEST)\n',
    'if mod == minqlx.MOD_ROCKET: pass\n',
    'flags = minqlx.CVAR_ARCHIVE\n',
    'player.set_health(100)\n',
    'player.god()\n',
    'self.play_sound("x")\n',
    'self.center_print("x")\n',
    'name = minqlx.TEAMS[1]\n',
])
def test_removed_minqlx_apis_are_incompatible_with_minqlxtended(snippet):
    assert scan_incompatibilities(snippet, MINQLXTENDED), snippet


# --- minqlxtended source, minqlx target -----------------------------------

@pytest.mark.parametrize('snippet', [
    'import minqlxtended\n',
    'from minqlxtended import Plugin\n',
    'return minqlxtended.Return.STOP_ALL\n',
    'self.add_hook("chat", self.h, minqlxtended.Priority.LOWEST)\n',
    'if mod == minqlxtended.Weapon.ROCKET: pass\n',
])
def test_minqlxtended_apis_are_incompatible_with_minqlx(snippet):
    assert scan_incompatibilities(snippet, MINQLX), snippet


def test_a_plain_minqlx_plugin_is_not_flagged_for_minqlx():
    source = 'import minqlx\n\nclass p(minqlx.Plugin):\n    pass\n'
    assert scan_incompatibilities(source, MINQLX) == []


# --- handler arity --------------------------------------------------------

def test_a_stale_player_connect_arity_is_incompatible_with_minqlxtended():
    """minqlxtended dispatches (player, is_bot) and validates at registration,
    so a one-argument handler stops the whole plugin from loading."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.handle_connect)\n'
        '    def handle_connect(self, player):\n'
        '        pass\n'
    )
    reasons = scan_incompatibilities(source, MINQLXTENDED)
    assert any('player_connect' in r for r in reasons), reasons


def test_the_correct_player_connect_arity_is_not_flagged():
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.handle_connect)\n'
        '    def handle_connect(self, player, is_bot):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_an_event_with_equal_arity_on_both_runtimes_is_never_flagged():
    """`game_end` takes one argument on both runtimes — same count, different
    meaning (a stats dict on minqlx, a bool on minqlxtended). It stays in
    `_EVENT_ARITY` on purpose, so this has to genuinely run the count
    comparison and find it equal, not just skip because the event is absent
    from the table (see the not-in-table case below)."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("game_end", self.handle_game_end)\n'
        '    def handle_game_end(self, data):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_an_event_not_in_the_arity_table_is_never_flagged():
    """`map` is (mapname, factory) on both runtimes but isn't in
    `_EVENT_ARITY` at all — a different path than the equal-arity case above,
    where the event is present but the counts happen to match."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("map", self.handle_map)\n'
        '    def handle_map(self, mapname, factory):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_handler_taking_star_args_is_never_flagged():
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("kill", self.handle_kill)\n'
        '    def handle_kill(self, *args):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_stale_round_end_arity_is_incompatible_with_minqlx():
    """`_EVENT_ARITY[MINQLX]` had zero coverage — every prior arity test
    targeted minqlxtended. minqlx's round_end dispatches one argument; a
    handler ported from minqlxtended without updating its signature is
    stale."""
    source = (
        'import minqlx\n'
        'class p(minqlx.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("round_end", self.handle_round_end)\n'
        '    def handle_round_end(self, data, extra):\n'
        '        pass\n'
    )
    reasons = scan_incompatibilities(source, MINQLX)
    assert any('round_end' in r for r in reasons), reasons


def test_a_commented_out_add_hook_call_does_not_trigger_an_arity_check():
    """`_ADD_HOOK` has to run against raw text to see the quoted event name
    (`code_only()` blanks it), which means it could match a call sitting
    inside a comment. The handler here is never actually registered — only a
    real, live `add_hook()` call may trigger the arity comparison."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        pass\n'
        '    # self.add_hook("player_connect", self.handle_connect)\n'
        '    def handle_connect(self, player):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_call_valued_default_argument_does_not_truncate_the_signature():
    """A nested `(...)` in a default value must not truncate the captured
    parameter list at the first `)` — that would misdetect a correctly-ported
    two-argument handler as stale."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.handle_connect)\n'
        '    def handle_connect(self, player, is_bot=default_factory()):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


# --- classify -------------------------------------------------------------

def test_a_hash_match_is_compatible_even_when_tokens_look_wrong():
    """The allow-list is the only proof of compatibility. A vendored baseline
    file is compatible by definition, whatever a heuristic thinks of it."""
    text = 'import minqlx\n'
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    verdict, reasons = classify(text, MINQLXTENDED, baseline_sha256=digest)
    assert verdict == VERDICT_COMPATIBLE
    assert reasons == []


def test_a_token_hit_with_no_hash_match_is_incompatible():
    verdict, reasons = classify('import minqlx\n', MINQLXTENDED, baseline_sha256=None)
    assert verdict == VERDICT_INCOMPATIBLE
    assert reasons


def test_a_clean_file_with_no_hash_match_is_unknown():
    """Custom, or a bundled plugin someone edited. Not provably broken, not
    provably fine — and the design strips anything that is not `compatible`."""
    verdict, reasons = classify('x = 1\n', MINQLXTENDED, baseline_sha256=None)
    assert verdict == VERDICT_UNKNOWN
    assert reasons == []


def test_a_wrong_hash_falls_through_to_the_scanner():
    verdict, _ = classify('import minqlx\n', MINQLXTENDED, baseline_sha256='deadbeef')
    assert verdict == VERDICT_INCOMPATIBLE
