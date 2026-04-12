from pathlib import Path
from unittest.mock import patch

from ui import db
from ui.models import Host, HostStatus
from ui.task_logic.standalone_host_remove import remove_standalone_host_logic


def _create_host(**overrides):
    defaults = dict(
        name='self-host',
        provider='self',
        is_standalone=True,
        status=HostStatus.ACTIVE,
        ip_address='203.0.113.10',
        ssh_user='root',
        ssh_port=22,
    )
    defaults.update(overrides)
    host = Host(**defaults)
    db.session.add(host)
    db.session.commit()
    return host


@patch('ui.task_logic.standalone_host_remove.get_current_job')
@patch('ui.task_logic.standalone_host_remove.remove_authorized_key')
def test_remove_standalone_host_removes_self_authorized_key(
    mock_remove_key, mock_job, app, tmp_path
):
    """Self-host destroy task reads the pub key and removes it from
    authorized_keys before unlinking the file."""
    mock_job.return_value.id = 'job-1'

    key_path = tmp_path / 'self_id_rsa'
    key_path.write_text('private')
    pub_path = Path(str(key_path) + '.pub')
    pub_path.write_text('ssh-rsa self-host-key\n')

    with app.app_context():
        host = _create_host(ssh_key_path=str(key_path))
        host_id = host.id

        result = remove_standalone_host_logic(host_id)

    assert 'removed from inventory' in result
    mock_remove_key.assert_called_once_with('ssh-rsa self-host-key')
    assert not pub_path.exists()
    assert not key_path.exists()


@patch('ui.task_logic.standalone_host_remove.get_current_job')
@patch('ui.task_logic.standalone_host_remove.remove_managed_key_via_key')
@patch('ui.task_logic.standalone_host_remove.remove_authorized_key')
def test_remove_standalone_host_skips_key_removal_for_non_self_provider(
    mock_remove_key, mock_remove_managed, mock_job, app, tmp_path
):
    """Standalone (non-self) hosts must not touch authorized_keys."""
    mock_job.return_value.id = 'job-2'

    key_path = tmp_path / 'standalone_id_rsa'
    key_path.write_text('private')
    Path(str(key_path) + '.pub').write_text('ssh-rsa standalone-key\n')

    with app.app_context():
        host = _create_host(
            name='standalone-host',
            provider='user-provided',
            ssh_key_path=str(key_path),
        )
        host_id = host.id

        remove_standalone_host_logic(host_id)

    mock_remove_key.assert_not_called()
    mock_remove_managed.assert_not_called()


@patch('ui.task_logic.standalone_host_remove.get_current_job')
@patch('ui.task_logic.standalone_host_remove.remove_authorized_key')
def test_remove_standalone_host_continues_when_key_removal_fails(
    mock_remove_key, mock_job, app, tmp_path
):
    """A failure to scrub authorized_keys must not abort host destruction —
    the host record is still deleted so the operator is not left with a
    zombie row."""
    mock_job.return_value.id = 'job-3'
    mock_remove_key.side_effect = OSError('permission denied')

    key_path = tmp_path / 'self_id_rsa'
    key_path.write_text('private')
    Path(str(key_path) + '.pub').write_text('ssh-rsa failing-key\n')

    with app.app_context():
        host = _create_host(ssh_key_path=str(key_path))
        host_id = host.id

        result = remove_standalone_host_logic(host_id)

        assert db.session.get(Host, host_id) is None

    assert 'removed from inventory' in result
    mock_remove_key.assert_called_once()


@patch('ui.task_logic.standalone_host_remove.append_log')
@patch('ui.task_logic.standalone_host_remove.get_current_job')
@patch('ui.task_logic.standalone_host_remove.remove_authorized_key', return_value=False)
def test_remove_standalone_host_warns_when_authorized_key_missing(
    mock_remove_key, mock_job, mock_append_log, app, tmp_path
):
    """If the key is already missing from authorized_keys, the task should
    warn instead of claiming successful removal."""
    mock_job.return_value.id = 'job-4'

    key_path = tmp_path / 'self_id_rsa'
    key_path.write_text('private')
    Path(str(key_path) + '.pub').write_text('ssh-rsa missing-key\n')

    with app.app_context():
        host = _create_host(ssh_key_path=str(key_path))
        host_id = host.id

        result = remove_standalone_host_logic(host_id)

        assert db.session.get(Host, host_id) is None

    messages = [call.args[1] for call in mock_append_log.call_args_list if len(call.args) > 1]
    assert 'removed from inventory' in result
    mock_remove_key.assert_called_once_with('ssh-rsa missing-key')
    assert "Removed self-host public key from authorized_keys" not in messages
    assert "Warning: Self-host public key was not present in authorized_keys" in messages


@patch('ui.task_logic.standalone_host_remove.get_current_job')
@patch('ui.task_logic.standalone_host_remove.remove_managed_key_via_key', return_value=True)
def test_remove_standalone_host_removes_managed_remote_key(
    mock_remove_managed, mock_job, app, tmp_path
):
    """Managed standalone hosts remove the QLSM-owned remote authorized_keys
    entry before deleting local key material."""
    mock_job.return_value.id = 'job-5'

    key_path = tmp_path / 'managed_id_rsa'
    key_path.write_text('private')
    pub_path = Path(str(key_path) + '.pub')
    pub_path.write_text('ssh-rsa managed-key\n')

    with app.app_context():
        host = _create_host(
            name='standalone-host',
            provider='standalone',
            ssh_key_path=str(key_path),
        )
        host_id = host.id

        result = remove_standalone_host_logic(host_id)

        assert db.session.get(Host, host_id) is None

    assert 'removed from inventory' in result
    mock_remove_managed.assert_called_once_with(
        host='203.0.113.10',
        port=22,
        username='root',
        private_key_path=str(key_path),
    )
    assert not pub_path.exists()
    assert not key_path.exists()


@patch('ui.task_logic.standalone_host_remove.append_log')
@patch('ui.task_logic.standalone_host_remove.get_current_job')
@patch('ui.task_logic.standalone_host_remove.remove_managed_key_via_key', side_effect=OSError('permission denied'))
def test_remove_standalone_host_warns_when_managed_key_cleanup_fails(
    mock_remove_managed, mock_job, mock_append_log, app, tmp_path
):
    """Managed-key cleanup failures must not block host deletion."""
    mock_job.return_value.id = 'job-6'

    key_path = tmp_path / 'managed_id_rsa'
    key_path.write_text('private')
    Path(str(key_path) + '.pub').write_text('ssh-rsa managed-key\n')

    with app.app_context():
        host = _create_host(
            name='standalone-host',
            provider='standalone',
            ssh_key_path=str(key_path),
        )
        host_id = host.id

        result = remove_standalone_host_logic(host_id)

        assert db.session.get(Host, host_id) is None

    messages = [call.args[1] for call in mock_append_log.call_args_list if len(call.args) > 1]
    assert 'removed from inventory' in result
    mock_remove_managed.assert_called_once()
    assert any('Warning: Failed to remove managed standalone SSH key' in message for message in messages)
