"""No SQLite write lock spans a playbook run, and a task's failure status
survives a locked database.

Task code changes rows before a run (status, logs, cpu affinity) and the next
query autoflushes them, opening a write transaction. Held for the whole ansible
run, it made every other writer wait busy_timeout and fail with "database is
locked"; the failing task then could not save ERROR either and the instance
stayed in CONFIGURING behind a job RQ counted as successful.
"""
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from ui import create_app, db
from ui.database import create_host, create_instance
from ui.models import HostStatus, InstanceStatus, QLInstance
from ui.task_logic import common
from ui.task_logic.ansible_runner import (
    SimpleAnsibleResult,
    _run_ansible_playbook,
    _run_host_ansible_playbook,
)
from ui.task_logic.cpu_affinity import ensure_instance_cpu_affinity

TASK_LOGIC_MODULE = 'ui.task_logic.ansible_instance_mgmt'


@pytest.fixture
def file_db(tmp_path):
    """A file-backed database, so a second connection can probe its lock."""
    db_path = tmp_path / 'qlsm.db'
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path.as_posix()}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        yield str(db_path)
        db.session.remove()
        db.engine.dispose()


def _other_writer_can_lock(db_path):
    """True when another connection could start writing right now."""
    conn = sqlite3.connect(db_path, timeout=0)
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.rollback()
        return True
    except sqlite3.OperationalError as exc:
        if 'locked' not in str(exc):
            raise
        return False
    finally:
        conn.close()


def _locked_error():
    return OperationalError('COMMIT', {}, sqlite3.OperationalError('database is locked'))


def _host_with_uncommitted_affinity():
    host = create_host(
        name='lock-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
        ip_address='10.0.0.1',
        ssh_user='root',
        ssh_key_path='key.pem',
    )
    instance = create_instance('lock-inst', host.id, 27960, 'Lock test')
    ensure_instance_cpu_affinity(instance)
    # What the next query's autoflush does: emits the UPDATEs and opens the
    # write transaction the playbook used to run under.
    db.session.flush()
    return host, instance


def _popen_probe(db_path, seen):
    def _popen(*args, **kwargs):
        seen['other_writer_can_lock'] = _other_writer_can_lock(db_path)
        process = MagicMock()
        process.returncode = 0
        process.communicate.return_value = ('', '')
        process.wait.return_value = 0
        return process
    return _popen


def test_instance_playbook_runs_without_holding_the_write_lock(file_db):
    _host, instance = _host_with_uncommitted_affinity()
    assert not _other_writer_can_lock(file_db), 'precondition: the flush holds the lock'

    seen = {}
    with patch('ui.task_logic.ansible_runner.subprocess.Popen', side_effect=_popen_probe(file_db, seen)), \
            patch('ui.task_logic.ansible_runner._stream_output', return_value=('', '')):
        result, error = _run_ansible_playbook(instance, 'add_qlds_instance.yml')

    assert error is None and result.rc == 0
    assert seen == {'other_writer_can_lock': True}
    # The pre-run changes were committed, not dropped.
    db.session.expire_all()
    assert db.session.get(QLInstance, instance.id).cpu_affinity == 0


def test_host_playbook_runs_without_holding_the_write_lock(file_db):
    host, _instance = _host_with_uncommitted_affinity()
    assert not _other_writer_can_lock(file_db), 'precondition: the flush holds the lock'

    seen = {}
    with patch('ui.task_logic.ansible_runner.subprocess.Popen', side_effect=_popen_probe(file_db, seen)):
        success, _stdout, _stderr = _run_host_ansible_playbook(host, 'restart_host.yml', capture_output=True)

    assert success is True
    assert seen == {'other_writer_can_lock': True}


def test_commit_with_retry_reapplies_changes_after_a_locked_commit():
    apply_changes = MagicMock()
    with patch.object(common.time, 'sleep') as sleep, \
            patch('ui.db.session') as session:
        session.commit.side_effect = [_locked_error(), None]
        common.commit_with_retry(apply_changes)

    assert apply_changes.call_count == 2
    assert session.commit.call_count == 2
    session.rollback.assert_called_once()
    sleep.assert_called_once()


def test_commit_with_retry_does_not_retry_other_errors():
    other = OperationalError('COMMIT', {}, sqlite3.OperationalError('disk I/O error'))
    apply_changes = MagicMock()
    with patch.object(common.time, 'sleep'), patch('ui.db.session') as session:
        session.commit.side_effect = other
        with pytest.raises(OperationalError):
            common.commit_with_retry(apply_changes)

    assert apply_changes.call_count == 1
    session.rollback.assert_called_once()


def test_record_task_failure_rolls_back_first_and_raises_when_still_locked():
    calls = []
    apply_changes = MagicMock(side_effect=lambda: calls.append('apply'))
    with patch.object(common.time, 'sleep'), patch('ui.db.session') as session:
        session.rollback.side_effect = lambda: calls.append('rollback')
        session.commit.side_effect = _locked_error()
        with pytest.raises(OperationalError):
            common.record_task_failure(apply_changes)

    attempts = common.DB_LOCKED_RETRY_ATTEMPTS
    assert calls[:2] == ['rollback', 'apply']
    assert apply_changes.call_count == attempts
    assert session.commit.call_count == attempts


def _mock_instance():
    instance = MagicMock(spec=QLInstance)
    instance.id = 12
    instance.port = 27960
    instance.status = InstanceStatus.RUNNING
    instance.lan_rate_enabled = False
    instance.host = MagicMock()
    instance.host.name = 'test-host'
    return instance


@patch(f'{TASK_LOGIC_MODULE}.ensure_instance_cpu_affinity', return_value=None)
@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_ld_preload_paths', return_value='')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_apply_records_error_after_rollback_when_final_commit_is_locked(
    mock_get_job, mock_session, _append_log, _prep_zmq, _build_args,
    _build_preload, mock_run_playbook, _affinity, file_db,
):
    """The 2026-10-19 incident: the playbook succeeded, the status commit
    after it hit a locked database. ERROR must still be saved."""
    from ui.task_logic.ansible_instance_mgmt import apply_instance_config_logic

    mock_get_job.return_value = MagicMock(id='job-1')
    instance = _mock_instance()
    mock_session.get.return_value = instance
    mock_run_playbook.return_value = (SimpleAnsibleResult(0, 'ok', ''), None)

    calls = []
    commits = iter([None, None, _locked_error(), None])

    def _commit():
        calls.append('commit')
        result = next(commits)
        if result is not None:
            raise result

    mock_session.commit.side_effect = _commit
    mock_session.rollback.side_effect = lambda: calls.append('rollback')

    with patch(f'{TASK_LOGIC_MODULE}.service_runtime'), \
            patch('ui.task_logic.access_permission_sync.write_and_report_admin_levels'):
        result = apply_instance_config_logic(12, restart=True)

    assert instance.status == InstanceStatus.ERROR
    assert 'database is locked' in result
    # CONFIGURING, post-affinity, the failed RUNNING commit, then rollback
    # before the ERROR commit -- without it that commit fails as well.
    assert calls == ['commit', 'commit', 'commit', 'rollback', 'commit']


@patch(f'{TASK_LOGIC_MODULE}.ensure_instance_cpu_affinity', return_value=None)
@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook', side_effect=RuntimeError('boom'))
@patch(f'{TASK_LOGIC_MODULE}._build_ld_preload_paths', return_value='')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_raises_when_error_status_cannot_be_saved(
    mock_get_job, mock_session, _append_log, _prep_zmq, _build_args,
    _build_preload, _run_playbook, _affinity, file_db,
):
    """If ERROR cannot be committed either, the job must fail so RQ runs
    instance_job_failure_handler instead of reporting success."""
    from ui.task_logic.ansible_instance_mgmt import deploy_instance_logic

    mock_get_job.return_value = MagicMock(id='job-2')
    instance = _mock_instance()
    mock_session.get.return_value = instance

    commits = iter([None, None])

    def _commit():
        try:
            next(commits)
        except StopIteration:
            raise _locked_error()

    mock_session.commit.side_effect = _commit

    with patch.object(common.time, 'sleep'), pytest.raises(OperationalError):
        deploy_instance_logic(12)

    assert mock_session.rollback.call_count >= 1
    assert instance.status == InstanceStatus.ERROR


def test_commit_with_retry_retries_a_lock_hit_while_applying_changes():
    """After a rollback, apply_changes() reads expired attributes and the
    autoflush can hit the lock before commit(); that attempt is retried too."""
    apply_changes = MagicMock(side_effect=[_locked_error(), None])
    with patch.object(common.time, 'sleep') as sleep, \
            patch('ui.db.session') as session:
        assert common.commit_with_retry(apply_changes) is True

    assert apply_changes.call_count == 2
    session.commit.assert_called_once()
    session.rollback.assert_called_once()
    sleep.assert_called_once()


def test_commit_with_retry_skips_the_write_when_apply_changes_declines():
    with patch('ui.db.session') as session:
        assert common.commit_with_retry(MagicMock(return_value=False)) is False

    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_failure_callback_timeout_covers_the_retry_budget():
    from rq.job import Callback
    from ui import tasks
    from ui.task_logic.job_failure_handlers import instance_job_failure_handler

    assert tasks.FAILURE_CALLBACK_TIMEOUT > common.DB_LOCKED_RETRY_BUDGET_SECONDS
    queue = MagicMock()
    with patch.object(tasks.restart_instance.helper.rq, 'get_queue', return_value=queue):
        tasks.enqueue_task(tasks.restart_instance, 7, lock_token='tok',
                           on_failure=instance_job_failure_handler)

    on_failure = queue.enqueue_call.call_args.kwargs['on_failure']
    assert isinstance(on_failure, Callback)
    assert on_failure.func is instance_job_failure_handler
    assert on_failure.timeout == tasks.FAILURE_CALLBACK_TIMEOUT


def test_delete_saves_error_when_the_pre_playbook_commit_is_locked(file_db):
    """The runner commits before ansible starts; if that commit hits a lock,
    the instance must leave DELETING so the operator can retry the delete."""
    from ui.task_logic.ansible_instance_mgmt import delete_instance_logic

    host = create_host(name='del-host', provider='vultr', region='ewr',
                       machine_size='vhf-2c-2gb', status=HostStatus.ACTIVE,
                       ip_address='10.0.0.1', ssh_user='root', ssh_key_path='key.pem')
    instance = create_instance('del-inst', host.id, 27960, 'Delete test')
    instance.status = InstanceStatus.DELETING
    db.session.commit()
    instance_id = instance.id

    with patch(f'{TASK_LOGIC_MODULE}.get_current_job', return_value=MagicMock(id='job-del')), \
            patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook', side_effect=_locked_error()):
        result = delete_instance_logic(instance_id)

    assert 'deletion' in result
    db.session.expire_all()
    saved = db.session.get(QLInstance, instance_id)
    assert saved.status == InstanceStatus.ERROR
    assert 'database is locked' in saved.logs


def _restart_instance_row():
    host = create_host(name='rs-host', provider='vultr', region='ewr',
                       machine_size='vhf-2c-2gb', status=HostStatus.ACTIVE,
                       ip_address='10.0.0.1', ssh_user='root', ssh_key_path='key.pem')
    instance = create_instance('rs-inst', host.id, 27960, 'Restart test')
    instance.status = InstanceStatus.RUNNING
    db.session.commit()
    return instance


def test_bulk_restart_leaves_a_busy_instance_alone(file_db):
    instance = _restart_instance_row()
    instance.status = InstanceStatus.STOPPED
    instance.logs = 'stop finished'
    db.session.commit()
    with patch('ui.task_lock.acquire_lock', return_value=False), \
            patch('ui.tasks.enqueue_task') as enqueue:
        assert common.queue_instance_restart(
            instance, 'queued', InstanceStatus.RUNNING, 'Plugin updates applied',
            still_ours=lambda fresh: fresh.status == InstanceStatus.RUNNING) is False

    enqueue.assert_not_called()
    # Another operation owns the instance: status and log stay as it left them.
    assert instance.status == InstanceStatus.STOPPED
    assert instance.logs == 'stop finished'


def test_bulk_restart_does_not_restart_an_instance_changed_meanwhile(file_db):
    instance = _restart_instance_row()
    instance.status = InstanceStatus.STOPPED
    db.session.commit()
    with patch('ui.task_lock.acquire_lock', return_value=True), \
            patch('ui.task_lock.release_lock') as release, \
            patch('ui.tasks.enqueue_task') as enqueue:
        assert common.queue_instance_restart(
            instance, 'queued', InstanceStatus.RUNNING, 'Plugin updates applied',
            still_ours=lambda fresh: fresh.status == InstanceStatus.RUNNING) is False

    enqueue.assert_not_called()
    release.assert_called_once()
    assert instance.status == InstanceStatus.STOPPED


def test_bulk_restart_releases_the_lock_when_enqueue_fails(file_db):
    instance = _restart_instance_row()
    with patch('ui.task_lock.acquire_lock', return_value=True), \
            patch('ui.task_lock.release_lock') as release, \
            patch('ui.tasks.enqueue_task', side_effect=RuntimeError('redis down')):
        assert common.queue_instance_restart(
            instance, 'queued', InstanceStatus.RUNNING, 'Plugin updates applied',
            still_ours=lambda fresh: True) is False

    release.assert_called_once()
    assert release.call_args.args[:2] == ('instance', instance.id)
    assert instance.status == InstanceStatus.RUNNING
    assert 'could not queue a restart' in instance.logs
