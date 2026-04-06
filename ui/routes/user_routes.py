from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from ui import db
from ui.models import User
from ui.auth_validation import validate_password, validate_username

# Create a Blueprint for user management API routes
user_api_bp = Blueprint('user_api_routes', __name__)


@user_api_bp.route('/', methods=['GET'])
@jwt_required()
def list_users():
    """Get all users."""
    users = User.query.order_by(User.username).all()
    return jsonify({"data": [user.to_dict() for user in users]}), 200


@user_api_bp.route('/', methods=['POST'])
@jwt_required()
def create_user():
    """Create a new user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON."}}), 400

    username = data.get('username', '')
    password = data.get('password', '')

    # Validate username
    username_error = validate_username(username)
    if username_error:
        return jsonify({"error": {"message": username_error}}), 400

    username = username.strip()

    # Validate password
    password_error = validate_password(password)
    if password_error:
        return jsonify({"error": {"message": password_error}}), 400

    # Check for duplicate username
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({"error": {"message": f"Username '{username}' already exists."}}), 409

    try:
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        current_app.logger.info(f"User '{username}' created by '{get_jwt_identity()}'.")
        return jsonify({
            "data": new_user.to_dict(),
            "message": f"User '{username}' created successfully."
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user '{username}': {e}")
        return jsonify({"error": {"message": "Failed to create user."}}), 500


@user_api_bp.route('/<int:user_id>/password', methods=['PUT'])
@jwt_required()
def reset_password(user_id):
    """Reset password for a user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON."}}), 400

    password = data.get('password', '')

    # Validate password
    password_error = validate_password(password)
    if password_error:
        return jsonify({"error": {"message": password_error}}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": {"message": "User not found."}}), 404

    try:
        user.set_password(password)
        db.session.commit()

        current_app.logger.info(
            f"Password reset for user '{user.username}' by '{get_jwt_identity()}'."
        )
        return jsonify({
            "data": user.to_dict(),
            "message": f"Password for '{user.username}' reset successfully."
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error resetting password for user {user_id}: {e}")
        return jsonify({"error": {"message": "Failed to reset password."}}), 500


@user_api_bp.route('/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    """Delete a user."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": {"message": "User not found."}}), 404

    # Prevent self-deletion
    current_username = get_jwt_identity()
    if user.username == current_username:
        return jsonify({"error": {"message": "Cannot delete your own account."}}), 403

    try:
        username = user.username
        db.session.delete(user)
        db.session.commit()

        current_app.logger.info(f"User '{username}' deleted by '{current_username}'.")
        return jsonify({
            "message": f"User '{username}' deleted successfully."
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user {user_id}: {e}")
        return jsonify({"error": {"message": "Failed to delete user."}}), 500
