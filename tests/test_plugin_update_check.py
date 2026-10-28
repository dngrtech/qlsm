import os
import pytest
from unittest.mock import patch
from ui.database import create_host
from ui.models import HostStatus, InstanceStatus
from ui.task_logic.plugin_update_check import (
    check_common_pool, check_instance_selected_plugins, check_host_updates,
)

# The default-runtime (minqlx) pool -- these tests use hosts with no
# explicit runtime, which normalizes to minqlx.
MINQLX_PLUGINS_POOL_DIR = os.path.join('ql-assets', 'data', 'minqlx-plugins')


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


@patch('ui.task_logic.plugin_update_check.run_host_ssh_command')
def test_check_common_pool_reports_modified_and_added(mock_adhoc, app, temp_config_dir):
    pool_dir = os.path.abspath(MINQLX_PLUGINS_POOL_DIR)
    os.makedirs(pool_dir, exist_ok=True)
    with open(os.path.join(pool_dir, 'a.py'), 'w') as f:
        f.write('new content')
    with open(os.path.join(pool_dir, 'b.py'), 'w') as f:
        f.write('unchanged')

    from ui.update_checks import hash_file
    stale_hash = 'deadbeef' * 4  # deliberately wrong so a.py shows as modified
    unchanged_hash = hash_file(os.path.join(pool_dir, 'b.py'))
    mock_adhoc.return_value = (
        True,
        f"{stale_hash}  /home/ql/assets/common/minqlx-plugins/a.py\n"
        f"{unchanged_hash}  /home/ql/assets/common/minqlx-plugins/b.py\n",
        "",
    )

    with app.app_context():
        host = create_host(name='check-pool-host', provider='vultr', status=HostStatus.ACTIVE)
        changes, error = check_common_pool(host)

    assert error is None
    names = {c["name"]: c["change"] for c in changes}
    assert names.get("a.py") == "modified"
    assert "b.py" not in names


@patch('ui.task_logic.plugin_update_check.run_host_ssh_command')
def test_check_common_pool_propagates_error(mock_adhoc, app, temp_config_dir):
    mock_adhoc.return_value = (False, "", "unreachable")

    with app.app_context():
        host = create_host(name='check-pool-unreachable', provider='vultr', status=HostStatus.ACTIVE)
        changes, error = check_common_pool(host)

    assert changes is None
    assert error == "unreachable"


def test_check_instance_selected_plugins_reports_only_modified_files(app, temp_config_dir):
    pool_dir = os.path.abspath(MINQLX_PLUGINS_POOL_DIR)
    os.makedirs(pool_dir, exist_ok=True)
    with open(os.path.join(pool_dir, 'present.py'), 'w') as f:
        f.write('new version')
    with open(os.path.join(pool_dir, 'never_had.py'), 'w') as f:
        f.write('pool-only plugin, delivered by the restart backfill')

    with app.app_context():
        from ui.database import db
        from ui.models import QLInstance

        host = create_host(name='check-instance-host', provider='vultr', status=HostStatus.ACTIVE)
        inst = QLInstance(name='inst-1', port=27960, hostname='server1', host_id=host.id, status=InstanceStatus.RUNNING)
        db.session.add(inst)
        db.session.commit()

        scripts_dir = os.path.join('configs', host.name, str(inst.id), 'scripts')
        os.makedirs(scripts_dir, exist_ok=True)
        with open(os.path.join(scripts_dir, 'present.py'), 'w') as f:
            f.write('stale local copy')
        with open(os.path.join(scripts_dir, 'highfps.py'), 'w') as f:
            f.write('preset-only plugin, not in the pool')

        changes = check_instance_selected_plugins(host, inst)

    # present.py: instance has it, pool content differs -> modified.
    # never_had.py (pool only) and highfps.py (instance only) aren't stale
    # copies, so neither is reported.
    assert changes == [{"name": "present.py", "change": "modified"}]


@patch('ui.task_logic.plugin_update_check.run_host_ssh_command')
def test_check_host_updates_aggregates_instances(mock_adhoc, app, temp_config_dir):
    mock_adhoc.return_value = (True, "", "")

    with app.app_context():
        from ui.database import db
        from ui.models import QLInstance

        host = create_host(name='check-agg-host', provider='vultr', status=HostStatus.ACTIVE)
        inst = QLInstance(name='inst-1', port=27960, hostname='server1', host_id=host.id, status=InstanceStatus.RUNNING)
        db.session.add(inst)
        db.session.commit()

        result = check_host_updates(host)

    assert result["host_id"] == host.id
    assert result["common_pool_changes"] == []
    assert len(result["instances"]) == 1
    assert result["instances"][0]["id"] == inst.id
    assert result["instances"][0]["selected_plugin_changes"] == []


@patch('ui.task_logic.plugin_update_check.run_host_ssh_command')
def test_check_common_pool_uses_the_operator_copy_over_the_built_in(mock_adhoc, app, temp_config_dir):
    """A repo download that shadows a bundled plugin, or adds a new one, is
    what the host must be compared against -- workers read the same data/
    mount the web process wrote to."""
    builtin = os.path.abspath(MINQLX_PLUGINS_POOL_DIR)
    operator = os.path.abspath(os.path.join('data', 'shared-plugins', 'minqlx'))
    os.makedirs(builtin); os.makedirs(operator)
    with open(os.path.join(builtin, 'balance.py'), 'w') as f:
        f.write('bundled')
    with open(os.path.join(operator, 'balance.py'), 'w') as f:
        f.write('operator')
    with open(os.path.join(operator, 'backfire.py'), 'w') as f:
        f.write('downloaded')

    from ui.update_checks import hash_file
    mock_adhoc.return_value = (
        True,
        f"{hash_file(os.path.join(builtin, 'balance.py'))}  /home/ql/assets/common/minqlx-plugins/balance.py\n",
        "",
    )

    with app.app_context():
        host = create_host(name='check-pool-operator', provider='vultr', status=HostStatus.ACTIVE)
        changes, error = check_common_pool(host)

    assert error is None
    names = {c["name"]: c["change"] for c in changes}
    assert names == {"balance.py": "modified", "backfire.py": "added"}


def _host_with_instance(name):
    from ui.database import db
    from ui.models import QLInstance

    host = create_host(name=name, provider='vultr', status=HostStatus.ACTIVE)
    inst = QLInstance(name='inst-1', port=27960, hostname='server1', host_id=host.id, status=InstanceStatus.RUNNING)
    db.session.add(inst)
    db.session.commit()
    scripts_dir = os.path.join('configs', host.name, str(inst.id), 'scripts')
    os.makedirs(scripts_dir, exist_ok=True)
    return host, inst, scripts_dir


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def test_check_instance_selected_plugins_sees_stale_package_folder(app, temp_config_dir):
    pool_dir = os.path.abspath(MINQLX_PLUGINS_POOL_DIR)
    _write(os.path.join(pool_dir, 'pkg_plugin.py'), 'same')
    _write(os.path.join(pool_dir, 'restore', '__init__.py'), 'same')
    _write(os.path.join(pool_dir, 'restore', 'items.py'), 'new items with note_item_pickup')
    _write(os.path.join(pool_dir, 'restore', 'fresh.py'), 'module added to the package upstream')

    with app.app_context():
        host, inst, scripts_dir = _host_with_instance('check-package-host')
        _write(os.path.join(scripts_dir, 'pkg_plugin.py'), 'same')
        _write(os.path.join(scripts_dir, 'restore', '__init__.py'), 'same')
        _write(os.path.join(scripts_dir, 'restore', 'items.py'), 'old items')
        _write(os.path.join(scripts_dir, 'restore', 'custom_only.py'), 'only the instance has it')
        _write(os.path.join(scripts_dir, 'restore', '__pycache__', 'items.cpython-312.pyc.py'), 'ignored')

        changes = check_instance_selected_plugins(host, inst)

    assert changes == [
        {"name": "restore/fresh.py", "change": "added"},
        {"name": "restore/items.py", "change": "modified"},
    ]


def test_check_instance_selected_plugins_ignores_package_the_instance_lacks(app, temp_config_dir):
    pool_dir = os.path.abspath(MINQLX_PLUGINS_POOL_DIR)
    _write(os.path.join(pool_dir, 'restore', 'items.py'), 'pool only package')

    with app.app_context():
        host, inst, scripts_dir = _host_with_instance('check-nopackage-host')
        _write(os.path.join(scripts_dir, 'other.py'), 'x')

        assert check_instance_selected_plugins(host, inst) == []


def test_apply_copies_package_members_and_refuses_unsafe_paths(app, temp_config_dir):
    from ui.task_logic.ansible_plugin_update import _copy_selected_plugin_files

    pool_dir = os.path.abspath(MINQLX_PLUGINS_POOL_DIR)
    _write(os.path.join(pool_dir, 'restore', 'items.py'), 'new items')
    _write(os.path.join(pool_dir, 'plain.py'), 'plain')

    with app.app_context():
        host, inst, scripts_dir = _host_with_instance('apply-package-host')
        applied, skipped = _copy_selected_plugin_files(
            host, inst,
            ['restore/items.py', 'plain.py', '../evil.py', 'restore/../../evil.py', '/abs/x.py', 'restore//x.py', 'restore/nope.py'],
        )

        assert sorted(applied) == ['plain.py', 'restore/items.py']
        assert sorted(skipped) == sorted(['../evil.py', 'restore/../../evil.py', '/abs/x.py', 'restore//x.py', 'restore/nope.py'])
        with open(os.path.join(scripts_dir, 'restore', 'items.py')) as f:
            assert f.read() == 'new items'
        assert not os.path.exists(os.path.join(scripts_dir, '..', 'evil.py'))
