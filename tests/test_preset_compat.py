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


def test_checked_plugins_as_a_string_falls_back_to_empty_instead_of_exploding():
    """A hand-edited checked_plugins.json can hold anything. On the matched-
    runtime path a bad value passes through harmlessly; this gate must not
    turn that into silent corruption (a string iterates into characters) just
    because the runtimes now differ."""
    response = {'scripts': {'mine.py': 'import minqlx\n'}, 'checked_plugins': 'nope'}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['checked_plugins'] == []


def test_checked_plugins_as_an_int_falls_back_to_empty_instead_of_raising():
    response = {'scripts': {'mine.py': 'import minqlx\n'}, 'checked_plugins': 42}
    result = apply_compatibility(response, MINQLX, MINQLXTENDED)
    assert result['checked_plugins'] == []


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
