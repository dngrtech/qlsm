"""ui/task_logic/instance_runtime_update.py: the Python entry points Task 5
calls to install minqlxtended on a host and to configure existing instances
(upgrade and rollback). The Ansible runner is monkeypatched; nothing runs
against any host."""
import json
import os
import tarfile

import pytest

from ui import db
from ui.models import Host, HostStatus, InstanceStatus, QLInstance
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.runtime import MINQLX, MINQLXTENDED, runtime_paths
from ui.task_logic import instance_runtime_update as mod

OP = 'c' * 32
OLD_OP = 'd' * 32
VENV = f'/home/ql/runtime-deps/minqlxtended/{OP}/1'


@pytest.fixture
def env(app, tmp_path, monkeypatch):
    app.config['RUNTIME_UPGRADES_DIR'] = str(tmp_path / 'upgrades')
    calls = []
    outcome = {'ok': True, 'stdout': 'ok', 'stderr': ''}

    def fake_runner(host, playbook_name, extravars=None, capture_output=False):
        record = {'host': host.name, 'playbook': playbook_name, 'extravars': dict(extravars or {})}
        archive = (extravars or {}).get('stage_archive')
        if archive:
            with tarfile.open(archive) as tar:
                record['archive'] = sorted(m.name for m in tar.getmembers() if m.isfile())
                record['archive_bytes'] = {m.name: tar.extractfile(m).read()
                                           for m in tar.getmembers() if m.isfile()}
        calls.append(record)
        return outcome['ok'], outcome['stdout'], outcome['stderr']

    monkeypatch.setattr(mod, '_run_host_ansible_playbook', fake_runner)

    config_dir = tmp_path / 'inputs' / 'instances' / '1'
    files = {
        'server.cfg': b'set sv_hostname "x"\n',
        'access.txt': b'76561198000000001|admin\n',
        'cfgs/nested/extra.cfg': b'set g_x 1\n',
        'notes.md': b'not managed\n',
        'scripts/balance.py': b'import minqlxtended\n',
        'scripts/requirements.txt': b'requests\n',
        'scripts/data/state.json': b'{}\n',
        'factories/my.factories': b'[]\n',
        'user-hooks/mine.so': b'\x7fELFuser',
        'user-hooks/readme.txt': b'skip\n',
    }
    for rel, data in files.items():
        path = config_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    hooks = tmp_path / 'system-hooks'
    hooks.mkdir()
    (hooks / 'force_rate.so').write_bytes(b'\x7fELFsys')
    (hooks / 'README').write_text('skip')

    with app.app_context():
        host = Host(name='up-host', provider='vultr', ip_address='10.0.0.9', ssh_user='ansible',
                    ssh_key_path='/keys/k', runtime=MINQLXTENDED, status=HostStatus.CONFIGURING)
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(id=1, name='i1', port=27960, hostname='hn', host_id=host.id,
                          qlx_plugins='balance', status=InstanceStatus.STOPPED,
                          zmq_rcon_port=28888, zmq_rcon_password='rp',
                          zmq_stats_port=29999, zmq_stats_password='sp')
        db.session.add(inst)
        db.session.add(HostRuntimeUpgradeOperation(id=OLD_OP, host_id=host.id, state='rolled_back'))
        db.session.add(HostRuntimeUpgradeOperation(id=OP, host_id=host.id, state='configuring'))
        db.session.commit()
        yield {'calls': calls, 'outcome': outcome, 'host_id': host.id, 'tmp': tmp_path,
               'inputs': {'config_dir': str(config_dir), 'system_hooks_dir': str(hooks)}}


def _configure(env, runtime=MINQLXTENDED, deps=VENV, **kwargs):
    return mod.configure_existing_instance(1, runtime, env['inputs'], deps,
                                           operation_id=OP, fencing_token=4, **kwargs)


def test_configure_runs_the_update_playbook_never_the_creation_path(env):
    result = _configure(env)
    assert result['ok'] is True and result['error'] is None
    [call] = env['calls']
    assert call['playbook'] == 'update_instance_runtime.yml'
    ev = call['extravars']
    assert ev['operation_id'] == OP and ev['fencing_token'] == 4
    assert ev['terminal_operation_ids'] == [OLD_OP]
    assert ev['instance_id'] == 1 and ev['port'] == 27960
    assert ev['runtime'] == MINQLXTENDED
    assert ev['runtime_artifacts'] == ['minqlxtended.x64.so', 'minqlxtended.zip',
                                       'run_server_x64_minqlxtended.sh']
    assert ev['launch_script'] == 'run_server_x64_minqlxtended.sh'
    assert ev['runtime_plugins_dirname'] == 'minqlxtended-plugins'
    assert ev['python_deps_path'] == VENV
    assert ev['restore_from_operation'] == ''
    assert '+set qlx_pluginsPath /home/ql/qlds-27960/minqlxtended-plugins' in ev['qlds_args']


@pytest.mark.parametrize('runtime', [MINQLX, MINQLXTENDED])
def test_runtime_artifacts_take_engine_and_launcher_from_runtime_paths(runtime):
    required, _optional = mod._runtime_artifacts(runtime)
    paths = runtime_paths(runtime)
    assert paths['engine_so'] in required
    assert paths['launch_script'] in required


def test_configure_stages_exactly_the_managed_files(env):
    _configure(env)
    [call] = env['calls']
    assert call['archive'] == [
        'baseq3/access.txt',
        'baseq3/cfgs/nested/extra.cfg',
        'baseq3/scripts/my.factories',
        'baseq3/server.cfg',
        'minqlxtended-plugins/balance.py',
        'minqlxtended-plugins/data/state.json',
        'minqlxtended-plugins/requirements.txt',
        'system-hooks/force_rate.so',
        'user-hooks/mine.so',
    ]
    assert call['archive_bytes']['baseq3/server.cfg'] == b'set sv_hostname "x"\n'
    assert not os.path.exists(call['extravars']['stage_archive'])  # cleaned up


def test_configure_persists_the_dependency_path_only_on_success(app, env):
    env['outcome']['ok'] = False
    env['outcome']['stderr'] = 'boom'
    result = _configure(env)
    assert result['ok'] is False and 'boom' in result['error']
    assert db.session.get(QLInstance, 1).python_deps_path is None
    env['outcome']['ok'] = True
    assert _configure(env)['ok'] is True
    assert db.session.get(QLInstance, 1).python_deps_path == VENV


def test_configure_fetches_the_inventory_into_the_operation_dir(app, env):
    _configure(env)
    path = env['calls'][0]['extravars']['local_manifest_path']
    assert path == os.path.join(str(env['tmp'] / 'upgrades'), str(env['host_id']), OP, 'remote', '1.json')
    assert os.path.isdir(os.path.dirname(path))


def test_rollback_is_an_inventory_restore_only(app, env):
    """No archive, no runtime artifacts, no re-rendered unit: the recorded
    originals come back exactly, so a rebuilt minqlx-shared cannot leak in."""
    host = db.session.get(Host, env['host_id'])
    host.runtime = MINQLX
    inst = db.session.get(QLInstance, 1)
    inst.python_deps_path = VENV
    db.session.commit()
    result = mod.configure_existing_instance(1, MINQLX, None, None, operation_id=OP,
                                             fencing_token=5, restore_from_operation=OP)
    assert result['ok'] is True, result['error']
    [call] = env['calls']
    assert call['playbook'] == 'update_instance_runtime.yml'
    assert call['extravars'] == {
        'operation_id': OP, 'fencing_token': 5, 'terminal_operation_ids': [OLD_OP],
        'instance_id': 1, 'port': 27960, 'restore_from_operation': OP,
    }
    assert 'archive' not in call
    assert db.session.get(QLInstance, 1).python_deps_path is None


def test_rollback_refuses_a_dependency_path(app, env):
    db.session.get(Host, env['host_id']).runtime = MINQLX
    db.session.commit()
    result = mod.configure_existing_instance(1, MINQLX, None, VENV, operation_id=OP,
                                             fencing_token=5, restore_from_operation=OP)
    assert result['ok'] is False and env['calls'] == []


def test_configure_refuses_a_runtime_the_host_is_not_on(env):
    result = _configure(env, runtime=MINQLX, deps=None)
    assert result['ok'] is False and 'runtime' in result['error']
    assert env['calls'] == []


@pytest.mark.parametrize('deps', ['/tmp/venv', f'/home/ql/runtime-deps/../x', 'relative'])
def test_configure_refuses_a_dependency_path_outside_runtime_deps(env, deps):
    result = _configure(env, deps=deps)
    assert result['ok'] is False and env['calls'] == []


def test_configure_refuses_a_minqlx_dependency_path(app, env):
    db.session.get(Host, env['host_id']).runtime = MINQLX
    db.session.commit()
    result = _configure(env, runtime=MINQLX, deps=VENV)
    assert result['ok'] is False and env['calls'] == []


@pytest.mark.parametrize('kwargs', [
    {'operation_id': 'nothex', 'fencing_token': 1},
    {'operation_id': OP, 'fencing_token': -1},
])
def test_configure_validates_operation_identity(env, kwargs):
    result = mod.configure_existing_instance(1, MINQLXTENDED, env['inputs'], VENV, **kwargs)
    assert result['ok'] is False and env['calls'] == []


def test_configure_never_raises(env, monkeypatch):
    monkeypatch.setattr(mod, '_build_stage_archive', lambda *a, **k: 1 / 0)
    result = _configure(env)
    assert result['ok'] is False and 'division' in result['error']


def test_missing_instance_is_an_error_result(env):
    result = mod.configure_existing_instance(999, MINQLXTENDED, env['inputs'], VENV,
                                             operation_id=OP, fencing_token=1)
    assert result['ok'] is False and 'not found' in result['error']


def _install_inputs(env):
    pool = env['tmp'] / 'inputs' / 'target_builtin_pool'
    pool.mkdir(parents=True)
    (pool / 'requirements.txt').write_text('redis>=5.1.0\n')
    return mod.install_inputs_from_materialized(str(env['tmp'] / 'inputs'), [1, 2])


def test_install_inputs_from_materialized_layout(env):
    inputs = _install_inputs(env)
    root = str(env['tmp'] / 'inputs')
    assert inputs['core_requirements'] == os.path.join(root, 'target_builtin_pool', 'requirements.txt')
    assert inputs['builtin_pool_dir'] == os.path.join(root, 'target_builtin_pool')
    assert inputs['operator_pool_dir'] is None
    assert inputs['instances'] == {
        1: {'requirements': os.path.join(root, 'instances', '1', 'scripts', 'requirements.txt')},
        2: {'requirements': None},
    }


def test_install_runs_the_minimal_installer_and_reports_dependency_paths(env):
    result = mod.install_runtime_on_host(env['host_id'], operation_id=OP, fencing_token=4,
                                         immutable_inputs=_install_inputs(env))
    assert result['ok'] is True
    [call] = env['calls']
    assert call['playbook'] == 'install_runtime.yml'
    ev = call['extravars']
    assert ev['operation_id'] == OP and ev['fencing_token'] == 4
    target = runtime_paths(MINQLXTENDED)
    assert ev['minqlxtended_git_repo'] == target['git_repo']
    assert ev['minqlxtended_git_version'] == target['git_version']
    assert ev['minqlxtended_shared_dir'] == target['shared_dir']
    assert ev['runtime_plugins_dirname'] == target['plugins_dirname']
    assert ev['terminal_operation_ids'] == [OLD_OP]
    assert ev['core_requirements_src'].endswith('target_builtin_pool/requirements.txt')
    assert ev['common_plugins_builtin_src'].endswith('target_builtin_pool')
    assert os.path.basename(ev['common_plugins_operator_src']).startswith('qlsm-empty-operator-pool-')
    assert ev['runtime_instances'] == [
        {'id': 1, 'requirements_src': ev['runtime_instances'][0]['requirements_src']},
        {'id': 2, 'requirements_src': ''},
    ]
    assert result['details']['dependency_paths'] == {
        1: f'/home/ql/runtime-deps/minqlxtended/{OP}/1',
        2: f'/home/ql/runtime-deps/minqlxtended/{OP}/2',
    }


def test_install_failure_is_reported_not_raised(env):
    env['outcome'].update(ok=False, stdout='TASK [x] fatal: pip failed', stderr='')
    result = mod.install_runtime_on_host(env['host_id'], operation_id=OP, fencing_token=4,
                                         immutable_inputs=_install_inputs(env))
    assert result['ok'] is False and 'pip failed' in result['error']
    assert result['details']['dependency_paths'] == {}


def test_install_with_zero_instances_builds_only(env):
    inputs = mod.install_inputs_from_materialized(str(env['tmp'] / 'inputs'), [])
    result = mod.install_runtime_on_host(env['host_id'], operation_id=OP, fencing_token=1,
                                         immutable_inputs=inputs)
    assert result['ok'] is True
    assert env['calls'][0]['extravars']['runtime_instances'] == []


def test_finalize_runs_the_finalize_playbook(env):
    result = mod.finalize_runtime_operation(env['host_id'], operation_id=OP, fencing_token=4)
    assert result['ok'] is True
    assert env['calls'][0]['playbook'] == 'finalize_runtime_operation.yml'
    assert env['calls'][0]['extravars'] == {'operation_id': OP, 'fencing_token': 4}


def test_remote_inventory_dir_does_not_break_snapshot_verification(app, env):
    """The fetched manifests live under <snapshot>/remote/, which Task 3's
    published-snapshot verification must ignore."""
    from ui.runtime_upgrade_snapshot import SNAPSHOT_SCHEMA_VERSION, _verify_published, snapshot_dir

    path = snapshot_dir(env['host_id'], OP)
    os.makedirs(os.path.join(path, 'remote'))
    with open(os.path.join(path, 'remote', '1.json'), 'w') as handle:
        json.dump({'entries': {}}, handle)
    with open(os.path.join(path, 'manifest.json'), 'w') as handle:
        json.dump({'schema': SNAPSHOT_SCHEMA_VERSION, 'complete': True, 'operation_id': OP,
                   'host_id': env['host_id'], 'trees': {}, 'instances': []}, handle)
    _verify_published(path, OP, env['host_id'])


# --- fix round 1 ---------------------------------------------------------------

def test_install_never_falls_back_to_the_live_operator_pool(env):
    """No captured operator pool -> an empty staged dir, never the default
    (live data/shared-plugins/<runtime>)."""
    seen = {}

    def runner(host, playbook_name, extravars=None, capture_output=False):
        src = extravars.get('common_plugins_operator_src')
        seen['src'] = src
        seen['exists_and_empty'] = bool(src) and os.path.isdir(src) and os.listdir(src) == []
        return True, 'ok', ''

    mod_runner = mod._run_host_ansible_playbook
    mod._run_host_ansible_playbook = runner
    try:
        inputs = _install_inputs(env)
        assert inputs['operator_pool_dir'] is None
        result = mod.install_runtime_on_host(env['host_id'], operation_id=OP, fencing_token=1,
                                             immutable_inputs=inputs)
    finally:
        mod._run_host_ansible_playbook = mod_runner
    assert result['ok'] is True
    assert seen['exists_and_empty'] is True
    assert 'shared-plugins' not in seen['src']
    assert not os.path.exists(seen['src'])  # cleaned up afterwards


def test_entry_points_handle_the_runners_two_value_early_return(app, env, monkeypatch):
    """_run_host_ansible_playbook returns (None, error) when SSH details are
    missing; the entry points must report that error, not raise."""
    from ui.task_logic import ansible_runner
    monkeypatch.setattr(mod, '_run_host_ansible_playbook', ansible_runner._run_host_ansible_playbook)
    host = db.session.get(Host, env['host_id'])
    host.ssh_key_path = None
    db.session.commit()
    configure = _configure(env)
    assert configure['ok'] is False and 'Host details missing' in configure['error']
    install = mod.install_runtime_on_host(env['host_id'], operation_id=OP, fencing_token=1,
                                          immutable_inputs=_install_inputs(env))
    assert install['ok'] is False and 'Host details missing' in install['error']
    final = mod.finalize_runtime_operation(env['host_id'], operation_id=OP, fencing_token=1)
    assert final['ok'] is False and 'Host details missing' in final['error']


# --- Local review #2: DB writes under an operation go through its fenced commit ----

def _stale_execution():
    """An Execution for OP whose token a takeover has since bumped."""
    from ui.task_logic.host_runtime_upgrade_state import Execution, claim_operation

    op = db.session.get(HostRuntimeUpgradeOperation, OP)
    op.fencing_token = 4
    db.session.commit()
    stale = Execution(OP, 4, 'job-1', None)
    assert claim_operation(OP, 'job-2') == 5
    return stale


def test_configure_db_write_is_fenced_after_a_takeover(app, env):
    from ui.task_logic.host_runtime_upgrade_state import StaleExecution

    stale = _stale_execution()
    with pytest.raises(StaleExecution):
        _configure(env, commit=stale.commit)
    db.session.expire_all()
    assert db.session.get(QLInstance, 1).python_deps_path is None


def test_rollback_restore_db_write_is_fenced_after_a_takeover(app, env):
    from ui.task_logic.host_runtime_upgrade_state import StaleExecution

    db.session.get(Host, env['host_id']).runtime = MINQLX
    db.session.get(QLInstance, 1).python_deps_path = VENV
    db.session.commit()
    stale = _stale_execution()
    with pytest.raises(StaleExecution):
        mod.configure_existing_instance(1, MINQLX, None, None, operation_id=OP, fencing_token=4,
                                        restore_from_operation=OP, commit=stale.commit)
    db.session.expire_all()
    assert db.session.get(QLInstance, 1).python_deps_path == VENV


def test_configure_without_an_operation_commit_still_commits(app, env):
    assert _configure(env)['ok'] is True
    db.session.expire_all()
    assert db.session.get(QLInstance, 1).python_deps_path == VENV
