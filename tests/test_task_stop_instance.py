from unittest.mock import MagicMock, patch

from ui import create_app
from ui.models import Host, QLInstance, InstanceStatus
from ui.task_logic.ansible_instance_mgmt import stop_instance_logic
from ui.task_logic.ansible_runner import SimpleAnsibleResult

MOD = "ui.task_logic.ansible_instance_mgmt"


def _mock_instance():
    host = MagicMock(spec=Host)
    host.name = "test-host"
    host.ip_address = "1.2.3.4"
    host.ssh_user = "testuser"
    host.ssh_key_path = "/fake/key.pem"

    inst = MagicMock(spec=QLInstance)
    inst.id = 7
    inst.port = 27960
    inst.status = InstanceStatus.RUNNING
    inst.host = host
    return inst


@patch(f"{MOD}._run_ansible_playbook")
@patch(f"{MOD}.append_log")
@patch(f"{MOD}.db.session")
@patch(f"{MOD}.get_current_job", return_value=None)
def test_stop_instance_logic_without_rq_job(mock_job, mock_session, mock_log, mock_run):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        inst = _mock_instance()
        mock_session.get.return_value = inst
        mock_run.return_value = (SimpleAnsibleResult(0, "ok", ""), None)

        result = stop_instance_logic(7)

    assert inst.status == InstanceStatus.STOPPED
    assert "stop successful" in result
