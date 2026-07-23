"""Structural checks that Global RCON docs and version sources stay in sync.

Assertions stay structural on purpose: canonical event names, navigation
entries, the forbidden global command channel, and cross-file version
equality. Prose wording is reviewed by humans, not frozen here.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FLEET_EVENTS = (
    'rcon:fleet_join',
    'rcon:fleet_targets',
    'rcon:fleet_command',
    'rcon:fleet_leave',
)


def read(relative_path):
    return (ROOT / relative_path).read_text()


def test_versions_stay_synchronized():
    version_file = read('VERSION').strip()
    manifest = json.loads(read('docs/user/version.json'))
    assert version_file == manifest['latest']
    assert f'`v{version_file}`' in read('docs/user/releases.md')


def test_api_reference_documents_fleet_events():
    api_reference = read('docs/api_reference.md')
    for event in FLEET_EVENTS:
        assert event in api_reference
    # Fan-out is per instance; there is no single global command channel.
    assert 'rcon:cmd:global' not in api_reference


def test_user_docs_cover_the_global_rcon_page():
    user_doc = read('docs/user/operations/global-rcon.md')
    assert '/global-rcon' in user_doc
    assert 'Global RCON' in read('mkdocs.yml')
    assert 'operations/global-rcon.md' in read('mkdocs.yml')
    assert 'Global RCON' in read('docs/user/index.md')
    # The individual console page must point at the fleet page and back.
    assert 'global-rcon.md' in read('docs/user/operations/rcon-console.md')
    assert 'rcon-console.md' in user_doc
