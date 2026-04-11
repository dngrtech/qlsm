import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ui.routes import self_host_helpers as helpers
from ui.task_logic import self_host_network as net


def test_detect_docker_host_ip_from_proc_route(tmp_path):
    route_file = tmp_path / "route"
    route_file.write_text(
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
        "eth0\t00000000\t010011AC\t0003\t0\t0\t0\t00000000\n"
    )

    assert net.detect_docker_host_ip(route_path=route_file) == "172.17.0.1"


def test_detect_docker_host_ip_falls_back_to_ip_route(monkeypatch, tmp_path):
    route_file = tmp_path / "missing"

    def fake_run(cmd, check, capture_output, text):
        assert cmd == ["ip", "route", "show", "default"]
        return subprocess.CompletedProcess(cmd, 0, stdout="default via 172.18.0.1 dev eth0\n", stderr="")

    monkeypatch.setattr(net.subprocess, "run", fake_run)

    assert net.detect_docker_host_ip(route_path=route_file) == "172.18.0.1"


def test_detect_docker_host_ip_raises_when_unavailable(monkeypatch, tmp_path):
    route_file = tmp_path / "route"
    route_file.write_text("Iface\tDestination\tGateway\tFlags\n")

    def fake_run(cmd, check, capture_output, text):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no route")

    monkeypatch.setattr(net.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="Could not detect host machine IP"):
        net.detect_docker_host_ip(route_path=route_file)


def test_resolve_self_host_management_target_prefers_env_override(monkeypatch):
    monkeypatch.setenv("QLSM_SELF_HOST_SSH_TARGET", "10.10.10.10")

    assert net.resolve_self_host_management_target() == "10.10.10.10"


def test_resolve_self_host_management_target_prefers_host_docker_internal(monkeypatch):
    monkeypatch.delenv("QLSM_SELF_HOST_SSH_TARGET", raising=False)
    monkeypatch.setattr(
        net,
        "_can_resolve_hostname",
        lambda name: name == "host.docker.internal",
    )
    monkeypatch.setattr(
        net,
        "detect_docker_host_ip",
        lambda **_: "172.18.0.1",
    )

    assert net.resolve_self_host_management_target() == "host.docker.internal"


def test_resolve_self_host_management_target_falls_back_to_gateway(monkeypatch):
    monkeypatch.delenv("QLSM_SELF_HOST_SSH_TARGET", raising=False)
    monkeypatch.setattr(net, "_can_resolve_hostname", lambda name: False)
    monkeypatch.setattr(
        net,
        "detect_docker_host_ip",
        lambda **_: "172.18.0.1",
    )

    assert net.resolve_self_host_management_target() == "172.18.0.1"


def test_detect_default_self_ssh_user_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("QLSM_HOST_USER", "rage")

    assert helpers.detect_default_self_ssh_user(host_ssh_dir=tmp_path) == "rage"


def test_remove_authorized_key_rewrites_file(tmp_path):
    host_ssh = tmp_path / "host-ssh"
    host_ssh.mkdir()
    auth = host_ssh / "authorized_keys"
    auth.write_text("ssh-rsa keep\nssh-rsa remove\n")

    removed = helpers.remove_authorized_key("ssh-rsa remove", host_ssh_dir=host_ssh)

    assert removed is True
    assert auth.read_text() == "ssh-rsa keep\n"
    assert oct(auth.stat().st_mode & 0o777) == "0o600"


def test_generate_self_host_keys_cleans_up_authorized_key_on_chmod_error(monkeypatch, tmp_path):
    ssh_keys = tmp_path / "keys"
    host_ssh = tmp_path / "host-ssh"
    host_ssh.mkdir()

    def fake_run(cmd, check, capture_output, text):
        key_path = Path(cmd[cmd.index("-f") + 1])
        key_path.write_text("private")
        Path(str(key_path) + ".pub").write_text("ssh-rsa generated\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(helpers.subprocess, "run", fake_run)
    monkeypatch.setattr(helpers.os, "chmod", MagicMock(side_effect=OSError("chmod failed")))

    with pytest.raises(helpers.SelfHostKeyError):
        helpers.generate_self_host_keys("self-host", ssh_keys_dir=ssh_keys, host_ssh_dir=host_ssh)

    assert not (ssh_keys / "self-host_self_id_rsa").exists()
    assert not (ssh_keys / "self-host_self_id_rsa.pub").exists()
    assert "generated" not in (host_ssh / "authorized_keys").read_text()
