"""_run_host_ansible_playbook resolves bare names under ansible/playbooks/ and
leaves an absolute path alone -- AddonContext.run_playbook hands it the
absolute path of a playbook inside the addon's own package directory."""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ui.task_logic.ansible_runner import _run_host_ansible_playbook


def _playbook_path_for(playbook_name):
    host = SimpleNamespace(id=1, name='h', ip_address='10.0.0.1', ssh_user='root', ssh_key_path='k')
    process = MagicMock()
    process.communicate.return_value = ('', '')
    process.wait.return_value = 0
    with patch('ui.task_logic.ansible_runner.subprocess.Popen', return_value=process) as popen:
        _run_host_ansible_playbook(host, playbook_name, capture_output=True)
    return popen.call_args[0][0][1]


def test_bare_name_resolves_under_core_playbooks():
    assert _playbook_path_for('setup_host.yml') == os.path.abspath('ansible/playbooks/setup_host.yml')


def test_absolute_path_is_used_as_is(tmp_path):
    addon_playbook = str(tmp_path / 'addon-packages' / 'thing' / 'playbooks' / 'sync_thing.yml')
    assert _playbook_path_for(addon_playbook) == addon_playbook
