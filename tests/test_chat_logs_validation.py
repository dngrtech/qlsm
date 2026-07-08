"""Validation tests for the chat-logs endpoint.

These guard the security-sensitive input handling on
GET /api/instances/<id>/chat-logs: the filter_mode enum, the filename regex
(path-traversal / injection guard), and the `since` allowlist. The rejection
paths return 400 before any Ansible execution, so they need no subprocess mocks.
"""
from types import SimpleNamespace
from unittest.mock import patch

from flask_jwt_extended import create_access_token

from ui import db
from ui.database import create_host, create_instance
from ui.models import HostStatus


def _make_instance(app):
    with app.app_context():
        host = create_host(name='chatlog-host', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(
            name='chatlog-inst', host_id=host.id, port=27960, hostname='chat.host',
        )
        db.session.commit()
        token = create_access_token(identity='testuser')
        return instance.id, token


def _headers(token):
    return {'Authorization': f'Bearer {token}'}


def _get(client, instance_id, token, **params):
    return client.get(
        f'/api/instances/{instance_id}/chat-logs',
        query_string=params,
        headers=_headers(token),
    )


def test_invalid_filter_mode_rejected(client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='bogus')
    assert resp.status_code == 400


def test_path_traversal_filename_rejected(client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='lines', filename='../../../../etc/passwd')
    assert resp.status_code == 400


def test_malformed_filename_rejected(client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='lines', filename='chat.log.abc')
    assert resp.status_code == 400


def test_invalid_since_rejected_in_time_mode(client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='time', since='yesterday')
    assert resp.status_code == 400


@patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_chat_logs',
       return_value=(True, 'log line', None))
def test_invalid_since_ignored_outside_time_mode(mock_fetch, client, app):
    """`since` is only meaningful for time mode; a bad value must not 400 in lines mode."""
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='lines', since='yesterday')
    assert resp.status_code == 200


@patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_chat_logs',
       return_value=(True, 'log line', None))
def test_valid_time_request_passes_validation(mock_fetch, client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='time', since='1 hour ago')
    assert resp.status_code == 200
    # `since` and filter_mode reach the task logic unchanged
    assert mock_fetch.call_args.kwargs['filter_mode'] == 'time'
    assert mock_fetch.call_args.kwargs['since'] == '1 hour ago'
