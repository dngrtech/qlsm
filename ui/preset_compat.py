"""Filter a preset response for a host running a different minqlx runtime.

This is the I/O half of the compatibility gate: `ui.plugin_compat` decides,
this module fetches what it needs to decide with and rewrites the response.

Runtimes that match are the overwhelmingly common case and must cost nothing --
`apply_compatibility` returns the very same object it was given, so a matched
load is byte-identical to what QLSM returned before this gate existed.
"""
import json
import os

from ui.plugin_compat import VERDICT_COMPATIBLE, baseline_digest, classify
from ui.preset_support import BUILTIN_PRESETS_DIR, default_preset_name_for_runtime
from ui.runtime import normalize_runtime, runtime_paths

# ql-assets/ is shipped, read-only repo content, so it is anchored to the repo
# rather than the working directory -- the same way ansible_instance_hooks.py:22
# anchors the system-hooks directory. This asymmetry with BUILTIN_PRESETS_DIR
# below is deliberate, not an oversight: if a wrong CWD silently emptied the
# hash allow-list, every plugin would fall through to the scanner, land
# `unknown`, and be stripped on every cross-runtime load. That failure is
# silent and total, so this lookup must not depend on where QLSM was launched.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ASSETS_DIR = os.path.join(REPO_ROOT, 'ql-assets', 'data')

# BUILTIN_PRESETS_DIR, by contrast, is imported from preset_support and stays
# working-directory-relative, because that is how every other preset lookup in
# QLSM resolves and a self-hosted deployment keeps its presets beside its
# configs. Degrading to "no replacements offered" is safe; degrading to "no
# allow-list" is not.


def _manifest_path(runtime):
    directory = runtime_paths(runtime)['asset_plugins_dir']
    return os.path.join(ASSETS_DIR, directory, 'manifest.json')


def baseline_hashes(runtime):
    """filename -> sha256 for the runtime's vendored plugin baseline.

    A missing or malformed manifest yields {}, which costs compatibility
    (everything falls through to the scanner) but never raises: a preset load
    must not 500 because an asset file is absent.
    """
    try:
        with open(_manifest_path(runtime), 'r', encoding='utf-8') as handle:
            manifest = json.load(handle)
    except (OSError, ValueError):
        return {}
    files = manifest.get('files')
    if not isinstance(files, dict):
        return {}
    return {
        name: entry.get('sha256')
        for name, entry in files.items()
        if isinstance(entry, dict) and entry.get('sha256')
    }


def replacement_scripts(runtime):
    """filename -> text for every plugin a fresh instance on `runtime` can pick.

    Read from the runtime's default builtin preset `scripts/` rather than the
    baseline directory: the baseline also holds files that are always deployed
    and never offered (serverchecker.py), and it lacks preset-only files such as
    highfps.py. The default preset is precisely the pickable set.
    """
    preset = default_preset_name_for_runtime(runtime)
    directory = os.path.join(BUILTIN_PRESETS_DIR, preset, 'scripts')
    scripts = {}
    try:
        names = os.listdir(directory)
    except OSError:
        return scripts
    for name in names:
        if not name.endswith('.py'):
            continue
        try:
            with open(os.path.join(directory, name), 'r', encoding='utf-8') as handle:
                scripts[name] = handle.read()
        except (OSError, ValueError):
            # ValueError catches UnicodeDecodeError: one plugin saved in the
            # wrong encoding must not take down every other file's read, or a
            # single bad script anywhere in the preset directory would fail
            # every cross-runtime preset load, not just its own.
            continue
    return scripts


def shipped_scripts(runtime):
    """relpath -> text for EVERY .py the runtime's default builtin preset ships,
    subdirectories included.

    `replacement_scripts()` above is deliberately flat, because only a root-level file
    can be offered as a replacement. This one is not: the draft filter restores a
    subdirectory file the source overlay wrote over, and the report has to describe
    that, so both need to see `discord_extensions/admin.py`.

    draft_routes._target_default_preset_files() delegates here so the report and the
    filter cannot disagree about which files the target ships -- they disagreeing is
    the whole failure class this gate exists to eliminate.
    """
    preset = default_preset_name_for_runtime(runtime)
    directory = os.path.join(BUILTIN_PRESETS_DIR, preset, 'scripts')
    scripts = {}
    for root, _dirs, filenames in os.walk(directory):
        for name in filenames:
            if not name.endswith('.py'):
                continue
            full_path = os.path.join(root, name)
            try:
                with open(full_path, 'r', encoding='utf-8') as handle:
                    scripts[os.path.relpath(full_path, directory)] = handle.read()
            except (OSError, ValueError):
                continue
    return scripts


def _strip_entry(path, verdict, reasons, replacements, shipped=None):
    """One row of the operator-facing report.

    `replacement` is a filename in `replacements`, or None when the target
    runtime has no counterpart -- an offer is never invented, because upstream
    balance.py is not QLSM's and mybalance.py has no equivalent at all.

    Only a root-level file can be offered a replacement. A preset's scripts/
    may contain subdirectories (the minqlx default ships discord_extensions/
    and extras/), but those hold helper modules imported by a root plugin, not
    plugins in their own right -- isEnableablePluginPath() in the frontend
    rejects any path containing a separator, so they can never appear in
    checked_plugins either. Offering the target's root-level `balance.py` in
    place of a stripped `extras/balance.py` would silently relocate the file
    into the plugin root, which is a different thing from what was there.
    Subdirectory files are still stripped and still reported; they are just
    never handed a replacement.
    """
    if '/' in path or os.sep in path:
        # A subdirectory file cannot be OFFERED a replacement, but since the draft
        # filter restores one the target ships at this same path, saying only
        # "stripped, nothing available" would describe a loss that does not happen.
        # `auto_replaced` is how the dialog tells those two outcomes apart.
        return {'path': path, 'verdict': verdict, 'reasons': reasons,
                'replacement': None,
                'auto_replaced': path in (shipped or {})}
    return {
        'path': path,
        'verdict': verdict,
        'reasons': reasons,
        'replacement': path if path in replacements else None,
        # Root-level files are never auto-restored; the operator ticks them or they go.
        'auto_replaced': False,
    }


def source_catalog_digests(runtime):
    """relpath -> sha256 for every .py the SOURCE runtime's default preset ships.

    This is the allow-list for "the operator never touched this file". A preset's
    `scripts` map is not just the preset's own files: _read_preset_scripts() lays
    the whole default builtin catalog of the preset's runtime down first and
    overlays the preset's files on top, so a plain minqlx preset arrives carrying
    all 48 stock minqlx plugins verbatim. Every one of those is stripped against
    minqlxtended, and reporting them made the dialog a 48-row wall of files the
    operator never chose, edited, or even knew were in the preset.

    Compared by CONTENT, not by name, for the same reason _apply_runtime_filter
    compares the target's shipped files by content: a preset that overwrote
    `motd.py` with something of its own must not be waved through as pristine
    just because a file by that name exists in the catalog.
    """
    return {rel: baseline_digest(text)
            for rel, text in shipped_scripts(runtime).items()}


def _report_kind(entry):
    """Which of the three things the dialog has to say about a reported strip.

    `replaceable` -- a same-named file exists on the target and the operator
    chooses whether to take it; taking it discards whatever this preset held at
    that path. `helper` -- a subdirectory module the target ships at the same
    path, restored with no choice offered (see _strip_entry). `unavailable` --
    the target has nothing by this name, so the file goes and any tick with it.
    """
    if entry['replacement']:
        return 'replaceable'
    if entry['auto_replaced']:
        return 'helper'
    return 'unavailable'


def apply_compatibility(response_data, preset_runtime, target_runtime):
    """Strip what cannot run on `target_runtime` and report what needs a decision.

    Returns `response_data` itself -- not a copy -- when there is nothing to do,
    so a same-runtime load is provably unchanged.

    Only ACTIONABLE strips are reported. A stock plugin the operator never edited
    is swapped for the target runtime's own copy of the same file with no prompt
    (`auto_accepted`), because there is nothing to decide: the operator did not
    write that file, so nothing of theirs is lost. What reaches the dialog is the
    two cases where something genuinely is at stake -- a file the operator's
    preset customised (accepting the swap discards those edits) and a file the
    target runtime has no counterpart for at all (it goes away).

    Enablement is NOT decided here or in the dialog. A plugin comes back checked
    if and only if the preset had it checked and its file survives; accepting a
    replacement carries the file over at the selection state the preset recorded.
    """
    if target_runtime is None:
        return response_data
    preset = normalize_runtime(preset_runtime)
    target = normalize_runtime(target_runtime)
    if preset == target:
        return response_data

    hashes = baseline_hashes(target)
    candidates = replacement_scripts(target)
    shipped = shipped_scripts(target)
    # Empty when the source runtime's builtin preset is missing: every file then
    # reads as customised and lands in the dialog, which is the old behaviour --
    # noisy, but never silently drops something the operator wrote.
    source_catalog = source_catalog_digests(preset)
    scripts = response_data.get('scripts') or {}

    checked_plugins = response_data.get('checked_plugins')
    # A preset with no checked_plugins.json at all (pre-dates this feature) is
    # None here, same as a hand-edited file holding a bare string or int (read
    # by _read_preset_checked_plugins() with no type guard). Neither means
    # "the operator explicitly selected nothing" -- both must fall through to
    # the frontend's own "preset pre-dates this feature -- keep current
    # defaults" branch (`presetData.checked_plugins != null`), which an empty
    # list would defeat by looking like a genuine, deliberate empty selection.
    had_selection = isinstance(checked_plugins, list)
    if not had_selection:
        checked_plugins = []
    checked_set = set(checked_plugins)

    kept = {}
    stripped = []
    offered = {}
    auto_accepted = []
    for path, content in scripts.items():
        # Only Python is classified. .so hooks LD_PRELOAD into qzeroded and know
        # nothing about either runtime; .txt and fonts are data.
        if not path.lower().endswith('.py'):
            kept[path] = content
            continue
        verdict, reasons = classify(
            content, target, baseline_sha256=hashes.get(os.path.basename(path)))
        if verdict == VERDICT_COMPATIBLE:
            kept[path] = content
            continue
        entry = _strip_entry(path, verdict, reasons, candidates, shipped)
        entry['originally_checked'] = path in checked_set
        # `from_catalog` separates "you edited a stock plugin" from "this is a
        # file of your own" -- the same strip, but the operator needs to be told
        # about them in different words.
        entry['from_catalog'] = path in source_catalog
        pristine = (isinstance(content, str)
                    and source_catalog.get(path) == baseline_digest(content))
        if entry['replacement']:
            offered[entry['replacement']] = candidates[entry['replacement']]

        if pristine and entry['replacement']:
            # Untouched stock plugin, and the target ships its own version of the
            # same file: swap it in and say nothing. Accepting is not the same as
            # enabling -- `checked` below is untouched either way, so this cannot
            # turn the target's default catalog on behind the operator's back.
            auto_accepted.append(entry['replacement'])
            kept[path] = candidates[entry['replacement']]
            continue
        if pristine and entry['auto_replaced']:
            # Same, for a helper module under a subdirectory. The draft filter
            # restores these itself (see _apply_runtime_filter); no offer is
            # made because a subdirectory file can never be a checkable plugin.
            kept[path] = shipped[path]
            continue
        if pristine and not entry['originally_checked']:
            # A stock plugin with no counterpart on the target, that the preset
            # did not have enabled. It came from the catalog seed rather than
            # from anything the operator did, so its loss is not news.
            continue
        # What is left genuinely needs the operator: their own edits are about to
        # be discarded, or a plugin they had enabled is about to disappear.
        entry['kind'] = _report_kind(entry)
        stripped.append(entry)

    stripped_paths = {entry['path'] for entry in stripped}
    # Only a REPORTED strip can cost a plugin its tick. An auto-swapped one keeps
    # exactly the selection state the preset recorded, which is the whole point:
    # loading a minqlx preset onto minqlxtended must reproduce that preset's
    # plugin selection, not the target runtime's default one.
    checked = [path for path in checked_plugins if path not in stripped_paths]

    result = dict(response_data)
    # NO CONSUMER. Nothing in the frontend reads the filtered scripts map:
    # applyPresetData() (AddInstanceForm.jsx, EditInstanceConfigModal.jsx)
    # never touches presetData.scripts -- the plugin files an instance gets
    # come from the draft workspace, which _apply_runtime_filter() filters
    # separately and independently. mergeReplacements() writes into this map,
    # but nothing reads what it produces either. Enforcing the gate here and
    # nowhere else is precisely what got the first P5 implementation rejected.
    # Kept because it is part of the GET /presets/<id> response contract and
    # removing it is a separate change; do not mistake it for the gate.
    result['scripts'] = kept
    # None (not []) when the preset never recorded a selection at all, so the
    # frontend's `checked_plugins != null` legacy branch still fires instead
    # of reading this as "the operator deliberately picked nothing."
    result['checked_plugins'] = checked if had_selection else None
    result['compatibility'] = {
        'preset_runtime': preset,
        'target_runtime': target,
        'stripped': sorted(stripped, key=lambda entry: entry['path']),
        'replacements': offered,
        # Replacements applied without asking. The frontend must pass these to
        # the draft alongside whatever the operator ticked, on BOTH paths --
        # including the one where `stripped` is empty and no dialog opens at
        # all -- or _apply_runtime_filter deletes the source file and writes
        # nothing back, and the plugin list comes up missing the target
        # runtime's own standard plugins.
        'auto_accepted': sorted(set(auto_accepted)),
    }
    return result
