import io
from unittest.mock import patch

import pytest

from tests.helpers import auth_headers
from ui import db
from ui.models import Host, InstanceStatus, QLInstance


@pytest.fixture(autouse=True)
def mock_lock():
    """CRUD endpoints use Redis-backed locking; mock it in tests."""
    with patch("ui.routes.instance_hooks_files_routes.acquire_lock", return_value=True), \
         patch("ui.routes.instance_hooks_files_routes.release_lock"):
        yield


@pytest.fixture
def headers(app):
    return auth_headers(app, "u")


@pytest.fixture
def instance(app, tmp_path, monkeypatch):
    with app.app_context():
        host = Host(name="hu", provider="vultr", ip_address="1.1.1.1")
        db.session.add(host); db.session.flush()
        inst = QLInstance(
            name="iu", port=27980, hostname="hh", host_id=host.id, qlx_plugins="",
            ld_preload_hooks=None, status=InstanceStatus.RUNNING,
            zmq_rcon_port=29110, zmq_rcon_password="r",
            zmq_stats_port=29111, zmq_stats_password="s",
        )
        db.session.add(inst); db.session.commit()
        monkeypatch.setattr(
            "ui.task_logic.hook_paths.CONFIGS_BASE",
            str(tmp_path / "configs"),
        )
        yield inst


def _upload(client, headers, inst_id, filename, content):
    return client.post(
        f"/api/instances/{inst_id}/hooks/files",
        data={"file": (io.BytesIO(content), filename)},
        headers=headers,
        content_type="multipart/form-data",
    )


def test_upload_creates_file_in_user_hooks(client, headers, instance, tmp_path):
    res = _upload(client, headers, instance.id, "alpha.so", b"\x7fELF" + b"\x00" * 64)
    assert res.status_code == 201
    body = res.get_json()["data"]
    assert body["filename"] == "alpha.so"
    assert (tmp_path / "configs" / "hu" / str(instance.id) / "user-hooks" / "alpha.so").is_file()


def test_upload_rejects_non_elf(client, headers, instance):
    res = _upload(client, headers, instance.id, "bad.so", b"NOT_ELF_DATA")
    assert res.status_code == 400


def test_upload_rejects_non_so_extension(client, headers, instance):
    res = _upload(client, headers, instance.id, "bad.txt", b"\x7fELF")
    assert res.status_code == 400


def test_upload_rejects_reserved_name(client, headers, instance):
    res = _upload(client, headers, instance.id, "force_rate.so", b"\x7fELF")
    assert res.status_code == 400
    assert "reserved" in res.get_json()["error"]["message"].lower()


def test_upload_rejects_path_traversal(client, headers, instance):
    res = _upload(client, headers, instance.id, "../escape.so", b"\x7fELF")
    assert res.status_code == 400


def test_upload_rejects_collision(client, headers, instance):
    _upload(client, headers, instance.id, "dup.so", b"\x7fELF" + b"\x00" * 8)
    res = _upload(client, headers, instance.id, "dup.so", b"\x7fELF" + b"\x00" * 8)
    assert res.status_code == 409


def test_upload_requires_auth(client, instance):
    res = client.post(
        f"/api/instances/{instance.id}/hooks/files",
        data={"file": (io.BytesIO(b"\x7fELF"), "x.so")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 401


def test_upload_rejects_unicode_filename(client, headers, instance):
    res = _upload(client, headers, instance.id, "héllo.so", b"\x7fELF")
    assert res.status_code == 400
    assert "forbidden" in res.get_json()["error"]["message"].lower()


# ── Replace ──────────────────────────────────────────────────────────────────

def _put_file(client, headers, inst_id, filename, content):
    return client.put(
        f"/api/instances/{inst_id}/hooks/files/{filename}",
        data={"file": (io.BytesIO(content), filename)},
        headers=headers,
        content_type="multipart/form-data",
    )


def test_replace_swaps_binary(client, headers, instance, tmp_path):
    _upload(client, headers, instance.id, "swap.so", b"\x7fELF" + b"v1")
    res = _put_file(client, headers, instance.id, "swap.so", b"\x7fELF" + b"v2new")
    assert res.status_code == 200
    contents = (tmp_path / "configs" / "hu" / str(instance.id) / "user-hooks" / "swap.so").read_bytes()
    assert contents == b"\x7fELF" + b"v2new"


def test_replace_404_when_missing(client, headers, instance):
    res = _put_file(client, headers, instance.id, "nope.so", b"\x7fELF")
    assert res.status_code == 404


def test_replace_rejects_non_elf(client, headers, instance):
    _upload(client, headers, instance.id, "swap2.so", b"\x7fELF")
    res = _put_file(client, headers, instance.id, "swap2.so", b"NOT")
    assert res.status_code == 400


# ── Download ─────────────────────────────────────────────────────────────────

def test_download_returns_so_bytes(client, headers, instance):
    _upload(client, headers, instance.id, "dl.so", b"\x7fELFCONTENT")
    res = client.get(f"/api/instances/{instance.id}/hooks/files/dl.so", headers=headers)
    assert res.status_code == 200
    assert res.data == b"\x7fELFCONTENT"
    assert "attachment" in res.headers.get("Content-Disposition", "").lower()


def test_download_404_when_missing(client, headers, instance):
    res = client.get(f"/api/instances/{instance.id}/hooks/files/gone.so", headers=headers)
    assert res.status_code == 404


# ── Rename ───────────────────────────────────────────────────────────────────

def _rename(client, headers, inst_id, filename, new_name):
    return client.patch(
        f"/api/instances/{inst_id}/hooks/files/{filename}",
        json={"new_name": new_name},
        headers=headers,
    )


def test_rename_moves_file(client, headers, instance, tmp_path):
    _upload(client, headers, instance.id, "old.so", b"\x7fELF" + b"a")
    res = _rename(client, headers, instance.id, "old.so", "new.so")
    assert res.status_code == 200
    base = tmp_path / "configs" / "hu" / str(instance.id) / "user-hooks"
    assert not (base / "old.so").exists()
    assert (base / "new.so").is_file()


def test_rename_cascades_ld_preload_hooks(app, client, headers, instance):
    _upload(client, headers, instance.id, "k.so", b"\x7fELF")
    with app.app_context():
        inst = db.session.get(QLInstance, instance.id)
        inst.ld_preload_hooks = "k.so"
        db.session.commit()

    res = _rename(client, headers, instance.id, "k.so", "k2.so")
    assert res.status_code == 200

    with app.app_context():
        inst = db.session.get(QLInstance, instance.id)
        assert inst.ld_preload_hooks == "k2.so"


def test_rename_cascades_binary_metadata(app, client, headers, instance):
    from ui.models import BinaryMetadata
    _upload(client, headers, instance.id, "m.so", b"\x7fELF")
    with app.app_context():
        db.session.add(BinaryMetadata(
            context_type="instance", context_key=str(instance.id),
            file_path="m.so", description="desc",
        ))
        db.session.commit()

    _rename(client, headers, instance.id, "m.so", "m2.so")
    with app.app_context():
        row = BinaryMetadata.query.filter_by(
            context_type="instance", context_key=str(instance.id), file_path="m2.so",
        ).first()
        assert row is not None and row.description == "desc"


def test_rename_rejects_collision(client, headers, instance):
    _upload(client, headers, instance.id, "x.so", b"\x7fELF")
    _upload(client, headers, instance.id, "y.so", b"\x7fELF")
    res = _rename(client, headers, instance.id, "x.so", "y.so")
    assert res.status_code == 409


def test_rename_rejects_reserved_name(client, headers, instance):
    _upload(client, headers, instance.id, "z.so", b"\x7fELF")
    res = _rename(client, headers, instance.id, "z.so", "force_rate.so")
    assert res.status_code == 400


# ── Delete ───────────────────────────────────────────────────────────────────

def _delete(client, headers, inst_id, filename):
    return client.delete(f"/api/instances/{inst_id}/hooks/files/{filename}", headers=headers)


def test_delete_removes_file(client, headers, instance, tmp_path):
    _upload(client, headers, instance.id, "d.so", b"\x7fELF")
    res = _delete(client, headers, instance.id, "d.so")
    assert res.status_code == 204
    assert not (tmp_path / "configs" / "hu" / str(instance.id) / "user-hooks" / "d.so").exists()


def test_delete_cascades_ld_preload_hooks(app, client, headers, instance):
    _upload(client, headers, instance.id, "rm.so", b"\x7fELF")
    with app.app_context():
        inst = db.session.get(QLInstance, instance.id)
        inst.ld_preload_hooks = "rm.so,keep.so"
        db.session.commit()

    _delete(client, headers, instance.id, "rm.so")

    with app.app_context():
        inst = db.session.get(QLInstance, instance.id)
        assert inst.ld_preload_hooks == "keep.so"


def test_delete_removes_binary_metadata(app, client, headers, instance):
    from ui.models import BinaryMetadata
    _upload(client, headers, instance.id, "mt.so", b"\x7fELF")
    with app.app_context():
        db.session.add(BinaryMetadata(
            context_type="instance", context_key=str(instance.id),
            file_path="mt.so", description="d",
        ))
        db.session.commit()

    _delete(client, headers, instance.id, "mt.so")
    with app.app_context():
        assert BinaryMetadata.query.filter_by(
            context_type="instance", context_key=str(instance.id), file_path="mt.so",
        ).first() is None


def test_delete_404_when_missing(client, headers, instance):
    res = _delete(client, headers, instance.id, "nope.so")
    assert res.status_code == 404


# ── Description ──────────────────────────────────────────────────────────────

def _set_desc(client, headers, inst_id, filename, description):
    return client.patch(
        f"/api/instances/{inst_id}/hooks/files/{filename}/description",
        json={"description": description},
        headers=headers,
    )


def test_description_creates_row(app, client, headers, instance):
    from ui.models import BinaryMetadata
    _upload(client, headers, instance.id, "dd.so", b"\x7fELF")
    res = _set_desc(client, headers, instance.id, "dd.so", "Speed mod")
    assert res.status_code == 200

    with app.app_context():
        row = BinaryMetadata.query.filter_by(
            context_type="instance", context_key=str(instance.id), file_path="dd.so",
        ).one()
        assert row.description == "Speed mod"


def test_description_updates_row(app, client, headers, instance):
    _upload(client, headers, instance.id, "du.so", b"\x7fELF")
    _set_desc(client, headers, instance.id, "du.so", "first")
    _set_desc(client, headers, instance.id, "du.so", "second")
    from ui.models import BinaryMetadata
    with app.app_context():
        row = BinaryMetadata.query.filter_by(
            context_type="instance", context_key=str(instance.id), file_path="du.so",
        ).one()
        assert row.description == "second"


def test_description_rejects_invalid_chars(client, headers, instance):
    _upload(client, headers, instance.id, "dx.so", b"\x7fELF")
    res = _set_desc(client, headers, instance.id, "dx.so", "<script>")
    assert res.status_code == 400


def test_description_404_when_file_missing(client, headers, instance):
    res = _set_desc(client, headers, instance.id, "ghost.so", "x")
    assert res.status_code == 404
