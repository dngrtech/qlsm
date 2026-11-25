import pytest
from unittest.mock import patch, MagicMock
from ui.task_logic.ansible_workshop_update import force_update_workshop_logic
from ui.models import HostStatus, InstanceStatus
from ui.database import create_host, get_host, get_instance

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
    with patch('ui.task_logic.ansible_workshop_update._run_host_ansible_playbook') as mock:
        yield mock

@pytest.fixture
def mock_get_current_job():
    with patch('ui.task_logic.ansible_workshop_update.get_current_job') as mock:
        mock_job = MagicMock()
        mock_job.id = 'test-job-id'
        mock.return_value = mock_job
        yield mock

def test_force_update_workshop_success_no_restarts(app, mock_run_playbook, mock_get_current_job, mock_restart_instance_queue):
    mock_run_playbook.return_value = (True, "mock stdout", "mock stderr")
    
    with app.app_context():
        host = create_host(name='test-host-workshop', provider='vultr', status=HostStatus.ACTIVE)
        from ui.database import db
        from ui.models import QLInstance
        
        inst1 = QLInstance(name='inst-1', port=27960, hostname='server1', host_id=host.id, status=InstanceStatus.RUNNING)
        inst2 = QLInstance(name='inst-2', port=27961, hostname='server2', host_id=host.id, status=InstanceStatus.STOPPED)
        db.session.add_all([inst1, inst2])
        db.session.commit()
        
        host_id = host.id
        inst1_id = inst1.id
        inst2_id = inst2.id

        result = force_update_workshop_logic(host_id, '123456', [])
        
        assert result is True
        mock_run_playbook.assert_called_once()
        mock_restart_instance_queue.assert_not_called()
        
        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ACTIVE
        assert 'Workshop item 123456 updated' in updated_host.logs
        
        updated_inst1 = get_instance(inst1_id)
        assert updated_inst1.status == InstanceStatus.UPDATED
        
        updated_inst2 = get_instance(inst2_id)
        assert updated_inst2.status == InstanceStatus.STOPPED
        assert 'service left stopped' in updated_inst2.logs


def test_force_update_workshop_success_with_restarts(app, mock_run_playbook, mock_get_current_job, mock_restart_instance_queue):
    mock_run_playbook.return_value = (True, "mock stdout", "")
    
    with app.app_context():
        host = create_host(name='test-host-workshop2', provider='vultr', status=HostStatus.ACTIVE)
        from ui.database import db
        from ui.models import QLInstance
        
        inst1 = QLInstance(name='inst-1', port=27960, hostname='server1', host_id=host.id, status=InstanceStatus.RUNNING)
        inst2 = QLInstance(name='inst-2', port=27961, hostname='server2', host_id=host.id, status=InstanceStatus.STOPPED)
        db.session.add_all([inst1, inst2])
        db.session.commit()
        
        host_id = host.id
        inst1_id = inst1.id
        inst2_id = inst2.id

        result = force_update_workshop_logic(host_id, '123456', [inst1_id, inst2_id])
        
        assert result is True
        mock_run_playbook.assert_called_once()
        _assert_restart_queued(mock_restart_instance_queue, inst1_id) # Should only queue inst-1 since inst-2 is STOPPED
        
        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ACTIVE
        
        updated_inst1 = get_instance(inst1_id)
        assert updated_inst1.status == InstanceStatus.RESTARTING
        
        updated_inst2 = get_instance(inst2_id)
        assert updated_inst2.status == InstanceStatus.STOPPED # Didn't restart
        assert 'service left stopped' in updated_inst2.logs


def test_force_update_workshop_ansible_failure(app, mock_run_playbook, mock_get_current_job, mock_restart_instance_queue):
    mock_run_playbook.return_value = (False, "mock stdout", "error running playbook")
    
    with app.app_context():
        host = create_host(name='test-host-workshop3', provider='vultr', status=HostStatus.ACTIVE)
        from ui.database import db
        from ui.models import QLInstance
        
        inst1 = QLInstance(name='inst-1', port=27960, hostname='server1', host_id=host.id, status=InstanceStatus.RUNNING)
        db.session.add(inst1)
        db.session.commit()
        
        host_id = host.id
        inst1_id = inst1.id

        result = force_update_workshop_logic(host_id, '123456', [inst1_id])
        
        assert result is False
        mock_run_playbook.assert_called_once()
        mock_restart_instance_queue.assert_not_called()
        
        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ERROR
        assert 'Workshop update failed: error running playbook' in updated_host.logs
        
        updated_inst1 = get_instance(inst1_id)
        assert updated_inst1.status == InstanceStatus.RUNNING # Reverted
        assert 'Workshop update failed. Reverting state' in updated_inst1.logs


def test_force_update_workshop_host_not_found(app):
    with app.app_context():
        result = force_update_workshop_logic(99999, '123456', [])
        assert result is False
