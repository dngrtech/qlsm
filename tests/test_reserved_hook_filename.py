import io

import pytest

from tests.helpers import auth_headers
from ui import db
from ui.models import Host, QLInstance


@pytest.fixture
def instance_in_db(app):
    with app.app_context():
        host = Host(name="h1", provider="vultr", ip_address="1.1.1.1")
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(
            name="i1",
            port=27960,
            hostname="hn",
            host_id=host.id,
            qlx_plugins="",
            zmq_rcon_port=28888,
            zmq_rcon_password="x",
            zmq_stats_port=29999,
            zmq_stats_password="y",
        )
        db.session.add(inst)
        db.session.commit()
        yield inst


def test_commit_rejects_reserved_filename(client, app, instance_in_db):
    headers = auth_headers(app, "testuser")
    response = client.post(
        "/api/drafts/",
        json={
            "source": "instance",
            "host": instance_in_db.host.name,
            "instance_id": instance_in_db.id,
        },
        headers=headers,
    )
    assert response.status_code == 201
    draft_id = response.get_json()["data"]["draft_id"]
    upload = client.post(
        f"/api/drafts/{draft_id}/upload",
        data={"file": (io.BytesIO(b"\x7fELF" + b"\x00" * 32), "force_rate.so")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200

    response = client.post(
        f"/api/drafts/{draft_id}/commit",
        json={
            "target": "instance",
            "host": instance_in_db.host.name,
            "instance_id": instance_in_db.id,
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "reserved" in response.get_json()["error"]["message"].lower()
