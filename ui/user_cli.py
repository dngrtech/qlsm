import click
from flask import current_app
from flask.cli import with_appcontext

from ui import db
from ui.auth_validation import validate_password, validate_username
from ui.models import User

DEFAULT_ADMIN_PASSWORD = 'admin'


def get_user_by_username(username):
    """Get a user by username."""
    return User.query.filter_by(username=username).first()


def create_default_admin(username):
    """Create the bootstrap admin user if it does not already exist."""
    username_error = validate_username(username)
    if username_error:
        return None, username_error

    username = username.strip()
    if get_user_by_username(username):
        return None, f"User '{username}' already exists."

    user = User(username=username, password_change_required=True)
    user.set_password(DEFAULT_ADMIN_PASSWORD)

    try:
        db.session.add(user)
        db.session.commit()
        return user, None
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"Error creating default admin {username}: {exc}")
        return None, f"Error creating default admin: {exc}"


@click.command('create-user')
@click.argument('username')
@with_appcontext
def create_user_command(username):
    """Create a new user with an interactive password prompt."""
    username_error = validate_username(username)
    if username_error:
        click.echo(username_error)
        return

    username = username.strip()
    if get_user_by_username(username):
        click.echo(f"Error: User '{username}' already exists.")
        return

    password = click.prompt('Password', hide_input=True, confirmation_prompt=True)
    password_error = validate_password(password)
    if password_error:
        click.echo(password_error)
        return

    new_user = User(username=username)
    new_user.set_password(password)

    try:
        db.session.add(new_user)
        db.session.commit()
        click.echo(f"User '{username}' created successfully.")
    except Exception as exc:
        db.session.rollback()
        click.echo(f"Error creating user: {exc}")
        current_app.logger.error(f"Error creating user {username}: {exc}")


@click.command('update-user-password')
@click.argument('username')
@with_appcontext
def update_user_password_command(username):
    """Update the password for an existing user."""
    user = get_user_by_username(username)
    if not user:
        click.echo(f"Error: User '{username}' not found.")
        return

    click.echo(f"Updating password for user '{username}'.")
    password = click.prompt('New password', hide_input=True, confirmation_prompt=True)
    password_error = validate_password(password)
    if password_error:
        click.echo(password_error)
        return

    user.set_password(password)

    try:
        db.session.commit()
        click.echo(f"Password for user '{username}' updated successfully.")
    except Exception as exc:
        db.session.rollback()
        click.echo(f"Error updating password: {exc}")
        current_app.logger.error(f"Error updating password for user {username}: {exc}")


@click.command('create-default-admin')
@click.argument('username')
@with_appcontext
def create_default_admin_command(username):
    """Create the bootstrap admin user with a forced password change."""
    user, error = create_default_admin(username)
    if error:
        raise click.ClickException(error)

    click.echo(f"Default admin user '{user.username}' created successfully.")


def register_user_commands(app):
    """Register user-related CLI commands."""
    app.cli.add_command(create_user_command)
    app.cli.add_command(update_user_password_command)
    app.cli.add_command(create_default_admin_command)
