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


@patch('ui.task_logic.plugin_update_check.run_host_ansible_adhoc')
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


@patch('ui.task_logic.plugin_update_check.run_host_ansible_adhoc')
def test_check_common_pool_propagates_error(mock_adhoc, app, temp_config_dir):
    mock_adhoc.return_value = (False, "", "unreachable")

    with app.app_context():
        host = create_host(name='check-pool-unreachable', provider='vultr', status=HostStatus.ACTIVE)
        changes, error = check_common_pool(host)

    assert changes is None
    assert error == "unreachable"


def test_check_instance_selected_plugins_flags_modified_and_new_pool_files(app, temp_config_dir):
    pool_dir = os.path.abspath(MINQLX_PLUGINS_POOL_DIR)
    os.makedirs(pool_dir, exist_ok=True)
    with open(os.path.join(pool_dir, 'present.py'), 'w') as f:
        f.write('new version')
    with open(os.path.join(pool_dir, 'never_had.py'), 'w') as f:
        f.write('added to the pool after this instance was created')

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

        changes = check_instance_selected_plugins(host, inst)

    names = {c["name"]: c["change"] for c in changes}
    # present.py: instance has it, pool content differs -> modified
    assert names.get("present.py") == "modified"
    # never_had.py: instance's scripts/ predates this pool file -> surfaced as
    # "added" so it can be picked up via "Check for Updates" instead of a
    # manual docker cp (the match_restore.py incident this check exists for)
    assert names.get("never_had.py") == "added"


@patch('ui.task_logic.plugin_update_check.run_host_ansible_adhoc')
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
