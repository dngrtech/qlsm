"""Branching test: reconfigure_instance_lan_rate_logic must call
apply_instance_hooks_logic for migrated hosts and fall through to the
existing legacy code path for non-migrated hosts."""
import pytest
from unittest.mock import patch, MagicMock

from ui import create_app, db
from ui.models import Host, HostStatus, QLInstance, InstanceStatus
from ui.task_logic import ansible_instance_mgmt


@pytest.fixture(scope='module')
def app():
    _app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with _app.app_context():
        db.create_all()
        yield _app
        db.drop_all()


def _make_db_instance(app, lan_rate_uses_hook):
    with app.app_context():
        host = Host(
            name=f"branch-test-{'migrated' if lan_rate_uses_hook else 'legacy'}",
            provider="vultr",
            os_type="debian",
            ip_address="1.2.3.4",
            status=HostStatus.ACTIVE,
            lan_rate_uses_hook=lan_rate_uses_hook,
        )
        db.session.add(host)
        db.session.commit()
        instance = QLInstance(
            host_id=host.id,
            name=f"i-{'migrated' if lan_rate_uses_hook else 'legacy'}",
            hostname="Test Server",
            port=27960,
            lan_rate_enabled=True,
            status=InstanceStatus.CONFIGURING,
        )
        db.session.add(instance)
        db.session.commit()
        return instance.id


TASK_MODULE = 'ui.task_logic.ansible_instance_mgmt'


def test_reconfigure_delegates_to_apply_hooks_on_migrated_host(app):
    instance_id = _make_db_instance(app, lan_rate_uses_hook=True)

    mock_job = MagicMock()
    mock_job.id = "test-job-id"

    with patch(f"{TASK_MODULE}.get_current_job", return_value=mock_job), \
         patch("ui.task_logic.ansible_instance_hooks.apply_instance_hooks_logic",
               return_value=True) as apply_hooks:
        with app.app_context():
            ansible_instance_mgmt.reconfigure_instance_lan_rate_logic(instance_id)

    apply_hooks.assert_called_once_with(instance_id, restart_service=True)


def test_reconfigure_falls_through_to_legacy_on_unmigrated_host(app):
    """On a legacy host, apply_instance_hooks_logic must NOT be called."""
    instance_id = _make_db_instance(app, lan_rate_uses_hook=False)

    mock_job = MagicMock()
    mock_job.id = "test-job-id"

    mock_result = MagicMock()
    mock_result.rc = 0
    mock_result.stats = {"failures": {}}
    mock_result.stdout = MagicMock(return_value="")
    mock_result._stderr = ""

    with patch(f"{TASK_MODULE}.get_current_job", return_value=mock_job), \
         patch("ui.task_logic.ansible_instance_hooks.apply_instance_hooks_logic") as apply_hooks, \
         patch(f"{TASK_MODULE}._run_ansible_playbook",
               return_value=(mock_result, None)) as mock_runner:
        with app.app_context():
            ansible_instance_mgmt.reconfigure_instance_lan_rate_logic(instance_id)

    apply_hooks.assert_not_called()
    mock_runner.assert_called_once()
