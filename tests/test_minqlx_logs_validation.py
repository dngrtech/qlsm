"""Validation tests for the minqlx-logs endpoints.

These guard GET /api/instances/<id>/minqlx-logs and
GET /api/instances/<id>/minqlx-logs/list input handling:
filter_mode is limited to lines/all, filename is limited to minqlx.log
rotations, lines is an integer in range for lines mode, missing
instance/host state is classified before task execution, and rejection
paths return before Ansible execution.
"""
from unittest.mock import patch

from flask_jwt_extended import create_access_token

from ui import db
from ui.database import create_host, create_instance
from ui.models import HostStatus, QLInstance


def _make_instance(app):
    with app.app_context():
        host = create_host(name='minqlx-host', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(
            name='minqlx-inst', host_id=host.id, port=27960, hostname='minqlx.host',
        )
        db.session.commit()
        token = create_access_token(identity='testuser')
        return instance.id, token


def _make_instance_without_host(app):
    with app.app_context():
        instance = QLInstance(
            name='minqlx-no-host', host_id=999999, port=27961, hostname='minqlx.nohost',
        )
        db.session.add(instance)
        db.session.commit()
        token = create_access_token(identity='testuser')
        return instance.id, token


def _headers(token):
    return {'Authorization': f'Bearer {token}'}


def _get(client, instance_id, token, **params):
    return client.get(
        f'/api/instances/{instance_id}/minqlx-logs',
        query_string=params,
        headers=_headers(token),
    )


def _get_list(client, instance_id, token):
    return client.get(
        f'/api/instances/{instance_id}/minqlx-logs/list',
        headers=_headers(token),
    )


def test_invalid_filter_mode_rejected_before_task_logic(client, app):
    instance_id, token = _make_instance(app)
    with patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs') as mock_fetch:
        resp = _get(client, instance_id, token, filter_mode='bogus')
    assert resp.status_code == 400
    mock_fetch.assert_not_called()


def test_time_filter_mode_rejected_before_task_logic(client, app):
    instance_id, token = _make_instance(app)
    with patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs') as mock_fetch:
        resp = _get(client, instance_id, token, filter_mode='time')
    assert resp.status_code == 400
    mock_fetch.assert_not_called()


def test_path_traversal_filename_rejected_before_task_logic(client, app):
    instance_id, token = _make_instance(app)
    with patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs') as mock_fetch:
        resp = _get(client, instance_id, token, filter_mode='lines', filename='../../../../etc/passwd')
    assert resp.status_code == 400
    mock_fetch.assert_not_called()


def test_malformed_filename_rejected_before_task_logic(client, app):
    instance_id, token = _make_instance(app)
    with patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs') as mock_fetch:
        resp = _get(client, instance_id, token, filter_mode='lines', filename='minqlx.log.old')
    assert resp.status_code == 400
    mock_fetch.assert_not_called()


def test_lines_below_minimum_rejected_before_task_logic(client, app):
    instance_id, token = _make_instance(app)
    with patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs') as mock_fetch:
        resp = _get(client, instance_id, token, filter_mode='lines', lines=9)
    assert resp.status_code == 400
    mock_fetch.assert_not_called()


def test_lines_above_maximum_rejected_before_task_logic(client, app):
    instance_id, token = _make_instance(app)
    with patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs') as mock_fetch:
        resp = _get(client, instance_id, token, filter_mode='lines', lines=10001)
    assert resp.status_code == 400
    mock_fetch.assert_not_called()


def test_non_integer_lines_rejected_before_task_logic(client, app):
    instance_id, token = _make_instance(app)
    with patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs') as mock_fetch:
        resp = _get(client, instance_id, token, filter_mode='lines', lines='abc')
    assert resp.status_code == 400
    mock_fetch.assert_not_called()


def test_missing_instance_fetch_returns_404_before_task_logic(client, app):
    _, token = _make_instance(app)
    with patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs') as mock_fetch:
        resp = _get(client, 999999, token, filter_mode='lines')
    assert resp.status_code == 404
    mock_fetch.assert_not_called()


def test_missing_host_fetch_returns_400_before_task_logic(client, app):
    instance_id, token = _make_instance_without_host(app)
    with patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs') as mock_fetch:
        resp = _get(client, instance_id, token, filter_mode='lines')
    assert resp.status_code == 400
    mock_fetch.assert_not_called()


def test_missing_instance_list_returns_404_before_task_logic(client, app):
    _, token = _make_instance(app)
    with patch('ui.task_logic.ansible_instance_mgmt.list_instance_minqlx_logs') as mock_list:
        resp = _get_list(client, 999999, token)
    assert resp.status_code == 404
    mock_list.assert_not_called()


def test_missing_host_list_returns_400_before_task_logic(client, app):
    instance_id, token = _make_instance_without_host(app)
    with patch('ui.task_logic.ansible_instance_mgmt.list_instance_minqlx_logs') as mock_list:
        resp = _get_list(client, instance_id, token)
    assert resp.status_code == 400
    mock_list.assert_not_called()


@patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs',
       return_value=(True, 'log line', None))
def test_valid_lines_request_passes_validation(mock_fetch, client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='lines', lines=250, filename='minqlx.log.1')
    assert resp.status_code == 200
    assert resp.get_json()['data']['logs'] == 'log line'
    assert mock_fetch.call_args.kwargs['filter_mode'] == 'lines'
    assert mock_fetch.call_args.kwargs['lines'] == 250
    assert mock_fetch.call_args.kwargs['filename'] == 'minqlx.log.1'


@patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs',
       return_value=(True, 'all log lines', None))
def test_valid_all_request_passes_validation(mock_fetch, client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='all', lines=1, filename='minqlx.log')
    assert resp.status_code == 200
    assert resp.get_json()['data']['logs'] == 'all log lines'
    assert mock_fetch.call_args.kwargs['filter_mode'] == 'all'


@patch('ui.task_logic.ansible_instance_mgmt.list_instance_minqlx_logs',
       return_value=(True, ['minqlx.log', 'minqlx.log.1'], None))
def test_list_request_passes_validation(mock_list, client, app):
    instance_id, token = _make_instance(app)
    resp = _get_list(client, instance_id, token)
    assert resp.status_code == 200
    assert resp.get_json()['data'] == {
        'files': ['minqlx.log', 'minqlx.log.1'],
        'instance_name': 'minqlx-inst',
    }
    mock_list.assert_called_once_with(instance_id)
