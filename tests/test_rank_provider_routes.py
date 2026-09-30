import json
from unittest.mock import MagicMock, patch

import pytest

from ui import db
from ui.models import Host, QLInstance, RankProviderConfig
from tests.helpers import auth_headers, make_user

VALID_A = '76561198000000001'


@pytest.fixture(autouse=True)
def stub_redis(app):
    """Every /ranks test in this module needs a working Redis stub.

    create_app always installs a client (ui/__init__.py:113-119) and
    redis_lib.from_url does not connect, so the key is present but unusable and
    tests/conftest.py overrides nothing. Left alone, RankService._live_gametype
    gets None back, _resolve_game_type returns None, and get_ratings returns
    ({}, True) BEFORE any adapter call — so a test that patches the adapter's
    transport passes without ever reaching it. That is exactly how
    test_a_provider_failure_is_a_200_with_empty_data would vouch for a contract
    it never exercises. It also removes a real source of nondeterminism: on a
    developer box running run-dev.sh the unstubbed client talks to live Redis.

    Follows tests/test_server_status_routes.py:41-46, the repo's precedent.
    """
    client = MagicMock()
    # A real status blob, so the derived game type is a real short code.
    client.get.side_effect = lambda key: (
        json.dumps({'gametype': 'ca', 'map': 'campgrounds', 'players': []})
        if key.startswith('server:status:') else None
    )
    client.scan_iter.return_value = []
    app.extensions['redis'] = client
    return client


def _seed():
    host = Host(name='host-a', ip_address='10.0.0.1', ssh_user='root',
                ssh_key_path='/keys/id', ssh_port=22, provider='vultr')
    db.session.add(host)
    db.session.flush()
    instance = QLInstance(name='inst-a', port=27960, hostname='hn', host_id=host.id)
    db.session.add(instance)
    db.session.commit()
    return instance.id


def _put(client, app, instance_id, payload):
    return client.put(f'/api/instances/{instance_id}/rank-provider',
                      json=payload, headers=auth_headers(app, 'adminuser'))


# --- auth -----------------------------------------------------------------

def test_every_route_requires_authentication(client, app):
    with app.app_context():
        instance_id = _seed()
    assert client.get(f'/api/instances/{instance_id}/rank-provider').status_code == 401
    assert client.put(f'/api/instances/{instance_id}/rank-provider', json={}).status_code == 401
    assert client.delete(f'/api/instances/{instance_id}/rank-provider').status_code == 401
    assert client.get(f'/api/instances/{instance_id}/ranks').status_code == 401


# --- GET / PUT / DELETE ---------------------------------------------------

def test_get_returns_null_when_unconfigured(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    response = client.get(f'/api/instances/{instance_id}/rank-provider',
                          headers=auth_headers(app, 'adminuser'))
    assert response.status_code == 200
    assert response.get_json()['data'] is None


def test_put_creates_then_get_returns_the_api_key_in_clear(client, app):
    """Masking would be this app's only masked secret, and a masked GET feeding
    a whole-object PUT overwrites the real token on the first unrelated edit."""
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    assert _put(client, app, instance_id, {
        'provider_type': 'slipgate', 'base_url': 'https://slipgate.gg/api/v1',
        'api_key': 'sgs_secret', 'enabled': True,
    }).status_code == 200
    body = client.get(f'/api/instances/{instance_id}/rank-provider',
                      headers=auth_headers(app, 'adminuser')).get_json()['data']
    assert body['api_key'] == 'sgs_secret'
    assert body['provider_type'] == 'slipgate'


def test_put_is_an_upsert(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    _put(client, app, instance_id, {'provider_type': 'slipgate',
                                    'base_url': 'https://a.example'})
    _put(client, app, instance_id, {'provider_type': 'qlstats',
                                    'base_url': 'http://b.example'})
    with app.app_context():
        rows = RankProviderConfig.query.filter_by(instance_id=instance_id).all()
        assert len(rows) == 1
        assert rows[0].provider_type == 'qlstats'


def test_put_strips_trailing_slashes_from_base_url(client, app):
    """Adapters concatenate paths onto it; a trailing slash yields // and a 404
    with no useful error."""
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    _put(client, app, instance_id, {'provider_type': 'slipgate',
                                    'base_url': 'https://slipgate.gg/api/v1///'})
    with app.app_context():
        row = RankProviderConfig.query.filter_by(instance_id=instance_id).first()
        assert row.base_url == 'https://slipgate.gg/api/v1'


def test_put_rejects_an_unknown_provider_type_and_writes_nothing(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    response = _put(client, app, instance_id, {'provider_type': 'bogus',
                                               'base_url': 'http://x.example'})
    assert response.status_code == 400
    with app.app_context():
        assert RankProviderConfig.query.count() == 0


def test_put_rejects_a_non_http_scheme(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    response = _put(client, app, instance_id, {'provider_type': 'slipgate',
                                               'base_url': 'file:///etc/passwd'})
    assert response.status_code == 400


def test_put_requires_provider_type_and_base_url(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    assert _put(client, app, instance_id, {'base_url': 'http://x.example'}).status_code == 400
    assert _put(client, app, instance_id, {'provider_type': 'slipgate'}).status_code == 400


def test_put_accepts_a_blank_game_type(client, app):
    """Blank means 'derive it', which is the normal case."""
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    assert _put(client, app, instance_id, {
        'provider_type': 'slipgate', 'base_url': 'https://slipgate.gg/api/v1',
        'game_type': '',
    }).status_code == 200


def test_put_rejects_an_over_long_base_url(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    assert _put(client, app, instance_id, {
        'provider_type': 'slipgate', 'base_url': 'http://' + 'a' * 300,
    }).status_code == 400


def test_put_persists_extra(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    _put(client, app, instance_id, {
        'provider_type': 'qlstats', 'base_url': 'http://qlstats.net',
        'extra': {'rating_system': 'elo_b'},
    })
    with app.app_context():
        row = RankProviderConfig.query.filter_by(instance_id=instance_id).first()
        assert row.extra_dict() == {'rating_system': 'elo_b'}


def test_put_rejects_a_non_string_extra_value(client, app):
    """extra is the one operator-controlled value that reaches an outbound URL.
    Rejecting non-strings also closes json.dumps of arbitrary nested data into
    an unbounded Text column."""
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    assert _put(client, app, instance_id, {
        'provider_type': 'qlstats', 'base_url': 'http://qlstats.net',
        'extra': {'rating_system': {'nested': 'object'}},
    }).status_code == 400


def test_put_rejects_an_oversized_extra_blob(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    assert _put(client, app, instance_id, {
        'provider_type': 'qlstats', 'base_url': 'http://qlstats.net',
        'extra': {'padding': 'x' * 4096},
    }).status_code == 400


def test_put_rejects_an_unknown_qlstats_rating_system(client, app):
    """base_url gets five rules and steam_ids gets a regex plus a cap for the
    same reason: the value becomes part of an outbound request. The UI only
    offers elo and elo_b, so this turns a typo's silent 404 into a clear error
    at write time."""
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    assert _put(client, app, instance_id, {
        'provider_type': 'qlstats', 'base_url': 'http://qlstats.net',
        'extra': {'rating_system': 'elo_c'},
    }).status_code == 400
    with app.app_context():
        assert RankProviderConfig.query.count() == 0


def test_put_allows_a_rating_system_key_for_a_non_qlstats_provider(client, app):
    """The rating_system rule is scoped to qlstats. extra does not get a
    per-provider schema framework for a column with one key in it."""
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    assert _put(client, app, instance_id, {
        'provider_type': 'slipgate', 'base_url': 'https://slipgate.gg/api/v1',
        'extra': {'rating_system': 'anything'},
    }).status_code == 200


def test_delete_removes_the_config(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    _put(client, app, instance_id, {'provider_type': 'slipgate',
                                    'base_url': 'https://slipgate.gg/api/v1'})
    assert client.delete(f'/api/instances/{instance_id}/rank-provider',
                         headers=auth_headers(app, 'adminuser')).status_code == 200
    with app.app_context():
        assert RankProviderConfig.query.count() == 0


def test_put_and_delete_invalidate_the_cache(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    with patch('ui.routes.rank_provider_routes.RankService.invalidate') as invalidate:
        _put(client, app, instance_id, {'provider_type': 'slipgate',
                                        'base_url': 'https://slipgate.gg/api/v1'})
        client.delete(f'/api/instances/{instance_id}/rank-provider',
                      headers=auth_headers(app, 'adminuser'))
    assert invalidate.call_count == 2


def test_unknown_instance_is_404(client, app):
    make_user(app, 'adminuser', 'password123')
    headers = auth_headers(app, 'adminuser')
    assert client.get('/api/instances/424242/rank-provider', headers=headers).status_code == 404


# --- /ranks ---------------------------------------------------------------

def test_ranks_reports_unconfigured(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    response = client.get(f'/api/instances/{instance_id}/ranks?steam_ids={VALID_A}',
                          headers=auth_headers(app, 'adminuser'))
    assert response.status_code == 200
    body = response.get_json()
    assert body['data'] == {}
    assert body['configured'] is False


def test_ranks_returns_data_and_configured(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    _put(client, app, instance_id, {'provider_type': 'slipgate',
                                    'base_url': 'https://slipgate.gg/api/v1'})
    payload = {VALID_A: {'rating': None, 'display': '1650', 'provisional': False}}
    with patch('ui.routes.rank_provider_routes.RankService.get_ratings',
               return_value=(payload, True)):
        response = client.get(f'/api/instances/{instance_id}/ranks?steam_ids={VALID_A}',
                              headers=auth_headers(app, 'adminuser'))
    body = response.get_json()
    assert body['configured'] is True
    assert body['data'][VALID_A]['display'] == '1650'


def test_a_provider_failure_is_a_200_with_empty_data(client, app):
    """Errors never propagate to the Live Status UI as a failure state.

    The stub_redis fixture is what makes this test mean anything: without a
    status blob the game type resolves to None and the request returns before
    the adapter is ever built. Assert the transport was actually reached, so
    this cannot silently go back to passing for the wrong reason.
    """
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    _put(client, app, instance_id, {'provider_type': 'slipgate',
                                    'base_url': 'https://slipgate.gg/api/v1'})
    with patch('ui.rank_providers.slipgate.requests.post',
               side_effect=Exception('down')) as post:
        response = client.get(f'/api/instances/{instance_id}/ranks?steam_ids={VALID_A}',
                              headers=auth_headers(app, 'adminuser'))
    post.assert_called_once()
    assert response.status_code == 200
    assert response.get_json()['data'] == {}


def test_ranks_works_without_redis(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    _put(client, app, instance_id, {
        'provider_type': 'elo_service', 'base_url': 'http://elo:5002',
        'game_type': 'ffa_auto',
    })
    app.extensions.pop('redis', None)
    with patch('ui.rank_providers.elo_service.requests.get') as get:
        get.return_value.status_code = 200
        get.return_value.json.return_value = {VALID_A: {'sort_score': 1800, 'mu': 25}}
        response = client.get(f'/api/instances/{instance_id}/ranks?steam_ids={VALID_A}',
                              headers=auth_headers(app, 'adminuser'))
    assert response.status_code == 200
    assert response.get_json()['data'][VALID_A]['display'] == '1800'


def test_ranks_drops_invalid_ids_before_the_adapter_sees_them(client, app):
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    _put(client, app, instance_id, {
        'provider_type': 'elo_service', 'base_url': 'http://elo:5002',
        'game_type': 'ffa_auto',
    })
    with patch('ui.rank_providers.elo_service.requests.get') as get:
        get.return_value.status_code = 200
        get.return_value.json.return_value = {}
        client.get(
            f'/api/instances/{instance_id}/ranks?steam_ids=../../admin,12345,{VALID_A}',
            headers=auth_headers(app, 'adminuser'))
    assert get.call_args[1]['params']['ids'] == VALID_A


# --- secret boundary ------------------------------------------------------

def test_the_api_key_never_appears_in_the_instance_endpoints(client, app):
    """/api/v1/instances strips a DENYLIST, so anything added to
    QLInstance.to_dict() is exposed to every external API key holder."""
    make_user(app, 'adminuser', 'password123')
    with app.app_context():
        instance_id = _seed()
    _put(client, app, instance_id, {
        'provider_type': 'slipgate', 'base_url': 'https://slipgate.gg/api/v1',
        'api_key': 'sgs_secret',
    })
    headers = auth_headers(app, 'adminuser')
    listing = client.get('/api/instances/', headers=headers)
    assert 'sgs_secret' not in listing.get_data(as_text=True)
    ranks = client.get(f'/api/instances/{instance_id}/ranks?steam_ids={VALID_A}',
                       headers=headers)
    assert 'sgs_secret' not in ranks.get_data(as_text=True)

    key = client.post('/api/settings/api-key', headers=headers).get_json()['data']['key']
    external = client.get('/api/v1/instances', headers={'Authorization': f'Bearer {key}'})
    assert external.status_code == 200
    assert 'sgs_secret' not in external.get_data(as_text=True)
