"""The gate strips what cannot run and offers what can."""
import json
import os

import pytest

from ui.preset_compat import (
    apply_compatibility,
    baseline_hashes,
    replacement_scripts,
)
from ui.runtime import MINQLX, MINQLXTENDED


def test_baseline_hashes_reads_the_manifest():
    hashes = baseline_hashes(MINQLXTENDED)
    assert 'essentials.py' in hashes
    assert len(hashes['essentials.py']) == 64


def test_baseline_hashes_match_the_files_on_disk():
    """A manifest that disagrees with its own directory would silently strip
    every file it covers.

    Resolved through the module's own ASSETS_DIR rather than a literal relative
    path, so this test asserts what the production lookup actually reads and
    does not quietly depend on pytest's working directory.
    """
    import hashlib
    from ui.preset_compat import ASSETS_DIR
    directory = os.path.join(ASSETS_DIR, 'minqlxtended-plugins')
    hashes = baseline_hashes(MINQLXTENDED)
    assert hashes, 'manifest must not be empty, or the loop below checks nothing'
    compared = 0
    for name, digest in hashes.items():
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            continue
        with open(path, 'rb') as handle:
            assert hashlib.sha256(handle.read()).hexdigest() == digest, name
        compared += 1
    # A manifest that returned {} would make this loop a no-op that still
    # passes -- assert real comparisons actually happened.
    assert compared > 0


def test_baseline_hashes_survive_a_changed_working_directory(tmp_path, monkeypatch):
    """ql-assets/ is shipped, read-only repo content. If this lookup were
    working-directory-relative, a CWD change would empty the allow-list, every
    plugin would fall through to the scanner as `unknown`, and a cross-runtime
    load would silently strip all of them."""
    monkeypatch.chdir(tmp_path)
    assert 'essentials.py' in baseline_hashes(MINQLXTENDED)


def test_replacement_scripts_come_from_the_runtime_default_preset():
    scripts = replacement_scripts(MINQLXTENDED)
    assert 'myFun.py' in scripts
    assert 'import minqlxtended' in scripts['myFun.py']


def test_replacement_scripts_exclude_the_non_pickable_baseline_files():
    """serverchecker.py ships via the baseline directory and is not an option
    the operator picks, so it must never be offered as a replacement."""
    assert 'serverchecker.py' not in replacement_scripts(MINQLXTENDED)


def test_matching_runtimes_return_the_response_untouched():
    response = {'scripts': {'anything.py': 'import minqlx\n'}, 'checked_plugins': ['anything.py']}
    result = apply_compatibility(response, MINQLX, MINQLX)
    assert result is response
    assert 'compatibility' not in result


def test_a_none_target_runtime_returns_the_response_untouched():
    response = {'scripts': {'anything.py': 'import minqlx\n'}}
    assert apply_compatibility(response, MINQLX, None) is response


def test_an_incompatible_script_is_stripped_and_reported():
    response = {
        'scripts': {'mine.py': 'import minqlx\nx = minqlx.RET_STOP_ALL\n'},
        'checked_plugins': ['mine.py'],
    }
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert 'mine.py' not in result['scripts']
    assert result['checked_plugins'] == []
    stripped = result['compatibility']['stripped']
    assert [entry['path'] for entry in stripped] == ['mine.py']
    assert stripped[0]['verdict'] == 'incompatible'
    assert stripped[0]['reasons']


def test_a_baseline_file_survives_by_hash():
    scripts = replacement_scripts(MINQLXTENDED)
    response = {'scripts': {'essentials.py': scripts['essentials.py']}, 'checked_plugins': ['essentials.py']}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert 'essentials.py' in result['scripts']
    assert result['checked_plugins'] == ['essentials.py']
    assert result['compatibility']['stripped'] == []


def test_an_unknown_script_is_stripped_too():
    """Not provably broken is not the same as safe. The design strips anything
    that is not provably compatible."""
    response = {'scripts': {'custom.py': 'x = 1\n'}, 'checked_plugins': ['custom.py']}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert 'custom.py' not in result['scripts']
    assert result['compatibility']['stripped'][0]['verdict'] == 'unknown'


def test_a_same_named_target_plugin_is_offered_as_a_replacement():
    response = {'scripts': {'myFun.py': 'import minqlx\n'}, 'checked_plugins': ['myFun.py']}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['replacement'] == 'myFun.py'
    assert 'import minqlxtended' in result['compatibility']['replacements']['myFun.py']


def test_a_checked_plugin_is_reported_as_originally_checked():
    response = {'scripts': {'myFun.py': 'import minqlx\n'}, 'checked_plugins': ['myFun.py']}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['originally_checked'] is True


def test_an_unchecked_plugin_is_not_reported_as_originally_checked():
    """_read_preset_scripts() seeds the scripts dict from the entire default
    catalog before overlaying the preset's own files, so a file can appear
    here without ever having been part of the operator's actual selection.
    Reporting it is fine (the operator can see it and opt in); defaulting it
    to pre-accepted on the frontend is the bug this flag exists to prevent."""
    response = {'scripts': {'myFun.py': 'import minqlx\n'}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['originally_checked'] is False


def test_a_plugin_with_no_counterpart_is_offered_nothing():
    """A file the minqlxtended default preset does not ship gets no offer;
    inventing one would be a silent swap of non-equivalent behaviour.

    This used to use mybalance.py, which has since been ported and now IS
    offered. ServerStatus.py replaces it because it can never gain a
    counterpart: it is not a plugin at all, but an Oracle WebLogic admin
    script in Python 2 that reads sys.argv[1:6] at import."""
    response = {'scripts': {'ServerStatus.py': 'import minqlx\n'}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['replacement'] is None
    assert 'ServerStatus.py' not in result['compatibility']['replacements']


def test_a_subdirectory_helper_is_stripped_but_offered_no_replacement():
    """scripts/ may hold subdirectories of helper modules imported by a root
    plugin. They are not plugins, can never be in checked_plugins, and must not
    be silently relocated into the plugin root by a replacement offer."""
    response = {'scripts': {'extras/balance.py': 'import minqlx\n'}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['path'] == 'extras/balance.py'
    assert entry['replacement'] is None
    assert result['compatibility']['replacements'] == {}


def test_non_python_scripts_are_carried_through_unclassified():
    """The .so hooks detour qzeroded and know nothing about either runtime."""
    response = {'scripts': {'highfps_hook.so': 'YmFzZTY0', 'notes.txt': 'hello'}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['scripts']['highfps_hook.so'] == 'YmFzZTY0'
    assert result['scripts']['notes.txt'] == 'hello'
    assert result['compatibility']['stripped'] == []


def test_the_original_response_is_not_mutated():
    response = {'scripts': {'mine.py': 'import minqlx\n'}, 'checked_plugins': ['mine.py']}
    apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert 'mine.py' in response['scripts']
    assert response['checked_plugins'] == ['mine.py']


def test_the_reverse_direction_strips_a_minqlxtended_plugin_for_a_minqlx_host():
    response = {'scripts': {'ported.py': 'import minqlxtended\n'}, 'checked_plugins': ['ported.py']}
    result = apply_compatibility(response, MINQLXTENDED, MINQLX)
    assert 'ported.py' not in result['scripts']
    assert result['compatibility']['target_runtime'] == MINQLX
    assert result['compatibility']['preset_runtime'] == MINQLXTENDED


def test_replacement_scripts_skips_a_file_that_is_not_utf8(tmp_path, monkeypatch):
    """One plugin saved in the wrong encoding must not take down every other
    file's read: UnicodeDecodeError is a ValueError, not an OSError, so the
    per-file except clause has to catch both."""
    import ui.preset_compat as preset_compat
    preset_dir = tmp_path / 'default-minqlxtended' / 'scripts'
    preset_dir.mkdir(parents=True)
    (preset_dir / 'good.py').write_text('import minqlxtended\n', encoding='utf-8')
    (preset_dir / 'bad.py').write_bytes(b'# broken \xe9 latin-1 comment\nimport minqlxtended\n')
    monkeypatch.setattr(preset_compat, 'BUILTIN_PRESETS_DIR', str(tmp_path))
    scripts = preset_compat.replacement_scripts(MINQLXTENDED)
    assert scripts == {'good.py': 'import minqlxtended\n'}


def test_apply_compatibility_completes_when_a_replacement_candidate_is_unreadable(tmp_path, monkeypatch):
    """The crash reproduced above must not surface through apply_compatibility
    either: a bad file among the replacement candidates must not take down an
    otherwise-unrelated preset load."""
    import ui.preset_compat as preset_compat
    preset_dir = tmp_path / 'default-minqlxtended' / 'scripts'
    preset_dir.mkdir(parents=True)
    (preset_dir / 'bad.py').write_bytes(b'\xe9 not utf-8\n')
    monkeypatch.setattr(preset_compat, 'BUILTIN_PRESETS_DIR', str(tmp_path))
    response = {'scripts': {'mine.py': 'import minqlx\nx = minqlx.RET_STOP_ALL\n'}, 'checked_plugins': ['mine.py']}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert 'mine.py' not in result['scripts']
    assert result['checked_plugins'] == []


def test_checked_plugins_as_a_string_falls_back_to_none_instead_of_exploding():
    """A hand-edited checked_plugins.json can hold anything. On the matched-
    runtime path a bad value passes through harmlessly; this gate must not
    turn that into silent corruption (a string iterates into characters) just
    because the runtimes now differ. It also must not read a malformed value
    as "the operator explicitly selected nothing" -- None (not []) tells the
    frontend to fall back to its own legacy-preset defaults."""
    response = {'scripts': {'mine.py': 'import minqlx\n'}, 'checked_plugins': 'nope'}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['checked_plugins'] is None


def test_checked_plugins_as_an_int_falls_back_to_none_instead_of_raising():
    response = {'scripts': {'mine.py': 'import minqlx\n'}, 'checked_plugins': 42}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['checked_plugins'] is None


def test_a_missing_checked_plugins_stays_none_instead_of_becoming_an_empty_selection():
    """A preset with no checked_plugins.json at all (pre-dates this feature)
    reads as None, same as the matched-runtime path. Coercing it to []
    here would look identical to "the operator deliberately checked
    nothing", so the frontend's `checked_plugins != null` legacy branch
    (keep whatever is currently checked) would never fire, and a legacy
    preset would silently load onto a new instance with zero plugins."""
    response = {'scripts': {'myFun.py': 'import minqlx\n'}}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['checked_plugins'] is None
    # The entry is still reported and still not pre-accepted, since nothing
    # was ever checked for it -- None only changes what happens to the whole
    # instance's plugin selection, not per-entry defaulting.
    assert result['compatibility']['stripped'][0]['originally_checked'] is False


def test_a_subdirectory_helper_the_target_ships_is_reported_auto_replaced():
    """The report has to describe the restore, or it describes a loss that never happens.

    _apply_runtime_filter puts the target's own copy back when the source overlay writes
    over a subdirectory file it also ships. Without a marker, that file appears in
    `stripped` with `replacement: None`, which the dialog renders identically to a file
    that is genuinely gone -- the two were indistinguishable, and operators reported the
    discord_extensions/ helpers as "still incompatible" while they were landing fine.
    """
    path = os.path.join('discord_extensions', 'admin.py')
    response = {'scripts': {path: 'import minqlx\n'}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['path'] == path
    assert entry['auto_replaced'] is True
    # Still no offer: a subdirectory file cannot be ticked, it is simply restored.
    assert entry['replacement'] is None


def test_a_subdirectory_helper_the_target_does_not_ship_is_a_real_loss():
    """The marker must distinguish, not blanket every subdirectory file."""
    path = os.path.join('discord_extensions', 'not_shipped_by_target.py')
    response = {'scripts': {path: 'import minqlx\n'}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['auto_replaced'] is False
    assert entry['replacement'] is None


def test_a_root_level_file_is_never_auto_replaced():
    """Root files go through the dialog. Auto-swapping one would change a plugin under
    the operator without asking, which is what the checkbox exists to prevent."""
    response = {'scripts': {'balance.py': 'import minqlx\n'}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['auto_replaced'] is False
    assert entry['replacement'] == 'balance.py'


def test_the_report_and_the_filter_read_the_same_shipped_files():
    """draft_routes delegates to shipped_scripts() precisely so these cannot diverge.

    They are the two halves of one promise -- what the operator is shown and what lands
    on disk -- and this gate has already been rewritten twice over them drifting apart.
    """
    from ui.preset_compat import shipped_scripts
    from ui.routes.draft_routes import _target_default_preset_files
    assert shipped_scripts(MINQLXTENDED) == _target_default_preset_files(MINQLXTENDED)


# --- Only actionable strips reach the operator -------------------------------
#
# A preset's `scripts` map is not the operator's file list: _read_preset_scripts()
# lays the whole default catalog of the preset's runtime down first and overlays
# the preset's own files on top. Every one of those stock files is stripped
# against the other runtime, which turned the dialog into a ~48-row wall of
# plugins the operator never chose, edited, or knew were in the preset -- and
# confirming it re-enabled the lot. The gate now swaps a stock file the preset
# never touched for the target's own copy silently, and reports only what the
# operator genuinely has a stake in.


def _stock(name, runtime=MINQLX):
    """A file byte-identical to the one `runtime`'s default preset ships."""
    from ui.preset_compat import shipped_scripts
    return shipped_scripts(runtime)[name]


def test_an_untouched_stock_plugin_is_not_reported_to_the_operator():
    response = {'scripts': {'balance.py': _stock('balance.py')}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['compatibility']['stripped'] == []


def test_an_untouched_stock_plugin_is_swapped_automatically():
    """It still has to reach the draft as an accepted replacement: the filter
    deletes the source file and only writes back what it is handed."""
    response = {'scripts': {'balance.py': _stock('balance.py')}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['compatibility']['auto_accepted'] == ['balance.py']


def test_an_untouched_stock_plugin_keeps_the_tick_the_preset_gave_it():
    """The whole point: loading a preset must reproduce THAT preset's plugin
    selection on the target runtime, not the target's default selection."""
    response = {
        'scripts': {'balance.py': _stock('balance.py'), 'motd.py': _stock('motd.py')},
        'checked_plugins': ['balance.py'],
    }
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['checked_plugins'] == ['balance.py']


def test_an_untouched_stock_plugin_the_preset_disabled_stays_disabled():
    """The reported bug, stated as a test: a stock plugin the operator never
    enabled must not come back enabled just because the target ships one."""
    response = {
        'scripts': {'balance.py': _stock('balance.py'), 'motd.py': _stock('motd.py')},
        'checked_plugins': ['balance.py'],
    }
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert 'motd.py' not in result['checked_plugins']


def test_a_modified_stock_plugin_is_reported_as_a_decision():
    """Accepting the swap discards the operator's edits, so it is theirs to make."""
    response = {
        'scripts': {'balance.py': _stock('balance.py') + '\n# my edit\n'},
        'checked_plugins': ['balance.py'],
    }
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['path'] == 'balance.py'
    assert entry['kind'] == 'replaceable'
    # from_catalog is what lets the dialog say "you modified a standard plugin"
    # rather than "this is a plugin of your own" -- same strip, different news.
    assert entry['from_catalog'] is True


def test_a_custom_plugin_with_no_counterpart_is_reported():
    response = {
        'scripts': {'mycustom.py': 'import minqlx\n'},
        'checked_plugins': ['mycustom.py'],
    }
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['kind'] == 'unavailable'
    assert entry['from_catalog'] is False


def test_a_stock_plugin_with_no_counterpart_the_preset_had_enabled_is_reported():
    """ServerStatus.py is the real case: minqlx ships it, minqlxtended has
    nothing by that name. Losing a plugin the operator had running is news even
    though they never edited the file."""
    response = {
        'scripts': {'ServerStatus.py': _stock('ServerStatus.py')},
        'checked_plugins': ['ServerStatus.py'],
    }
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['path'] == 'ServerStatus.py'
    assert entry['kind'] == 'unavailable'
    assert entry['originally_checked'] is True


def test_a_stock_plugin_with_no_counterpart_the_preset_disabled_is_dropped_quietly():
    """It came from the catalog seed, not from anything the operator did."""
    response = {
        'scripts': {'ServerStatus.py': _stock('ServerStatus.py')},
        'checked_plugins': [],
    }
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['compatibility']['stripped'] == []


def test_a_modified_helper_module_is_still_reported_as_auto_replaced():
    """Restoring the target's copy loses whatever the preset put there, so the
    operator is told -- but there is still no choice to offer."""
    path = os.path.join('discord_extensions', 'admin.py')
    response = {'scripts': {path: 'import minqlx\n'}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['kind'] == 'helper'
    assert entry['auto_replaced'] is True


def test_an_untouched_helper_module_is_restored_without_a_word():
    path = os.path.join('discord_extensions', 'admin.py')
    response = {'scripts': {path: _stock(path)}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['compatibility']['stripped'] == []


def test_a_whole_untouched_catalog_asks_the_operator_nothing():
    """The reported symptom, end to end. A preset saved from a plain minqlx
    instance carries the entire minqlx catalog; before this, all ~48 files were
    listed and confirming the dialog enabled every one of them."""
    from ui.preset_compat import shipped_scripts
    catalog = shipped_scripts(MINQLX)
    response = {'scripts': dict(catalog), 'checked_plugins': ['balance.py']}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    # ServerStatus.py is the only catalog plugin minqlxtended has no version of,
    # and this preset did not have it enabled, so nothing needs saying.
    assert result['compatibility']['stripped'] == []
    assert result['checked_plugins'] == ['balance.py']


def test_a_preset_that_recorded_no_selection_still_records_none():
    """Legacy presets pre-date checked_plugins.json. None is not an empty
    selection -- the frontend keeps the current defaults for it, and an empty
    list would instead load the instance with no plugins at all."""
    from ui.preset_compat import shipped_scripts
    response = {'scripts': dict(shipped_scripts(MINQLX))}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['checked_plugins'] is None


# --- "Untouched" means untouched by EITHER allow-list ------------------------
#
# The source runtime ships more plugins than its default preset offers, and for
# a few files the two disagree on content. Checking only the default preset got
# both halves wrong on the same real preset: stock plugins the default preset
# does not carry were reported as the operator's own work, and a preset holding
# upstream's untouched motd.py was reported as having modified it -- when the
# modification is QLSM's own default preset.


def _manifest_stock(name, runtime=MINQLX):
    """A file byte-identical to what `runtime`'s baseline MANIFEST records,
    which is not always what its default preset ships."""
    from ui.preset_compat import ASSETS_DIR
    from ui.runtime import runtime_paths
    directory = os.path.join(ASSETS_DIR, runtime_paths(runtime)['asset_plugins_dir'])
    with open(os.path.join(directory, name), 'r', encoding='utf-8') as handle:
        return handle.read()


def test_the_two_source_allow_lists_actually_differ():
    """Guards the premise. If the manifest and the default preset ever held the
    same files with the same content, every test below would pass vacuously."""
    from ui.preset_compat import baseline_hashes, shipped_scripts
    manifest = baseline_hashes(MINQLX)
    catalog = shipped_scripts(MINQLX)
    assert set(manifest) - set(catalog), 'manifest must carry files the default preset does not'
    from ui.plugin_compat import baseline_digest
    disagree = {name for name, digest in manifest.items()
                if name in catalog and baseline_digest(catalog[name]) != digest}
    assert disagree, 'the two lists must disagree on some file\'s content'


def test_a_stock_plugin_absent_from_the_default_preset_is_not_called_the_operators():
    """reset_acc.py and suppress_join_msg.py are in the minqlx manifest but not
    in QLSM's minqlx default preset. Reporting them made a real preset's dialog
    claim the operator had written stock upstream plugins."""
    content = _manifest_stock('reset_acc.py')
    response = {'scripts': {'reset_acc.py': content}, 'checked_plugins': ['reset_acc.py']}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['compatibility']['stripped'] == []
    assert 'reset_acc.py' in result['compatibility']['auto_accepted']
    assert result['checked_plugins'] == ['reset_acc.py']


def test_a_preset_holding_upstreams_file_is_not_accused_of_modifying_it():
    """QLSM's minqlx default preset ships a customised motd.py; the manifest
    records upstream's. A preset carrying upstream's untouched copy differs from
    the default preset and used to be reported as 'this preset modified it' --
    exactly backwards, since the modification is QLSM's."""
    content = _manifest_stock('motd.py')
    from ui.plugin_compat import baseline_digest
    from ui.preset_compat import shipped_scripts
    assert baseline_digest(shipped_scripts(MINQLX)['motd.py']) != baseline_digest(content), (
        'this test is only meaningful while the default preset and the manifest '
        'disagree about motd.py')
    response = {'scripts': {'motd.py': content}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['compatibility']['stripped'] == []


def test_a_genuinely_edited_plugin_is_still_reported():
    """The widened allow-list must not swallow real edits."""
    content = _manifest_stock('motd.py') + '\n# my edit\n'
    response = {'scripts': {'motd.py': content}, 'checked_plugins': ['motd.py']}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    entry = result['compatibility']['stripped'][0]
    assert entry['path'] == 'motd.py'
    assert entry['kind'] == 'replaceable'
    assert entry['from_catalog'] is True


def test_a_subdirectory_file_cannot_borrow_a_root_plugins_manifest_hash():
    """The manifest is keyed by bare filename. `extras/motd.py` is not `motd.py`,
    and must not read as untouched because a root plugin by that name matches."""
    path = os.path.join('extras', 'motd.py')
    response = {'scripts': {path: _manifest_stock('motd.py')}, 'checked_plugins': []}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert [entry['path'] for entry in result['compatibility']['stripped']] == [path]


def test_a_plugin_of_the_operators_own_is_not_called_a_standard_one():
    """from_catalog drives the dialog's wording: claiming the operator modified
    a standard plugin when they wrote the file themselves is a false statement
    about their own work."""
    response = {'scripts': {'x76admin.py': 'import minqlx\n'}, 'checked_plugins': ['x76admin.py']}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['compatibility']['stripped'][0]['from_catalog'] is False


def test_root_plugin_path_governs_every_decision_from_one_place():
    """Three decisions read this rule -- whether a replacement may be offered,
    whether the bare-filename manifest may be consulted, and whether a file
    counts as coming from the source catalog. They lived as three separate
    inline copies of the same condition; keeping them in sync by hand is how the
    two halves of this gate have already drifted apart twice."""
    from ui.preset_compat import is_root_plugin_path
    assert is_root_plugin_path('balance.py') is True
    assert is_root_plugin_path(os.path.join('extras', 'balance.py')) is False
    assert is_root_plugin_path('discord_extensions/admin.py') is False
