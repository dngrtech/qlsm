"""Decide whether a plugin file can run on a given minqlx runtime.

Pure text analysis: no I/O, no filesystem, no database. The caller supplies the
file text and the sha256 the target runtime's baseline records for that
filename, and gets back a verdict.

The asymmetry is deliberate. This module can prove a file is **incompatible**
-- it names an API the target runtime removed -- but it can never prove a file
is compatible, because "I found nothing" is not evidence about code I do not
understand. Compatibility comes from the hash allow-list alone. Everything
else is `unknown`, and the compatibility gate strips anything that is not
`compatible`.
"""
import hashlib
import io
import re
import tokenize

from ui.runtime import MINQLX, MINQLXTENDED, normalize_runtime

VERDICT_COMPATIBLE = 'compatible'
VERDICT_INCOMPATIBLE = 'incompatible'
VERDICT_UNKNOWN = 'unknown'

# PEP 701 (Python 3.12) retokenized f-strings: what used to be one STRING
# token is now FSTRING_START / FSTRING_MIDDLE / FSTRING_END, with the
# embedded `{expr}` tokenized as ordinary code in between. Those three names
# don't exist on 3.10/3.11, so they're resolved defensively -- this module
# has to mask correctly on whichever interpreter runs it (worktree dev boxes
# are 3.10; CI and production are 3.12), or an f-string body silently stops
# being masked on the newer interpreter alone.
_MASK_TOKEN_TYPES = {tokenize.COMMENT, tokenize.STRING}
_MASK_TOKEN_TYPES.update(
    token_type for token_type in (
        getattr(tokenize, 'FSTRING_START', None),
        getattr(tokenize, 'FSTRING_MIDDLE', None),
        getattr(tokenize, 'FSTRING_END', None),
    )
    if token_type is not None
)


def code_only(text):
    """`text` with every comment and string blanked to spaces.

    Line and column positions survive, so a reason can still cite a real line
    number. Scanning the raw text instead would strip a file for mentioning
    `RET_STOP_ALL` in a docstring, which is exactly the sort of false positive
    that makes an operator stop trusting the gate.

    A file that does not tokenize is returned unchanged rather than treated as
    empty -- a syntactically broken file should still be scannable.
    """
    try:
        lines = text.splitlines(keepends=True)
        masked = [list(line) for line in lines]
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type not in _MASK_TOKEN_TYPES:
                continue
            (srow, scol), (erow, ecol) = token.start, token.end
            for row in range(srow, erow + 1):
                index = row - 1
                if index >= len(masked):
                    break
                start = scol if row == srow else 0
                end = ecol if row == erow else len(masked[index])
                for col in range(start, min(end, len(masked[index]))):
                    if masked[index][col] != '\n':
                        masked[index][col] = ' '
        return ''.join(''.join(row) for row in masked)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return text


# Each entry is (compiled pattern, reason). The pattern runs against the masked
# text, so a match is real code, not prose.
#
# `minqlx` is a prefix of `minqlxtended`, so every minqlx pattern ends at a word
# boundary: `minqlx\b` cannot match inside `minqlxtended` because `t` is a word
# character. Getting this wrong strips every correctly-ported file.
_REMOVED_ON_MINQLXTENDED = [
    (re.compile(r'^\s*import\s+minqlx\b(?!tended)', re.M), 'imports the minqlx module'),
    (re.compile(r'^\s*from\s+minqlx\b(?!tended)', re.M), 'imports from the minqlx module'),
    (re.compile(r'\bminqlx\.(?!\w*tended)'), 'references the minqlx module'),
    (re.compile(r'\bRET_[A-Z_]+\b'), 'uses a RET_* constant (minqlxtended uses Return.*)'),
    (re.compile(r'\bPRI_[A-Z_]+\b'), 'uses a PRI_* constant (minqlxtended uses Priority.*)'),
    (re.compile(r'\bWP_[A-Z_]+\b'), 'uses a WP_* constant (minqlxtended uses Weapon.*)'),
    (re.compile(r'\bMOD_[A-Z_]+\b'), 'uses a MOD_* means-of-death constant'),
    (re.compile(r'\bET_[A-Z_]+\b'), 'uses an ET_* entity-type constant'),
    (re.compile(r'\bSS_[A-Z_]+\b'), 'uses an SS_* constant'),
    (re.compile(r'\bCVAR_[A-Z_]+\b'), 'uses a CVAR_* flag constant'),
    (re.compile(r'\bSVF_[A-Z_]+\b'), 'uses an SVF_* constant'),
    (re.compile(r'\bTR_[A-Z_]+\b'), 'uses a TR_* constant'),
    (re.compile(r'\bSAY_[A-Z_]+\b'), 'uses a SAY_* constant'),
    (re.compile(r'\bTEAMS\['), 'indexes the TEAMS table'),
    (re.compile(r'\bGAMETYPES\['), 'indexes the GAMETYPES table'),
    (re.compile(r'\bWEAPONS\['), 'indexes the WEAPONS table'),
    (re.compile(r'\bITEMS\['), 'indexes the ITEMS table'),
    (re.compile(r'\.set_health\s*\('), 'calls set_health() (a property on minqlxtended)'),
    (re.compile(r'\.set_armor\s*\('), 'calls set_armor() (a property on minqlxtended)'),
    (re.compile(r'\.set_score\s*\('), 'calls set_score() (a property on minqlxtended)'),
    (re.compile(r'\.god\s*\('), 'calls god() (a property on minqlxtended)'),
    (re.compile(r'\.noclip\s*\('), 'calls noclip() (a property on minqlxtended)'),
    (re.compile(r'\bself\.lock\s*\('), 'calls Plugin.lock(), removed on minqlxtended'),
    (re.compile(r'\bself\.tempban\s*\('), 'calls Plugin.tempban(), removed on minqlxtended'),
    (re.compile(r'\bself\.slap\s*\('), 'calls Plugin.slap(), removed on minqlxtended'),
    (re.compile(r'\bself\.console\s*\('), 'calls Plugin.console(), removed on minqlxtended'),
]

_REMOVED_ON_MINQLX = [
    (re.compile(r'^\s*import\s+minqlxtended\b', re.M), 'imports the minqlxtended module'),
    (re.compile(r'^\s*from\s+minqlxtended\b', re.M), 'imports from the minqlxtended module'),
    (re.compile(r'\bminqlxtended\.'), 'references the minqlxtended module'),
    (re.compile(r'\bReturn\.[A-Z_]+\b'), 'uses Return.* (minqlx uses RET_*)'),
    (re.compile(r'\bPriority\.[A-Z_]+\b'), 'uses Priority.* (minqlx uses PRI_*)'),
    (re.compile(r'\bWeapon\.[A-Z_]+\b'), 'uses Weapon.* (minqlx uses WP_*)'),
]

_PATTERNS_BY_TARGET = {
    MINQLXTENDED: _REMOVED_ON_MINQLXTENDED,
    MINQLX: _REMOVED_ON_MINQLX,
}

# The events whose dispatch signature changed between the runtimes. Arity
# checking can only catch the subset where the argument *count* changed --
# `game_end` (1/1), `kill` (3/3) and `death` (3/3) keep the same count but
# change argument *meaning* instead (`game_end`'s argument goes from a stats
# dict to a bool; `kill`/`death`'s third argument goes from a stats dict to a
# means-of-death value). They stay in the table anyway, both so a `*args`
# handler on one of them is genuinely exercised by the "absorbs anything"
# bypass below rather than skipped for being absent from the table, and so a
# handler with the wrong *count* on them still gets caught. Every other event
# has the same arity on both runtimes and is deliberately left out -- adding
# it here could only produce false positives. Values are the argument count
# excluding `self`.
_EVENT_ARITY = {
    MINQLX: {
        'player_connect': 1, 'game_start': 1, 'game_end': 1,
        'round_end': 1, 'team_switch_attempt': 3, 'kill': 3, 'death': 3,
    },
    MINQLXTENDED: {
        'player_connect': 2, 'game_start': 0, 'game_end': 1,
        'round_end': 3, 'team_switch_attempt': 4, 'kill': 3, 'death': 3,
    },
}

# An ALL-CAPS name the file itself binds at module scope is the author's own
# symbol, not a Quake constant the target runtime removed. Only column 0
# counts: an assignment inside a function or class body is a local, and a
# local named MOD_ROCKET does not make a reference to MOD_ROCKET elsewhere
# in the file safe.
_MODULE_SCOPE_ASSIGN = re.compile(
    r'^(?P<name>[A-Z][A-Z0-9_]*)\s*(?::[^=\n]+)?=(?!=)', re.M)

# Only the prefix patterns can collide with an author's identifiers. Anchored
# patterns (imports, `minqlx.`, `TEAMS[`, method calls) cannot, so suppression
# must never apply to them.
_SUPPRESSIBLE_PREFIXES = ('RET_', 'PRI_', 'WP_', 'MOD_', 'ET_', 'SS_',
                          'CVAR_', 'SVF_', 'TR_', 'SAY_')


def _locally_defined(masked):
    """ALL-CAPS names the file binds at module scope (column 0)."""
    return {m.group('name') for m in _MODULE_SCOPE_ASSIGN.finditer(masked)}


_ADD_HOOK = re.compile(
    r'\badd_hook\s*\(\s*["\'](?P<event>\w+)["\']\s*,\s*self\.(?P<handler>\w+)')
# Matches only up to the opening `(` of the signature -- the parameter list
# itself is captured by walking forward from there (see `_scan_params`),
# because a plain `[^)]*` class stops at the first `)`, which a call-valued
# default like `is_bot=default_factory()` closes before the signature does.
_DEF = re.compile(r'^\s*def\s+(?P<name>\w+)\s*\(', re.M)


def _line_of(text, index):
    return text.count('\n', 0, index) + 1


def _is_ident_char(char):
    return char.isalnum() or char == '_'


def _scan_params(text, start):
    """Top-level parameter strings between a `def`'s opening `(` (at `start`)
    and its matching close paren, or `None` if the signature never closes.

    Tracks nesting depth across `()`, `[]` and `{}`, and skips over string
    literals, so a comma belonging to a default value -- `is_bot=[1, 2, 3]`,
    `sep=", "` -- is never mistaken for a parameter separator; only a comma
    at depth 1 (directly inside the signature's own parens), with no lambda
    header open (see below), splits.

    A `lambda` default -- `cb=lambda a, b: a` -- opens no bracket, so its own
    parameter commas sit at the very same depth as the signature's. On seeing
    the whole word `lambda` (never `lambda_fn`) at depth *d*, that depth is
    pushed onto `lambda_depths`; comma-splitting is suppressed for as long as
    `lambda_depths` is non-empty. The header closes on the first `:` seen
    back at that same depth *d* -- not on a `:` inside a nested bracket
    (`lambda a: {1: 2}`, whose colon is one depth deeper), and not on an
    annotation colon elsewhere in the signature (nothing pops the stack
    unless it's open, and a lambda header can't itself contain one -- lambda
    parameters can't be annotated). Depth-matching the closer to the opener
    this way also makes nested lambdas resolve innermost-first for free.

    Running off the end of `text` without returning to depth 0 means the
    signature is unterminated -- only reachable on an already-broken file.
    Returning `None` there instead of the partial text the walk accumulated
    keeps that the same silent miss the old `[^)]*\\)` regex produced, rather
    than guessing at a parameter list that was never actually written.
    """
    depth = 1
    index = start
    param_start = start
    params = []
    quote = None
    lambda_depths = []
    length = len(text)
    while index < length:
        char = text[index]
        if quote:
            if char == '\\':
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if (char == 'l' and text[index:index + 6] == 'lambda'
                and (index == 0 or not _is_ident_char(text[index - 1]))
                and (index + 6 >= length or not _is_ident_char(text[index + 6]))):
            lambda_depths.append(depth)
            index += 6
            continue
        if char in '"\'':
            quote = char
        elif char == ':' and lambda_depths and lambda_depths[-1] == depth:
            lambda_depths.pop()
        elif char in '([{':
            depth += 1
        elif char in ')]}':
            depth -= 1
            if depth == 0:
                params.append(text[param_start:index])
                return params
        elif char == ',' and depth == 1 and not lambda_depths:
            params.append(text[param_start:index])
            param_start = index + 1
        index += 1
    return None


def _handler_params(masked):
    """Map handler name -> its parameter list, `self` dropped."""
    found = {}
    for match in _DEF.finditer(masked):
        raw_params = _scan_params(masked, match.end())
        if raw_params is None:
            continue  # unterminated signature -- unparseable, skip it
        params = [p.strip() for p in raw_params if p.strip()]
        if params and params[0] == 'self':
            params = params[1:]
        found[match.group('name')] = (params, _line_of(masked, match.start()))
    return found


def _scan_arities(text, masked, target_runtime):
    """Flag a handler registered for an event whose arity differs on the target.

    minqlxtended validates the signature at `add_hook()` rather than at dispatch,
    so one stale handler stops the whole plugin from loading at server start --
    which makes this worth catching before the file ever reaches a host.

    `_ADD_HOOK` runs against the raw `text`, not `masked`: `code_only()` blanks
    every string literal, including the quoted event name `add_hook()` needs to
    identify which event a handler is registered for. A match is then required
    to land outside every masked span -- otherwise a commented-out or
    docstring-embedded `add_hook()` call would register a handler that was
    never actually wired up. `_handler_params` still reads `masked`, since a
    string-valued default argument could otherwise hide a comma from the
    parameter-count logic.
    """
    arities = _EVENT_ARITY[target_runtime]
    handlers = _handler_params(masked)
    reasons = []
    for match in _ADD_HOOK.finditer(text):
        if not masked[match.start():match.end()].strip():
            continue  # inside a comment or string -- code_only() blanked it
        event = match.group('event')
        if event not in arities:
            continue
        entry = handlers.get(match.group('handler'))
        if entry is None:
            continue
        params, line = entry
        if any(p.startswith('*') for p in params):
            continue  # *args / **kwargs absorb anything
        required = [p for p in params if '=' not in p]
        expected = arities[event]
        if len(required) > expected or len(params) < expected:
            reasons.append(
                f'line {line}: {match.group("handler")}() takes {len(params)} '
                f'argument(s) but {event} dispatches {expected} on {target_runtime}')
    return reasons


def scan_incompatibilities(text, target_runtime):
    """Reasons `text` cannot run on `target_runtime`, each prefixed `line N: `.

    An empty list means the scan found nothing, which is not the same as
    "compatible" -- see the module docstring.
    """
    if not isinstance(text, str) or not text:
        return []
    # A leading UTF-8 BOM (U+FEFF) is not `\s`, so it defeats every `^\s*`
    # anchor below and a BOM'd `import minqlx` lands `unknown` instead of
    # `incompatible`. This is local to scanning, not `classify()`'s hash --
    # a baseline file's manifest sha256 is computed over its bytes as shipped,
    # BOM included, so stripping it before hashing would break the allow-list.
    if text.startswith('\ufeff'):
        text = text[1:]
    target = normalize_runtime(target_runtime)
    masked = code_only(text)
    reasons = []
    local_names = _locally_defined(masked)
    for pattern, description in _PATTERNS_BY_TARGET[target]:
        for match in pattern.finditer(masked):
            token = match.group(0)
            if (token.startswith(_SUPPRESSIBLE_PREFIXES)
                    and token in local_names):
                continue  # the author's own module-scope symbol
            reasons.append(
                f'line {_line_of(masked, match.start())}: {description}')
            break
    reasons.extend(_scan_arities(text, masked, target))
    return reasons


def baseline_digest(text):
    """The one hashing rule the manifest and the gate must agree on.

    Line endings are normalised to LF first. The generator reads files as
    bytes and the gate reads them as text (which already converts CRLF to LF),
    so hashing the raw bytes on one side and the decoded text on the other
    silently disagrees for every CRLF file -- 9 of the 63 files in the minqlx
    baseline. Normalising on both sides is what makes the allow-list work at
    all; changing it on one side only moves the mismatch.
    """
    if not isinstance(text, str):
        text = text.decode('utf-8')
    normalised = text.replace('\r\n', '\n').replace('\r', '\n')
    return hashlib.sha256(normalised.encode('utf-8')).hexdigest()


def classify(text, target_runtime, baseline_sha256=None):
    """Verdict for one file against `target_runtime`.

    `baseline_sha256` is what the target runtime's manifest records for this
    filename, or None when the baseline has no file by that name.
    """
    if baseline_sha256 and isinstance(text, str):
        if baseline_digest(text) == baseline_sha256:
            return VERDICT_COMPATIBLE, []
    reasons = scan_incompatibilities(text, target_runtime)
    if reasons:
        return VERDICT_INCOMPATIBLE, reasons
    return VERDICT_UNKNOWN, []
