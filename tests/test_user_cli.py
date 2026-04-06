from ui import db
from ui.models import User
from tests.helpers import make_user


def test_create_default_admin_creates_flagged_user(runner, app):
    """Bootstrap admin command creates the default flagged account."""
    result = runner.invoke(args=['create-default-admin', 'admin'])

    assert result.exit_code == 0

    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        assert user is not None
        assert user.password_change_required is True
        assert user.check_password('admin')


def test_create_user_rejects_short_password(runner, app):
    """Interactive create-user enforces password policy."""
    result = runner.invoke(args=['create-user', 'shorty'], input='short\nshort\n')

    assert result.exit_code == 0
    assert 'Password must be at least 8 characters.' in result.output

    with app.app_context():
        assert User.query.filter_by(username='shorty').first() is None


def test_create_default_admin_invalid_username_fails(runner, app):
    """Bootstrap admin command should fail fast on invalid usernames."""
    result = runner.invoke(args=['create-default-admin', 'bad user'])

    assert result.exit_code == 1
    assert 'Username can only contain letters, numbers, hyphens, and underscores.' in result.output

    with app.app_context():
        assert User.query.filter_by(username='bad user').first() is None


def test_update_user_password_rejects_short_password(runner, app):
    """Interactive password reset enforces password policy."""
    make_user(app, 'existing', 'validpass1')

    result = runner.invoke(
        args=['update-user-password', 'existing'],
        input='short\nshort\n'
    )

    assert result.exit_code == 0
    assert 'Password must be at least 8 characters.' in result.output

    with app.app_context():
        user = User.query.filter_by(username='existing').first()
        assert user is not None
        assert user.check_password('validpass1')
