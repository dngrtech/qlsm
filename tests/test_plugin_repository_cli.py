import pytest

from ui import db
from ui.models import PluginRepository
import ui.routes.plugin_repository_routes as plugin_repository_routes
import ui.plugin_repository_cli as cli
from ui.plugin_repository_cli import DEFAULT_PLUGIN_REPOSITORIES
from ui.plugin_repositories import PluginRepositoryError

GITHUB_URL = 'https://github.com/D00MSDAYDEVICE/minqlx'
RAW_MAIN = 'https://raw.githubusercontent.com/D00MSDAYDEVICE/minqlx/main/'
PLUGINS = [{'filename': 'hello.py', 'label': None, 'description': None,
            'runtime': 'minqlx', 'requires_qlsm_version': None}]


@pytest.fixture(autouse=True)
def _doomsday_only(monkeypatch):
    # Most tests assume a single seeded repository; the full default list
    # is covered by test_seed_adds_every_default_repository.
    monkeypatch.setattr(cli, 'DEFAULT_PLUGIN_REPOSITORIES', DEFAULT_PLUGIN_REPOSITORIES[:1])


def _patch_fetch(monkeypatch, error=None):
    calls = []

    def fake_fetch_manifest(url):
        calls.append(url)
        if error:
            raise PluginRepositoryError(error)
        return {'plugins': [dict(p) for p in PLUGINS], 'addons': []}
    monkeypatch.setattr(plugin_repository_routes, 'fetch_manifest', fake_fetch_manifest)
    return calls


def test_seed_adds_default_repository_resolved_to_raw(runner, app, monkeypatch):
    _patch_fetch(monkeypatch)
    result = runner.invoke(args=['seed-plugin-repositories'])

    assert result.exit_code == 0
    assert DEFAULT_PLUGIN_REPOSITORIES[0][0] in result.output
    with app.app_context():
        repo = PluginRepository.query.one()
        assert repo.url == RAW_MAIN
        assert repo.display_url == GITHUB_URL
        assert repo.to_dict()['plugins'][0]['filename'] == 'hello.py'
        assert repo.last_sync_error is None


def test_seed_is_idempotent(runner, app, monkeypatch):
    _patch_fetch(monkeypatch)
    runner.invoke(args=['seed-plugin-repositories'])
    result = runner.invoke(args=['seed-plugin-repositories'])

    assert result.exit_code == 0
    assert 'already present' in result.output
    with app.app_context():
        assert PluginRepository.query.count() == 1


def test_seed_skips_repository_already_added_by_url(runner, app, monkeypatch):
    calls = _patch_fetch(monkeypatch)
    with app.app_context():
        db.session.add(PluginRepository(name='Doomsday', url=RAW_MAIN, display_url=GITHUB_URL + '/'))
        db.session.commit()

    result = runner.invoke(args=['seed-plugin-repositories'])

    assert result.exit_code == 0
    assert calls == []
    with app.app_context():
        assert PluginRepository.query.count() == 1


def test_seed_keeps_repository_when_first_sync_fails(runner, app, monkeypatch):
    _patch_fetch(monkeypatch, error='offline')
    result = runner.invoke(args=['seed-plugin-repositories'])

    assert result.exit_code == 0
    with app.app_context():
        repo = PluginRepository.query.one()
        # Left unresolved, so the Sync button retries the GitHub resolution.
        assert repo.url == GITHUB_URL
        assert repo.display_url is None
        assert repo.last_sync_error


def test_seed_adds_every_default_repository(runner, app, monkeypatch):
    monkeypatch.setattr(cli, 'DEFAULT_PLUGIN_REPOSITORIES', DEFAULT_PLUGIN_REPOSITORIES)
    _patch_fetch(monkeypatch)
    result = runner.invoke(args=['seed-plugin-repositories'])

    assert result.exit_code == 0
    with app.app_context():
        urls = {r.display_url or r.url for r in PluginRepository.query.all()}
    assert 'https://github.com/D00MSDAYDEVICE/minqlx' in urls
    assert len(urls) == len(DEFAULT_PLUGIN_REPOSITORIES) == 1
