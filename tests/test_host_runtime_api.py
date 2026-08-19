"""POST /api/hosts accepts an optional runtime, defaulting to minqlx."""
import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import Host
from ui.runtime import MINQLX, MINQLXTENDED


@pytest.fixture
def auth_headers(app):
    with app.app_context():
        return {"Authorization": f"Bearer {create_access_token(identity='testuser')}"}


@pytest.fixture
def stub_provisioning(monkeypatch):
    """Host creation enqueues a provisioning job; we only care about the row."""
    import ui.routes.host_routes as mod
    monkeypatch.setattr(mod, "enqueue_task", lambda *a, **k: None)
    monkeypatch.setattr(mod, "acquire_lock", lambda *a, **k: True)
    monkeypatch.setattr(mod, "release_lock", lambda *a, **k: None)
    monkeypatch.setattr(mod, "is_vultr_configured", lambda: True)


def _cloud_payload(name, **extra):
    return {"name": name, "provider": "vultr", "region": "ewr",
            "machine_size": "vc2-1c-2gb", **extra}


def test_cloud_host_defaults_to_minqlx(app, client, auth_headers, stub_provisioning):
    response = client.post("/api/hosts/", json=_cloud_payload("default-host"),
                           headers=auth_headers)
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["runtime"] == MINQLX

    with app.app_context():
        host = Host.query.filter_by(name="default-host").one()
        assert host.runtime == MINQLX
        assert host.os_type == "debian"


def test_cloud_host_accepts_minqlxtended_and_targets_ubuntu(app, client, auth_headers,
                                                            stub_provisioning):
    """A minqlxtended host provisions on Ubuntu 24.04, so os_type must follow
    the runtime rather than the old hardcoded 'debian'."""
    response = client.post("/api/hosts/",
                           json=_cloud_payload("tended-host", runtime="minqlxtended"),
                           headers=auth_headers)
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["runtime"] == MINQLXTENDED

    with app.app_context():
        host = Host.query.filter_by(name="tended-host").one()
        assert host.runtime == MINQLXTENDED
        assert host.os_type == "ubuntu"


@pytest.mark.parametrize("bad", ["minqlx2", "", "  ", "MINQLX-TENDED", 7, [], {}])
def test_invalid_runtime_is_rejected(app, client, auth_headers, stub_provisioning, bad):
    """An unknown runtime must 400, never silently default -- the choice is
    irreversible, so guessing on the operator's behalf is not acceptable."""
    response = client.post("/api/hosts/", json=_cloud_payload("bad-host", runtime=bad),
                           headers=auth_headers)
    assert response.status_code == 400
    assert "runtime" in response.get_json()["error"]["message"].lower()

    with app.app_context():
        assert Host.query.filter_by(name="bad-host").first() is None


def test_runtime_is_case_insensitive(app, client, auth_headers, stub_provisioning):
    response = client.post("/api/hosts/",
                           json=_cloud_payload("case-host", runtime="MinQLXtended"),
                           headers=auth_headers)
    assert response.status_code == 201, response.get_json()

    with app.app_context():
        assert Host.query.filter_by(name="case-host").one().runtime == MINQLXTENDED


def test_validate_runtime_helper():
    from ui.routes.host_routes import _validate_runtime

    assert _validate_runtime(None) == (MINQLX, None)
    assert _validate_runtime("minqlxtended") == (MINQLXTENDED, None)

    value, error = _validate_runtime("nope")
    assert value is None
    assert "minqlx" in error and "minqlxtended" in error
