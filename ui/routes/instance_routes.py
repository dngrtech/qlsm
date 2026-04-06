import os
import re
import shutil
import uuid
from flask import Blueprint, request, current_app, jsonify
import sqlalchemy
from ui import db
from ui.models import QLInstance, Host, HostStatus, InstanceStatus
from ui.database import (
    get_instances, get_instance, create_instance, update_instance, delete_instance,
    get_host,
)
from ui.tasks import deploy_instance, apply_instance_config, restart_instance, stop_instance, start_instance, delete_instance as delete_instance_task, reconfigure_instance_lan_rate, enqueue_task
from ui.task_logic.job_failure_handlers import instance_job_failure_handler
from ui.task_lock import acquire_lock, release_lock
from flask_jwt_extended import jwt_required # Import the decorator from Flask-JWT-Extended

# Create a Blueprint for instance API routes
instance_api_bp = Blueprint('instance_api_routes', __name__) # url_prefix will be set when registering

_QLX_PLUGINS_RE = re.compile(r'^[a-zA-Z0-9_, ]*$')

def _validate_qlx_plugins(value):
    """Validate and sanitize qlx_plugins string. Returns (cleaned, error)."""
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "qlx_plugins must be a string"
    value = value.strip()
    if len(value) > 1000:
        return None, "qlx_plugins exceeds maximum length (1000)"
    if not _QLX_PLUGINS_RE.match(value):
        return None, "qlx_plugins contains invalid characters"
    return value, None

@instance_api_bp.route('/ping', methods=['GET'])
def ping_instances_api():
    return jsonify({"message": "pong from instance_api"}), 200

# Helper function to read default config files - needed for creating new instances if not provided in API
def _read_default_config(filename):
    """Reads content from a file in configs/presets/default/."""
    default_config_path = os.path.join('configs', 'presets', 'default', filename)
    try:
        with open(default_config_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        current_app.logger.warning(f"Default config file not found: {default_config_path}")
        return None
    except Exception as e:
        current_app.logger.error(f"Error reading default config file {default_config_path}: {e}")
        return None


@instance_api_bp.route('/', methods=['POST'], endpoint='add_instance_api')
@jwt_required()
def add_instance_api():
    """Handles adding a new QL instance via API."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    name = data.get('name')
    host_id = data.get('host_id')
    port = data.get('port')
    hostname = data.get('hostname')
    lan_rate_enabled = data.get('lan_rate_enabled', False) # Default to False
    configs_data = data.get('configs', {}) # Expect a 'configs' object in JSON
    qlx_plugins, qlx_err = _validate_qlx_plugins(data.get('qlx_plugins'))
    if qlx_err:
        return jsonify({"error": {"message": qlx_err}}), 400
    checked_plugins = data.get('checked_plugins')
    if checked_plugins is not None:
        qlx_plugins_str = ', '.join(checked_plugins)
        qlx_plugins, qlx_err = _validate_qlx_plugins(qlx_plugins_str)
        if qlx_err:
            return jsonify({"error": {"message": qlx_err}}), 400

    # Basic validation
    if not name or not host_id or not port or not hostname:
        return jsonify({"error": {"message": "Name, Host ID, Port, and Server Hostname are required."}}), 400

    try:
        port_int = int(port)
        host_id_int = int(host_id)

        selected_host = get_host(host_id_int)
        if not selected_host or selected_host.status != HostStatus.ACTIVE:
            return jsonify({"error": {"message": "Invalid or inactive host selected."}}), 400

        if len(selected_host.instances) >= 4:
            return jsonify({"error": {"message": "Host has reached the maximum of 4 instances."}}), 400

        # --- Validate draft before creating the instance ---
        draft_id = data.get('draft_id')
        if data.get('scripts'):
            return jsonify({"error": {"message": "The 'scripts' payload is no longer supported. Use draft_id instead. Please refresh your browser."}}), 400
        if draft_id:
            from ui.routes.draft_routes import _validate_draft_id, _draft_exists
            if not _validate_draft_id(draft_id):
                return jsonify({"error": {"message": "Invalid draft_id"}}), 400
            if not _draft_exists(draft_id):
                return jsonify({"error": {"message": "Draft not found. It may have expired. Please try again."}}), 400

        # --- Try creating the instance ---
        instance = create_instance(
            name=name, host_id=host_id_int, port=port_int, hostname=hostname, 
            lan_rate_enabled=bool(lan_rate_enabled), qlx_plugins=qlx_plugins
        )

        # --- Save submitted config content to files ---
        instance_config_dir = os.path.join('configs', selected_host.name, str(instance.id))
        os.makedirs(instance_config_dir, exist_ok=True)
        current_app.logger.info(f"Created instance config directory: {instance_config_dir}")

        # Config files to look for in JSON, or use default if not provided
        config_files_to_process = {
            'server.cfg': configs_data.get('server.cfg', _read_default_config('server.cfg')),
            'mappool.txt': configs_data.get('mappool.txt', _read_default_config('mappool.txt')),
            'access.txt': configs_data.get('access.txt', _read_default_config('access.txt')),
            'workshop.txt': configs_data.get('workshop.txt', _read_default_config('workshop.txt'))
        }

        for filename, content in config_files_to_process.items():
            if content is not None: # Only save if content exists (either from JSON or default)
                filepath = os.path.join(instance_config_dir, filename)
                with open(filepath, 'w') as f:
                    f.write(content)
                current_app.logger.info(f"Saved {filename} to {filepath} for instance {instance.id}")

        # --- Handle scripts via draft ---
        instance_scripts_dir = os.path.join(instance_config_dir, 'scripts')

        if draft_id:
            from ui.routes.draft_routes import _get_draft_scripts_path, _get_draft_base_path

            draft_scripts = _get_draft_scripts_path(draft_id)
            if os.path.exists(draft_scripts):
                shutil.copytree(draft_scripts, instance_scripts_dir, dirs_exist_ok=True)
                current_app.logger.info(f"Copied draft {draft_id} scripts to {instance_scripts_dir}")

            shutil.rmtree(_get_draft_base_path(draft_id), ignore_errors=True)
        else:
            # No draft — copy defaults
            default_scripts_dir = os.path.join('configs', 'presets', 'default', 'scripts')
            if os.path.exists(default_scripts_dir):
                shutil.copytree(default_scripts_dir, instance_scripts_dir, dirs_exist_ok=True)
            else:
                os.makedirs(instance_scripts_dir, exist_ok=True)

        # --- Handle factories ---
        # Key distinction:
        # - 'factories' key MISSING from request → copy all defaults (legacy behavior)
        # - 'factories' key PRESENT (even if empty {}) → respect user selection, only deploy selected
        instance_factories_dir = os.path.join(instance_config_dir, 'factories')
        os.makedirs(instance_factories_dir, exist_ok=True)
        
        if 'factories' in data:
            # User explicitly provided factory selection - only deploy what they selected
            # First, clear the directory to remove any previous files
            if os.path.exists(instance_factories_dir):
                shutil.rmtree(instance_factories_dir)
            os.makedirs(instance_factories_dir, exist_ok=True)
            
            factories_data = data.get('factories', {})
            for filename, content in factories_data.items():
                if content is not None:
                    factory_path = os.path.join(instance_factories_dir, filename)
                    with open(factory_path, 'w') as f:
                        f.write(content)
                    current_app.logger.info(f"Saved user-selected factory {filename} for instance {instance.id}")
            current_app.logger.info(f"User selected {len(factories_data)} factories for instance {instance.id}")
        else:
            # No factories key in request - copy all defaults (legacy/fallback behavior)
            default_factories_dir = os.path.join('configs', 'presets', 'default', 'factories')
            if os.path.exists(default_factories_dir):
                shutil.copytree(default_factories_dir, instance_factories_dir, dirs_exist_ok=True)
                current_app.logger.info(f"Copied default factories to {instance_factories_dir} for instance {instance.id}")

        # Acquire entity lock before enqueue
        lock_token = str(uuid.uuid4())
        if not acquire_lock('instance', instance.id, lock_token, ttl=1260):
            return jsonify({"error": {"message": f'Another operation is running on this instance. Please wait for it to complete.'}}), 409

        # Update status to DEPLOYING and enqueue task
        try:
            update_instance(instance.id, status=InstanceStatus.DEPLOYING)
            job = enqueue_task(deploy_instance, instance.id, lock_token=lock_token, on_failure=instance_job_failure_handler)
        except Exception as enqueue_err:
            release_lock('instance', instance.id, lock_token)
            update_instance(instance.id, status=InstanceStatus.IDLE)
            raise enqueue_err
        if job:
            current_app.logger.info(f"Enqueued job {job.id} for deploy_instance for instance {instance.id}")
            return jsonify({"data": instance.to_dict(), "message": f'Instance "{name}" created, configuration saved, and deployment task queued.'}), 201
        else:
            release_lock('instance', instance.id, lock_token)
            current_app.logger.error(f"Failed to enqueue deploy_instance task for instance {instance.id}")
            update_instance(instance.id, status=InstanceStatus.ERROR)
            return jsonify({"error": {"message": "Error queuing deployment task."}}), 500

    except sqlalchemy.exc.OperationalError as e:
        db.session.rollback()
        current_app.logger.error(f"Database operational error creating instance: {e}", exc_info=True)
        if "readonly database" in str(e):
            return jsonify({"error": {"message": "Database error: The database is currently read-only."}}), 500
        return jsonify({"error": {"message": f'Database operational error: {str(e)}'}}), 500
    except sqlalchemy.exc.IntegrityError as e:
        db.session.rollback()
        current_app.logger.warning(f"IntegrityError creating instance: {e}")
        # Assuming selected_host is available
        error_message = f'An instance with the name "{name}" already exists on host "{selected_host.name if selected_host else "Unknown"}". Please choose a unique name.'
        return jsonify({"error": {"message": error_message}}), 409 # 409 Conflict
    except ValueError:
        return jsonify({"error": {"message": "Port must be a number."}}), 400
    except Exception as e:
        db.session.rollback() # Ensure rollback for any other unexpected error during the process
        current_app.logger.error(f"Unexpected error during instance add: {e}", exc_info=True)
        # Attempt to clean up instance if it was created before the error
        if 'instance' in locals() and instance and instance.id:
            try:
                delete_instance(instance.id) # This might also fail, but worth a try
                # Also attempt to remove the config directory
                if 'instance_config_dir' in locals() and os.path.exists(instance_config_dir):
                    shutil.rmtree(instance_config_dir)
            except Exception as cleanup_err:
                current_app.logger.error(f"Failed to cleanup instance/configs for {instance.id if 'instance' in locals() and instance else 'unknown instance'} after error: {cleanup_err}")
        return jsonify({"error": {"message": f'An unexpected error occurred: {str(e)}'}}), 500

@instance_api_bp.route('/', methods=['GET'], endpoint='list_instances_api')
@jwt_required()
def list_instances_api():
    """Returns a list of all QL instances."""
    instances = get_instances()
    instance_list = [inst.to_dict() for inst in instances]
    return jsonify({"data": instance_list})

@instance_api_bp.route('/<int:instance_id>', methods=['GET', 'PUT'], endpoint='view_instance_api')
@jwt_required()
def view_instance_api(instance_id): # Renamed function
    """Returns details for or updates a specific QL instance."""
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    if request.method == 'PUT':
        data = request.get_json()
        if not data:
             return jsonify({"error": {"message": "Request body must be JSON"}}), 400
        
        # Currently only supporting name updates
        new_name = data.get('name')
        new_hostname = data.get('hostname')

        if new_name or new_hostname:
            try:
                update_kwargs = {}
                
                # Handle Name Update
                if new_name:
                    # Check for uniqueness on the same host
                    existing_instance = QLInstance.query.filter(
                        QLInstance.host_id == instance.host_id,
                        db.func.lower(QLInstance.name) == new_name.lower()
                    ).first()
                    if existing_instance and existing_instance.id != instance.id:
                        return jsonify({"error": {"message": f"An instance with the name '{new_name}' already exists on this host."}}), 409
                    update_kwargs['name'] = new_name

                # Handle Hostname Update
                if new_hostname:
                    update_kwargs['hostname'] = new_hostname

                if update_kwargs:
                    update_instance(instance.id, **update_kwargs)
                    # Refresh instance to ensure we have latest data
                    db.session.refresh(instance)
                    return jsonify({"data": instance.to_dict(), "message": "Instance details updated successfully."})
                else:
                     return jsonify({"message": "No changes detected."})
            except sqlalchemy.exc.IntegrityError:
                db.session.rollback()
                return jsonify({"error": {"message": f"An instance with the name '{new_name}' already exists."}}), 409
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error updating instance {instance.id}: {e}", exc_info=True)
                return jsonify({"error": {"message": f"Failed to update instance: {str(e)}"}}), 500

    return jsonify({"data": instance.to_dict()}) # Assuming QLInstance model has to_dict()

@instance_api_bp.route('/<int:instance_id>', methods=['DELETE'], endpoint='delete_instance_api') # Changed method from POST to DELETE
@jwt_required()
def delete_instance_api(instance_id): # Renamed function
    """Handles initiating the deletion of an existing QL instance via API."""
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    if instance.status in [InstanceStatus.DELETING, InstanceStatus.CONFIGURING]:
        return jsonify({"error": {"message": f'Instance "{instance.name}" is currently busy ({instance.status.value}). Cannot initiate deletion.'}}), 409

    lock_token = str(uuid.uuid4())
    if not acquire_lock('instance', instance.id, lock_token, ttl=360):
        return jsonify({"error": {"message": f'Another operation is running on instance "{instance.name}". Please wait for it to complete.'}}), 409

    try:
        instance.status = InstanceStatus.DELETING
        db.session.commit()
        current_app.logger.info(f"Set instance {instance.id} status to DELETING.")

        enqueue_task(delete_instance_task, instance.id, lock_token=lock_token, on_failure=instance_job_failure_handler)
        current_app.logger.info(f"Enqueued delete_instance task for instance {instance.id}.")
        return jsonify({"message": f'Instance "{instance.name}" deletion initiated.'}), 202 # 202 Accepted

    except Exception as e:
        release_lock('instance', instance.id, lock_token)
        db.session.rollback()
        current_app.logger.error(f"Error initiating instance deletion for {instance.id}: {e}", exc_info=True)
        return jsonify({"error": {"message": f'Error initiating instance deletion: {str(e)}'}}), 500

@instance_api_bp.route('/<int:instance_id>/restart', methods=['POST'], endpoint='restart_instance_api')
@jwt_required()
def restart_instance_api(instance_id): # Renamed function
    """Handles restarting an existing QL instance via API."""
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    if instance.status in [InstanceStatus.DEPLOYING, InstanceStatus.CONFIGURING, InstanceStatus.RESTARTING,
                           InstanceStatus.DELETING, InstanceStatus.STOPPING, InstanceStatus.STARTING]:
         return jsonify({"error": {"message": f'Instance "{instance.name}" is currently busy ({instance.status.value}). Cannot restart now.'}}), 409

    lock_token = str(uuid.uuid4())
    if not acquire_lock('instance', instance.id, lock_token, ttl=180):
        return jsonify({"error": {"message": f'Another operation is running on instance "{instance.name}". Please wait for it to complete.'}}), 409

    try:
        update_instance(instance.id, status=InstanceStatus.RESTARTING)
        enqueue_task(restart_instance, instance.id, lock_token=lock_token, on_failure=instance_job_failure_handler)
        current_app.logger.info(f'Instance "{instance.name}" (ID: {instance.id}) restart task queued.')
        return jsonify({"message": f'Instance "{instance.name}" restart task queued.'}), 202 # 202 Accepted
    except Exception as e:
        release_lock('instance', instance.id, lock_token)
        current_app.logger.error(f'Error queuing instance restart for {instance.id}: {e}', exc_info=True)
        return jsonify({"error": {"message": f'Error queuing instance restart: {str(e)}'}}), 500

@instance_api_bp.route('/<int:instance_id>/stop', methods=['POST'], endpoint='stop_instance_api')
@jwt_required()
def stop_instance_api(instance_id):
    """Handles stopping an existing QL instance via API."""
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    busy_statuses = [InstanceStatus.DEPLOYING, InstanceStatus.CONFIGURING, InstanceStatus.RESTARTING,
                     InstanceStatus.DELETING, InstanceStatus.STOPPING, InstanceStatus.STARTING]
    if instance.status in busy_statuses:
        return jsonify({"error": {"message": f'Instance "{instance.name}" is currently busy ({instance.status.value}). Cannot stop now.'}}), 409

    if instance.status == InstanceStatus.STOPPED:
        return jsonify({"error": {"message": f'Instance "{instance.name}" is already stopped.'}}), 409

    lock_token = str(uuid.uuid4())
    if not acquire_lock('instance', instance.id, lock_token, ttl=180):
        return jsonify({"error": {"message": f'Another operation is running on instance "{instance.name}". Please wait for it to complete.'}}), 409

    try:
        update_instance(instance.id, status=InstanceStatus.STOPPING)
        enqueue_task(stop_instance, instance.id, lock_token=lock_token, on_failure=instance_job_failure_handler)
        current_app.logger.info(f'Instance "{instance.name}" (ID: {instance.id}) stop task queued.')
        return jsonify({"message": f'Instance "{instance.name}" stop task queued.'}), 202
    except Exception as e:
        release_lock('instance', instance.id, lock_token)
        current_app.logger.error(f'Error queuing instance stop for {instance.id}: {e}', exc_info=True)
        return jsonify({"error": {"message": f'Error queuing instance stop: {str(e)}'}}), 500

@instance_api_bp.route('/<int:instance_id>/start', methods=['POST'], endpoint='start_instance_api')
@jwt_required()
def start_instance_api(instance_id):
    """Handles starting a stopped QL instance via API."""
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    busy_statuses = [InstanceStatus.DEPLOYING, InstanceStatus.CONFIGURING, InstanceStatus.RESTARTING,
                     InstanceStatus.DELETING, InstanceStatus.STOPPING, InstanceStatus.STARTING]
    if instance.status in busy_statuses:
        return jsonify({"error": {"message": f'Instance "{instance.name}" is currently busy ({instance.status.value}). Cannot start now.'}}), 409

    if instance.status in [InstanceStatus.RUNNING, InstanceStatus.UPDATED]:
        return jsonify({"error": {"message": f'Instance "{instance.name}" is already running.'}}), 409

    lock_token = str(uuid.uuid4())
    if not acquire_lock('instance', instance.id, lock_token, ttl=180):
        return jsonify({"error": {"message": f'Another operation is running on instance "{instance.name}". Please wait for it to complete.'}}), 409

    try:
        update_instance(instance.id, status=InstanceStatus.STARTING)
        enqueue_task(start_instance, instance.id, lock_token=lock_token, on_failure=instance_job_failure_handler)
        current_app.logger.info(f'Instance "{instance.name}" (ID: {instance.id}) start task queued.')
        return jsonify({"message": f'Instance "{instance.name}" start task queued.'}), 202
    except Exception as e:
        release_lock('instance', instance.id, lock_token)
        current_app.logger.error(f'Error queuing instance start for {instance.id}: {e}', exc_info=True)
        return jsonify({"error": {"message": f'Error queuing instance start: {str(e)}'}}), 500

@instance_api_bp.route('/<int:instance_id>/lan-rate', methods=['PUT'], endpoint='update_instance_lan_rate_api')
@jwt_required()
def update_instance_lan_rate_api(instance_id):
    """Handles toggling LAN rate mode for an existing QL instance via API."""
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    # Check if instance is busy
    if instance.status in [InstanceStatus.DEPLOYING, InstanceStatus.CONFIGURING, InstanceStatus.RESTARTING,
                           InstanceStatus.DELETING, InstanceStatus.STOPPING, InstanceStatus.STARTING]:
        return jsonify({"error": {"message": f'Instance "{instance.name}" is currently busy ({instance.status.value}). Cannot update LAN rate now.'}}), 409

    data = request.get_json()
    if not data or 'lan_rate_enabled' not in data:
        return jsonify({"error": {"message": "Request body must include 'lan_rate_enabled' boolean."}}), 400

    lan_rate_enabled = bool(data.get('lan_rate_enabled'))

    # Check if value is actually changing
    if instance.lan_rate_enabled == lan_rate_enabled:
        return jsonify({"message": f'LAN rate mode is already {"enabled" if lan_rate_enabled else "disabled"} for instance "{instance.name}".'}), 200

    lock_token = str(uuid.uuid4())
    if not acquire_lock('instance', instance.id, lock_token, ttl=660):
        return jsonify({"error": {"message": f'Another operation is running on instance "{instance.name}". Please wait for it to complete.'}}), 409

    original_lan_rate = instance.lan_rate_enabled
    try:
        # Update the database field
        update_instance(instance.id, lan_rate_enabled=lan_rate_enabled, status=InstanceStatus.CONFIGURING)

        # Enqueue the reconfiguration task
        job = enqueue_task(reconfigure_instance_lan_rate, instance.id, lock_token=lock_token, timeout=600, on_failure=instance_job_failure_handler)
        if job:
            current_app.logger.info(f'Instance "{instance.name}" (ID: {instance.id}) LAN rate reconfiguration task queued.')
            # Refresh instance to get updated state
            db.session.refresh(instance)
            return jsonify({
                "message": f'LAN rate mode {"enabled" if lan_rate_enabled else "disabled"} for instance "{instance.name}". Reconfiguration task queued.',
                "data": instance.to_dict()
            }), 202
        else:
            release_lock('instance', instance.id, lock_token)
            current_app.logger.error(f"Failed to enqueue reconfigure_instance_lan_rate task for instance {instance.id}")
            # Revert changes on failure
            update_instance(instance.id, lan_rate_enabled=original_lan_rate, status=InstanceStatus.ERROR)
            return jsonify({"error": {"message": "Error queuing LAN rate reconfiguration task."}}), 500
    except Exception as e:
        release_lock('instance', instance.id, lock_token)
        current_app.logger.error(f'Error updating LAN rate for instance {instance.id}: {e}', exc_info=True)
        # Revert to original state on any exception
        try:
            update_instance(instance.id, lan_rate_enabled=original_lan_rate, status=InstanceStatus.RUNNING)
        except Exception:
            pass  # Best effort revert
        return jsonify({"error": {"message": f'Error updating LAN rate: {str(e)}'}}), 500

@instance_api_bp.route('/<int:instance_id>/logs', methods=['GET'], endpoint='view_instance_logs_api') # Added methods=['GET']
@jwt_required()
def view_instance_logs_api(instance_id): # Renamed function
    """Returns logs for a specific QL instance."""
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    return jsonify({"data": {"logs": instance.logs or ""}})

@instance_api_bp.route('/<int:instance_id>/remote-logs', methods=['GET'], endpoint='fetch_remote_logs_api')
@jwt_required()
def fetch_remote_logs_api(instance_id):
    """Fetches logs from the remote QLDS instance via Ansible journalctl.
    
    Query parameters:
        filter_mode: 'time' or 'lines' (default: 'lines')
        since: Time period for time-based filtering (default: '1 hour ago')
        lines: Number of lines for line-based filtering (default: 500)
    """
    from ui.task_logic.ansible_instance_mgmt import fetch_instance_remote_logs
    
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    # Check if instance has a host
    if not instance.host:
        return jsonify({"error": {"message": "Instance has no associated host."}}), 400

    # Get query parameters
    filter_mode = request.args.get('filter_mode', 'lines')
    since = request.args.get('since', '1 hour ago')
    lines = request.args.get('lines', 500, type=int)
    
    # Validate filter_mode
    if filter_mode not in ('time', 'lines'):
        return jsonify({"error": {"message": "filter_mode must be 'time' or 'lines'"}}), 400
    
    # Validate lines (sensible range)
    if lines < 10 or lines > 10000:
        return jsonify({"error": {"message": "lines must be between 10 and 10000"}}), 400

    current_app.logger.info(f"Fetching remote logs for instance {instance_id} ({instance.name}) - mode: {filter_mode}, since: {since}, lines: {lines}")

    success, logs, error_msg = fetch_instance_remote_logs(
        instance_id, 
        filter_mode=filter_mode, 
        since=since, 
        lines=lines
    )

    if success:
        return jsonify({"data": {"logs": logs, "instance_name": instance.name, "port": instance.port, "filter_mode": filter_mode, "lines": lines, "since": since}})
    else:
        current_app.logger.error(f"Failed to fetch remote logs for instance {instance_id}: {error_msg}")
        return jsonify({"error": {"message": error_msg}}), 500

@instance_api_bp.route('/<int:instance_id>/chat-logs', methods=['GET'], endpoint='fetch_remote_chat_logs_api')
@jwt_required()
def fetch_remote_chat_logs_api(instance_id):
    """Fetches chat logs from the remote QLDS instance.
    
    Query parameters:
        lines: Number of lines to fetch (default: 500)
    """
    from ui.task_logic.ansible_instance_mgmt import fetch_instance_chat_logs
    
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    # Check if instance has a host
    if not instance.host:
        return jsonify({"error": {"message": "Instance has no associated host."}}), 400

    # Get query parameters
    lines = request.args.get('lines', 500, type=int)
    filename = request.args.get('filename', 'chat.log')
    
    # Validate lines (sensible range)
    if lines < 10 or lines > 10000:
        return jsonify({"error": {"message": "lines must be between 10 and 10000"}}), 400

    current_app.logger.info(f"Fetching chat logs for instance {instance_id} ({instance.name}) - lines: {lines}, filename: {filename}")

    success, logs, error_msg = fetch_instance_chat_logs(
        instance_id, 
        lines=lines,
        filename=filename
    )

    if success:
        return jsonify({"data": {"logs": logs, "instance_name": instance.name, "port": instance.port, "lines": lines, "filename": filename}})
    else:
        current_app.logger.error(f"Failed to fetch chat logs for instance {instance_id}: {error_msg}")
        return jsonify({"error": {"message": error_msg}}), 500

@instance_api_bp.route('/<int:instance_id>/chat-logs/list', methods=['GET'], endpoint='list_remote_chat_logs_api')
@jwt_required()
def list_remote_chat_logs_api(instance_id):
    """Lists available chat log files from the remote QLDS instance."""
    from ui.task_logic.ansible_instance_mgmt import list_instance_chat_logs
    
    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    current_app.logger.info(f"Listing chat logs for instance {instance_id} ({instance.name})")

    success, files, error_msg = list_instance_chat_logs(instance_id)

    if success:
        return jsonify({"data": {"files": files, "instance_name": instance.name}})
    else:
        current_app.logger.error(f"Failed to list chat logs for instance {instance_id}: {error_msg}")
        return jsonify({"error": {"message": error_msg}}), 500

# Helper function to read instance-specific config files - still needed for API
def _read_instance_config(host_name, instance_id, filename):
    """Reads content from a file in configs/<host_name>/<instance_id>/filename."""
    config_path = os.path.join('configs', host_name, str(instance_id), filename)
    try:
        with open(config_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        current_app.logger.info(f"Instance config file not found, will use empty: {config_path}")
        return "" # Return empty string if not found, template will handle it
    except Exception as e:
        current_app.logger.error(f"Error reading instance config file {config_path}: {e}")
        return f"# Error reading file: {e}" # Return error message in content

# Route for viewing/editing instance configuration files
@instance_api_bp.route('/<int:instance_id>/config', methods=['GET', 'PUT'], endpoint='manage_instance_config_api')
@jwt_required()
def manage_instance_config_api(instance_id): # Renamed and combined GET/POST from edit_instance_config
    """Handles viewing and editing configuration files for a QL instance via API."""
    instance = get_instance(instance_id)
    if not instance or not instance.host:
        return jsonify({"error": {"message": "Instance or associated host not found."}}), 404

    host_name = instance.host.name
    instance_config_dir = os.path.join('configs', host_name, str(instance.id))

    if request.method == 'PUT':
        data = request.get_json()
        if not data:
            return jsonify({"error": {"message": "Request body must be JSON"}}), 400

        lock_token = str(uuid.uuid4())
        if not acquire_lock('instance', instance.id, lock_token, ttl=360):
            return jsonify({"error": {"message": f'Another operation is running on instance "{instance.name}". Please wait for it to complete.'}}), 409
        lock_transferred = False
        
        # Expect a 'configs' object in the JSON payload
        configs_to_save = data.get('configs', {})
        
        # Define which config files are expected/allowed
        expected_files = ['server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt']
        
        try:
            os.makedirs(instance_config_dir, exist_ok=True)
            for filename in expected_files:
                content = configs_to_save.get(filename)
                if content is not None: # Save if provided, even if empty string
                    filepath = os.path.join(instance_config_dir, filename)
                    with open(filepath, 'w') as f:
                        f.write(content)
                    current_app.logger.info(f"Saved updated {filename} to {filepath} for instance {instance.id}")
                # If a file is not in `configs_to_save`, it's not touched.
                # To delete a file, client could send empty content.

            # Handle scripts via draft or legacy
            draft_id = data.get('draft_id')
            scripts_to_save = data.get('scripts', {})

            if draft_id:
                from ui.routes.draft_routes import (
                    _validate_draft_id, _draft_exists,
                    _get_draft_scripts_path, _get_draft_base_path
                )
                if not _validate_draft_id(draft_id):
                    return jsonify({"error": {"message": "Invalid draft_id"}}), 400
                if not _draft_exists(draft_id):
                    return jsonify({"error": {"message": "Draft not found. It may have expired."}}), 400

                instance_scripts_dir = os.path.join(instance_config_dir, 'scripts')
                draft_scripts = _get_draft_scripts_path(draft_id)
                if os.path.exists(draft_scripts):
                    if os.path.exists(instance_scripts_dir):
                        shutil.rmtree(instance_scripts_dir)
                    shutil.copytree(draft_scripts, instance_scripts_dir)
                shutil.rmtree(_get_draft_base_path(draft_id), ignore_errors=True)

            elif scripts_to_save:
                # Legacy partial-update path (text edits only, no binary support)
                instance_scripts_dir = os.path.join(instance_config_dir, 'scripts')
                os.makedirs(instance_scripts_dir, exist_ok=True)
                for relative_path, content in scripts_to_save.items():
                    script_path = os.path.join(instance_scripts_dir, relative_path)
                    os.makedirs(os.path.dirname(script_path), exist_ok=True)
                    with open(script_path, 'w') as f:
                        f.write(content)
                current_app.logger.info(f"Saved updated scripts for instance {instance.id}")

            # Handle factories updates
            factories_to_save = data.get('factories', {})
            # Note: For factories, we need to handle additions, updates, and removals (if content is None/missing?)
            # The current frontend implementation usually sends the full state of enabled factories.
            # If we want to support removal, we should clear the directory and rewrite, OR sync intelligently.
            # For now, let's assume factories_to_save contains ALL active factories and their content.
            # A cleaner approach for "management" API is to sync:
            # 1. Ensure dir exists
            instance_factories_dir = os.path.join(instance_config_dir, 'factories')
            os.makedirs(instance_factories_dir, exist_ok=True)
            
            # 2. Get existing files to identify removals
            existing_factories = set(f for f in os.listdir(instance_factories_dir) if f.endswith('.factories'))
            received_factories = set(factories_to_save.keys())
            
            # 3. Save/Update received
            for filename, content in factories_to_save.items():
                if content is not None:
                    filepath = os.path.join(instance_factories_dir, filename)
                    with open(filepath, 'w') as f:
                        f.write(content)
                    current_app.logger.info(f"Saved updated factory {filename} for instance {instance.id}")
            
            # 4. Remove valid .factories files that are NOT in the received list
            # This enforces that the backend state matches the frontend selection
            for filename in existing_factories:
                if filename not in received_factories:
                    filepath = os.path.join(instance_factories_dir, filename)
                    try:
                        os.remove(filepath)
                        current_app.logger.info(f"Removed unselected factory {filename} for instance {instance.id}")
                    except OSError as e:
                        current_app.logger.error(f"Error removing factory {filename}: {e}")


            restart = data.get('restart', True)
            
            # Only update qlx_plugins when the key is explicitly present in the
            # payload.  If the user never opened the Plugins tab, the frontend
            # omits the key entirely and we must NOT overwrite the DB value.
            update_kwargs = dict(status=InstanceStatus.CONFIGURING)
            if 'lan_rate_enabled' in data:
                update_kwargs['lan_rate_enabled'] = bool(data.get('lan_rate_enabled'))
            checked_plugins = data.get('checked_plugins')
            if checked_plugins is not None:
                qlx_plugins_str = ', '.join(checked_plugins)
                validated_plugins, qlx_err = _validate_qlx_plugins(qlx_plugins_str)
                if qlx_err:
                    return jsonify({"error": {"message": qlx_err}}), 400
                update_kwargs['qlx_plugins'] = validated_plugins
            elif 'qlx_plugins' in data:
                validated_plugins, qlx_err = _validate_qlx_plugins(data['qlx_plugins'])
                if qlx_err:
                    return jsonify({"error": {"message": qlx_err}}), 400
                update_kwargs['qlx_plugins'] = validated_plugins
            
            update_instance(instance.id, **update_kwargs)
            job = enqueue_task(apply_instance_config, instance.id, restart=restart, lock_token=lock_token, on_failure=instance_job_failure_handler)
            if job:
                lock_transferred = True
                current_app.logger.info(f"Enqueued job {job.id} for apply_instance_config for instance {instance.id}")
                return jsonify({"message": f'Configuration for instance "{instance.name}" saved and update task queued.'}), 202
            else:
                current_app.logger.error(f"Failed to enqueue apply_instance_config task for instance {instance.id}")
                update_instance(instance.id, status=InstanceStatus.ERROR)
                return jsonify({"error": {"message": "Error queuing configuration update task."}}), 500

        except Exception as e:
            current_app.logger.error(f"Error saving updated config files for instance {instance.id}: {e}", exc_info=True)
            return jsonify({"error": {"message": f'Error saving configuration files: {str(e)}'}}), 500
        finally:
            if not lock_transferred:
                release_lock('instance', instance.id, lock_token)

    # GET request
    current_configs = {
        'server.cfg': _read_instance_config(host_name, instance.id, 'server.cfg'),
        'mappool.txt': _read_instance_config(host_name, instance.id, 'mappool.txt'),
        'access.txt': _read_instance_config(host_name, instance.id, 'access.txt'),
        'workshop.txt': _read_instance_config(host_name, instance.id, 'workshop.txt')
    }
    
    # Read factories
    instance_factories_dir = os.path.join('configs', host_name, str(instance.id), 'factories')
    factories_content = {}
    if os.path.exists(instance_factories_dir):
        for filename in os.listdir(instance_factories_dir):
            if filename.endswith('.factories'):
                filepath = os.path.join(instance_factories_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        factories_content[filename] = f.read()
                except Exception as e:
                    current_app.logger.error(f"Error reading factory {filename}: {e}")
    
    current_configs['factories'] = factories_content
    
    return jsonify({"data": current_configs})

@instance_api_bp.route('/check-name', methods=['GET'])
# This route is often used for frontend validation before form submission,
# so it might not strictly need JWT protection if it doesn't reveal sensitive data
# and is only checking for name uniqueness based on public/semi-public info.
# For now, let's keep it unprotected for potentially easier frontend integration.
# If it needs protection, add @jwt_required here.
def check_instance_name():
    """Checks if an instance name is unique for a given host."""
    host_id = request.args.get('host_id', type=int)
    name = request.args.get('name', type=str)

    if not host_id or not name:
        # Return error if parameters are missing, though JS should prevent this
        return jsonify({'error': 'Missing host_id or name parameter'}), 400

    # Check if an instance with this name already exists on the specified host
    existing_instance = QLInstance.query.filter(
        QLInstance.host_id == host_id,
        db.func.lower(QLInstance.name) == name.lower()
    ).first()

    is_unique = existing_instance is None
    return jsonify({'is_unique': is_unique})



# Route for getting available ports for a host
# Note: get_available_ports was moved to host_routes.py as GET /api/hosts/<int:host_id>/available-ports
# The original @instance_bp.route('/get-available-ports/<int:host_id>') is now removed from here.
