import pytest
from tests.helpers import make_user, auth_headers
from ui.models import User
from ui import db


# --- GET /api/users/ ---

def test_list_users_authenticated(client, app):
    """Authenticated request returns list of users."""
    make_user(app, 'listuser1', 'password123')
    headers = auth_headers(app, 'listuser1')
    response = client.get('/api/users/', headers=headers)
    assert response.status_code == 200
    data = response.get_json()
    assert 'data' in data
    assert isinstance(data['data'], list)
    usernames = [u['username'] for u in data['data']]
    assert 'listuser1' in usernames


def test_list_users_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/users/')
    assert response.status_code == 401


def test_list_users_ordered_alphabetically(client, app):
    """Users are returned in alphabetical order."""
    make_user(app, 'beta', 'betapass123')
    make_user(app, 'alpha', 'alphapass12')
    headers = auth_headers(app, 'alpha')
    response = client.get('/api/users/', headers=headers)
    assert response.status_code == 200
    usernames = [u['username'] for u in response.get_json()['data']]
    assert usernames == sorted(usernames)


# --- POST /api/users/ ---

def test_create_user_success(client, app):
    """Valid data creates a new user."""
    make_user(app, 'creator', 'creatorpass')
    headers = auth_headers(app, 'creator')
    response = client.post('/api/users/', headers=headers, json={
        'username': 'newuser',
        'password': 'newpassword1'
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data['data']['username'] == 'newuser'

    with app.app_context():
        user = User.query.filter_by(username='newuser').first()
        assert user is not None
        assert user.check_password('newpassword1')


def test_create_user_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.post('/api/users/', json={
        'username': 'hacker',
        'password': 'hackerpass1'
    })
    assert response.status_code == 401


def test_create_user_missing_body(client, app):
    """No valid JSON body returns 4xx error."""
    make_user(app, 'adminuser', 'adminpass12')
    headers = auth_headers(app, 'adminuser')
    response = client.post('/api/users/', headers=headers,
                           data='not json', content_type='text/plain')
    assert response.status_code in (400, 415)


def test_create_user_duplicate_username(client, app):
    """Duplicate username returns 409."""
    make_user(app, 'dupuser', 'duppassword')
    headers = auth_headers(app, 'dupuser')
    response = client.post('/api/users/', headers=headers, json={
        'username': 'dupuser',
        'password': 'anotherpass1'
    })
    assert response.status_code == 409
    assert 'already exists' in response.get_json()['error']['message']


def test_create_user_invalid_username_chars(client, app):
    """Username with special chars returns 400."""
    make_user(app, 'admin2', 'admin2pass1')
    headers = auth_headers(app, 'admin2')
    response = client.post('/api/users/', headers=headers, json={
        'username': 'bad user!',
        'password': 'validpass12'
    })
    assert response.status_code == 400


def test_create_user_username_too_short(client, app):
    """Username shorter than 2 chars returns 400."""
    make_user(app, 'admin3', 'admin3pass1')
    headers = auth_headers(app, 'admin3')
    response = client.post('/api/users/', headers=headers, json={
        'username': 'a',
        'password': 'validpass12'
    })
    assert response.status_code == 400


def test_create_user_password_too_short(client, app):
    """Password shorter than 8 chars returns 400."""
    make_user(app, 'admin4', 'admin4pass1')
    headers = auth_headers(app, 'admin4')
    response = client.post('/api/users/', headers=headers, json={
        'username': 'newuser2',
        'password': 'short'
    })
    assert response.status_code == 400
    assert 'Password must be at least' in response.get_json()['error']['message']


def test_create_user_password_too_long(client, app):
    """Password longer than 128 chars returns 400."""
    make_user(app, 'admin5', 'admin5pass1')
    headers = auth_headers(app, 'admin5')
    response = client.post('/api/users/', headers=headers, json={
        'username': 'newuser3',
        'password': 'a' * 129
    })
    assert response.status_code == 400


# --- PUT /api/users/<id>/password ---

def test_reset_password_success(client, app):
    """Valid password reset updates the user's password."""
    user_id = make_user(app, 'resetme', 'oldpassword1')
    make_user(app, 'resetter', 'resetterpass')
    headers = auth_headers(app, 'resetter')
    response = client.put(f'/api/users/{user_id}/password', headers=headers, json={
        'password': 'newpassword99'
    })
    assert response.status_code == 200

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.check_password('newpassword99')
        assert not user.check_password('oldpassword1')


def test_reset_password_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    user_id = make_user(app, 'resetme2', 'somepassword')
    response = client.put(f'/api/users/{user_id}/password', json={
        'password': 'newpassword99'
    })
    assert response.status_code == 401


def test_reset_password_user_not_found(client, app):
    """Non-existent user ID returns 404."""
    make_user(app, 'admin6', 'admin6pass1')
    headers = auth_headers(app, 'admin6')
    response = client.put('/api/users/99999/password', headers=headers, json={
        'password': 'newpassword99'
    })
    assert response.status_code == 404


def test_reset_password_too_short(client, app):
    """Password shorter than 8 chars returns 400."""
    user_id = make_user(app, 'resetme3', 'oldpassword3')
    make_user(app, 'admin7', 'admin7pass1')
    headers = auth_headers(app, 'admin7')
    response = client.put(f'/api/users/{user_id}/password', headers=headers, json={
        'password': 'short'
    })
    assert response.status_code == 400


def test_reset_password_no_body(client, app):
    """No valid JSON body returns 4xx error."""
    user_id = make_user(app, 'resetme4', 'oldpassword4')
    make_user(app, 'admin8', 'admin8pass1')
    headers = auth_headers(app, 'admin8')
    response = client.put(f'/api/users/{user_id}/password', headers=headers,
                          data='not json', content_type='text/plain')
    assert response.status_code in (400, 415)


# --- DELETE /api/users/<id> ---

def test_delete_user_success(client, app):
    """Admin can delete another user."""
    target_id = make_user(app, 'victim', 'victimpass1')
    make_user(app, 'deleteadmin', 'deleteadmin1')
    headers = auth_headers(app, 'deleteadmin')
    response = client.delete(f'/api/users/{target_id}', headers=headers)
    assert response.status_code == 200

    with app.app_context():
        assert db.session.get(User, target_id) is None


def test_delete_user_unauthenticated(client, app):
    """Unauthenticated delete returns 401."""
    user_id = make_user(app, 'safeu', 'safeupass12')
    response = client.delete(f'/api/users/{user_id}')
    assert response.status_code == 401


def test_delete_user_not_found(client, app):
    """Deleting non-existent user returns 404."""
    make_user(app, 'admin9', 'admin9pass1')
    headers = auth_headers(app, 'admin9')
    response = client.delete('/api/users/99999', headers=headers)
    assert response.status_code == 404


def test_delete_user_self_deletion_prevented(client, app):
    """User cannot delete their own account."""
    user_id = make_user(app, 'selfdelete', 'selfdelpass1')
    headers = auth_headers(app, 'selfdelete')
    response = client.delete(f'/api/users/{user_id}', headers=headers)
    assert response.status_code == 403
    assert 'Cannot delete your own account' in response.get_json()['error']['message']

    with app.app_context():
        assert db.session.get(User, user_id) is not None
