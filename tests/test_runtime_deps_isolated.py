"""Ruling R11: once a host is upgraded (Host.runtime_deps_isolated, set by the
orchestrator), instances created or redeployed on it get their own venv at
/home/ql/runtime-deps/minqlxtended/instances/<id>/ and never use system pip.
With the flag off everything is exactly as before."""
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest
import yaml

from ui import create_app, db
from ui.models import Host, InstanceStatus, QLInstance
from ui.runtime import (
    MINQLX,
    MINQLXTENDED,
    instance_runtime_extravars,
    isolated_instance_deps_path,
    runtime_extravars,
)
from ui.task_logic import ansible_instance_mgmt as mgmt

OP_VENV = '/home/ql/runtime-deps/minqlxtended/' + 'a' * 32 + '/1'


@pytest.fixture
def make_instance(app, tmp_path, monkeypatch):
    monkeypatch.setattr(mgmt, 'CONFIGS_BASE', str(tmp_path / 'configs'))

    def make(isolated, runtime=MINQLXTENDED, deps=None, requirements=None):
        host = Host(name=f'iso-{isolated}-{runtime}-{deps is None}', provider='vultr',
                    ip_address='10.0.0.1', runtime=runtime, runtime_deps_isolated=isolated)
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(name=f'i-{host.id}', port=27960 + host.id, hostname='hn', host_id=host.id,
                          qlx_plugins='', status=InstanceStatus.RUNNING, python_deps_path=deps,
                          zmq_rcon_port=28888, zmq_rcon_password='x',
                          zmq_stats_port=29999, zmq_stats_password='y')
        db.session.add(inst)
        db.session.commit()
        if requirements is not None:
            req = tmp_path / 'configs' / host.name / str(inst.id) / 'scripts' / 'requirements.txt'
            req.parent.mkdir(parents=True)
            req.write_text(requirements)
        return inst
    with app.app_context():
        yield make


def test_flag_defaults_to_false(make_instance):
    host = Host(name='plain', provider='vultr')
    db.session.add(host)
    db.session.commit()
    assert db.session.get(Host, host.id).runtime_deps_isolated is False


def test_flag_off_leaves_extravars_unchanged(make_instance):
    inst = make_instance(False)
    assert instance_runtime_extravars(inst) == runtime_extravars(inst.host)
    assert inst.python_deps_path is None


def test_flag_on_minqlx_host_is_ignored(make_instance):
    inst = make_instance(True, runtime=MINQLX)
    assert instance_runtime_extravars(inst) == runtime_extravars(inst.host)


def test_flag_on_gives_a_new_instance_its_own_venv(make_instance):
    inst = make_instance(True, requirements='six\n')
    extravars = instance_runtime_extravars(inst)
    path = isolated_instance_deps_path(inst.id)
    assert path == f'/home/ql/runtime-deps/minqlxtended/instances/{inst.id}'
    assert inst.python_deps_path == path
    assert extravars['python_deps_path'] == path
    assert extravars['python_deps_ensure'] is True
    core = extravars['python_deps_core_requirements_src']
    assert os.path.isabs(core) and core.endswith('ql-assets/data/minqlxtended-plugins/requirements.txt')
    assert os.path.isfile(core)
    # Instance requirements come from the copy synced to the host, not the controller.
    assert 'python_deps_requirements_src' not in extravars


def test_flag_on_keeps_an_upgraded_instances_operation_venv(make_instance):
    inst = make_instance(True, deps=OP_VENV)
    extravars = instance_runtime_extravars(inst)
    assert extravars['python_deps_path'] == OP_VENV
    assert extravars['python_deps_ensure'] is True
    assert 'python_deps_requirements_src' not in extravars


def _capture(monkeypatch):
    captured = {}

    def fake_run(instance, playbook, extravars=None):
        captured['playbook'] = playbook
        captured['extravars'] = extravars
        return SimpleNamespace(rc=0, status='successful', stdout=lambda: ''), None

    monkeypatch.setattr(mgmt, '_run_ansible_playbook', fake_run)
    monkeypatch.setattr(mgmt, '_prepare_instance_zmq', lambda inst: None)
    monkeypatch.setattr(mgmt, 'ensure_instance_cpu_affinity', lambda inst: None)
    monkeypatch.setattr(mgmt, 'with_self_host_network_extravars', lambda inst, e: e)
    monkeypatch.setattr(mgmt, 'get_current_job', lambda: SimpleNamespace(id='job'))
    return captured


@pytest.mark.parametrize('isolated', [False, True])
def test_deploy_on_an_isolated_host_builds_and_persists_a_venv(make_instance, monkeypatch, isolated):
    inst = make_instance(isolated)
    captured = _capture(monkeypatch)
    try:
        mgmt.deploy_instance_logic(inst.id)
    except Exception:
        pass
    assert captured['playbook'] == 'add_qlds_instance.yml'
    stored = db.session.get(QLInstance, inst.id).python_deps_path
    if isolated:
        assert captured['extravars']['python_deps_ensure'] is True
        assert captured['extravars']['python_deps_path'] == isolated_instance_deps_path(inst.id)
        assert stored == isolated_instance_deps_path(inst.id)
    else:
        for key in ('python_deps_path', 'python_deps_ensure', 'python_deps_core_requirements_src'):
            assert key not in captured['extravars']
        assert stored is None


@pytest.mark.parametrize('isolated', [False, True])
def test_standalone_setup_skips_global_pip_only_on_isolated_hosts(app, isolated):
    from ui.task_logic.standalone_host_setup import _setup_playbook_extra_vars
    with app.app_context():
        host = Host(name=f'sa-{isolated}', provider='standalone', ssh_port=22, is_standalone=True,
                    runtime=MINQLXTENDED, runtime_deps_isolated=isolated)
        db.session.add(host)
        db.session.commit()
        extra = _setup_playbook_extra_vars(host)
    if isolated:
        assert extra['skip_pip_install'] is True
    else:
        assert 'skip_pip_install' not in extra


@pytest.mark.parametrize('isolated', [False, True])
def test_cloud_setup_skips_global_pip_only_on_isolated_hosts(app, monkeypatch, isolated):
    import ui.task_logic.ansible_host_setup as mod
    from ui.models import HostStatus

    with app.app_context():
        host = Host(name=f'cloud-{isolated}', provider='vultr', ip_address='10.0.0.5',
                    ssh_key_path='/key', ssh_user='ansible', runtime=MINQLXTENDED,
                    runtime_deps_isolated=isolated, status=HostStatus.PROVISIONED_PENDING_SETUP)
        db.session.add(host)
        db.session.commit()
        host_id = host.id
    captured = {}

    class FakeProcess:
        returncode = 0
        stdout = stderr = None

    def fake_popen(args, **kwargs):
        captured['args'] = args
        return FakeProcess()

    monkeypatch.setattr(mod.subprocess, 'Popen', fake_popen)
    monkeypatch.setattr(mod.subprocess, 'run',
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout='', stderr=''))
    monkeypatch.setattr(mod.os.path, 'exists', lambda path: True)
    monkeypatch.setattr('ui.task_logic.ansible_runner._stream_output', lambda p: ('', ''))
    monkeypatch.setattr(mod, 'get_current_job', lambda: SimpleNamespace(id='job'))
    with app.app_context():
        try:
            mod.setup_host_ansible_logic(host_id)
        except Exception:
            pass
    payloads = [json.loads(a) for a in captured['args'] if a.startswith('{')]
    merged = {k: v for p in payloads for k, v in p.items()}
    assert merged['runtime'] == MINQLXTENDED
    if isolated:
        assert merged['skip_pip_install'] is True
    else:
        assert 'skip_pip_install' not in merged


def _tasks(path):
    with open(path) as handle:
        return yaml.safe_load(handle)


def test_dependency_install_ensures_the_venv_before_any_pip():
    tasks = _tasks('ansible/playbooks/tasks/install_minqlx_deps.yml')
    ensure = next(t for t in tasks if t.get('ansible.builtin.include_tasks'))
    assert ensure['ansible.builtin.include_tasks'] == 'runtime_python_deps.yml'
    installs = [t for t in tasks if t.get('ansible.builtin.pip') or t.get('ansible.builtin.shell')]
    assert installs and all(tasks.index(ensure) < tasks.index(t) for t in installs)
    assert ensure['when'] == "python_deps_ensure | default(false) | bool"
    assert ensure['vars']['runtime_deps_dir'] == '{{ python_deps_path | dirname }}'
    for task in tasks:
        if task.get('ansible.builtin.pip') or 'pip3' in str(task.get('command', '')):
            assert "python_deps_path | default('') | length == 0" in str(task.get('when', ''))


def test_runtime_python_deps_accepts_an_explicit_directory():
    tasks = _tasks('ansible/playbooks/tasks/runtime_python_deps.yml')
    resolve = tasks[0]['ansible.builtin.set_fact']['runtime_deps_op_dir']
    assert 'runtime_deps_dir if runtime_deps_dir is defined' in resolve


def test_migration_adds_and_removes_the_flag(tmp_path, preserve_logging_config):
    from flask_migrate import downgrade, stamp, upgrade

    db_path = tmp_path / 'migrated.db'
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
                      'SQLALCHEMY_TRACK_MODIFICATIONS': False, 'RCON_ENABLED': False})
    migrations = os.path.join(os.path.dirname(__file__), '..', 'migrations')

    def columns():
        conn = sqlite3.connect(db_path)
        try:
            return {row[1] for row in conn.execute('PRAGMA table_info(host)')}
        finally:
            conn.close()

    try:
        with app.app_context():
            db.create_all()
            db.session.execute(db.text('ALTER TABLE host DROP COLUMN runtime_deps_isolated'))
            db.session.commit()
            stamp(directory=migrations, revision='20261104130000')
            upgrade(directory=migrations, revision='20261104140000')
            assert 'runtime_deps_isolated' in columns()
            downgrade(directory=migrations, revision='20261104130000')
            assert 'runtime_deps_isolated' not in columns()
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


# --- Local review #1/#4: soft-fail outside the installer, one pip run --------------

_SOFT_FAIL = "{{ runtime_deps_soft_fail | default(false) | bool }}"


def _named(tasks, fragment):
    matches = [t for t in tasks if fragment in t.get('name', '')]
    assert len(matches) == 1, (fragment, [t.get('name') for t in tasks])
    return matches[0]


def test_venv_pip_failures_only_warn_when_soft_fail_is_set():
    tasks = _tasks('ansible/playbooks/tasks/runtime_python_deps.yml')
    install = _named(tasks, 'Install core and instance requirements')
    check = _named(tasks, 'Verify each venv')
    for task in (install, check):
        assert task.get('ignore_errors') == _SOFT_FAIL, task['name']
        assert task.get('register'), task['name']
    warns = [t for t in tasks if 'QLSM_PIP_WARN:' in str(t.get('ansible.builtin.debug', ''))]
    assert len(warns) == 2
    for warn in warns:
        assert 'runtime_deps_soft_fail' in str(warn.get('when', ''))
    # Creating the venv (and the ABI checks) stays hard in every mode.
    for name in ('Create each instance', 'Confirm each venv', 'Require the venv interpreter'):
        assert 'ignore_errors' not in _named(tasks, name), name


def test_installer_keeps_venv_pip_failures_fatal():
    with open('ansible/playbooks/install_runtime.yml') as handle:
        text = handle.read()
    assert 'runtime_deps_soft_fail' not in text


def test_instance_dependency_step_soft_fails_and_installs_once():
    tasks = _tasks('ansible/playbooks/tasks/install_minqlx_deps.yml')
    ensure = _named(tasks, "Ensure the instance's isolated dependency venv")
    assert ensure['vars']['runtime_deps_soft_fail'] is True
    stat = _named(tasks, 'Check if requirements.txt exists')
    # The remote instance requirements (what the old second step installed)
    # go into the ensure run, so an operation venv keeps getting them.
    item = ensure['vars']['runtime_instances'][0]
    assert item['requirements_src'] == ''
    assert 'minqlx_req_stat_result.stat.exists' in item['remote_requirements']
    assert "runtime_plugins_dirname ~ '/requirements.txt'" in item['remote_requirements']
    assert tasks.index(stat) < tasks.index(ensure)
    for task in tasks[:tasks.index(ensure)]:
        assert 'pip' not in str(task.get('ansible.builtin.pip', '')) and 'install' not in task.get('name', '').lower()
    second = _named(tasks, "Install plugin Python deps into the instance's isolated venv")
    assert "not (python_deps_ensure | default(false) | bool)" in str(second['when'])


def test_remote_requirements_join_the_single_pip_run():
    tasks = _tasks('ansible/playbooks/tasks/runtime_python_deps.yml')
    install = _named(tasks, 'Install core and instance requirements')
    assert 'item.remote_requirements' in install['ansible.builtin.command']['argv']
    assert 'item.remote_requirements' in str(install['when'])


# --- Local review #5: a reused instance id never inherits a deleted instance's venv ---

def test_new_instance_venv_carries_an_ownership_marker(make_instance):
    inst = make_instance(True)
    extravars = instance_runtime_extravars(inst)
    assert extravars['python_deps_owner'] == f'{inst.id}:{inst.created_at.isoformat()}'


@pytest.mark.parametrize('isolated,deps', [(False, None), (True, OP_VENV)])
def test_no_ownership_marker_outside_new_instance_venvs(make_instance, isolated, deps):
    assert 'python_deps_owner' not in instance_runtime_extravars(make_instance(isolated, deps=deps))


def _claim_task():
    tasks = _tasks('ansible/playbooks/tasks/install_minqlx_deps.yml')
    claim = _named(tasks, 'Claim the instance')
    ensure = _named(tasks, "Ensure the instance's isolated dependency venv")
    assert tasks.index(claim) < tasks.index(ensure)
    assert claim['become_user'] == 'ql'
    assert 'python_deps_owner' in str(claim['when'])
    return claim


def _run_claim(tmp_path, venv, owner):
    import subprocess
    import sys
    claim = _claim_task()
    script = claim['vars']['python_deps_claim_py']
    out = subprocess.run([sys.executable, '-c', script, str(venv), owner],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_claim_rebuilds_a_venv_owned_by_another_instance(tmp_path):
    venv = tmp_path / 'instances' / '7'
    (venv / 'lib').mkdir(parents=True)
    (venv / 'lib' / 'old_pkg.py').write_text('x')
    (venv / '.qlsm-owner').write_text('7:2026-01-01T00:00:00')
    assert _run_claim(tmp_path, venv, '7:2026-11-04T10:00:00') == 'rebuilt'
    assert sorted(p.name for p in venv.iterdir()) == ['.qlsm-owner']
    assert (venv / '.qlsm-owner').read_text() == '7:2026-11-04T10:00:00'


def test_claim_keeps_its_own_venv(tmp_path):
    venv = tmp_path / 'instances' / '7'
    (venv / 'lib').mkdir(parents=True)
    (venv / '.qlsm-owner').write_text('7:a')
    assert _run_claim(tmp_path, venv, '7:a') == 'kept'
    assert (venv / 'lib').is_dir()


def test_claim_creates_a_missing_venv_dir_with_its_marker(tmp_path):
    venv = tmp_path / 'instances' / '7'
    assert _run_claim(tmp_path, venv, '7:a') == 'claimed'
    assert (venv / '.qlsm-owner').read_text() == '7:a'


def test_claim_replaces_an_unmarked_venv_and_never_follows_a_symlink(tmp_path):
    target = tmp_path / 'elsewhere'
    target.mkdir()
    (target / 'keep.txt').write_text('x')
    venv = tmp_path / 'instances' / '7'
    venv.parent.mkdir()
    venv.symlink_to(target)
    assert _run_claim(tmp_path, venv, '7:a') == 'rebuilt'
    assert (target / 'keep.txt').exists()
    assert venv.is_dir() and not venv.is_symlink()


def test_claim_validates_the_venv_path():
    claim = _claim_task()
    tasks = _tasks('ansible/playbooks/tasks/install_minqlx_deps.yml')
    check = tasks[tasks.index(claim) - 1]
    assert 'ansible.builtin.assert' in check
    text = str(check['ansible.builtin.assert']['that'])
    assert '^/home/ql/runtime-deps/minqlxtended/instances/[0-9]+$' in text


def test_instance_delete_removes_its_new_instance_venv_as_ql():
    tasks = _tasks('ansible/playbooks/manage_qlds_service.yml')[0]['tasks']
    remove = _named(tasks, "Remove the instance's isolated dependency venv")
    assert remove['become_user'] == 'ql'
    assert remove['ansible.builtin.file'] == {
        'path': '/home/ql/runtime-deps/minqlxtended/instances/{{ id | int }}', 'state': 'absent'}
    assert "service_action == 'delete'" in str(remove['when'])


# --- Local review #6: the core requirements path does not depend on the cwd ---

def test_core_requirements_path_is_independent_of_the_cwd(make_instance, monkeypatch, tmp_path):
    inst = make_instance(True)
    monkeypatch.chdir(tmp_path)
    core = instance_runtime_extravars(inst)['python_deps_core_requirements_src']
    assert os.path.isfile(core), core
    assert core.endswith('ql-assets/data/minqlxtended-plugins/requirements.txt')
    assert not core.startswith(str(tmp_path))
