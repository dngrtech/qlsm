import logging
import os
import subprocess # For running Terraform CLI
import json       # For parsing Terraform JSON output
import shutil     # For checking if terraform executable exists
import re         # For parsing error messages

# Import database and models - requires app context
from ui import db
from ui.models import HostStatus # Only need HostStatus here
from .common import append_log # Import from the common module

log = logging.getLogger(__name__)

def _detect_stale_state_404(stderr):
    """
    Detects if the error is due to a stale Terraform state (404 instance not found).
    Returns the resource address if detected, None otherwise.
    """
    if not stderr:
        return None

    # Check for the 404 error pattern
    if '"status":404' in stderr or '"status": 404' in stderr:
        if 'instance not found' in stderr.lower() or 'not found' in stderr.lower():
            # Try to extract the resource address from the error
            # Pattern: "with module.vultr_host_instance.vultr_instance.this,"
            # Support array indices like resource[0]
            match = re.search(r'with\s+([\w.\[\]]+),', stderr)
            if match:
                return match.group(1)

    return None

def _cleanup_stale_state(host, resource_address, terraform_root_dir):
    """
    Removes a stale resource from Terraform state.
    Returns True if successful, False otherwise.
    Note: Does not commit to database - caller should handle commits.
    """
    try:
        log.warning(f"Detected stale state for resource: {resource_address}. Attempting cleanup.")
        append_log(host, f"Detected stale Terraform state for: {resource_address}")

        result = subprocess.run(
            ['terraform', 'state', 'rm', resource_address],
            cwd=terraform_root_dir,
            check=True,
            capture_output=True,
            text=True,
            env=os.environ
        )

        log.info(f"Successfully removed stale resource {resource_address} from state.")
        append_log(host, f"Cleaned up stale state: {resource_address}\nOutput: {result.stdout}")
        return True

    except subprocess.CalledProcessError as e:
        log.error(f"Failed to clean up stale state for {resource_address}: {e}")
        append_log(host, f"Failed to clean up stale state for {resource_address}: {e.stderr}")
        return False
    except Exception as e:
        log.exception(f"Unexpected error during stale state cleanup: {e}")
        append_log(host, f"Unexpected error during stale state cleanup: {e}")
        return False

def run_terraform_with_retry(host, command_args, terraform_root_dir, parse_json=False):
    """
    Runs a Terraform command with automatic retry on stale state cleanup.
    Returns (result, error) tuple. On success, result contains stdout or parsed JSON.
    """
    result, error = _run_terraform_command(host, command_args, terraform_root_dir, parse_json)

    # Check if the error was due to stale state that was cleaned up
    if error == "STALE_STATE_CLEANED":
        log.info(f"Stale state was cleaned up. Retrying: terraform {' '.join(command_args)}")
        append_log(host, f"Stale state cleaned up successfully. Retrying command...")
        db.session.commit()

        # Retry the command once (do not retry again if it returns STALE_STATE_CLEANED)
        result, error = _run_terraform_command(host, command_args, terraform_root_dir, parse_json)

        # If retry also encounters stale state, treat it as an error
        if error == "STALE_STATE_CLEANED":
            error = "Multiple stale resources detected. Manual cleanup may be required."
            append_log(host, error)
            db.session.commit()

    return result, error

def _run_terraform_command(host, command_args, terraform_root_dir, parse_json=False):
    """Runs a Terraform command using subprocess, logs output, and handles errors."""
    log.info(f"Running Terraform command in {terraform_root_dir}: {' '.join(command_args)}")
    append_log(host, f"Executing: terraform {' '.join(command_args)}")
    try:
        # Use check=True to raise CalledProcessError on non-zero exit codes
        result = subprocess.run(['terraform'] + command_args,
                                cwd=terraform_root_dir,
                                check=True,
                                capture_output=True,
                                text=True,
                                env=os.environ) # Pass environment variables (e.g., VULTR_API_KEY)
        log.debug(f"Terraform stdout:\n{result.stdout}")
        if result.stderr:
            log.warning(f"Terraform stderr:\n{result.stderr}") # Log stderr as warning
        append_log(host, f"Command successful.\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}")

        if parse_json:
            return json.loads(result.stdout), None # Return data, no error
        return result.stdout, None # Return stdout, no error

    except FileNotFoundError:
        # This should be caught earlier, but handle defensively
        log.error("Terraform executable not found during command execution.")
        append_log(host, "Command failed: Terraform executable not found.")
        host.status = HostStatus.ERROR
        db.session.commit()
        return None, "Terraform executable not found"
    except subprocess.CalledProcessError as e:
        log.error(f"Terraform command failed: {e}")
        log.error(f"Stderr:\n{e.stderr}")
        log.error(f"Stdout:\n{e.stdout}")

        # Check if this is a stale state 404 error
        stale_resource = _detect_stale_state_404(e.stderr)
        if stale_resource:
            append_log(host, f"Command failed due to stale state! RC: {e.returncode}\nStderr:\n{e.stderr}\nStdout:\n{e.stdout}")
            db.session.commit()  # Commit error log before cleanup attempt

            # Attempt to clean up the stale state
            if _cleanup_stale_state(host, stale_resource, terraform_root_dir):
                db.session.commit()  # Commit cleanup logs
                # Return a special error code to indicate that cleanup was successful and retry is possible
                return None, "STALE_STATE_CLEANED"
            else:
                # Cleanup failed, return the original error
                append_log(host, "Stale state cleanup failed. Manual intervention required.")
                db.session.commit()  # Commit failure message
                error_detail = e.stderr or e.stdout or ""
                return None, f"Terraform command failed (RC: {e.returncode}): {error_detail}"
        else:
            # Not a stale state error, log and return normally
            append_log(host, f"Command failed! RC: {e.returncode}\nStderr:\n{e.stderr}\nStdout:\n{e.stdout}")
            error_detail = e.stderr or e.stdout or ""
            return None, f"Terraform command failed (RC: {e.returncode}): {error_detail}"
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse Terraform JSON output: {e}")
        append_log(host, f"Command failed: Could not parse Terraform JSON output.")
        # Let the calling function decide if this error is fatal
        # host.status = HostStatus.ERROR # Removed status update from helper
        # db.session.commit() # Removed commit from helper
        return None, "Failed to parse Terraform JSON output"
    except Exception as e:
        # Catch any other unexpected errors during subprocess execution
        log.exception(f"Unexpected error running Terraform command: {e}")
        append_log(host, f"Command failed with unexpected error: {e}")
        # Let the calling function decide if this error is fatal
        # host.status = HostStatus.ERROR # Removed status update from helper
        # db.session.commit() # Removed commit from helper
        return None, f"Unexpected error running Terraform: {e}"
