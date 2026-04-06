import re

USERNAME_MIN_LENGTH = 2
USERNAME_MAX_LENGTH = 80
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def validate_username(username):
    """Validate username and return an error message or None."""
    if not isinstance(username, str):
        return "Username must be a string."

    username = username.strip()
    if not username:
        return "Username is required."

    if len(username) < USERNAME_MIN_LENGTH:
        return f"Username must be at least {USERNAME_MIN_LENGTH} characters."

    if len(username) > USERNAME_MAX_LENGTH:
        return f"Username must be at most {USERNAME_MAX_LENGTH} characters."

    if not USERNAME_PATTERN.match(username):
        return "Username can only contain letters, numbers, hyphens, and underscores."

    return None


def validate_password(password):
    """Validate password and return an error message or None."""
    if not isinstance(password, str):
        return "Password must be a string."

    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."

    if len(password) > PASSWORD_MAX_LENGTH:
        return f"Password must be at most {PASSWORD_MAX_LENGTH} characters."

    return None


def is_login_password_format_valid(password):
    """Allow existing stored passwords while still rejecting invalid payloads."""
    return isinstance(password, str) and len(password) <= PASSWORD_MAX_LENGTH
