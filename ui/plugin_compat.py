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
            if token.type not in (tokenize.COMMENT, tokenize.STRING):
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
    (re.compile(r'\bself\.play_sound\s*\('), 'calls Plugin.play_sound(), removed on minqlxtended'),
    (re.compile(r'\bself\.center_print\s*\('), 'calls Plugin.center_print(), removed on minqlxtended'),
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

# Only the six events whose dispatch signature differs between the runtimes.
# Everything else has the same arity on both, and listing it here could only
# produce false positives. Values are the argument count excluding `self`.
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

_ADD_HOOK = re.compile(
    r'\badd_hook\s*\(\s*["\'](?P<event>\w+)["\']\s*,\s*self\.(?P<handler>\w+)')
_DEF = re.compile(r'^\s*def\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)', re.M)


def _line_of(text, index):
    return text.count('\n', 0, index) + 1


def _handler_params(masked):
    """Map handler name -> its parameter list, `self` dropped."""
    found = {}
    for match in _DEF.finditer(masked):
        params = [p.strip() for p in match.group('params').split(',') if p.strip()]
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
    identify which event a handler is registered for. `_handler_params` still
    reads `masked`, since a string-valued default argument could otherwise hide
    a comma from the parameter-count logic.
    """
    arities = _EVENT_ARITY[target_runtime]
    handlers = _handler_params(masked)
    reasons = []
    for match in _ADD_HOOK.finditer(text):
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
    target = normalize_runtime(target_runtime)
    masked = code_only(text)
    reasons = []
    for pattern, description in _PATTERNS_BY_TARGET[target]:
        match = pattern.search(masked)
        if match:
            reasons.append(f'line {_line_of(masked, match.start())}: {description}')
    reasons.extend(_scan_arities(text, masked, target))
    return reasons


def classify(text, target_runtime, baseline_sha256=None):
    """Verdict for one file against `target_runtime`.

    `baseline_sha256` is what the target runtime's manifest records for this
    filename, or None when the baseline has no file by that name.
    """
    if baseline_sha256 and isinstance(text, str):
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if digest == baseline_sha256:
            return VERDICT_COMPATIBLE, []
    reasons = scan_incompatibilities(text, target_runtime)
    if reasons:
        return VERDICT_INCOMPATIBLE, reasons
    return VERDICT_UNKNOWN, []
