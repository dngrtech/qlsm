"""Tests for POST /api/hosts/<id>/resize."""
from unittest.mock import patch

import pytest

from tests.helpers import auth_headers, make_user
from ui import db
from ui.database import create_host, get_host
from ui.models import HostStatus

DEFAULT_USER = "resizeadmin"
DEFAULT_PASS = "resizeadminp1"


@pytest.fixture(autouse=True)
def setup_user(app):
    make_user(app, DEFAULT_USER, DEFAULT_PASS)


def _make_vultr_active_host(app, name="resize-host", plan="vc2-1c-2gb"):
    with app.app_context():
        host = create_host(
            name=name,
            provider="vultr",
            region="ewr",
            machine_size=plan,
            status=HostStatus.ACTIVE,
        )
        host.workspace_name = f"host-{host.id}-{name}"
        db.session.commit()
        return host.id


@patch("ui.routes.host_routes.enqueue_task")
@patch("ui.routes.host_routes.acquire_lock", return_value=True)
def test_resize_host_success(mock_lock, mock_enqueue, client, app):
    """Valid upgrade returns 202, sets host CONFIGURING, and queues task."""
    host_id = _make_vultr_active_host(app)
    headers = auth_headers(app, DEFAULT_USER)

    response = client.post(
        f"/api/hosts/{host_id}/resize",
        headers=headers,
        json={"new_plan": "vc2-2c-4gb"},
    )

    assert response.status_code == 202
    body = response.get_json()
    assert body["data"]["new_plan"] == "vc2-2c-4gb"
    assert body["data"]["current_plan"] == "vc2-1c-2gb"
    mock_enqueue.assert_called_once()
    assert mock_lock.call_args.kwargs["ttl"] == 900

    with app.app_context():
        host = get_host(host_id)
        assert host.status == HostStatus.CONFIGURING


def test_resize_host_not_found(client, app):
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post("/api/hosts/99999/resize", headers=headers, json={"new_plan": "vc2-2c-4gb"})
    assert response.status_code == 404


def test_resize_host_unauthenticated(client):
    response = client.post("/api/hosts/1/resize", json={"new_plan": "vc2-2c-4gb"})
    assert response.status_code == 401


def test_resize_host_non_vultr(client, app):
    """Non-Vultr hosts return 409."""
    with app.app_context():
        host = create_host(name="sa-host", provider="standalone", is_standalone=True, status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers, json={"new_plan": "vc2-2c-4gb"})

    assert response.status_code == 409
    assert "vultr" in response.get_json()["error"]["message"].lower()


def test_resize_host_not_active(client, app):
    with app.app_context():
        host = create_host(
            name="err-host",
            provider="vultr",
            region="ewr",
            machine_size="vc2-1c-2gb",
            status=HostStatus.ERROR,
        )
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers, json={"new_plan": "vc2-2c-4gb"})

    assert response.status_code == 409
    assert "active" in response.get_json()["error"]["message"].lower()


def test_resize_host_missing_body(client, app):
    host_id = _make_vultr_active_host(app, name="no-body")
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers)
    assert response.status_code == 400


def test_resize_host_missing_new_plan(client, app):
    host_id = _make_vultr_active_host(app, name="no-plan")
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers, json={})
    assert response.status_code == 400


def test_resize_host_invalid_new_plan_type(client, app):
    host_id = _make_vultr_active_host(app, name="bad-plan-type")
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers, json={"new_plan": 123})
    assert response.status_code == 400


def test_resize_host_unknown_plan(client, app):
    host_id = _make_vultr_active_host(app, name="unknown-plan")
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers, json={"new_plan": "made-up"})
    assert response.status_code == 400
    assert "unknown plan" in response.get_json()["error"]["message"].lower()


def test_resize_host_same_plan(client, app):
    host_id = _make_vultr_active_host(app, name="same-plan", plan="vc2-1c-2gb")
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers, json={"new_plan": "vc2-1c-2gb"})
    assert response.status_code == 400
    assert "same plan" in response.get_json()["error"]["message"].lower()


def test_resize_host_downgrade_rejected(client, app):
    host_id = _make_vultr_active_host(app, name="dg-host", plan="vc2-2c-4gb")
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers, json={"new_plan": "vc2-1c-1gb"})
    assert response.status_code == 400
    assert "upgrade" in response.get_json()["error"]["message"].lower()


def test_resize_host_cross_family_rejected(client, app):
    host_id = _make_vultr_active_host(app, name="xf-host", plan="vc2-1c-2gb")
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers, json={"new_plan": "vhf-2c-4gb"})
    assert response.status_code == 400
    assert "family" in response.get_json()["error"]["message"].lower()


@patch("ui.routes.host_routes.acquire_lock", return_value=False)
def test_resize_host_lock_conflict(mock_lock, client, app):
    host_id = _make_vultr_active_host(app, name="locked-host")
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f"/api/hosts/{host_id}/resize", headers=headers, json={"new_plan": "vc2-2c-4gb"})

    assert response.status_code == 409
    assert "another operation" in response.get_json()["error"]["message"].lower()


@patch("ui.routes.host_routes.release_lock")
@patch("ui.routes.host_routes.enqueue_task", side_effect=Exception("Redis down"))
@patch("ui.routes.host_routes.acquire_lock", return_value=True)
def test_resize_host_enqueue_failure_reverts_status(mock_lock, mock_enqueue, mock_release, client, app):
    """If enqueue fails after status flipped to CONFIGURING, revert to ACTIVE."""
    host_id = _make_vultr_active_host(app, name="enqueue-fail-host")
    headers = auth_headers(app, DEFAULT_USER)

    response = client.post(
        f"/api/hosts/{host_id}/resize",
        headers=headers,
        json={"new_plan": "vc2-2c-4gb"},
    )

    assert response.status_code == 500
    mock_release.assert_called_once()
    with app.app_context():
        host = get_host(host_id)
        assert host.status == HostStatus.ACTIVE


def test_resize_host_non_dict_body_rejected(client, app):
    """Non-object JSON (list, string) must return 400 not 500."""
    host_id = _make_vultr_active_host(app, name="badjson-host")
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(
        f"/api/hosts/{host_id}/resize",
        headers=headers,
        json=["not", "an", "object"],
    )
    assert response.status_code == 400
