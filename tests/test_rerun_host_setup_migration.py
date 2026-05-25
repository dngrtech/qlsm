"""Re-run Host Setup must, after a successful setup_host.yml run, flip the
host's lan_rate_uses_hook flag to True and call apply_instance_hooks_logic
for each instance with lan_rate_enabled=True — by ID, not by ORM iteration."""
from unittest.mock import MagicMock, patch
import tempfile

from ui import create_app
from ui.models import db, Host, HostStatus, QLInstance, InstanceStatus

CLOUD_MODULE = "ui.task_logic.ansible_host_setup"
STANDALONE_MODULE = "ui.task_logic.standalone_host_setup"


def _make_app():
    db_fd, db_path = tempfile.mkstemp()
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "RCON_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
    return app


def _build_host_with_instances(instances_spec, provider="vultr"):
    """Create a Host with QLInstances in the test DB.

    instances_spec: list of (name, lan_rate_enabled) tuples.
    Returns (app, host_id).
    """
    app = _make_app()
    with app.app_context():
        host = Host(
            name="legacy-host",
            provider=provider,
            os_type="debian",
            ip_address="1.2.3.4",
            ssh_key_path="/key",
            ssh_user="ansible",
            status=HostStatus.CONFIGURING,
            lan_rate_uses_hook=False,
        )
        db.session.add(host)
        db.session.commit()
        host_id = host.id
        for idx, (name, lan_rate_enabled) in enumerate(instances_spec):
            db.session.add(QLInstance(
                host_id=host_id,
                name=name,
                hostname=f"QL Server {name}",
                port=27960 + idx,
                lan_rate_enabled=lan_rate_enabled,
                status=InstanceStatus.RUNNING,
            ))
        db.session.commit()
        return app, host_id


# ---------------------------------------------------------------------------
# Test 1 – cloud (ansible_host_setup) rerun migrates only lan_rate=on instances
# ---------------------------------------------------------------------------

@patch(f"{CLOUD_MODULE}.os.path.exists", return_value=True)
@patch(f"{CLOUD_MODULE}.subprocess.run")
@patch(f"{CLOUD_MODULE}.subprocess.Popen")
@patch("ui.task_logic.ansible_runner._stream_output", return_value=("stdout ok", ""))
@patch(f"{CLOUD_MODULE}.get_current_job")
def test_cloud_rerun_migrates_only_lan_rate_enabled_instances(
    mock_job, mock_stream, mock_popen, mock_run, mock_exists
):
    app, host_id = _build_host_with_instances([
        ("i-on", True),
        ("i-off", False),
        ("i-on-2", True),
    ])

    mock_job.return_value = MagicMock(id="job-rerun-1")
    proc = MagicMock()
    proc.returncode = 0
    mock_popen.return_value = proc
    mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)

    with app.app_context():
        enabled_ids = {
            i.id for i in QLInstance.query.filter_by(
                host_id=host_id, lan_rate_enabled=True
            ).all()
        }

    with patch(
        "ui.task_logic.ansible_instance_hooks.apply_instance_hooks_logic",
        return_value=True,
    ) as apply_hooks:
        with app.app_context():
            from ui.task_logic.ansible_host_setup import setup_host_ansible_logic
            setup_host_ansible_logic(host_id, rerun=True)

    with app.app_context():
        host = db.session.get(Host, host_id)
        assert host.lan_rate_uses_hook is True
        assert host.status == HostStatus.ACTIVE

    called_ids = {c.args[0] for c in apply_hooks.call_args_list}
    assert called_ids == enabled_ids
    assert all(
        c.kwargs.get("restart_service") is True
        for c in apply_hooks.call_args_list
    )


# ---------------------------------------------------------------------------
# Test 2 – cloud rerun continues when one instance fails; host still goes ACTIVE
# ---------------------------------------------------------------------------

@patch(f"{CLOUD_MODULE}.os.path.exists", return_value=True)
@patch(f"{CLOUD_MODULE}.subprocess.run")
@patch(f"{CLOUD_MODULE}.subprocess.Popen")
@patch("ui.task_logic.ansible_runner._stream_output", return_value=("stdout ok", ""))
@patch(f"{CLOUD_MODULE}.get_current_job")
def test_cloud_rerun_continues_on_instance_failure(
    mock_job, mock_stream, mock_popen, mock_run, mock_exists
):
    app, host_id = _build_host_with_instances([
        ("i-fail", True),
        ("i-ok", True),
    ])

    mock_job.return_value = MagicMock(id="job-rerun-2")
    proc = MagicMock()
    proc.returncode = 0
    mock_popen.return_value = proc
    mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)

    call_count = [0]

    def _side_effect(instance_id, restart_service=True):
        call_count[0] += 1
        # First call fails, second succeeds
        return call_count[0] != 1

    with patch(
        "ui.task_logic.ansible_instance_hooks.apply_instance_hooks_logic",
        side_effect=_side_effect,
    ) as apply_hooks:
        with app.app_context():
            from ui.task_logic.ansible_host_setup import setup_host_ansible_logic
            setup_host_ansible_logic(host_id, rerun=True)

    with app.app_context():
        host = db.session.get(Host, host_id)
        # Host still becomes ACTIVE despite one instance failure
        assert host.status == HostStatus.ACTIVE
        assert host.lan_rate_uses_hook is True

    assert apply_hooks.call_count == 2


# ---------------------------------------------------------------------------
# Test 3 – standalone rerun migrates lan_rate_enabled instances
# ---------------------------------------------------------------------------

@patch(f"{STANDALONE_MODULE}.os.path.exists", return_value=True)
@patch(f"{STANDALONE_MODULE}.subprocess.run")
@patch(f"{STANDALONE_MODULE}.subprocess.Popen")
@patch("ui.task_logic.ansible_runner._stream_output", return_value=("stdout ok", ""))
@patch(f"{STANDALONE_MODULE}.get_current_job")
@patch("ui.task_logic.standalone_host_setup._generate_standalone_inventory")
@patch("ui.task_logic.standalone_host_setup._wait_for_ssh", return_value=True)
def test_standalone_rerun_migrates_lan_rate_enabled_instances(
    mock_wait_ssh,
    mock_gen_inventory,
    mock_job,
    mock_stream,
    mock_popen,
    mock_run,
    mock_exists,
):
    app, host_id = _build_host_with_instances(
        [
            ("i-on", True),
            ("i-off", False),
        ],
        provider="standalone",
    )

    mock_job.return_value = MagicMock(id="job-standalone-rerun-1")
    proc = MagicMock()
    proc.returncode = 0
    mock_popen.return_value = proc
    mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
    mock_gen_inventory.return_value = ("/tmp/inv.yml", "1.2.3.4")

    with app.app_context():
        enabled_ids = {
            i.id for i in QLInstance.query.filter_by(
                host_id=host_id, lan_rate_enabled=True
            ).all()
        }

    with patch(
        "ui.task_logic.ansible_instance_hooks.apply_instance_hooks_logic",
        return_value=True,
    ) as apply_hooks:
        with app.app_context():
            from ui.task_logic.standalone_host_setup import setup_standalone_host_logic
            setup_standalone_host_logic(host_id, rerun=True)

    with app.app_context():
        host = db.session.get(Host, host_id)
        assert host.lan_rate_uses_hook is True
        assert host.status == HostStatus.ACTIVE

    called_ids = {c.args[0] for c in apply_hooks.call_args_list}
    assert called_ids == enabled_ids
    assert all(
        c.kwargs.get("restart_service") is True
        for c in apply_hooks.call_args_list
    )
