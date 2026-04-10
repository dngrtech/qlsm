from types import SimpleNamespace

from ui.task_logic.standalone_inventory import (
    generate_standalone_inventory,
    inventory_filename_for_host,
)


def _host(provider='standalone'):
    return SimpleNamespace(
        id=1,
        name='test-host',
        provider=provider,
        ip_address='172.17.0.1',
        ssh_user='rage',
        ssh_key_path='/tmp/self-key',
        ssh_port=22,
    )


def test_inventory_filename_for_standalone():
    assert inventory_filename_for_host(_host('standalone')) == 'test-host_standalone_host.yml'


def test_inventory_filename_for_self():
    assert inventory_filename_for_host(_host('self')) == 'test-host_self_host.yml'


def test_generate_self_inventory_writes_ssh_inventory(tmp_path):
    path = generate_standalone_inventory(_host('self'), inventory_dir=tmp_path)

    assert path == str(tmp_path / 'test-host_self_host.yml')
    content = (tmp_path / 'test-host_self_host.yml').read_text()
    assert 'ansible_host: 172.17.0.1' in content
    assert 'ansible_user: rage' in content
    assert 'ansible_ssh_private_key_file: /tmp/self-key' in content
    assert 'ansible_port: 22' in content


def test_inventory_filename_used_for_self_cleanup():
    host = _host('self')

    assert inventory_filename_for_host(host) == 'test-host_self_host.yml'
