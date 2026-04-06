import importlib.util
import sys
import types
import zipfile
from pathlib import Path

import pytest


def _load_serverchecker_module(monkeypatch):
    fake_minqlx = types.SimpleNamespace(Plugin=type('Plugin', (), {}))
    monkeypatch.setitem(sys.modules, 'minqlx', fake_minqlx)

    module_path = (
        Path(__file__).resolve().parents[1]
        / 'ql-assets'
        / 'data'
        / 'minqlx-plugins'
        / 'serverchecker.py'
    )
    spec = importlib.util.spec_from_file_location('serverchecker_under_test', module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_map_pk3(item_dir, pk3_name, map_names):
    item_dir.mkdir(parents=True, exist_ok=True)
    pk3_path = item_dir / pk3_name
    with zipfile.ZipFile(pk3_path, mode='w') as archive:
        for map_name in map_names:
            archive.writestr(f'maps/{map_name}.bsp', b'')
    return pk3_path


@pytest.mark.usefixtures('monkeypatch')
def test_resolve_workshop_item_finds_map_in_first_matching_item(tmp_path, monkeypatch):
    module = _load_serverchecker_module(monkeypatch)
    base_path = tmp_path / 'qlds-27960'
    _write_map_pk3(
        base_path / 'steamapps' / 'workshop' / 'content' / '282440' / '123',
        'uprise.pk3',
        ['uprise'],
    )

    resolved = module._resolve_map_workshop_item('uprise', ['123'], str(base_path))

    assert resolved == '123'


@pytest.mark.usefixtures('monkeypatch')
def test_resolve_workshop_item_returns_none_when_no_match(tmp_path, monkeypatch):
    module = _load_serverchecker_module(monkeypatch)
    base_path = tmp_path / 'qlds-27960'
    _write_map_pk3(
        base_path / 'steamapps' / 'workshop' / 'content' / '282440' / '123',
        'other.pk3',
        ['campgrounds'],
    )

    resolved = module._resolve_map_workshop_item('uprise', ['123'], str(base_path))

    assert resolved is None


@pytest.mark.usefixtures('monkeypatch')
def test_resolve_workshop_item_prefers_first_match_when_ambiguous(tmp_path, monkeypatch):
    module = _load_serverchecker_module(monkeypatch)
    base_path = tmp_path / 'qlds-27960'
    _write_map_pk3(
        base_path / 'steamapps' / 'workshop' / 'content' / '282440' / '111',
        'first.pk3',
        ['uprise'],
    )
    _write_map_pk3(
        base_path / 'steamapps' / 'workshop' / 'content' / '282440' / '222',
        'second.pk3',
        ['uprise'],
    )

    resolved = module._resolve_map_workshop_item('uprise', ['222', '111'], str(base_path))

    assert resolved == '222'
