import hashlib
import io
import json
import os
import zipfile

import pytest

import ui.plugin_repositories as plugin_repositories
from ui.plugin_manifest import PLUGIN_MANIFEST_MAX_SIZE
from ui.plugin_repositories import (
    PluginRepositoryError,
    addon_update_status,
    build_inline_manifest,
    dependency_filenames,
    download_addon,
    download_plugin,
    expand_with_dependencies,
    fetch_manifest,
    fetch_plugin_source,
    is_safe_package_relpath,
    is_safe_plugin_filename,
    package_update_status,
    plugin_update_status,
    plugin_update_status_with_dependencies,
    version_risk,
)


class FakeResponse:
    def __init__(self, status_code=200, content=b''):
        self.status_code = status_code
        self.content = content


def make_addon_zip(addon_id='demo-addon', version='1.2.0', extra_files=None):
    """A minimal valid addon package as bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('qlsm-addon.json', json.dumps({'id': addon_id, 'version': version}))
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)
    return buf.getvalue()


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
    result = fetch_manifest('https://example.com/repo')
    assert result['addons'] == []
    assert result['plugins'] == [{
        'filename': 'balance2.py',
        'label': 'Balance',
        'description': None,
        'runtime': 'minqlx',
        'version': None,
        'sha256': None,
        'requires_qlsm_version': '1.0.0',
        'depends_on': [],
        'package_files': {},
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
    plugins = fetch_manifest('https://example.com/repo')['plugins']
    assert [p['filename'] for p in plugins] == ['good.py', 'also_good.py']
    # An unrecognized runtime string is dropped to None rather than kept raw.
    assert plugins[1]['runtime'] is None


def test_fetch_manifest_keeps_list_cvars_and_commands(monkeypatch):
    cvars = [{'cvar': 'qlx_demo', 'type': 'bool', 'default': False}]
    commands = [{'name': '!demo', 'description': 'Demo'}]
    manifest = {'plugins': [
        {'filename': 'demo.py', 'cvars': cvars, 'commands': commands},
        {'filename': 'bad.py', 'cvars': 'not-a-list', 'commands': {'a': 1}},
    ]}
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, json.dumps(manifest).encode()),
    )
    plugins = fetch_manifest('https://example.com/repo')['plugins']
    assert plugins[0]['cvars'] == cvars
    assert plugins[0]['commands'] == commands
    # Malformed fields are dropped, the plugin itself stays listed.
    assert plugins[1]['filename'] == 'bad.py'
    assert 'cvars' not in plugins[1]
    assert 'commands' not in plugins[1]


def test_fetch_manifest_falls_back_to_the_legacy_filename(monkeypatch):
    urls = []

    def fake_get(url, timeout):
        urls.append(url)
        if url.endswith('qlsm-repository.json'):
            return FakeResponse(404, b'')
        return FakeResponse(200, json.dumps({'plugins': [{'filename': 'good.py'}]}).encode())

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    result = fetch_manifest('https://example.com/repo')
    assert urls == [
        'https://example.com/repo/qlsm-repository.json',
        'https://example.com/repo/qlsm-plugins.json',
    ]
    assert [p['filename'] for p in result['plugins']] == ['good.py']


def test_fetch_manifest_parses_and_filters_addon_entries(monkeypatch):
    good_sha = 'a' * 64
    manifest = {'addons': [
        {'id': 'good-addon', 'zip': 'good-addon.zip', 'version': '1.2.0',
         'sha256': good_sha.upper(), 'label': 'Good'},
        {'id': 'nested-ok', 'zip': 'packages/nested.zip'},
        {'id': 'Bad_Id', 'zip': 'x.zip'},
        {'id': 'no-zip'},
        {'id': 'escape', 'zip': '../evil.zip'},
        {'id': 'absolute', 'zip': '/evil.zip'},
        {'id': 'not-a-zip', 'zip': 'thing.tar.gz'},
        {'id': 'bad-sha', 'zip': 'ok.zip', 'sha256': 'zz'},
    ]}
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, json.dumps(manifest).encode()),
    )
    addons = fetch_manifest('https://example.com/repo')['addons']
    assert [a['id'] for a in addons] == ['good-addon', 'nested-ok', 'bad-sha']
    # Hashes are normalized to lowercase; an invalid hash is dropped to None.
    assert addons[0]['sha256'] == good_sha
    assert addons[2]['sha256'] is None
    assert addons[1]['zip'] == 'packages/nested.zip'


# --- build_inline_manifest ---

def test_build_inline_manifest_keeps_only_metadata_fields():
    entry = {
        'filename': 'demo.py', 'label': 'Demo', 'description': None,
        'runtime': 'minqlx', 'requires_qlsm_version': '1.0.0', 'version_risk': None,
        'cvars': [{'cvar': 'qlx_demo'}],
    }
    assert build_inline_manifest(entry) == {'label': 'Demo', 'cvars': [{'cvar': 'qlx_demo'}]}


def test_build_inline_manifest_none_for_bare_entry():
    assert build_inline_manifest({'filename': 'demo.py', 'label': None, 'description': None,
                                  'runtime': None, 'requires_qlsm_version': None}) is None
    assert build_inline_manifest(None) is None
    # Scaffolded empty lists are "no metadata" too -- they must not produce a
    # {"cvars": []} sidecar that stops a stale one from being cleaned up.
    assert build_inline_manifest({'filename': 'demo.py', 'cvars': [], 'commands': []}) is None


def test_build_inline_manifest_none_when_over_the_sidecar_size_cap():
    entry = {'filename': 'demo.py', 'description': 'x' * (16 * 1024 + 1)}
    assert build_inline_manifest(entry) is None


def test_fetch_manifest_prefers_the_repository_manifest(monkeypatch):
    seen = {}

    def fake_get(url, timeout):
        seen['url'] = url
        return FakeResponse(200, json.dumps({'plugins': []}).encode())

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    fetch_manifest('https://example.com/repo/')
    assert seen['url'] == 'https://example.com/repo/qlsm-repository.json'


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

    written = tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'demo_plugin.py'
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

    manifest_path = tmp_path / 'data' / 'shared-plugins' / 'minqlxtended' / 'demo_plugin.ql-plugin.json'
    assert manifest_path.read_text() == '{"label": "Demo"}'


def test_download_plugin_skips_a_malformed_sidecar_without_failing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(200, b'not json')
        return FakeResponse(200, b'print("hello")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlx')

    pool = tmp_path / 'data' / 'shared-plugins' / 'minqlx'
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
    pool = tmp_path / 'data' / 'shared-plugins' / 'minqlx'
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


def test_download_plugin_leaves_a_matching_pool_file_alone_without_prompting(tmp_path, monkeypatch):
    """The repo copy differs only in CRLF line endings: no 'exists' error, the
    local LF copy is kept as is, and the sidecar still syncs."""
    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'data' / 'shared-plugins' / 'minqlx'
    pool.mkdir(parents=True)
    (pool / 'balance.py').write_bytes(b'import minqlx\nprint("same")\n')

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(200, b'{"label": "Balance"}')
        return FakeResponse(200, b'import minqlx\r\nprint("same")\r\n')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'balance.py', 'minqlx')
    assert (pool / 'balance.py').read_bytes() == b'import minqlx\nprint("same")\n'
    assert (pool / 'balance.ql-plugin.json').read_bytes() == b'{"label": "Balance"}'


def test_download_plugin_overwrite_true_replaces_the_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'data' / 'shared-plugins' / 'minqlx'
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
    pool = tmp_path / 'data' / 'shared-plugins' / 'minqlx'
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


def test_download_plugin_writes_inline_manifest_when_repo_has_no_sidecar(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(404, b'')
        return FakeResponse(200, b'print("hello")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    inline = {'label': 'Demo', 'cvars': [{'cvar': 'qlx_demo', 'type': 'bool', 'default': False}]}
    download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlx', inline_manifest=inline)

    manifest_path = tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'demo_plugin.ql-plugin.json'
    assert json.loads(manifest_path.read_text()) == inline


def test_download_plugin_separate_sidecar_wins_over_inline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(200, b'{"label": "From sidecar"}')
        return FakeResponse(200, b'print("hello")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlx',
                    inline_manifest={'label': 'From inline'})

    manifest_path = tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'demo_plugin.ql-plugin.json'
    assert manifest_path.read_text() == '{"label": "From sidecar"}'


@pytest.mark.parametrize('bad_sidecar', [b'not json', b'[]', b'"oops"'])
def test_download_plugin_unusable_sidecar_falls_back_to_inline(tmp_path, monkeypatch, bad_sidecar):
    # Invalid JSON, or valid JSON that is not an object: the pool reader
    # (load_manifest_file) would reject either, so inline must win instead.
    monkeypatch.chdir(tmp_path)

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(200, bad_sidecar)
        return FakeResponse(200, b'print("hello")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlx',
                    inline_manifest={'label': 'From inline'})

    manifest_path = tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'demo_plugin.ql-plugin.json'
    assert json.loads(manifest_path.read_text()) == {'label': 'From inline'}


def test_download_plugin_inline_manifest_at_the_cap_is_written_within_the_cap(tmp_path, monkeypatch):
    # build_inline_manifest() measures compact JSON; the file written must be
    # the same bytes, otherwise load_manifest_file() (which checks on-disk
    # size against PLUGIN_MANIFEST_MAX_SIZE) silently ignores the sidecar.
    # Many small cvars make the indented form far larger than the compact one.
    monkeypatch.chdir(tmp_path)
    inline = {
        'label': 'Big',
        'cvars': [{'cvar': f'qlx_v{i}', 'type': 'bool', 'default': False} for i in range(200)],
        'description': '',
    }
    padding = PLUGIN_MANIFEST_MAX_SIZE - len(json.dumps(inline).encode('utf-8'))
    inline['description'] = 'x' * padding
    assert len(json.dumps(inline).encode('utf-8')) == PLUGIN_MANIFEST_MAX_SIZE  # precondition
    assert build_inline_manifest({'filename': 'demo_plugin.py', **inline}) == inline

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(404, b'')
        return FakeResponse(200, b'print("hello")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'demo_plugin.py', 'minqlx', inline_manifest=inline)

    manifest_path = tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'demo_plugin.ql-plugin.json'
    assert os.path.getsize(manifest_path) <= PLUGIN_MANIFEST_MAX_SIZE
    assert json.loads(manifest_path.read_text()) == inline


# --- github.com URL resolution ---

def test_github_raw_bases_tries_both_default_branches():
    assert plugin_repositories.github_raw_bases('https://github.com/D00MSDAYDEVICE/minqlx') == [
        'https://raw.githubusercontent.com/D00MSDAYDEVICE/minqlx/main/',
        'https://raw.githubusercontent.com/D00MSDAYDEVICE/minqlx/master/',
    ]


def test_github_raw_bases_accepts_trailing_slash_and_git_suffix():
    expected = 'https://raw.githubusercontent.com/owner/repo/main/'
    for url in ('https://github.com/owner/repo/', 'https://github.com/owner/repo.git',
                'http://www.github.com/owner/repo'):
        assert plugin_repositories.github_raw_bases(url)[0] == expected


def test_github_raw_bases_uses_the_branch_and_subfolder_in_the_url():
    assert plugin_repositories.github_raw_bases('https://github.com/owner/repo/tree/dev/plugins') == [
        'https://raw.githubusercontent.com/owner/repo/dev/plugins/',
    ]


def test_github_raw_bases_ignores_other_urls():
    assert plugin_repositories.github_raw_bases('https://example.com/plugins/') == []
    assert plugin_repositories.github_raw_bases(
        'https://raw.githubusercontent.com/owner/repo/main/') == []


def test_resolve_manifest_source_falls_through_to_the_second_branch():
    tried = []

    def fake_fetch(url):
        tried.append(url)
        if '/main/' in url:
            raise plugin_repositories.PluginRepositoryError('404')
        return [{'filename': 'a.py'}]

    fetch_url, plugins = plugin_repositories.resolve_manifest_source(
        'https://github.com/owner/repo', fake_fetch)
    assert fetch_url == 'https://raw.githubusercontent.com/owner/repo/master/'
    assert plugins == [{'filename': 'a.py'}]
    assert len(tried) == 2


def test_resolve_manifest_source_reports_both_branches_when_neither_has_a_manifest():
    def fake_fetch(url):
        raise plugin_repositories.PluginRepositoryError('404')

    with pytest.raises(plugin_repositories.PluginRepositoryError) as excinfo:
        plugin_repositories.resolve_manifest_source('https://github.com/owner/repo', fake_fetch)
    assert 'main or master' in str(excinfo.value)


def test_resolve_manifest_source_leaves_a_plain_url_alone():
    fetch_url, _ = plugin_repositories.resolve_manifest_source(
        'https://example.com/plugins/', lambda url: [])
    assert fetch_url == 'https://example.com/plugins/'


# --- is_safe_plugin_filename / fetch_plugin_source ---

@pytest.mark.parametrize('name, expected', [
    ('autokick.py', True),
    ('my-plugin_2.py', True),
    ('../autokick.py', False),
    ('sub/autokick.py', False),
    ('autokick.txt', False),
    ('', False),
    (None, False),
])
def test_is_safe_plugin_filename(name, expected):
    assert is_safe_plugin_filename(name) is expected


# --- download_addon ---

def _addon_entry(**overrides):
    entry = {'id': 'demo-addon', 'zip': 'demo-addon.zip', 'version': '1.2.0',
             'sha256': None, 'label': None, 'description': None,
             'requires_qlsm_version': None}
    entry.update(overrides)
    return entry


def test_download_addon_installs_the_package(tmp_path, monkeypatch):
    blob = make_addon_zip(extra_files={'backend.py': 'def register(ctx): pass'})
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, blob),
    )
    packages_dir = tmp_path / 'addon-packages'
    manifest = download_addon('https://example.com/repo', _addon_entry(), str(packages_dir))
    assert manifest['id'] == 'demo-addon'
    assert manifest['version'] == '1.2.0'
    assert (packages_dir / 'demo-addon' / 'qlsm-addon.json').is_file()
    assert (packages_dir / 'demo-addon' / 'backend.py').is_file()


def test_download_addon_verifies_a_declared_sha256(tmp_path, monkeypatch):
    blob = make_addon_zip()
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, blob),
    )
    packages_dir = tmp_path / 'addon-packages'

    entry = _addon_entry(sha256=hashlib.sha256(blob).hexdigest())
    download_addon('https://example.com/repo', entry, str(packages_dir))
    assert (packages_dir / 'demo-addon' / 'qlsm-addon.json').is_file()

    with pytest.raises(PluginRepositoryError, match='sha256'):
        download_addon('https://example.com/repo', _addon_entry(sha256='b' * 64), str(packages_dir))


def test_download_addon_rejects_an_id_mismatch_without_installing(tmp_path, monkeypatch):
    blob = make_addon_zip(addon_id='something-else')
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, blob),
    )
    packages_dir = tmp_path / 'addon-packages'
    with pytest.raises(PluginRepositoryError, match='something-else'):
        download_addon('https://example.com/repo', _addon_entry(), str(packages_dir))
    assert not (packages_dir / 'something-else').exists()
    assert not (packages_dir / 'demo-addon').exists()


def test_download_addon_rejects_a_broken_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, b'not a zip'),
    )
    with pytest.raises(PluginRepositoryError, match='not a valid addon package'):
        download_addon('https://example.com/repo', _addon_entry(), str(tmp_path / 'addon-packages'))


def test_download_addon_installing_over_an_existing_copy_is_the_update(tmp_path, monkeypatch, app_context):
    packages_dir = tmp_path / 'addon-packages'
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, make_addon_zip(version='1.0.0')),
    )
    download_addon('https://example.com/repo', _addon_entry(), str(packages_dir))

    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, make_addon_zip(version='2.0.0')),
    )
    manifest = download_addon('https://example.com/repo', _addon_entry(), str(packages_dir))
    assert manifest['version'] == '2.0.0'
    installed = json.loads((packages_dir / 'demo-addon' / 'qlsm-addon.json').read_text())
    assert installed['version'] == '2.0.0'


# --- plugin_update_status ---

def _plugin_entry(**overrides):
    entry = {'filename': 'demo_plugin.py', 'label': None, 'description': None,
             'runtime': 'minqlx', 'version': None, 'sha256': None,
             'requires_qlsm_version': None, 'depends_on': []}
    entry.update(overrides)
    return entry


def test_plugin_update_status_by_pool_hash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'data' / 'shared-plugins' / 'minqlx'
    pool.mkdir(parents=True)
    # CRLF on disk vs the LF-normalized hash in the manifest: still up to
    # date, matching download_plugin()'s own CRLF-insensitive comparison.
    (pool / 'demo_plugin.py').write_bytes(b'print("hello")\r\n')
    matching = hashlib.sha256(b'print("hello")\n').hexdigest()

    assert plugin_update_status(_plugin_entry(sha256=matching)) == 'up_to_date'
    assert plugin_update_status(_plugin_entry(sha256='c' * 64)) == 'update_available'
    assert plugin_update_status(_plugin_entry(sha256=None)) == 'unknown'
    assert plugin_update_status(_plugin_entry(filename='absent.py', sha256=matching)) == 'not_installed'
    assert plugin_update_status(_plugin_entry(runtime=None, sha256=matching)) == 'unknown'


# --- depends_on: hiding helpers and pulling them in ---

def test_fetch_manifest_normalizes_depends_on(monkeypatch):
    manifest = {'plugins': [
        {'filename': 'chat_rcon.py',
         'depends_on': ['chat_rcon_acl.py', ' chat_rcon_acl.py ', 'has/slash.py', 42, None]},
        {'filename': 'chat_rcon_acl.py'},
        {'filename': 'plain.py', 'depends_on': 'not-a-list'},
    ]}
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, json.dumps(manifest).encode()),
    )
    plugins = fetch_manifest('https://example.com/repo')['plugins']
    # Whitespace trimmed, duplicate collapsed, unsafe/non-string entries dropped.
    assert plugins[0]['depends_on'] == ['chat_rcon_acl.py']
    assert plugins[1]['depends_on'] == []
    assert plugins[2]['depends_on'] == []


def test_build_inline_manifest_carries_depends_on_into_the_sidecar():
    # The pool sidecar is what makes the Plugins tab hide the same helper from
    # its own checkbox list, so it has to travel with the download.
    entry = {'filename': 'chat_rcon.py', 'label': 'Chat RCON',
             'depends_on': ['chat_rcon_acl.py']}
    assert build_inline_manifest(entry) == {
        'label': 'Chat RCON', 'depends_on': ['chat_rcon_acl.py'],
    }
    assert build_inline_manifest({'filename': 'plain.py', 'depends_on': []}) is None


def test_dependency_filenames_only_counts_published_entries():
    plugins = [
        _plugin_entry(filename='chat_rcon.py', depends_on=['chat_rcon_acl.py', 'absent.py']),
        _plugin_entry(filename='chat_rcon_acl.py'),
        _plugin_entry(filename='self_ref.py', depends_on=['self_ref.py']),
    ]
    # 'absent.py' isn't in the repo, so there's no row to hide and nothing to
    # download; a self-reference must not hide its own row.
    assert dependency_filenames(plugins) == {'chat_rcon_acl.py'}


def test_expand_with_dependencies_is_transitive_and_dependency_first():
    plugins = [
        _plugin_entry(filename='top.py', depends_on=['mid.py']),
        _plugin_entry(filename='mid.py', depends_on=['leaf.py']),
        _plugin_entry(filename='leaf.py'),
        _plugin_entry(filename='unrelated.py'),
    ]
    ordered, pulled_by = expand_with_dependencies(plugins, ['top.py'])
    assert ordered == ['leaf.py', 'mid.py', 'top.py']
    # Each helper remembers who dragged it in -- the route needs that to give
    # a runtime-less helper the runtime of its puller.
    assert pulled_by == {'mid.py': 'top.py', 'leaf.py': 'mid.py'}


def test_expand_with_dependencies_does_not_mark_an_explicit_pick_as_auto():
    plugins = [
        _plugin_entry(filename='top.py', depends_on=['helper.py']),
        _plugin_entry(filename='helper.py'),
    ]
    ordered, pulled_by = expand_with_dependencies(plugins, ['top.py', 'helper.py'])
    assert sorted(ordered) == ['helper.py', 'top.py']
    assert pulled_by == {}


def test_expand_with_dependencies_survives_a_cycle_and_unknown_names():
    plugins = [
        _plugin_entry(filename='a.py', depends_on=['b.py']),
        _plugin_entry(filename='b.py', depends_on=['a.py']),
    ]
    ordered, pulled_by = expand_with_dependencies(plugins, ['a.py', 'nowhere.py'])
    assert set(ordered) == {'a.py', 'b.py', 'nowhere.py'}
    assert pulled_by == {'b.py': 'a.py'}


def test_plugin_update_status_with_dependencies_folds_in_a_stale_helper(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'data' / 'shared-plugins' / 'minqlx'
    pool.mkdir(parents=True)
    (pool / 'top.py').write_bytes(b'top')
    (pool / 'helper.py').write_bytes(b'old helper')
    top = _plugin_entry(filename='top.py', depends_on=['helper.py'],
                        sha256=hashlib.sha256(b'top').hexdigest())
    fresh_helper = _plugin_entry(filename='helper.py',
                                 sha256=hashlib.sha256(b'old helper').hexdigest())
    stale_helper = _plugin_entry(filename='helper.py', sha256='d' * 64)

    assert plugin_update_status_with_dependencies([top, fresh_helper], top) == 'up_to_date'
    assert plugin_update_status_with_dependencies([top, stale_helper], top) == 'update_available'
    # The plugin's own absence outranks anything its helper is doing.
    missing_top = _plugin_entry(filename='absent.py', depends_on=['helper.py'], sha256='e' * 64)
    assert plugin_update_status_with_dependencies(
        [missing_top, stale_helper], missing_top) == 'not_installed'


# --- package_files: folder-style plugin entries ---

def test_fetch_manifest_normalizes_package_files(monkeypatch):
    good_sha = 'a' * 64
    manifest = {'plugins': [
        {'filename': 'match_restore.py', 'package_files': {
            'restore/__init__.py': good_sha.upper(),
            'restore/codec.py': good_sha,
            'no_subdir.py': good_sha,        # rejected: not under a subdirectory
            'restore/../evil.py': good_sha,  # rejected: escapes via ..
            'restore/bad.py': 'not-a-hash',  # rejected: not a valid sha256
        }},
    ]}
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, json.dumps(manifest).encode()),
    )
    plugins = fetch_manifest('https://example.com/repo')['plugins']
    assert plugins[0]['package_files'] == {
        'restore/__init__.py': good_sha,
        'restore/codec.py': good_sha,
    }


def test_fetch_manifest_drops_oversized_package_files_entirely(monkeypatch):
    huge = {f'restore/f{i}.py': 'a' * 64 for i in range(plugin_repositories.PACKAGE_MAX_FILES + 1)}
    manifest = {'plugins': [{'filename': 'match_restore.py', 'package_files': huge}]}
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, json.dumps(manifest).encode()),
    )
    plugins = fetch_manifest('https://example.com/repo')['plugins']
    # A partial member list would ship a broken package, so the whole field
    # is dropped rather than truncated.
    assert plugins[0]['package_files'] == {}


@pytest.mark.parametrize('path, expected', [
    ('restore/codec.py', True),
    ('restore/sub/deep.py', True),
    ('bare.py', False),
    ('../evil.py', False),
    ('restore/../evil.py', False),
    ('/etc/passwd', False),
    ('restore/.hidden.py', False),
    ('C:/restore/codec.py', False),
    ('restore/bad name.py', False),
    ('', False),
    (None, False),
])
def test_is_safe_package_relpath(path, expected):
    assert is_safe_package_relpath(path) is expected


def test_download_plugin_writes_package_files_alongside_the_main_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(404, b'')
        if url.endswith('restore/__init__.py'):
            return FakeResponse(200, b'')
        if url.endswith('restore/codec.py'):
            return FakeResponse(200, b'def encode(): pass')
        return FakeResponse(200, b'import restore')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin(
        'https://example.com/repo', 'match_restore.py', 'minqlx',
        package_files={'restore/__init__.py': 'x', 'restore/codec.py': 'y'},
    )

    pool = tmp_path / 'data' / 'shared-plugins' / 'minqlx'
    assert (pool / 'match_restore.py').read_bytes() == b'import restore'
    assert (pool / 'restore' / '__init__.py').read_bytes() == b''
    assert (pool / 'restore' / 'codec.py').read_bytes() == b'def encode(): pass'


def test_download_plugin_rejects_unsafe_package_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not fetch anything')),
    )
    for bad in ('../evil.py', 'bare.py', '/abs/path.py', 'restore/../evil.py'):
        with pytest.raises(PluginRepositoryError):
            download_plugin('https://example.com/repo', 'match_restore.py', 'minqlx',
                            package_files={bad: 'x'})


def test_download_plugin_package_conflict_names_every_conflicting_path_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    restore = tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'restore'
    restore.mkdir(parents=True)
    (restore / 'codec.py').write_text('old codec')
    # match_restore.py itself was never downloaded -- only this one member exists.

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(404, b'')
        if url.endswith('restore/codec.py'):
            return FakeResponse(200, b'new codec')
        if url.endswith('restore/__init__.py'):
            return FakeResponse(200, b'')
        return FakeResponse(200, b'import restore')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    with pytest.raises(PluginRepositoryError) as excinfo:
        download_plugin(
            'https://example.com/repo', 'match_restore.py', 'minqlx',
            package_files={'restore/__init__.py': 'x', 'restore/codec.py': 'y'},
        )
    assert excinfo.value.code == 'exists'
    assert 'restore/codec.py' in str(excinfo.value)
    # All-or-nothing: the member that WOULD have been new is not written either.
    assert not (tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'match_restore.py').exists()
    assert not (restore / '__init__.py').exists()
    assert (restore / 'codec.py').read_text() == 'old codec'


def test_download_plugin_package_overwrite_true_replaces_changed_members(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    restore = tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'restore'
    restore.mkdir(parents=True)
    (restore / 'codec.py').write_text('old codec')

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(404, b'')
        if url.endswith('restore/codec.py'):
            return FakeResponse(200, b'new codec')
        if url.endswith('restore/__init__.py'):
            return FakeResponse(200, b'')
        return FakeResponse(200, b'import restore')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin(
        'https://example.com/repo', 'match_restore.py', 'minqlx', overwrite=True,
        package_files={'restore/__init__.py': 'x', 'restore/codec.py': 'y'},
    )
    assert (restore / 'codec.py').read_text() == 'new codec'
    assert (restore / '__init__.py').read_bytes() == b''
    assert (tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'match_restore.py').read_bytes() == b'import restore'


def test_package_update_status_is_crlf_insensitive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    restore = tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'restore'
    restore.mkdir(parents=True)
    (restore / 'codec.py').write_bytes(b'def encode(): pass\r\n')
    declared = hashlib.sha256(b'def encode(): pass\n').hexdigest()
    assert package_update_status('minqlx', {'restore/codec.py': declared}) == 'up_to_date'


def test_package_update_status_missing_or_stale_member_is_an_update():
    assert package_update_status('minqlx', {}) == 'up_to_date'
    assert package_update_status('minqlx', {'restore/codec.py': 'a' * 64}) == 'update_available'


def test_plugin_update_status_folds_in_package_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'data' / 'shared-plugins' / 'minqlx'
    restore = pool / 'restore'
    restore.mkdir(parents=True)
    (pool / 'match_restore.py').write_bytes(b'import restore\n')
    (restore / 'codec.py').write_bytes(b'def encode(): pass\n')

    main_sha = hashlib.sha256(b'import restore\n').hexdigest()
    codec_sha = hashlib.sha256(b'def encode(): pass\n').hexdigest()

    up_to_date = _plugin_entry(filename='match_restore.py', sha256=main_sha,
                               package_files={'restore/codec.py': codec_sha})
    assert plugin_update_status(up_to_date) == 'up_to_date'

    stale_member = _plugin_entry(filename='match_restore.py', sha256=main_sha,
                                 package_files={'restore/codec.py': 'c' * 64})
    assert plugin_update_status(stale_member) == 'update_available'

    missing_member = _plugin_entry(filename='match_restore.py', sha256=main_sha,
                                   package_files={'restore/codec.py': codec_sha,
                                                  'restore/draft.py': 'd' * 64})
    assert plugin_update_status(missing_member) == 'update_available'

    # The main file itself missing still outranks package_files -- there is
    # nothing installed to be "up to date" at all.
    absent_main = _plugin_entry(filename='absent.py', sha256=main_sha,
                                package_files={'restore/codec.py': codec_sha})
    assert plugin_update_status(absent_main) == 'not_installed'


# --- addon_update_status ---

def _install_addon(packages_dir, addon_id='demo-addon', version='1.0.0'):
    target = packages_dir / addon_id
    target.mkdir(parents=True)
    (target / 'qlsm-addon.json').write_text(json.dumps({'id': addon_id, 'version': version}))


def test_addon_update_status_compares_versions(tmp_path):
    _install_addon(tmp_path, version='1.0.0')

    newer = addon_update_status(_addon_entry(version='1.1.0'), str(tmp_path))
    assert newer['status'] == 'update_available'
    assert newer['installed_version'] == '1.0.0'
    assert newer['available_version'] == '1.1.0'

    assert addon_update_status(_addon_entry(version='1.0.0'), str(tmp_path))['status'] == 'up_to_date'
    # An older repo copy is not an "update" -- installing it would downgrade.
    assert addon_update_status(_addon_entry(version='0.9.0'), str(tmp_path))['status'] == 'up_to_date'


def test_addon_update_status_not_installed_and_unknown(tmp_path):
    assert addon_update_status(_addon_entry(), str(tmp_path))['status'] == 'not_installed'
    assert addon_update_status(_addon_entry(), None)['status'] == 'unknown'

    _install_addon(tmp_path)
    assert addon_update_status(_addon_entry(version=None), str(tmp_path))['status'] == 'unknown'


def test_addon_update_status_unparseable_versions_compare_as_strings(tmp_path):
    _install_addon(tmp_path, version='2026-09-17')
    assert addon_update_status(_addon_entry(version='2026-09-17'), str(tmp_path))['status'] == 'up_to_date'
    assert addon_update_status(_addon_entry(version='2026-09-18'), str(tmp_path))['status'] == 'update_available'


def test_fetch_plugin_source_fetches_the_file_under_the_base_url(monkeypatch):
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        return FakeResponse(200, b'print("repo")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    assert fetch_plugin_source('https://example.com/repo/', 'demo.py') == b'print("repo")'
    assert calls == ['https://example.com/repo/demo.py']


def test_fetch_plugin_source_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(plugin_repositories.requests, 'get', lambda url, timeout: FakeResponse(404, b''))
    with pytest.raises(PluginRepositoryError, match='HTTP 404'):
        fetch_plugin_source('https://example.com/repo', 'demo.py')


def test_download_plugin_refuses_to_shadow_a_built_in_plugin(tmp_path, monkeypatch):
    """A repo plugin sharing a name with a bundled one hits the same 'exists'
    prompt as an earlier download, and nothing is written to either tier."""
    monkeypatch.chdir(tmp_path)
    builtin = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    builtin.mkdir(parents=True)
    (builtin / 'balance.py').write_text('# bundled copy')

    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, b'print("repo copy")'),
    )
    with pytest.raises(PluginRepositoryError) as excinfo:
        download_plugin('https://example.com/repo', 'balance.py', 'minqlx')
    assert excinfo.value.code == 'exists'
    assert (builtin / 'balance.py').read_text() == '# bundled copy'
    assert not (tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'balance.py').exists()


def test_download_plugin_overwrite_shadows_the_built_in_without_touching_it(tmp_path, monkeypatch):
    """overwrite=True writes the operator copy; the image's built-in file is
    never modified."""
    monkeypatch.chdir(tmp_path)
    builtin = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    builtin.mkdir(parents=True)
    (builtin / 'balance.py').write_text('# bundled copy')

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(404, b'')
        return FakeResponse(200, b'print("repo copy")')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'balance.py', 'minqlx', overwrite=True)

    operator = tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'balance.py'
    assert operator.read_bytes() == b'print("repo copy")'
    assert (builtin / 'balance.py').read_text() == '# bundled copy'


def test_download_plugin_matching_built_in_is_left_alone(tmp_path, monkeypatch):
    """Same code as the bundled copy: no prompt and no operator copy either,
    so the built-in keeps receiving release updates."""
    monkeypatch.chdir(tmp_path)
    builtin = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    builtin.mkdir(parents=True)
    (builtin / 'balance.py').write_bytes(b'print("same")\n')

    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200 if url.endswith('.py') else 404, b'print("same")\r\n' if url.endswith('.py') else b''),
    )
    download_plugin('https://example.com/repo', 'balance.py', 'minqlx')
    assert not (tmp_path / 'data' / 'shared-plugins' / 'minqlx' / 'balance.py').exists()


def test_download_plugin_matching_built_in_writes_no_orphan_sidecar(tmp_path, monkeypatch):
    """The repo ships a sidecar for a plugin whose code matches the bundled
    copy. Nothing may land in the operator tier: an orphan sidecar there
    would shadow the built-in one and hide every later release's update."""
    monkeypatch.chdir(tmp_path)
    builtin = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    builtin.mkdir(parents=True)
    (builtin / 'balance.py').write_bytes(b'print("same")\n')
    (builtin / 'balance.ql-plugin.json').write_text('{"label": "Bundled"}')

    def fake_get(url, timeout):
        if url.endswith('.ql-plugin.json'):
            return FakeResponse(200, b'{"label": "Repo"}')
        return FakeResponse(200, b'print("same")\r\n')

    monkeypatch.setattr(plugin_repositories.requests, 'get', fake_get)
    download_plugin('https://example.com/repo', 'balance.py', 'minqlx',
                    inline_manifest={'label': 'Inline'})

    assert not (tmp_path / 'data' / 'shared-plugins').exists()
    assert (builtin / 'balance.ql-plugin.json').read_text() == '{"label": "Bundled"}'


def test_download_plugin_refused_download_creates_no_operator_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    builtin = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    builtin.mkdir(parents=True)
    (builtin / 'balance.py').write_text('# bundled copy')
    monkeypatch.setattr(
        plugin_repositories.requests, 'get',
        lambda url, timeout: FakeResponse(200, b'print("repo copy")'),
    )
    with pytest.raises(PluginRepositoryError):
        download_plugin('https://example.com/repo', 'balance.py', 'minqlx')
    assert not (tmp_path / 'data' / 'shared-plugins').exists()
