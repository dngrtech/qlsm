import io
import os

import pytest

from tests.helpers import auth_headers
from ui import db
from ui.models import Host, QLInstance


@pytest.fixture
def instance_with_so(app, tmp_path, monkeypatch):
    monkeypatch.setattr("ui.routes.draft_routes.CONFIGS_BASE", str(tmp_path / "configs"))
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
            ld_preload_hooks="a.so,b.so",
            zmq_rcon_port=28888,
            zmq_rcon_password="x",
            zmq_stats_port=29999,
            zmq_stats_password="y",
        )
        db.session.add(inst)
        db.session.commit()
        scripts = tmp_path / "configs" / host.name / str(inst.id) / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "a.so").write_bytes(b"\x7fELF" + b"\x00" * 32)
        (scripts / "b.so").write_bytes(b"\x7fELF" + b"\x00" * 32)
        yield inst


def test_commit_removes_orphan_hooks_from_instance(client, app, instance_with_so):
    headers = auth_headers(app, "testuser")
    response = client.post(
        "/api/drafts/",
        json={
            "source": "instance",
            "host": instance_with_so.host.name,
            "instance_id": instance_with_so.id,
        },
        headers=headers,
    )
    assert response.status_code == 201
    draft_id = response.get_json()["data"]["draft_id"]
    os.remove(os.path.join(app.config["DRAFTS_BASE"], draft_id, "scripts", "a.so"))
    upload = client.post(
        f"/api/drafts/{draft_id}/upload",
        data={"file": (io.BytesIO(b"\x7fELF" + b"\x00" * 32), "b.so")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200

    response = client.post(
        f"/api/drafts/{draft_id}/commit",
        json={
            "target": "instance",
            "host": instance_with_so.host.name,
            "instance_id": instance_with_so.id,
        },
        headers=headers,
    )
    assert response.status_code == 200

    with app.app_context():
        fresh = db.session.get(QLInstance, instance_with_so.id)
        assert fresh.ld_preload_hooks == "b.so"
