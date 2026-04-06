import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt,
    get_jwt_identity,
    set_access_cookies,
    unset_jwt_cookies
)
from ui.models import User
from ui import db, limiter
from ui.auth_validation import (
    is_login_password_format_valid,
    validate_password,
    validate_username,
)

auth_api_bp = Blueprint('auth_api_routes', __name__)

_LOCKOUT_THRESHOLD = 10  # failed attempts within the window
_LOCKOUT_TTL = 15 * 60   # seconds (15 minutes)
_MAX_LOG_USERNAME = 200   # max chars for username in log output
_DEFAULT_BOOTSTRAP_PASSWORD = 'admin'


def _safe_repr(username):
    """Return a repr() of username truncated to _MAX_LOG_USERNAME chars."""
    r = repr(username)
    return r[:_MAX_LOG_USERNAME] + '...' if len(r) > _MAX_LOG_USERNAME else r


def _redis():
    return current_app.extensions.get('redis')


def _user_payload(user):
    return {
        "username": user.username,
        "id": user.id,
        "passwordChangeRequired": user.password_change_required
    }


def _is_locked_out(username):
    r = _redis()
    if r is None:
        return False
    try:
        count = r.get(f"login_failures:{username.lower()}")
        return int(count) >= _LOCKOUT_THRESHOLD if count else False
    except Exception:
        return False  # fail open if Redis is unavailable


def _record_failure(username):
    r = _redis()
    if r is None:
        return
    try:
        key = f"login_failures:{username.lower()}"
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, _LOCKOUT_TTL)
        pipe.execute()
    except Exception:
        pass


def _clear_failures(username):
    r = _redis()
    if r is None:
        return
    try:
        r.delete(f"login_failures:{username.lower()}")
    except Exception:
        pass


@auth_api_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login_api():
    """Handles user login and JWT generation using Flask-JWT-Extended."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": {"message": "Username and password are required."}}), 400

    username_error = validate_username(username)
    if username_error:
        current_app.logger.warning(f"Invalid username format attempt: {_safe_repr(username)}")
        return jsonify({"error": {"message": "Invalid username or password."}}), 401

    username = username.strip()

    if not is_login_password_format_valid(password):
        current_app.logger.warning(f"Invalid password format attempt for username: {_safe_repr(username)}")
        return jsonify({"error": {"message": "Invalid username or password."}}), 401

    # Per-account lockout check (tracks failed attempts across IPs)
    if _is_locked_out(username):
        current_app.logger.warning(f"Locked-out login attempt for username: {_safe_repr(username)}")
        return jsonify({"error": {"message": "Invalid username or password."}}), 401

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        try:
            _clear_failures(username)
            user.last_login_at = datetime.datetime.now(datetime.timezone.utc)
            db.session.commit()

            expires_delta = datetime.timedelta(hours=current_app.config.get('JWT_EXPIRATION_HOURS', 24))
            access_token = create_access_token(identity=user.username, expires_delta=expires_delta)

            current_app.logger.info(f"User '{username}' logged in successfully.")

            response = jsonify({
                "data": {
                    "message": "Login successful.",
                    "user": _user_payload(user)
                }
            })
            set_access_cookies(response, access_token)
            return response, 200
        except Exception as e:
            current_app.logger.error(f"Error during login for user {username}: {e}", exc_info=True)
            return jsonify({"error": {"message": "An internal error occurred during login."}}), 500
    else:
        _record_failure(username)
        current_app.logger.warning(f"Failed login attempt for username: {_safe_repr(username)}")
        return jsonify({"error": {"message": "Invalid username or password."}}), 401


@auth_api_bp.route('/status', methods=['GET'])
@jwt_required()
def auth_status():
    """Checks if the user has a valid session cookie and returns user info."""
    current_user_identity = get_jwt_identity()
    user = User.query.filter_by(username=current_user_identity).first()
    if not user:
        return jsonify({"error": {"message": "Authenticated user not found in database."}}), 401

    return jsonify({
        "data": {
            "isAuthenticated": True,
            "user": _user_payload(user)
        }
    }), 200


@auth_api_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """Update the authenticated user's password and clear forced rotation."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON."}}), 400

    password = data.get('password', '')
    confirm_password = data.get('confirmPassword', '')

    if password != confirm_password:
        return jsonify({"error": {"message": "Passwords do not match."}}), 400

    password_error = validate_password(password)
    if password_error:
        return jsonify({"error": {"message": password_error}}), 400

    if password == _DEFAULT_BOOTSTRAP_PASSWORD:
        return jsonify({"error": {"message": "New password cannot be the default password."}}), 400

    user = User.query.filter_by(username=get_jwt_identity()).first()
    if not user:
        return jsonify({"error": {"message": "Authenticated user not found in database."}}), 401

    try:
        user.set_password(password)
        user.password_change_required = False
        db.session.commit()
        current_app.logger.info(f"User '{user.username}' changed password successfully.")
        return jsonify({"data": {"message": "Password changed successfully."}}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"Error changing password for user {user.username}: {e}",
            exc_info=True
        )
        return jsonify({"error": {"message": "Failed to change password."}}), 500


@auth_api_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout_api():
    """Handles user logout: revokes the JWT and unsets the cookie."""
    jwt_payload = get_jwt()
    try:
        r = _redis()
        if r is not None:
            jti = jwt_payload["jti"]
            exp = jwt_payload.get("exp", 0)
            ttl = max(0, int(exp - datetime.datetime.now(datetime.timezone.utc).timestamp()))
            if ttl > 0:
                r.setex(f"jwt_blocklist:{jti}", ttl, "revoked")
    except Exception as e:
        current_app.logger.warning(f"Failed to blocklist JWT on logout: {e}")

    response = jsonify({"data": {"message": "Logout successful."}})
    unset_jwt_cookies(response)
    current_app.logger.info(f"User '{get_jwt_identity()}' logged out.")
    return response, 200
