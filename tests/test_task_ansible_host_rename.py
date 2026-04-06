import os
import pytest
import tempfile
from unittest.mock import MagicMock, patch, call

from ui import create_app, db
from ui.models import Host, HostStatus
from ui.task_logic.ansible_host_rename import _update_inventory_file, _rename_config_folder, rename_host_logic

TASK_LOGIC_MODULE = 'ui.task_logic.ansible_host_rename'

@pytest.fixture(scope='module')
def test_app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SERVER_NAME': 'localhost.test'
    })
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


# ---------------------------------------------------------------------------
# _update_inventory_file
# ---------------------------------------------------------------------------

def _make_yaml_inventory_content(host_name, ip='1.2.3.4', key_path=None):
    if key_path is None:
        key_path = f'/opt/qlds-ui/terraform/ssh-keys/{host_name.lower()}_standalone_id_rsa'
    return (
        f'all:\n'
        f'  hosts:\n'
        f'    {host_name}:\n'
        f'      ansible_host: {ip}\n'
        f'      ansible_user: root\n'
        f'      ansible_ssh_private_key_file: {key_path}\n'
        f'      ansible_port: 22\n'
    )


def _make_ini_inventory_content(host_name, ip='1.2.3.4', key_path=None):
    if key_path is None:
        key_path = f'/opt/qlds-ui/terraform/ssh-keys/{host_name.lower()}_vultr_id_rsa'
    return (
        f'[all]\n'
        f'{host_name} ansible_host={ip} ansible_user=root '
        f'ansible_ssh_private_key_file={key_path} ansible_port=22\n'
    )


def test_update_inventory_file_standalone_suffix():
    """Finds and renames a _standalone_host.yml inventory file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_file = os.path.join(tmpdir, 'my-host_standalone_host.yml')
        with open(old_file, 'w') as f:
            f.write(_make_yaml_inventory_content('my-host'))

        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir):
            success, err = _update_inventory_file('my-host', 'My-Host', MagicMock())

        assert success is True
        assert err is None
        assert not os.path.exists(old_file)
        assert os.path.exists(os.path.join(tmpdir, 'My-Host_standalone_host.yml'))


def test_update_inventory_file_vultr_suffix():
    """Finds and renames a _vultr_host.yml inventory file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ssh_key_path = '/opt/qlds-ui/terraform/ssh-keys/vultr-host_vultr_id_rsa'
        old_file = os.path.join(tmpdir, 'vultr-host_vultr_host.yml')
        with open(old_file, 'w') as f:
            f.write(_make_ini_inventory_content('vultr-host', key_path=ssh_key_path))

        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir):
            success, err = _update_inventory_file('vultr-host', 'Vultr-Host', MagicMock())

        assert success is True
        new_file = os.path.join(tmpdir, 'Vultr-Host_vultr_host.yml')
        assert os.path.exists(new_file)
        assert not os.path.exists(old_file)
        content = open(new_file).read()
        assert 'Vultr-Host ansible_host=' in content
        assert 'vultr-host ansible_host=' not in content
        assert ssh_key_path in content


def test_update_inventory_file_updates_yaml_host_key():
    """YAML host key is updated to new name; SSH key file path is left unchanged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ssh_key_path = '/opt/qlds-ui/terraform/ssh-keys/my-host_standalone_id_rsa'
        old_file = os.path.join(tmpdir, 'my-host_standalone_host.yml')
        with open(old_file, 'w') as f:
            f.write(_make_yaml_inventory_content('my-host', key_path=ssh_key_path))

        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir):
            _update_inventory_file('my-host', 'My-Host', MagicMock())

        content = open(os.path.join(tmpdir, 'My-Host_standalone_host.yml')).read()
        assert 'My-Host:' in content        # YAML key updated
        assert 'my-host:' not in content    # old key gone
        assert ssh_key_path in content      # SSH key path untouched


def test_update_inventory_file_not_found():
    """Returns (False, error_msg) when no matching inventory file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir):
            success, err = _update_inventory_file('missing-host', 'Missing-Host', MagicMock())

    assert success is False
    assert 'missing-host' in err


def test_update_inventory_file_multiple_matches_returns_error():
    """Returns (False, error_msg) when multiple inventory files match — avoids non-deterministic rename."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for suffix in ('_standalone_host.yml', '_vultr_host.yml'):
            with open(os.path.join(tmpdir, f'my-host{suffix}'), 'w') as f:
                f.write(_make_yaml_inventory_content('my-host'))

        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir):
            success, err = _update_inventory_file('my-host', 'My-Host', MagicMock())

    assert success is False
    assert 'Multiple' in err


def test_update_inventory_file_case_only_rename():
    """Case-only rename (thunderdome-king-tx → Thunderdome-King-TX) works correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_file = os.path.join(tmpdir, 'thunderdome-king-tx_standalone_host.yml')
        with open(old_file, 'w') as f:
            f.write(_make_yaml_inventory_content('thunderdome-king-tx', ip='45.33.122.127'))

        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir):
            success, err = _update_inventory_file(
                'thunderdome-king-tx', 'Thunderdome-King-TX', MagicMock()
            )

        assert success is True
        new_file = os.path.join(tmpdir, 'Thunderdome-King-TX_standalone_host.yml')
        assert os.path.exists(new_file)
        content = open(new_file).read()
        assert 'Thunderdome-King-TX:' in content
        assert '45.33.122.127' in content   # IP preserved


# ---------------------------------------------------------------------------
# _rename_config_folder
# ---------------------------------------------------------------------------

def test_rename_config_folder_happy_path():
    """Config folder is renamed when it exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, 'my-host'))

        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir):
            success, err = _rename_config_folder('my-host', 'My-Host')

        assert success is True
        assert err is None
        assert not os.path.exists(os.path.join(tmpdir, 'my-host'))
        assert os.path.exists(os.path.join(tmpdir, 'My-Host'))


def test_rename_config_folder_missing_is_noop():
    """No config folder is not an error — returns True silently."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir):
            success, err = _rename_config_folder('nonexistent-host', 'Nonexistent-Host')

    assert success is True
    assert err is None


def test_rename_config_folder_destination_exists():
    """Returns (False, error) if destination folder already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, 'my-host'))
        os.makedirs(os.path.join(tmpdir, 'My-Host'))

        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir):
            success, err = _rename_config_folder('my-host', 'My-Host')

    assert success is False
    assert 'My-Host' in err


def test_rename_config_folder_os_error():
    """Returns (False, error) when os.rename raises an OSError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, 'my-host'))

        with patch(f'{TASK_LOGIC_MODULE}.os.path.abspath', return_value=tmpdir), \
             patch(f'{TASK_LOGIC_MODULE}.os.rename', side_effect=OSError('Permission denied')):
            success, err = _rename_config_folder('my-host', 'My-Host')

    assert success is False
    assert 'Permission denied' in err


# ---------------------------------------------------------------------------
# rename_host_logic (integration)
# ---------------------------------------------------------------------------

@patch(f'{TASK_LOGIC_MODULE}._run_host_ansible_playbook', return_value=(True, 'ok', ''))
@patch(f'{TASK_LOGIC_MODULE}._rename_config_folder', return_value=(True, None))
@patch(f'{TASK_LOGIC_MODULE}._update_inventory_file', return_value=(True, None))
@patch(f'{TASK_LOGIC_MODULE}.update_host')
@patch(f'{TASK_LOGIC_MODULE}.get_host')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_rename_host_logic_success(
    mock_job, mock_get_host, mock_update_host,
    mock_inv, mock_cfg, mock_ansible, test_app
):
    mock_job.return_value = MagicMock(id='job-1')
    host = Host(id=7, name='My-Host', status=HostStatus.ACTIVE,
                ip_address='1.2.3.4', ssh_key_path='/key', ssh_user='root', logs=None)
    mock_get_host.return_value = host

    result = rename_host_logic(7, 'my-host', 'My-Host')

    assert result is True
    mock_inv.assert_called_once_with('my-host', 'My-Host', host)
    mock_cfg.assert_called_once_with('my-host', 'My-Host')
    mock_ansible.assert_called_once()
    final_status = mock_update_host.call_args_list[-1].kwargs.get('status')
    assert final_status == HostStatus.ACTIVE


@patch(f'{TASK_LOGIC_MODULE}._update_inventory_file', return_value=(False, 'Inventory file not found'))
@patch(f'{TASK_LOGIC_MODULE}.update_host')
@patch(f'{TASK_LOGIC_MODULE}.get_host')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_rename_host_logic_inventory_failure_sets_error(
    mock_job, mock_get_host, mock_update_host, mock_inv, test_app
):
    mock_job.return_value = MagicMock(id='job-2')
    host = Host(id=7, name='My-Host', status=HostStatus.ACTIVE,
                ip_address='1.2.3.4', ssh_key_path='/key', ssh_user='root', logs=None)
    mock_get_host.return_value = host

    result = rename_host_logic(7, 'my-host', 'My-Host')

    assert result is False
    final_status = mock_update_host.call_args_list[-1].kwargs.get('status')
    assert final_status == HostStatus.ERROR


@patch(f'{TASK_LOGIC_MODULE}._run_host_ansible_playbook', return_value=(False, '', 'ansible error'))
@patch(f'{TASK_LOGIC_MODULE}._rename_config_folder', return_value=(True, None))
@patch(f'{TASK_LOGIC_MODULE}._update_inventory_file', return_value=(True, None))
@patch(f'{TASK_LOGIC_MODULE}.update_host')
@patch(f'{TASK_LOGIC_MODULE}.get_host')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_rename_host_logic_ansible_failure_sets_error(
    mock_job, mock_get_host, mock_update_host,
    mock_inv, mock_cfg, mock_ansible, test_app
):
    mock_job.return_value = MagicMock(id='job-3')
    host = Host(id=7, name='My-Host', status=HostStatus.ACTIVE,
                ip_address='1.2.3.4', ssh_key_path='/key', ssh_user='root', logs=None)
    mock_get_host.return_value = host

    result = rename_host_logic(7, 'my-host', 'My-Host')

    assert result is False
    final_status = mock_update_host.call_args_list[-1].kwargs.get('status')
    assert final_status == HostStatus.ERROR


@patch(f'{TASK_LOGIC_MODULE}.update_host')
@patch(f'{TASK_LOGIC_MODULE}.get_host', return_value=None)
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_rename_host_logic_host_not_found(mock_job, mock_get_host, mock_update_host, test_app):
    mock_job.return_value = MagicMock(id='job-4')
    result = rename_host_logic(99, 'ghost', 'Ghost')
    assert result is False
    mock_update_host.assert_not_called()


@patch(f'{TASK_LOGIC_MODULE}._rename_config_folder', return_value=(False, 'Permission denied'))
@patch(f'{TASK_LOGIC_MODULE}._update_inventory_file', return_value=(True, None))
@patch(f'{TASK_LOGIC_MODULE}.update_host')
@patch(f'{TASK_LOGIC_MODULE}.get_host')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_rename_host_logic_config_folder_failure_sets_error(
    mock_job, mock_get_host, mock_update_host, mock_inv, mock_cfg, test_app
):
    """Config folder failure after inventory success sets ERROR and skips Ansible."""
    mock_job.return_value = MagicMock(id='job-5')
    host = Host(id=7, name='My-Host', status=HostStatus.ACTIVE,
                ip_address='1.2.3.4', ssh_key_path='/key', ssh_user='root', logs=None)
    mock_get_host.return_value = host

    with patch(f'{TASK_LOGIC_MODULE}._run_host_ansible_playbook') as mock_ansible:
        result = rename_host_logic(7, 'my-host', 'My-Host')
        mock_ansible.assert_not_called()

    assert result is False
    final_status = mock_update_host.call_args_list[-1].kwargs.get('status')
    assert final_status == HostStatus.ERROR
