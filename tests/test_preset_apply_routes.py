"""Instance endpoints for the server-side preset apply: keep-cvars, preview, apply."""
import os
from unittest.mock import MagicMock, patch

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import HostStatus
from tests.test_preset_apply import (  # noqa: F401
    _add_preset_hook, _host, _instance, _preset, _with_compatibility, env,
)


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
    # The hash is compared under the instance lock, on the re-read row.
    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.release_lock'), \
         patch('ui.routes.instance_routes.enqueue_task') as enqueue:
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
    ('preset-preview', None),
    ('apply-preset', None),
    ('preset-preview', [1]),
    ('apply-preset', 'x'),
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


def test_apply_changing_hooks_on_an_updated_instance_forces_a_restart(client, headers, env):  # noqa: F811
    """An UPDATED instance still runs on its old files: a preset that changes
    its hooks must restart it, or the previous hooks stay loaded (the same
    rule as a config save, which the apply goes through)."""
    from ui.models import InstanceStatus

    host = _host()
    instance = _instance(host, server_cfg='', status=InstanceStatus.UPDATED)
    preset = _preset(env, enabled_hooks=['new.so'], checked_plugins=[])
    _add_preset_hook(preset, 'new.so')
    preview = _preview(client, headers, instance, preset).get_json()['data']
    assert preview['diff']['hooks'] == {'before': [], 'after': ['new.so']}

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task',
               return_value=MagicMock(id='job-1')) as enqueue:
        response = _apply(client, headers, instance, preset, preview['preview_hash'], restart=False,
                          confirm_restart=True)

    assert response.status_code == 202, response.get_json()
    assert enqueue.call_args.kwargs['restart'] is True


def test_deferred_apply_lists_its_change_only_once_synced(client, headers, setup):
    """The apply goes through save_instance_config: without a restart its
    pending record is staged and stays hidden until the sync job publishes
    it, so a sync that never ran does not show the preset as on the host."""
    from ui.models import InstanceStatus, QLInstance
    from ui.pending_changes import publish_pending_changes

    instance, preset = setup
    with client.application.app_context():
        db.session.get(QLInstance, instance.id).status = InstanceStatus.RUNNING
        db.session.commit()
    preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1')) as enqueue:
        response = _apply(client, headers, instance, preset, preview_hash, restart=False)
    assert response.status_code == 202, response.get_json()
    assert enqueue.call_args.kwargs['restart'] is False

    url = f'/api/instances/{instance.id}/pending-changes'
    assert client.get(url, headers=headers).get_json()['data']['entries'] == []
    with client.application.app_context():
        publish_pending_changes(instance.id)  # what the sync job does on the host
        db.session.commit()
    [entry] = client.get(url, headers=headers).get_json()['data']['entries']
    assert any(f['path'] == 'server.cfg' for f in entry['files'])


def _locked_apply(client, headers, instance, preset, preview_hash, **extra):
    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.release_lock'), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1')) as enqueue:
        response = _apply(client, headers, instance, preset, preview_hash, **extra)
    return response, enqueue


def test_apply_refuses_when_the_server_changed_after_the_preview(client, headers, setup):
    """Another operator saved the server between preview and apply: the
    apply must not overwrite it."""
    instance, preset = setup
    preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    cfg = os.path.join('configs', instance.host.name, str(instance.id), 'server.cfg')
    with open(cfg, 'a', encoding='utf-8') as f:
        f.write('set g_motd "edited by someone else"\n')

    response, enqueue = _locked_apply(client, headers, instance, preset, preview_hash, restart=False)
    assert response.status_code == 409, response.get_json()
    enqueue.assert_not_called()


def test_apply_never_starts_a_stopped_server(client, headers, setup):
    from ui.models import InstanceStatus, QLInstance

    instance, preset = setup
    with client.application.app_context():
        db.session.get(QLInstance, instance.id).status = InstanceStatus.STOPPED
        db.session.commit()
    preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    response, enqueue = _locked_apply(client, headers, instance, preset, preview_hash, restart=True)
    assert response.status_code == 202, response.get_json()
    assert enqueue.call_args.kwargs['restart'] is False


def test_apply_reads_the_status_again_under_the_lock(client, headers, setup):
    """A stop that finished while the apply built its target (seconds: SSH
    admin read, draft copy) is what the save sees, not the earlier read."""
    from ui.models import InstanceStatus, QLInstance

    instance, preset = setup
    with client.application.app_context():
        db.session.get(QLInstance, instance.id).status = InstanceStatus.RUNNING
        db.session.commit()
    preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']

    def _stop_meanwhile(*args, **kwargs):
        import sqlalchemy
        with db.engine.begin() as conn:
            conn.execute(sqlalchemy.text("UPDATE ql_instance SET status = 'STOPPED' WHERE id = :id"),
                         {'id': instance.id})
        return True

    with patch('ui.routes.instance_routes.acquire_lock', side_effect=_stop_meanwhile), \
         patch('ui.routes.instance_routes.release_lock'), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1')) as enqueue:
        response = _apply(client, headers, instance, preset, preview_hash, restart=True)
    assert response.status_code == 202, response.get_json()
    assert enqueue.call_args.kwargs['previous_status'] == 'stopped'
    assert enqueue.call_args.kwargs['restart'] is False


def test_preview_maps_an_unavailable_runtime_to_409(client, headers, setup):
    from ui.custom_runtime import RuntimeUnavailable

    instance, preset = setup
    with patch('ui.preset_apply.plugin_api_for_host', side_effect=RuntimeUnavailable('provider gone')):
        response = _preview(client, headers, instance, preset)
    assert response.status_code == 409
    assert 'provider gone' in response.get_json()['error']['message']


def test_preview_returns_the_whole_resulting_admin_list(client, headers, env):  # noqa: F811
    from ui import preset_apply

    host = _host()
    instance = _instance(host, server_cfg='')
    preset = _preset(env, admins=[{'steam_id64': '76561198000000001', 'level': 5}, {'steam_id64': '76561198000000002', 'level': 3}])
    current = [{'steam_id64': '76561198000000002', 'level': 3}, {'steam_id64': '76561198000000003', 'level': 4}]
    with patch.object(preset_apply, 'read_live_admins', return_value=(current, {}, None)):
        data = _preview(client, headers, instance, preset).get_json()['data']
    assert data['admins']['before'] == current
    assert sorted(data['admins']['after'], key=lambda e: e['steam_id64']) == [
        {'steam_id64': '76561198000000001', 'level': 5}, {'steam_id64': '76561198000000002', 'level': 3}]


def test_a_save_between_the_preview_diff_and_its_hash_is_not_applied(client, headers, setup):
    """Diff and hash come from one snapshot: a save landing between the two
    reads must make the apply refuse, not overwrite what the preview never
    showed."""
    from ui.preset_apply import diff_preset_target as real_diff

    instance, preset = setup
    cfg = os.path.join('configs', instance.host.name, str(instance.id), 'server.cfg')

    def _diff_then_save(*args, **kwargs):
        diff = real_diff(*args, **kwargs)
        with open(cfg, 'a', encoding='utf-8') as f:
            f.write('set g_motd "saved meanwhile"\n')
        return diff

    with patch('ui.routes.instance_routes.diff_preset_target', side_effect=_diff_then_save):
        preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    response, enqueue = _locked_apply(client, headers, instance, preset, preview_hash, restart=False)
    assert response.status_code == 409, response.get_json()
    enqueue.assert_not_called()


def test_a_live_admin_level_change_after_the_preview_is_not_applied(client, headers, env):  # noqa: F811
    """Same delta (A -> 5) against different live levels (3, then 4): the
    observed levels are part of the hash."""
    from ui import preset_apply

    host = _host()
    instance = _instance(host, server_cfg='')
    preset = _preset(env, admins=[{'steam_id64': '76561198000000001', 'level': 5}])
    with patch.object(preset_apply, 'read_live_admins',
                      return_value=([{'steam_id64': '76561198000000001', 'level': 3}], {}, None)):
        preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    with patch.object(preset_apply, 'read_live_admins',
                      return_value=([{'steam_id64': '76561198000000001', 'level': 4}], {}, None)):
        response, enqueue = _locked_apply(client, headers, instance, preset, preview_hash, restart=False)
    assert response.status_code == 409, response.get_json()
    enqueue.assert_not_called()


@pytest.mark.parametrize('status, expected', [('RUNNING', 409), ('UPDATED', 409), ('STOPPED', 202)])
def test_lan_rate_change_needs_a_restart_on_a_live_server(client, headers, env, status, expected):  # noqa: F811
    from ui.models import InstanceStatus

    host = _host()
    instance = _instance(host, server_cfg='', lan_rate_enabled=False, status=InstanceStatus[status])
    preset = _preset(env, lan_rate_enabled=True)
    preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    response, enqueue = _locked_apply(client, headers, instance, preset, preview_hash, restart=False)
    assert response.status_code == expected, response.get_json()
    if expected == 202:
        assert enqueue.call_args.kwargs['restart'] is False
    else:
        enqueue.assert_not_called()
        assert 'restart' in response.get_json()['error']['message'].lower()


def test_a_live_admin_change_after_the_apply_read_it_is_refused(client, headers, env):  # noqa: F811
    """The maintainer's sequence: preview and apply both read A=1; A goes to
    3 after the apply's read, before it takes the lock. The admin baseline
    is read again under the lock, so the apply refuses instead of queueing
    the preset's level 4 over a level it never saw."""
    from ui import preset_apply

    host = _host()
    instance = _instance(host, server_cfg='')
    preset = _preset(env, admins=[{'steam_id64': '76561198000000001', 'level': 4}])
    level1 = ([{'steam_id64': '76561198000000001', 'level': 1}], {}, None)
    level3 = ([{'steam_id64': '76561198000000001', 'level': 3}], {}, None)
    with patch.object(preset_apply, 'read_live_admins', return_value=level1):
        preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    # Apply: the target is built against level 1, the under-lock read sees 3.
    with patch.object(preset_apply, 'read_live_admins', side_effect=[level1, level3, level3]):
        response, enqueue = _locked_apply(client, headers, instance, preset, preview_hash, restart=False)
    assert response.status_code == 409, response.get_json()
    enqueue.assert_not_called()


@pytest.mark.parametrize('status, restart, hooks_change, confirm, expected', [
    ('RUNNING', False, True, False, 409),   # forced hook restart, unconfirmed
    ('UPDATED', False, True, False, 409),
    ('RUNNING', False, True, True, 202),
    ('RUNNING', True, False, False, 409),   # asked-for restart, unconfirmed
    ('RUNNING', True, False, True, 202),
    ('STOPPED', True, True, False, 202),    # a stopped server is never started
    ('RUNNING', False, False, False, 202),  # nothing restarts
])
def test_apply_refuses_an_unconfirmed_restart_of_a_live_server(
        client, headers, env, status, restart, hooks_change, confirm, expected):  # noqa: F811
    from ui.models import InstanceStatus

    host = _host()
    instance = _instance(host, server_cfg='', status=InstanceStatus[status], ld_preload_hooks='old.so')
    hooks = os.path.join('configs', host.name, str(instance.id), 'user-hooks')
    os.makedirs(hooks, exist_ok=True)
    for name in ('old.so', 'new.so'):
        with open(os.path.join(hooks, name), 'wb') as f:
            f.write(b'\x7fELF')
    preset = _preset(env, enabled_hooks=['new.so'] if hooks_change else ['old.so'])
    preview_hash = _preview(client, headers, instance, preset).get_json()['data']['preview_hash']
    response, enqueue = _locked_apply(client, headers, instance, preset, preview_hash,
                                      restart=restart, confirm_restart=confirm)
    assert response.status_code == expected, response.get_json()
    if expected == 409:
        enqueue.assert_not_called()
        assert 'Confirm the restart' in response.get_json()['error']['message']
