from flask import Blueprint, request, jsonify, current_app # Removed render_template, redirect, url_for, flash, abort. Added jsonify, current_app
from ui import db, rq
from ui.models import Host, HostStatus, InstanceStatus # Added InstanceStatus
from ui.database import (
    get_hosts, get_host, get_host_by_name, create_host, update_host, delete_host # delete_host might be used by delete_host_route
)
import re
import os
import ipaddress
import subprocess
import tempfile
import uuid
from ui.task_lock import acquire_lock, release_lock, force_release_lock

# Host name validation constants
HOST_NAME_MAX_LENGTH = 20
HOST_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$')
SSH_USER_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_.-]{0,63}$')

# Systemd OnCalendar validation (matches formats produced by the frontend)
SYSTEMD_CALENDAR_RE = re.compile(
    r'^(?:'
    r'\*-\*-\* \d{2}:\d{2}:00'  # daily
    r'|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:,(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun))* \*-\*-\* \d{2}:\d{2}:00'  # weekly
    r'|\*-\*-(?:0[1-9]|[12]\d|3[01])(?:,(?:0[1-9]|[12]\d|3[01]))* \d{2}:\d{2}:00'  # monthly
    r')$'
)

def validate_host_name(name, exclude_host_id=None):
    """Validates host name. Returns (validated_name, error_dict)."""
    if not isinstance(name, str):
        return None, {"message": "Name must be a string", "status_code": 400}
    name = name.strip()  # Remove lowercase normalization
    if not name:
        return None, {"message": "Name cannot be empty", "status_code": 400}
    if len(name) > HOST_NAME_MAX_LENGTH:
        return None, {"message": f"Name cannot exceed {HOST_NAME_MAX_LENGTH} characters", "status_code": 400}
    if name.isdigit():
        return None, {"message": "Host name cannot contain only digits.", "status_code": 400}
    if not HOST_NAME_PATTERN.match(name):
        return None, {"message": "Name must start and end with a letter or number, and can only contain letters, numbers, and hyphens", "status_code": 400}
    existing_host = get_host_by_name(name)
    if existing_host and (exclude_host_id is None or existing_host.id != exclude_host_id):
        return None, {"message": f"A host with the name '{name}' already exists", "status_code": 409}
    return name, None

def validate_ip_address(ip_str):
    """Validates IP address format. Returns (validated_ip, error_dict)."""
    if not isinstance(ip_str, str):
        return None, {"message": "IP address must be a string", "status_code": 400}
    ip_str = ip_str.strip()
    if not ip_str:
        return None, {"message": "IP address cannot be empty", "status_code": 400}
    try:
        # Parse and validate IP address (supports both IPv4 and IPv6)
        ip_obj = ipaddress.ip_address(ip_str)
        return str(ip_obj), None
    except ValueError:
        return None, {"message": "Invalid IP address format", "status_code": 400}

# Valid OS info surfaced during standalone host auto-detection
UBUNTU_99K_LAN_RATE_WARNING = "99k LAN rate is not compatible with Ubuntu."
VALID_STANDALONE_AUTH_METHODS = {'key', 'password'}
VALID_TIMEZONES = {
    'Africa/Johannesburg', 'America/Anchorage', 'America/Chicago', 'America/Denver',
    'America/Los_Angeles', 'America/Mexico_City', 'America/New_York', 'America/Sao_Paulo',
    'America/Santiago', 'America/Toronto', 'Asia/Colombo', 'Asia/Dubai', 'Asia/Jakarta',
    'Asia/Jerusalem', 'Asia/Kolkata', 'Asia/Riyadh', 'Asia/Seoul', 'Asia/Shanghai',
    'Asia/Singapore', 'Asia/Tokyo', 'Australia/Melbourne', 'Australia/Perth',
    'Australia/Sydney', 'Europe/Amsterdam', 'Europe/Berlin', 'Europe/London',
    'Europe/Madrid', 'Europe/Moscow', 'Europe/Paris', 'Europe/Stockholm', 'Europe/Warsaw',
    'Pacific/Auckland', 'Pacific/Honolulu', 'UTC',
}


def is_vultr_configured():
    return bool(os.environ.get('VULTR_API_KEY', '').strip())

# Import task functions
from ui.tasks import provision_host, destroy_host, \
    install_qlfilter_task, uninstall_qlfilter_task, check_qlfilter_status_task, \
    restart_host_task, rename_host_task, \
    setup_standalone_host_ansible, remove_standalone_host, \
    force_update_workshop_task, configure_host_auto_restart_task, \
    enqueue_task
from ui.task_logic.job_failure_handlers import host_job_failure_handler
from ui.routes.self_host_helpers import (
    SelfHostKeyError,
    cleanup_self_host_key_material,
    detect_default_self_ssh_user,
    generate_self_host_keys,
)
from ui.standalone_ssh import StandaloneSSHError, bootstrap_managed_key
from ui.standalone_ssh import detect_local_os, detect_remote_os
from ui.standalone_ssh import remove_managed_key
from ui.standalone_ssh import verify_password_login, verify_passwordless_sudo
from flask_jwt_extended import jwt_required # Import the decorator from Flask-JWT-Extended

# Create a Blueprint for host API routes
host_api_bp = Blueprint('host_api_routes', __name__) # url_prefix will be set when registering with main api_bp

@host_api_bp.route('/', methods=['GET'], endpoint='list_hosts_api')
@jwt_required()
def list_hosts_api():
    """Returns a list of configured host servers."""
    hosts = get_hosts()
    host_list = [host.to_dict() for host in hosts] # Assuming Host model has a to_dict() method
    return jsonify({"data": host_list})

@host_api_bp.route('/', methods=['POST'], endpoint='add_host_api')
@jwt_required()
def add_host_api():
    """Handles adding a new host server via API."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    name = data.get('name')
    provider = data.get('provider')

    if not name or not provider:
        return jsonify({"error": {"message": "Name and Provider are required."}}), 400

    # Validate host name
    validated_name, error = validate_host_name(name)
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]
    name = validated_name

    if provider == 'self':
        return _handle_self_host_creation(name, data)
    if provider == 'standalone':
        return _handle_standalone_host_creation(name, data)
    return _handle_cloud_host_creation(name, provider, data)


def _handle_cloud_host_creation(name, provider, data):
    """Handle creation of cloud-provisioned hosts (Vultr, etc.)."""
    region = data.get('region')
    machine_size = data.get('machine_size')
    timezone = data.get('timezone')

    if provider == 'vultr' and not is_vultr_configured():
        return jsonify({
            "error": {
                "message": "Vultr deployment is unavailable until VULTR_API_KEY is added to the environment."
            }
        }), 400

    if not region or not machine_size:
        return jsonify({"error": {"message": "Region and Machine Size are required for cloud providers."}}), 400

    # Validate timezone if provided (optional for cloud hosts)
    if timezone is not None:
        if not isinstance(timezone, str) or not timezone.strip():
            return jsonify({"error": {"message": "Timezone must be a non-empty string."}}), 400
        timezone = timezone.strip()
        if timezone not in VALID_TIMEZONES:
            return jsonify({"error": {"message": f"Invalid timezone. Must be a valid IANA timezone."}}), 400

    try:
        host = create_host(
            name=name,
            provider=provider,
            region=region,
            machine_size=machine_size,
            timezone=timezone,
            os_type='debian',
            is_standalone=False,
            status=HostStatus.PENDING
        )
        if host:
            lock_token = str(uuid.uuid4())
            if not acquire_lock('host', host.id, lock_token, ttl=1500):
                return jsonify({"error": {"message": f'Another operation is running on host "{name}". Please wait for it to complete.'}}), 409
            try:
                update_host(host.id, status=HostStatus.PROVISIONING)
                enqueue_task(provision_host, host.id, lock_token=lock_token, on_failure=host_job_failure_handler)
            except Exception:
                release_lock('host', host.id, lock_token)
                raise
            current_app.logger.info(f'Host "{name}" (ID: {host.id}) added and provisioning task queued.')
            return jsonify({"data": host.to_dict(), "message": f'Host "{name}" added and provisioning task queued.'}), 201
        else:
            current_app.logger.error(f'Error adding host "{name}" - create_host returned None.')
            return jsonify({"error": {"message": f'Error adding host "{name}".'}}), 500
    except Exception as e:
        current_app.logger.error(f'Error adding host: {e}', exc_info=True)
        return jsonify({"error": {"message": f'Error adding host: {str(e)}'}}), 500


def _validate_standalone_auth_method(value):
    if value is None:
        return 'key', None
    if not isinstance(value, str):
        return None, {"message": "SSH auth method must be a string.", "status_code": 400}

    value = value.strip().lower()
    if value == 'ssh_key':
        value = 'key'
    if value not in VALID_STANDALONE_AUTH_METHODS:
        return None, {"message": "SSH auth method must be either 'key' or 'password'.", "status_code": 400}
    return value, None


def _validate_standalone_auth_credential(auth_method, ssh_key=None, ssh_password=None):
    if auth_method == 'key':
        if not isinstance(ssh_key, str) or not ssh_key.strip():
            return None, {"message": "SSH private key is required for standalone hosts.", "status_code": 400}
        return ssh_key.strip(), None

    if not isinstance(ssh_password, str) or ssh_password == '':
        return None, {"message": "SSH password is required for standalone hosts.", "status_code": 400}
    return ssh_password, None


def _standalone_private_key_path(name, ssh_keys_dir='terraform/ssh-keys'):
    resolved_dir = os.path.abspath(ssh_keys_dir)
    os.makedirs(resolved_dir, exist_ok=True)
    return os.path.join(resolved_dir, f"{name}_standalone_id_rsa")


def _cleanup_local_key_material(*paths):
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _cleanup_password_bootstrap_artifacts(ip_address, ssh_port, ssh_user, ssh_key_path, public_key_path, managed_key_installed):
    if managed_key_installed and ssh_key_path:
        try:
            remove_managed_key(ip_address, ssh_port, ssh_user, ssh_key_path)
        except Exception as exc:
            current_app.logger.warning(
                "Failed to remove bootstrapped managed SSH key during rollback for %s:%s as %s: %s",
                ip_address,
                ssh_port,
                ssh_user,
                exc,
            )
    _cleanup_local_key_material(ssh_key_path, public_key_path)


def generate_managed_standalone_keypair(name, ssh_keys_dir='terraform/ssh-keys'):
    ssh_key_path = _standalone_private_key_path(name, ssh_keys_dir=ssh_keys_dir)
    public_key_path = f"{ssh_key_path}.pub"
    _cleanup_local_key_material(ssh_key_path, public_key_path)

    try:
        subprocess.run(
            ['ssh-keygen', '-q', '-t', 'rsa', '-b', '4096', '-f', ssh_key_path, '-N', ''],
            check=True,
            capture_output=True,
            text=True,
        )
        os.chmod(ssh_key_path, 0o600)
        return ssh_key_path, public_key_path
    except Exception:
        _cleanup_local_key_material(ssh_key_path, public_key_path)
        raise


def _write_standalone_private_key(name, ssh_key, ssh_keys_dir='terraform/ssh-keys'):
    ssh_key_path = _standalone_private_key_path(name, ssh_keys_dir=ssh_keys_dir)
    _cleanup_local_key_material(ssh_key_path, f"{ssh_key_path}.pub")

    with open(ssh_key_path, 'w') as handle:
        handle.write(ssh_key + '\n')
    os.chmod(ssh_key_path, 0o600)
    return ssh_key_path


def test_password_connection(host, port, username, password, timeout=15):
    if not verify_password_login(host, port, username, password, timeout=timeout):
        return False, "Connection failed: password authentication failed or host is unreachable."
    if username != 'root' and not verify_passwordless_sudo(host, port, username, password, timeout=timeout):
        return False, "Connection failed: passwordless sudo is required for non-root users."
    return True, "Connection successful"


def _build_detected_os_success_message(detected_os):
    detected_name = detected_os['pretty_name']
    detected_os_type = detected_os['os_type']
    message = f"Connection successful. Detected OS: {detected_name}."
    if detected_os_type == 'ubuntu':
        message = f"{message} Warning: {UBUNTU_99K_LAN_RATE_WARNING}"
    return message


def _validate_detected_remote_os(detected_os):
    detected_name = detected_os['pretty_name']
    detected_os_type = detected_os['os_type']

    if detected_os_type is None:
        return (
            False,
            f"Connection failed: detected OS {detected_name} is not supported. "
            "QLSM standalone hosts must run Debian or Ubuntu 20.x, 22.x, or 24.x.",
        )

    return True, _build_detected_os_success_message(detected_os)


def _detect_and_validate_remote_os(*, host, port, username, timeout=15, password=None, key_filename=None):
    try:
        detected_os = detect_remote_os(
            host=host,
            port=port,
            username=username,
            timeout=timeout,
            password=password,
            key_filename=key_filename,
        )
    except StandaloneSSHError as exc:
        return False, f"Connection failed: {exc}", None

    success, message = _validate_detected_remote_os(detected_os)
    return success, message, detected_os


def _test_standalone_connection_with_key(validated_ip, ssh_port, ssh_user, ssh_key):
    temp_key_path = None
    try:
        temp_key_path = os.path.join(tempfile.gettempdir(), f"test_conn_{uuid.uuid4().hex}")
        with open(temp_key_path, 'w') as handle:
            handle.write(ssh_key + '\n')
        os.chmod(temp_key_path, 0o600)

        ansible_cmd = [
            'ansible', 'all',
            '-i', f'{validated_ip},',
            '-m', 'ping',
            '-u', ssh_user,
            '--private-key', temp_key_path,
            '-e', f'ansible_port={ssh_port}',
            '-e', 'ansible_ssh_common_args="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"',
            '--timeout', '15'
        ]

        current_app.logger.info(f"Testing connection to {validated_ip}:{ssh_port} as {ssh_user}")
        result = subprocess.run(
            ansible_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            current_app.logger.info(f"Connection test successful for {validated_ip}")
            success, message, _ = _detect_and_validate_remote_os(
                host=validated_ip,
                port=ssh_port,
                username=ssh_user,
                timeout=15,
                key_filename=temp_key_path,
            )
            return jsonify({"data": {"success": success, "message": message}}), 200

        error_output = result.stderr or result.stdout or "Unknown error"
        current_app.logger.warning(f"Connection test failed for {validated_ip}: {error_output}")
        return jsonify({"data": {"success": False, "message": f"Connection failed: {error_output}"}}), 200

    except subprocess.TimeoutExpired:
        current_app.logger.warning(f"Connection test timed out for {validated_ip}")
        return jsonify({"data": {"success": False, "message": "Connection timed out"}}), 200
    except Exception as exc:
        current_app.logger.error(f"Error testing connection: {exc}", exc_info=True)
        return jsonify({"error": {"message": f"Error testing connection: {str(exc)}"}}), 500
    finally:
        if temp_key_path and os.path.exists(temp_key_path):
            try:
                os.remove(temp_key_path)
            except OSError:
                pass


def _handle_standalone_host_creation(name, data):
    """Handle creation of standalone (user-provided) hosts."""
    ip_address = data.get('ip_address')
    ssh_key = data.get('ssh_key')
    ssh_password = data.get('ssh_password')
    ssh_user = data.get('ssh_user', 'root')
    ssh_port = data.get('ssh_port', 22)
    ssh_auth_method = data.get('ssh_auth_method')
    timezone = data.get('timezone')

    # Validate required fields
    if not ip_address:
        return jsonify({"error": {"message": "IP address is required for standalone hosts."}}), 400
    if not timezone:
        return jsonify({"error": {"message": "Timezone is required for standalone hosts."}}), 400

    ssh_auth_method, error = _validate_standalone_auth_method(ssh_auth_method)
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    credential, error = _validate_standalone_auth_credential(
        ssh_auth_method,
        ssh_key=ssh_key,
        ssh_password=ssh_password,
    )
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    # Validate IP address
    validated_ip, error = validate_ip_address(ip_address)
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]
    ip_address = validated_ip

    # Validate SSH port
    try:
        ssh_port = int(ssh_port)
        if not (1 <= ssh_port <= 65535):
            return jsonify({"error": {"message": "SSH port must be between 1 and 65535."}}), 400
    except (TypeError, ValueError):
        return jsonify({"error": {"message": "SSH port must be a valid integer."}}), 400

    # Validate timezone
    if not isinstance(timezone, str) or not timezone.strip():
        return jsonify({"error": {"message": "Timezone must be a non-empty string."}}), 400
    timezone = timezone.strip()
    if timezone not in VALID_TIMEZONES:
        return jsonify({"error": {"message": "Invalid timezone. Must be a valid IANA timezone."}}), 400

    ssh_user, error = _validate_standalone_ssh_user(ssh_user)
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    host = None
    lock_token = None
    ssh_key_path = None
    public_key_path = None
    managed_key_installed = False
    try:
        if ssh_auth_method == 'password':
            ssh_key_path, public_key_path = generate_managed_standalone_keypair(name)
            bootstrap_managed_key(
                validated_ip,
                ssh_port,
                ssh_user,
                credential,
                ssh_key_path,
            )
            managed_key_installed = True
        else:
            ssh_key_path = _write_standalone_private_key(name, credential)

        remote_os_ok, remote_os_message, detected_os = _detect_and_validate_remote_os(
            host=validated_ip,
            port=ssh_port,
            username=ssh_user,
            timeout=30,
            key_filename=ssh_key_path,
        )
        if not remote_os_ok:
            if ssh_auth_method == 'password':
                _cleanup_password_bootstrap_artifacts(
                    validated_ip,
                    ssh_port,
                    ssh_user,
                    ssh_key_path,
                    public_key_path,
                    managed_key_installed,
                )
            else:
                _cleanup_local_key_material(ssh_key_path, public_key_path)
            return jsonify({"error": {"message": remote_os_message}}), 400

        # Create host record
        host = create_host(
            name=name,
            provider='standalone',
            ip_address=validated_ip,
            ssh_user=ssh_user,
            ssh_key_path=ssh_key_path,
            ssh_port=ssh_port,
            os_type=detected_os['os_type'],
            timezone=timezone,
            is_standalone=True,
            status=HostStatus.PENDING
        )

        if host:
            lock_token = str(uuid.uuid4())
            if not acquire_lock('host', host.id, lock_token, ttl=1260):
                db.session.delete(host)
                db.session.commit()
                if ssh_auth_method == 'password':
                    _cleanup_password_bootstrap_artifacts(
                        validated_ip,
                        ssh_port,
                        ssh_user,
                        ssh_key_path,
                        public_key_path,
                        managed_key_installed,
                    )
                else:
                    _cleanup_local_key_material(ssh_key_path, public_key_path)
                return jsonify({"error": {"message": f'Another operation is running on host "{name}". Please wait for it to complete.'}}), 409
            try:
                # Skip PROVISIONING, go directly to PROVISIONED_PENDING_SETUP
                update_host(host.id, status=HostStatus.PROVISIONED_PENDING_SETUP)
                # Queue the Ansible setup task
                enqueue_task(setup_standalone_host_ansible, host.id, timeout=1200, lock_token=lock_token, on_failure=host_job_failure_handler)
            except Exception:
                release_lock('host', host.id, lock_token)
                raise
            current_app.logger.info(f'Standalone host "{name}" (ID: {host.id}) added and setup task queued.')
            return jsonify({"data": host.to_dict(), "message": f'Standalone host "{name}" added and setup task queued.'}), 201
        else:
            if ssh_auth_method == 'password':
                _cleanup_password_bootstrap_artifacts(
                    validated_ip,
                    ssh_port,
                    ssh_user,
                    ssh_key_path,
                    public_key_path,
                    managed_key_installed,
                )
            else:
                _cleanup_local_key_material(ssh_key_path, public_key_path)
            current_app.logger.error(f'Error adding standalone host "{name}" - create_host returned None.')
            return jsonify({"error": {"message": f'Error adding standalone host "{name}".'}}), 500

    except StandaloneSSHError as exc:
        if ssh_auth_method == 'password':
            _cleanup_password_bootstrap_artifacts(
                validated_ip,
                ssh_port,
                ssh_user,
                ssh_key_path,
                public_key_path,
                managed_key_installed,
            )
        else:
            _cleanup_local_key_material(ssh_key_path, public_key_path)
        current_app.logger.warning(f'Standalone password bootstrap failed for "{name}": {exc}')
        return jsonify({"error": {"message": str(exc)}}), 400
    except Exception as e:
        if host:
            try:
                db.session.delete(host)
                db.session.commit()
            except Exception:
                db.session.rollback()
        if ssh_auth_method == 'password':
            _cleanup_password_bootstrap_artifacts(
                validated_ip,
                ssh_port,
                ssh_user,
                ssh_key_path,
                public_key_path,
                managed_key_installed,
            )
        else:
            _cleanup_local_key_material(ssh_key_path, public_key_path)
        current_app.logger.error(f'Error adding standalone host: {e}', exc_info=True)
        return jsonify({"error": {"message": f'Error adding standalone host: {str(e)}'}}), 500

# Note: The GET part of the original add_host is removed as forms are handled by React.

@host_api_bp.route('/self/defaults', methods=['GET'], endpoint='get_self_host_defaults_api')
@jwt_required()
def get_self_host_defaults_api():
    ssh_user = detect_default_self_ssh_user()
    host_ip = os.environ.get('QLSM_HOST_IP', '').strip() or None
    os_info = detect_local_os()
    return jsonify({
        "data": {
            "ssh_user": ssh_user,
            "host_ip": host_ip,
            "os_info": os_info,
            "provider_capabilities": {
                "vultr": {
                    "configured": is_vultr_configured(),
                }
            },
        }
    })


def _validate_self_ssh_user(value):
    if value is None:
        value = detect_default_self_ssh_user()
    if not isinstance(value, str):
        return None, {"message": "SSH username must be a string.", "status_code": 400}
    value = value.strip()
    if not value:
        return None, {"message": "SSH username cannot be empty.", "status_code": 400}
    if not SSH_USER_PATTERN.match(value):
        return None, {"message": "SSH username contains invalid characters.", "status_code": 400}
    return value, None


def _validate_standalone_ssh_user(value):
    if value is None:
        value = 'root'
    if not isinstance(value, str):
        return None, {"message": "SSH username must be a string.", "status_code": 400}
    value = value.strip()
    if not value:
        return None, {"message": "SSH username cannot be empty.", "status_code": 400}
    if not SSH_USER_PATTERN.match(value):
        return None, {"message": "SSH username contains invalid characters.", "status_code": 400}
    return value, None


def _validate_required_timezone(timezone):
    if not isinstance(timezone, str) or not timezone.strip():
        return None, {"message": "Timezone is required for self hosts.", "status_code": 400}
    timezone = timezone.strip()
    if timezone not in VALID_TIMEZONES:
        return None, {"message": "Invalid timezone. Must be a valid IANA timezone.", "status_code": 400}
    return timezone, None


def _handle_self_host_creation(name, data):
    existing_self = Host.query.filter_by(provider='self').first()
    if existing_self:
        return jsonify({"error": {"message": "A self host already exists. Only one QLSM Host (self) is allowed."}}), 409

    timezone, error = _validate_required_timezone(data.get('timezone'))
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    ssh_user, error = _validate_self_ssh_user(data.get('ssh_user'))
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    ip_address, error = validate_ip_address(data.get('ip_address', ''))
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    host = None
    key_path = None
    public_key = None
    lock_token = None
    local_os_info = detect_local_os()
    local_os_type = local_os_info.get('os_type') if local_os_info else None
    try:
        key_path, public_key = generate_self_host_keys(name)
        host = create_host(
            name=name,
            provider='self',
            ip_address=ip_address,
            ssh_user=ssh_user,
            ssh_key_path=key_path,
            ssh_port=22,
            os_type=local_os_type,
            is_standalone=True,
            timezone=timezone,
            status=HostStatus.PENDING,
        )

        lock_token = str(uuid.uuid4())
        if not acquire_lock('host', host.id, lock_token, ttl=1260):
            db.session.delete(host)
            db.session.commit()
            cleanup_self_host_key_material(key_path, public_key=public_key)
            return jsonify({"error": {"message": f'Another operation is running on host "{name}". Please wait for it to complete.'}}), 409

        update_host(host.id, status=HostStatus.PROVISIONED_PENDING_SETUP)
        enqueue_task(
            setup_standalone_host_ansible,
            host.id,
            timeout=1200,
            lock_token=lock_token,
            on_failure=host_job_failure_handler,
        )
        current_app.logger.info(f'Self host "{name}" (ID: {host.id}) added and setup task queued.')
        return jsonify({"data": host.to_dict(), "message": f'Self host "{name}" added and setup task queued.'}), 201
    except ValueError as exc:
        return jsonify({"error": {"message": str(exc)}}), 500
    except SelfHostKeyError:
        return jsonify({"error": {"message": "SSH key generation failed."}}), 500
    except Exception as exc:
        if lock_token and host:
            try:
                release_lock('host', host.id, lock_token)
            except Exception as lock_exc:
                current_app.logger.warning(
                    "Could not release self-host creation lock for host %s: %s",
                    host.id,
                    lock_exc,
                )
        if host:
            try:
                db.session.delete(host)
                db.session.commit()
            except Exception:
                db.session.rollback()
        if key_path:
            cleanup_self_host_key_material(key_path, public_key=public_key)
        current_app.logger.error(f'Error adding self host: {exc}', exc_info=True)
        return jsonify({"error": {"message": f'Error adding self host: {str(exc)}'}}), 500


@host_api_bp.route('/<int:host_id>', methods=['GET'], endpoint='view_host_api') # Changed route from /view to just /<id> for RESTful GET
@jwt_required()
def view_host_api(host_id): # Renamed function
    """Returns details for a specific host server."""
    host = get_host(host_id)
    if not host:
        # flash('Host not found.', 'danger')
        return jsonify({"error": {"message": "Host not found."}}), 404

    return jsonify({"data": host.to_dict()}) # Assuming Host model has a to_dict() method

@host_api_bp.route('/<int:host_id>', methods=['DELETE'], endpoint='delete_host_api') # Changed method from POST to DELETE
@jwt_required()
def delete_host_api(host_id): # Renamed function
    """Handles deleting an existing host server via API."""
    host = get_host(host_id)
    if not host:
        return jsonify({"error": {"message": "Host not found."}}), 404

    # Check if host has active instances (as per PRD)
    if host.instances and any(instance.status != InstanceStatus.DELETING for instance in host.instances):
         return jsonify({"error": {"message": f'Cannot delete host "{host.name}" because it has associated active Quake Live instances. Please delete them first.'}}), 409

    host_name = host.name
    is_standalone = host.is_standalone

    # Stale-lock detection: if the host has been in a transitional state with
    # no DB activity for longer than the max provisioning lock TTL (1500s), the
    # task that holds the lock is almost certainly dead (worker crash, OOM kill).
    # Force-release the stale lock so the delete can proceed.
    STALE_LOCK_THRESHOLD_SECONDS = 1800
    STALE_TRANSITIONAL_STATUSES = {
        HostStatus.PROVISIONING,
        HostStatus.PROVISIONED_PENDING_SETUP,
        HostStatus.CONFIGURING,
        HostStatus.REBOOTING,
    }
    import datetime as _dt
    if (
        host.status in STALE_TRANSITIONAL_STATUSES
        and host.last_updated is not None
        and (_dt.datetime.utcnow() - host.last_updated).total_seconds() > STALE_LOCK_THRESHOLD_SECONDS
    ):
        current_app.logger.warning(
            f'Host "{host_name}" ({host_id}) has been in {host.status.value} for '
            f'>{STALE_LOCK_THRESHOLD_SECONDS}s with no activity. Force-releasing stale lock.'
        )
        force_release_lock('host', host.id)

    lock_token = str(uuid.uuid4())
    if not acquire_lock('host', host.id, lock_token, ttl=240):
        return jsonify({"error": {"message": f'Another operation is running on host "{host_name}". Please wait for it to complete.'}}), 409

    try:
        update_host(host.id, status=HostStatus.DELETING)
        if is_standalone:
            enqueue_task(remove_standalone_host, host.id, lock_token=lock_token, on_failure=host_job_failure_handler)
            action_msg = f'Standalone host "{host_name}" removal task queued.'
        else:
            enqueue_task(destroy_host, host.id, lock_token=lock_token, on_failure=host_job_failure_handler)
            action_msg = f'Host "{host_name}" deletion task queued.'
        current_app.logger.info(action_msg)
        return jsonify({"message": action_msg}), 202
    except Exception as e:
        release_lock('host', host.id, lock_token)
        current_app.logger.error(f'Error queuing host deletion for {host.id}: {e}', exc_info=True)
        return jsonify({"error": {"message": f'Error queuing host deletion: {str(e)}'}}), 500


@host_api_bp.route('/<int:host_id>', methods=['PUT'], endpoint='update_host_api')
@jwt_required()
def update_host_api(host_id):
    """Handles updating an existing host server via API."""
    current_app.logger.info(f"Received request to update host ID: {host_id}")
    host = get_host(host_id)
    if not host:
        current_app.logger.warning(f"Update host: Host ID {host_id} not found.")
        return jsonify({"error": {"message": "Host not found"}}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "No data provided"}}), 400

    # Handle name update
    if 'name' in data:
        name = data['name']

        # Validate host name using shared helper
        validated_name, error = validate_host_name(name, exclude_host_id=host_id)
        if error:
            return jsonify({"error": {"message": error["message"]}}), error["status_code"]
        name = validated_name

        try:
            # Check if name is actually changing
            old_name = host.name
            is_name_changing = (name != old_name)

            # Update database with new name
            updated_host = update_host(host_id, name=name)
            if not updated_host:
                return jsonify({"error": {"message": "Failed to update host"}}), 500

            current_app.logger.info(f"Host {host_id} name updated to '{name}'")

            # If name changed, enqueue task to update inventory and remote hostname
            if is_name_changing:
                lock_token = str(uuid.uuid4())
                if not acquire_lock('host', host_id, lock_token, ttl=240):
                    # Revert name change
                    update_host(host_id, name=old_name)
                    return jsonify({"error": {"message": f'Another operation is running on host "{old_name}". Please wait for it to complete.'}}), 409
                try:
                    enqueue_task(rename_host_task, host_id, old_name, name, lock_token=lock_token, on_failure=host_job_failure_handler)
                except Exception:
                    release_lock('host', host_id, lock_token)
                    update_host(host_id, name=old_name)
                    raise
                current_app.logger.info(f"Rename task queued for host {host_id}: {old_name} -> {name}")
                return jsonify({
                    "message": f"Host renamed from '{old_name}' to '{name}'. Inventory update task queued.",
                    "data": updated_host.to_dict()
                }), 200

            return jsonify({
                "message": "Host updated successfully",
                "data": updated_host.to_dict()
            }), 200
        except Exception as e:
            current_app.logger.error(f"Error updating host {host_id}: {e}")
            return jsonify({"error": {"message": "Failed to update host"}}), 500

    return jsonify({"error": {"message": "No valid fields to update"}}), 400


@host_api_bp.route('/<int:host_id>/logs', methods=['GET'], endpoint='view_host_logs_api') # Added methods=['GET']
@jwt_required()
def view_host_logs_api(host_id): # Renamed function
    """Returns logs for a specific host."""
    host = get_host(host_id)
    if not host:
        # flash('Host not found.', 'danger')
        return jsonify({"error": {"message": "Host not found."}}), 404

    # Pass the host object which contains the logs
    return jsonify({"data": {"logs": host.logs or ""}})

@host_api_bp.route('/<int:host_id>/available-ports', methods=['GET'], endpoint='get_available_ports_api')
@jwt_required()
def get_available_ports_api(host_id):
    """Returns a list of available ports for a given host."""
    # This logic is moved from the old instance_routes.py
    POSSIBLE_PORTS = [27960, 27961, 27962, 27963] # Define or get from config

    host = get_host(host_id)
    if not host:
        return jsonify({'error': {'message': 'Host not found'}}), 404

    # Find ports already used by instances on this host
    # Ensure instances are loaded; depends on SQLAlchemy session state or explicit loading
    # If host.instances is a lazy-loaded relationship, accessing it here should query the DB.
    try:
        used_ports = {instance.port for instance in host.instances}
    except Exception as e:
        current_app.logger.error(f"Error accessing host.instances for host {host_id}: {e}", exc_info=True)
        return jsonify({'error': {'message': 'Could not retrieve instance data for host.'}}), 500
        
    available_ports = [port for port in POSSIBLE_PORTS if port not in used_ports]
    return jsonify({'data': {'available_ports': available_ports}})

# QLFilter Management Endpoints

@host_api_bp.route('/<int:host_id>/qlfilter/install', methods=['POST'], endpoint='install_qlfilter_api')
@jwt_required()
def install_qlfilter_api(host_id):
    """Enqueues a task to install QLFilter on the host."""
    host = get_host(host_id)
    if not host:
        return jsonify({"error": {"message": "Host not found."}}), 404

    if host.status not in [HostStatus.ACTIVE]: # Only allow on active hosts
        return jsonify({"error": {"message": f"Host is not in a valid state for QLFilter installation (current: {host.status.value})."}}), 409

    try:
        from ui.models import QLFilterStatus # Ensure QLFilterStatus is imported
        lock_token = str(uuid.uuid4())
        if not acquire_lock('host', host.id, lock_token, ttl=240):
            return jsonify({"error": {"message": f'Another operation is running on host "{host.name}". Please wait for it to complete.'}}), 409
        prev_qlfilter_status = host.qlfilter_status
        try:
            update_host(host.id, qlfilter_status=QLFilterStatus.INSTALLING)
            enqueue_task(install_qlfilter_task, host.id, lock_token=lock_token, on_failure=host_job_failure_handler)
        except Exception:
            release_lock('host', host.id, lock_token)
            update_host(host.id, qlfilter_status=prev_qlfilter_status)
            raise
        current_app.logger.info(f'QLFilter installation task queued for host ID {host.id}.')
        return jsonify({"message": f'QLFilter installation task queued for host "{host.name}".'}), 202
    except Exception as e:
        current_app.logger.error(f'Error queuing QLFilter installation for host {host.id}: {e}', exc_info=True)
        return jsonify({"error": {"message": f'Error queuing QLFilter installation: {str(e)}'}}), 500

@host_api_bp.route('/<int:host_id>/qlfilter/uninstall', methods=['POST'], endpoint='uninstall_qlfilter_api')
@jwt_required()
def uninstall_qlfilter_api(host_id):
    """Enqueues a task to uninstall QLFilter from the host."""
    host = get_host(host_id)
    if not host:
        return jsonify({"error": {"message": "Host not found."}}), 404
    
    try:
        from ui.models import QLFilterStatus # Ensure QLFilterStatus is imported
        lock_token = str(uuid.uuid4())
        if not acquire_lock('host', host.id, lock_token, ttl=240):
            return jsonify({"error": {"message": f'Another operation is running on host "{host.name}". Please wait for it to complete.'}}), 409
        prev_qlfilter_status = host.qlfilter_status
        try:
            update_host(host.id, qlfilter_status=QLFilterStatus.UNINSTALLING)
            enqueue_task(uninstall_qlfilter_task, host.id, lock_token=lock_token, on_failure=host_job_failure_handler)
        except Exception:
            release_lock('host', host.id, lock_token)
            update_host(host.id, qlfilter_status=prev_qlfilter_status)
            raise
        current_app.logger.info(f'QLFilter uninstallation task queued for host ID {host.id}.')
        return jsonify({"message": f'QLFilter uninstallation task queued for host "{host.name}".'}), 202
    except Exception as e:
        current_app.logger.error(f'Error queuing QLFilter uninstallation for host {host.id}: {e}', exc_info=True)
        return jsonify({"error": {"message": f'Error queuing QLFilter uninstallation: {str(e)}'}}), 500

@host_api_bp.route('/<int:host_id>/qlfilter/status', methods=['GET'], endpoint='get_qlfilter_status_api')
@jwt_required()
def get_qlfilter_status_api(host_id):
    """Returns the current QLFilter status for the host from the database."""
    host = get_host(host_id)
    if not host:
        return jsonify({"error": {"message": "Host not found."}}), 404

    # The qlfilter_status is an Enum member, so we return its value.
    # The Host.to_dict() method already handles converting enum to its value.
    # If qlfilter_status can be None in the DB, to_dict() should handle it (e.g. default to UNKNOWN.value)
    status_value = host.qlfilter_status.value if host.qlfilter_status else 'unknown' # Ensure a string is returned
    
    current_app.logger.info(f'Returning QLFilter status for host ID {host.id}: {status_value}')
    return jsonify({"data": {"qlfilter_status": status_value}}), 200

@host_api_bp.route('/<int:host_id>/qlfilter/refresh-status', methods=['POST'], endpoint='refresh_qlfilter_status_api')
@jwt_required()
def refresh_qlfilter_status_api(host_id):
    """Enqueues a task to refresh the QLFilter status for the host."""
    host = get_host(host_id)
    if not host:
        return jsonify({"error": {"message": "Host not found."}}), 404

    try:
        lock_token = str(uuid.uuid4())
        if not acquire_lock('host', host.id, lock_token, ttl=240):
            return jsonify({"error": {"message": f'Another operation is running on host "{host.name}". Please wait for it to complete.'}}), 409
        try:
            enqueue_task(check_qlfilter_status_task, host.id, lock_token=lock_token, on_failure=host_job_failure_handler)
        except Exception:
            release_lock('host', host.id, lock_token)
            raise
        current_app.logger.info(f'QLFilter status refresh task queued for host ID {host.id}.')
        return jsonify({"message": f'QLFilter status refresh task queued for host "{host.name}".'}), 202
    except Exception as e:
        current_app.logger.error(f'Error queuing QLFilter status refresh for host {host.id}: {e}', exc_info=True)
        return jsonify({"error": {"message": f'Error queuing QLFilter status refresh: {str(e)}'}}), 500

# New API Endpoint to restart a host
@host_api_bp.route('/<int:host_id>/restart', methods=['POST'], endpoint='restart_host_api')
@jwt_required()
def restart_host_api(host_id):
    """Handles restarting a host server via API."""
    current_app.logger.info(f"Received API request to restart host ID: {host_id}")
    host = get_host(host_id)
    if not host:
        current_app.logger.warning(f"Restart host API: Host ID {host_id} not found.")
        return jsonify({"error": {"message": "Host not found"}}), 404

    # Basic validation: only allow restart if host is ACTIVE
    if host.status != HostStatus.ACTIVE:
        current_app.logger.warning(f"Restart host API: Host ID {host_id} is not in ACTIVE state (current: {host.status.value}).")
        return jsonify({"error": {"message": f"Host must be in ACTIVE state to restart. Current state: {host.status.value}"}}), 400

    try:
        lock_token = str(uuid.uuid4())
        if not acquire_lock('host', host.id, lock_token, ttl=180):
            return jsonify({"error": {"message": f'Another operation is running on host "{host.name}". Please wait for it to complete.'}}), 409
        try:
            enqueue_task(restart_host_task, host.id, lock_token=lock_token, on_failure=host_job_failure_handler)
        except Exception:
            release_lock('host', host.id, lock_token)
            raise
        current_app.logger.info(f"Restart task enqueued for host ID: {host.id} via API.")
        # The task itself will set HostStatus.REBOOTING
        return jsonify({"message": "Host restart process initiated."}), 202
    except Exception as e:
        current_app.logger.error(f"Error enqueuing restart task for host {host_id} via API: {e}", exc_info=True)
        return jsonify({"error": {"message": "Failed to initiate host restart process"}}), 500

@host_api_bp.route('/<int:host_id>/update-workshop', methods=['POST'], endpoint='force_update_workshop_api')
@jwt_required()
def force_update_workshop_api(host_id):
    """Handles triggering a workshop update for a host via API."""
    current_app.logger.info(f"Received API request to update workshop items for host ID: {host_id}")
    host = get_host(host_id)
    if not host:
        current_app.logger.warning(f"Update workshop API: Host ID {host_id} not found.")
        return jsonify({"error": {"message": "Host not found"}}), 404

    # Basic validation: only allow if host is ACTIVE
    if host.status != HostStatus.ACTIVE:
        current_app.logger.warning(f"Update workshop API: Host ID {host_id} is not in ACTIVE state (current: {host.status.value}).")
        return jsonify({"error": {"message": f"Host must be in ACTIVE state to update workshop. Current state: {host.status.value}"}}), 400

    data = request.get_json()
    if not data or 'workshop_id' not in data:
        return jsonify({"error": {"message": "workshop_id is required"}}), 400

    workshop_id = str(data.get('workshop_id', '')).strip()
    if not workshop_id or not re.fullmatch(r'\d+', workshop_id):
        return jsonify({"error": {"message": "workshop_id must be a non-empty numeric string"}}), 400

    restart_instances = data.get('restart_instances', [])
    if not isinstance(restart_instances, list) or not all(isinstance(x, int) for x in restart_instances):
        return jsonify({"error": {"message": "restart_instances must be a list of integers"}}), 400

    try:
        lock_token = str(uuid.uuid4())
        if not acquire_lock('host', host_id, lock_token, ttl=240):
            return jsonify({"error": {"message": f'Another operation is running on host "{host.name}". Please wait for it to complete.'}}), 409
        try:
            enqueue_task(force_update_workshop_task, host_id, workshop_id, restart_instances, lock_token=lock_token, on_failure=host_job_failure_handler)
        except Exception:
            release_lock('host', host_id, lock_token)
            raise
        current_app.logger.info(f"Workshop update task enqueued for host ID: {host_id}, item: {workshop_id} via API.")
        return jsonify({"message": "Workshop update process initiated."}), 202
    except Exception as e:
        current_app.logger.error(f"Error enqueuing workshop update task for host {host_id} via API: {e}", exc_info=True)
        return jsonify({"error": {"message": "Failed to initiate workshop update process"}}), 500

@host_api_bp.route('/<int:host_id>/auto-restart', methods=['POST'], endpoint='configure_auto_restart_api')
@jwt_required()
def configure_auto_restart_api(host_id):
    """Handles configuring the auto-restart schedule for a host via systemd timer."""
    current_app.logger.info(f"Received API request to configure auto-restart for host ID: {host_id}")
    host = get_host(host_id)
    if not host:
        current_app.logger.warning(f"Configure auto-restart API: Host ID {host_id} not found.")
        return jsonify({"error": {"message": "Host not found"}}), 404

    # Only allow on active hosts
    if host.status != HostStatus.ACTIVE:
        current_app.logger.warning(f"Configure auto-restart API: Host ID {host_id} is not in ACTIVE state (current: {host.status.value}).")
        return jsonify({"error": {"message": f"Host must be in ACTIVE state. Current state: {host.status.value}"}}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "No data provided"}}), 400

    # schedule string (systemd OnCalendar format). Empty or None means remove schedule.
    schedule = data.get('schedule')
    if schedule is not None:
        schedule = str(schedule).strip()
        if not schedule:
            schedule = None

    # Validate schedule format against known systemd OnCalendar patterns
    if schedule and not SYSTEMD_CALENDAR_RE.match(schedule):
        return jsonify({"error": {"message": "Invalid schedule format"}}), 400

    try:
        lock_token = str(uuid.uuid4())
        if not acquire_lock('host', host.id, lock_token, ttl=180):
            return jsonify({"error": {"message": f'Another operation is running on host "{host.name}". Please wait for it to complete.'}}), 409
        try:
            update_host(host.id, status=HostStatus.CONFIGURING)
            enqueue_task(configure_host_auto_restart_task, host.id, schedule, lock_token=lock_token, on_failure=host_job_failure_handler)
        except Exception:
            release_lock('host', host.id, lock_token)
            raise
        current_app.logger.info(f"Auto-restart config task enqueued for host ID: {host_id} via API.")
        return jsonify({
            "message": "Auto-restart configuration process initiated.",
            "data": {"auto_restart_schedule": schedule}
        }), 202
    except Exception as e:
        current_app.logger.error(f"Error enqueuing auto-restart config task for host {host_id}: {e}", exc_info=True)
        return jsonify({"error": {"message": "Failed to initiate auto-restart configuration"}}), 500


@host_api_bp.route('/test-connection', methods=['POST'], endpoint='test_connection_api')
@jwt_required()
def test_connection_api():
    """Tests SSH connectivity to a standalone host using Ansible ping."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    ip_address = data.get('ip_address')
    ssh_port = data.get('ssh_port', 22)
    ssh_user = data.get('ssh_user', 'root')
    ssh_key = data.get('ssh_key')
    ssh_password = data.get('ssh_password')
    ssh_auth_method = data.get('ssh_auth_method')

    # Validate required fields
    if not ip_address:
        return jsonify({"error": {"message": "IP address is required."}}), 400

    ssh_auth_method, error = _validate_standalone_auth_method(ssh_auth_method)
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    credential, error = _validate_standalone_auth_credential(
        ssh_auth_method,
        ssh_key=ssh_key,
        ssh_password=ssh_password,
    )
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    # Validate IP address
    validated_ip, error = validate_ip_address(ip_address)
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    # Validate SSH port
    try:
        ssh_port = int(ssh_port)
        if not (1 <= ssh_port <= 65535):
            return jsonify({"error": {"message": "SSH port must be between 1 and 65535."}}), 400
    except (TypeError, ValueError):
        return jsonify({"error": {"message": "SSH port must be a valid integer."}}), 400

    ssh_user, error = _validate_standalone_ssh_user(ssh_user)
    if error:
        return jsonify({"error": {"message": error["message"]}}), error["status_code"]

    if ssh_auth_method == 'password':
        success, message = test_password_connection(
            validated_ip,
            ssh_port,
            ssh_user,
            credential,
        )
        if success:
            success, message, _ = _detect_and_validate_remote_os(
                host=validated_ip,
                port=ssh_port,
                username=ssh_user,
                timeout=15,
                password=credential,
            )
        return jsonify({"data": {"success": success, "message": message}}), 200

    return _test_standalone_connection_with_key(
        validated_ip,
        ssh_port,
        ssh_user,
        credential,
    )
