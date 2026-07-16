import inspect
from unittest.mock import MagicMock, patch

import pytest

from ui import db
from ui.models import Host, HostStatus, InstanceStatus, QLInstance


CLOUD_MODULE = "ui.task_logic.ansible_host_setup"
STANDALONE_MODULE = "ui.task_logic.standalone_host_setup"
COMMON_HELPER = "ui.task_logic.common._reconcile_host_instances_after_setup"


def _build_host(app, *, provider, status):
    with app.app_context():
        host = Host(
            name=f"{provider}-recovery-host",
            provider=provider,
            os_type="debian",
            ip_address="1.2.3.4",
            ssh_key_path="/key",
            ssh_user="ansible",
            status=status,
            is_standalone=provider == "standalone",
            lan_rate_uses_hook=False,
        )
        db.session.add(host)
        db.session.flush()
        db.session.add_all([
            QLInstance(
                host_id=host.id,
                name=f"{provider}-running",
                hostname="Running server",
                port=27960,
                status=InstanceStatus.RUNNING,
            ),
            QLInstance(
                host_id=host.id,
                name=f"{provider}-stopped",
                hostname="Stopped server",
                port=27961,
                status=InstanceStatus.STOPPED,
            ),
        ])
        db.session.commit()
        return host.id


def _run_cloud_setup(app, host_id, *, rerun):
    process = MagicMock(returncode=0)
    with patch(f"{CLOUD_MODULE}.get_current_job", return_value=MagicMock(id="job")), \
         patch(f"{CLOUD_MODULE}.os.path.exists", return_value=True), \
         patch(f"{CLOUD_MODULE}.subprocess.run"), \
         patch(f"{CLOUD_MODULE}.subprocess.Popen", return_value=process), \
         patch(
             "ui.task_logic.ansible_runner._stream_output",
             return_value=("stdout ok", ""),
         ):
        with app.app_context():
            from ui.task_logic.ansible_host_setup import setup_host_ansible_logic
            return setup_host_ansible_logic(host_id, rerun=rerun)


def _run_standalone_setup(app, host_id, *, rerun):
    with patch(
        f"{STANDALONE_MODULE}.get_current_job",
        return_value=MagicMock(id="job"),
    ), patch(
        f"{STANDALONE_MODULE}._generate_standalone_inventory",
        return_value=("/tmp/inventory.yml", "1.2.3.4"),
    ), patch(
        f"{STANDALONE_MODULE}._wait_for_ssh",
        return_value=True,
    ), patch(
        f"{STANDALONE_MODULE}._run_setup_playbook",
        return_value=True,
    ):
        with app.app_context():
            from ui.task_logic.standalone_host_setup import setup_standalone_host_logic
            return setup_standalone_host_logic(host_id, rerun=rerun)


@pytest.mark.parametrize(
    ("module_name", "function_name"),
    [
        (CLOUD_MODULE, "setup_host_ansible_logic"),
        (STANDALONE_MODULE, "setup_standalone_host_logic"),
    ],
)
def test_rerun_callers_no_longer_reference_legacy_instance_paths(
    module_name, function_name
):
    module = __import__(module_name, fromlist=[function_name])
    source = inspect.getsource(getattr(module, function_name))

    assert "_migrate_host_instances_to_hook" not in source
    assert "_restart_running_instances" not in source
    assert "update_instance_hooks.yml" not in source
    assert "restart_instance_logic" not in source


@pytest.mark.parametrize(
    ("provider", "runner"),
    [
        ("vultr", _run_cloud_setup),
        ("standalone", _run_standalone_setup),
    ],
)
def test_rerun_uses_shared_reconciliation_once_and_stays_active(
    app, provider, runner
):
    host_id = _build_host(
        app,
        provider=provider,
        status=HostStatus.CONFIGURING,
    )
    seen_host_ids = []

    def fake_reconcile(host):
        seen_host_ids.append(host.id)
        host.lan_rate_uses_hook = True
        return 1, 1

    with patch(COMMON_HELPER, side_effect=fake_reconcile) as reconcile, \
         patch(
             "ui.task_logic.ansible_instance_hooks.apply_instance_hooks_logic"
         ) as legacy_hooks, \
         patch(
             "ui.task_logic.ansible_instance_mgmt.restart_instance_logic"
         ) as legacy_restart, \
         patch(
             "ui.task_logic.ansible_runner._run_ansible_playbook"
         ) as legacy_playbook:
        result = runner(app, host_id, rerun=True)

    assert "Status: ACTIVE" in result
    assert reconcile.call_count == 1
    assert seen_host_ids == [host_id]
    legacy_hooks.assert_not_called()
    legacy_restart.assert_not_called()
    legacy_playbook.assert_not_called()

    with app.app_context():
        host = db.session.get(Host, host_id)
        assert host.status == HostStatus.ACTIVE
        assert host.lan_rate_uses_hook is True
        assert (host.logs or "").count(
            "Instance reconciliation after host setup: 1 ok, 1 failed"
        ) == 1


@pytest.mark.parametrize(
    ("provider", "runner"),
    [
        ("vultr", _run_cloud_setup),
        ("standalone", _run_standalone_setup),
    ],
)
def test_initial_setup_skips_reconciliation_and_marks_hook_migration(
    app, provider, runner
):
    host_id = _build_host(
        app,
        provider=provider,
        status=HostStatus.PROVISIONED_PENDING_SETUP,
    )

    with patch(COMMON_HELPER) as reconcile:
        result = runner(app, host_id, rerun=False)

    assert "Status: ACTIVE" in result
    reconcile.assert_not_called()
    with app.app_context():
        host = db.session.get(Host, host_id)
        assert host.status == HostStatus.ACTIVE
        assert host.lan_rate_uses_hook is True
        assert "Instance reconciliation after host setup" not in (host.logs or "")
