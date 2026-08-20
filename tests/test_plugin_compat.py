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


def test_code_only_masks_forbidden_text_even_with_doubled_braces_in_an_fstring():
    """On 3.12, FSTRING_MIDDLE's token text collapses a doubled `{{`/`}}` to a
    single brace, so the token string is shorter than the source span it
    covers. Masking has to blank by the token's start/end source coordinates,
    not by `len(token.string)`, or the doubled-brace prefix throws off every
    position after it and the tail of the line survives unmasked."""
    masked = code_only('x = f"{{escaped}} import minqlx and RET_STOP_ALL"\n')
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


@pytest.mark.parametrize('default_expr', [
    'is_bot=[1, 2, 3]',
    'flags={1, 2, 3}',
    "meta={'k0':0,'k1':1,'k2':2}",
])
def test_a_default_value_with_a_top_level_comma_does_not_split_the_signature(default_expr):
    """A default's own commas -- inside a list/set/dict literal -- must not
    be mistaken for parameter separators. Splitting on every comma regardless
    of nesting would inflate the parameter count and flag a correctly-ported
    two-argument handler as stale. Mutation-verified in the fix report: each
    of these three cases genuinely flags under a naive `.split(',')` and
    doesn't under the bracket-depth-aware split."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.handle_connect)\n'
        f'    def handle_connect(self, player, {default_expr}):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_three_param_lambda_default_does_not_inflate_game_start_arity():
    """`lambda` opens no bracket, so its own parameter commas sit at the same
    depth as the signature's -- a naive bracket-only depth tracker walks
    straight past them. `game_start` dispatches 0 arguments on minqlxtended;
    this handler takes only the implicit `cb` default and must not be flagged
    for the lambda's 3 parameters."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("game_start", self.h)\n'
        '    def h(self, cb=lambda a, b, c: a):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_two_param_lambda_default_does_not_inflate_player_connect_arity():
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.h)\n'
        '    def h(self, player, is_bot, key=lambda a, b: a):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_single_param_lambda_default_is_not_flagged():
    """A one-parameter lambda has no internal comma to mishandle, so this
    passes even without the lambda-scope fix -- kept as a baseline alongside
    the multi-param cases above rather than as proof of the fix itself."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.handle_connect)\n'
        '    def handle_connect(self, player, cb=lambda a: a):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_lambda_body_containing_a_dict_literal_does_not_end_the_header_early():
    """The lambda header must close on the `:` right after its own parameter
    list (`a, b:`), not on the dict literal's key-value `:` one depth deeper
    in the body. Targets `game_start` (expected 0 args on minqlxtended)
    rather than a 2-arg event: with a wider arity gap, closing the header
    early -- which merges only one comma's worth of text back into the
    signature -- still overshoots the expected count and is guaranteed to
    surface as a flag, rather than landing exactly on the boundary by
    chance."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("game_start", self.h)\n'
        '    def h(self, cb=lambda a, b: {1: 2}):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_lambda_nested_inside_a_call_default_does_not_split_the_signature():
    """Composability check, not a lambda-specific regression test: a lambda
    passed as an argument to another call is already inside that call's own
    `(...)`, so `_scan_params`'s pre-existing bracket-depth tracking (round 2)
    keeps every comma inside it below depth 1 whether or not `lambda` is
    understood at all -- lambda-awareness can only matter for a comma that
    sits at the very same depth as the signature's own, which a call-wrapped
    lambda's commas never do. Kept because the team lead asked for this exact
    shape and it's a real one plugin authors write; not counted among the
    mutation-verified cases below."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.handle_connect)\n'
        '    def handle_connect(self, player, cb=make(lambda a, b: a)):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_parameter_literally_named_lambda_fn_is_not_treated_as_the_keyword():
    """`lambda` has to match as a whole word. Without a word-boundary check,
    a parameter merely *named* something lambda-ish would open a bogus lambda
    scope that never finds its terminating `:`, silently swallowing every
    comma after it and merging the rest of the signature into one
    parameter."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.handle_connect)\n'
        '    def handle_connect(self, lambda_fn, is_bot):\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_a_string_default_containing_a_comma_does_not_split_an_unparseable_signature():
    """A comma inside a *string* default, unlike inside a bracketed literal,
    can't actually reach the split logic on a normal file: `code_only()`
    blanks the whole string token -- quotes and all -- before `_scan_params`
    ever sees it, so the naive split doesn't misbehave on it either (verified
    in the fix report; it was a vacuous case). The one path where a raw
    string's comma *is* live is the untokenizable fallback, where `masked`
    is the unmasked original text: a syntax error anywhere in the file (the
    trailing broken `def bad(:` below) forces every def in the file,
    including an otherwise-fine one, to be scanned unmasked. Mutation-
    verified: this genuinely flags under a naive `.split(',')` and doesn't
    under the string-aware split."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.handle_connect)\n'
        "    def handle_connect(self, player, sep=', x, '):\n"
        '        pass\n'
        'def bad(:\n'
        '    pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


def test_an_unterminated_signature_is_skipped_rather_than_guessed():
    """A `def` with no closing paren anywhere in the file is only reachable on
    an already-broken file. The old `[^)]*\\)` regex simply failed to match --
    a silent miss, the safe direction. The depth-walk that replaced it must
    fail the same way rather than returning whatever it accumulated running
    off the end of the text."""
    source = (
        'import minqlxtended\n'
        'class p(minqlxtended.Plugin):\n'
        '    def __init__(self):\n'
        '        self.add_hook("player_connect", self.handle_connect)\n'
        '    def handle_connect(self, player\n'
        '        pass\n'
    )
    assert scan_incompatibilities(source, MINQLXTENDED) == []


# --- BOM handling -----------------------------------------------------------

def test_a_bom_prefixed_minqlx_import_is_still_flagged():
    """A leading UTF-8 BOM (U+FEFF) is not `\\s`, so it defeats the
    `^\\s*import` anchor unless stripped first. Not hypothetical:
    ql-assets/data/minqlxtended-plugins/player_info.py ships with a BOM in
    this repo today."""
    reasons = scan_incompatibilities('\ufeffimport minqlx\n', MINQLXTENDED)
    assert reasons


def test_classify_still_hash_matches_a_bom_prefixed_file():
    """`classify()` must hash the text exactly as given, BOM included -- a
    baseline file's manifest sha256 is computed over its bytes as shipped, so
    stripping the BOM before hashing here would break the allow-list."""
    text = '\ufeffimport minqlx\n'
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    verdict, reasons = classify(text, MINQLXTENDED, baseline_sha256=digest)
    assert verdict == VERDICT_COMPATIBLE
    assert reasons == []


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


def test_play_sound_and_center_print_are_not_flagged():
    """Both exist on minqlxtended -- 10 of the 40 files in QLSM's own shipped
    minqlxtended baseline call them, and minqlxtended_stub.py implements both."""
    text = (
        "import minqlxtended\n"
        "class p(minqlxtended.Plugin):\n"
        "    def f(self):\n"
        "        self.play_sound('sound/x.ogg')\n"
        "        self.center_print('hi')\n"
    )
    assert scan_incompatibilities(text, 'minqlxtended') == []


def test_module_scope_all_caps_assignment_is_the_authors_own_symbol():
    """MOD_LIST is a name a real plugin author would plausibly pick."""
    text = (
        "import minqlxtended\n"
        "MOD_LIST = ['rocket', 'rail']\n"
        "class p(minqlxtended.Plugin):\n"
        "    def f(self):\n"
        "        return MOD_LIST\n"
    )
    assert scan_incompatibilities(text, 'minqlxtended') == []


def test_all_caps_constant_not_assigned_locally_is_still_flagged():
    """The narrowing must not disarm the pattern for genuine Quake constants."""
    text = (
        "import minqlxtended\n"
        "class p(minqlxtended.Plugin):\n"
        "    def f(self, d):\n"
        "        return d['mod'] == MOD_ROCKET\n"
    )
    reasons = scan_incompatibilities(text, 'minqlxtended')
    assert any('MOD_*' in r for r in reasons)


def test_indented_assignment_does_not_suppress():
    """Only a module-scope assignment counts as the author defining the name."""
    text = (
        "import minqlxtended\n"
        "class p(minqlxtended.Plugin):\n"
        "    def f(self):\n"
        "        MOD_ROCKET = 1\n"
        "        return MOD_ROCKET\n"
    )
    assert scan_incompatibilities(text, 'minqlxtended') != []
