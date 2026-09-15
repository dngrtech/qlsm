import json

import pytest

import ui.plugin_repositories as plugin_repositories
from ui.plugin_repositories import (
    PluginRepositoryError,
    download_plugin,
    fetch_manifest,
    version_risk,
)


class FakeResponse:
    def __init__(self, status_code=200, content=b''):
        self.status_code = status_code
        self.content = content


# --- fetch_manifest ---

def test_fetch_manifest_parses_valid_entries(monkeypatch):
    manifest = {
        'plugins': [
            {'filename': 'balance2.py', 'label': 'Balance', 'runtime': 'minqlx',
             'requires_qlsm_version': '1.0.0'},
        ]
    }
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, json.dumps(manifest).encode()),
    )
    plugins = fetch_manifest('https://example.com/repo')
    assert plugins == [{
        'filename': 'balance2.py',
        'label': 'Balance',
        'description': None,
        'runtime': 'minqlx',
        'requires_qlsm_version': '1.0.0',
    }]


def test_fetch_manifest_drops_bad_entries_but_keeps_good_ones(monkeypatch):
    manifest = {'plugins': [
        {'filename': 'good.py'},
        {'filename': 'has/slash.py'},
        {'filename': 'no_extension'},
        {'filename': 42},
        'not-a-dict',
        {'filename': 'also_good.py', 'runtime': 'not-a-real-runtime'},
    ]}
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, json.dumps(manifest).encode()),
    )
    plugins = fetch_manifest('https://example.com/repo')
    assert [p['filename'] for p in plugins] == ['good.py', 'also_good.py']
    # An unrecognized runtime string is dropped to None rather than kept raw.
    assert plugins[1]['runtime'] is None


def test_fetch_manifest_requests_the_manifest_filename(monkeypatch):
    seen = {}

    def fake_get(url, timeout):
        seen['url'] = url
        return FakeResponse(200, json.dumps({'plugins': []}).encode())

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    fetch_manifest('https://example.com/repo/')
    assert seen['url'] == 'https://example.com/repo/qlsm-plugins.json'


def test_fetch_manifest_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(plugin_repositories.requests, 'get', lambda url, timeout: FakeResponse(404, b''))
    with pytest.raises(PluginRepositoryError):
        fetch_manifest('https://example.com/repo')


def test_fetch_manifest_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(plugin_repositories.requests, 'get', lambda url, timeout: FakeResponse(200, b'not json'))
    with pytest.raises(PluginRepositoryError):
        fetch_manifest('https://example.com/repo')


def test_fetch_manifest_raises_when_plugins_key_is_missing(monkeypatch):
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, json.dumps({'nope': []}).encode()),
    )
    with pytest.raises(PluginRepositoryError):
        fetch_manifest('https://example.com/repo')


def test_fetch_manifest_raises_when_oversized(monkeypatch):
    monkeypatch.setattr(
        plugin_repositories, 'MANIFEST_MAX_SIZE', 10,
    )
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, b'x' * 100),
    )
    with pytest.raises(PluginRepositoryError):
        fetch_manifest('https://example.com/repo')


# --- version_risk ---

def test_version_risk_hard_warning_when_required_is_newer():
    risk = version_risk('2.0.0', current_qlsm_version='1.5.0')
    assert risk['level'] == 'hard'
    assert '2.0.0' in risk['message']
    assert '1.5.0' in risk['message']


def test_version_risk_none_when_required_is_older_or_equal():
    assert version_risk('1.0.0', current_qlsm_version='1.5.0') is None
    assert version_risk('1.5.0', current_qlsm_version='1.5.0') is None


def test_version_risk_none_when_unparseable_or_missing():
    assert version_risk(None, current_qlsm_version='1.5.0') is None
    assert version_risk('not-a-version', current_qlsm_version='1.5.0') is None
    assert version_risk('1.5.0', current_qlsm_version=None) is None


# --- download_plugin ---

def test_download_plugin_writes_source_into_the_matching_pool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(404, b'')
        return FakeResponse(200, b'print("hello")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlx')

    written = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins' / 'demo_plugin.py'
    assert written.read_bytes() == b'print("hello")'
    assert calls[0] == 'https://example.com/repo/demo_plugin.py'


def test_download_plugin_also_writes_a_valid_sidecar_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(200, b'{"label": "Demo"}')
        return FakeResponse(200, b'print("hello")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlxtended')

    manifest_path = tmp_path / 'ql-assets' / 'data' / 'minqlxtended-plugins' / 'demo_plugin.ql-plugin.json'
    assert manifest_path.read_text() == '{"label": "Demo"}'


def test_download_plugin_skips_a_malformed_sidecar_without_failing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(200, b'not json')
        return FakeResponse(200, b'print("hello")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlx')

    pool = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    assert (pool / 'demo_plugin.py').exists()
    assert not (pool / 'demo_plugin.ql-plugin.json').exists()


def test_download_plugin_rejects_unsafe_filenames(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(PluginRepositoryError):
        download_plugin('https://example.com/repo', '../evil.py', 'minqlx')
    with pytest.raises(PluginRepositoryError):
        download_plugin('https://example.com/repo', 'sub/dir.py', 'minqlx')
    with pytest.raises(PluginRepositoryError):
        download_plugin('https://example.com/repo', 'not_python.txt', 'minqlx')


def test_download_plugin_raises_when_source_fetch_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plugin_repositories.requests, 'get', lambda url, timeout: FakeResponse(404, b''))
    with pytest.raises(PluginRepositoryError):
        download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlx')


def test_download_plugin_refuses_to_overwrite_an_existing_pool_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    pool.mkdir(parents=True)
    (pool / 'balance.py').write_text('# bundled copy')

    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, b'print("repo copy")'),
    )
    with pytest.raises(PluginRepositoryError) as excinfo:
        download_plugin('https://example.com/repo', 'balance.py', 'minqlx')
    assert excinfo.value.code == 'exists'
    # The bundled copy must survive the refused download untouched.
    assert (pool / 'balance.py').read_text() == '# bundled copy'


def test_download_plugin_overwrite_true_replaces_the_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    pool.mkdir(parents=True)
    (pool / 'balance.py').write_text('# bundled copy')

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(404, b'')
        return FakeResponse(200, b'print("repo copy")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'balance.py', 'minqlx', overwrite=True)
    assert (pool / 'balance.py').read_bytes() == b'print("repo copy")'


def test_download_plugin_removes_a_stale_sidecar_when_the_new_copy_has_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    pool.mkdir(parents=True)
    (pool / 'demo_plugin.py').write_text('# old copy')
    (pool / 'demo_plugin.ql-plugin.json').write_text('{"label": "Old"}')

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(404, b'')
        return FakeResponse(200, b'print("new copy")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlx', overwrite=True)

    assert (pool / 'demo_plugin.py').read_bytes() == b'print("new copy")'
    assert not (pool / 'demo_plugin.ql-plugin.json').exists()
