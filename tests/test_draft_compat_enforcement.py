"""What the dialog promised is what is on disk.

The P5 branch shipped a gate that filtered `response_data['scripts']` -- a
field no frontend code reads -- and passed 550 tests. This module asserts on
the draft directory instead, because that directory is what
instance_routes.py copies onto the instance.
"""
import os

from ui.preset_compat import apply_compatibility, replacement_scripts
from ui.routes.draft_routes import _seed_draft

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
    reported_kept = {name for name in report['scripts'] if name.endswith('.py')}
    assert reported_kept, (
        'the fixture must leave at least one file KEPT, or on_disk == reported_kept '
        'degenerates to set() == set() and passes against a filter that deletes everything')
    assert reported_kept != source_files, (
        'fixture must actually exercise cross-runtime stripping, or this '
        'test cannot tell a correct filter from a disabled one')

    draft = tmp_path / 'draft'
    with app.app_context():
        _seed_draft(str(draft), str(seeded_src), 'default',
                    target_runtime='minqlxtended', source_runtime='minqlx')
    on_disk = _pys(str(draft))

    assert on_disk == reported_kept, (
        'the draft on disk and the compatibility report disagree about what '
        'a real minqlx -> minqlxtended preset load keeps: '
        f'disk-only={on_disk - reported_kept} report-only={reported_kept - on_disk}')
