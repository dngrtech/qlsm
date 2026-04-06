"""Shared test helpers for route test files."""
from flask_jwt_extended import create_access_token
from ui import db
from ui.models import User


def make_user(app, username, password):
    """Create a test user and return its id."""
    with app.app_context():
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def auth_headers(app, identity):
    """Return Authorization headers with a valid JWT token."""
    with app.app_context():
        token = create_access_token(identity=identity)
    return {'Authorization': f'Bearer {token}'}
