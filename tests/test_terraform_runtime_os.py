"""Every Terraform entry point must pass the host's own OS.

If resize omitted it, Terraform would re-resolve os_id to the default and
Vultr would reinstall the operating system on a running game server.
"""
import pytest

from ui import db
from ui.models import Host, HostStatus
from ui.runtime import MINQLX, MINQLXTENDED


def _make_host(app, runtime, name, status=HostStatus.ACTIVE):
    with app.app_context():
        host = Host(name=name, provider="vultr", runtime=runtime,
                    region="ewr", machine_size="vc2-1c-2gb",
                    workspace_name=f"{name}-ws", ip_address="10.0.0.9",
                    status=status)
        db.session.add(host)
        db.session.commit()
        return host.id


class _FakeJob:
    """Stand-in for an RQ job. provision/destroy dereference job.id
    unconditionally, and get_current_job() returns None outside a real
    worker, so it must be patched for those entry points to run at all."""
    id = "fake-job-id"


def test_os_vars_for_minqlx_is_debian_12():
    from ui.task_logic.terraform_runner import _os_vars

    class H:
        runtime = MINQLX

    assert _os_vars(H()) == [
        "-var=os_name=Debian 12 x64 (bookworm)",
        "-var=os_family=debian",
    ]


def test_os_vars_for_minqlxtended_is_ubuntu_2404():
    from ui.task_logic.terraform_runner import _os_vars

    class H:
        runtime = MINQLXTENDED

    assert _os_vars(H()) == [
        "-var=os_name=Ubuntu 24.04 LTS x64",
        "-var=os_family=ubuntu",
    ]


def test_os_vars_for_a_legacy_host_with_null_runtime():
    from ui.task_logic.terraform_runner import _os_vars

    class H:
        runtime = None

    assert "-var=os_family=debian" in _os_vars(H())


@pytest.mark.parametrize("entry_point", ["provision", "resize", "destroy"])
def test_every_terraform_entry_point_passes_the_hosts_os(app, monkeypatch, entry_point):
    # resize_host_logic requires the host to already be CONFIGURING before it
    # will touch Terraform at all; provision/destroy don't gate on status.
    initial_status = HostStatus.CONFIGURING if entry_point == "resize" else HostStatus.ACTIVE
    host_id = _make_host(app, MINQLXTENDED, f"tf-{entry_point}", status=initial_status)
    captured = []

    def fake_run(host, args, cwd, parse_json=False):
        captured.append(args)
        return ({} if parse_json else ""), None

    if entry_point == "provision":
        import ui.task_logic.terraform_provision as mod
        fn = lambda: mod.provision_host_logic(host_id)
    elif entry_point == "resize":
        import ui.task_logic.terraform_resize as mod
        fn = lambda: mod.resize_host_logic(host_id, "vc2-2c-4gb")
    else:
        import ui.task_logic.terraform_destroy as mod
        fn = lambda: mod.destroy_host_logic(host_id)

    monkeypatch.setattr(mod, "_run_terraform_command", fake_run, raising=False)
    monkeypatch.setattr(mod, "run_terraform_with_retry", fake_run, raising=False)
    monkeypatch.setattr(mod, "get_current_job", lambda: _FakeJob(), raising=False)

    with app.app_context():
        try:
            fn()
        except Exception:
            # We only care about the arguments handed to Terraform, not about
            # completing the whole task against stubbed output.
            pass

    apply_calls = [a for a in captured
                   if any(x in ("apply", "destroy") for x in a)]
    assert apply_calls, f"{entry_point} never invoked apply/destroy"
    for args in apply_calls:
        assert "-var=os_name=Ubuntu 24.04 LTS x64" in args, args
        assert "-var=os_family=ubuntu" in args, args


def test_module_default_os_id_matches_the_vultr_api():
    """variables.tf hardcoded 2139 for Debian 12; the API reports 2136."""
    from pathlib import Path

    text = Path("terraform/modules/vultr_instance/variables.tf").read_text()
    assert "2139" not in text
    assert "2136" in text


def test_root_module_resolves_the_os_by_variable():
    from pathlib import Path

    text = Path("terraform/vultr-root/main.tf").read_text()
    assert "var.os_name" in text
    assert "var.os_family" in text
    # The old hardcoded lookup must be gone, or the variable would be inert.
    assert 'values = ["Debian 12 x64 (bookworm)"]' not in text
