"""A preset records the runtime it was saved from, and keeps it across an
export/import round trip."""
import io
import json
import zipfile

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.database import create_preset
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
    """Defensive normalisation: a runtime that never got the column default
    still serialises as minqlx. Transient (never added to the session), so
    there is no expiry and no autoflush -- the in-memory None is read
    directly. SQLAlchemy applies column defaults at flush time, not at
    construction, so a transient preset's runtime is naturally None here.
    """
    with app.app_context():
        preset = ConfigPreset(name="old", path="configs/presets/old")
        assert preset.runtime is None
        assert preset.to_dict()["runtime"] == MINQLX


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


def test_create_preset_without_a_runtime_defaults_to_minqlx(app, client, auth_headers, tmp_path, monkeypatch):
    """The API-level counterpart to test_preset_defaults_to_minqlx: omitting
    'runtime' from the create payload entirely (not just constructing the
    ORM object directly) must land on minqlx."""
    import ui.routes.preset_api_routes as mod
    monkeypatch.setattr(mod, "PRESETS_DIR", str(tmp_path / "presets"), raising=False)

    response = client.post("/api/presets/",
                           json={"name": "no-runtime-given", "description": "d"},
                           headers=auth_headers)
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["runtime"] == MINQLX


def test_overwrite_with_an_explicit_runtime_restamps_the_preset(
    app, client, auth_headers, tmp_path, monkeypatch
):
    """A minqlx preset overwritten with content saved from a minqlxtended
    host must pick up the new runtime, not keep claiming minqlx for content
    that no longer matches."""
    import ui.routes.preset_api_routes as mod
    presets_dir = tmp_path / "presets"
    monkeypatch.setattr(mod, "PRESETS_DIR", str(presets_dir), raising=False)

    with app.app_context():
        preset_path = presets_dir / "overwrite-me"
        preset_path.mkdir(parents=True)
        preset = create_preset(
            name="overwrite-me", description="", path=str(preset_path), runtime=MINQLX
        )
        preset_id = preset.id

    response = client.put(
        f"/api/presets/{preset_id}",
        json={"description": "updated", "runtime": "minqlxtended"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["runtime"] == MINQLXTENDED

    with app.app_context():
        assert db.session.get(ConfigPreset, preset_id).runtime == MINQLXTENDED


def test_update_without_a_runtime_key_leaves_an_existing_minqlxtended_preset_alone(
    app, client, auth_headers, tmp_path, monkeypatch
):
    """The regression guard: update_preset_api also serves plain rename and
    description edits from the preset manager, which have no originating
    host and send no 'runtime' key at all. An absent runtime must NOT be
    defaulted to minqlx the way create's does -- that would silently
    downgrade every minqlxtended preset the first time someone tweaks its
    description."""
    import ui.routes.preset_api_routes as mod
    presets_dir = tmp_path / "presets"
    monkeypatch.setattr(mod, "PRESETS_DIR", str(presets_dir), raising=False)

    with app.app_context():
        preset_path = presets_dir / "stay-tended"
        preset_path.mkdir(parents=True)
        preset = create_preset(
            name="stay-tended", description="old", path=str(preset_path),
            runtime=MINQLXTENDED,
        )
        preset_id = preset.id

    response = client.put(
        f"/api/presets/{preset_id}",
        json={"description": "new desc"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["runtime"] == MINQLXTENDED

    with app.app_context():
        assert db.session.get(ConfigPreset, preset_id).runtime == MINQLXTENDED


def test_update_rejects_an_unknown_runtime_and_does_not_mutate_the_row(
    app, client, auth_headers, tmp_path, monkeypatch
):
    import ui.routes.preset_api_routes as mod
    presets_dir = tmp_path / "presets"
    monkeypatch.setattr(mod, "PRESETS_DIR", str(presets_dir), raising=False)

    with app.app_context():
        preset_path = presets_dir / "bad-update"
        preset_path.mkdir(parents=True)
        preset = create_preset(
            name="bad-update", description="old", path=str(preset_path), runtime=MINQLX
        )
        preset_id = preset.id

    response = client.put(
        f"/api/presets/{preset_id}",
        json={"description": "new desc", "runtime": "minqlx3"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "runtime" in response.get_json()["error"]["message"].lower()

    with app.app_context():
        preset = db.session.get(ConfigPreset, preset_id)
        assert preset.runtime == MINQLX
        assert preset.description == "old"  # validated before any mutation


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
        # Transient (never added to the session): the column default applies
        # at flush time, not construction, so runtime is naturally None here
        # -- exercising the normalisation honestly, with no expiry/autoflush
        # involved.
        preset = ConfigPreset(name="legacy-export", path="configs/presets/legacy-export")
        assert preset.runtime is None
        manifest = _preset_export_manifest(preset, 0)

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
