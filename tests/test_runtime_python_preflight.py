"""minqlxtended links -lpython3.12, so a host below that cannot run it."""
import pytest
import yaml

from ui.runtime import MINQLX, MINQLXTENDED


@pytest.mark.parametrize("version", ["3.12.3", "3.13.0", "3.12", "4.0.0"])
def test_supported_python_passes(version):
    from ui.routes.host_routes import _validate_runtime_python

    ok, _ = _validate_runtime_python({"python_version": version}, MINQLXTENDED)
    assert ok is True


@pytest.mark.parametrize("version", ["3.11.2", "3.9.7", "2.7.18", "3.8"])
def test_old_python_is_rejected_for_minqlxtended(version):
    from ui.routes.host_routes import _validate_runtime_python

    ok, message = _validate_runtime_python({"python_version": version}, MINQLXTENDED)
    assert ok is False
    assert "3.12" in message
    assert version in message


@pytest.mark.parametrize("version", ["3.9.7", None, "garbage"])
def test_minqlx_never_gates_on_python(version):
    """minqlx has no floor. Adding one would break existing hosts on the next
    setup re-run."""
    from ui.routes.host_routes import _validate_runtime_python

    ok, _ = _validate_runtime_python({"python_version": version}, MINQLX)
    assert ok is True


def test_undetectable_python_is_rejected_for_minqlxtended():
    """If we cannot prove the host is new enough, refuse -- the choice is
    irreversible."""
    from ui.routes.host_routes import _validate_runtime_python

    ok, message = _validate_runtime_python({"python_version": None}, MINQLXTENDED)
    assert ok is False
    assert "could not" in message.lower() or "unable" in message.lower()


def test_detect_remote_os_reports_the_python_version(monkeypatch):
    """The probe runs in the SSH session detect_remote_os already opens."""
    import ui.standalone_ssh as mod

    commands = []

    class FakeClient:
        pass

    def fake_run_checked(client, command):
        commands.append(command)
        if "os-release" in command:
            return 'ID=ubuntu\nVERSION_ID="24.04"\nPRETTY_NAME="Ubuntu 24.04 LTS"\n', ""
        if "python3" in command:
            return "Python 3.12.3\n", ""
        return "", ""

    class FakeSession:
        def __enter__(self):
            return FakeClient()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(mod, "_ssh_session", lambda **kwargs: FakeSession())
    monkeypatch.setattr(mod, "_run_checked_command", fake_run_checked)
    monkeypatch.setattr(mod, "_check_qlsm_running", lambda client: False)

    result = mod.detect_remote_os(host="1.2.3.4", port=22, username="ql")

    assert result["python_version"] == "3.12.3"
    assert any("python3" in c for c in commands)


def test_detect_remote_os_tolerates_a_missing_python(monkeypatch):
    import ui.standalone_ssh as mod

    def fake_run_checked(client, command):
        if "os-release" in command:
            return 'ID=debian\nVERSION_ID="12"\nPRETTY_NAME="Debian GNU/Linux 12"\n', ""
        raise mod.StandaloneSSHError("python3: command not found")

    class FakeSession:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(mod, "_ssh_session", lambda **kwargs: FakeSession())
    monkeypatch.setattr(mod, "_run_checked_command", fake_run_checked)
    monkeypatch.setattr(mod, "_check_qlsm_running", lambda client: False)

    result = mod.detect_remote_os(host="1.2.3.4", port=22, username="ql")

    assert result["python_version"] is None
    assert result["os_type"] == "debian"


def test_setup_playbook_asserts_the_python_floor():
    """The playbook is the authoritative gate -- it also covers 'self' hosts,
    where QLSM has no SSH session to probe from."""
    with open("ansible/playbooks/setup_host.yml") as handle:
        playbook = yaml.safe_load(handle)

    tasks = playbook[0]["tasks"]
    asserts = [t for t in tasks if "assert" in t and "python" in str(t).lower()]
    assert asserts, "setup_host.yml has no Python version assert"

    gate = asserts[0]
    assert "minqlxtended" in str(gate.get("when", "")), "the gate must not fire on minqlx hosts"
    assert "3.12" in str(gate["assert"]["that"])
