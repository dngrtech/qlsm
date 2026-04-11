import os
import pwd
import subprocess
from pathlib import Path


class SelfHostKeyError(RuntimeError):
    pass


def detect_default_self_ssh_user(host_ssh_dir="/host-ssh"):
    env_user = os.environ.get("QLSM_HOST_USER", "").strip()
    if env_user:
        return env_user

    try:
        uid = os.stat(host_ssh_dir).st_uid
        return pwd.getpwuid(uid).pw_name
    except Exception:
        return "root"


def generate_self_host_keys(name, ssh_keys_dir="terraform/ssh-keys", host_ssh_dir="/host-ssh"):
    key_dir = Path(ssh_keys_dir).resolve()
    key_dir.mkdir(parents=True, exist_ok=True)
    key_path = key_dir / f"{name}_self_id_rsa"
    public_key = None

    try:
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", str(key_path), "-N", ""],
            check=True,
            capture_output=True,
            text=True,
        )
        public_key = Path(str(key_path) + ".pub").read_text().strip()
        append_authorized_key(public_key, host_ssh_dir=host_ssh_dir)
        return str(key_path), public_key
    except Exception as exc:
        cleanup_self_host_key_material(key_path, public_key=public_key, host_ssh_dir=host_ssh_dir)
        raise SelfHostKeyError("SSH key generation failed.") from exc


def append_authorized_key(public_key, host_ssh_dir="/host-ssh"):
    auth_path = Path(host_ssh_dir) / "authorized_keys"
    auth_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    existing = auth_path.read_text().splitlines() if auth_path.exists() else []
    if public_key not in [line.strip() for line in existing]:
        with auth_path.open("a") as handle:
            handle.write(public_key.rstrip() + "\n")
    os.chmod(auth_path, 0o600)


def remove_authorized_key(public_key, host_ssh_dir="/host-ssh"):
    auth_path = Path(host_ssh_dir) / "authorized_keys"
    if not auth_path.exists():
        return False

    target = public_key.strip()
    lines = auth_path.read_text().splitlines()
    kept = [line for line in lines if line.strip() != target]
    if kept == lines:
        return False

    tmp_path = auth_path.with_name(f".{auth_path.name}.tmp")
    tmp_path.write_text(("\n".join(kept) + "\n") if kept else "")
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, auth_path)
    return True


def cleanup_self_host_key_material(key_path, public_key=None, host_ssh_dir="/host-ssh"):
    if public_key:
        try:
            remove_authorized_key(public_key, host_ssh_dir=host_ssh_dir)
        except OSError:
            _remove_authorized_key_best_effort(public_key, host_ssh_dir=host_ssh_dir)
    for path in (Path(key_path), Path(str(key_path) + ".pub")):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _remove_authorized_key_best_effort(public_key, host_ssh_dir="/host-ssh"):
    auth_path = Path(host_ssh_dir) / "authorized_keys"
    try:
        target = public_key.strip()
        lines = auth_path.read_text().splitlines()
        kept = [line for line in lines if line.strip() != target]
        auth_path.write_text(("\n".join(kept) + "\n") if kept else "")
    except OSError:
        pass
