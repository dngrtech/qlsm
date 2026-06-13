import os
import re
import shutil
import uuid
from flask import Blueprint, request, current_app, jsonify
import sqlalchemy
from ui import db
from ui.models import QLInstance, Host, HostStatus, InstanceStatus
from ui.lan_rate_policy import (
    lan_rate_unsupported_message,
    would_enable_unsupported_lan_rate,
)
from ui.preset_support import resolve_preset_path, resolve_preset_subdir
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
PROTECTED_CONFIG_FILES = {'server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt'}
ALLOWED_CONFIG_EXTENSIONS = {'.cfg', '.txt', '.ent'}
ALLOWED_FACTORY_EXTENSIONS = {'.factories'}
RESERVED_CONFIG_FOLDER_NAMES = {'scripts', 'factories'}
_FOLDER_NAME_RE = re.compile(r'^[A-Za-z0-9._-]+$')
MAX_CONFIG_PATH_DEPTH = 2  # one folder + filename


def _validate_path_segment(name, allowed_extensions=None):
    """Validate a single path segment (file or folder name).

    When allowed_extensions is None, treat name as a folder segment and skip
    the extension check.
    """
    if not isinstance(name, str) or not name:
        return "Invalid name"
    if '/' in name or '\\' in name or '..' in name or name.startswith('.'):
        return f"Invalid name: {name}"
    if not _FOLDER_NAME_RE.match(name):
        return f"Invalid characters in: {name}"
    if len(name) > 64:
        return f"Name too long: {name}"
    if allowed_extensions is not None:
        ext = os.path.splitext(name)[1].lower()
        if ext not in allowed_extensions:
            return f"Disallowed extension {ext} for {name}"
    return None


def _validate_relative_path(path, allowed_extensions, max_depth=MAX_CONFIG_PATH_DEPTH):
    """Validate a relative file path. Each segment is validated; depth is capped."""
    if not isinstance(path, str) or not path:
        return "Invalid path"
    if path.startswith('/') or path.endswith('/'):
        return f"Invalid path: {path}"
    segments = path.split('/')
    if len(segments) > max_depth:
        return f"Path too deep: {path} (max depth {max_depth})"
    for i, segment in enumerate(segments):
        is_last = (i == len(segments) - 1)
        err = _validate_path_segment(
            segment,
            allowed_extensions if is_last else None,
        )
        if err:
            return err
    return None


def _validate_filename(name, allowed_extensions):
    """Backwards-compatible flat-name validator (no `/`)."""
    return _validate_relative_path(name, allowed_extensions, max_depth=1)


def _validate_configs_map(configs_data, require_protected=True):
    """Validate configs map. Keys may be relative paths up to MAX_CONFIG_PATH_DEPTH.

    Returns (error_message, status_code) or (None, None).
    """
    if not isinstance(configs_data, dict):
        return "configs must be a dict", 400
    for path, content in configs_data.items():
        err = _validate_relative_path(path, ALLOWED_CONFIG_EXTENSIONS)
        if err:
            return err, 400
        if content is not None and not isinstance(content, str):
            return f"Config content for {path} must be a string", 400
        # Reject reserved-folder collisions
        if '/' in path:
            top = path.split('/', 1)[0]
            if top.lower() in RESERVED_CONFIG_FOLDER_NAMES:
                return f"Reserved folder name: {top}", 400
    missing = PROTECTED_CONFIG_FILES - set(configs_data.keys())
    if require_protected and missing:
        return f"Built-in files cannot be removed: {', '.join(sorted(missing))}", 400
    return None, None


def _validate_factories_map(factories_data):
    """Validate factories map. Returns (error_message, status_code) or (None, None)."""
    if not isinstance(factories_data, dict):
        return "factories must be a dict", 400
    for filename, content in factories_data.items():
        err = _validate_filename(filename, ALLOWED_FACTORY_EXTENSIONS)
        if err:
            return err, 400
        if content is not None and not isinstance(content, str):
            return f"Factory content for {filename} must be a string", 400
    return None, None


def _should_sync_configs(configs_data):
    """Return True when the payload represents the full file-manager config set."""
    if not isinstance(configs_data, dict):
        return False
    received = set(configs_data.keys())
    has_custom_file = any(filename not in PROTECTED_CONFIG_FILES for filename in received)
    return has_custom_file or PROTECTED_CONFIG_FILES.issubset(received)


def _validate_config_folders(folders):
    """Validate config_folders array. Returns (error_message, status_code) or (None, None)."""
    if folders is None:
        return None, None
    if not isinstance(folders, list):
        return "config_folders must be a list", 400
    for name in folders:
        if not isinstance(name, str):
            return "config_folders entries must be strings", 400
        err = _validate_path_segment(name, None)
        if err:
            return err, 400
        if name.lower() in RESERVED_CONFIG_FOLDER_NAMES:
            return f"Reserved folder name: {name}", 400
    return None, None


def _write_configs_to_disk(instance_dir, configs_data):
    """Write only the config files present in the map (creates parent dirs)."""
    os.makedirs(instance_dir, exist_ok=True)
    for rel_path, content in configs_data.items():
        full_path = os.path.join(instance_dir, rel_path)
        os.makedirs(os.path.dirname(full_path) or instance_dir, exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content if content is not None else '')


def _list_managed_files_recursive(instance_dir):
    """Yield relative paths of managed files (cfg/txt/ent) under instance_dir,
    excluding reserved subdirs (scripts/, factories/)."""
    for root, dirs, files in os.walk(instance_dir):
        if root == instance_dir:
            dirs[:] = [d for d in dirs if d.lower() not in RESERVED_CONFIG_FOLDER_NAMES]
        for fname in files:
            if os.path.splitext(fname)[1].lower() in ALLOWED_CONFIG_EXTENSIONS:
                full = os.path.join(root, fname)
                yield os.path.relpath(full, instance_dir).replace(os.sep, '/')


def _list_managed_folders(instance_dir):
    """Return top-level managed folders (excluding reserved subdirs)."""
    if not os.path.isdir(instance_dir):
        return []
    return [
        name for name in os.listdir(instance_dir)
        if os.path.isdir(os.path.join(instance_dir, name))
        and name.lower() not in RESERVED_CONFIG_FOLDER_NAMES
    ]


def _sync_configs_to_disk(instance_dir, configs_data, config_folders=None):
    """Write configs (nested supported), create empty folders, and remove orphans.

    config_folders semantics:
      - None         → caller did not supply the field. Preserve all existing
                       top-level folders (legacy/partial-client safety).
      - list (incl []) → caller explicitly listed the folders that must exist
                         after sync. Prune any other top-level folder not in
                         this list (or implied by a nested file path), but only
                         via os.rmdir (empty-only); folders that still contain
                         unmanaged content are left alone.
    """
    os.makedirs(instance_dir, exist_ok=True)
    folder_pruning_requested = config_folders is not None
    config_folders = list(config_folders or [])

    desired_folders = set(config_folders)
    for rel_path in configs_data.keys():
        if '/' in rel_path:
            desired_folders.add(rel_path.split('/', 1)[0])

    _write_configs_to_disk(instance_dir, configs_data)

    for folder in desired_folders:
        os.makedirs(os.path.join(instance_dir, folder), exist_ok=True)

    received_paths = set(configs_data.keys())
    for rel_path in list(_list_managed_files_recursive(instance_dir)):
        if rel_path in PROTECTED_CONFIG_FILES:
            continue
        if rel_path not in received_paths:
            try:
                os.remove(os.path.join(instance_dir, rel_path))
            except OSError as e:
                current_app.logger.error(f"Error removing config file {rel_path}: {e}")

    if folder_pruning_requested:
        for name in _list_managed_folders(instance_dir):
            if name in desired_folders:
                continue
            folder_path = os.path.join(instance_dir, name)
            try:
                os.rmdir(folder_path)
            except OSError as e:
                current_app.logger.warning(
                    f"Skipping non-empty orphan folder {folder_path}: {e}"
                )


def _sync_factories_to_disk(factories_dir, factories_data):
    """Write factories and remove managed factory files absent from the map."""
    os.makedirs(factories_dir, exist_ok=True)
    existing = {
        filename for filename in os.listdir(factories_dir)
        if os.path.isfile(os.path.join(factories_dir, filename))
        and os.path.splitext(filename)[1].lower() in ALLOWED_FACTORY_EXTENSIONS
    }
    received = set(factories_data.keys())

    for filename, content in factories_data.items():
        with open(os.path.join(factories_dir, filename), 'w') as f:
            f.write(content if content is not None else '')

    for filename in existing - received:
        try:
            os.remove(os.path.join(factories_dir, filename))
        except OSError as e:
            current_app.logger.error(f"Error removing factory {filename}: {e}")

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
    """Reads content from the registered default preset."""
    default_config_path = os.path.join(resolve_preset_path('default'), filename)
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
    hostname = (data.get('hostname') or '').strip()
    lan_rate_enabled = data.get('lan_rate_enabled', False) # Default to False
    configs_data = data.get('configs', {}) # Expect a 'configs' object in JSON
    qlx_plugins, qlx_err = _validate_qlx_plugins(data.get('qlx_plugins'))
    if qlx_err:
        return jsonify({"error": {"message": qlx_err}}), 400
    checked_plugins = data.get('checked_plugins')
    if checked_plugins is not None:
        if (
            not isinstance(checked_plugins, list) or
            not all(isinstance(plugin, str) for plugin in checked_plugins)
        ):
            return jsonify({"error": {"message": "checked_plugins must be a list of strings"}}), 400
        qlx_plugins_str = ', '.join(checked_plugins)
        qlx_plugins, qlx_err = _validate_qlx_plugins(qlx_plugins_str)
        if qlx_err:
            return jsonify({"error": {"message": qlx_err}}), 400

    # Basic validation
    if not name or not host_id or not port or not hostname:
        return jsonify({"error": {"message": "Name, Host ID, Port, and Server Hostname are required."}}), 400

    if len(hostname) > 64:
        return jsonify({"error": {"message": "Server Hostname must be 64 characters or fewer."}}), 400

    try:
        port_int = int(port)
        host_id_int = int(host_id)

        selected_host = get_host(host_id_int)
        if not selected_host or selected_host.status != HostStatus.ACTIVE:
            return jsonify({"error": {"message": "Invalid or inactive host selected."}}), 400

        if would_enable_unsupported_lan_rate(
            selected_host,
            current_enabled=False,
            requested_enabled=lan_rate_enabled,
        ):
            return jsonify({"error": {"message": lan_rate_unsupported_message(selected_host)}}), 400

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

        configs_to_save = dict(configs_data) if isinstance(configs_data, dict) else configs_data
        if isinstance(configs_to_save, dict):
            for filename in PROTECTED_CONFIG_FILES:
                if filename not in configs_to_save:
                    configs_to_save[filename] = _read_default_config(filename)
        err, code = _validate_configs_map(configs_to_save)
        if err:
            return jsonify({"error": {"message": err}}), code

        config_folders_create = data.get('config_folders') or []
        if config_folders_create:
            err, code = _validate_config_folders(config_folders_create)
            if err:
                return jsonify({"error": {"message": err}}), code

        if 'factories' in data:
            factories_data = data.get('factories', {})
            err, code = _validate_factories_map(factories_data)
            if err:
                return jsonify({"error": {"message": err}}), code

        # --- Try creating the instance ---
        instance = create_instance(
            name=name, host_id=host_id_int, port=port_int, hostname=hostname, 
            lan_rate_enabled=bool(lan_rate_enabled), qlx_plugins=qlx_plugins
        )

        # --- Save submitted config content to files ---
        instance_config_dir = os.path.join('configs', selected_host.name, str(instance.id))
        os.makedirs(instance_config_dir, exist_ok=True)
        current_app.logger.info(f"Created instance config directory: {instance_config_dir}")

        _sync_configs_to_disk(instance_config_dir, configs_to_save, config_folders_create)
        current_app.logger.info(
            f"Synced {len(configs_to_save)} config files and "
            f"{len(config_folders_create)} folders for instance {instance.id}"
        )

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
            default_scripts_dir = resolve_preset_subdir('default', 'scripts')
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

        instance_user_hooks_dir = os.path.join(instance_config_dir, 'user-hooks')
        os.makedirs(instance_user_hooks_dir, exist_ok=True)
        
        if 'factories' in data:
            # User explicitly provided factory selection - only deploy what they selected
            factories_data = data.get('factories', {})
            _sync_factories_to_disk(instance_factories_dir, factories_data)
            current_app.logger.info(f"User selected {len(factories_data)} factories for instance {instance.id}")
        else:
            # No factories key in request - copy all defaults (legacy/fallback behavior)
            default_factories_dir = resolve_preset_subdir('default', 'factories')
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
        new_hostname = (data.get('hostname') or '').strip() or None

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
                    if len(new_hostname) > 64:
                        return jsonify({"error": {"message": "Server Hostname must be 64 characters or fewer."}}), 400
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

    if would_enable_unsupported_lan_rate(
        instance.host,
        current_enabled=instance.lan_rate_enabled,
        requested_enabled=lan_rate_enabled,
    ):
        return jsonify({"error": {"message": lan_rate_unsupported_message(instance.host)}}), 400

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
        filter_mode: 'time', 'lines', or 'all' (default: 'lines')
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
    if filter_mode not in ('time', 'lines', 'all'):
        return jsonify({"error": {"message": "filter_mode must be 'time', 'lines', or 'all'"}}), 400

    # Validate lines (sensible range) — not applicable for 'all' mode
    if filter_mode != 'all' and (lines < 10 or lines > 10000):
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

        metadata_update_kwargs = {}
        new_name = data.get('name')
        if new_name is not None:
            if not isinstance(new_name, str):
                return jsonify({"error": {"message": "Name must be a string"}}), 400
            stripped_name = new_name.strip()
            if not stripped_name:
                return jsonify({"error": {"message": "Name cannot be empty"}}), 400
            existing_instance = QLInstance.query.filter(
                db.func.lower(QLInstance.name) == stripped_name.lower()
            ).first()
            if existing_instance and existing_instance.id != instance.id:
                return jsonify({"error": {"message": f"An instance with the name '{stripped_name}' already exists."}}), 409
            metadata_update_kwargs['name'] = stripped_name

        new_hostname = data.get('hostname')
        if new_hostname is not None:
            if not isinstance(new_hostname, str):
                return jsonify({"error": {"message": "Server Hostname must be a string"}}), 400
            stripped_hostname = new_hostname.strip()
            if not stripped_hostname:
                return jsonify({"error": {"message": "Server Hostname cannot be empty."}}), 400
            if len(stripped_hostname) > 64:
                return jsonify({"error": {"message": "Server Hostname must be 64 characters or fewer."}}), 400
            metadata_update_kwargs['hostname'] = stripped_hostname

        if (
            'lan_rate_enabled' in data and
            would_enable_unsupported_lan_rate(
                instance.host,
                current_enabled=instance.lan_rate_enabled,
                requested_enabled=data.get('lan_rate_enabled'),
            )
        ):
            return jsonify({"error": {"message": lan_rate_unsupported_message(instance.host)}}), 400

        configs_present = 'configs' in data
        configs_to_save = data.get('configs', {}) if configs_present else None
        if configs_present:
            err, code = _validate_configs_map(configs_to_save, require_protected=True)
            if err:
                return jsonify({"error": {"message": err}}), code

        factories_present = 'factories' in data
        factories_to_save = data.get('factories', {}) if factories_present else None
        if factories_present:
            err, code = _validate_factories_map(factories_to_save)
            if err:
                return jsonify({"error": {"message": err}}), code

        config_folders_present = 'config_folders' in data
        config_folders_value = data.get('config_folders') if config_folders_present else None
        if config_folders_present:
            err, code = _validate_config_folders(config_folders_value)
            if err:
                return jsonify({"error": {"message": err}}), code

        draft_id = data.get('draft_id')
        scripts_to_save = data.get('scripts', {})
        if draft_id:
            from ui.routes.draft_routes import _validate_draft_id, _draft_exists
            if not _validate_draft_id(draft_id):
                return jsonify({"error": {"message": "Invalid draft_id"}}), 400
            if not _draft_exists(draft_id):
                return jsonify({"error": {"message": "Draft not found. It may have expired."}}), 400

        update_kwargs = dict(status=InstanceStatus.CONFIGURING)
        update_kwargs.update(metadata_update_kwargs)
        if 'lan_rate_enabled' in data:
            update_kwargs['lan_rate_enabled'] = bool(data.get('lan_rate_enabled'))

        lock_token = str(uuid.uuid4())
        if not acquire_lock('instance', instance.id, lock_token, ttl=360):
            return jsonify({"error": {"message": f'Another operation is running on instance "{instance.name}". Please wait for it to complete.'}}), 409
        lock_transferred = False
        status_committed = False

        try:
            checked_plugins = data.get('checked_plugins')
            if checked_plugins is not None:
                if (
                    not isinstance(checked_plugins, list) or
                    not all(isinstance(plugin, str) for plugin in checked_plugins)
                ):
                    return jsonify({"error": {"message": "checked_plugins must be a list of strings"}}), 400
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

            if configs_present:
                _sync_configs_to_disk(
                    instance_config_dir,
                    configs_to_save,
                    config_folders_value if config_folders_present else None,
                )
                current_app.logger.info(
                    f"Synced {len(configs_to_save)} config files and "
                    f"{len(config_folders_value or [])} folders for instance {instance.id}"
                )

            # Handle scripts via draft or legacy
            if draft_id:
                from ui.routes.draft_routes import (
                    _get_draft_scripts_path, _get_draft_base_path
                )

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

            # Handle factories updates when the client sends the full factories map.
            if factories_present:
                instance_factories_dir = os.path.join(instance_config_dir, 'factories')
                _sync_factories_to_disk(instance_factories_dir, factories_to_save)

            try:
                update_instance(instance.id, **update_kwargs)
                status_committed = True
            except sqlalchemy.exc.IntegrityError:
                db.session.rollback()
                return jsonify({"error": {"message": f"An instance with the name '{new_name}' already exists."}}), 409

            restart = data.get('restart', True)
            reconcile_lan_rate_network = 'lan_rate_enabled' in data
            job = enqueue_task(
                apply_instance_config,
                instance.id,
                restart=restart,
                reconcile_lan_rate_network=reconcile_lan_rate_network,
                lock_token=lock_token,
                on_failure=instance_job_failure_handler,
            )
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
            if status_committed:
                try:
                    update_instance(instance.id, status=InstanceStatus.ERROR)
                except Exception as status_error:
                    current_app.logger.error(f"Failed to mark instance {instance.id} ERROR after config save failure: {status_error}", exc_info=True)
            return jsonify({"error": {"message": f'Error saving configuration files: {str(e)}'}}), 500
        finally:
            if not lock_transferred:
                release_lock('instance', instance.id, lock_token)

    # GET request
    current_configs = {}
    if os.path.isdir(instance_config_dir):
        for rel_path in _list_managed_files_recursive(instance_config_dir):
            full_path = os.path.join(instance_config_dir, rel_path)
            try:
                with open(full_path, 'r') as f:
                    current_configs[rel_path] = f.read()
            except OSError as e:
                current_app.logger.error(f"Error reading config file {rel_path}: {e}")

    for filename in PROTECTED_CONFIG_FILES:
        if filename not in current_configs:
            current_configs[filename] = _read_default_config(filename)

    current_configs['config_folders'] = _list_managed_folders(instance_config_dir)

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
