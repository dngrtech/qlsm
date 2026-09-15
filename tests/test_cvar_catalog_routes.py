"""Tests for the cvar catalog endpoint and the catalog data behind it."""

import json
import os
import subprocess
import sys

import pytest
from flask_jwt_extended import create_access_token

from ui.routes.cvar_catalog_routes import CATALOG_PATH

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity='testuser')
    return {'Authorization': f'Bearer {token}'}


class TestCvarCatalogEndpoint:
    def test_requires_auth(self, client):
        assert client.get('/api/cvar-catalog').status_code == 401

    def test_returns_catalog(self, client, auth_headers):
        response = client.get('/api/cvar-catalog', headers=auth_headers)
        assert response.status_code == 200
        payload = response.get_json()['data']
        names = {entry['name'] for entry in payload['cvars']}
        # the settings the old hand-typed list was missing
        assert {'g_respawn_delay_min', 'g_respawn_delay_max', 'g_startingWeapons',
                'g_spawnItemWeapons', 'dmflags', 'timelimit'} <= names
        assert len(names) > 400
        assert any(cmd['name'] == 'reload_mappool' for cmd in payload['commands'])

    def test_every_entry_says_where_it_came_from(self, client, auth_headers):
        payload = client.get('/api/cvar-catalog', headers=auth_headers).get_json()['data']
        known_sources = set(payload['sources'])
        for entry in payload['cvars']:
            assert entry['source'] in known_sources, entry
            # a description is only allowed to claim a source other than the
            # bare dump when there actually is one
            if entry['source'] == 'listcvars':
                assert entry['description'] is None, entry

    def test_no_plugin_cvars_in_the_engine_catalog(self, client, auth_headers):
        """qlx_* belongs to the plugins a server actually runs, so it must come
        from the plugin manifests instead of a baked-in list."""
        payload = client.get('/api/cvar-catalog', headers=auth_headers).get_json()['data']
        assert not [c for c in payload['cvars'] if c['name'].lower().startswith('qlx_')]

    def test_weapon_bitmask_table_is_served(self, client, auth_headers):
        payload = client.get('/api/cvar-catalog', headers=auth_headers).get_json()['data']
        starting = next(c for c in payload['cvars'] if c['name'] == 'g_startingWeapons')
        bits = dict((value, label) for value, label in starting['bitmask']['bits'])
        assert bits[8192] == 'Heavy Machine Gun'
        assert bits[64] == 'Railgun'

    def test_etag_allows_a_cheap_revalidation(self, client, auth_headers):
        first = client.get('/api/cvar-catalog', headers=auth_headers)
        etag = first.headers['ETag']
        again = client.get('/api/cvar-catalog', headers={**auth_headers, 'If-None-Match': etag})
        assert again.status_code == 304


class TestCatalogData:
    def test_catalog_matches_its_generator(self):
        """The committed catalog must be what scripts/gen_cvar_catalog.py
        produces from the committed inputs -- otherwise a hand edit silently
        becomes a second source of truth again."""
        result = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, 'scripts', 'gen_cvar_catalog.py'), '--check'],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_catalog_is_valid_json_with_a_version(self):
        with open(CATALOG_PATH, encoding='utf-8') as handle:
            payload = json.load(handle)
        assert payload['version'] >= 1
        assert payload['groups']
