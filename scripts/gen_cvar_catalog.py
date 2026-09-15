#!/usr/bin/env python3
"""Build ui/data/ql_cvar_catalog.json - the cvar/command catalog the config
editor's autocomplete is built from.

Why this exists: the editor used to carry a hand-typed list of ~50 cvars with
no record of where they came from. Everything here is assembled from inputs
that are checked in next to this script, and every entry keeps the tag of the
source it came from, so a reader (and the tooltip in the editor) can tell a
verified description apart from one that was read off the cvar name.

Inputs (all in scripts/cvar-catalog/, no game files or network needed):

  qlds-listcvars.txt        Names of every cvar a live QLDS registers, from a
                            `listcvars` dump. This is what decides whether a
                            cvar exists at all, and its canonical spelling.
  curated-descriptions.json Hand-written descriptions, each with a source tag.
  factory-cvars.json        Which cvars the game's own factories set and to
                            what value - marks a cvar as factory/gameplay
                            settable and supplies real example values.

  ...plus the annotated server.cfg of the default preset, which is the example
  config shipped by the game and carries id's own comments for ~50 cvars.

qlx_* cvars are deliberately NOT in this catalog. They belong to whatever
minqlx plugins a given server runs, and the UI reads them from that server's
plugin manifests instead (ui/plugin_manifest.py).

Usage:
    python scripts/gen_cvar_catalog.py                 # regenerate the catalog
    python scripts/gen_cvar_catalog.py --check         # fail if it is stale
    python scripts/gen_cvar_catalog.py --factories <pak00>/scripts/factories.txt \
        --write-factory-index                        # refresh factory-cvars.json
"""

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, 'scripts', 'cvar-catalog')
LISTCVARS_FILE = os.path.join(DATA_DIR, 'qlds-listcvars.txt')
CURATED_FILE = os.path.join(DATA_DIR, 'curated-descriptions.json')
FACTORY_INDEX_FILE = os.path.join(DATA_DIR, 'factory-cvars.json')
SERVER_CFG_FILE = os.path.join(REPO_ROOT, 'configs', 'presets', '_builtin', 'default', 'server.cfg')
OUTPUT_FILE = os.path.join(REPO_ROOT, 'ui', 'data', 'ql_cvar_catalog.json')

CATALOG_VERSION = 1

# Where a description came from. Shown in the editor next to the text.
SOURCE_LABELS = {
    'server.cfg': "the game's own annotated example server.cfg",
    'ql-live': 'verified Quake Live reference notes',
    'factories': "the game's own factory definitions",
    'naming': 'read off the cvar name - not verified on a live server',
    'qlsm': 'behaviour of this app',
    'listcvars': 'a listcvars dump only - no description',
}

GROUPS = [
    ('server', 'Server'),
    ('gameplay', 'Gameplay'),
    ('weapons', 'Weapons'),
    ('physics', 'Player physics'),
    ('bots', 'Bots'),
    ('network', 'Network'),
    ('rcon', 'Rcon / stats sockets'),
    ('files', 'File system'),
    ('engine', 'Engine'),
]

# Weapon suffixes used by the g_damage_*, weapon_reload_* and friends families.
# Names from the item table in the ql-live reference; the set is confirmed by
# the engine's own g_bestStartingWeapons default,
# "gh bfg rl lg rg hmg cg sg pg mg ng gl g pl".
WEAPON_SUFFIXES = {
    'g': 'Gauntlet',
    'gauntlet': 'Gauntlet',
    'mg': 'Machine Gun',
    'hmg': 'Heavy Machine Gun',
    'sg': 'Shotgun',
    'gl': 'Grenade Launcher',
    'rl': 'Rocket Launcher',
    'lg': 'Lightning Gun',
    'rg': 'Railgun',
    'pg': 'Plasma Gun',
    'bfg': 'BFG10K',
    'ng': 'Nailgun',
    'pl': 'Prox Launcher',
    'prox': 'Prox Launcher',
    'cg': 'Chaingun',
    'gh': 'Grappling Hook',
    'hook': 'Grappling Hook',
}

# family prefix -> sentence template, filled with the weapon name
WEAPON_FAMILIES = [
    ('g_damage_', 'Direct damage a {w} hit deals.'),
    ('g_knockback_', 'Knockback a {w} hit imparts.'),
    ('g_splashdamage_', 'Splash damage of a {w} shot.'),
    ('g_splashradius_', 'Splash radius of a {w} shot, in units.'),
    ('g_velocity_', 'Projectile speed of the {w}.'),
    ('g_startingAmmo_', 'Ammo a player spawns with for the {w}.'),
    ('g_accelRate_', 'Acceleration rate of a {w} projectile.'),
    ('g_accelFactor_', 'Acceleration factor of a {w} projectile.'),
    ('weapon_reload_', 'Milliseconds between {w} shots.'),
    ('weapon_gravity_', 'Gravity applied to {w} projectiles.'),
]

# Console commands worth suggesting at the start of a line in a .cfg. Names and
# descriptions come from the builtin-command catalog in the ql-live reference
# (originally tjone270/Quake-Live documentation, cross-checked against runtime
# listcmds output).
COMMANDS = [
    ('set', 'Sets a cvar (no archive flag).'),
    ('seta', 'Sets a cvar with the archive flag.'),
    ('exec', 'Executes a configuration file.'),
    ('vstr', 'Executes commands stored in a cvar.'),
    ('alias', 'Creates a command alias.'),
    ('unalias', 'Removes a single alias.'),
    ('bind', 'Binds a key to a command or alias.'),
    ('unbind', 'Removes a single bind on a key.'),
    ('unbindall', 'Removes all set binds.'),
    ('toggle', "Inverts a cvar's boolean value."),
    ('reset', 'Resets a cvar to its initial value.'),
    ('clearcvar', 'Clears a cvar\'s value, setting it to "".'),
    ('cvar_restart', 'Restarts the cvar subsystem, clearing most cvar changes.'),
    ('writeconfig', 'Writes a config with all set cvars and binds.'),
    ('condump', 'Dumps all buffered console text to a file.'),
    ('echo', 'Prints text to the console.'),
    ('wait', 'Waits one frame (or N frames) before continuing.'),
    ('map', 'Loads a map normally.'),
    ('devmap', 'Loads a map in development/cheats mode.'),
    ('map_restart', 'Reloads the map and entities and respawns all players.'),
    ('startRandomMap', 'Runs a random map from the map pool file.'),
    ('reload_mappool', 'Reloads the map pool file from sv_mapPoolFile. The pool is otherwise only read at server init.'),
    ('kick', 'Kicks a player by name.'),
    ('clientkick', 'Kicks a player or bot by client ID.'),
    ('say', 'Sends a message from the server.'),
    ('status', 'Lists all clients with IDs, scores, ping, IP and Steam ID.'),
    ('serverinfo', 'Displays the serverinfo cvars clients and the browser see.'),
    ('listcvars', 'Lists all cvars, with optional filtering.'),
    ('listcmds', 'Lists all commands, with optional filtering.'),
    ('killserver', 'Unloads the current map; the process keeps running.'),
    ('quit', 'Exits the server process immediately.'),
]

# Bitmask cvars, with the bit tables the editor shows instead of a plain
# description. Each table says how it was established.
BITMASKS = {
    'g_startingWeapons': {
        'source': 'factories',
        'note': ("Bit values read out of the game's own factories: ca = 8447 (everything up to the "
                 "plasma gun, plus the heavy machine gun), ictf/iffa = 65 (gauntlet + railgun), "
                 "actf = 515 (gauntlet + machine gun + grappling hook), _rj = 17 (gauntlet + rocket "
                 "launcher), infected = 7 (gauntlet + machine gun + shotgun)."),
        'bits': [
            [1, 'Gauntlet'], [2, 'Machine Gun'], [4, 'Shotgun'], [8, 'Grenade Launcher'],
            [16, 'Rocket Launcher'], [32, 'Lightning Gun'], [64, 'Railgun'], [128, 'Plasma Gun'],
            [256, 'BFG10K'], [512, 'Grappling Hook'], [1024, 'Nailgun'], [2048, 'Prox Launcher'],
            [4096, 'Chaingun'], [8192, 'Heavy Machine Gun'],
        ],
    },
    'g_voteFlags': {
        'source': 'ql-live',
        'note': ('Set bit = that vote is DISABLED. Bits 1 (map) and 4 (nextmap) are coupled inside '
                 'the client: denying either hides the whole map section of the in-game vote menu, '
                 'so a working tournament value is 13816, not 13820.'),
        'bits': [
            [1, 'map'], [2, 'map_restart'], [4, 'nextmap'], [8, 'gametype'], [16, 'kick'],
            [32, 'timelimit'], [64, 'fraglimit'], [128, 'shuffle'], [256, 'teamsize'],
            [512, 'cointoss / random'], [1024, 'loadouts'], [2048, 'end-game voting'],
            [4096, 'ammo (global)'], [8192, 'timers (item)'],
        ],
    },
}


def group_for(name):
    lowered = name.lower()
    if lowered.startswith('zmq_'):
        return 'rcon'
    if lowered.startswith('net_'):
        return 'network'
    if lowered.startswith('fs_'):
        return 'files'
    if lowered.startswith('bot_'):
        return 'bots'
    if lowered.startswith('pmove_'):
        return 'physics'
    if lowered.startswith('weapon_'):
        return 'weapons'
    if lowered.startswith('sv_'):
        return 'server'
    if lowered.startswith('com_') or lowered.startswith('cm_') or lowered.startswith('cl_') \
            or lowered.startswith('r_') or lowered.startswith('in_') or lowered.startswith('ui_'):
        return 'engine'
    if lowered.startswith('g_'):
        for family, _ in WEAPON_FAMILIES:
            if lowered.startswith(family.lower()):
                return 'weapons'
        return 'gameplay'
    if lowered in ('timelimit', 'fraglimit', 'capturelimit', 'roundlimit', 'roundtimelimit',
                   'scorelimit', 'mercylimit', 'teamsize', 'dmflags', 'practiceflags',
                   'armor_tiered', 'mapname', 'nextmap', 'nextmaps'):
        return 'gameplay'
    if lowered in ('serverstartup', 'dedicated', 'logfile', 'appendlogfile'):
        return 'server'
    return 'engine'


# Factories an operator is most likely to recognise, shown first in examples.
EXAMPLE_FACTORY_ORDER = ['ca', 'duel', 'ffa', 'tdm', 'ctf', 'ft', 'race']


def factory_examples(usage):
    ordered = sorted(usage.items(), key=lambda kv: (
        EXAMPLE_FACTORY_ORDER.index(kv[0]) if kv[0] in EXAMPLE_FACTORY_ORDER else len(EXAMPLE_FACTORY_ORDER),
        kv[0],
    ))
    return [f'{fid} = {value}' for fid, value in ordered[:3]]


def naming_description(name):
    """Description mechanically derived from a weapon-suffix family name."""
    lowered = name.lower()
    for family, template in WEAPON_FAMILIES:
        prefix = family.lower()
        if not lowered.startswith(prefix):
            continue
        suffix = lowered[len(prefix):]
        # g_knockback_rl_self, g_damage_lg_falloff, ...
        extra = None
        if '_' in suffix:
            suffix, extra = suffix.split('_', 1)
        weapon = WEAPON_SUFFIXES.get(suffix)
        if not weapon:
            return None
        text = template.format(w=weapon)
        if extra == 'self':
            text = text.replace(' imparts.', ' imparts on the player who fired it.')
            if not text.endswith('fired it.'):
                text += ' Applied to the player who fired it.'
        elif extra == 'falloff':
            text += ' This is the falloff variant.'
        elif extra == 'outer':
            text += ' This is the outer-radius variant.'
        elif extra:
            return None
        return text
    return None


def parse_server_cfg(path):
    """Descriptions from the annotated example server.cfg.

    Handles the three shapes that file uses:
        set x "v"      // description
                       // continued on the next line
        // set x "v"   // description        (commented-out example)
        // set x "v" - description           (the qlx_ block's dash form)
    """
    if not os.path.isfile(path):
        return {}
    out = {}
    last = None
    set_re = re.compile(r'^\s*(?://\s*)?set\s+(\S+)\s+"[^"]*"\s*(?://\s*(.*?)\s*|-\s*(.*?)\s*)?$')
    comment_re = re.compile(r'^(\s+)//\s*(.+?)\s*$')
    for raw in open(path, encoding='utf-8', errors='replace'):
        line = raw.rstrip('\n')
        match = set_re.match(line)
        if match:
            name = match.group(1)
            text = match.group(2) or match.group(3)
            if text:
                out[name.lower()] = {'name': name, 'text': text}
                last = name.lower()
            else:
                last = None
            continue
        # indented comment right under a set line continues its description
        cont = comment_re.match(line)
        if cont and last:
            out[last]['text'] += ' ' + cont.group(2)
            continue
        last = None
    return {k: v for k, v in out.items()}


def load_names(path):
    names = []
    for raw in open(path, encoding='utf-8'):
        line = raw.strip()
        if line and not line.startswith('#'):
            names.append(line)
    return names


def build_catalog():
    names = load_names(LISTCVARS_FILE)
    curated = json.load(open(CURATED_FILE, encoding='utf-8'))['entries']
    curated = {k.lower(): v for k, v in curated.items()}
    factory_index = json.load(open(FACTORY_INDEX_FILE, encoding='utf-8'))
    factory_cvars = {k.lower(): v for k, v in factory_index['cvars'].items()}
    from_cfg = parse_server_cfg(SERVER_CFG_FILE)

    cvars = []
    for name in names:
        key = name.lower()
        description, source = None, 'listcvars'
        if key in curated:
            description, source = curated[key][0], curated[key][1] or 'listcvars'
        elif key in from_cfg:
            description, source = from_cfg[key]['text'], 'server.cfg'
        else:
            derived = naming_description(name)
            if derived:
                description, source = derived, 'naming'
        entry = {
            'name': name,
            'group': group_for(name),
            'description': description,
            'source': source,
        }
        used_by = factory_cvars.get(key)
        if used_by:
            entry['factory'] = True
            # A couple of real values, so the operator sees the shape of the setting.
            entry['examples'] = factory_examples(used_by)
        if name in BITMASKS:
            entry['bitmask'] = BITMASKS[name]
        cvars.append(entry)

    # Cvars the example config documents but this QLDS build did not register
    # (commented-out examples for other builds). Keep them, flagged, rather
    # than dropping a documented setting on the floor.
    known = {n.lower() for n in names}
    for key, item in sorted(from_cfg.items()):
        if key in known or key.startswith('qlx_'):
            continue
        cvars.append({
            'name': item['name'],
            'group': group_for(item['name']),
            'description': item['text'],
            'source': 'server.cfg',
            'not_in_dump': True,
        })

    cvars.sort(key=lambda c: c['name'].lower())
    return {
        'version': CATALOG_VERSION,
        'generated_by': 'scripts/gen_cvar_catalog.py',
        'about': ('Server cvars and console commands offered by the config editor. Every entry '
                  'carries the source of its description; regenerate with scripts/gen_cvar_catalog.py.'),
        'sources': SOURCE_LABELS,
        'groups': [{'key': key, 'label': label} for key, label in GROUPS],
        'gametypes': factory_index.get('gametypes', []),
        'commands': [{'name': n, 'description': d, 'source': 'ql-live'} for n, d in COMMANDS],
        'cvars': cvars,
    }


def write_factory_index(factories_path):
    """Refresh factory-cvars.json from the game's own scripts/factories.txt."""
    data = json.load(open(factories_path, encoding='utf-8', errors='replace'))
    canonical, usage = {}, {}
    for factory in data:
        for cvar, value in (factory.get('cvars') or {}).items():
            key = cvar.lower()
            current = canonical.get(key)
            if current is None or sum(c.isupper() for c in cvar) > sum(c.isupper() for c in current):
                canonical[key] = cvar
            usage.setdefault(key, {})[factory['id']] = value
    index = json.load(open(FACTORY_INDEX_FILE, encoding='utf-8'))
    index['gametypes'] = sorted({f['basegt'] for f in data})
    index['factories'] = sorted(f['id'] for f in data)
    index['cvars'] = {canonical[k]: dict(sorted(v.items())) for k, v in sorted(usage.items())}
    dump(FACTORY_INDEX_FILE, index)
    print(f'factory-cvars.json: {len(index["cvars"])} cvars from {len(data)} factories')


def dump(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='exit non-zero if the catalog on disk is stale')
    parser.add_argument('--factories', help="path to the game's scripts/factories.txt")
    parser.add_argument('--write-factory-index', action='store_true', help='refresh factory-cvars.json from --factories')
    args = parser.parse_args()

    if args.write_factory_index:
        if not args.factories:
            parser.error('--write-factory-index needs --factories')
        write_factory_index(args.factories)

    catalog = build_catalog()
    if args.check:
        if not os.path.isfile(OUTPUT_FILE):
            print(f'{OUTPUT_FILE} is missing; run scripts/gen_cvar_catalog.py', file=sys.stderr)
            return 1
        current = json.load(open(OUTPUT_FILE, encoding='utf-8'))
        if current != catalog:
            print('ql_cvar_catalog.json is out of date; run scripts/gen_cvar_catalog.py', file=sys.stderr)
            return 1
        print('ql_cvar_catalog.json is up to date')
        return 0

    dump(OUTPUT_FILE, catalog)
    described = sum(1 for c in catalog['cvars'] if c['description'])
    print(f'{OUTPUT_FILE}: {len(catalog["cvars"])} cvars ({described} described), '
          f'{len(catalog["commands"])} commands')
    return 0


if __name__ == '__main__':
    sys.exit(main())
