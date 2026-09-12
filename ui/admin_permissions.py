"""Pure helpers for the per-instance admin list.

Redis holds the live minqlx permission levels; `instance_admin` rows hold the
list QLSM manages and reapplies after a deploy. Everything here is offline:
payload validation, turning rows into sync entries, and stripping QLSM's
legacy numeric lines out of Quake Live's access.txt.
"""

import re

STEAMID64_RE = re.compile(r'^7656119\d{10}$')
# A line QLSM used to write: "<steamid>|<0-5>", optionally with a trailing
# comment. Quake Live's own roles (|admin, |mod, |ban) must survive.
NUMERIC_ADMIN_LINE_RE = re.compile(r'^\s*7656119\d{10}\s*\|\s*[0-5]\s*(#.*)?$')

MAX_LEVEL = 5


def validate_admin_entries(payload):
    """Validate the admin list a client sent.

    Returns (entries, None) on success -- a list of
    {'steam_id64': str, 'level': int}, de-duplicated with the last entry for a
    SteamID winning -- or (None, message). Invalid levels are rejected, never
    clamped.
    """
    if not isinstance(payload, list):
        return None, 'admins must be a list.'

    by_id = {}
    for item in payload:
        if not isinstance(item, dict):
            return None, 'Each admin must be an object with steam_id64 and level.'
        raw_id = item.get('steam_id64')
        if not isinstance(raw_id, str):
            return None, 'SteamID64 is required.'
        steam_id = raw_id.strip()
        if not STEAMID64_RE.match(steam_id):
            return None, 'SteamID64 must be a 17-digit Steam64 ID starting with 7656119.'
        raw_level = item.get('level')
        if isinstance(raw_level, bool) or raw_level is None:
            return None, f'Admin level for {steam_id} must be an integer between 0 and {MAX_LEVEL}.'
        try:
            level = int(raw_level)
        except (TypeError, ValueError):
            return None, f'Admin level for {steam_id} must be an integer between 0 and {MAX_LEVEL}.'
        if not 0 <= level <= MAX_LEVEL:
            return None, f'Admin level for {steam_id} must be between 0 and {MAX_LEVEL}.'
        by_id[steam_id] = level

    return [{'steam_id64': sid, 'level': lvl} for sid, lvl in by_id.items()], None


def strip_numeric_admin_lines(text):
    """Remove QLSM's legacy "steamid|<0-5>" lines, leaving comments, blanks and
    Quake Live's own admin/mod/ban lines untouched."""
    if not text:
        return text
    kept = [line for line in text.split('\n') if not NUMERIC_ADMIN_LINE_RE.match(line)]
    return '\n'.join(kept)


def entries_from_rows(rows):
    """{steam_id: level} for the permission sync."""
    return {row.steam_id64: int(row.level) for row in rows}
