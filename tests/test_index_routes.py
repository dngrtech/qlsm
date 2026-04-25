from ui import db
from ui.models import ConfigPreset


def test_default_config_route_uses_builtin_default_db_path(client, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    builtin_dir = tmp_path / 'configs' / 'presets' / '_builtin' / 'default'
    builtin_dir.mkdir(parents=True)
    (builtin_dir / 'server.cfg').write_text('set sv_hostname "builtin"\n')

    with app.app_context():
        db.session.add(ConfigPreset(
            name='default',
            description='Default',
            path='configs/presets/_builtin/default',
            is_builtin=True,
        ))
        db.session.commit()

    response = client.get('/api/default-config/server.cfg')

    assert response.status_code == 200
    assert response.text == 'set sv_hostname "builtin"\n'


def test_default_config_route_rejects_path_traversal(client, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    builtin_dir = tmp_path / 'configs' / 'presets' / '_builtin' / 'default'
    builtin_dir.mkdir(parents=True)
    (tmp_path / 'secret.txt').write_text('secret')

    with app.app_context():
        db.session.add(ConfigPreset(
            name='default',
            description='Default',
            path='configs/presets/_builtin/default',
            is_builtin=True,
        ))
        db.session.commit()

    response = client.get('/api/default-config/../../../../secret.txt')

    assert response.status_code == 404
