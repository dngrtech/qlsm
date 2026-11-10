"""GET/POST /api/hosts/<id>/runtime-upgrade: the compatibility dry-run and the
confirmation that reserves the host and queues the upgrade job.

Real SQLite and instance config trees under tmp_path (runtime_upgrade_harness);
Redis task locks are a dict, and the RQ enqueue is captured.
"""
import json

import pytest

from tests.helpers import auth_headers
from tests.runtime_upgrade_harness import make_env, make_host
from ui import db
from ui.models import Host, HostStatus, InstanceStatus, QLInstance
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.routes import host_runtime_upgrade_routes as routes
from ui.task_lock import MAINTENANCE_LOCK_KEY


class FakeLocks:
    """task_lock's acquire/release semantics over a dict, including the
    refusal while a backup holds the maintenance lock."""

    def __init__(self):
        self.held = {}
        self.maintenance = False

    def acquire_lock(self, entity_type, entity_id, token, ttl):
        key = (entity_type, entity_id)
        if self.maintenance or key in self.held:
            return False
        self.held[key] = (token, ttl)
        return True

    def release_lock(self, entity_type, entity_id, token):
        key = (entity_type, entity_id)
        if self.held.get(key, (None,))[0] == token:
            del self.held[key]
            return True
        return False

    def acquire_locks(self, entity_type, entity_ids, token, ttl):
        acquired = []
        for entity_id in sorted(set(entity_ids)):
            if not self.acquire_lock(entity_type, entity_id, token, ttl):
                self.release_locks(entity_type, acquired, token)
                return False
            acquired.append(entity_id)
        return True

    def release_locks(self, entity_type, entity_ids, token):
        for entity_id in sorted(set(entity_ids)):
            self.release_lock(entity_type, entity_id, token)

    def maintenance_active(self):
        return self.maintenance


@pytest.fixture
def headers(app):
    return auth_headers(app, 'u')


@pytest.fixture
def locks(monkeypatch):
    fake = FakeLocks()
    for name in ('acquire_lock', 'release_lock', 'acquire_locks', 'release_locks'):
        monkeypatch.setattr(routes, name, getattr(fake, name))
    monkeypatch.setattr(routes, '_backup_maintenance_active', fake.maintenance_active)
    return fake


@pytest.fixture
def enqueued(monkeypatch, locks):
    """Captures enqueue_task calls; records which locks were held at the time."""
    calls = []

    def fake_enqueue(task_func, *args, **kwargs):
        calls.append({'task': task_func, 'args': args, 'kwargs': kwargs,
                      'locks_held': dict(locks.held)})
        return None

    monkeypatch.setattr('ui.tasks.enqueue_task', fake_enqueue)
    return calls


@pytest.fixture
def world(app, tmp_path, monkeypatch):
    env = make_env(app, tmp_path, monkeypatch)
    with app.app_context():
        host = make_host(env)
        yield env, host.id, sorted(inst.id for inst in host.instances)


def _url(host_id):
    return f'/api/hosts/{host_id}/runtime-upgrade'


def _dry_run(client, headers, host_id):
    resp = client.get(_url(host_id), headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']


def _post(client, headers, host_id, body):
    return client.post(_url(host_id), headers=headers, json=body)


def _ops():
    return HostRuntimeUpgradeOperation.query.all()


def _error(resp):
    return resp.get_json()['error']['message']


# --- GET ----------------------------------------------------------------------

def test_get_dry_run_returns_instances_and_fingerprint(app, client, headers, world):
    _env, host_id, instance_ids = world
    for inst in db.session.get(Host, host_id).instances:
        inst.zmq_rcon_password = f'RCONSECRET{inst.id}'
        inst.zmq_stats_password = f'STATSSECRET{inst.id}'
    db.session.commit()
    data = _dry_run(client, headers, host_id)

    assert data['eligibility'] == {'visible': True, 'enabled': True, 'reason': None}
    assert [row['instance_id'] for row in data['instances']] == instance_ids
    first = data['instances'][0]
    assert 'balance.py' in first['auto_accepted']
    assert [row['path'] for row in first['stripped'] if row['kind'] == 'replaceable'] == ['ban.py']
    assert isinstance(data['fingerprint'], str) and len(data['fingerprint']) == 64
    # The capture carries ZMQ passwords; nothing of it but the digest leaves.
    body = json.dumps(data)
    assert 'SECRET' not in body
    assert 'renderer' not in body


def test_get_ineligible_returns_409_with_reason(app, client, headers, world):
    _env, host_id, _ids = world
    host = db.session.get(Host, host_id)
    host.os_version = '22.04'
    db.session.commit()

    resp = client.get(_url(host_id), headers=headers)
    assert resp.status_code == 409
    assert _error(resp) == 'minqlxtended requires Ubuntu 24.04 or newer; this host runs Ubuntu 22.04'


def test_get_runtime_not_minqlx_returns_409(app, client, headers, world):
    _env, host_id, _ids = world
    db.session.get(Host, host_id).runtime = 'minqlxtended'
    db.session.commit()

    resp = client.get(_url(host_id), headers=headers)
    assert resp.status_code == 409
    assert _error(resp)


def test_get_missing_host_returns_404(app, client, headers, world):
    assert client.get(_url(9999), headers=headers).status_code == 404


def test_requires_jwt(app, client, world):
    _env, host_id, _ids = world
    assert client.get(_url(host_id)).status_code == 401
    assert client.post(_url(host_id), json={'fingerprint': 'x'}).status_code == 401


# --- POST: body validation (before any lock) ------------------------------------

@pytest.mark.parametrize('body', [
    [],
    {'accepted_replacements': {}},
    {'fingerprint': 5, 'accepted_replacements': {}},
    {'fingerprint': '', 'accepted_replacements': {}},
    {'fingerprint': 'f', 'accepted_replacements': []},
    {'fingerprint': 'f', 'accepted_replacements': {'x': []}},
    {'fingerprint': 'f', 'accepted_replacements': {'1': [3]}},
    {'fingerprint': 'f', 'accepted_replacements': {'1': ['ban.py', 'ban.py']}},
    {'fingerprint': 'f', 'accepted_replacements': {'1': [], '01': []}},
])
def test_post_rejects_malformed_body(app, client, headers, world, locks, enqueued, body):
    _env, host_id, _ids = world
    resp = _post(client, headers, host_id, body)
    assert resp.status_code == 400, resp.get_json()
    assert locks.held == {}
    assert _ops() == [] and enqueued == []


def test_post_rejects_non_list_value(app, client, headers, world, locks, enqueued):
    _env, host_id, ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    resp = _post(client, headers, host_id,
                 {'fingerprint': fp, 'accepted_replacements': {str(ids[0]): 'ban.py'}})
    assert resp.status_code == 400
    assert locks.held == {}
    assert _ops() == [] and enqueued == []


def test_post_rejects_unoffered_path(app, client, headers, world, locks, enqueued):
    _env, host_id, ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    # mine.py is stripped with nothing to replace it: never offered.
    resp = _post(client, headers, host_id,
                 {'fingerprint': fp, 'accepted_replacements': {str(ids[0]): ['ban.py', 'mine.py']}})
    assert resp.status_code == 400
    assert 'mine.py' in _error(resp)
    assert locks.held == {}
    assert _ops() == [] and enqueued == []
    assert db.session.get(Host, host_id).status == HostStatus.ACTIVE


def test_post_rejects_unknown_instance(app, client, headers, world, locks, enqueued):
    _env, host_id, _ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    resp = _post(client, headers, host_id,
                 {'fingerprint': fp, 'accepted_replacements': {'9999': []}})
    assert resp.status_code == 400
    assert locks.held == {}
    assert _ops() == [] and enqueued == []


# --- POST: success ----------------------------------------------------------------

def test_post_enqueues_and_returns_202(app, client, headers, world, locks, enqueued):
    from ui.tasks import upgrade_host_runtime

    _env, host_id, ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    # auto-accepted balance.py may be echoed back (combineAcceptedPaths output).
    resp = _post(client, headers, host_id, {
        'fingerprint': fp,
        'accepted_replacements': {str(ids[0]): ['ban.py', 'balance.py'], str(ids[1]): []},
    })

    assert resp.status_code == 202, resp.get_json()
    assert resp.get_json() == {'data': {'status': 'configuring'}, 'message': 'Runtime upgrade queued.'}

    [op] = _ops()
    assert op.state == 'preparing'
    assert op.fingerprint == fp
    assert op.original_runtime == 'minqlx'
    assert op.original_host_status == 'active'
    inputs = json.loads(op.inputs_json)
    assert [inst['instance_id'] for inst in inputs['instances']] == ids
    answers = json.loads(op.answers_json)
    assert answers[str(ids[0])] == ['ban.py']
    assert answers[str(ids[1])] == [] and answers[str(ids[2])] == []
    assert db.session.get(Host, host_id).status == HostStatus.CONFIGURING

    [call] = enqueued
    assert call['task'] is upgrade_host_runtime
    assert call['args'] == (op.id,)
    assert call['kwargs']['job_id'] == op.rq_job_id
    from ui.task_logic.job_failure_handlers import runtime_upgrade_job_failure_handler
    assert call['kwargs']['on_failure'] is runtime_upgrade_job_failure_handler
    # R12: the worker takes the locks itself; none may be held at enqueue.
    assert call['locks_held'] == {}
    assert locks.held == {}


def test_post_takes_host_and_instance_locks_with_upgrade_ttl(app, client, headers, world,
                                                               locks, enqueued, monkeypatch):
    _env, host_id, ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    seen = {}
    original = routes.capture_upgrade_inputs

    def spy(host):
        seen.update(locks.held)
        return original(host)

    monkeypatch.setattr(routes, 'capture_upgrade_inputs', spy)
    resp = _post(client, headers, host_id, {'fingerprint': fp, 'accepted_replacements': {}})
    assert resp.status_code == 202
    from ui.tasks import RUNTIME_UPGRADE_TIMEOUT
    assert set(seen) == {('host', host_id)} | {('instance', i) for i in ids}
    assert {ttl for _token, ttl in seen.values()} == {RUNTIME_UPGRADE_TIMEOUT + 300}
    assert len({token for token, _ttl in seen.values()}) == 1


def test_post_enqueue_failure_leaves_reservation_for_reconciler(app, client, headers, world,
                                                                locks, monkeypatch):
    _env, host_id, _ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']

    def broken(*_a, **_k):
        raise ConnectionError('redis down')

    monkeypatch.setattr('ui.tasks.enqueue_task', broken)
    resp = _post(client, headers, host_id, {'fingerprint': fp, 'accepted_replacements': {}})

    assert resp.status_code == 500
    assert 'automatically' in _error(resp)
    [op] = _ops()
    # The job id was recorded before the push; whether the push landed is
    # unknown, so the route leaves the row to the reconciler.
    assert op.state == 'preparing' and op.rq_job_id
    assert db.session.get(Host, host_id).status == HostStatus.CONFIGURING
    assert locks.held == {}


# --- POST: conflicts (409) --------------------------------------------------------

def test_post_409_when_instance_locked(app, client, headers, world, locks, enqueued):
    _env, host_id, ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    locks.held[('instance', ids[1])] = ('other-task', 60)

    resp = _post(client, headers, host_id, {'fingerprint': fp, 'accepted_replacements': {}})
    assert resp.status_code == 409
    assert locks.held == {('instance', ids[1]): ('other-task', 60)}
    assert _ops() == [] and enqueued == []
    assert db.session.get(Host, host_id).status == HostStatus.ACTIVE


def test_post_409_when_host_locked(app, client, headers, world, locks, enqueued):
    _env, host_id, _ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    locks.held[('host', host_id)] = ('other-task', 60)

    resp = _post(client, headers, host_id, {'fingerprint': fp, 'accepted_replacements': {}})
    assert resp.status_code == 409
    assert locks.held == {('host', host_id): ('other-task', 60)}
    assert _ops() == [] and enqueued == []


def test_post_409_during_backup_maintenance(app, client, headers, world, locks, enqueued):
    _env, host_id, _ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    locks.maintenance = True

    resp = _post(client, headers, host_id, {'fingerprint': fp, 'accepted_replacements': {}})
    assert resp.status_code == 409
    assert 'backup' in _error(resp).lower()
    assert locks.held == {}
    assert _ops() == [] and enqueued == []


def test_post_409_when_fingerprint_stale(app, client, headers, world, locks, enqueued):
    env, host_id, ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    host = db.session.get(Host, host_id)
    (env.configs / host.name / str(ids[0]) / 'server.cfg').write_text('set sv_hostname "edited"\n')

    resp = _post(client, headers, host_id, {'fingerprint': fp, 'accepted_replacements': {}})
    assert resp.status_code == 409
    assert 'changed' in _error(resp)
    assert locks.held == {}
    assert _ops() == [] and enqueued == []
    assert db.session.get(Host, host_id).status == HostStatus.ACTIVE


def test_post_409_when_already_reserved(app, client, headers, world, locks, enqueued):
    _env, host_id, _ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    db.session.add(HostRuntimeUpgradeOperation(host_id=host_id, state='recovery_required'))
    db.session.commit()

    resp = _post(client, headers, host_id, {'fingerprint': fp, 'accepted_replacements': {}})
    assert resp.status_code == 409
    assert 'being upgraded' in _error(resp)
    assert locks.held == {}
    assert len(_ops()) == 1 and enqueued == []


def test_post_409_when_host_not_active(app, client, headers, world, locks, enqueued):
    _env, host_id, _ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    db.session.get(Host, host_id).status = HostStatus.ERROR
    db.session.commit()

    resp = _post(client, headers, host_id, {'fingerprint': fp, 'accepted_replacements': {}})
    assert resp.status_code == 409
    assert 'ACTIVE' in _error(resp)
    assert locks.held == {}
    assert _ops() == [] and enqueued == []


def test_post_409_when_instance_added_while_waiting_for_locks(app, client, headers, world,
                                                               locks, enqueued, monkeypatch):
    """An instance created between the pre-lock read and the lock is unlocked:
    refuse rather than upgrade a host with an instance nobody holds."""
    _env, host_id, _ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    original = locks.acquire_locks

    def acquire_then_add(entity_type, entity_ids, token, ttl):
        ok = original(entity_type, entity_ids, token, ttl)
        db.session.add(QLInstance(host_id=host_id, name='late', port=27999, hostname='late',
                                  zmq_rcon_port=28999, zmq_rcon_password='r', zmq_stats_port=29998,
                                  zmq_stats_password='s', status=InstanceStatus.STOPPED))
        db.session.commit()
        return ok

    monkeypatch.setattr(routes, 'acquire_locks', acquire_then_add)
    resp = _post(client, headers, host_id, {'fingerprint': fp, 'accepted_replacements': {}})
    assert resp.status_code == 409
    assert locks.held == {}
    assert _ops() == [] and enqueued == []


def test_post_missing_host_returns_404(app, client, headers, world, locks, enqueued):
    resp = _post(client, headers, 9999, {'fingerprint': 'f', 'accepted_replacements': {}})
    assert resp.status_code == 404


def test_get_classifies_each_instance_once_with_an_identical_fingerprint(
        app, client, headers, world, monkeypatch):
    from ui import runtime_upgrade
    from ui.runtime_upgrade import capture_upgrade_inputs, classification_fingerprint, classify_instance

    _env, host_id, instance_ids = world
    host = db.session.get(Host, host_id)
    expected_rows = [classify_instance(inst) for inst in sorted(host.instances, key=lambda i: i.id)]
    expected_fp = classification_fingerprint(capture_upgrade_inputs(host))
    real = runtime_upgrade._classify
    calls = []

    def counting(instance):
        calls.append(instance.id)
        return real(instance)

    monkeypatch.setattr(runtime_upgrade, '_classify', counting)
    data = _dry_run(client, headers, host_id)
    assert sorted(calls) == instance_ids
    assert data['instances'] == json.loads(json.dumps(expected_rows))
    assert data['fingerprint'] == expected_fp


# --- plugin uploads ---------------------------------------------------------------

GOOD_PLUGIN = 'import minqlxtended\n\nclass mine(minqlxtended.Plugin):\n    pass\n'
BAD_PLUGIN = 'import minqlx\n\nclass mine(minqlx.Plugin):\n    pass\n'


def _validate_url(host_id):
    return f'/api/hosts/{host_id}/runtime-upgrade/validate-plugin'


def test_validate_plugin_accepts_a_ported_file(app, client, headers, world):
    _env, host_id, _ids = world
    resp = client.post(_validate_url(host_id), headers=headers,
                       json={'path': 'mine.py', 'text': GOOD_PLUGIN})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json() == {'data': {'path': 'mine.py', 'verdict': 'unknown'}}
    assert _ops() == []


def test_validate_plugin_rejects_minqlx_code_with_reasons(app, client, headers, world):
    _env, host_id, _ids = world
    resp = client.post(_validate_url(host_id), headers=headers,
                       json={'path': 'mine.py', 'text': BAD_PLUGIN})
    assert resp.status_code == 400
    error = resp.get_json()['error']
    assert error['message'] and error['reasons']


def test_validate_plugin_rejects_a_lone_surrogate_with_400(app, client, headers, world):
    _env, host_id, _ids = world
    resp = client.post(_validate_url(host_id), headers=headers,
                       json={'path': 'mine.py', 'text': '\ud800'})
    assert resp.status_code == 400
    assert resp.get_json()['error']['message']


@pytest.mark.parametrize('raw', [
    b'[]', b'null', b'not json', b'', b'{"path": 1, "text": "x"}',
    b'{"path": "mine.py"}', b'{"path": "\\ud800", "text": "x"}',
    b'[' * 100000,
])
def test_validate_plugin_malformed_bodies_return_400(app, client, headers, world, raw):
    _env, host_id, _ids = world
    resp = client.post(_validate_url(host_id), headers=headers, data=raw,
                       content_type='application/json')
    assert resp.status_code == 400, resp.data
    assert resp.get_json()['error']['message']


def test_validate_plugin_requires_jwt(app, client, world):
    _env, host_id, _ids = world
    assert client.post(_validate_url(host_id),
                       json={'path': 'mine.py', 'text': GOOD_PLUGIN}).status_code == 401


def test_validate_plugin_missing_host_returns_404(app, client, headers, world):
    resp = client.post(_validate_url(99999), headers=headers,
                       json={'path': 'mine.py', 'text': GOOD_PLUGIN})
    assert resp.status_code == 404


def _upload_body(fp, ids, **extra):
    body = {
        'fingerprint': fp,
        'accepted_replacements': {},
        'uploaded_files': {'f1': {'path': 'mine.py', 'text': GOOD_PLUGIN}},
        'uploaded_file_ids': {str(ids[0]): {'mine.py': 'f1'}},
    }
    body.update(extra)
    return body


def test_post_with_an_upload_stores_it_on_the_operation(app, client, headers, world, locks, enqueued):
    _env, host_id, ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    resp = _post(client, headers, host_id, _upload_body(fp, ids))
    assert resp.status_code == 202, resp.get_json()
    [op] = _ops()
    uploads = json.loads(op.uploads_json)
    assert uploads[str(ids[0])] == {'mine.py': GOOD_PLUGIN}
    assert json.loads(op.answers_json) == {str(i): [] for i in ids}


def test_post_shares_one_upload_between_instances(app, client, headers, world, locks, enqueued):
    from ui.models import QLInstance
    _env, host_id, ids = world
    # make mine.py enabled (hence unavailable) on a second instance too
    db.session.get(QLInstance, ids[1]).qlx_plugins = 'balance, mine'
    db.session.commit()
    fp = _dry_run(client, headers, host_id)['fingerprint']
    body = _upload_body(fp, ids, uploaded_file_ids={
        str(ids[0]): {'mine.py': 'f1'}, str(ids[1]): {'mine.py': 'f1'}})
    resp = _post(client, headers, host_id, body)
    assert resp.status_code == 202, resp.get_json()
    [op] = _ops()
    uploads = json.loads(op.uploads_json)
    assert uploads[str(ids[0])] == uploads[str(ids[1])] == {'mine.py': GOOD_PLUGIN}


def _bad_upload(name):
    big = 'import minqlxtended\n\nclass mine(minqlxtended.Plugin):\n    pass\n' + '#' * (500 * 1024)
    return {
        'missing_file_id': {'uploaded_file_ids': {'IDS0': {'mine.py': 'nope'}}},
        'path_mismatch': {'uploaded_files': {'f1': {'path': 'other.py', 'text': GOOD_PLUGIN}}},
        'replaceable_path': {
            'uploaded_files': {'f1': {'path': 'ban.py', 'text': GOOD_PLUGIN}},
            'uploaded_file_ids': {'IDS0': {'ban.py': 'f1'}}},
        'path_not_in_rows': {
            'uploaded_files': {'f1': {'path': 'zzz.py', 'text': GOOD_PLUGIN}},
            'uploaded_file_ids': {'IDS0': {'zzz.py': 'f1'}}},
        'unknown_instance': {'uploaded_file_ids': {'9999': {'mine.py': 'f1'}}},
        'too_big_total': {
            'uploaded_files': {f'f{i}': {'path': 'mine.py', 'text': big} for i in range(5)}},
        'files_not_dict': {'uploaded_files': []},
        'ids_not_dict': {'uploaded_file_ids': []},
        'file_entry_not_dict': {'uploaded_files': {'f1': 'x'}},
        'ids_entry_not_dict': {'uploaded_file_ids': {'IDS0': ['mine.py']}},
        'file_id_not_str': {'uploaded_file_ids': {'IDS0': {'mine.py': 5}}},
        'bad_instance_key': {'uploaded_file_ids': {'x': {'mine.py': 'f1'}}},
        'lone_surrogate_text': {'uploaded_files': {'f1': {'path': 'mine.py', 'text': '\ud800'}}},
        'lone_surrogate_unreferenced': {
            'uploaded_files': {'f1': {'path': 'mine.py', 'text': GOOD_PLUGIN},
                               'f2': {'path': 'mine.py', 'text': '\ud800'}}},
        'lone_surrogate_path': {
            'uploaded_files': {'f1': {'path': 'mine\ud800.py', 'text': GOOD_PLUGIN}},
            'uploaded_file_ids': {'IDS0': {'mine\ud800.py': 'f1'}}},
        'lone_surrogate_accepted_path': {'accepted_replacements': {'IDS0': ['\ud800']}},
        'invalid_plugin': {'uploaded_files': {'f1': {'path': 'mine.py', 'text': BAD_PLUGIN}}},
    }[name]


@pytest.mark.parametrize('name', [
    'missing_file_id', 'path_mismatch', 'replaceable_path', 'path_not_in_rows',
    'unknown_instance', 'too_big_total', 'files_not_dict', 'ids_not_dict',
    'file_entry_not_dict', 'ids_entry_not_dict', 'file_id_not_str', 'bad_instance_key',
    'lone_surrogate_text', 'lone_surrogate_unreferenced', 'lone_surrogate_path',
    'lone_surrogate_accepted_path', 'invalid_plugin',
])
def test_post_rejects_bad_uploads(app, client, headers, world, locks, enqueued, name):
    _env, host_id, ids = world
    fp = _dry_run(client, headers, host_id)['fingerprint']
    override = json.loads(json.dumps(_bad_upload(name)).replace('IDS0', str(ids[0])))
    resp = _post(client, headers, host_id, _upload_body(fp, ids, **override))
    assert resp.status_code == 400, resp.get_json()
    assert locks.held == {}
    assert _ops() == [] and enqueued == []
    assert db.session.get(Host, host_id).status == HostStatus.ACTIVE


def test_post_malformed_raw_bodies_return_400(app, client, headers, world, locks, enqueued):
    _env, host_id, _ids = world
    for raw in (b'not json', b'', b'[' * 100000, b'{"fingerprint": "\\ud800"}'):
        resp = client.post(_url(host_id), headers=headers, data=raw,
                           content_type='application/json')
        assert resp.status_code == 400, (raw[:20], resp.data)
