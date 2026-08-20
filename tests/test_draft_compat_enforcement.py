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
    """Every file the report says was stripped is absent from the draft.

    This is the assertion that was missing. It ties the operator-facing
    report to the bytes on disk, so the two cannot drift apart again.
    """
    files = {'bad.py': MINQLX_PLUGIN}
    report = apply_compatibility(
        {'scripts': dict(files), 'checked_plugins': list(files)},
        'minqlx', 'minqlxtended')
    stripped = {entry['path'] for entry in report['compatibility']['stripped']}
    assert stripped, 'fixture must actually be incompatible'

    draft = _seed(app, tmp_path, files)
    on_disk = set(os.listdir(draft))
    assert stripped.isdisjoint(on_disk), (
        f'the report claims {stripped} were stripped, but {stripped & on_disk} '
        f'are still on disk and would be copied onto the instance')


def test_accepting_a_replacement_puts_target_code_on_disk(app, tmp_path):
    """The name in checked_plugins must not point at minqlx code.

    Consequence (b) of the Critical: ticking the name while leaving the minqlx
    file under it enables minqlx code on a minqlxtended host.
    """
    candidates = replacement_scripts('minqlxtended')
    name = sorted(candidates)[0]
    draft = _seed(app, tmp_path, {name: MINQLX_PLUGIN}, accepted=[name])
    assert (draft / name).read_text() == candidates[name]


def test_a_matched_runtime_load_installs_everything(app, tmp_path):
    """The common case must be untouched: no target_runtime, no filtering."""
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


def test_real_default_preset_survives_a_matched_runtime_load(app):
    """The regression test for the 53 -> 40 over-strip, against the real preset.

    Synthetic fixtures missed this: the shipped preset copies have drifted from the
    ql-assets baseline, so 8 of them do not digest-match and land `unknown`. Only a
    real-asset test exercises that.
    """
    import tempfile
    src = 'configs/presets/_builtin/default/scripts'
    def pys(root):
        return {os.path.relpath(os.path.join(r, f), root)
                for r, _d, fs in os.walk(root) for f in fs if f.endswith('.py')}
    with tempfile.TemporaryDirectory() as tmp:
        draft = os.path.join(tmp, 'draft')
        with app.app_context():
            _seed_draft(draft, src, 'default',
                        target_runtime='minqlx', source_runtime='minqlx')
        assert pys(draft) == pys(src), 'matched-runtime load lost files'
