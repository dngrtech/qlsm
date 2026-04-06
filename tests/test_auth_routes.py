import pytest
from tests.helpers import make_user, auth_headers
from ui import db
from ui.models import User


# --- POST /api/auth/login ---

def test_login_success(client, app):
    """Valid credentials return 200 and set JWT cookie."""
    make_user(app, 'loginuser', 'securepass1')
    response = client.post('/api/auth/login', json={
        'username': 'loginuser',
        'password': 'securepass1'
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['user']['username'] == 'loginuser'
    assert 'access_token_cookie' in response.headers.get('Set-Cookie', '')


def test_login_allows_existing_short_password(client, app):
    """Existing stored passwords should not be rejected by login policy."""
    make_user(app, 'bootstrap', 'admin')
    response = client.post('/api/auth/login', json={
        'username': 'bootstrap',
        'password': 'admin'
    })
    assert response.status_code == 200


def test_login_wrong_password(client, app):
    """Wrong password returns 401."""
    make_user(app, 'user2', 'correctpass1')
    response = client.post('/api/auth/login', json={
        'username': 'user2',
        'password': 'wrongpassword'
    })
    assert response.status_code == 401
    assert 'Invalid username or password' in response.get_json()['error']['message']


def test_login_nonexistent_user(client, app):
    """Non-existent username returns 401."""
    response = client.post('/api/auth/login', json={
        'username': 'nobody',
        'password': 'somepassword'
    })
    assert response.status_code == 401


def test_login_missing_body(client, app):
    """No valid JSON body returns 4xx error."""
    # Flask returns 415 for wrong content-type, 400 for missing JSON fields
    response = client.post('/api/auth/login', data='not json',
                           content_type='text/plain')
    assert response.status_code in (400, 415)


def test_login_missing_fields(client, app):
    """Missing username or password returns 400."""
    response = client.post('/api/auth/login', json={'username': 'user'})
    assert response.status_code == 400

    response = client.post('/api/auth/login', json={'password': 'pass'})
    assert response.status_code == 400


def test_login_invalid_username_format(client, app):
    """Username with invalid chars returns 401 (security: don't reveal why)."""
    response = client.post('/api/auth/login', json={
        'username': 'bad user!@#',
        'password': 'somepassword'
    })
    assert response.status_code == 401


def test_login_username_too_short(client, app):
    """Username shorter than 2 chars returns 401."""
    response = client.post('/api/auth/login', json={
        'username': 'a',
        'password': 'somepassword'
    })
    assert response.status_code == 401


def test_login_updates_last_login_at(client, app):
    """Successful login updates user.last_login_at timestamp."""
    make_user(app, 'tsuser', 'timestamp123')
    with app.app_context():
        user_before = User.query.filter_by(username='tsuser').first()
        before_ts = user_before.last_login_at

    client.post('/api/auth/login', json={
        'username': 'tsuser',
        'password': 'timestamp123'
    })

    with app.app_context():
        user_after = User.query.filter_by(username='tsuser').first()
        assert user_after.last_login_at is not None
        if before_ts is not None:
            assert user_after.last_login_at >= before_ts


def test_login_returns_password_change_required_flag(client, app):
    """Login response includes password change requirement state."""
    user_id = make_user(app, 'flaggeduser', 'securepass1')
    with app.app_context():
        user = db.session.get(User, user_id)
        user.password_change_required = True
        db.session.commit()

    response = client.post('/api/auth/login', json={
        'username': 'flaggeduser',
        'password': 'securepass1'
    })

    assert response.status_code == 200
    assert response.get_json()['data']['user']['passwordChangeRequired'] is True


# --- GET /api/auth/status ---

def test_auth_status_authenticated(client, app):
    """Authenticated user receives isAuthenticated=True with user info."""
    make_user(app, 'statususer', 'statuspass1')
    headers = auth_headers(app, 'statususer')
    response = client.get('/api/auth/status', headers=headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['isAuthenticated'] is True
    assert data['data']['user']['username'] == 'statususer'


def test_auth_status_returns_password_change_required_flag(client, app):
    """Auth status includes password change requirement state."""
    user_id = make_user(app, 'statusflag', 'statuspass1')
    with app.app_context():
        user = db.session.get(User, user_id)
        user.password_change_required = True
        db.session.commit()

    headers = auth_headers(app, 'statusflag')
    response = client.get('/api/auth/status', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data']['user']['passwordChangeRequired'] is True


def test_auth_status_unauthenticated(client, app):
    """No token returns 401."""
    response = client.get('/api/auth/status')
    assert response.status_code == 401


def test_auth_status_invalid_token(client, app):
    """Invalid/tampered token returns 401 or 422."""
    headers = {'Authorization': 'Bearer not.a.valid.token'}
    response = client.get('/api/auth/status', headers=headers)
    assert response.status_code in (401, 422)


# --- POST /api/auth/change-password ---

def test_change_password_success_clears_required_flag(client, app):
    """Changing password clears the forced-rotation flag."""
    user_id = make_user(app, 'bootstrap', 'admin')
    with app.app_context():
        user = db.session.get(User, user_id)
        user.password_change_required = True
        db.session.commit()

    headers = auth_headers(app, 'bootstrap')
    response = client.post('/api/auth/change-password', headers=headers, json={
        'password': 'newsecurepass1',
        'confirmPassword': 'newsecurepass1'
    })

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(username='bootstrap').first()
        assert user.password_change_required is False
        assert user.check_password('newsecurepass1')


def test_change_password_rejects_short_password(client, app):
    """Short passwords are rejected by the change-password endpoint."""
    user_id = make_user(app, 'bootstrap2', 'admin')
    with app.app_context():
        user = db.session.get(User, user_id)
        user.password_change_required = True
        db.session.commit()

    headers = auth_headers(app, 'bootstrap2')
    response = client.post('/api/auth/change-password', headers=headers, json={
        'password': 'short',
        'confirmPassword': 'short'
    })

    assert response.status_code == 400
    assert 'Password must be at least 8 characters.' in response.get_json()['error']['message']


def test_change_password_rejects_mismatched_confirmation(client, app):
    """Password confirmation must match."""
    user_id = make_user(app, 'bootstrap3', 'admin')
    with app.app_context():
        user = db.session.get(User, user_id)
        user.password_change_required = True
        db.session.commit()

    headers = auth_headers(app, 'bootstrap3')
    response = client.post('/api/auth/change-password', headers=headers, json={
        'password': 'newsecurepass1',
        'confirmPassword': 'differentpass1'
    })

    assert response.status_code == 400
    assert 'Passwords do not match.' in response.get_json()['error']['message']


def test_change_password_rejects_admin_password(client, app):
    """Bootstrap password cannot be reused as the replacement password."""
    user_id = make_user(app, 'bootstrap4', 'admin')
    with app.app_context():
        user = db.session.get(User, user_id)
        user.password_change_required = True
        db.session.commit()

    headers = auth_headers(app, 'bootstrap4')
    # 'admin' (5 chars) is rejected by the length check before reaching
    # the bootstrap password check — this is intentional to avoid leaking
    # the identity of the default password via error messages.
    response = client.post('/api/auth/change-password', headers=headers, json={
        'password': 'admin',
        'confirmPassword': 'admin'
    })

    assert response.status_code == 400
    assert 'at least 8 characters' in response.get_json()['error']['message']


# --- POST /api/auth/logout ---

def test_logout_success(client, app):
    """Authenticated user can log out successfully."""
    make_user(app, 'logoutuser', 'logoutpass1')
    headers = auth_headers(app, 'logoutuser')
    response = client.post('/api/auth/logout', headers=headers)
    assert response.status_code == 200
    data = response.get_json()
    assert 'Logout successful' in data['data']['message']


def test_logout_unauthenticated(client, app):
    """Unauthenticated logout returns 401."""
    response = client.post('/api/auth/logout')
    assert response.status_code == 401
