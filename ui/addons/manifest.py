"""Parse + validate an addon's `qlsm-addon.json` manifest.

Validation never raises. A malformed manifest yields a list of human-readable
errors and the addon is reported as `broken` in the catalog instead of loading
-- same principle as ui/plugin_manifest.load_manifest_file(), one level up: a
bad addon must never take qlsm's startup down with it.
"""
import json
import os
import re

MANIFEST_FILENAME = 'qlsm-addon.json'
MANIFEST_MAX_SIZE = 64 * 1024  # metadata only, not a data file

ADDON_ID_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
ADDON_ID_MAX = 64

SCOPES = ('global', 'host', 'instance')
FIELD_TYPES = ('bool', 'number', 'string', 'secret', 'select')
PANEL_KINDS = ('form', 'table', 'logs')
MOUNT_POINTS = (
    'host_menu', 'instance_menu', 'instance_tabs', 'settings_section', 'page',
    'add_instance_tabs',
)

# `panel` = core renders its shell and the addon fills the body.
# `modal`  = the addon's component *is* the whole dialog, so an addon can
# mount a purpose-built screen (its own width, header actions, subtitle)
# rather than a generic panel that loses half its controls.
RENDER_MODES = ('panel', 'modal')

# Bumped when the contract a mounted component sees (ctx shape, ui kit) changes
# in a way an already-built addon bundle cannot survive. An addon declaring a
# higher value is listed but not mounted -- see ui/addons/registry.py.
# 4: adds the `live_status_columns` mount point and `icon_url` support.
CURRENT_UI_API = 4

LIVE_STATUS_COLUMN_ALIGNS = ('left', 'right')
LIVE_STATUS_COLUMN_LABEL_MAX = 24
PAGE_NAV_LABEL_MAX = 32

# Extensions ui/routes/addon_routes.py is willing to serve as an image. Checked
# here too so a manifest pointing `icon_url` at something the route refuses
# (`backend.py`, a `.gif`) is an install-time error with a reason, rather than
# a broken image the operator has to open devtools to explain.
IMAGE_EXTENSIONS = ('.svg', '.png', '.webp')


class ManifestError(ValueError):
    """Only raised by parse_manifest_strict(); the normal path collects errors."""


def _err(errors, msg):
    errors.append(msg)
    return errors


# Characters that have no business in a manifest-declared relative path and
# that are exactly what turns one into an escape:
#   %  -- `%2e%2e` and `..%2f` are a `..` segment as far as a URL parser is
#         concerned, so a `..`-only check does not see them; nothing legitimate
#         here needs percent-encoding, since `{placeholders}` cover the
#         variable parts
#   ?  -- starts a query string, which both detaches the rest of the path from
#         this check and swallows the `?steam_ids=` core appends
#   #  -- same, as a fragment
#   \  -- a path separator on Windows, where these are resolved with
#         os.path.join, so `..\x` is a real traversal a `/`-only split reads
#         as one harmless filename
_UNSAFE_PATH_CHARS = ('%', '?', '#', '\\')

# Control and whitespace characters (tab, CR, LF, ...) that a URL parser
# strips before it ever looks at dot segments -- `".\t./.\t./hosts"` reaches
# the browser's parser as `"../../hosts"`, which is exactly the traversal the
# segment check below exists to catch, but the raw string it sees here is
# neither `.` nor `..` so it sails through. Rejecting these outright, rather
# than trying to strip them the same way a parser would, means there is no
# second place that has to agree with the browser on what counts as
# whitespace.
_CONTROL_CHAR_RE = re.compile(r'[\x00-\x20\x7f]')


def _escapes_addon_dir(path):
    """True when a manifest-declared relative path could leave its own base.

    Used for both halves of the same promise: an `icon_url`/`component` must
    stay inside the addon's `ui/` directory, and a panel or column `route`
    must stay under the addon's own `/api/addons/<id>/` prefix. Both are
    resolved by something that collapses dot segments -- `os.path.join` on
    the server, the URL parser in the browser -- so `..` has to be rejected
    here, in every spelling, rather than relied on to fail later.

    The asset route does re-check the resolved path, but a `route` has no
    such second line: the browser normalizes `/api/addons/x/../../hosts` to
    `/api/hosts` and sends it with the operator's cookie before any qlsm code
    sees it.
    """
    if _CONTROL_CHAR_RE.search(path):
        return True
    candidate = path.replace('\\', '/')
    if candidate.startswith('/'):
        return True
    if any(ch in path for ch in _UNSAFE_PATH_CHARS):
        return True
    # A single trailing slash is fine (some endpoints are declared that way);
    # an empty segment anywhere else, or any dot segment, is not.
    segments = candidate[:-1].split('/') if candidate.endswith('/') else candidate.split('/')
    return any(segment in ('', '.', '..') for segment in segments)


def _validate_icon_ref(where, icon, icon_url, errors):
    """`icon` (a name from the frontend's fixed allow-list) and `icon_url` (a
    path inside the addon's own `ui/` directory) are mutually exclusive --
    same traversal protection as a tier-2 `component` path, since icon_url is
    served through the same `ui/<path>` route.
    """
    if icon is not None and icon_url is not None:
        _err(errors, f'{where}: "icon" and "icon_url" are mutually exclusive')
        return
    if icon_url is not None:
        if not isinstance(icon_url, str) or not icon_url.strip():
            _err(errors, f'{where}: "icon_url" must be a non-empty string')
        elif _escapes_addon_dir(icon_url):
            _err(errors, f'{where}: "icon_url" must stay inside the addon')
        elif os.path.splitext(icon_url)[1].lower() not in IMAGE_EXTENSIONS:
            _err(errors, f'{where}: "icon_url" must be one of {", ".join(IMAGE_EXTENSIONS)}')
    elif icon is not None:
        if not isinstance(icon, str) or not icon.strip():
            _err(errors, f'{where}: "icon" must be a non-empty string')


def _validate_field(field, where, errors):
    """One settings field / declarative form field."""
    if not isinstance(field, dict):
        return _err(errors, f'{where}: field must be an object')
    key = field.get('key')
    if not isinstance(key, str) or not key.strip():
        return _err(errors, f'{where}: field is missing a "key"')
    ftype = field.get('type')
    if ftype not in FIELD_TYPES:
        return _err(errors, f'{where}.{key}: type must be one of {", ".join(FIELD_TYPES)}')
    for bound in ('min', 'max'):
        if bound in field:
            if ftype != 'number':
                _err(errors, f'{where}.{key}: "{bound}" only applies to type "number"')
            elif not isinstance(field[bound], (int, float)) or isinstance(field[bound], bool):
                _err(errors, f'{where}.{key}: "{bound}" must be a number')
    if ftype == 'select':
        options = field.get('options')
        if not isinstance(options, list) or not options:
            _err(errors, f'{where}.{key}: type "select" requires a non-empty "options" list')
        else:
            for option in options:
                value = option.get('value') if isinstance(option, dict) else option
                if not isinstance(value, str) or not value.strip():
                    _err(errors, f'{where}.{key}: each option must have a non-empty string value')
                if isinstance(option, dict):
                    _validate_icon_ref(
                        f'{where}.{key}: option "{value}"',
                        option.get('icon'), option.get('icon_url'), errors,
                    )
    elif 'options' in field:
        _err(errors, f'{where}.{key}: "options" only applies to type "select"')
    return errors


def _validate_settings(settings, errors):
    """`settings` maps a scope name to that scope's list of fields."""
    if settings is None:
        return {}
    if not isinstance(settings, dict):
        _err(errors, '"settings" must be an object keyed by scope')
        return {}
    for scope, fields in settings.items():
        if scope not in SCOPES:
            _err(errors, f'"settings": unknown scope "{scope}"')
            continue
        if not isinstance(fields, list):
            _err(errors, f'"settings.{scope}" must be a list of fields')
            continue
        seen = set()
        for field in fields:
            _validate_field(field, f'settings.{scope}', errors)
            key = field.get('key') if isinstance(field, dict) else None
            if key in seen:
                _err(errors, f'settings.{scope}: duplicate field key "{key}"')
            seen.add(key)
    return settings


def _validate_relative_route(where, path, errors, allow_query=True):
    """A panel/column route must stay under the addon's own API prefix.

    This is the whole of the "an addon cannot point a declarative route at a
    core endpoint" guarantee: the frontend builds the URL as
    `/api/addons/<id>/<path>`, and nothing downstream re-checks it. Rejecting
    only `/api/`-style absolute paths was not enough -- `../../hosts` resolves
    to `/api/hosts` in the browser, with the operator's cookie attached, and
    a panel `submit` route carries a verb, so a mutating core call was
    reachable the same way.

    A panel route may carry a query string (`files?instance_id={instance_id}`
    is what the bundled example does); only the path part in front of it is
    subject to the escape rules, since a URL parser does not collapse dot
    segments inside a query. `allow_query=False` is for the
    `live_status_columns` route, where core appends its own `?steam_ids=` and
    a declared `?` would swallow it.
    """
    if path.startswith('/') or '://' in path:
        _err(errors, f'{where}: must be relative to the addon prefix, not absolute')
        return
    if '#' in path:
        # Never reaches the server, and silently truncates whatever follows.
        _err(errors, f'{where}: must not contain a fragment ("#")')
        return
    head, separator, query = path.partition('?')
    if separator:
        if not allow_query:
            _err(errors, f'{where}: must not carry a query string -- core appends its own')
            return
        if '?' in query:
            _err(errors, f'{where}: must not contain more than one "?"')
            return
    if _escapes_addon_dir(head):
        _err(errors, f'{where}: must stay inside the addon prefix')


# Mirrors parseRoute() in frontend-react/src/components/addons/panelRoute.js:
# a verb from this list, spaces, then the path -- anything else is a GET path
# in full. The two must split a route identically, or the path validated here
# is not the path the browser requests.
_ROUTE_RE = re.compile(r'(GET|POST|PUT|PATCH|DELETE) +(.*)', re.IGNORECASE)


def _split_route(where, route, errors):
    """Split a declared route into `(method, path)`, or None after an error.

    Whitespace other than a plain space is refused anywhere in the route, so
    there is no second separator the frontend could split on instead.
    """
    if any(ch != ' ' and (ch.isspace() or ch == '\ufeff') for ch in route):
        _err(errors, f'{where}: must not contain whitespace other than a single space after the method')
        return None
    route = route.strip(' ')
    match = _ROUTE_RE.fullmatch(route)
    if match:
        return match.group(1).upper(), match.group(2).strip(' ')
    return 'GET', route


def _validate_panel_route(where, route, errors):
    """Validate a declared `"METHOD path"` (or bare `path`) route string.

    Shared by every place a panel can declare a route that
    `addonRequest`/`addonDownload` will call with the operator's session:
    `load`/`submit`, a managed form's `status.load`, and a table's
    `row_actions`/`bulk_actions`. Missing any one of these left a declared
    route that never went through `_validate_relative_route` at all -- the
    absolute-path and traversal rejection only ever applied to the two kinds
    checked here historically.
    """
    if route is None:
        return
    if not isinstance(route, str) or not route.strip():
        _err(errors, f'{where}: must be a non-empty string')
        return
    parsed = _split_route(where, route, errors)
    if parsed:
        _validate_relative_route(where, parsed[1], errors)


def _validate_panel(name, panel, errors):
    if not isinstance(panel, dict):
        return _err(errors, f'panels.{name}: must be an object')
    kind = panel.get('kind')
    if kind not in PANEL_KINDS:
        return _err(errors, f'panels.{name}: kind must be one of {", ".join(PANEL_KINDS)}')
    # Routes are relative to the addon's own /api/addons/<id>/ prefix.
    # Rejecting absolute paths here is what stops a panel from being
    # pointed at a core endpoint (see spec 5.1).
    for route_key in ('load', 'submit'):
        _validate_panel_route(f'panels.{name}.{route_key}', panel.get(route_key), errors)
    status = panel.get('status')
    if isinstance(status, dict):
        _validate_panel_route(f'panels.{name}.status.load', status.get('load'), errors)
    for action_key in ('row_actions', 'bulk_actions'):
        actions = panel.get(action_key)
        if not isinstance(actions, list):
            continue
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            action_id = action.get('id') if isinstance(action.get('id'), str) else index
            _validate_panel_route(
                f'panels.{name}.{action_key}[{action_id}].route', action.get('route'), errors,
            )
    for field in panel.get('fields') or []:
        _validate_field(field, f'panels.{name}', errors)
    return errors


MENU_STATUS_POINTS = ('host_menu', 'instance_menu')


def _validate_menu_status(mount, status, errors):
    """Validate a menu entry's optional `status` route.

    It is fetched with the operator's session each time the menu opens, so it
    follows the panel route rules and is GET only: opening a menu must never
    mutate anything.
    """
    where = f'ui.{mount}.status'
    if mount not in MENU_STATUS_POINTS:
        _err(errors, f'{where}: only allowed on host_menu and instance_menu entries')
        return
    before = len(errors)
    _validate_panel_route(where, status, errors)
    if len(errors) > before:
        return
    method, _path = _split_route(where, status, errors)
    if method != 'GET':
        _err(errors, f'{where}: must be a GET route')


def _validate_live_status_column(item, errors):
    """Validate one entry; returns its id, or None when there isn't a usable one.

    Returning None rather than a placeholder matters: the caller feeds this
    into a `set` for the duplicate check, so handing back anything unhashable
    (which `_err`'s return value is -- it returns the error *list*) turned a
    malformed entry into a TypeError out of `read_manifest()`, and from there
    out of `create_app()`, since the registry scan reads manifests during app
    construction. A bad manifest must stay a validation error.
    """
    if not isinstance(item, dict):
        _err(errors, 'ui.live_status_columns: entry must be an object')
        return None
    col_id = item.get('id')
    if not isinstance(col_id, str) or not col_id.strip():
        _err(errors, 'ui.live_status_columns: entry is missing "id"')
        col_id = None
    where = f'ui.live_status_columns.{col_id}' if col_id else 'ui.live_status_columns'
    label = item.get('label')
    if not isinstance(label, str) or not label.strip():
        _err(errors, f'{where}: "label" is required')
    elif len(label) > LIVE_STATUS_COLUMN_LABEL_MAX:
        _err(errors, f'{where}: "label" must be at most '
                     f'{LIVE_STATUS_COLUMN_LABEL_MAX} characters')
    align = item.get('align', 'left')
    if align not in LIVE_STATUS_COLUMN_ALIGNS:
        _err(errors, f'{where}: "align" must be one of '
                     f'{", ".join(LIVE_STATUS_COLUMN_ALIGNS)}')
    _validate_icon_ref(where, item.get('icon'), item.get('icon_url'), errors)
    route = item.get('route')
    if not isinstance(route, str) or not route.strip():
        _err(errors, f'{where}: "route" is required')
    else:
        parsed = _split_route(f'{where}: "route"', route, errors)
        if parsed:
            method, path = parsed
            if method != 'GET':
                _err(errors, f'{where}: "route" must be a GET route')
            # Same rule as a panel route: relative to the addon's own prefix, so
            # a column cannot be pointed at a core endpoint.
            _validate_relative_route(f'{where}: "route"', path, errors, allow_query=False)
    return col_id


def _validate_live_status_columns(entries, errors):
    if entries is None:
        return
    if not isinstance(entries, list):
        _err(errors, '"ui.live_status_columns" must be a list')
        return
    seen = set()
    for item in entries:
        col_id = _validate_live_status_column(item, errors)
        # A missing id is already reported; skipping it here keeps the
        # duplicate check from adding a second, confusing error about an
        # id that does not exist.
        if col_id is None:
            continue
        if col_id in seen:
            _err(errors, f'ui.live_status_columns: duplicate column id "{col_id}"')
        seen.add(col_id)


def _validate_page_nav(nav, errors):
    """`ui.page.nav` -- a top-level navbar entry that links to the page."""
    if nav is None:
        return
    if not isinstance(nav, dict):
        _err(errors, 'ui.page.nav: must be an object')
        return
    label = nav.get('label')
    if not isinstance(label, str) or not label.strip():
        _err(errors, 'ui.page.nav: "label" is required')
    elif len(label) > PAGE_NAV_LABEL_MAX:
        _err(errors, f'ui.page.nav: "label" must be at most {PAGE_NAV_LABEL_MAX} characters')
    # The name is resolved against the frontend's fixed icon list, which
    # falls back to a default for a name it does not know.
    _validate_icon_ref('ui.page.nav', nav.get('icon'), None, errors)


def _validate_add_instance_tab(item, panels, errors):
    """An Add Instance form tab has no instance to save to yet.

    Its values travel with the create request (`addon_options`) to the
    addon's own `instance.created` handler, so a panel there is a `form`
    whose optional `load` prefills it (with `{host_id}` of the selected
    host) and which declares no `submit` -- a submit route would read as if
    the tab saved somewhere on its own. It is a tab inside core's form, so
    it cannot be its own dialog either.
    """
    if item.get('renders') == 'modal':
        _err(errors, 'ui.add_instance_tabs: "renders": "modal" is not available here')
    if panels is None:
        return
    panel = panels.get(item['panel'])
    if not isinstance(panel, dict):
        return  # already reported as undeclared / malformed
    if panel.get('kind') != 'form':
        _err(errors, f'ui.add_instance_tabs: panel "{item["panel"]}" must be of kind "form"')
    if panel.get('submit') is not None:
        _err(errors, f'ui.add_instance_tabs: panel "{item["panel"]}" must not declare "submit" '
                     '-- its values are sent with the create request')


def _validate_ui(ui, errors):
    if ui is None:
        return {}
    if not isinstance(ui, dict):
        _err(errors, '"ui" must be an object')
        return {}

    _validate_icon_ref('ui', ui.get('icon'), ui.get('icon_url'), errors)
    _validate_live_status_columns(ui.get('live_status_columns'), errors)

    panels = ui.get('panels') or {}
    if not isinstance(panels, dict):
        _err(errors, '"ui.panels" must be an object')
        panels = {}
    for name, panel in panels.items():
        _validate_panel(name, panel, errors)

    for mount in MOUNT_POINTS:
        entries = ui.get(mount)
        if entries is None:
            continue
        # settings_section / page are single objects; the menu/tab points are lists.
        items = entries if isinstance(entries, list) else [entries]
        for item in items:
            if not isinstance(item, dict):
                _err(errors, f'ui.{mount}: entry must be an object')
                continue
            has_panel = isinstance(item.get('panel'), str) and item['panel'].strip()
            has_component = isinstance(item.get('component'), str) and item['component'].strip()
            if not has_panel and not has_component:
                _err(errors, f'ui.{mount}: entry needs either "panel" or "component"')
            if has_panel and has_component:
                _err(errors, f'ui.{mount}: entry has both "panel" and "component" -- pick one')
            if has_panel and item['panel'] not in panels:
                _err(errors, f'ui.{mount}: panel "{item["panel"]}" is not declared in ui.panels')
            if has_component:
                # A component is served from the addon's own ui/ directory;
                # anything escaping it is a path-traversal attempt.
                comp = item['component']
                if _escapes_addon_dir(comp):
                    _err(errors, f'ui.{mount}: component path "{comp}" must stay inside the addon')
            renders = item.get('renders')
            if renders is not None and renders not in RENDER_MODES:
                _err(errors, f'ui.{mount}: "renders" must be one of {", ".join(RENDER_MODES)}')
            if renders == 'modal' and not has_component:
                _err(errors, f'ui.{mount}: "renders": "modal" needs a component, not a panel')
            if mount == 'page':
                _validate_page_nav(item.get('nav'), errors)
            if item.get('status') is not None:
                _validate_menu_status(mount, item['status'], errors)
            if mount == 'add_instance_tabs':
                _validate_add_instance_tab(item, panels if has_panel else None, errors)
    return ui


def validate_manifest(data):
    """Return (normalized_manifest, errors). `errors` empty means loadable."""
    errors = []
    if not isinstance(data, dict):
        return None, ['manifest must be a JSON object']

    addon_id = data.get('id')
    if not isinstance(addon_id, str) or not addon_id.strip():
        _err(errors, '"id" is required')
        addon_id = None
    else:
        addon_id = addon_id.strip()
        if len(addon_id) > ADDON_ID_MAX:
            _err(errors, f'"id" must be at most {ADDON_ID_MAX} characters')
        if not ADDON_ID_RE.match(addon_id):
            _err(errors, '"id" must be kebab-case (lowercase letters, digits, single dashes)')

    version = data.get('version')
    if not isinstance(version, str) or not version.strip():
        _err(errors, '"version" is required')

    scopes = data.get('scopes') or ['global']
    if not isinstance(scopes, list) or not scopes:
        _err(errors, '"scopes" must be a non-empty list')
        scopes = ['global']
    else:
        for scope in scopes:
            if scope not in SCOPES:
                _err(errors, f'"scopes": unknown scope "{scope}"')
        scopes = [s for s in SCOPES if s in scopes]  # canonical order, deduped

    ui_api = data.get('ui_api', CURRENT_UI_API)
    if not isinstance(ui_api, int) or isinstance(ui_api, bool) or ui_api < 1:
        _err(errors, '"ui_api" must be a positive integer')
        ui_api = CURRENT_UI_API

    depends = data.get('depends') or []
    if not isinstance(depends, list) or any(not isinstance(d, str) for d in depends):
        _err(errors, '"depends" must be a list of addon ids')
        depends = []

    settings = _validate_settings(data.get('settings'), errors)
    ui = _validate_ui(data.get('ui'), errors)

    manifest = {
        'id': addon_id,
        'version': (version or '').strip() if isinstance(version, str) else '',
        'name': data.get('name') or addon_id or '',
        'description': data.get('description') or '',
        'scopes': scopes,
        'ui_api': ui_api,
        'depends': depends,
        'settings': settings,
        'ui': ui,
    }
    return manifest, errors


def read_manifest(directory):
    """Read + validate the manifest in `directory`.

    Returns (manifest_or_None, errors). A missing file is reported as an error
    too -- the caller decides whether a directory without one is simply not an
    addon (registry.py skips those before calling here).
    """
    path = os.path.join(directory, MANIFEST_FILENAME)
    if not os.path.isfile(path):
        return None, [f'{MANIFEST_FILENAME} not found']
    try:
        if os.path.getsize(path) > MANIFEST_MAX_SIZE:
            return None, [f'{MANIFEST_FILENAME} is larger than {MANIFEST_MAX_SIZE} bytes']
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return None, [f'{MANIFEST_FILENAME} could not be read: {e}']
    return validate_manifest(data)
