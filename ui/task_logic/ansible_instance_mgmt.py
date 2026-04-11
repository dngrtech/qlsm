import logging
import os
import random
import re
import shutil
import time
import subprocess
from pathlib import Path
from rq import get_current_job

# Import database and models - requires app context
from ui import db
from ui.models import QLInstance, InstanceStatus, Host # Need Host for cleanup path
from .common import append_log # Import from the common module
from .ansible_runner import _run_ansible_playbook
from .self_host_network import is_self_host, with_self_host_network_extravars

from .zmq_utils import ensure_zmq_rcon_setup


SYSTEM_PLUGINS = ['serverchecker']


# Validates and sanitizes input to prevent injection or malformed args
def _validate_instance_fields(instance):
    required_fields = [
        'port', 'hostname', 'id', 'zmq_rcon_port', 'zmq_rcon_password',
        'zmq_stats_port', 'zmq_stats_password'
    ]
    for field in required_fields:
        value = getattr(instance, field, None)
        if value is None or str(value).strip() == "":
            raise ValueError(f"Instance missing required field: {field}")
        
        # Basic sanity check for string fields to prevent shell injection attempts
        # allowing only alphanumeric, dashes, underscores, dots, and colons in most fields
        if isinstance(value, str) and field != 'hostname': # Hostname might allow more, but we quote it
             if any(char in value for char in [';', '&', '|', '$', '`', '(', ')', '<', '>', '\\']):
                 raise ValueError(f"Invalid character in field {field}: {value}")

    # Ensure port is an integer
    try:
        int(instance.port)
        int(instance.zmq_rcon_port)
        int(instance.zmq_stats_port)
    except ValueError:
        raise ValueError("Ports must be integers")


def _prepare_instance_zmq(instance):
    """Ensure ZMQ RCON is set up and commit any changes."""
    ensure_zmq_rcon_setup(instance)
    if db.session.dirty:
        db.session.commit()


def _self_host_redis_args(instance):
    if not is_self_host(getattr(instance, "host", None)):
        return []

    redis_password = (os.environ.get("REDIS_PASSWORD") or "").strip()
    if not redis_password:
        raise ValueError("Self-host instance Redis password is not configured.")

    return [
        '+set qlx_redisAddress "127.0.0.1:6379"',
        f'+set qlx_redisPassword "{redis_password}"',
    ]


def _build_qlds_args_string(instance):
    _validate_instance_fields(instance)

    homepath = f'/home/ql/qlds-{instance.port}'

    parts = []

    if instance.lan_rate_enabled:
        parts += ['+set sv_serverType 1', '+set sv_lanForceRate 1']
    else:
        parts += ['+set sv_serverType 2', '+set sv_lanForceRate 0']

    redis_db_index = instance.port - 27959
    parts += [
        '+set net_strict 1',
        f'+set net_port {instance.port}',
        f'+set sv_hostname "{instance.hostname}"',
        f'+set qlx_serverBrandName "{instance.hostname}"',
    ]
    parts += _self_host_redis_args(instance)
    parts += [
        f'+set qlx_redisDatabase {redis_db_index}',
        f'+set fs_homepath {homepath}',
        f'+set qlx_pluginsPath {homepath}/minqlx-plugins',
        # ZMQ RCON
        '+set zmq_rcon_enable 1',
        f'+set zmq_rcon_port {instance.zmq_rcon_port}',
        f'+set zmq_rcon_password "{instance.zmq_rcon_password}"',
        # ZMQ Stats (zmq_stats_enable is set by the minqlx launch script)
        f'+set zmq_stats_port {instance.zmq_stats_port}',
        f'+set zmq_stats_password "{instance.zmq_stats_password}"',
    ]

    user_plugins = [p.strip() for p in instance.qlx_plugins.split(',') if p.strip()] if instance.qlx_plugins else []
    all_plugins = SYSTEM_PLUGINS + [p for p in user_plugins if p not in SYSTEM_PLUGINS]
    parts.append(f'+set qlx_plugins "{", ".join(all_plugins)}"')

    return ' '.join(parts)


log = logging.getLogger(__name__)


def _extract_ansible_failure_detail(stdout_content, stderr_content, rc):
    match = re.search(r'"msg":\s*"([^"]+)"', stdout_content or "")
    if match:
        return match.group(1)
    for source in (stderr_content, stdout_content):
        if source:
            for line in reversed(source.splitlines()):
                line = line.strip()
                if line:
                    return line[:400]
    return f"Ansible runner failed with RC: {rc}"


def deploy_instance_logic(instance_id):
    """
    Logic for deploying a QL instance via Ansible.
    """
    job = get_current_job()
    instance = None
    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found.")
            return f"Error: Instance {instance_id} not found."

        # --- Check for associated host BEFORE proceeding ---
        if not instance.host:
            log.error(f"Host not found for instance {instance.id}.")
            append_log(instance, "Task failed: Associated host not found.")
            instance.status = InstanceStatus.ERROR
            db.session.commit() # Commit the ERROR status
            return f"Error during instance {instance.id} deployment: Host not found"
        # --- End host check ---

        append_log(instance, f"Task started: deploy_instance (Job ID: {job.id})")
        instance.status = InstanceStatus.DEPLOYING
        db.session.commit() # Commit DEPLOYING status
        log.info(f"Instance {instance_id} status set to DEPLOYING.")

        # Ensure ZMQ setup is ready before building args
        _prepare_instance_zmq(instance)
        
        # Prepare extravars specific to deployment (now safe to access instance.host.name)
        qlds_args_string = _build_qlds_args_string(instance)

        deploy_extravars = {
            'port': instance.port,
            'host_name': instance.host.name, # Pass the host name (used for config path)
            'qlds_args': qlds_args_string, # Pass the constructed args for the service
            'lan_rate_enabled': instance.lan_rate_enabled # Pass for conditional iptables/sysctl
        }
        deploy_extravars = with_self_host_network_extravars(instance, deploy_extravars)

        # Pass the instance object directly to the helper
        runner_result, error_msg = _run_ansible_playbook(
            instance, # Pass instance object
            'add_qlds_instance.yml', # Use the new playbook for adding instances
            extravars=deploy_extravars
        )


        if error_msg: # Handle errors from helper function (e.g., host missing details)
            # Status already set to ERROR in helper if possible
            return f"Error during instance {instance_id} deployment: {error_msg}"

        if runner_result is None: # Should not happen if error_msg is None, but check anyway
             raise Exception("Ansible runner did not return a result unexpectedly.")

        # Check result and update status - Read stdout and check for "no hosts matched"
        no_hosts_matched = False
        stdout_content = runner_result.stdout() if hasattr(runner_result, 'stdout') and callable(runner_result.stdout) else getattr(runner_result, '_stdout', "")
        stderr_content = getattr(runner_result, '_stderr', "")

        append_log(instance, f"Ansible execution finished. RC: {runner_result.rc}.")

        # Determine final status based ONLY on rc and stdout content check
        if runner_result.rc == 0:
            # Primary check: Look for the specific message in stdout
            if "skipping: no hosts matched" in stdout_content:
                 no_hosts_matched = True
            # If rc is 0 and the specific message wasn't found, it's a success
            else: # not no_hosts_matched implicitly true here
                instance.status = InstanceStatus.RUNNING
                append_log(instance, f"Task finished successfully. Status: RUNNING.")
                db.session.commit()
                log.info(f"Finished task deploy_instance for instance_id: {instance_id}. Status: RUNNING")
                return f"Instance {instance_id} deployment successful. Status: RUNNING"

        # Handle failures (rc != 0 OR (rc == 0 AND no_hosts_matched))
        instance.status = InstanceStatus.ERROR
        if no_hosts_matched: # This condition is only met if rc was 0 but the string was found
            error_detail = "No hosts matched in inventory (detected in stdout)."
            log.error(f"Ansible runner indicated success (RC=0) but no hosts matched for instance {instance_id} deployment: {error_detail}")
            append_log(instance, f"Task failed: {error_detail}.")
        else: # This handles the rc != 0 case
            error_detail = _extract_ansible_failure_detail(
                stdout_content,
                stderr_content,
                runner_result.rc,
            )
            log.error(f"Ansible runner failed for instance {instance_id} deployment. RC: {runner_result.rc}")
            append_log(instance, f"Task failed: {error_detail}.")

        db.session.commit() # Commit ERROR status for both failure cases
        return f"Error: Instance {instance_id} deployment failed. {error_detail}"

    except Exception as e:
        log.exception(f"Exception in deploy_instance for instance_id {instance_id}: {e}")
        if instance:
            try:
                instance.status = InstanceStatus.ERROR
                append_log(instance, f"Task failed with exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update instance status/log on exception: {commit_err}")
        return f"Error during instance {instance_id} deployment: {e}"


def restart_instance_logic(instance_id):
    """
    Logic for restarting a QL instance via Ansible.
    """
    job = get_current_job()
    instance = None
    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found.")
            return f"Error: Instance {instance_id} not found."
            
        # --- Check for associated host BEFORE proceeding ---
        if not instance.host:
            log.error(f"Host not found for instance {instance.id} during restart.")
            append_log(instance, "Task failed: Associated host not found.")
            instance.status = InstanceStatus.ERROR
            db.session.commit()
            return f"Error during instance {instance.id} restart: Host not found"

        append_log(instance, f"Task started: restart_instance (Job ID: {job.id})")
        instance.status = InstanceStatus.RESTARTING
        db.session.commit()
        log.info(f"Instance {instance_id} status set to RESTARTING.")

        # Ensure ZMQ setup is ready before building args
        _prepare_instance_zmq(instance)
        
        # Construct qlds_args
        qlds_args_string = _build_qlds_args_string(instance)

        # Prepare extravars for sync_instance_configs_and_restart.yml
        # We use this playbook because it re-templates the service file with new args AND restarts
        restart_extravars = {
            'host_name': instance.host.name,
            'port': instance.port, 
            'id': instance.id,
            'qlds_args': qlds_args_string
        }

        # Pass the instance object directly to the helper
        runner_result, error_msg = _run_ansible_playbook(
            instance, # Pass instance object
            'sync_instance_configs_and_restart.yml',
            extravars=restart_extravars
        )

        if error_msg: # Handle errors from helper function (e.g., host missing details)
            return f"Error during instance {instance_id} restart: {error_msg}"

        if runner_result is None:
             raise Exception("Ansible runner did not return a result unexpectedly.")

        # Check result and update status
        stdout_content = runner_result.stdout() if hasattr(runner_result, 'stdout') and callable(runner_result.stdout) else getattr(runner_result, '_stdout', "")
        stderr_content = getattr(runner_result, '_stderr', "")

        if runner_result.rc == 0:
            instance.status = InstanceStatus.RUNNING
            append_log(instance, f"Task finished successfully. Status: RUNNING.")
            db.session.commit()
            log.info(f"Finished task restart_instance for instance_id: {instance_id}. Status: RUNNING")
            return f"Instance {instance_id} restart successful. Status: RUNNING"
        else:
            instance.status = InstanceStatus.ERROR
            append_log(instance, f"Task failed: Ansible runner RC: {runner_result.rc}.")
            db.session.commit()
            log.error(f"Ansible runner failed for instance {instance_id} restart. RC: {runner_result.rc}")
            return f"Error: Instance {instance_id} restart failed. RC: {runner_result.rc}"

    except Exception as e:
        log.exception(f"Exception in restart_instance for instance_id {instance_id}: {e}")
        if instance:
            try:
                instance.status = InstanceStatus.ERROR
                append_log(instance, f"Task failed with exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update instance status/log on exception: {commit_err}")
        return f"Error during instance {instance_id} restart: {e}"


def stop_instance_logic(instance_id):
    """
    Logic for stopping a QL instance via Ansible.
    """
    job = get_current_job()
    instance = None
    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found.")
            return f"Error: Instance {instance_id} not found."

        append_log(instance, f"Task started: stop_instance (Job ID: {job.id})")
        instance.status = InstanceStatus.STOPPING
        db.session.commit()
        log.info(f"Instance {instance_id} status set to STOPPING.")

        stop_extravars = {
            'service_state': 'stopped',
            'port': instance.port,
            'id': instance.id
        }

        runner_result, error_msg = _run_ansible_playbook(
            instance,
            'manage_qlds_service.yml',
            extravars=stop_extravars
        )

        if error_msg:
            return f"Error during instance {instance_id} stop: {error_msg}"

        if runner_result is None:
            raise Exception("Ansible runner did not return a result unexpectedly.")

        stdout_content = runner_result.stdout() if hasattr(runner_result, 'stdout') and callable(runner_result.stdout) else getattr(runner_result, '_stdout', "")
        stderr_content = getattr(runner_result, '_stderr', "")

        if runner_result.rc == 0:
            instance.status = InstanceStatus.STOPPED
            append_log(instance, f"Task finished successfully. Status: STOPPED.")
            db.session.commit()
            log.info(f"Finished task stop_instance for instance_id: {instance_id}. Status: STOPPED")
            return f"Instance {instance_id} stop successful. Status: STOPPED"
        else:
            instance.status = InstanceStatus.ERROR
            append_log(instance, f"Task failed: Ansible runner RC: {runner_result.rc}.")
            db.session.commit()
            log.error(f"Ansible runner failed for instance {instance_id} stop. RC: {runner_result.rc}")
            return f"Error: Instance {instance_id} stop failed. RC: {runner_result.rc}"

    except Exception as e:
        log.exception(f"Exception in stop_instance for instance_id {instance_id}: {e}")
        if instance:
            try:
                instance.status = InstanceStatus.ERROR
                append_log(instance, f"Task failed with exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update instance status/log on exception: {commit_err}")
        return f"Error during instance {instance_id} stop: {e}"


def start_instance_logic(instance_id):
    """
    Logic for starting a QL instance via Ansible.
    """
    job = get_current_job()
    instance = None
    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found.")
            return f"Error: Instance {instance_id} not found."

        append_log(instance, f"Task started: start_instance (Job ID: {job.id})")
        instance.status = InstanceStatus.STARTING
        db.session.commit()
        log.info(f"Instance {instance_id} status set to STARTING.")

        start_extravars = {
            'service_state': 'started',
            'port': instance.port,
            'id': instance.id,
            'lan_rate_enabled': instance.lan_rate_enabled
        }
        start_extravars = with_self_host_network_extravars(instance, start_extravars)

        runner_result, error_msg = _run_ansible_playbook(
            instance,
            'manage_qlds_service.yml',
            extravars=start_extravars
        )

        if error_msg:
            return f"Error during instance {instance_id} start: {error_msg}"

        if runner_result is None:
            raise Exception("Ansible runner did not return a result unexpectedly.")

        stdout_content = runner_result.stdout() if hasattr(runner_result, 'stdout') and callable(runner_result.stdout) else getattr(runner_result, '_stdout', "")
        stderr_content = getattr(runner_result, '_stderr', "")

        if runner_result.rc == 0:
            instance.status = InstanceStatus.RUNNING
            append_log(instance, f"Task finished successfully. Status: RUNNING.")
            db.session.commit()
            log.info(f"Finished task start_instance for instance_id: {instance_id}. Status: RUNNING")
            return f"Instance {instance_id} start successful. Status: RUNNING"
        else:
            instance.status = InstanceStatus.ERROR
            append_log(instance, f"Task failed: Ansible runner RC: {runner_result.rc}.")
            db.session.commit()
            log.error(f"Ansible runner failed for instance {instance_id} start. RC: {runner_result.rc}")
            return f"Error: Instance {instance_id} start failed. RC: {runner_result.rc}"

    except Exception as e:
        log.exception(f"Exception in start_instance for instance_id {instance_id}: {e}")
        if instance:
            try:
                instance.status = InstanceStatus.ERROR
                append_log(instance, f"Task failed with exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update instance status/log on exception: {commit_err}")
        return f"Error during instance {instance_id} start: {e}"


def apply_instance_config_logic(instance_id, restart=True):
    """
    Logic for applying configuration to a QL instance via Ansible.
    This involves syncing config files and optionally restarting the service.
    """
    job = get_current_job()
    job_id = job.id if job else "MANUAL"
    
    instance = None
    original_status = None # To revert to if Ansible succeeds
    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found.")
            return f"Error: Instance {instance_id} not found."

        if not instance.host:
            log.error(f"Host not found for instance {instance.id} during config apply.")
            append_log(instance, "Task failed: Associated host not found.")
            instance.status = InstanceStatus.ERROR
            db.session.commit()
            return f"Error during instance {instance.id} config apply: Host not found"

        original_status = instance.status # Store original status
        append_log(instance, f"Task started: apply_instance_config (Job ID: {job_id}, Restart: {restart})")
        instance.status = InstanceStatus.CONFIGURING
        db.session.commit()
        log.info(f"Instance {instance_id} status set to CONFIGURING.")

        # Ensure ZMQ setup is ready before building args
        _prepare_instance_zmq(instance)
        
        qlds_args_string = _build_qlds_args_string(instance)

        # Prepare extravars
        apply_config_extravars = {
            'host_name': instance.host.name, # For sourcing configs
            'port': instance.port,         # Add port to target correct service name for restart
            'id': instance.id,             # Keep id
            'qlds_args': qlds_args_string, # Pass constructed args for service re-templating
            'restart_service': restart     # Pass restart flag
        }
        apply_config_extravars = with_self_host_network_extravars(instance, apply_config_extravars)

        # Run the new playbook: sync_instance_configs_and_restart.yml
        runner_result, error_msg = _run_ansible_playbook(
            instance, # Pass instance object
            'sync_instance_configs_and_restart.yml',
            extravars=apply_config_extravars
        )

        if error_msg: # Handle errors from helper function (e.g., host missing details)
            # Status already set to ERROR in helper if possible
            return f"Error during instance {instance_id} config apply: {error_msg}"

        if runner_result is None:
             raise Exception("Ansible runner did not return a result unexpectedly.")

        # Check result and update status
        stdout_content = runner_result.stdout() if hasattr(runner_result, 'stdout') and callable(runner_result.stdout) else getattr(runner_result, '_stdout', "")
        stderr_content = getattr(runner_result, '_stderr', "")

        if runner_result.rc == 0:
            # If Ansible playbook was successful, the instance should be running with new config.
            final_status = InstanceStatus.RUNNING
            
            status_msg = ""
            if original_status == InstanceStatus.STOPPED:
                # If it was stopped, and we restarted, it's now running. 
                # If we didn't restart, it's still stopped? 
                # Actually, sync_instance_configs_and_restart.yml handles the service state.
                # If restart_service is True, it restarts (ensures started).
                # If restart_service is False, it doesn't touch service state.
                # So if it was STOPPED and we didn't restart, it remains STOPPED.
                if restart:
                     status_msg = "Instance started with new config."
                else:
                     status_msg = "Config synced (Instance remains STOPPED)."
                     final_status = InstanceStatus.STOPPED
            else:
                 # It was running (or other).
                 if restart:
                     status_msg = "Config applied and instance restarted."
                 else:
                     status_msg = "Config synced (Restart skipped)."
                     final_status = InstanceStatus.UPDATED

            append_log(instance, f"Task finished successfully. {status_msg} Status: {final_status.value}.")

            instance.status = final_status
            db.session.commit()
            log.info(f"Finished task apply_instance_config for instance_id: {instance_id}. Status: {final_status.value}")
            return f"Instance {instance_id} config application successful. Status: {final_status.value}"
        else:
            instance.status = InstanceStatus.ERROR
            append_log(instance, f"Task failed: Ansible runner RC: {runner_result.rc}.")
            db.session.commit()
            log.error(f"Ansible runner failed for instance {instance_id} config apply. RC: {runner_result.rc}")
            return f"Error: Instance {instance_id} config application failed. RC: {runner_result.rc}"

    except Exception as e:
        log.exception(f"Exception in apply_instance_config_logic for instance_id {instance_id}: {e}")
        if instance:
            try:
                instance.status = InstanceStatus.ERROR
                append_log(instance, f"Task failed with exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update instance status/log on exception: {commit_err}")
        return f"Error during instance {instance_id} config application: {e}"


def delete_instance_logic(instance_id):
    """
    Logic for deleting a QL instance via Ansible and cleaning up local files.
    Ensures cleanup happens even if Ansible playbook fails.
    """
    job = get_current_job()
    instance = None
    ansible_failed = False # Flag to track ansible failure for return message
    ansible_rc = None # Store ansible return code

    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found for deletion.")
            return f"Error: Instance {instance_id} not found."

        host = instance.host
        if not host:
            log.error(f"Host not found for instance {instance.id} during deletion.")
            # Cannot append log to instance if it doesn't exist, but we should still try to delete if possible?
            # For now, let's fail the task if host is missing.
            # If we wanted to delete instance record even without host, logic would need adjustment.
            # append_log(instance, "Task failed: Associated host not found.") # This would fail
            # instance.status = InstanceStatus.ERROR # This would fail
            # db.session.commit() # This would fail
            return f"Error during instance {instance.id} deletion: Host not found"

        append_log(instance, f"Task started: delete_instance (Job ID: {job.id})")
        log.info(f"Instance {instance_id} deletion task started.")

        # Prepare extravars specific to deletion
        delete_extravars = {
            'service_action': 'delete',
            'port': instance.port, # Add port to target correct service name and directory
            'id': instance.id      # Keep id
        }
        delete_extravars = with_self_host_network_extravars(
            instance,
            delete_extravars,
            exclude_instance_id=instance.id,
        )

        # Pass the instance object directly to the helper
        runner_result, error_msg = _run_ansible_playbook(
            instance, # Pass instance object
            'manage_qlds_service.yml',
            extravars=delete_extravars
        )

        if error_msg: # Handle errors from helper function (e.g., host missing details)
            append_log(instance, f"Ansible helper function failed: {error_msg}. Proceeding with cleanup.")
            log.error(f"Ansible helper function failed for instance {instance_id} deletion: {error_msg}")
            ansible_failed = True
        elif runner_result is None:
            append_log(instance, f"Ansible runner did not return a result object. Proceeding with cleanup.")
            log.error(f"Ansible runner did not return a result object for instance {instance_id} deletion.")
            ansible_failed = True
        elif runner_result.rc == 0:
            append_log(instance, f"Ansible deletion playbook finished successfully (RC: {runner_result.rc}).")
            log.info(f"Ansible deletion playbook successful for instance {instance_id}.")
            ansible_rc = runner_result.rc
        else:
            append_log(instance, f"Ansible deletion playbook failed (RC: {runner_result.rc}). Proceeding with cleanup.")
            log.error(f"Ansible runner failed for instance {instance_id} deletion (RC: {runner_result.rc}), but proceeding with cleanup.")
            ansible_failed = True
            ansible_rc = runner_result.rc

        # --- Perform Cleanup Unconditionally ---
        log.info(f"Performing unconditional cleanup for instance {instance_id}.")

        # Remove local config directory
        local_config_dir_path = Path(f"configs/{host.name}/{instance.id}")
        cleanup_log_msg = ""
        try:
            if local_config_dir_path.exists() and local_config_dir_path.is_dir():
                shutil.rmtree(local_config_dir_path)
                cleanup_log_msg = f"Successfully removed local config directory: {local_config_dir_path}"
                log.info(cleanup_log_msg)
            else:
                cleanup_log_msg = f"Local config directory not found or not a directory, skipping removal: {local_config_dir_path}"
                log.warning(cleanup_log_msg)
        except OSError as e:
            cleanup_log_msg = f"Error removing local config directory {local_config_dir_path}: {e}"
            log.error(cleanup_log_msg)
        # Append cleanup log message *before* deleting the instance record
        append_log(instance, cleanup_log_msg)

        # Delete instance from DB
        try:
            instance_name_for_log = instance.name # Store name before deleting
            db.session.delete(instance)
            db.session.commit()
            log.info(f"Finished task delete_instance for instance_id: {instance_id}. Instance record '{instance_name_for_log}' deleted.")
            # Note: Logs appended before deletion are still associated with the job, but not the DB record anymore.

            # Return success message indicating UI/DB deletion is done, mention Ansible failure if applicable.
            if ansible_failed:
                 rc_msg = f" (RC: {ansible_rc})" if ansible_rc is not None else ""
                 return f"Instance '{instance_name_for_log}' (ID: {instance_id}) deleted from UI/DB (Ansible playbook failed{rc_msg})."
            else:
                 return f"Instance '{instance_name_for_log}' (ID: {instance_id}) deletion successful."
        except Exception as db_err:
            log.exception(f"Failed to delete instance {instance_id} from database after cleanup attempt: {db_err}")
            raise

    except Exception as e:
        log.exception(f"Outer exception in delete_instance for instance_id {instance_id}: {e}")
        # Attempt to set ERROR status if instance object exists and DB delete hasn't happened
        # This part is tricky because the DB delete might have failed above.
        if instance:
            try:
                # Check if the instance is still in the session (i.e., DB delete failed or wasn't reached)
                if instance in db.session:
                    # Avoid overwriting DELETING status if already set by route
                    if instance.status != InstanceStatus.DELETING:
                         instance.status = InstanceStatus.ERROR
                    append_log(instance, f"Task failed with outer exception: {e}")
                    db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update instance status/log on outer exception during deletion: {commit_err}")
        # Return a generic error message for the job
        return f"Error during instance {instance_id} deletion: {e}"


def reconfigure_instance_lan_rate_logic(instance_id):
    """
    Logic for reconfiguring LAN rate settings for a QL instance via Ansible.
    This re-renders the systemd service file, adds/removes NAT iptables rules,
    and restarts the instance service.
    """
    job = get_current_job()
    instance = None
    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found.")
            return f"Error: Instance {instance_id} not found."

        if not instance.host:
            log.error(f"Host not found for instance {instance.id} during LAN rate reconfiguration.")
            append_log(instance, "Task failed: Associated host not found.")
            instance.status = InstanceStatus.ERROR
            db.session.commit()
            return f"Error during instance {instance.id} LAN rate reconfiguration: Host not found"

        append_log(instance, f"Task started: reconfigure_instance_lan_rate (Job ID: {job.id})")
        instance.status = InstanceStatus.CONFIGURING
        db.session.commit()
        log.info(f"Instance {instance_id} status set to CONFIGURING for LAN rate reconfiguration.")

        # Ensure ZMQ setup is ready before building args
        _prepare_instance_zmq(instance)
        
        qlds_args_string = _build_qlds_args_string(instance)

        reconfigure_extravars = {
            'port': instance.port,
            'host_name': instance.host.name,
            'qlds_args': qlds_args_string,
            'lan_rate_enabled': instance.lan_rate_enabled
        }
        reconfigure_extravars = with_self_host_network_extravars(instance, reconfigure_extravars)

        # Run the LAN rate update playbook
        runner_result, error_msg = _run_ansible_playbook(
            instance,
            'update_instance_lan_rate.yml',
            extravars=reconfigure_extravars
        )

        if error_msg:
            return f"Error during instance {instance_id} LAN rate reconfiguration: {error_msg}"

        if runner_result is None:
            raise Exception("Ansible runner did not return a result unexpectedly.")

        stdout_content = runner_result.stdout() if hasattr(runner_result, 'stdout') and callable(runner_result.stdout) else getattr(runner_result, '_stdout', "")
        stderr_content = getattr(runner_result, '_stderr', "")

        append_log(instance, f"Ansible execution finished. RC: {runner_result.rc}.")

        if runner_result.rc == 0:
            instance.status = InstanceStatus.RUNNING
            lan_status = "enabled" if instance.lan_rate_enabled else "disabled"
            append_log(instance, f"Task finished successfully. LAN rate {lan_status}. Status: RUNNING.")
            db.session.commit()
            log.info(f"Finished task reconfigure_instance_lan_rate for instance_id: {instance_id}. LAN rate {lan_status}. Status: RUNNING")
            return f"Instance {instance_id} LAN rate reconfiguration successful. LAN rate {lan_status}. Status: RUNNING"
        else:
            instance.status = InstanceStatus.ERROR
            append_log(instance, f"Task failed: Ansible runner RC: {runner_result.rc}.")
            db.session.commit()
            log.error(f"Ansible runner failed for instance {instance_id} LAN rate reconfiguration. RC: {runner_result.rc}")
            return f"Error: Instance {instance_id} LAN rate reconfiguration failed. RC: {runner_result.rc}"

    except Exception as e:
        log.exception(f"Exception in reconfigure_instance_lan_rate for instance_id {instance_id}: {e}")
        if instance:
            try:
                instance.status = InstanceStatus.ERROR
                append_log(instance, f"Task failed with exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update instance status/log on exception: {commit_err}")
        return f"Error during instance {instance_id} LAN rate reconfiguration: {e}"


def fetch_instance_remote_logs(instance_id, filter_mode='lines', since='1 hour ago', lines=500):
    """
    Fetch logs from a remote QLDS instance via Ansible journalctl.
    This is a synchronous function (not an RQ task) for quick log retrieval.
    
    Args:
        instance_id: ID of the instance
        filter_mode: 'time' for time-based filtering, 'lines' for line count
        since: Time period for time-based filtering (e.g., '1 hour ago', '15 minutes ago')
        lines: Number of lines for line-based filtering
    
    Returns a tuple: (success: bool, logs: str, error_msg: str or None)
    """
    import re
    import json
    import subprocess
    import select
    
    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found.")
            return False, "", f"Instance {instance_id} not found."

        host = instance.host
        if not host:
            log.error(f"Host not found for instance {instance.id}.")
            return False, "", "Associated host not found."

        if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
            log.error(f"Host {host.id} is missing required details for Ansible.")
            return False, "", "Host details missing (IP, SSH key, or user)."

        playbook_path = os.path.abspath('ansible/playbooks/fetch_instance_logs.yml')
        inventory_path = os.path.abspath('ansible/inventory/')

        extravars = {
            'port': instance.port,
            'ansible_ssh_user': host.ssh_user,
            'ansible_ssh_private_key_file': os.path.abspath(host.ssh_key_path),
            'filter_mode': filter_mode,
            'since': since,
            'lines': lines
        }

        # Set environment variables
        env = os.environ.copy()
        env['ANSIBLE_PIPELINING'] = 'True'
        env['ANSIBLE_REMOTE_TMP'] = '/tmp'
        env['ANSIBLE_BECOME_FLAGS'] = '-H -S -n'
        env['ANSIBLE_ALLOW_WORLD_READABLE_TMPFILES'] = 'True'

        # Build the command
        cmd = ['ansible-playbook', playbook_path, '-i', inventory_path, '-l', host.name, '-e', json.dumps(extravars)]

        log.info(f"Fetching remote logs for instance {instance_id} on host {host.name}...")

        # Run synchronously and capture output
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        stdout, stderr = process.communicate(timeout=30)  # 30 second timeout
        rc = process.returncode

        if rc != 0:
            log.error(f"Ansible failed to fetch logs for instance {instance_id}. RC: {rc}")
            return False, "", f"Failed to fetch logs (RC: {rc}). Check if the instance exists on the remote host."

        # Extract logs from the debug task output
        # The debug module outputs: "msg": "<log content>"
        # We need to parse this from the Ansible JSON output or the debug message
        logs = ""
        
        # Look for the debug output pattern in stdout
        # Ansible debug outputs look like: "msg": "log content here"
        # Since we're using debug with msg, we can parse the output
        
        # Try to find the "msg" content from the debug task
        # The output format from `ansible.builtin.debug` with `msg` looks like:
        # ok: [hostname] => {
        #     "msg": "actual log content"
        # }
        
        # Use regex to extract the msg content
        msg_pattern = r'"msg":\s*"(.*?)"(?=\s*\})'
        # For multiline logs, we need a different approach
        # Let's look for the pattern that includes newlines
        
        # Actually, for large logs, Ansible will escape newlines as \n
        # Let's find all msg blocks
        lines = stdout.split('\n')
        in_msg = False
        msg_lines = []
        
        for line in lines:
            if '"msg":' in line:
                # Start of message - extract content after "msg":
                match = re.search(r'"msg":\s*"(.*)$', line)
                if match:
                    content = match.group(1)
                    # Check if it ends with a quote (single line msg)
                    if content.endswith('"'):
                        msg_lines.append(content[:-1])
                    else:
                        msg_lines.append(content)
                        in_msg = True
            elif in_msg:
                # Check if this line ends the msg
                if line.strip().endswith('"'):
                    msg_lines.append(line.rstrip()[:-1])
                    in_msg = False
                elif line.strip() == '}':
                    in_msg = False
                else:
                    msg_lines.append(line)
        
        if msg_lines:
            # Join and unescape the log content
            logs = '\n'.join(msg_lines)
            # Unescape common escape sequences
            logs = logs.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
        else:
            # Fallback: if we couldn't parse the msg, return a portion of stdout
            logs = "Could not parse log output. Raw Ansible output:\n" + stdout[-2000:]  # Last 2000 chars

        log.info(f"Successfully fetched {len(logs)} bytes of logs for instance {instance_id}")
        return True, logs, None

    except subprocess.TimeoutExpired:
        log.error(f"Timeout fetching logs for instance {instance_id}")
        return False, "", "Timeout while fetching logs from remote host."
    except Exception as e:
        log.exception(f"Exception fetching logs for instance {instance_id}: {e}")
        return False, "", str(e)


def fetch_instance_chat_logs(instance_id, lines=500, filename='chat.log'):
    """
    Fetch chat logs from a remote QLDS instance via Ansible.
    This is a synchronous function (not an RQ task) for quick log retrieval.
    
    Args:
        instance_id: ID of the instance
        lines: Number of lines for line-based filtering
        filename: Name of the log file to fetch (default: chat.log)
    
    Returns a tuple: (success: bool, logs: str, error_msg: str or None)
    """
    import re
    import json
    import subprocess
    
    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found.")
            return False, "", f"Instance {instance_id} not found."

        host = instance.host
        if not host:
            log.error(f"Host not found for instance {instance.id}.")
            return False, "", "Associated host not found."

        if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
            log.error(f"Host {host.id} is missing required details for Ansible.")
            return False, "", "Host details missing (IP, SSH key, or user)."

        playbook_path = os.path.abspath('ansible/playbooks/fetch_chat_logs.yml')
        inventory_path = os.path.abspath('ansible/inventory/')

        extravars = {
            'port': instance.port,
            'ansible_ssh_user': host.ssh_user,
            'ansible_ssh_private_key_file': os.path.abspath(host.ssh_key_path),
            'lines': lines,
            'filename': filename
        }

        # Set environment variables
        env = os.environ.copy()
        env['ANSIBLE_PIPELINING'] = 'True'
        env['ANSIBLE_REMOTE_TMP'] = '/tmp'
        env['ANSIBLE_BECOME_FLAGS'] = '-H -S -n'
        env['ANSIBLE_ALLOW_WORLD_READABLE_TMPFILES'] = 'True'

        # Build the command
        cmd = ['ansible-playbook', playbook_path, '-i', inventory_path, '-l', host.name, '-e', json.dumps(extravars)]

        log.info(f"Fetching chat logs for instance {instance_id} on host {host.name}...")

        # Run synchronously and capture output
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        stdout, stderr = process.communicate(timeout=15)  # 15 second timeout (text files should be fast)
        rc = process.returncode

        if rc != 0:
            log.error(f"Ansible failed to fetch chat logs for instance {instance_id}. RC: {rc}")
            return False, "", f"Failed to fetch chat logs (RC: {rc}). Check if the instance exists on the remote host."

        # Extract logs from the debug task output (reuse similar logic to system logs)
        logs = ""
        lines_output = stdout.split('\n')
        in_msg = False
        msg_lines = []
        
        for line in lines_output:
            if '"msg":' in line:
                match = re.search(r'"msg":\s*"(.*)$', line)
                if match:
                    content = match.group(1)
                    if content.endswith('"'):
                        msg_lines.append(content[:-1])
                    else:
                        msg_lines.append(content)
                        in_msg = True
            elif in_msg:
                if line.strip().endswith('"'):
                    msg_lines.append(line.rstrip()[:-1])
                    in_msg = False
                elif line.strip() == '}':
                    in_msg = False
                else:
                    msg_lines.append(line)
        
        if msg_lines:
            logs = '\n'.join(msg_lines)
            # Unescape
            logs = logs.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
        else:
            logs = "Could not parse chat log output. Raw Ansible output:\n" + stdout[-1000:]

        log.info(f"Successfully fetched {len(logs)} bytes of chat logs for instance {instance_id}")
        return True, logs, None

    except subprocess.TimeoutExpired:
        log.error(f"Timeout fetching chat logs for instance {instance_id}")
        return False, "", "Timeout while fetching chat logs from remote host."
    except Exception as e:
        log.exception(f"Exception fetching chat logs for instance {instance_id}: {e}")
        return False, "", str(e)


def list_instance_chat_logs(instance_id):
    """
    List available chat log files from a remote QLDS instance.

    Args:
        instance_id: ID of the instance

    Returns a tuple: (success: bool, files: list, error_msg: str or None)
    """
    import re
    import json
    import subprocess

    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            return False, [], f"Instance {instance_id} not found."

        host = instance.host
        if not host:
            return False, [], "Associated host not found."

        if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
            return False, [], "Host details missing."

        playbook_path = os.path.abspath('ansible/playbooks/list_chat_logs.yml')
        inventory_path = os.path.abspath('ansible/inventory/')

        extravars = {
            'port': instance.port,
            'ansible_ssh_user': host.ssh_user,
            'ansible_ssh_private_key_file': os.path.abspath(host.ssh_key_path)
        }

        env = os.environ.copy()
        env['ANSIBLE_PIPELINING'] = 'True'
        env['ANSIBLE_REMOTE_TMP'] = '/tmp'
        env['ANSIBLE_BECOME_FLAGS'] = '-H -S -n'
        env['ANSIBLE_ALLOW_WORLD_READABLE_TMPFILES'] = 'True'
        env['ANSIBLE_NOCOLOR'] = 'True'

        cmd = ['ansible-playbook', playbook_path, '-i', inventory_path, '-l', host.name, '-e', json.dumps(extravars)]

        log.info(f"Listing chat logs for instance {instance_id} on host {host.name}...")

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        stdout, stderr = process.communicate(timeout=10)
        rc = process.returncode

        if rc != 0:
            log.error(f"Ansible failed to list chat logs for instance {instance_id}. RC: {rc}. stderr: {stderr[-500:]}")
            return False, [], f"Failed to list chat logs (RC: {rc})."

        # Parse the debug task's msg from Ansible default callback output.
        # The playbook outputs: msg: "{{ chat_log_files | to_json }}"
        # which produces a JSON-encoded string in the debug output like:
        #   "msg": "[\"chat.log\", \"chat.log.1\"]"
        # Use same line-by-line approach as fetch_instance_chat_logs for robustness.
        msg_content = ""
        in_msg = False
        msg_lines = []

        for line in stdout.split('\n'):
            if '"msg":' in line:
                match = re.search(r'"msg":\s*"(.*)$', line)
                if match:
                    content = match.group(1)
                    if content.endswith('"'):
                        msg_content = content[:-1]
                    else:
                        msg_lines.append(content)
                        in_msg = True
            elif in_msg:
                if line.strip().endswith('"'):
                    msg_lines.append(line.rstrip()[:-1])
                    in_msg = False
                elif line.strip() == '}':
                    in_msg = False
                else:
                    msg_lines.append(line)

        if msg_lines:
            msg_content = '\n'.join(msg_lines)

        if not msg_content:
            log.warning(f"No 'msg' found in ansible output for instance {instance_id}. stdout: {stdout[-1000:]}")
            return True, [], None  # No files found is not an error

        # Unescape and parse the JSON list
        msg_content = msg_content.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')

        try:
            files = json.loads(msg_content)
            if isinstance(files, list):
                return True, files, None
            else:
                log.warning(f"Parsed msg is not a list: {type(files)}")
                return True, [], None
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse file list JSON for instance {instance_id}: {e}. Content: {msg_content[:500]}")
            return False, [], "Failed to parse log file list."

    except subprocess.TimeoutExpired:
        log.error(f"Timeout listing chat logs for instance {instance_id}")
        return False, [], "Timeout while listing chat logs."
    except Exception as e:
        log.exception(f"Exception listing chat logs for instance {instance_id}: {e}")
        return False, [], str(e)
