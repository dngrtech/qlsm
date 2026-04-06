import json
import pytest
from unittest.mock import MagicMock
from flask_jwt_extended import create_access_token
from ui import create_app, db


@pytest.fixture
def status_app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'JWT_SECRET_KEY': 'test-secret',
        'JWT_TOKEN_LOCATION': ['headers'],
        'JWT_COOKIE_CSRF_PROTECT': False,
    })
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture
def status_client(status_app):
    return status_app.test_client()


@pytest.fixture
def auth_headers(status_app):
    with status_app.app_context():
        token = create_access_token(identity='testuser')
    return {'Authorization': f'Bearer {token}'}


def test_server_status_requires_auth(status_client):
    response = status_client.get('/api/server-status')
    assert response.status_code == 401


def test_server_status_empty_when_no_redis_data(status_app, status_client, auth_headers):
    mock_redis = MagicMock()
    mock_redis.keys.return_value = []
    # Blocklist check calls redis.get("jwt_blocklist:<jti>") — must return None (not blocked)
    mock_redis.get.return_value = None
    status_app.extensions['redis'] = mock_redis

    response = status_client.get('/api/server-status', headers=auth_headers)

    assert response.status_code == 200
    assert response.json['data'] == {}


def test_server_status_returns_cached_data(status_app, status_client, auth_headers):
    payload = {'map': 'campgrounds', 'players': [], 'maxplayers': 16, 'state': 'warmup'}
    mock_redis = MagicMock()
    mock_redis.keys.return_value = ['server:status:1:5']
    # Return None for blocklist check, payload JSON for status key
    mock_redis.get.side_effect = lambda key: None if key.startswith('jwt_blocklist:') else json.dumps(payload)
    status_app.extensions['redis'] = mock_redis

    response = status_client.get('/api/server-status', headers=auth_headers)

    assert response.status_code == 200
    data = response.json['data']
    assert '5' in data
    assert data['5']['map'] == 'campgrounds'


def test_server_status_handles_expired_key(status_app, status_client, auth_headers):
    """Key found via KEYS but expired before GET — returns null for that instance."""
    mock_redis = MagicMock()
    mock_redis.keys.return_value = ['server:status:1:5']
    mock_redis.get.return_value = None  # Expired between KEYS and GET
    status_app.extensions['redis'] = mock_redis

    response = status_client.get('/api/server-status', headers=auth_headers)

    assert response.status_code == 200
    assert response.json['data']['5'] is None


def test_server_status_no_redis_returns_empty(status_app, status_client, auth_headers):
    """If Redis unavailable, endpoint returns empty data gracefully."""
    status_app.extensions.pop('redis', None)

    response = status_client.get('/api/server-status', headers=auth_headers)

    assert response.status_code == 200
    assert response.json['data'] == {}


def test_workshop_preview_requires_auth(status_client):
    response = status_client.get('/api/server-status/workshop-preview/2358556636')
    assert response.status_code == 401


def test_workshop_preview_invalid_id_returns_400(status_app, status_client, auth_headers):
    response = status_client.get('/api/server-status/workshop-preview/not-numeric', headers=auth_headers)
    assert response.status_code == 400
    assert response.json['error']['message'] == 'workshop_id must be numeric'


def test_workshop_preview_rate_limited(status_app, status_client, auth_headers, monkeypatch):
    status_app.extensions.pop('redis', None)
    preview_url = 'https://images.steamusercontent.com/ugc/example.jpg'

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                'response': {
                    'publishedfiledetails': [
                        {'preview_url': preview_url}
                    ]
                }
            }

    import ui.routes.server_status_routes as server_status_routes
    monkeypatch.setattr(server_status_routes.requests, 'post', lambda *args, **kwargs: FakeResponse())
    max_requests = int(server_status_routes.WORKSHOP_PREVIEW_RATE_LIMIT.split(' ')[0])

    for _ in range(max_requests):
        response = status_client.get('/api/server-status/workshop-preview/2358556636', headers=auth_headers)
        assert response.status_code == 200

    response = status_client.get('/api/server-status/workshop-preview/2358556636', headers=auth_headers)
    assert response.status_code == 429


def test_workshop_preview_no_redis_fetches_steam(status_app, status_client, auth_headers, monkeypatch):
    status_app.extensions.pop('redis', None)
    preview_url = 'https://images.steamusercontent.com/ugc/example.jpg'

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                'response': {
                    'publishedfiledetails': [
                        {'preview_url': preview_url}
                    ]
                }
            }

    import ui.routes.server_status_routes as server_status_routes
    monkeypatch.setattr(server_status_routes.requests, 'post', lambda *args, **kwargs: FakeResponse())

    response = status_client.get('/api/server-status/workshop-preview/2358556636', headers=auth_headers)

    assert response.status_code == 200
    assert response.json['data']['workshop_id'] == '2358556636'
    assert response.json['data']['preview_url'] == preview_url
    assert response.json['data']['source'] == 'steam'


def test_workshop_preview_cache_hit_returns_url(status_app, status_client, auth_headers, monkeypatch):
    cache_key = 'steam:workshop:preview:2358556636'
    preview_url = 'https://images.steamusercontent.com/ugc/example.jpg'
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: None if key.startswith('jwt_blocklist:') else (
        preview_url if key == cache_key else None
    )
    status_app.extensions['redis'] = mock_redis

    import ui.routes.server_status_routes as server_status_routes
    steam_post = MagicMock()
    monkeypatch.setattr(server_status_routes.requests, 'post', steam_post)

    response = status_client.get('/api/server-status/workshop-preview/2358556636', headers=auth_headers)

    assert response.status_code == 200
    assert response.json['data']['workshop_id'] == '2358556636'
    assert response.json['data']['preview_url'] == preview_url
    assert response.json['data']['source'] == 'cache'
    steam_post.assert_not_called()


def test_workshop_preview_cache_miss_fetches_steam(status_app, status_client, auth_headers, monkeypatch):
    cache_key = 'steam:workshop:preview:2358556636'
    preview_url = 'https://images.steamusercontent.com/ugc/example.jpg'
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: None if key.startswith('jwt_blocklist:') else None
    status_app.extensions['redis'] = mock_redis

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                'response': {
                    'publishedfiledetails': [
                        {'preview_url': preview_url}
                    ]
                }
            }

    import ui.routes.server_status_routes as server_status_routes
    monkeypatch.setattr(server_status_routes.requests, 'post', lambda *args, **kwargs: FakeResponse())

    response = status_client.get('/api/server-status/workshop-preview/2358556636', headers=auth_headers)

    assert response.status_code == 200
    assert response.json['data']['preview_url'] == preview_url
    assert response.json['data']['source'] == 'steam'
    mock_redis.setex.assert_called_with(cache_key, 86400, preview_url)


def test_workshop_preview_no_preview_url_returns_null(status_app, status_client, auth_headers, monkeypatch):
    cache_key = 'steam:workshop:preview:2358556636'
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: None if key.startswith('jwt_blocklist:') else None
    status_app.extensions['redis'] = mock_redis

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                'response': {
                    'publishedfiledetails': [
                        {'preview_url': ''}
                    ]
                }
            }

    import ui.routes.server_status_routes as server_status_routes
    monkeypatch.setattr(server_status_routes.requests, 'post', lambda *args, **kwargs: FakeResponse())

    response = status_client.get('/api/server-status/workshop-preview/2358556636', headers=auth_headers)

    assert response.status_code == 200
    assert response.json['data']['preview_url'] is None
    mock_redis.setex.assert_called_with(cache_key, 1800, '__none__')


def test_workshop_preview_steam_failure_returns_null(status_app, status_client, auth_headers, monkeypatch):
    cache_key = 'steam:workshop:preview:2358556636'
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: None if key.startswith('jwt_blocklist:') else None
    status_app.extensions['redis'] = mock_redis

    import ui.routes.server_status_routes as server_status_routes
    monkeypatch.setattr(
        server_status_routes.requests,
        'post',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('boom')),
    )

    response = status_client.get('/api/server-status/workshop-preview/2358556636', headers=auth_headers)

    assert response.status_code == 200
    assert response.json['data']['preview_url'] is None
    mock_redis.setex.assert_called_with(cache_key, 1800, '__none__')
