import os
from pathlib import Path


class LocalSSHKeyMaterialError(RuntimeError):
    """Raised when generated local SSH key files cannot be made usable."""


def normalize_local_ssh_key_material(private_key_path, public_key_path=None):
    """Align local SSH key ownership with the key directory owner.

    This protects against flows that happen to run as root and would otherwise
    leave key files owned by root:root with mode 0600, making them unreadable to
    the normal app user later.
    """
    private_path = Path(private_key_path)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    owner_stat = private_path.parent.stat()
    owner_uid = owner_stat.st_uid
    owner_gid = owner_stat.st_gid

    try:
        os.chown(private_path, owner_uid, owner_gid)
        os.chmod(private_path, 0o600)
        if public_key_path:
            public_path = Path(public_key_path)
            if public_path.exists():
                os.chown(public_path, owner_uid, owner_gid)
    except OSError as exc:
        raise LocalSSHKeyMaterialError(
            "Failed to prepare local SSH key material with usable ownership/permissions."
        ) from exc
