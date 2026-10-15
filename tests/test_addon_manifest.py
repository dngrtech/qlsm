"""Manifest validation: what loads, what is rejected, and why."""
import json

import pytest

from ui.addons.manifest import CURRENT_UI_API, read_manifest, validate_manifest


def _minimal(**overrides):
    data = {'id': 'sample-addon', 'version': '1.0.0'}
    data.update(overrides)
    return data


def test_minimal_manifest_is_valid():
    manifest, errors = validate_manifest(_minimal())
    assert errors == []
    assert manifest['id'] == 'sample-addon'
    assert manifest['scopes'] == ['global']
    assert manifest['ui_api'] == CURRENT_UI_API


@pytest.mark.parametrize('bad_id', [
    'Sample',           # uppercase
    'sample_addon',     # underscore
    'sample--addon',    # double dash
    '-sample',          # leading dash
    'sample-',          # trailing dash
    '',
])
def test_id_must_be_kebab_case(bad_id):
    _, errors = validate_manifest(_minimal(id=bad_id))
    assert errors, f'expected {bad_id!r} to be rejected'


def test_version_is_required():
    _, errors = validate_manifest({'id': 'sample-addon'})
    assert any('version' in e for e in errors)


def test_scopes_are_canonically_ordered_and_deduped():
    manifest, errors = validate_manifest(
        _minimal(scopes=['instance', 'global', 'instance', 'host'])
    )
    assert errors == []
    assert manifest['scopes'] == ['global', 'host', 'instance']


def test_unknown_scope_is_rejected():
    _, errors = validate_manifest(_minimal(scopes=['galaxy']))
    assert any('galaxy' in e for e in errors)


def test_settings_field_type_must_be_known():
    _, errors = validate_manifest(_minimal(settings={
        'host': [{'key': 'url', 'type': 'urlish'}],
    }))
    assert any('type must be one of' in e for e in errors)


def test_min_max_only_apply_to_numbers():
    _, errors = validate_manifest(_minimal(settings={
        'host': [{'key': 'name', 'type': 'string', 'min': 1}],
    }))
    assert any('only applies to type "number"' in e for e in errors)


def test_duplicate_setting_keys_are_rejected():
    _, errors = validate_manifest(_minimal(settings={
        'host': [
            {'key': 'url', 'type': 'string'},
            {'key': 'url', 'type': 'string'},
        ],
    }))
    assert any('duplicate field key' in e for e in errors)


def test_panel_route_may_not_be_absolute():
    """A panel pointing at a core endpoint is the whole thing this prevents."""
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form', 'load': 'GET /api/hosts'}},
    }))
    assert any('must be relative to the addon prefix' in e for e in errors)


def test_panel_route_may_not_be_external_url():
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form', 'load': 'GET https://evil.example/steal'}},
    }))
    assert any('must be relative' in e for e in errors)


def test_relative_panel_route_is_accepted():
    manifest, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form', 'load': 'GET hosts/{host_id}'}},
        'host_menu': [{'id': 'relay', 'label': 'Relay', 'panel': 'p'}],
    }))
    assert errors == []
    assert manifest['ui']['host_menu'][0]['panel'] == 'p'


def test_menu_entry_must_reference_a_declared_panel():
    _, errors = validate_manifest(_minimal(ui={
        'panels': {},
        'host_menu': [{'id': 'relay', 'panel': 'nope'}],
    }))
    assert any('not declared in ui.panels' in e for e in errors)


def test_menu_entry_needs_panel_or_component():
    _, errors = validate_manifest(_minimal(ui={'host_menu': [{'id': 'relay'}]}))
    assert any('needs either "panel" or "component"' in e for e in errors)


def test_menu_entry_cannot_have_both():
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form'}},
        'host_menu': [{'id': 'relay', 'panel': 'p', 'component': 'ui/x.js'}],
    }))
    assert any('pick one' in e for e in errors)


@pytest.mark.parametrize('component', ['/etc/passwd', '../../backend.py', 'a/../../b.js'])
def test_component_path_may_not_escape_the_addon(component):
    _, errors = validate_manifest(_minimal(ui={
        'host_menu': [{'id': 'relay', 'component': component}],
    }))
    assert any('must stay inside the addon' in e for e in errors)


def test_unknown_panel_kind_is_rejected():
    _, errors = validate_manifest(_minimal(ui={'panels': {'p': {'kind': 'hologram'}}}))
    assert any('kind must be one of' in e for e in errors)


def test_read_manifest_reports_missing_file(tmp_path):
    manifest, errors = read_manifest(str(tmp_path))
    assert manifest is None
    assert any('not found' in e for e in errors)


def test_read_manifest_reports_bad_json(tmp_path):
    (tmp_path / 'qlsm-addon.json').write_text('{not json', encoding='utf-8')
    manifest, errors = read_manifest(str(tmp_path))
    assert manifest is None
    assert any('could not be read' in e for e in errors)


def test_read_manifest_round_trip(tmp_path):
    (tmp_path / 'qlsm-addon.json').write_text(
        json.dumps(_minimal(name='Sample Addon')), encoding='utf-8'
    )
    manifest, errors = read_manifest(str(tmp_path))
    assert errors == []
    assert manifest['name'] == 'Sample Addon'


# ---- render mode ------------------------------------------------------

def test_a_component_entry_may_render_its_own_modal():
    manifest, errors = validate_manifest(_minimal(ui={
        'host_menu': [{'id': 'relay', 'component': 'ui/Panel.js', 'renders': 'modal'}],
    }))
    assert errors == []
    assert manifest['ui']['host_menu'][0]['renders'] == 'modal'


def test_render_mode_must_be_known():
    _, errors = validate_manifest(_minimal(ui={
        'host_menu': [{'id': 'relay', 'component': 'ui/Panel.js', 'renders': 'hologram'}],
    }))
    assert any('"renders" must be one of' in e for e in errors)


def test_modal_render_mode_requires_a_component():
    """A declarative panel cannot be the whole dialog -- it has no shell."""
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form'}},
        'host_menu': [{'id': 'relay', 'panel': 'p', 'renders': 'modal'}],
    }))
    assert any('needs a component' in e for e in errors)


def test_panel_render_mode_is_fine_with_a_panel():
    manifest, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form'}},
        'host_menu': [{'id': 'relay', 'panel': 'p', 'renders': 'panel'}],
    }))
    assert errors == []


# ---- select option icons -----------------------------------------------

def test_select_option_icon_url_is_accepted():
    manifest, errors = validate_manifest(_minimal(settings={
        'instance': [{
            'key': 'provider', 'type': 'select',
            'options': [{'value': 'qlstats', 'label': 'qlstats', 'icon_url': 'logos/qlstats.svg'}],
        }],
    }))
    assert errors == []
    assert manifest['settings']['instance'][0]['options'][0]['icon_url'] == 'logos/qlstats.svg'


def test_select_option_icon_and_icon_url_are_mutually_exclusive():
    _, errors = validate_manifest(_minimal(settings={
        'instance': [{
            'key': 'provider', 'type': 'select',
            'options': [{'value': 'qlstats', 'icon': 'gauge', 'icon_url': 'logos/qlstats.svg'}],
        }],
    }))
    assert any('mutually exclusive' in e for e in errors)


@pytest.mark.parametrize('icon_url', ['/etc/passwd', '../../backend.py', 'a/../../b.svg'])
def test_select_option_icon_url_may_not_escape_the_addon(icon_url):
    _, errors = validate_manifest(_minimal(settings={
        'instance': [{
            'key': 'provider', 'type': 'select',
            'options': [{'value': 'qlstats', 'icon_url': icon_url}],
        }],
    }))
    assert any('must stay inside the addon' in e for e in errors)


# ---- live_status_columns -------------------------------------------------

def _column(**overrides):
    col = {'id': 'rating', 'label': 'Rating', 'route': 'GET instances/{instance_id}/ranks'}
    col.update(overrides)
    return col


def test_live_status_column_is_accepted():
    manifest, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column()]}))
    assert errors == []
    assert manifest['ui']['live_status_columns'][0]['id'] == 'rating'


def test_live_status_column_requires_id():
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(id='')]}))
    assert any('missing "id"' in e for e in errors)


def test_live_status_column_requires_label():
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(label='')]}))
    assert any('"label" is required' in e for e in errors)


def test_live_status_column_label_has_a_length_cap():
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(label='x' * 25)]}))
    assert any('at most 24 characters' in e for e in errors)


def test_live_status_column_align_must_be_known():
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(align='center')]}))
    assert any('"align" must be one of' in e for e in errors)


def test_live_status_column_route_must_be_get():
    _, errors = validate_manifest(_minimal(ui={
        'live_status_columns': [_column(route='POST instances/{instance_id}/ranks')],
    }))
    assert any('must be a GET route' in e for e in errors)


def test_live_status_column_route_may_not_be_absolute():
    _, errors = validate_manifest(_minimal(ui={
        'live_status_columns': [_column(route='GET /api/hosts')],
    }))
    assert any('must be relative to the addon prefix' in e for e in errors)


def test_live_status_column_duplicate_id_is_rejected():
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(), _column()]}))
    assert any('duplicate column id' in e for e in errors)


def test_live_status_column_icon_and_icon_url_are_mutually_exclusive():
    _, errors = validate_manifest(_minimal(ui={
        'live_status_columns': [_column(icon='gauge', icon_url='logos/qlstats.svg')],
    }))
    assert any('mutually exclusive' in e for e in errors)


def test_addon_level_icon_url_is_accepted():
    manifest, errors = validate_manifest(_minimal(ui={'icon_url': 'logos/player-ranks.svg'}))
    assert errors == []
    assert manifest['ui']['icon_url'] == 'logos/player-ranks.svg'


def test_addon_level_icon_and_icon_url_are_mutually_exclusive():
    _, errors = validate_manifest(_minimal(ui={'icon': 'gauge', 'icon_url': 'logos/player-ranks.svg'}))
    assert any('mutually exclusive' in e for e in errors)


def test_live_status_columns_must_be_a_list():
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': {'id': 'rating'}}))
    assert any('must be a list' in e for e in errors)


@pytest.mark.parametrize('entry', ['rating', 42, None, ['rating']])
def test_live_status_column_entry_must_be_an_object(entry):
    """A non-object entry used to raise TypeError out of validate_manifest()
    (the duplicate-id check fed it an unhashable value), and since the registry
    reads manifests inside create_app(), that took qlsm's startup down over one
    malformed third-party addon."""
    manifest, errors = validate_manifest(_minimal(ui={'live_status_columns': [entry]}))
    assert any('entry must be an object' in e for e in errors)
    # and exactly one error: no bogus duplicate-id noise on top of it
    assert not any('duplicate column id' in e for e in errors)


def test_live_status_columns_missing_ids_do_not_report_a_duplicate():
    _, errors = validate_manifest(_minimal(ui={
        'live_status_columns': [_column(id=''), _column(id='')],
    }))
    assert not any('duplicate column id' in e for e in errors)


@pytest.mark.parametrize('icon_url', [r'..\backend.py', r'\etc\passwd', r'a\..\..\b.svg'])
def test_icon_url_backslash_traversal_is_refused(icon_url):
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(icon_url=icon_url)]}))
    assert any('must stay inside the addon' in e for e in errors)


@pytest.mark.parametrize('icon_url', ['backend.py', 'logo.gif', 'logo'])
def test_icon_url_must_be_a_servable_image(icon_url):
    """The asset route only serves .svg/.png/.webp, so anything else is a
    broken image the operator cannot explain -- reject it at install time."""
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(icon_url=icon_url)]}))
    assert any('"icon_url" must be one of' in e for e in errors)


def test_component_backslash_traversal_is_refused():
    _, errors = validate_manifest(_minimal(ui={
        'page': {'id': 'p', 'component': r'..\..\backend.py'},
    }))
    assert any('must stay inside the addon' in e for e in errors)

# ---- a declarative route may not leave the addon's own API prefix --------

@pytest.mark.parametrize('path', ['../../hosts', 'a/../../../hosts', '%2e%2e/%2e%2e/hosts', r'..\..\hosts', './hosts', 'a//hosts'])
def test_live_status_column_route_may_not_escape_the_addon_prefix(path):
    """The frontend builds the URL as /api/addons/<id>/<path> and nothing
    downstream re-checks it, so `../../hosts` resolves to /api/hosts in the
    browser with the operator's cookie attached. `%2e%2e` and `..%5c` are the
    same `..` segment to a URL parser, and `?`/`#` detach the rest of the
    path (and swallow the ?steam_ids= core appends)."""
    _, errors = validate_manifest(_minimal(ui={
        'live_status_columns': [_column(route=f'GET {path}')],
    }))
    assert any('must stay inside the addon prefix' in e for e in errors), errors


@pytest.mark.parametrize('path', ['../../hosts', 'a/../../../hosts', '%2e%2e/%2e%2e/hosts', r'..\..\hosts', './hosts', 'a//hosts'])
def test_panel_load_route_may_not_escape_the_addon_prefix(path):
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form', 'load': f'GET {path}'}},
    }))
    assert any('must stay inside the addon prefix' in e for e in errors), errors


@pytest.mark.parametrize('path', ['../../hosts', 'a/../../../hosts', '%2e%2e/%2e%2e/hosts', r'..\..\hosts', './hosts', 'a//hosts'])
def test_panel_submit_route_may_not_escape_the_addon_prefix(path):
    """submit carries a verb, so the same escape reached mutating core calls."""
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form', 'submit': f'POST {path}'}},
    }))
    assert any('must stay inside the addon prefix' in e for e in errors), errors


@pytest.mark.parametrize('route', [
    'GET instances/{instance_id}/ranks',
    'instances/{instance_id}/ranks',
    'GET items/',
    'GET a/b/c',
])
def test_an_ordinary_relative_route_is_still_accepted(route):
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(route=route)]}))
    assert errors == []


@pytest.mark.parametrize('icon_url', ['%2e%2e/x.svg', '..%2fx.svg', '%2e/x.svg'])
def test_percent_encoded_traversal_in_icon_url_is_refused(icon_url):
    """`%2e%2e` is a `..` segment as far as the URL parser is concerned, so a
    `..`-only check let it through to another addon's ui/ directory."""
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(icon_url=icon_url)]}))
    assert any('must stay inside the addon' in e for e in errors), errors


@pytest.mark.parametrize('component', ['%2e%2e/Panel.js', 'a/../../backend.py', './Panel.js'])
def test_percent_encoded_traversal_in_a_component_path_is_refused(component):
    _, errors = validate_manifest(_minimal(ui={'page': {'id': 'p', 'component': component}}))
    assert any('must stay inside the addon' in e for e in errors), errors

@pytest.mark.parametrize('path', ['hosts#f', 'hosts?a=1#f'])
def test_a_route_may_not_carry_a_fragment(path):
    """A fragment never reaches the server and silently truncates the path."""
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form', 'load': f'GET {path}'}},
    }))
    assert any('fragment' in e for e in errors), errors


def test_a_panel_route_may_carry_a_query_string():
    """The bundled hello-addon declares GET files?instance_id={instance_id};
    a URL parser does not collapse dot segments inside a query, so only the
    path in front of the "?" is subject to the escape rules."""
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'table', 'load': 'GET files?instance_id={instance_id}'}},
    }))
    assert errors == []


def test_a_query_string_does_not_excuse_an_escaping_path():
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form', 'load': 'GET ../../hosts?a=1'}},
    }))
    assert any('must stay inside the addon prefix' in e for e in errors), errors


def test_a_live_status_column_route_may_not_carry_a_query_string():
    """Core appends its own ?steam_ids=, so a declared "?" swallows it."""
    _, errors = validate_manifest(_minimal(ui={
        'live_status_columns': [_column(route='GET ranks?scope=all')],
    }))
    assert any('core appends its own' in e for e in errors), errors


# ---- control/whitespace characters hide a dot segment from the parser ----

@pytest.mark.parametrize('path', ['.\t./.\t./hosts', '..\r/hosts', '..\n/hosts', '.. /hosts'])
def test_control_characters_in_a_route_are_refused(path):
    """A URL parser strips tabs/CR/LF/space before looking at dot segments,
    so ".\\t." reaches it as "..": reject the raw characters instead of
    trying to out-guess every parser's idea of whitespace."""
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form', 'load': f'GET {path}'}},
    }))
    assert any('must stay inside the addon prefix' in e or 'must not contain whitespace' in e
               for e in errors), errors


@pytest.mark.parametrize('icon_url', ['.\t./.\t./x.svg', 'a\r/../b.svg'])
def test_control_characters_in_an_icon_url_are_refused(icon_url):
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(icon_url=icon_url)]}))
    assert any('must stay inside the addon' in e for e in errors), errors


# ---- route declarations beyond panel load/submit must validate too ------

def test_status_load_route_may_not_escape_the_addon_prefix():
    """A managed form's status.load bypassed _validate_relative_route
    entirely -- only load/submit were ever checked."""
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form', 'status': {'load': 'GET ../../hosts'}}},
    }))
    assert any('must stay inside the addon prefix' in e for e in errors), errors


def test_row_action_route_may_not_escape_the_addon_prefix():
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {
            'kind': 'table',
            'load': 'GET files',
            'row_actions': [{'id': 'dl', 'label': 'Download', 'route': 'GET ../../hosts'}],
        }},
    }))
    assert any('must stay inside the addon prefix' in e for e in errors), errors


def test_bulk_action_route_may_not_escape_the_addon_prefix():
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {
            'kind': 'table',
            'load': 'GET files',
            'bulk_actions': [{'id': 'dl', 'label': 'Download selected', 'route': 'POST ../../hosts'}],
        }},
    }))
    assert any('must stay inside the addon prefix' in e for e in errors), errors


def test_row_action_route_may_not_be_absolute():
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {
            'kind': 'table',
            'load': 'GET files',
            'row_actions': [{'id': 'dl', 'label': 'Download', 'route': 'GET /api/hosts'}],
        }},
    }))
    assert any('must be relative to the addon prefix' in e for e in errors), errors


def test_status_load_and_actions_still_accept_ordinary_routes():
    manifest, errors = validate_manifest(_minimal(ui={
        'panels': {
            'managed': {'kind': 'form', 'status': {'load': 'GET status'}},
            'files_table': {
                'kind': 'table',
                'load': 'GET files?instance_id={instance_id}',
                'row_actions': [{'id': 'dl', 'label': 'Download', 'route': 'GET files/download?filename={name}'}],
                'bulk_actions': [{'id': 'dlb', 'label': 'Download selected', 'route': 'POST files/download-batch'}],
            },
        },
    }))
    assert errors == []
    assert manifest['ui']['panels']['files_table']['row_actions'][0]['route'] == 'GET files/download?filename={name}'


# ---- the verb/path split must agree with the frontend's parseRoute -------

_SPLIT_ESCAPES = [
    'DELETE ../../hosts/1?_= x',   # NBSP is the frontend's separator, the space hid the path
    '../../hosts/1?_= x',               # no verb: the whole string is the path
    'DELETE ../other-addon',
    'POST ../install',
    'PUT　../other/state',
    'DELETE﻿../other-addon',
    'PUT ../../hosts/1 x',
]


@pytest.mark.parametrize('route', _SPLIT_ESCAPES)
def test_panel_route_split_matches_the_frontend(route):
    """The frontend splits `METHOD path` on the verb list, and anything else is
    a GET path. Validating only the text after the first space let a route
    whose real path came before it through unchecked."""
    for panel in (
        {'kind': 'form', 'load': route},
        {'kind': 'form', 'submit': route},
        {'kind': 'form', 'status': {'load': route}},
        {'kind': 'table', 'row_actions': [{'id': 'a', 'label': 'A', 'route': route}]},
        {'kind': 'table', 'bulk_actions': [{'id': 'a', 'label': 'A', 'route': route}]},
    ):
        _, errors = validate_manifest(_minimal(ui={'panels': {'p': panel}}))
        assert errors, panel


@pytest.mark.parametrize('route', _SPLIT_ESCAPES + ['FOO instances/{instance_id}/ranks'])
def test_live_status_column_route_split_matches_the_frontend(route):
    _, errors = validate_manifest(_minimal(ui={'live_status_columns': [_column(route=route)]}))
    assert errors


@pytest.mark.parametrize('route', ['get items', 'POST  items', ' GET items ', 'GET items?q=a b'])
def test_route_split_still_accepts_what_the_frontend_parses(route):
    _, errors = validate_manifest(_minimal(ui={'panels': {'p': {'kind': 'form', 'load': route}}}))
    assert errors == []


# ---- page navbar entry ------------------------------------------------

def _page(nav):
    return _minimal(ui={'page': {'component': 'ui/Page.js', 'nav': nav}})


def test_page_nav_entry_is_valid():
    manifest, errors = validate_manifest(_page({'label': 'Hosts health', 'icon': 'activity'}))
    assert errors == []
    assert manifest['ui']['page']['nav'] == {'label': 'Hosts health', 'icon': 'activity'}


def test_page_nav_icon_is_optional():
    _, errors = validate_manifest(_page({'label': 'Hosts health'}))
    assert errors == []


def test_page_without_nav_is_still_valid():
    _, errors = validate_manifest(_minimal(ui={'page': {'component': 'ui/Page.js'}}))
    assert errors == []


@pytest.mark.parametrize('nav', ['Hosts', ['Hosts'], 7])
def test_page_nav_must_be_an_object(nav):
    _, errors = validate_manifest(_page(nav))
    assert any('ui.page.nav: must be an object' in e for e in errors)


@pytest.mark.parametrize('label', [None, '', '   ', 5])
def test_page_nav_label_is_required(label):
    _, errors = validate_manifest(_page({'label': label, 'icon': 'activity'}))
    assert any('ui.page.nav: "label" is required' in e for e in errors)


def test_page_nav_label_is_capped():
    _, errors = validate_manifest(_page({'label': 'x' * 33}))
    assert any('"label" must be at most 32 characters' in e for e in errors)
    _, errors = validate_manifest(_page({'label': 'x' * 32}))
    assert errors == []


@pytest.mark.parametrize('icon', ['', '  ', 3])
def test_page_nav_icon_must_be_a_name(icon):
    _, errors = validate_manifest(_page({'label': 'Hosts', 'icon': icon}))
    assert any('"icon" must be a non-empty string' in e for e in errors)


def _menu_status(status, point='host_menu'):
    return validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form'}},
        point: [{'id': 'relay', 'label': 'Relay', 'panel': 'p', 'status': status}],
    }))


@pytest.mark.parametrize('point', ['host_menu', 'instance_menu'])
def test_menu_status_route_accepted(point):
    _, errors = _menu_status('GET hosts/{host_id}/status', point)
    assert errors == []
    _, errors = _menu_status('instances/{instance_id}/status', point)
    assert errors == []


@pytest.mark.parametrize('route', ['POST hosts/{host_id}/status', 'DELETE x', 'put x'])
def test_menu_status_must_be_get(route):
    _, errors = _menu_status(route)
    assert any('status' in e and 'GET' in e for e in errors)


@pytest.mark.parametrize('route', [
    'GET /api/hosts', 'GET ../../hosts', 'GET https://evil.example/x', 5, '',
])
def test_menu_status_route_escape_rejected(route):
    _, errors = _menu_status(route)
    assert errors


def test_status_on_settings_section_rejected():
    _, errors = validate_manifest(_minimal(ui={
        'panels': {'p': {'kind': 'form'}},
        'settings_section': {'id': 's', 'panel': 'p', 'status': 'GET x'},
    }))
    assert any('status' in e and 'host_menu' in e for e in errors)
