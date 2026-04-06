import logging
import secrets
import string

from ui import db

log = logging.getLogger(__name__)


def generate_zmq_rcon_password(length=14):
    """Generate a secure random password for ZMQ RCON.

    Uses letters, digits, and safe punctuation (avoiding shell-problematic chars).
    """
    # Avoid: # (comment), ! (shell history), * (glob), % (format), & (background)
    # These get mangled by shell, Ansible, or Quake arg parsing even when quoted
    safe_punctuation = '-_=+'
    alphabet = string.ascii_letters + string.digits + safe_punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def ensure_zmq_rcon_setup(instance):
    """
    Ensure ZMQ RCON settings (port and password) are set for the instance.
    Port is calculated deterministically: 28888 + (game_port - 27960).
    If password is missing, generate it.
    """
    changed = False

    # Calculate deterministic ZMQ port
    # Base: 28888, Offset: game_port - 27960
    # e.g., 27960 -> 28888, 27961 -> 28889
    target_zmq_port = 28888 + (instance.port - 27960)

    # Calculate deterministic ZMQ Stats port (User requested stats support)
    # Base: 29999, Offset: game_port - 27960
    target_zmq_stats_port = 29999 + (instance.port - 27960)

    if instance.zmq_rcon_port != target_zmq_port:
        log.info(f"Updating ZMQ RCON port for instance {instance.id} from {instance.zmq_rcon_port} to {target_zmq_port}")
        instance.zmq_rcon_port = target_zmq_port
        changed = True

    if instance.zmq_stats_port != target_zmq_stats_port:
        log.info(f"Updating ZMQ Stats port for instance {instance.id} from {instance.zmq_stats_port} to {target_zmq_stats_port}")
        instance.zmq_stats_port = target_zmq_stats_port
        changed = True

    # Generate zmq_rcon_password if not already set
    if not instance.zmq_rcon_password:
        instance.zmq_rcon_password = generate_zmq_rcon_password()
        changed = True

    # Generate zmq_stats_password if not already set
    if not instance.zmq_stats_password:
        instance.zmq_stats_password = generate_zmq_rcon_password()
        changed = True

    if changed:
        log.info(f"Instance {instance.id} ZMQ RCON settings updated. Port: {instance.zmq_rcon_port}")

    return instance.zmq_rcon_port, instance.zmq_rcon_password
