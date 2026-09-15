import json

import pytest
from tests.helpers import make_user, auth_headers
from ui.models import PluginRepository
from ui import db
import ui.routes.plugin_repository_routes as plugin_repository_routes
from ui.plugin_repositories import PluginRepositoryError


PLUGIN_LIST = [
    {'filename': 'balance2.py', 'label': 'Balance', 'description': None,
     'runtime': 'minqlx', 'requires_qlsm_version': None},
]


def _patch_fetch(monkeypatch, plugins=None, error=None):
    def fake_fetch_manifest(url):
        if error:
            raise PluginRepositoryError(error)
        return plugins if plugins is not None else list(PLUGIN_LIST)
    monkeypatch.setattr(plugin_repository_routes, 'fetch_manifest', fake_fetch_manifest)


def _seeded_repo(name, url, plugins=None):
    """A PluginRepository as it looks right after a real sync -- unlike a bare
    db.session.add(), this populates manifest_json, which to_dict()['plugins']
    (and the download route's lookup) reads from. Creating a repo without this
    and then asserting on its plugin list is the bug three of these tests
    originally had (caught by CI, not locally -- see commit history)."""
    repo = PluginRepository(name=name, url=url)
    repo.manifest_json = json.dumps(plugins if plugins is not None else list(PLUGIN_LIST))
    db.session.add(repo)
    db.session.commit()
    return repo


# --- GET /api/plugin-repositories/ ---

def test_list_repositories_authenticated(client, app, monkeypatch):
    _patch_fetch(monkeypatch)
    make_user(app, 'listuser1', 'password123')
    headers = auth_headers(app, 'listuser1')
    with app.app_context():
        db.session.add(PluginRepository(name='Repo A', url='https://example.com/a'))
        db.session.commit()
    response = client.get('/api/plugin-repositories/', headers=headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    assert len(data) == 1
    assert data[0]['name'] == 'Repo A'
    # Never synced -- manifest_json is unset, so the plugin list is empty.
    assert data[0]['plugins'] == []


def test_list_repositories_unauthenticated(client, app):
    response = client.get('/api/plugin-repositories/')
    assert response.status_code == 401


# --- POST /api/plugin-repositories/ ---

def test_create_repository_syncs_immediately(client, app, monkeypatch):
    _patch_fetch(monkeypatch)
    make_user(app, 'creator', 'creatorpass')
    headers = auth_headers(app, 'creator')
    response = client.post('/api/plugin-repositories/', headers=headers, json={
        'name': 'My Repo', 'url': 'https://example.com/repo',
    })
    assert response.status_code == 201
    data = response.get_json()['data']
    assert data['name'] == 'My Repo'
    assert data['last_synced_at'] is not None
    assert data['last_sync_error'] is None
    assert [p['filename'] for p in data['plugins']] == ['balance2.py']


def test_create_repository_stores_sync_error_but_still_creates(client, app, monkeypatch):
    _patch_fetch(monkeypatch, error='boom')
    make_user(app, 'creator2', 'creatorpass')
    headers = auth_headers(app, 'creator2')
    response = client.post('/api/plugin-repositories/', headers=headers, json={
        'name': 'Broken Repo', 'url': 'https://example.com/broken',
    })
    assert response.status_code == 201
    data = response.get_json()['data']
    assert data['last_sync_error'] == 'boom'
    assert data['plugins'] == []


def test_create_repository_rejects_bad_url(client, app):
    make_user(app, 'creator3', 'creatorpass')
    headers = auth_headers(app, 'creator3')
    response = client.post('/api/plugin-repositories/', headers=headers, json={
        'name': 'Bad', 'url': 'not-a-url',
    })
    assert response.status_code == 400


def test_create_repository_rejects_duplicate_name(client, app, monkeypatch):
    _patch_fetch(monkeypatch)
    make_user(app, 'creator4', 'creatorpass')
    headers = auth_headers(app, 'creator4')
    client.post('/api/plugin-repositories/', headers=headers, json={
        'name': 'Dup', 'url': 'https://example.com/a',
    })
    response = client.post('/api/plugin-repositories/', headers=headers, json={
        'name': 'Dup', 'url': 'https://example.com/b',
    })
    assert response.status_code == 409


def test_create_repository_rejects_duplicate_name_ignoring_case(client, app, monkeypatch):
    _patch_fetch(monkeypatch)
    make_user(app, 'creator5', 'creatorpass')
    headers = auth_headers(app, 'creator5')
    client.post('/api/plugin-repositories/', headers=headers, json={
        'name': 'Dup', 'url': 'https://example.com/a',
    })
    response = client.post('/api/plugin-repositories/', headers=headers, json={
        'name': 'dup', 'url': 'https://example.com/b',
    })
    assert response.status_code == 409


def test_create_repository_rejects_duplicate_url_ignoring_trailing_slash(client, app, monkeypatch):
    _patch_fetch(monkeypatch)
    make_user(app, 'creator6', 'creatorpass')
    headers = auth_headers(app, 'creator6')
    client.post('/api/plugin-repositories/', headers=headers, json={
        'name': 'First', 'url': 'https://example.com/a',
    })
    response = client.post('/api/plugin-repositories/', headers=headers, json={
        'name': 'Second', 'url': 'https://example.com/a/',
    })
    assert response.status_code == 409
    assert "'First'" in response.get_json()['error']['message']


# --- POST /api/plugin-repositories/<id>/sync ---

def test_sync_updates_plugin_list(client, app, monkeypatch):
    _patch_fetch(monkeypatch)
    make_user(app, 'syncuser', 'password123')
    headers = auth_headers(app, 'syncuser')
    with app.app_context():
        repo = PluginRepository(name='Repo B', url='https://example.com/b')
        db.session.add(repo)
        db.session.commit()
        repo_id = repo.id

    _patch_fetch(monkeypatch, plugins=[
        {'filename': 'new_plugin.py', 'label': None, 'description': None,
         'runtime': None, 'requires_qlsm_version': None},
    ])
    response = client.post(f'/api/plugin-repositories/{repo_id}/sync', headers=headers)
    assert response.status_code == 200
    assert [p['filename'] for p in response.get_json()['data']['plugins']] == ['new_plugin.py']


def test_sync_missing_repo_404(client, app):
    make_user(app, 'syncuser2', 'password123')
    headers = auth_headers(app, 'syncuser2')
    response = client.post('/api/plugin-repositories/9999/sync', headers=headers)
    assert response.status_code == 404


def test_sync_reports_fetch_failure(client, app, monkeypatch):
    _patch_fetch(monkeypatch)
    make_user(app, 'syncuser3', 'password123')
    headers = auth_headers(app, 'syncuser3')
    with app.app_context():
        repo = PluginRepository(name='Repo C', url='https://example.com/c')
        db.session.add(repo)
        db.session.commit()
        repo_id = repo.id

    _patch_fetch(monkeypatch, error='unreachable')
    response = client.post(f'/api/plugin-repositories/{repo_id}/sync', headers=headers)
    assert response.status_code == 502
    assert response.get_json()['error']['message'] == 'unreachable'


# --- DELETE /api/plugin-repositories/<id> ---

def test_delete_repository(client, app, monkeypatch):
    _patch_fetch(monkeypatch)
    make_user(app, 'deluser', 'password123')
    headers = auth_headers(app, 'deluser')
    with app.app_context():
        repo = PluginRepository(name='Repo D', url='https://example.com/d')
        db.session.add(repo)
        db.session.commit()
        repo_id = repo.id

    response = client.delete(f'/api/plugin-repositories/{repo_id}', headers=headers)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(PluginRepository, repo_id) is None


# --- POST /api/plugin-repositories/<id>/download ---

def test_download_uses_the_manifests_own_runtime(client, app, monkeypatch):
    make_user(app, 'dlruntime', 'password123')
    headers = auth_headers(app, 'dlruntime')
    with app.app_context():
        repo = _seeded_repo('Repo E', 'https://example.com/e')
        repo_id = repo.id

    calls = []
    monkeypatch.setattr(
        plugin_repository_routes, 'download_plugin',
        lambda base_url, filename, runtime, overwrite=False: calls.append((base_url, filename, runtime)),
    )
    response = client.post(
        f'/api/plugin-repositories/{repo_id}/download', headers=headers,
        json={'filenames': ['balance2.py']},
    )
    assert response.status_code == 200
    assert response.get_json()['downloaded'] == ['balance2.py']
    assert calls == [('https://example.com/e', 'balance2.py', 'minqlx')]


def test_download_requires_a_runtime_when_manifest_has_none(client, app, monkeypatch):
    make_user(app, 'dlnoruntime', 'password123')
    headers = auth_headers(app, 'dlnoruntime')
    with app.app_context():
        repo = _seeded_repo('Repo F', 'https://example.com/f', plugins=[
            {'filename': 'no_runtime.py', 'label': None, 'description': None,
             'runtime': None, 'requires_qlsm_version': None},
        ])
        repo_id = repo.id

    response = client.post(
        f'/api/plugin-repositories/{repo_id}/download', headers=headers,
        json={'filenames': ['no_runtime.py']},
    )
    assert response.status_code == 502
    assert response.get_json()['downloaded'] == []
    assert response.get_json()['errors'][0]['filename'] == 'no_runtime.py'


def test_download_picked_runtime_does_not_override_declared_runtime(client, app, monkeypatch):
    make_user(app, 'dloverride', 'password123')
    headers = auth_headers(app, 'dloverride')
    with app.app_context():
        # One entry declares minqlx, the other declares nothing; a per-file
        # pick must only fill in the missing one.
        repo = _seeded_repo('Repo G', 'https://example.com/g', plugins=[
            {'filename': 'balance2.py', 'label': None, 'description': None,
             'runtime': 'minqlx', 'requires_qlsm_version': None},
            {'filename': 'no_runtime.py', 'label': None, 'description': None,
             'runtime': None, 'requires_qlsm_version': None},
        ])
        repo_id = repo.id

    calls = []
    monkeypatch.setattr(
        plugin_repository_routes, 'download_plugin',
        lambda base_url, filename, runtime, overwrite=False: calls.append((base_url, filename, runtime)),
    )
    response = client.post(
        f'/api/plugin-repositories/{repo_id}/download', headers=headers,
        json={
            'filenames': ['balance2.py', 'no_runtime.py'],
            'runtimes': {'balance2.py': 'minqlxtended', 'no_runtime.py': 'minqlxtended'},
        },
    )
    assert response.status_code == 200
    assert calls == [
        ('https://example.com/g', 'balance2.py', 'minqlx'),
        ('https://example.com/g', 'no_runtime.py', 'minqlxtended'),
    ]


def test_download_rejects_an_unknown_picked_runtime(client, app):
    make_user(app, 'dlbadpick', 'password123')
    headers = auth_headers(app, 'dlbadpick')
    with app.app_context():
        repo = _seeded_repo('Repo H', 'https://example.com/h')
        repo_id = repo.id

    response = client.post(
        f'/api/plugin-repositories/{repo_id}/download', headers=headers,
        json={'filenames': ['balance2.py'], 'runtimes': {'balance2.py': 'quake3'}},
    )
    assert response.status_code == 400


def test_download_partial_failure_returns_207(client, app, monkeypatch):
    make_user(app, 'dlpartial', 'password123')
    headers = auth_headers(app, 'dlpartial')
    with app.app_context():
        repo = _seeded_repo('Repo H', 'https://example.com/h', plugins=[
            {'filename': 'ok.py', 'label': None, 'description': None,
             'runtime': 'minqlx', 'requires_qlsm_version': None},
            {'filename': 'bad.py', 'label': None, 'description': None,
             'runtime': 'minqlx', 'requires_qlsm_version': None},
        ])
        repo_id = repo.id

    def fake_download(base_url, filename, runtime, overwrite=False):
        if filename == 'bad.py':
            raise PluginRepositoryError('download failed')

    monkeypatch.setattr(plugin_repository_routes, 'download_plugin', fake_download)
    response = client.post(
        f'/api/plugin-repositories/{repo_id}/download', headers=headers,
        json={'filenames': ['ok.py', 'bad.py']},
    )
    assert response.status_code == 207
    body = response.get_json()
    assert body['downloaded'] == ['ok.py']
    assert body['errors'][0]['filename'] == 'bad.py'


def test_download_surfaces_the_exists_code_and_overwrite_retries(client, app, monkeypatch):
    make_user(app, 'dloverwrite', 'password123')
    headers = auth_headers(app, 'dloverwrite')
    with app.app_context():
        repo = _seeded_repo('Repo I', 'https://example.com/i')
        repo_id = repo.id

    def fake_download(base_url, filename, runtime, overwrite=False):
        if not overwrite:
            raise PluginRepositoryError(f'{filename} already exists in the local pool.', code='exists')

    monkeypatch.setattr(plugin_repository_routes, 'download_plugin', fake_download)

    blocked = client.post(
        f'/api/plugin-repositories/{repo_id}/download', headers=headers,
        json={'filenames': ['balance2.py']},
    )
    assert blocked.status_code == 502
    assert blocked.get_json()['errors'][0]['code'] == 'exists'

    retried = client.post(
        f'/api/plugin-repositories/{repo_id}/download', headers=headers,
        json={'filenames': ['balance2.py'], 'overwrite': True},
    )
    assert retried.status_code == 200
    assert retried.get_json()['downloaded'] == ['balance2.py']
