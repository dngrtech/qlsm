"""What the dialog promised is what is on disk.

The P5 branch shipped a gate that filtered `response_data['scripts']` -- a
field no frontend code reads -- and passed 550 tests. This module asserts on
the draft directory instead, because that directory is what
instance_routes.py copies onto the instance.
"""
import os

from ui.plugin_compat import baseline_digest
from ui.preset_compat import apply_compatibility, replacement_scripts
from ui.routes.draft_routes import _seed_draft

MINQLX_DEFAULT = os.path.join('configs', 'presets', '_builtin', 'default', 'scripts')
MINQLXTENDED_DEFAULT = os.path.join(
    'configs', 'presets', '_builtin', 'default-minqlxtended', 'scripts')

# Files a minqlxtended-preset -> minqlx-host load can delete without ever naming
# them. A file qualifies by being shipped in the minqlx default preset and absent
# from the minqlxtended one: _seed_draft's overlay puts it in the draft, and the
# dialog -- computed from the SOURCE preset -- cannot list it. It then misses the
# ql-assets hash allow-list, lands `unknown`, and is deleted.
#
# This was nine files (commlink, iouonegirl, mybalance, mydiscordbot, the four
# discord_extensions/ helpers and extras/textart). Porting those to minqlxtended
# put them in BOTH default presets, which takes them out of this class entirely:
# they now arrive from the SOURCE preset, so the dialog lists them and any
# deletion is reported rather than silent.
#
# ServerStatus.py is what remains, and it cannot be closed the same way. It is
# not a plugin -- it is an Oracle WebLogic admin script in Python 2 that reads
# sys.argv[1:6] at import -- so there is no minqlxtended counterpart to ship.
UNREPORTED_OVERLAY_DELETIONS = {
    'ServerStatus.py',
}

MINQLX_PLUGIN = "import minqlx\n\n\nclass a(minqlx.Plugin):\n    RET = RET_STOP_ALL\n"


def _seed(app, tmp_path, files, accepted=None):
    source = tmp_path / 'src'
    source.mkdir()
    for name, text in files.items():
        (source / name).write_text(text)
    draft = tmp_path / 'draft'
    # _seed_draft resolves the default preset's path via resolve_preset_subdir(),
    # which hits the database through get_preset_by_name() on every call --
    # not only when a runtime filter runs. Task 3's own tests wrap every
    # _seed_draft call in app.app_context() for the same reason, including
    # its target_runtime=None case (tests/test_draft_routes.py:1257).
    with app.app_context():
        _seed_draft(str(draft), str(source), target_runtime='minqlxtended',
                    accepted_replacements=accepted)
    return draft


def test_the_report_and_the_directory_agree(app, tmp_path):
    """Every file the report strips is absent from the draft, and every file
    it keeps is present -- both directions.

    A fixture with only an incompatible file cannot distinguish "strip
    exactly the incompatible file" from "strip every .py unconditionally":
    both make the one file disappear. Pairing it with a file drawn from the
    real minqlxtended baseline (so it hash-matches the manifest and is judged
    compatible) pins the other direction too, ruling out an implementation
    that strips indiscriminately.
    """
    good_name = 'aliases.py'
    good_path = os.path.join('ql-assets', 'data', 'minqlxtended-plugins', good_name)
    with open(good_path, 'r', encoding='utf-8') as handle:
        good_content = handle.read()

    files = {'bad.py': MINQLX_PLUGIN, good_name: good_content}
    report = apply_compatibility(
        {'scripts': dict(files), 'checked_plugins': list(files)},
        'minqlx', 'minqlxtended')
    stripped = {entry['path'] for entry in report['compatibility']['stripped']}
    assert stripped == {'bad.py'}, (
        f'fixture must strip exactly the incompatible file, got {stripped}')

    draft = _seed(app, tmp_path, files)
    on_disk = set(os.listdir(draft))
    assert stripped.isdisjoint(on_disk), (
        f'the report claims {stripped} were stripped, but {stripped & on_disk} '
        f'are still on disk and would be copied onto the instance')
    assert good_name in on_disk, (
        f'{good_name} was not stripped by the report but is missing from disk')
    assert (draft / good_name).read_text() == good_content, (
        f'{good_name} survived but its content on disk was altered')


def test_accepting_a_replacement_puts_target_code_on_disk(app, tmp_path):
    """The name in checked_plugins must not point at minqlx code.

    Consequence (b) of the Critical: ticking the name while leaving the minqlx
    file under it enables minqlx code on a minqlxtended host. The disk bytes
    are compared against what apply_compatibility() OFFERED in its report,
    not against replacement_scripts() directly -- both currently read from
    the same source, so a direct comparison could not catch the dialog
    offering one thing while enforcement writes another.
    """
    candidates = replacement_scripts('minqlxtended')
    name = sorted(candidates)[0]

    report = apply_compatibility(
        {'scripts': {name: MINQLX_PLUGIN}, 'checked_plugins': [name]},
        'minqlx', 'minqlxtended')
    offered = report['compatibility']['replacements'].get(name)
    assert offered, f'{name} must be offered a replacement for this test to mean anything'

    draft = _seed(app, tmp_path, {name: MINQLX_PLUGIN}, accepted=[name])
    assert (draft / name).read_text() == offered, (
        'the bytes written to disk do not match what the report offered')


def test_a_matched_runtime_load_installs_everything(app, tmp_path):
    """No target_runtime means no filtering.

    The frontend only sends target_runtime when it has one (draftApi.js
    includes it conditionally, not on every call), so this omitted-runtime
    path is live rather than vestigial -- it does not need a frequency claim
    to justify testing it, only that the path exists.
    """
    source = tmp_path / 'src'
    source.mkdir()
    (source / 'x.py').write_text(MINQLX_PLUGIN)
    draft = tmp_path / 'draft'
    with app.app_context():
        _seed_draft(str(draft), str(source))
    assert (draft / 'x.py').exists()


def test_matched_runtime_passed_EXPLICITLY_still_installs_everything(tmp_path, app):
    """The real matched-runtime case: target_runtime is SET and equals the source.

    This is NOT the same as the test above. Once the frontend wires the gate up it
    passes the host's runtime on EVERY draft creation, matched or not -- so
    `target_runtime=None` stops being the matched-runtime path and this becomes it.
    An earlier revision of this branch filtered whenever target_runtime was merely
    truthy, and deleted 13 of the 53 plugins in QLSM's own default preset on a
    plain minqlx-preset-onto-minqlx-host load. Nothing caught it, because the only
    matched-runtime test was the one above, which passes no runtime at all.
    """
    source = tmp_path / 'src'
    source.mkdir()
    (source / 'x.py').write_text(MINQLX_PLUGIN)
    draft = tmp_path / 'draft'
    with app.app_context():
        _seed_draft(str(draft), str(source), target_runtime='minqlx',
                    source_runtime='minqlx')
    assert (draft / 'x.py').exists(), (
        'a matched-runtime load must not strip anything, even when the runtime '
        'is passed explicitly')


def _pys(root):
    return {os.path.relpath(os.path.join(r, f), root)
            for r, _d, fs in os.walk(root) for f in fs if f.endswith('.py')}


def _digests(root):
    """relpath -> baseline_digest for a shipped preset's scripts directory.

    Walked here rather than imported from draft_routes so the oracle does not
    reuse the implementation it is checking. The hashing RULE is shared on
    purpose -- baseline_digest is the one rule the manifest, the gate and this
    file must agree on, and re-deriving it would only re-create the raw-bytes
    vs normalised-text mismatch that already cost this branch a fix round.
    """
    digests = {}
    for root_dir, _dirs, filenames in os.walk(root):
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            full = os.path.join(root_dir, filename)
            with open(full, 'r', encoding='utf-8') as handle:
                digests[os.path.relpath(full, root)] = baseline_digest(handle.read())
    return digests


def test_real_default_preset_survives_a_matched_runtime_load(app):
    """The regression test for the 53 -> 40 over-strip, against the real preset.

    Synthetic fixtures missed this: the shipped preset copies have drifted from the
    ql-assets baseline, so 8 of them do not digest-match and land `unknown`. Only a
    real-asset test exercises that.
    """
    import tempfile
    src = 'configs/presets/_builtin/default/scripts'
    source_files = _pys(src)
    # Guard against a vacuous pass: os.walk() on a path that does not resolve
    # (e.g. this suite run from tests/ instead of the repo root) silently
    # yields nothing, _seed_draft then falls back to an empty draft, and
    # set() == set() is green having compared zero files -- inside the very
    # module whose purpose is catching exactly that failure mode.
    assert len(source_files) == 53, (
        f'expected the real default preset to have 53 .py files, found '
        f'{len(source_files)} -- run pytest from the repo root')

    with tempfile.TemporaryDirectory() as tmp:
        draft = os.path.join(tmp, 'draft')
        with app.app_context():
            _seed_draft(draft, src, 'default',
                        target_runtime='minqlx', source_runtime='minqlx')
        assert _pys(draft) == source_files, 'matched-runtime load lost files'


def test_real_default_preset_cross_runtime_filter_matches_the_report(app, tmp_path):
    """The real preset, run through a genuine CROSS-runtime filter, still
    agrees between what the report says was kept and what lands on disk --
    for both a file that gets stripped and one that survives.

    Every one of the real preset's 53 files opens with `import minqlx`, so
    on an unmodified minqlx -> minqlxtended filter every single one is
    INCOMPATIBLE and the kept set is empty on both sides -- the assertion
    would degenerate to set() == set() and pass against a filter that
    deletes everything unconditionally. This is NOT a test of the
    hash-drifted `unknown` files from the 53 -> 40 regression: those only
    matter on a matched-runtime load (see the test above), because a
    cross-runtime load never reaches the hash-vs-scanner distinction for
    files the scanner already flags on content alone. What this test
    actually proves is narrower and still real: swap one real file's
    content for its minqlxtended-baseline counterpart (so it hash-matches
    and is judged compatible), and the report and the disk must agree on
    BOTH the 52 files that get stripped AND the one that survives, using
    real preset content rather than single-line synthetic fixtures.
    """
    import shutil
    src = 'configs/presets/_builtin/default/scripts'
    source_files = _pys(src)
    assert len(source_files) == 53, (
        f'expected the real default preset to have 53 .py files, found '
        f'{len(source_files)} -- run pytest from the repo root')

    good_name = 'aliases.py'
    good_content_path = os.path.join('ql-assets', 'data', 'minqlxtended-plugins', good_name)
    with open(good_content_path, 'r', encoding='utf-8') as handle:
        good_content = handle.read()

    # A copy of the real preset with one file's content swapped for the
    # hash-matched minqlxtended original -- not a synthetic fixture, and not
    # a mutation of the shipped preset on disk.
    seeded_src = tmp_path / 'src'
    shutil.copytree(src, str(seeded_src))
    (seeded_src / good_name).write_text(good_content)

    scripts = {}
    for rel in source_files:
        with open(seeded_src / rel, 'r', encoding='utf-8') as handle:
            scripts[rel] = handle.read()

    report = apply_compatibility(
        {'scripts': scripts, 'checked_plugins': sorted(scripts)},
        'minqlx', 'minqlxtended')
    # The oracle is `compatibility.stripped` -- the list the dialog actually
    # renders (PresetCompatibilityDialog.jsx maps over it). `report['scripts']`
    # is the filtered copy nothing in the frontend reads: applyPresetData()
    # never touches presetData.scripts, the draft workspace supplies the files.
    # It is the same dead field the original P5 implementation was rejected for
    # enforcing on, so an assertion built from it proves nothing about what the
    # operator was shown.
    reported_stripped = {entry['path']
                         for entry in report['compatibility']['stripped']}
    reported_kept = source_files - reported_stripped
    assert reported_kept, (
        'the fixture must leave at least one file KEPT, or the disk comparison '
        'degenerates and passes against a filter that deletes everything')
    assert reported_stripped, (
        'fixture must actually exercise cross-runtime stripping, or this '
        'test cannot tell a correct filter from a disabled one')

    # A draft file byte-identical to what the TARGET runtime's own default
    # preset ships at that path is exempt from the filter -- deleting the
    # target's own shipped baseline is never correct -- so it can legitimately
    # survive even while the report lists it stripped. Folded into the expected
    # set rather than weakened to a subset check, so both directions stay
    # pinned.
    exempt = {rel for rel, digest in _digests(MINQLXTENDED_DEFAULT).items()
              if rel in scripts and baseline_digest(scripts[rel]) == digest}

    draft = tmp_path / 'draft'
    with app.app_context():
        _seed_draft(str(draft), str(seeded_src), 'default',
                    target_runtime='minqlxtended', source_runtime='minqlx')
    on_disk = _pys(str(draft))

    expected_on_disk = reported_kept | (reported_stripped & exempt)
    assert on_disk == expected_on_disk, (
        'the draft on disk and the compatibility report disagree about what '
        'a real minqlx -> minqlxtended preset load keeps: '
        f'disk-only={on_disk - expected_on_disk} '
        f'report-only={expected_on_disk - on_disk}')


def _seed_the_cross_runtime_overlay(app, tmp_path):
    """A minqlxtended preset loaded onto a minqlx host, the production way.

    'default' is not a test convenience: create_draft passes the TARGET
    runtime's builtin default whenever the runtimes differ (draft_routes.py,
    `runtimes_differ`), so for a minqlx host that is exactly this name. The
    draft therefore ends up holding the minqlx default's 53 files with the
    minqlxtended preset's 38 laid over the top, and the filter walks all of it.
    """
    draft = tmp_path / 'draft'
    with app.app_context():
        _seed_draft(str(draft), os.path.abspath(MINQLXTENDED_DEFAULT), 'default',
                    target_runtime='minqlx', source_runtime='minqlxtended')
    return draft


def test_a_cross_runtime_load_keeps_the_target_runtimes_own_shipped_plugins(
        app_with_builtin_presets, tmp_path):
    """The target's own default preset is overlaid FIRST, then filtered.

    Requires app_with_builtin_presets, not `app`: without the builtin preset
    rows, resolve_preset_subdir('default') answers a path that does not exist,
    the overlay branch never runs, and this test would pass vacuously against
    a filter that deletes the whole overlay. The overlay is the production
    path -- production always has those rows.
    """
    source_files = _pys(MINQLXTENDED_DEFAULT)
    overlay_files = _pys(MINQLX_DEFAULT)
    assert len(source_files) == 74 and len(overlay_files) == 53, (
        f'expected the two shipped defaults to hold 74 and 53 .py files, found '
        f'{len(source_files)} and {len(overlay_files)} -- run pytest from the '
        f'repo root')

    on_disk = _pys(str(_seed_the_cross_runtime_overlay(
        app_with_builtin_presets, tmp_path)))

    # Files only the TARGET's default preset has. Nothing in the source preset
    # overwrote them, so whatever is on disk under those paths came from the
    # target runtime's own shipped baseline -- which the target runtime can, by
    # definition, run.
    overlay_only = overlay_files - source_files
    assert overlay_only, (
        'the two shipped defaults must differ for this test to mean anything')
    assert overlay_only <= on_disk, (
        f'the load deleted {len(overlay_only - on_disk)} file(s) that came from '
        f'the TARGET runtime\'s own default preset: '
        f'{sorted(overlay_only - on_disk)}')


def test_a_cross_runtime_load_deletes_nothing_the_dialog_never_listed(
        app_with_builtin_presets, tmp_path):
    """The shown-vs-deleted invariant, over the file set production really has.

    The dialog is computed from the SOURCE preset (that is what GET /presets
    returns), while the draft holds the source preset ON TOP OF the target
    runtime's default. Anything deleted out of the half the dialog never saw is
    a file vanishing from an operator's config with no notice anywhere.
    """
    source_files = _pys(MINQLXTENDED_DEFAULT)
    overlay_files = _pys(MINQLX_DEFAULT)

    scripts = {}
    for rel in source_files:
        with open(os.path.join(MINQLXTENDED_DEFAULT, rel), 'r', encoding='utf-8') as handle:
            scripts[rel] = handle.read()
    report = apply_compatibility(
        {'scripts': scripts, 'checked_plugins': sorted(scripts)},
        'minqlxtended', 'minqlx')
    shown = {entry['path'] for entry in report['compatibility']['stripped']}
    assert shown, 'the dialog must list something, or this test cannot fail'

    on_disk = _pys(str(_seed_the_cross_runtime_overlay(
        app_with_builtin_presets, tmp_path)))
    deleted = (source_files | overlay_files) - on_disk
    assert deleted, (
        'the fixture must actually strip something, or a disabled filter passes')
    assert deleted <= shown, (
        f'{len(deleted - shown)} file(s) were deleted from the draft without '
        f'ever appearing in the dialog: {sorted(deleted - shown)}')


def test_the_silently_deleted_overlay_plugins_survive(
        app_with_builtin_presets, tmp_path):
    """Names it, so a regression reads as a regression and not as a set diff.

    These were deleted from every cross-runtime load onto a minqlx host and
    appeared in no dialog, no report and no log the operator sees. The set was
    nine files until the minqlxtended ports landed; see the note on
    UNREPORTED_OVERLAY_DELETIONS for why only ServerStatus.py is left.
    """
    on_disk = _pys(str(_seed_the_cross_runtime_overlay(
        app_with_builtin_presets, tmp_path)))
    assert UNREPORTED_OVERLAY_DELETIONS <= on_disk, (
        f'still deleted without notice: '
        f'{sorted(UNREPORTED_OVERLAY_DELETIONS - on_disk)}')

    # And they really are absent from the dialog -- if they were listed, their
    # deletion would merely be unwanted rather than silent, and the assertion
    # above would be pinning the wrong property.
    scripts = {}
    for rel in _pys(MINQLXTENDED_DEFAULT):
        with open(os.path.join(MINQLXTENDED_DEFAULT, rel), 'r', encoding='utf-8') as handle:
            scripts[rel] = handle.read()
    report = apply_compatibility(
        {'scripts': scripts, 'checked_plugins': sorted(scripts)},
        'minqlxtended', 'minqlx')
    shown = {entry['path'] for entry in report['compatibility']['stripped']}
    assert UNREPORTED_OVERLAY_DELETIONS.isdisjoint(shown), (
        f'these are listed in the dialog after all, so this test is pinning '
        f'the wrong thing: {sorted(UNREPORTED_OVERLAY_DELETIONS & shown)}')

