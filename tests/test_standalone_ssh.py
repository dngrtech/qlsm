from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import paramiko
import pytest

from ui.standalone_ssh import _AuditedAutoAddPolicy
from ui.standalone_ssh import _format_host_key_fingerprint
from ui.standalone_ssh import StandaloneSSHError
from ui.standalone_ssh import bootstrap_managed_key
from ui.standalone_ssh import detect_remote_os
from ui.standalone_ssh import install_managed_key
from ui.standalone_ssh import load_managed_public_key
from ui.standalone_ssh import remove_managed_key
from ui.standalone_ssh import verify_password_login
from ui.standalone_ssh import verify_passwordless_sudo


def _ssh_client(stdout_data=b"", stderr_data=b"", exit_status=0):
    client = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.channel.recv_exit_status.return_value = exit_status
    stdout.read.return_value = stdout_data
    stderr.read.return_value = stderr_data
    client.exec_command.return_value = (MagicMock(), stdout, stderr)
    return client


def test_load_managed_public_key_reads_sidecar(tmp_path):
    key_path = tmp_path / "host_id_rsa"
    pub_path = Path(f"{key_path}.pub")
    pub_path.write_text("ssh-rsa AAAA example\n", encoding="utf-8")

    assert load_managed_public_key(key_path) == "ssh-rsa AAAA example"


@patch("ui.standalone_ssh.paramiko.SSHClient")
def test_verify_password_login_uses_password_auth(mock_client_cls):
    client = _ssh_client()
    mock_client_cls.return_value = client

    assert verify_password_login("203.0.113.10", 2222, "ansible", "secret") is True

    client.connect.assert_called_once()
    policy = client.set_missing_host_key_policy.call_args.args[0]
    assert isinstance(policy, _AuditedAutoAddPolicy)
    kwargs = client.connect.call_args.kwargs
    assert kwargs["password"] == "secret"
    assert kwargs["allow_agent"] is False
    assert kwargs["look_for_keys"] is False
    client.exec_command.assert_called_once_with("true")
    client.close.assert_called_once()


@patch("ui.standalone_ssh.paramiko.SSHClient")
def test_verify_passwordless_sudo_skips_root(mock_client_cls):
    assert verify_passwordless_sudo("203.0.113.10", 22, "root", "secret") is True
    mock_client_cls.assert_not_called()


@patch("ui.standalone_ssh.paramiko.SSHClient")
def test_verify_passwordless_sudo_checks_non_root(mock_client_cls):
    client = _ssh_client()
    mock_client_cls.return_value = client

    assert verify_passwordless_sudo("203.0.113.10", 22, "ansible", "secret") is True
    client.exec_command.assert_called_once_with("sudo -n true")


@patch("ui.standalone_ssh.install_managed_key", return_value="ssh-rsa AAAA example")
@patch("ui.standalone_ssh.verify_passwordless_sudo", return_value=True)
@patch("ui.standalone_ssh.verify_password_login", return_value=True)
def test_bootstrap_managed_key_checks_password_and_sudo(
    mock_login,
    mock_sudo,
    mock_install,
):
    result = bootstrap_managed_key(
        "203.0.113.10",
        22,
        "ansible",
        "secret",
        "/tmp/host_id_rsa",
    )

    assert result == "ssh-rsa AAAA example"
    mock_login.assert_called_once_with("203.0.113.10", 22, "ansible", "secret", timeout=30)
    mock_sudo.assert_called_once_with("203.0.113.10", 22, "ansible", "secret", timeout=30)
    mock_install.assert_called_once_with(
        "203.0.113.10",
        22,
        "ansible",
        "secret",
        "/tmp/host_id_rsa",
        timeout=30,
    )


@patch("ui.standalone_ssh.install_managed_key", return_value="ssh-rsa AAAA example")
@patch("ui.standalone_ssh.verify_passwordless_sudo")
@patch("ui.standalone_ssh.verify_password_login", return_value=True)
def test_bootstrap_managed_key_skips_sudo_for_root(
    mock_login,
    mock_sudo,
    mock_install,
):
    bootstrap_managed_key("203.0.113.10", 22, "root", "secret", "/tmp/host_id_rsa")

    mock_sudo.assert_not_called()
    mock_install.assert_called_once()


@patch("ui.standalone_ssh.paramiko.SSHClient")
def test_install_managed_key_appends_public_key(mock_client_cls, tmp_path):
    key_path = tmp_path / "host_id_rsa"
    pub_path = Path(f"{key_path}.pub")
    pub_path.write_text("ssh-rsa AAAA example", encoding="utf-8")

    client = _ssh_client()
    mock_client_cls.return_value = client

    assert install_managed_key(
        "203.0.113.10",
        22,
        "ansible",
        "secret",
        key_path,
    ) == "ssh-rsa AAAA example"

    kwargs = client.connect.call_args.kwargs
    assert kwargs["password"] == "secret"
    command = client.exec_command.call_args.args[0]
    assert "grep -Fqx" in command
    assert "authorized_keys" in command
    assert "ssh-rsa AAAA example" in command


@patch("ui.standalone_ssh.paramiko.SSHClient")
def test_remove_managed_key_uses_key_auth(mock_client_cls, tmp_path):
    key_path = tmp_path / "host_id_rsa"
    pub_path = Path(f"{key_path}.pub")
    pub_path.write_text("ssh-rsa AAAA example", encoding="utf-8")

    client = _ssh_client()
    mock_client_cls.return_value = client

    assert remove_managed_key("203.0.113.10", 22, "ansible", key_path) == "ssh-rsa AAAA example"

    policy = client.set_missing_host_key_policy.call_args.args[0]
    assert isinstance(policy, paramiko.AutoAddPolicy)
    kwargs = client.connect.call_args.kwargs
    assert kwargs["key_filename"] == str(key_path)
    assert "password" not in kwargs
    command = client.exec_command.call_args.args[0]
    assert "authorized_keys" in command
    assert "ssh-rsa AAAA example" in command


def test_audited_auto_add_policy_logs_sha256_fingerprint(caplog):
    client = MagicMock()
    client._host_keys = MagicMock()
    client._host_keys_filename = None
    key = paramiko.RSAKey.generate(1024)

    with caplog.at_level("WARNING"):
        _AuditedAutoAddPolicy().missing_host_key(client, "203.0.113.10", key)

    fingerprint = _format_host_key_fingerprint(key)
    assert fingerprint in caplog.text
    client._host_keys.add.assert_called_once_with("203.0.113.10", key.get_name(), key)


@patch("ui.standalone_ssh.paramiko.SSHClient")
def test_detect_remote_os_maps_supported_release(mock_client_cls):
    client = _ssh_client(
        stdout_data=(
            b'NAME="Ubuntu"\n'
            b'VERSION="24.04.2 LTS (Noble Numbat)"\n'
            b'ID=ubuntu\n'
            b'VERSION_ID="24.04"\n'
            b'PRETTY_NAME="Ubuntu 24.04.2 LTS"\n'
        ),
    )
    mock_client_cls.return_value = client

    detected = detect_remote_os(
        host="203.0.113.10",
        port=22,
        username="root",
        password="secret",
    )

    assert detected == {
        "id": "ubuntu",
        "version_id": "24.04",
        "pretty_name": "Ubuntu 24.04.2 LTS",
        "os_type": "ubuntu",
    }


@patch("ui.standalone_ssh.paramiko.SSHClient")
def test_detect_remote_os_marks_unsupported_release(mock_client_cls):
    client = _ssh_client(
        stdout_data=(
            b'ID=ubuntu\n'
            b'VERSION_ID="18.04"\n'
            b'PRETTY_NAME="Ubuntu 18.04.6 LTS"\n'
        ),
    )
    mock_client_cls.return_value = client

    detected = detect_remote_os(
        host="203.0.113.11",
        port=22,
        username="root",
        key_filename="/tmp/test_key",
    )

    assert detected["pretty_name"] == "Ubuntu 18.04.6 LTS"
    assert detected["os_type"] is None


@patch("ui.standalone_ssh.paramiko.SSHClient")
def test_bootstrap_managed_key_fails_when_password_login_rejected(mock_client_cls):
    mock_client_cls.return_value = _ssh_client()

    with patch("ui.standalone_ssh.verify_password_login", return_value=False):
        with pytest.raises(StandaloneSSHError, match="Password authentication failed"):
            bootstrap_managed_key("203.0.113.10", 22, "ansible", "secret", "/tmp/host_id_rsa")
