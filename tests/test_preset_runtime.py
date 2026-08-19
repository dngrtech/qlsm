"""A preset records the runtime it was saved from, and keeps it across an
export/import round trip."""
import io
import json
import zipfile

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import ConfigPreset
from ui.runtime import MINQLX, MINQLXTENDED


@pytest.fixture
def auth_headers(app):
    with app.app_context():
        return {"Authorization": f"Bearer {create_access_token(identity='testuser')}"}


def test_preset_defaults_to_minqlx(app):
    with app.app_context():
        preset = ConfigPreset(name="legacy", path="configs/presets/legacy")
        db.session.add(preset)
        db.session.commit()
        assert preset.runtime == MINQLX
        assert preset.to_dict()["runtime"] == MINQLX


def test_preset_stores_and_serialises_minqlxtended(app):
    with app.app_context():
        preset = ConfigPreset(name="tended", path="configs/presets/tended",
                              runtime=MINQLXTENDED)
        db.session.add(preset)
        db.session.commit()
        assert preset.to_dict()["runtime"] == MINQLXTENDED


def test_null_preset_runtime_reads_as_minqlx(app):
    """An old export has no runtime recorded, and nothing but minqlx existed.

    Note: no flush() here. The column is NOT NULL, so flushing a None raises
    IntegrityError. ConfigPreset.to_dict() does not call db.session.refresh(),
    unlike Host.to_dict(), so the in-memory None is read directly -- which is
    exactly the normalisation path under test.
    """
    with app.app_context():
        preset = ConfigPreset(name="old", path="configs/presets/old")
        db.session.add(preset)
        db.session.commit()

        preset.runtime = None
        assert preset.to_dict()["runtime"] == MINQLX
        db.session.rollback()  # discard the dirty in-memory None


def test_create_preset_records_the_runtime(app, client, auth_headers, tmp_path, monkeypatch):
    import ui.routes.preset_api_routes as mod
    monkeypatch.setattr(mod, "PRESETS_DIR", str(tmp_path / "presets"), raising=False)

    response = client.post("/api/presets/",
                           json={"name": "saved-from-tended", "description": "d",
                                 "runtime": "minqlxtended"},
                           headers=auth_headers)
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["runtime"] == MINQLXTENDED


def test_create_preset_rejects_an_unknown_runtime(app, client, auth_headers, tmp_path, monkeypatch):
    import ui.routes.preset_api_routes as mod
    monkeypatch.setattr(mod, "PRESETS_DIR", str(tmp_path / "presets"), raising=False)

    response = client.post("/api/presets/",
                           json={"name": "bad-runtime", "runtime": "minqlx3"},
                           headers=auth_headers)
    assert response.status_code == 400
    assert "runtime" in response.get_json()["error"]["message"].lower()


def test_export_manifest_carries_the_runtime(app):
    from ui.routes.preset_api_routes import _preset_export_manifest

    with app.app_context():
        preset = ConfigPreset(name="exported", path="configs/presets/exported",
                              runtime=MINQLXTENDED)
        db.session.add(preset)
        db.session.commit()
        manifest = _preset_export_manifest(preset, 0)

    assert manifest["preset"]["runtime"] == MINQLXTENDED


def test_export_manifest_of_a_legacy_preset_says_minqlx(app):
    from ui.routes.preset_api_routes import _preset_export_manifest

    with app.app_context():
        preset = ConfigPreset(name="legacy-export", path="configs/presets/legacy-export")
        db.session.add(preset)
        db.session.commit()

        # No flush() -- the column is NOT NULL. _preset_export_manifest reads
        # preset.runtime directly, so the in-memory None exercises the
        # normalisation honestly.
        preset.runtime = None
        manifest = _preset_export_manifest(preset, 0)
        db.session.rollback()

    assert manifest["preset"]["runtime"] == MINQLX


def test_backup_round_trip_preserves_preset_runtime(app):
    from ui.task_logic.backup_db_export import _preset_row

    with app.app_context():
        preset = ConfigPreset(name="backup-me", path="configs/presets/backup-me",
                              runtime=MINQLXTENDED)
        db.session.add(preset)
        db.session.commit()
        assert _preset_row(preset)["runtime"] == MINQLXTENDED


def test_builtin_preset_manifest_runtime_defaults_to_minqlx(tmp_path):
    """Every _builtin preset that exists today is a minqlx preset."""
    from ui.builtin_presets import _load_manifest

    preset_dir = tmp_path / "default"
    preset_dir.mkdir()
    (preset_dir / "preset.json").write_text(json.dumps({
        "description": "A preset", "builtin": True,
    }))
    assert _load_manifest(str(preset_dir))["runtime"] == MINQLX


def test_builtin_preset_manifest_accepts_an_explicit_runtime(tmp_path):
    from ui.builtin_presets import _load_manifest

    preset_dir = tmp_path / "default-minqlxtended"
    preset_dir.mkdir()
    (preset_dir / "preset.json").write_text(json.dumps({
        "description": "A preset", "builtin": True, "runtime": "minqlxtended",
    }))
    assert _load_manifest(str(preset_dir))["runtime"] == MINQLXTENDED


def test_builtin_preset_manifest_rejects_a_bad_runtime(tmp_path):
    from ui.builtin_presets import BuiltinPresetError, _load_manifest

    preset_dir = tmp_path / "broken"
    preset_dir.mkdir()
    (preset_dir / "preset.json").write_text(json.dumps({
        "description": "A preset", "builtin": True, "runtime": "nope",
    }))
    with pytest.raises(BuiltinPresetError):
        _load_manifest(str(preset_dir))
