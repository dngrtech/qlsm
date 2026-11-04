"""Shared harness for the host runtime upgrade orchestrator tests.

Real: SQLite DB, instance config trees, snapshot/presets under tmp_path, the
conversion. Faked at the remote boundary: one FakeRemote per host holding each
instance's service/runtime/inventory state and the highest fencing token it
has seen (it survives a simulated worker death), FakeLocks standing in for
Redis, and FakeDeps -- the per-worker UpgradeDeps -- which can fail any call
or die (raise Crash, a BaseException nothing catches) at a checkpoint.
"""
import json
import os
import stat
from types import SimpleNamespace

from ui import db, plugin_pool, preset_compat, runtime_upgrade
from ui.models import Host, HostStatus, InstanceStatus, QLInstance
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.routes import preset_api_routes
from ui.runtime_upgrade import capture_upgrade_inputs, classification_fingerprint
from ui.task_logic.host_runtime_upgrade_deps import UpgradeDeps

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
REAL_BUILTIN_PRESETS = os.path.join(REPO_ROOT, 'configs', 'presets', '_builtin')
STOCK = os.path.join(REAL_BUILTIN_PRESETS, 'default', 'scripts')
ELF = b'\x7fELF\x02\x01\x01\x00' + bytes(range(64))
BUSY = 'another runtime operation play is still running on this host (operation x, holder pid 1)'


class Crash(BaseException):
    """Simulated worker death."""


def _read(path):
    with open(path, 'r', encoding='utf-8') as handle:
        return handle.read()


def make_env(app, tmp_path, monkeypatch):
    configs = tmp_path / 'configs'
    presets = tmp_path / 'presets'
    pool = tmp_path / 'shared-plugins'
    for path in (configs, presets, pool):
        path.mkdir()
    monkeypatch.setattr(runtime_upgrade, 'CONFIGS_BASE', str(configs))
    monkeypatch.setattr(plugin_pool, 'OPERATOR_POOL_BASE', str(pool))
    monkeypatch.setattr(preset_compat, 'BUILTIN_PRESETS_DIR', REAL_BUILTIN_PRESETS)
    monkeypatch.setattr(preset_api_routes, 'PRESETS_DIR', str(presets))
    monkeypatch.setattr('ui.task_logic.hook_paths.CONFIGS_BASE', str(configs))
    app.config['RUNTIME_UPGRADES_DIR'] = str(tmp_path / 'runtime-upgrades')
    return SimpleNamespace(tmp=tmp_path, configs=configs, pool=pool, presets=presets,
                           upgrades=tmp_path / 'runtime-upgrades')


# Three instances: A running (stock + edited plugins), B stopped with the
# force_rate.so hook enabled, C running with a NULL plugin selection.
SPECS = (
    ('A', InstanceStatus.RUNNING, 'balance, ban, mine', None),
    ('B', InstanceStatus.STOPPED, 'balance', 'force_rate.so'),
    ('C', InstanceStatus.RUNNING, None, None),
)


def make_host(env, specs=SPECS, name='uh'):
    host = Host(name=name, provider='vultr', status=HostStatus.ACTIVE, runtime='minqlx',
                os_type='ubuntu', os_version='24.04', ip_address='203.0.113.9',
                ssh_key_path='/k', lan_rate_uses_hook=True)
    db.session.add(host)
    db.session.commit()
    for index, (label, status, plugins, hooks) in enumerate(specs):
        inst = QLInstance(
            host_id=host.id, name=f'{name}-{label}', port=27960 + index, hostname=f'S{label}',
            qlx_plugins=plugins, ld_preload_hooks=hooks, lan_rate_enabled=bool(hooks),
            zmq_rcon_port=28888 + index, zmq_rcon_password='rcon',
            zmq_stats_port=29999 + index, zmq_stats_password='stats', status=status)
        db.session.add(inst)
        db.session.commit()
        root = env.configs / host.name / str(inst.id)
        (root / 'scripts').mkdir(parents=True)
        (root / 'scripts' / 'balance.py').write_text(_read(os.path.join(STOCK, 'balance.py')))
        (root / 'scripts' / 'ban.py').write_text(_read(os.path.join(STOCK, 'ban.py')) + '\n# edited\n')
        (root / 'scripts' / 'mine.py').write_text('import minqlx\n\nclass mine(minqlx.Plugin):\n    pass\n')
        (root / 'server.cfg').write_text(f'set sv_hostname "{label}"\n')
        (root / 'user-hooks').mkdir()
        (root / 'user-hooks' / 'force_rate.so').write_bytes(ELF)
        os.chmod(root / 'server.cfg', 0o640)
    db.session.refresh(host)
    return host


def create_operation(host, answers=None):
    """What Task 6 does on confirm: persist the capture and answers, reserve,
    put the host in CONFIGURING."""
    inputs = capture_upgrade_inputs(host)
    op = HostRuntimeUpgradeOperation(
        host_id=host.id, state='preparing', inputs_json=json.dumps(inputs),
        fingerprint=classification_fingerprint(inputs),
        answers_json=json.dumps(answers or {}), original_runtime=host.runtime,
        original_host_status='active')
    db.session.add(op)
    host.status = HostStatus.CONFIGURING
    db.session.commit()
    return op


def tree_state(root):
    files, dirs = {}, {}
    for current, _dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(current, root).replace(os.sep, '/')
        dirs[rel_dir] = stat.S_IMODE(os.stat(current).st_mode)
        for filename in filenames:
            full = os.path.join(current, filename)
            with open(full, 'rb') as handle:
                files[os.path.relpath(full, root).replace(os.sep, '/')] = (
                    handle.read(), stat.S_IMODE(os.stat(full).st_mode))
    return files, dirs


def capture_originals(env, host):
    return {
        inst.id: {
            'tree': tree_state(env.configs / host.name / str(inst.id)),
            'qlx_plugins': inst.qlx_plugins,
            'ld_preload_hooks': inst.ld_preload_hooks,
            'status': inst.status,
            'name': inst.name,
        }
        for inst in host.instances
    }


class FakeLocks:
    """Redis task locks: key -> owner token. Survives worker death."""

    def __init__(self):
        self.owners = {}

    def _keys(self, host_id, ids):
        return [('host', host_id)] + [('instance', i) for i in sorted(set(ids))]

    def acquire(self, operation_id, token, host_id, ids):
        keys = self._keys(host_id, ids)
        prefix = f'rtu:{operation_id}:'
        for key in keys:
            owner = self.owners.get(key)
            if owner and owner != token and not owner.startswith(prefix):
                return False
        for key in keys:
            self.owners[key] = token
        return True

    def renew(self, operation_id, token, host_id, ids):
        return all(self.owners.setdefault(key, token) == token for key in self._keys(host_id, ids))

    def release(self, operation_id, token, host_id, ids):
        for key in self._keys(host_id, ids):
            if self.owners.get(key) == token:
                del self.owners[key]


class FakeRemote:
    """The game host: per-instance service, runtime and inventory state."""

    def __init__(self, host):
        self.services = {inst.id: {'active': inst.status == InstanceStatus.RUNNING,
                                   'runtime': 'minqlx', 'inventory': False, 'deps': None}
                         for inst in host.instances}
        self.max_token = {}
        self.installed = False
        self.finalized = []
        self.busy = 0


class FakeDeps(UpgradeDeps):
    ready_timeout = 60

    def __init__(self, remote, locks, *, fail=(), crash_at=None, alive=(), on_checkpoint=None):
        self.remote = remote
        self.locks = locks
        self.fail = set(fail)
        self.crash_at = crash_at
        self.alive = set(alive)
        self.on_checkpoint = on_checkpoint
        self.calls = []
        self.enqueued = []
        self.enqueue_error = None
        self.dead = False

    def _service(self, instance):
        return self.remote.services[instance.id]

    def _fenced(self, operation_id, token):
        seen = self.remote.max_token.get(operation_id, 0)
        if token < seen:
            return f'stale fencing token {token}; host has seen {seen}'
        self.remote.max_token[operation_id] = token
        return None

    def stop(self, instance):
        self.calls.append(('stop', instance.id))
        if ('stop', instance.id) in self.fail:
            return False, 'stop playbook failed'
        self._service(instance)['active'] = False
        instance.status = InstanceStatus.STOPPED
        db.session.commit()
        return True, None

    def start(self, instance):
        self.calls.append(('start', instance.id))
        if ('start', instance.id) in self.fail:
            return False, 'start playbook failed'
        self._service(instance)['active'] = True
        return True, None

    def service_state(self, instance):
        if ('state', instance.id) in self.fail:
            return 'unknown'
        return 'active' if self._service(instance)['active'] else 'inactive'

    def wait_ready(self, instance, timeout=60):
        self.calls.append(('ready', instance.id))
        if ('ready', instance.id) in self.fail:
            return False, f'not ready within {timeout}s: server has not reported status'
        return (True, None) if self._service(instance)['active'] else (False, 'service is not active')

    def install(self, host_id, *, operation_id, fencing_token, immutable_inputs):
        self.calls.append(('install', host_id))
        refused = self._fenced(operation_id, fencing_token)
        if refused:
            return {'ok': False, 'error': refused, 'details': {}}
        if 'install' in self.fail:
            return {'ok': False, 'error': 'fatal: [uh]: FAILED! => python 3.12 required', 'details': {}}
        self.remote.installed = True
        return {'ok': True, 'error': None, 'details': {}}

    def configure(self, instance_id, runtime, immutable_inputs, dependency_path, *,
                  operation_id, fencing_token, restore_from_operation=None):
        rollback = restore_from_operation is not None
        self.calls.append(('configure', instance_id, runtime, rollback))
        instance = db.session.get(QLInstance, instance_id)
        service = self.remote.services[instance_id]
        if instance.host.runtime != runtime:
            return {'ok': False, 'error': 'commit the runtime first', 'details': {}}
        if self.remote.busy:
            self.remote.busy -= 1
            return {'ok': False, 'error': BUSY, 'details': {}}
        refused = self._fenced(operation_id, fencing_token)
        if refused:
            return {'ok': False, 'error': refused, 'details': {}}
        if service['active']:
            return {'ok': False, 'error': 'service is running', 'details': {}}
        if ('configure', instance_id, rollback) in self.fail:
            return {'ok': False, 'error': 'fatal: configure failed', 'details': {}}
        if rollback:
            if service['inventory']:
                service.update(runtime='minqlx', inventory=False, deps=None)
            instance.python_deps_path = None
        else:
            assert os.path.isdir(immutable_inputs['config_dir'])
            service.update(runtime=runtime, inventory=True, deps=dependency_path,
                           hooks=sorted(os.listdir(immutable_inputs['system_hooks_dir'])))
            instance.python_deps_path = dependency_path
        db.session.commit()
        return {'ok': True, 'error': None, 'details': {}}

    def finalize(self, host_id, *, operation_id, fencing_token):
        self.calls.append(('finalize', host_id))
        self.remote.finalized.append(operation_id)
        return {'ok': True, 'error': None, 'details': {}}

    def job_alive(self, job_id, now=None):
        return job_id in self.alive

    def enqueue_recovery(self, operation_id, job_id):
        if self.enqueue_error:
            raise self.enqueue_error
        self.enqueued.append((operation_id, job_id))

    def checkpoint(self, name):
        self.calls.append(('checkpoint', name))
        if self.on_checkpoint:
            self.on_checkpoint(name)
        if name == self.crash_at:
            self.dead = True
            # A dead worker's `finally` never runs: keep its locks.
            self.locks.release = lambda *a, **k: None
            raise Crash(name)


def fresh_worker():
    """Forget everything the dead worker's session held."""
    db.session.rollback()
    db.session.remove()


def restore_lock_release(locks):
    locks.release = FakeLocks.release.__get__(locks)


def assert_original(env, host_id, originals, remote, *, ops_state='rolled_back'):
    """Host back on minqlx with every instance's files, DB fields and service
    state as they were before the upgrade."""
    host = db.session.get(Host, host_id)
    assert host.runtime == 'minqlx'
    assert host.runtime_deps_isolated is False
    for iid, original in originals.items():
        inst = db.session.get(QLInstance, iid)
        assert tree_state(env.configs / host.name / str(iid)) == original['tree'], iid
        assert inst.qlx_plugins == original['qlx_plugins']
        assert inst.ld_preload_hooks == original['ld_preload_hooks']
        assert inst.status == original['status']
        assert inst.python_deps_path is None
        service = remote.services[iid]
        assert service['active'] == (original['status'] == InstanceStatus.RUNNING)
        assert service['runtime'] == 'minqlx' and service['inventory'] is False
    op = HostRuntimeUpgradeOperation.query.filter_by(host_id=host_id).order_by(
        HostRuntimeUpgradeOperation.created_at.desc()).first()
    assert op.state == ops_state
    return host, op
