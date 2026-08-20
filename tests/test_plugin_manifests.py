"""Both plugin baselines must ship a manifest, and it must match the files."""
import json
import os

from ui.plugin_compat import baseline_digest

BASELINES = ['minqlx-plugins', 'minqlxtended-plugins']


def _dir(name):
    return os.path.join('ql-assets', 'data', name)


def test_every_baseline_has_a_manifest():
    for name in BASELINES:
        assert os.path.isfile(os.path.join(_dir(name), 'manifest.json')), \
            f"{name} has no manifest.json -- baseline_hashes() would return {{}} " \
            f"and every plugin would be stripped in that direction"


def test_manifest_covers_every_py_file_and_hashes_match():
    for name in BASELINES:
        directory = _dir(name)
        with open(os.path.join(directory, 'manifest.json'), encoding='utf-8') as fh:
            files = json.load(fh)['files']
        on_disk = sorted(f for f in os.listdir(directory) if f.endswith('.py'))
        assert sorted(files) == on_disk, f"{name}: manifest and directory disagree"
        for filename in on_disk:
            with open(os.path.join(directory, filename), encoding='utf-8') as fh:
                text = fh.read()
            assert files[filename]['sha256'] == baseline_digest(text), \
                f"{name}/{filename}: manifest hash does not match the file"
