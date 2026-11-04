"""Executable runtime-upgrade check against a disposable Docker container.

Opt-in: QLSM_RUNTIME_INTEGRATION=1 (skipped otherwise, so CI is unaffected).
Needs Docker and ansible-core in the worktree venv. The only Ansible target is
the container this module starts; the inventory is generated here and points
at nothing else, and the container is removed afterwards.

It drives the real Python entry points (ui/task_logic/instance_runtime_update.py)
and the real playbooks. The stub minqlxtended repo (tests/fixtures/runtime_upgrade)
gets the real QLSM patch applied by the real build tasks; its launcher runs the
patched `loader` under the container's python3.12 in place of the x86_64
engine, which cannot run here. See the task report for what that does not prove.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('QLSM_RUNTIME_INTEGRATION') != '1',
                                reason='set QLSM_RUNTIME_INTEGRATION=1 to run against a disposable container')

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 'runtime_upgrade')
IMAGE = 'qlsm-runtime-upgrade-fixture:1'
HOST_NAME = 'qlsm-fixture'
ANSIBLE_BIN = os.path.join(os.path.dirname(sys.executable), 'ansible-playbook')
PORT = 27960
QLDS = f'/home/ql/qlds-{PORT}'

SETUP_OP = uuid.uuid4().hex
OP = uuid.uuid4().hex
CONFLICT_OP = uuid.uuid4().hex
APT_OP = uuid.uuid4().hex


def _sh(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


class Target:
    def __init__(self, name, workdir):
        self.name = name
        self.workdir = workdir

    def run(self, script, user='root', env=None, check=True):
        cmd = ['docker', 'exec', '-u', user]
        for key, value in (env or {}).items():
            cmd += ['-e', f'{key}={value}']
        result = _sh(cmd + [self.name, 'bash', '-c', script])
        if check and result.returncode != 0:
            raise AssertionError(f'{script!r} failed: {result.stdout}\n{result.stderr}')
        return result

    def out(self, script, **kwargs):
        return self.run(script, **kwargs).stdout.strip()

    def sha(self, path):
        return self.out(f'sha256sum {path} | cut -d" " -f1')


@pytest.fixture(scope='module')
def target(tmp_path_factory):
    if shutil.which('docker') is None or not os.path.exists(ANSIBLE_BIN):
        pytest.skip('docker and the venv ansible-playbook are required')
    workdir = tmp_path_factory.mktemp('runtime-upgrade-fixture')
    build = _sh(['docker', 'build', '-q', '-t', IMAGE, FIXTURE])
    assert build.returncode == 0, build.stderr
    name = f'qlsm-runtime-fixture-{uuid.uuid4().hex[:8]}'
    started = _sh(['docker', 'run', '-d', '--name', name, '--privileged', '--cgroupns=host',
                   '-v', '/sys/fs/cgroup:/sys/fs/cgroup:rw', '--tmpfs', '/run', '--tmpfs', '/run/lock',
                   '-p', '127.0.0.1::22', IMAGE])
    assert started.returncode == 0, started.stderr
    try:
        key = workdir / 'id_ed25519'
        assert _sh(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)]).returncode == 0
        tgt = Target(name, workdir)
        for _ in range(60):
            if tgt.run('systemctl is-active ssh', check=False).stdout.strip() == 'active':
                break
            time.sleep(1)
        _sh(['docker', 'cp', f'{key}.pub', f'{name}:/home/ansible/.ssh/authorized_keys'])
        tgt.run('chown -R ansible:ansible /home/ansible/.ssh && chmod 600 /home/ansible/.ssh/authorized_keys')
        port = _sh(['docker', 'port', name, '22']).stdout.strip().splitlines()[0].rsplit(':', 1)[1]
        inventory = workdir / 'inventory.ini'
        inventory.write_text(
            f'{HOST_NAME} ansible_host=127.0.0.1 ansible_port={port} ansible_user=ansible '
            f"ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'\n")
        cfg = workdir / 'ansible.cfg'
        cfg.write_text('[defaults]\nhost_key_checking = False\ninventory = %s\n' % inventory)
        tgt.key, tgt.inventory, tgt.cfg = str(key), str(inventory), str(cfg)
        _seed_target(tgt)
        yield tgt
    finally:
        _sh(['docker', 'rm', '-f', name])


def _seed_target(tgt):
    """An existing minqlx instance (stopped), its shared build, Redis data and
    a stub minqlxtended git repo the build tasks can clone."""
    tgt.run(f'''set -e
mkdir -p /home/ql/minqlx-shared/minqlx {QLDS}/baseq3/maps {QLDS}/minqlx-plugins /var/lib/redis
printf 'minqlx engine\\n' > /home/ql/minqlx-shared/minqlx.x64.so
printf '#!/bin/bash\\nexec sleep infinity\\n' > /home/ql/minqlx-shared/run_server_x64_minqlx.sh
chmod 755 /home/ql/minqlx-shared/*.so /home/ql/minqlx-shared/*.sh
printf 'MINQLX = 1\\n' > /home/ql/minqlx-shared/minqlx/__init__.py
cp -a /home/ql/minqlx-shared/. {QLDS}/
printf 'base q3 map\\n' > {QLDS}/baseq3/maps/sentinel.bsp
printf 'set sv_hostname "old"\\n' > {QLDS}/baseq3/server.cfg
printf 'import minqlx\\n' > {QLDS}/minqlx-plugins/balance.py
printf '{{"plugin": "owned"}}\\n' > {QLDS}/minqlx-plugins/plugin_data.json
mkdir -p /home/ql/assets/common/minqlx-plugins
printf 'redis dump\\n' > /var/lib/redis/dump.rdb
chown -R ql:ql /home/ql
''')
    tgt.run('rm -rf /srv/stub-minqlxtended && mkdir -p /srv')
    _sh(['docker', 'cp', os.path.join(FIXTURE, 'stub-minqlxtended'), f'{tgt.name}:/srv/stub-minqlxtended'])
    tgt.run('chown -R root:root /srv/stub-minqlxtended && cd /srv/stub-minqlxtended && git init -q && '
            'git add -A && git -c user.email=t@t -c user.name=t commit -q -m stub && '
            'chmod -R a+rX /srv/stub-minqlxtended && '
            'git config --system --add safe.directory "*"')
    tgt.stub_commit = tgt.out('git -C /srv/stub-minqlxtended rev-parse HEAD')


@pytest.fixture(scope='module')
def ctx(target, tmp_path_factory, monkeypatch_module):
    """App + DB rows for the container host, with the playbook runner pointed
    at the fixture inventory only."""
    from ui import create_app, db
    from ui.models import Host, HostStatus, InstanceStatus, QLInstance
    from ui.task_logic import ansible_runner

    work = tmp_path_factory.mktemp('runtime-upgrade-app')
    app = create_app({'TESTING': True, 'SECRET_KEY': 'x', 'JWT_SECRET_KEY': 'x',
                      'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'RCON_ENABLED': False,
                      'RUNTIME_UPGRADES_DIR': str(work / 'upgrades'), 'SERVER_NAME': 'test.server'})
    real_inventory = os.path.abspath('ansible/inventory/')

    class _Subprocess:
        def __getattr__(self, name):
            return getattr(subprocess, name)

        @staticmethod
        def Popen(cmd, **kwargs):
            assert cmd[0] == 'ansible-playbook'
            index = cmd.index('-i')
            assert cmd[index + 1] == real_inventory and cmd[cmd.index('-l') + 1] == HOST_NAME
            cmd = [ANSIBLE_BIN] + cmd[1:index + 1] + [target.inventory] + cmd[index + 2:]
            env = dict(kwargs.pop('env', None) or os.environ)
            env['ANSIBLE_CONFIG'] = target.cfg
            env['PATH'] = os.path.dirname(ANSIBLE_BIN) + os.pathsep + env.get('PATH', '')
            target.last_cmd = cmd
            return subprocess.Popen(cmd, env=env, **kwargs)

    monkeypatch_module.setattr(ansible_runner, 'subprocess', _Subprocess())
    with app.app_context():
        db.create_all()
        host = Host(name=HOST_NAME, provider='standalone', ip_address='127.0.0.1', ssh_user='ansible',
                    ssh_key_path=target.key, runtime='minqlx', status=HostStatus.CONFIGURING)
        db.session.add(host)
        db.session.flush()
        db.session.add(QLInstance(id=1, name='fixture-1', port=PORT, hostname='fx', host_id=host.id,
                                  qlx_plugins='balance', status=InstanceStatus.STOPPED,
                                  zmq_rcon_port=28888, zmq_rcon_password='rp',
                                  zmq_stats_port=29999, zmq_stats_password='sp'))
        db.session.commit()
        yield {'app': app, 'host_id': host.id, 'work': work}
        db.session.remove()


@pytest.fixture(scope='module')
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def _write_tree(root, files):
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write(text)


def _inputs(work, name, instance_requirements):
    """A materialize_upgrade_inputs()-shaped directory."""
    root = str(work / name)
    _write_tree(root, {
        'target_builtin_pool/requirements.txt': 'redis>=5.1.0\n',
        'target_builtin_pool/serverchecker.py': 'import minqlxtended\n',
        'instances/1/server.cfg': 'set sv_hostname "converted"\n',
        'instances/1/scripts/balance.py': 'import minqlxtended  # converted\n',
        'instances/1/scripts/requirements.txt': instance_requirements,
        'instances/1/factories/ffa.factories': '[]\n',
    })
    return root


def _minqlx_config(work):
    root = str(work / 'minqlx-config')
    _write_tree(root, {'server.cfg': 'set sv_hostname "old"\n', 'scripts/balance.py': 'import minqlx\n'})
    return root


def _global_python_state(tgt):
    return {
        'pip': tgt.out('python3 -m pip list --format=freeze --disable-pip-version-check 2>/dev/null'),
        'dist': tgt.out('ls -la /usr/local/lib/python3.12/dist-packages /usr/lib/python3/dist-packages | sha256sum'),
        'redis': tgt.out("python3 -c 'import redis; print(redis.__version__, redis.__file__)'", user='ql'),
        'dpkg': tgt.out("dpkg-query -W -f='${db:Status-Abbrev}|${Package}|${Version}\\n' | grep '^ii' | sha256sum"),
    }


def _sentinels(tgt):
    return {path: tgt.sha(path) for path in (
        f'{QLDS}/baseq3/maps/sentinel.bsp', f'{QLDS}/minqlx-plugins/plugin_data.json',
        '/var/lib/redis/dump.rdb', f'{QLDS}/minqlx.x64.so', f'{QLDS}/minqlx/__init__.py',
        '/home/ql/minqlx-shared/minqlx.x64.so')}


def _service_state(tgt):
    return tgt.run(f'systemctl is-active qlds@{PORT}', check=False).stdout.strip()


def _set_runtime(ctx, runtime):
    from ui import db
    from ui.models import Host
    db.session.get(Host, ctx['host_id']).runtime = runtime
    db.session.commit()


def test_upgrade_and_rollback_of_an_existing_stopped_instance(target, ctx, tmp_path):
    from ui import db
    from ui.models import QLInstance
    from ui.task_logic import instance_runtime_update as iru

    tgt = target
    build_vars = {'minqlxtended_git_repo': 'file:///srv/stub-minqlxtended',
                  'minqlxtended_git_version': tgt.stub_commit}
    real_runner = iru._run_host_ansible_playbook

    def runner(host, playbook, extravars=None, capture_output=False):
        merged = dict(extravars or {})
        if playbook == 'install_runtime.yml':
            merged.update(build_vars)
        return real_runner(host, playbook, extravars=merged, capture_output=capture_output)

    iru._run_host_ansible_playbook = runner
    try:
        # --- baseline: configure the minqlx instance through the same path, finalize
        _set_runtime(ctx, 'minqlx')
        result = iru.configure_existing_instance(1, 'minqlx', {'config_dir': _minqlx_config(ctx['work'])},
                                                 None, operation_id=SETUP_OP, fencing_token=1)
        assert result['ok'], result['error']
        assert iru.finalize_runtime_operation(ctx['host_id'], operation_id=SETUP_OP, fencing_token=1)['ok']
        assert _service_state(tgt) == 'inactive'
        unit_before = tgt.out(f'cat /etc/systemd/system/qlds@{PORT}.service')
        assert 'QLSM_PYTHON_DEPS' not in unit_before
        python_before = _global_python_state(tgt)
        assert python_before['redis'].startswith('2.')
        sentinels = _sentinels(tgt)
        cfg_before = tgt.sha(f'{QLDS}/baseq3/server.cfg')

        # --- install minqlxtended (isolated venv: core redis>=5.1 + instance six)
        inputs = _inputs(ctx['work'], 'inputs', 'six\n')
        install = iru.install_runtime_on_host(
            ctx['host_id'], operation_id=OP, fencing_token=1,
            immutable_inputs=iru.install_inputs_from_materialized(inputs, [1]))
        assert install['ok'], install['error']
        venv = install['details']['dependency_paths'][1]
        venv_redis = tgt.out(f"{venv}/bin/python -c 'import redis, six; print(redis.__version__)'", user='ql')
        assert int(venv_redis.split('.')[0]) >= 5
        assert tgt.out(f"{venv}/bin/python -c 'import sys; print(sys.flags.no_site, sys.prefix)'",
                       user='ql').endswith(venv)
        assert tgt.out(f'stat -c %U {venv} /home/ql/runtime-deps').split() == ['ql', 'ql']
        assert _global_python_state(tgt) == python_before
        assert _sentinels(tgt) == sentinels  # minqlx shared dir untouched
        assert 'QLSM_PYTHON_DEPS' in tgt.out('cat /home/ql/minqlxtended-shared/run_server_x64_minqlxtended.sh')
        assert tgt.out('stat -c "%U %a" /var/lib/qlsm/runtime-ops') == 'root 700'

        # --- configure the existing instance for minqlxtended, without starting it
        _set_runtime(ctx, 'minqlxtended')
        result = iru.configure_existing_instance(
            1, 'minqlxtended', {'config_dir': os.path.join(inputs, 'instances', '1')}, venv,
            operation_id=OP, fencing_token=1)
        assert result['ok'], result['error']
        assert db.session.get(QLInstance, 1).python_deps_path == venv
        unit = tgt.out(f'cat /etc/systemd/system/qlds@{PORT}.service')
        assert f'Environment=QLSM_PYTHON_DEPS={venv}' in unit
        assert 'ExecStart=/home/ql/qlds-%i/run_server_x64_minqlxtended.sh' in unit
        assert tgt.out(f'cat {QLDS}/baseq3/server.cfg') == 'set sv_hostname "converted"'
        assert tgt.out(f'ls {QLDS}/minqlxtended-plugins') .split() == ['balance.py', 'requirements.txt',
                                                                      'serverchecker.py']
        assert tgt.out(f'cat {QLDS}/minqlxtended.x64.so') == 'stub minqlxtended engine'
        assert _service_state(tgt) == 'inactive'
        assert _sentinels(tgt) == sentinels
        manifest = json.load(open(result['details']['manifest_path']))
        assert manifest['entries'][f'{QLDS}/baseq3/server.cfg']['existed'] is True

        # --- the patched loader, run as the service would, imports the isolated redis
        env_line = tgt.out(f'systemctl show -p Environment --value qlds@{PORT}')
        deps = dict(item.split('=', 1) for item in env_line.split())['QLSM_PYTHON_DEPS']
        tgt.run(f'{QLDS}/run_server_x64_minqlxtended.sh', user='ql',
                env={'QLSM_PYTHON_DEPS': deps, 'QLSM_PROBE_OUT': '/tmp/probe-up.json'})
        probe = json.loads(tgt.out('cat /tmp/probe-up.json'))
        assert int(probe['redis_version'].split('.')[0]) >= 5
        assert probe['redis_file'].startswith(venv + '/')
        assert not any('dist-packages' in p for p in probe['sys_path'])
        # ...and without the variable it is a no-op: the old global redis<3.
        tgt.run(f'{QLDS}/run_server_x64_minqlxtended.sh', user='ql',
                env={'QLSM_PROBE_OUT': '/tmp/probe-plain.json'})
        assert json.loads(tgt.out('cat /tmp/probe-plain.json'))['redis_version'].startswith('2.')

        # --- R4: later dependency installs for the upgraded instance go through
        # its venv (install_minqlx_deps.yml venv branch), never global pip.
        play = tmp_path / 'deps-play.yml'
        play.write_text(
            '- hosts: %s\n  become: yes\n  gather_facts: false\n  tasks:\n'
            '    - ansible.builtin.import_tasks: %s\n'
            % (HOST_NAME, os.path.join(ROOT, 'ansible/playbooks/tasks/install_minqlx_deps.yml')))
        deps_vars = {'qlds_dir': QLDS, 'runtime_plugins_dirname': 'minqlxtended-plugins',
                     'python_deps_path': venv}
        deps_run = _sh([ANSIBLE_BIN, str(play), '-i', tgt.inventory, '-l', HOST_NAME,
                        '-e', json.dumps(deps_vars)],
                       env=dict(os.environ, ANSIBLE_CONFIG=tgt.cfg, ANSIBLE_BECOME_FLAGS='-H -S -n',
                                ANSIBLE_PIPELINING='True'))
        assert deps_run.returncode == 0, deps_run.stdout + deps_run.stderr
        assert 'QLSM_PIP_WARN' not in deps_run.stdout
        venv_task = deps_run.stdout.split("isolated venv]", 1)[1].split('TASK [', 1)[0]
        assert 'changed: [%s]' % HOST_NAME in venv_task  # the venv branch really ran
        global_task = deps_run.stdout.split('TASK [Install plugin Python deps from requirements.txt]', 1)[1]
        assert global_task.split('TASK [', 1)[0].strip('* \n').startswith('skipping')
        after_deps = tgt.out(f"{venv}/bin/python -c 'import redis, six; print(redis.__version__)'", user='ql')
        assert int(after_deps.split('.')[0]) >= 5
        assert _global_python_state(tgt) == python_before

        # --- a stale fencing token is refused before any change
        stale = iru.configure_existing_instance(
            1, 'minqlxtended', {'config_dir': os.path.join(inputs, 'instances', '1')}, venv,
            operation_id=OP, fencing_token=0)
        assert not stale['ok'] and 'stale fencing token' in stale['error']

        # --- rollback: restore the inventory, configure minqlx with its original launch
        _set_runtime(ctx, 'minqlx')
        result = iru.configure_existing_instance(
            1, 'minqlx', {'config_dir': _minqlx_config(ctx['work'])}, None,
            operation_id=OP, fencing_token=2, restore_from_operation=OP)
        assert result['ok'], result['error']
        assert tgt.out(f'cat /etc/systemd/system/qlds@{PORT}.service') == unit_before
        assert tgt.sha(f'{QLDS}/baseq3/server.cfg') == cfg_before
        assert tgt.run(f'test -e {QLDS}/minqlxtended.x64.so', check=False).returncode != 0
        assert tgt.run(f'test -e {QLDS}/baseq3/scripts/ffa.factories', check=False).returncode != 0
        assert _service_state(tgt) == 'inactive'
        assert _sentinels(tgt) == sentinels
        assert _global_python_state(tgt) == python_before
        assert db.session.get(QLInstance, 1).python_deps_path is None
        assert tgt.run(f'test -d {venv}', check=False).returncode == 0  # old env kept
        assert iru.finalize_runtime_operation(ctx['host_id'], operation_id=OP, fencing_token=2)['ok']

        # --- conflicting instance requirements fail without touching global packages
        conflict = iru.install_runtime_on_host(
            ctx['host_id'], operation_id=CONFLICT_OP, fencing_token=1,
            immutable_inputs=iru.install_inputs_from_materialized(
                _inputs(ctx['work'], 'conflict', 'redis<3\n'), [1]))
        assert not conflict['ok']
        assert _global_python_state(tgt) == python_before
        assert iru.finalize_runtime_operation(ctx['host_id'], operation_id=CONFLICT_OP, fencing_token=1)['ok']
    finally:
        iru._run_host_ansible_playbook = real_runner


def test_apt_guard_rejects_an_install_that_removes_a_package(target, ctx):
    """chrony conflicts with the installed systemd-timesyncd: the simulation
    must refuse it and nothing may be installed or removed."""
    tgt = target
    installed = "dpkg-query -W -f='${db:Status-Abbrev}|${Package}|${Version}\\n' | grep '^ii'"
    dpkg_before = tgt.out(installed).splitlines()
    extravars = {
        'target_host_name': HOST_NAME, 'ansible_ssh_user': 'ansible',
        'ansible_ssh_private_key_file': tgt.key, 'operation_id': APT_OP, 'fencing_token': 1,
        'terminal_operation_ids': [SETUP_OP, OP, CONFLICT_OP], 'runtime_build_packages': ['chrony'],
        'common_plugins_builtin_src': '/nonexistent', 'runtime_instances': [],
    }
    env = dict(os.environ, ANSIBLE_CONFIG=tgt.cfg, ANSIBLE_BECOME_FLAGS='-H -S -n')
    result = _sh([ANSIBLE_BIN, os.path.join(ROOT, 'ansible/playbooks/install_runtime.yml'),
                  '-i', tgt.inventory, '-l', HOST_NAME, '-e', json.dumps(extravars)], env=env, cwd=ROOT)
    assert result.returncode != 0
    assert 'would remove systemd-timesyncd' in result.stdout
    assert tgt.out(installed).splitlines() == dpkg_before
    assert tgt.run('dpkg -s chrony', check=False).returncode != 0
    # The failed play still released its lock: the same operation can run again.
    record = json.loads(tgt.out('cat /var/lib/qlsm/runtime-ops/.token'))
    assert record['operation_id'] == APT_OP
    assert tgt.run(f"kill -0 {record['holder_pid']}", check=False).returncode != 0


def test_lock_refuses_a_concurrent_play(target, ctx):
    tgt = target
    holder = tgt.out('cat /var/lib/qlsm/runtime-ops/.token')
    pid = tgt.out('flock -n /var/lib/qlsm/runtime-ops/.lock sleep 30 >/dev/null 2>&1 & echo $!; sleep 1')
    from ui.task_logic import instance_runtime_update as iru
    _set_runtime(ctx, 'minqlx')
    result = iru.configure_existing_instance(
        1, 'minqlx', {'config_dir': _minqlx_config(ctx['work'])}, None,
        operation_id=APT_OP, fencing_token=5)
    assert not result['ok'] and 'still running' in result['error']
    assert tgt.out('cat /var/lib/qlsm/runtime-ops/.token') == holder
    tgt.run(f'kill {pid}; true')


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()
