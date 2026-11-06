"""POST /api/instances/ fires instance.created before the first deploy.

What matters: every addon gets only its own `addon_options` entry, the
handler runs with the instance row committed and before the deploy job is
queued (so what it prepares reaches the first deploy), and no handler can
stop the instance from being created.
"""
import sys
from unittest.mock import patch

from flask_jwt_extended import create_access_token

from tests.test_addon_registry import addon_app, write_addon  # noqa: F401  (fixture)
from ui import db
from ui.database import create_host
from ui.models import AppSetting, HostStatus, InstanceStatus, QLInstance

RECORDING_BACKEND = '''
    import sys

    from ui import db
    from ui.models import QLInstance

    CALLS = []

    def register(ctx):
        @ctx.on('instance.created')
        def created(instance_id, options):
            instance = db.session.get(QLInstance, instance_id)
            CALLS.append({
                'instance_id': instance_id,
                'options': options,
                'name': instance.name if instance else None,
                'status': instance.status.value if instance else None,
            })
'''

FAILING_BACKEND = '''
    from ui import db
    from ui.models import AppSetting

    def register(ctx):
        @ctx.on('instance.created')
        def created(instance_id, options):
            db.session.add(AppSetting(key='half-done', value='1'))
            raise RuntimeError('addon exploded')
'''


def _payload(host_id, **extra):
    payload = {
        'name': 'new-instance',
        'host_id': host_id,
        'port': 27960,
        'hostname': 'new.hostname',
        'configs': {'server.cfg': '', 'mappool.txt': '', 'access.txt': '', 'workshop.txt': ''},
    }
    payload.update(extra)
    return payload


def _setup(app):
    with app.app_context():
        host = create_host(name='created-host', provider='vultr', status=HostStatus.ACTIVE)
        db.session.commit()
        return host.id, {'Authorization': f'Bearer {create_access_token(identity="testuser")}'}


def _calls(addon_id):
    return sys.modules[f'qlsm_addon_{addon_id.replace("-", "_")}'].CALLS


@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
@patch('ui.routes.instance_routes.enqueue_task')
def test_each_addon_gets_its_own_options_before_the_deploy_is_queued(
    mock_enqueue, mock_lock, addon_app, tmp_path, monkeypatch,  # noqa: F811
):
    build, packages, _ = addon_app
    write_addon(packages, 'alpha', manifest={'id': 'alpha', 'version': '1.0.0'}, backend=RECORDING_BACKEND)
    write_addon(packages, 'beta', manifest={'id': 'beta', 'version': '1.0.0'}, backend=RECORDING_BACKEND)
    app = build()
    monkeypatch.chdir(tmp_path)
    host_id, headers = _setup(app)
    mock_enqueue.return_value = type('Job', (), {'id': 'fake-job-id'})()

    response = app.test_client().post('/api/instances/', json=_payload(
        host_id, addon_options={'alpha': {'enabled': True, 'server_id': '42'}},
    ), headers=headers)

    assert response.status_code == 201, response.get_json()
    instance_id = response.get_json()['data']['id']
    assert _calls('alpha') == [{
        'instance_id': instance_id, 'options': {'enabled': True, 'server_id': '42'},
        'name': 'new-instance', 'status': InstanceStatus.IDLE.value,
    }]
    # beta sent nothing: it is still called (an API client sends no tab
    # values at all), with empty options rather than alpha's.
    assert _calls('beta')[0]['options'] == {}
    mock_enqueue.assert_called_once()


@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
@patch('ui.routes.instance_routes.enqueue_task')
def test_a_failing_handler_cannot_stop_the_instance_being_created(
    mock_enqueue, mock_lock, addon_app, tmp_path, monkeypatch,  # noqa: F811
):
    build, packages, _ = addon_app
    write_addon(packages, 'angry', manifest={'id': 'angry', 'version': '1.0.0'}, backend=FAILING_BACKEND)
    app = build()
    monkeypatch.chdir(tmp_path)
    host_id, headers = _setup(app)
    mock_enqueue.return_value = type('Job', (), {'id': 'fake-job-id'})()

    response = app.test_client().post('/api/instances/', json=_payload(host_id), headers=headers)

    assert response.status_code == 201, response.get_json()
    mock_enqueue.assert_called_once()
    with app.app_context():
        instance = db.session.get(QLInstance, response.get_json()['data']['id'])
        assert instance.status == InstanceStatus.DEPLOYING
        # What the failing handler left in the session was rolled back, not
        # committed along with the status update that followed it.
        assert db.session.get(AppSetting, 'half-done') is None


@patch('ui.routes.instance_routes.enqueue_task')
def test_malformed_addon_options_are_rejected_before_anything_is_created(
    mock_enqueue, addon_app, tmp_path, monkeypatch,  # noqa: F811
):
    build, _, _ = addon_app
    app = build()
    monkeypatch.chdir(tmp_path)
    host_id, headers = _setup(app)

    for bad in (['alpha'], {'alpha': 'on'}):
        response = app.test_client().post(
            '/api/instances/', json=_payload(host_id, addon_options=bad), headers=headers,
        )
        assert response.status_code == 400
        assert 'addon_options' in response.get_json()['error']['message']

    mock_enqueue.assert_not_called()
    with app.app_context():
        assert QLInstance.query.count() == 0
