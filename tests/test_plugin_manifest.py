"""Tests for the plugin manifest lookup shared by the scripts/draft trees."""

import json

from ui import plugin_manifest


def _write(directory, name, payload):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding='utf-8')


class TestRuntimeAwarePoolLookup:
    """The two runtimes carry their own copy of the same plugin filenames, and
    those copies drift, so an instance's own runtime pool has to win."""

    def test_prefers_the_pool_of_the_instance_runtime(self, tmp_path, monkeypatch):
        minqlx_pool = tmp_path / 'minqlx-plugins'
        extended_pool = tmp_path / 'minqlxtended-plugins'
        _write(minqlx_pool, 'balance.ql-plugin.json', {'label': 'minqlx copy'})
        _write(extended_pool, 'balance.ql-plugin.json', {'label': 'minqlxtended copy'})
        monkeypatch.setattr(plugin_manifest, 'MINQLX_PLUGINS_POOL_DIR', str(minqlx_pool))
        monkeypatch.setattr(plugin_manifest, 'MINQLXTENDED_PLUGINS_POOL_DIR', str(extended_pool))
        monkeypatch.chdir(tmp_path)

        script = tmp_path / 'scripts' / 'balance.py'
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text('# plugin', encoding='utf-8')

        assert plugin_manifest.read_plugin_manifest(str(script), 'minqlxtended')['label'] == 'minqlxtended copy'
        assert plugin_manifest.read_plugin_manifest(str(script), 'minqlx')['label'] == 'minqlx copy'

    def test_falls_back_to_the_other_pool_when_the_runtime_one_has_nothing(self, tmp_path, monkeypatch):
        minqlx_pool = tmp_path / 'minqlx-plugins'
        extended_pool = tmp_path / 'minqlxtended-plugins'
        _write(minqlx_pool, 'balance.ql-plugin.json', {'label': 'only copy'})
        extended_pool.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(plugin_manifest, 'MINQLX_PLUGINS_POOL_DIR', str(minqlx_pool))
        monkeypatch.setattr(plugin_manifest, 'MINQLXTENDED_PLUGINS_POOL_DIR', str(extended_pool))
        monkeypatch.chdir(tmp_path)

        script = tmp_path / 'scripts' / 'balance.py'
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text('# plugin', encoding='utf-8')

        assert plugin_manifest.read_plugin_manifest(str(script), 'minqlxtended')['label'] == 'only copy'

    def test_unknown_runtime_still_answers_from_the_default_pool(self, tmp_path, monkeypatch):
        minqlx_pool = tmp_path / 'minqlx-plugins'
        _write(minqlx_pool, 'balance.ql-plugin.json', {'label': 'default pool'})
        monkeypatch.setattr(plugin_manifest, 'MINQLX_PLUGINS_POOL_DIR', str(minqlx_pool))
        monkeypatch.setattr(plugin_manifest, 'MINQLXTENDED_PLUGINS_POOL_DIR', str(tmp_path / 'missing'))
        monkeypatch.chdir(tmp_path)

        script = tmp_path / 'scripts' / 'balance.py'
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text('# plugin', encoding='utf-8')

        assert plugin_manifest.read_plugin_manifest(str(script), None)['label'] == 'default pool'
        assert plugin_manifest.read_plugin_manifest(str(script), 'nonsense')['label'] == 'default pool'
