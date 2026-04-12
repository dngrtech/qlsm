from __future__ import annotations

import shlex
from contextlib import contextmanager
from pathlib import Path

import paramiko


class StandaloneSSHError(RuntimeError):
    """Raised when standalone SSH bootstrap or cleanup fails."""


def _public_key_path(private_key_path):
    return Path(f"{private_key_path}.pub")


def load_managed_public_key(private_key_path):
    """Read the public-key sidecar that matches a managed private key."""
    public_key_path = _public_key_path(private_key_path)
    public_key = public_key_path.read_text(encoding="utf-8").strip()
    if not public_key:
        raise StandaloneSSHError(f"Public key sidecar is empty: {public_key_path}")
    return public_key


def _create_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return client


@contextmanager
def _ssh_session(*, host, port, username, timeout, password=None, key_filename=None):
    client = _create_client()
    try:
        connect_kwargs = {
            "hostname": host,
            "port": port,
            "username": username,
            "timeout": timeout,
            "banner_timeout": timeout,
            "auth_timeout": timeout,
            "allow_agent": False,
            "look_for_keys": False,
        }
        if password is not None:
            connect_kwargs["password"] = password
        if key_filename is not None:
            connect_kwargs["key_filename"] = str(key_filename)
        client.connect(**connect_kwargs)
        yield client
    finally:
        client.close()


def _decode_stream(stream):
    data = stream.read()
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


def _run_checked_command(client, command):
    stdin, stdout, stderr = client.exec_command(command)
    _ = stdin
    exit_status = stdout.channel.recv_exit_status()
    stdout_text = _decode_stream(stdout)
    stderr_text = _decode_stream(stderr)
    if exit_status != 0:
        details = stderr_text.strip() or stdout_text.strip() or f"exit status {exit_status}"
        raise StandaloneSSHError(f"Remote command failed: {details}")
    return stdout_text, stderr_text


def verify_password_login(host, port, username, password, timeout=30):
    """Check whether the supplied password can open an SSH session."""
    try:
        with _ssh_session(
            host=host,
            port=port,
            username=username,
            password=password,
            timeout=timeout,
        ) as client:
            _run_checked_command(client, "true")
        return True
    except (paramiko.AuthenticationException, paramiko.SSHException, OSError, StandaloneSSHError):
        return False


def verify_passwordless_sudo(host, port, username, password, timeout=30):
    """Check whether the user can run sudo without being prompted for a password."""
    if username == "root":
        return True

    try:
        with _ssh_session(
            host=host,
            port=port,
            username=username,
            password=password,
            timeout=timeout,
        ) as client:
            _run_checked_command(client, "sudo -n true")
        return True
    except (paramiko.AuthenticationException, paramiko.SSHException, OSError, StandaloneSSHError):
        return False


def install_managed_key(host, port, username, password, private_key_path, timeout=30, public_key=None):
    """Install the managed public key over a password-authenticated SSH session."""
    managed_public_key = public_key or load_managed_public_key(private_key_path)
    public_key_literal = shlex.quote(managed_public_key)
    command = (
        "set -eu; "
        "mkdir -p ~/.ssh; "
        "chmod 700 ~/.ssh; "
        "touch ~/.ssh/authorized_keys; "
        "chmod 600 ~/.ssh/authorized_keys; "
        f"if ! grep -Fqx {public_key_literal} ~/.ssh/authorized_keys; then "
        f"printf '%s\\n' {public_key_literal} >> ~/.ssh/authorized_keys; "
        "fi"
    )

    with _ssh_session(
        host=host,
        port=port,
        username=username,
        password=password,
        timeout=timeout,
    ) as client:
        _run_checked_command(client, command)
    return managed_public_key


def bootstrap_managed_key(host, port, username, password, private_key_path, timeout=30):
    """Validate password access, ensure sudo is passwordless when needed, then install the managed key."""
    if not verify_password_login(host, port, username, password, timeout=timeout):
        raise StandaloneSSHError("Password authentication failed.")

    if username != "root" and not verify_passwordless_sudo(host, port, username, password, timeout=timeout):
        raise StandaloneSSHError("Passwordless sudo is required for non-root bootstrap users.")

    return install_managed_key(
        host,
        port,
        username,
        password,
        private_key_path,
        timeout=timeout,
    )


def remove_managed_key(host, port, username, private_key_path, timeout=30):
    """Remove the managed public key over key-authenticated SSH."""
    managed_public_key = load_managed_public_key(private_key_path)
    command = f"""python3 - <<'PY'
from pathlib import Path

target = {managed_public_key!r}.strip()
path = Path.home() / ".ssh" / "authorized_keys"
if not path.exists():
    raise SystemExit(3)
lines = path.read_text(encoding="utf-8").splitlines()
kept = [line for line in lines if line.strip() != target]
if kept == lines:
    raise SystemExit(4)
path.write_text(("\\n".join(kept) + "\\n") if kept else "", encoding="utf-8")
PY"""

    with _ssh_session(
        host=host,
        port=port,
        username=username,
        key_filename=private_key_path,
        timeout=timeout,
    ) as client:
        _run_checked_command(client, command)
    return managed_public_key

