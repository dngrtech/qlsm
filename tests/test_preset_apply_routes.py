"""Instance endpoints for the server-side preset apply: keep-cvars, preview, apply."""
import os
from unittest.mock import MagicMock, patch

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import HostStatus
from tests.test_preset_apply import _host, _instance, _preset, _with_compatibility, env  # noqa: F401


@pytest.fixture
def headers(app):
    with app.app_context():
        return {'Authorization': f'Bearer {create_access_token(identity="testuser")}'}


@pytest.fixture
def setup(env):  # noqa: F811
    host = _host()
    instance = _instance(host, server_cfg='set sv_tags "mine"\n')
    preset = _preset(env, configs={'server.cfg': 'set sv_tags "preset"\nset g_motd "hi"\n'})
    return instance, preset


def _url(instance, name):
    return f'/api/instances/{instance.id}/{name}'


def _drafts_dir():
    from ui.routes.draft_routes import _get_draft_base_path
    return os.path.dirname(_get_draft_base_path('x'))


def _draft_ids():
    base = _drafts_dir()
    return set(os.listdir(base)) if os.path.isdir(base) else set()


def _preview(client, headers, instance, preset, **extra):
    return client.post(_url(instance, 'preset-preview'), headers=headers,
                       json={'preset_id': preset.id, **extra})


def test_keep_cvars_route_lists_sources(client, headers, setup):
    instance, preset = setup
    fake = [{'cvar': 'sv_tags', 'sources': ['launch args']}]
    with patch('ui.routes.instance_routes.collect_keep_cvars', return_value=fake):
        response = client.get(_url(instance, 'preset-keep-cvars'),
                              query_string={'preset_id': preset.id}, headers=headers)
    assert response.status_code == 200
    assert response.get_json() == {'data': fake}


def test_keep_cvars_route_404s(client, headers, setup):
    instance, preset = setup
    assert client.get(_url(instance, 'preset-keep-cvars'),
                      query_string={'preset_id': 9999}, headers=headers).status_code == 404
    assert client.get('/api/instances/9999/preset-keep-cvars',
                      query_string={'preset_id': preset.id}, headers=headers).status_code == 404


def test_preview_returns_diff_and_hash_and_leaves_no_draft(client, headers, setup):
    instance, preset = setup
    before = _draft_ids()
    response = _preview(client, headers, instance, preset)
    assert response.status_code == 200, response.get_json()
    data = response.get_json()['data']
    for key in ('compatibility', 'needs_decision', 'keep_cvars', 'kept_cvars', 'diff',
                'preview_hash', 'target'):
        assert key in data
    assert 'draft_id' not in data['target']
    assert data['preview_hash']
    assert any(f['path'] == 'server.cfg' for f in data['diff']['files'])
    assert _draft_ids() == before


def test_preview_keep_draft_returns_target_and_draft(client, headers, env):  # noqa: F811
    instance = _instance(_host())
    preset = _preset(env, scripts={'a.py': '# a\n'}, checked_plugins=['a.py'])
    before = _draft_ids()
    response = _preview(client, headers, instance, preset, keep_draft=True)
    assert response.status_code == 200, response.get_json()
    target = response.get_json()['data']['target']
    assert target['draft_id']
    assert _draft_ids() - before == {target['draft_id']}


def test_preview_keep_draft_of_a_legacy_preset_has_no_draft(client, headers, setup):
    instance, preset = setup
    before = _draft_ids()
    response = _preview(client, headers, instance, preset, keep_draft=True)
    assert response.status_code == 200, response.get_json()
    assert 'draft_id' not in response.get_json()['data']['target']
    assert _draft_ids() == before


def test_preview_hash_is_stable(client, headers, setup):
    instance, preset = setup
    first = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    second = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    assert first == second


def _apply(client, headers, instance, preset, preview_hash, **extra):
    return client.post(_url(instance, 'apply-preset'), headers=headers, json={
        'preset_id': preset.id, 'restart': False, 'preview_hash': preview_hash, **extra})


def test_apply_with_matching_hash_queues_the_save(client, headers, setup):
    instance, preset = setup
    preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    before = _draft_ids()
    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task',
               return_value=MagicMock(id='job-1')) as enqueue:
        response = _apply(client, headers, instance, preset, preview_hash, restart=True)
    assert response.status_code == 202, response.get_json()
    enqueue.assert_called_once()
    assert enqueue.call_args.kwargs['restart'] is True
    assert _draft_ids() == before


def test_apply_with_stale_hash_is_409(client, headers, setup):
    instance, preset = setup
    before = _draft_ids()
    with patch('ui.routes.instance_routes.enqueue_task') as enqueue:
        response = _apply(client, headers, instance, preset, 'stale')
    assert response.status_code == 409
    assert response.get_json()['error']['message'] == \
        'Preset or server changed since the preview. Preview again.'
    enqueue.assert_not_called()
    assert _draft_ids() == before


def test_apply_needing_compat_decision_is_422(client, headers, setup):
    instance, preset = setup
    before = _draft_ids()
    fake = {'payload': {'draft_id': None}, 'needs_decision': True}
    with patch('ui.routes.instance_routes.build_preset_target') as build:
        from ui.routes.draft_routes import create_draft_workspace
        draft_id, _ = create_draft_workspace({'source': 'preset', 'preset': preset.name})
        fake['payload']['draft_id'] = draft_id
        build.return_value = fake
        response = _apply(client, headers, instance, preset, 'whatever')
    assert response.status_code == 422
    assert response.get_json()['error']['message'] == 'Plugin compatibility needs a decision'
    assert _draft_ids() == before


def test_apply_with_declined_replacements_is_not_422(client, headers, setup):
    instance, preset = setup
    compatibility = {
        'preset_runtime': 'minqlxtended', 'target_runtime': 'minqlx',
        'stripped': [{'path': 'b.py', 'replacement': 'b.py', 'originally_checked': True}],
        'replacements': {'b.py': '# b target\n'},
        'auto_accepted': [],
    }
    with _with_compatibility(compatibility, None):
        undecided = _preview(client, headers, instance, preset).get_json()['data']
        decided = _preview(client, headers, instance, preset,
                           accepted_replacements=[]).get_json()['data']
        assert undecided['needs_decision'] is True
        assert decided['needs_decision'] is False
        with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
             patch('ui.routes.instance_routes.enqueue_task',
                   return_value=MagicMock(id='job-1')):
            response = _apply(client, headers, instance, preset, decided['preview_hash'],
                              accepted_replacements=[])
            absent = _apply(client, headers, instance, preset, undecided['preview_hash'])
    assert response.status_code == 202, response.get_json()
    assert absent.status_code == 422


def test_apply_on_locked_instance_is_409(client, headers, setup):
    instance, preset = setup
    preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    before = _draft_ids()
    with patch('ui.routes.instance_routes.acquire_lock', return_value=False), \
         patch('ui.routes.instance_routes.enqueue_task') as enqueue:
        response = _apply(client, headers, instance, preset, preview_hash)
    assert response.status_code == 409
    enqueue.assert_not_called()
    assert _draft_ids() == before


def test_preview_and_apply_refuse_a_configuring_host(client, headers, setup):
    instance, preset = setup
    instance.host.status = HostStatus.CONFIGURING
    db.session.commit()
    assert _preview(client, headers, instance, preset).status_code == 409
    assert _apply(client, headers, instance, preset, 'x').status_code == 409


def test_unknown_preset_is_404(client, headers, setup):
    instance, _ = setup
    response = client.post(_url(instance, 'preset-preview'), headers=headers,
                           json={'preset_id': 9999})
    assert response.status_code == 404


@pytest.mark.parametrize('route,body', [
    ('preset-preview', {}),
    ('preset-preview', {'preset_id': 'x'}),
    ('preset-preview', {'preset_id': True}),
    ('preset-preview', {'preset_id': 1, 'accepted_replacements': 'abc'}),
    ('preset-preview', {'preset_id': 1, 'accepted_replacements': [1]}),
    ('preset-preview', {'preset_id': 1, 'keep_cvars': 'sv_tags'}),
    ('preset-preview', {'preset_id': 1, 'keep_cvars': [None]}),
    ('preset-preview', {'preset_id': 1, 'keep_draft': 'yes'}),
    ('apply-preset', {'preset_id': 1, 'restart': False}),
    ('apply-preset', {'preset_id': 1, 'preview_hash': 'h'}),
    ('apply-preset', {'preset_id': 1, 'restart': 'yes', 'preview_hash': 'h'}),
    ('apply-preset', {'preset_id': 1, 'restart': False, 'preview_hash': 5}),
    ('apply-preset', {'preset_id': 1, 'restart': False, 'preview_hash': 'h',
                      'keep_cvars': 'sv_tags'}),
])
def test_bad_body_is_400(client, headers, setup, route, body):
    instance, _ = setup
    response = client.post(_url(instance, route), headers=headers, json=body)
    assert response.status_code == 400, response.get_json()
