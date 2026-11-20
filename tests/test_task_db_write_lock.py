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
