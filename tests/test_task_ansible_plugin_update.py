import os
import shutil
import pytest
from unittest.mock import patch, MagicMock
from ui.task_logic.ansible_plugin_update import apply_plugin_updates_logic
from ui.models import HostStatus, InstanceStatus
from ui.database import create_host, get_host, get_instance

# The default-runtime (minqlx) pool -- these tests use hosts with no
# explicit runtime, which normalizes to minqlx.
MINQLX_PLUGINS_POOL_DIR = os.path.join('ql-assets', 'data', 'minqlx-plugins')


@pytest.fixture
def mock_restart_instance_queue():
    # Restarts go through enqueue_task under the instance lock
    # (common.queue_instance_restart); yields the enqueue_task mock.
    with patch('ui.task_lock.acquire_lock', return_value=True),             patch('ui.task_lock.release_lock'),             patch('ui.tasks.enqueue_task') as mock:
        yield mock


def _assert_restart_queued(enqueue, instance_id):
    from ui.tasks import restart_instance
    from ui.task_logic.job_failure_handlers import instance_job_failure_handler
    enqueue.assert_called_once()
    args, kwargs = enqueue.call_args
    assert args == (restart_instance, instance_id)
    assert kwargs['lock_token']
    assert kwargs['on_failure'] is instance_job_failure_handler


@pytest.fixture
def mock_run_playbook():
    with patch('ui.task_logic.ansible_plugin_update._run_host_ansible_playbook') as mock:
        yield mock


@pytest.fixture
def mock_get_current_job():
    with patch('ui.task_logic.ansible_plugin_update.get_current_job') as mock:
        mock_job = MagicMock()
        mock_job.id = 'test-job-id'
        mock.return_value = mock_job
        yield mock


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    """Runs the test with CWD pointed at a scratch dir so configs/<host>/<id>/scripts/
    writes land somewhere disposable, not the real repo tree."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_apply_common_pool_only(app, mock_run_playbook, mock_get_current_job, mock_restart_instance_queue, temp_config_dir):
    mock_run_playbook.return_value = (True, "mock stdout", "mock stderr")

    with app.app_context():
        host = create_host(name='test-host-plugins', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

        result = apply_plugin_updates_logic(host_id, True, {}, [])

        assert result is True
        mock_run_playbook.assert_called_once()
        mock_restart_instance_queue.assert_not_called()

        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ACTIVE
        assert 'refreshed' in updated_host.logs


def test_apply_common_pool_failure(app, mock_run_playbook, mock_get_current_job, mock_restart_instance_queue, temp_config_dir):
    mock_run_playbook.return_value = (False, "mock stdout", "error running playbook")

    with app.app_context():
        host = create_host(name='test-host-plugins-fail', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

        result = apply_plugin_updates_logic(host_id, True, {}, [])

        assert result is False
        mock_restart_instance_queue.assert_not_called()

        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ERROR
        assert 'failed' in updated_host.logs.lower()


def test_apply_instance_selected_plugin_copies_file_and_queues_restart(
    app, mock_run_playbook, mock_get_current_job, mock_restart_instance_queue, temp_config_dir
):
    # A real pool plugin file, e.g. match_restore.py, must actually exist on
    # disk for the copy to happen — use whatever the repo ships, or fall back
    # to a throwaway one so this test doesn't depend on pool contents.
    pool_dir = os.path.abspath(MINQLX_PLUGINS_POOL_DIR)
    os.makedirs(pool_dir, exist_ok=True)
    with open(os.path.join(pool_dir, 'sample_plugin.py'), 'w') as f:
        f.write('# pool version\n')

    with app.app_context():
        from ui.database import db
        from ui.models import QLInstance

        host = create_host(name='test-host-instance-sel', provider='vultr', status=HostStatus.ACTIVE)
        inst = QLInstance(name='inst-1', port=27960, hostname='server1', host_id=host.id, status=InstanceStatus.RUNNING)
        db.session.add(inst)
        db.session.commit()

        host_id = host.id
        inst_id = inst.id

        result = apply_plugin_updates_logic(host_id, False, {inst_id: ['sample_plugin.py']}, [inst_id])

        assert result is True
        mock_run_playbook.assert_not_called()  # no common pool refresh requested
        _assert_restart_queued(mock_restart_instance_queue, inst_id)

        dest = os.path.join('configs', host.name, str(inst_id), 'scripts', 'sample_plugin.py')
        assert os.path.isfile(dest)
        with open(dest) as f:
            assert f.read() == '# pool version\n'

        updated_inst = get_instance(inst_id)
        assert updated_inst.status == InstanceStatus.RESTARTING


def test_apply_skips_stopped_instances_for_restart(app, mock_run_playbook, mock_get_current_job, mock_restart_instance_queue, temp_config_dir):
    mock_run_playbook.return_value = (True, "mock stdout", "mock stderr")

    with app.app_context():
        from ui.database import db
        from ui.models import QLInstance

        host = create_host(name='test-host-stopped', provider='vultr', status=HostStatus.ACTIVE)
        inst = QLInstance(name='inst-1', port=27960, hostname='server1', host_id=host.id, status=InstanceStatus.STOPPED)
        db.session.add(inst)
        db.session.commit()

        host_id = host.id
        inst_id = inst.id

        result = apply_plugin_updates_logic(host_id, True, {}, [inst_id])

        assert result is True
        mock_restart_instance_queue.assert_not_called()

        updated_inst = get_instance(inst_id)
        assert updated_inst.status == InstanceStatus.STOPPED


def test_apply_plugin_updates_host_not_found(app):
    with app.app_context():
        result = apply_plugin_updates_logic(99999, True, {}, [])
        assert result is False


def test_apply_instance_selected_plugin_prefers_the_operator_copy(
    app, mock_run_playbook, mock_get_current_job, mock_restart_instance_queue, temp_config_dir
):
    builtin = os.path.abspath(MINQLX_PLUGINS_POOL_DIR)
    operator = os.path.abspath(os.path.join('data', 'shared-plugins', 'minqlx'))
    os.makedirs(builtin); os.makedirs(operator)
    with open(os.path.join(builtin, 'sample_plugin.py'), 'w') as f:
        f.write('# bundled version\n')
    with open(os.path.join(operator, 'sample_plugin.py'), 'w') as f:
        f.write('# operator version\n')

    with app.app_context():
        from ui.database import db
        from ui.models import QLInstance

        host = create_host(name='test-host-operator-sel', provider='vultr', status=HostStatus.ACTIVE)
        inst = QLInstance(name='inst-1', port=27960, hostname='server1', host_id=host.id, status=InstanceStatus.RUNNING)
        db.session.add(inst)
        db.session.commit()

        result = apply_plugin_updates_logic(host.id, False, {inst.id: ['sample_plugin.py', 'missing.py']}, [])
        assert result is True

        dest = os.path.join('configs', host.name, str(inst.id), 'scripts', 'sample_plugin.py')
        with open(dest) as f:
            assert f.read() == '# operator version\n'
        assert not os.path.exists(os.path.join('configs', host.name, str(inst.id), 'scripts', 'missing.py'))
