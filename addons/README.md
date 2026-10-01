# QLSM addons

Optional features that plug into QLSM without core knowing they exist.

## Where addons are loaded from

| Source | Path | Notes |
|--------|------|-------|
| Bundled | `addons/<id>/` | Ships inside the Docker image |
| Installed | `$ADDON_PACKAGES_DIR/<id>/` (default `./addon-packages`) | Operator-writable volume |

A directory is an addon only if it contains `qlsm-addon.json`. An id present
in both sources resolves to the **installed** copy, so an operator can
override a bundled addon without rebuilding the image.

`addons/_examples/` has no manifest of its own, so it is skipped by the
scanner — the reference addon inside it does not load in production. To try
it, copy `addons/_examples/hello-addon/` into your addon-packages volume and
restart.

## What ships here today

**No feature addon does.** QLSM's image carries this documentation and the
reference examples, nothing else. A real addon lives in a repository the
operator installs from, so a QLSM install only runs the features its operator
asked for.

| Shipped here | What it is |
|--------------|------------|
| `_examples/hello-addon` | Reference only. Not loaded (`_examples` has no manifest of its own); copy it into the volume to try it. |
| `_examples/css-test-addon` | Reference only. Smallest possible tier-2 component, there only to prove `ui/Panel.css` gets loaded next to `ui/Panel.js`. |
| `_examples/ui-kit-test-addon` | Reference only. Exercises the shared `window.__qlsm.ui` kit (`Modal`, `Button`, `Panel`/`Card`, `AddonField`, `Icon`, `Stack`/`Row`) and needs no CSS of its own. |

**An addon owns its feature end to end.** Its endpoints, tasks, settings,
playbooks, host-side payload and UI all live in the addon package; core keeps
no half of a feature behind. That is what makes not installing one a real
choice rather than a partial one -- without the addon, its part of the UI and
its part of the API are simply not there.

**Two addons needing the same mechanism each carry their own copy of it.**
There is no addon-to-addon dependency concept -- no manifest field, no
install ordering, no uninstall guard -- so a shared addon could vanish out
from under both of its dependants at once, the opposite of the failure
isolation described below. Duplication is not free (the copies are free to
diverge and nothing keeps them in sync), but it is the lesser risk until
dependencies become a real feature.

## Layout

```
<addon-id>/
  qlsm-addon.json     # required: manifest
  backend.py          # optional: register(ctx)
  ui/                 # optional: pre-built components (.js/.css/.map only)
  playbooks/          # optional: addon-owned Ansible
  assets/             # optional: host-side payload
  plugins/            # optional: minqlx plugins the addon ships
```

## Failure isolation

A broken addon never takes QLSM down. A malformed manifest, an import that
raises, a `register()` that throws, a hook handler that blows up mid-deploy,
a component that crashes while rendering — each is contained and reported.
Broken addons stay **visible** on the Addons page with their error attached,
because silently disappearing is the harder failure to diagnose.

## Installing

Settings → Addons → **Install**, and upload a `.zip`. The archive may have
`qlsm-addon.json` at its root or nested one folder deep (what "Compress this
folder" produces). The install directory is named after the manifest's `id`,
not the folder in the archive.

Or from a repository: Settings → Repositories. A repository that publishes
`qlsm-repository.json` with an `addons` section (see
`ui/plugin_repositories.py` for the format) lists its addon packages there
with one-click **Install** / **Update** — the downloaded `.zip` goes through
exactly the same installer and checks as an upload, including the optional
`sha256` the repo manifest declares for the archive. Update detection
compares the repo entry's `version` against the installed package's own
`qlsm-addon.json`.

**The addon is not live until QLSM restarts.** Flask cannot hot-add or drop a
blueprint on a running app, so a freshly installed addon is listed as
*pending restart* rather than pretended to be active — the alternative is an
entry whose endpoints 404 with no explanation. Same for uninstall.

Uninstall removes the package directory. It keeps the addon's `AddonState`
rows, so reinstalling the same addon finds its settings again.

The upload is checked for archive size, total uncompressed size, entry count,
per-member compression ratio, absolute/`..` paths, symlinks, and a valid
manifest. Nothing is swapped into place until the whole archive has been
validated and staged, so a rejected upload leaves the previous install
untouched.

## Trust

An addon's Python half runs in-process with QLSM's full authority: the
database, SSH private keys, the cloud API key. There is no sandbox, and the
`AddonContext` is an ergonomics boundary, not a security one. Only install
addons you would trust with the QLSM host itself.

**Read [TRUST.md](TRUST.md) before installing an addon you did not write.**
The install checks above are about not being exploitable by a malformed
archive; they say nothing about whether the code inside is safe to run, and
there is no signing.

## Scopes

Three layers, each requiring the one above it:

| Scope | Means |
|-------|-------|
| `global` | The addon is on for this QLSM at all |
| `host` | Its payload is installed / enabled on that host |
| `instance` | The feature is on for that game server |

Turning an instance on while its host is off stores the intent but leaves the
addon inactive; the UI says so rather than silently doing nothing.

## UI, tier 1 — declarative

The manifest's `ui` block declares mount points; QLSM renders them with its
own components. Panel kinds: `form`, `table`. A `form` panel with no `load`
route is **managed** — values are stored by QLSM and an addon needs no
backend code at all for its settings.

A `table` panel declares its columns (`text` / `bytes` / `datetime`
formatting), an optional `selectable` flag with `bulk_actions`, and
`row_actions`. A route may contain both scope placeholders (`{instance_id}`)
and row placeholders (`{name}`); row values are URL-encoded, so a filename
with a space cannot break the query string. An action with `"download": true`
is fetched as a blob and saved under the filename from the response's
`Content-Disposition`, which keeps auth headers and works for POST endpoints
(the batch download posts a selection and gets a zip back). Bulk actions post
the selection under `selection_key` (default `selected`), so an addon can
keep the field name its API already uses.

Mount points: `host_menu`, `instance_menu`, `instance_tabs`,
`settings_section`, `page`. Routes in a panel are always relative to the
addon's own `/api/addons/<id>/` prefix, so a panel cannot point at a core
endpoint. Manifest validation enforces that, and rejects more than an
absolute path: a declared route may not contain a `.` or `..` segment, an
empty segment, a `%`, a `#`, or a backslash. The frontend builds the URL by
string concatenation and the browser then collapses dot segments, so
`../../hosts` would resolve to `/api/hosts` with the operator's cookie
attached, and `%2e%2e` is the same `..` segment to a URL parser.
`{placeholders}` cover every variable part, so nothing legitimate here needs
percent-encoding. A query string is allowed (`files?instance_id={instance_id}`
-- see `_examples/hello-addon`); only the path in front of the `?` is subject
to those rules.

Whitespace is refused as well. A route is `"METHOD path"` -- a verb from
`GET`/`POST`/`PUT`/`PATCH`/`DELETE`, plain spaces, then the path -- or a bare
path, which means `GET`. The path may not contain a space or any control
character, and no other whitespace (tab, newline, a non-breaking space, ...)
may appear anywhere in the route. The validator and the frontend split the
verb from the path by that one rule, so the path that is checked is the path
that is requested. The frontend also refuses to send a request whose final
path has a `.`, `..` or empty segment, which covers a table row's
`{placeholder}` values: they are filled in from the addon's own response,
after the manifest was validated.

### `live_status_columns` -- a column in core's own players table

Every other mount point gives an addon its own place: a menu entry, a tab, a
page. `live_status_columns` is the one exception -- it lets an addon add a
column to a component core owns (the players table in the instance Live
Status drawer), because that surface has no addon-owned equivalent to attach
to and adding one felt like the wrong tradeoff for a single column.

```json
{ "ui": { "live_status_columns": [
  { "id": "rating", "label": "Rating", "align": "right",
    "icon_url": "logos/qlstats.svg",
    "route": "GET instances/{instance_id}/ranks" }
] } }
```

- `id` -- required, unique within the addon.
- `label` -- required, at most 24 characters (the table is narrow).
- `align` -- `left` (default) or `right`.
- `icon` / `icon_url` -- optional, mutually exclusive. `icon` is a name from
  the frontend's fixed icon list; `icon_url` is a path inside the addon's own
  `ui/` directory (see "Icons and other images" below).
- `route` -- required, `GET` only, relative to the addon's own prefix and
  subject to the same escape rules as any panel route (see above);
  `{instance_id}` is substituted by core. Unlike a panel route it may not
  carry a query string of its own -- core appends `?steam_ids=`.

Core calls `GET /api/addons/<id>/<route>?steam_ids=a,b,c` (every connected
player, deduplicated, sorted, comma-joined) and expects
`{"data": {"<steam_id>": {"display": "1802", "title": "optional tooltip"}}, "configured": true}`.
`display` is rendered as-is, never parsed.

Polled every 30s while the drawer is open, deliberately not on core's own
15s status tick. A roster change also triggers a fetch, but only once the
roster has been stable for 3s and without restarting that 30s interval -- on
a filling server people connect every few seconds, and a round per join would
turn a slow source into a fast one.

A cell may instead carry `"entries": [{"display": "1357", "title": "...",
"icon": "...", "icon_url": "..."}, ...]` -- each entry is rendered stacked
(icon above/beside value, one per line) inside the single `<td>`, instead of
the flat `display`/`title` pair. This is for one column that bundles several
sub-values that would otherwise need one column each (e.g. several rating
sources) -- `entries` wins over `display`/`title` when both are present.
`icon`/`icon_url` per entry follow the same rule as the column's own
`icon`/`icon_url` above.

A cell, or any one entry, may also carry `"color"`: one of `white`,
`yellow`, `cyan`, `blue`, `magenta`, `green` (Quake Live's own `^N` colors --
the first use is a rank tier shown in its in-game color). It is a name from
that fixed list, not a CSS value: core picks the actual shade, a different one
per theme so yellow and cyan stay readable on a light background. Anything
else is ignored and the value renders in the default color.

`configured: false` (or a 404) hides the column entirely for that instance
-- this is the normal state for an instance the addon has no opinion about,
not an error, and core stops asking until the drawer is reopened. Any
*other* failure (timeout, 500, a backend mid-restart) is treated as
transient: the column keeps whatever it last showed and stays in the table,
and the next poll tries again. Core also normalizes the payload before
rendering, so a malformed body costs at most one empty cell -- the players
table itself never breaks over this. An addon may declare more columns than
fit -- e.g. one column per rating source, only some enabled per instance --
every declared column is still fetched, since whether it ends up configured
for a given instance is only known after that fetch. At most 3 columns that
come back `configured: true` are rendered (across every addon that declares
one), in the same addon-id-alphabetical order `dispatch()` uses elsewhere,
declaration order within one addon; the rest are dropped with a console
warning.

Requires `"ui_api": 4`.

## UI, tier 2 — the addon's own component

Build it yourself and ship the built file in `ui/`:

```js
// vite.config.js in the addon's own project
export default {
  build: { lib: { entry: 'src/Panel.jsx', formats: ['es'] } },
  rollupOptions: { external: ['react', 'react-dom', '@qlsm/ui'] },
}
```

**Do not bundle React.** QLSM publishes its own React and UI kit on
`window.__qlsm` precisely so your bundle can mark them external — two React
copies on one page break hooks in ways that are painful to debug.

The component receives one prop:

```js
export default function Panel({ ctx }) { /* ... */ }
// ctx = { addonId, scope: { kind, id }, api, apiFor, download, saveBlob, ui, manifest, modal }
```

`ctx.api(method, path, { params, data })` is pre-pinned to your addon's own
prefix; `ctx.apiFor(otherAddonId)` returns the same call pinned to another
addon's, which is how a component runs an action a *different* addon
contributed into it (see "Cross-addon UI contribution" below). Neither can
reach a core endpoint. `ctx.download(method, path, { data, fallbackName })` is the same call
for a file response -- it comes back as `{ blob, filename }`, keeping the
CSRF header and the 401 interceptor a bare `<a href>` would lose, and
`ctx.saveBlob(blob, filename)` hands it to the browser. `ctx.ui` is the
shared component kit.

**A component may be the whole dialog.** A mount point in `host_menu` or
`instance_menu` that declares `"renders": "modal"` gets no shell from core --
your component renders it, which is how a feature keeps a purpose-built
screen (its own width, header actions, subtitle) that the generic shell
cannot express. Then `ctx.modal` is set:

```json
{ "id": "demos", "label": "Demos", "icon": "film",
  "component": "Panel.js", "renders": "modal" }
```

`"component"` is a path relative to the addon's own `ui/` directory (core
serves it from `/api/addons/<id>/ui/<component>`) — not prefixed with `ui/`
itself, or the asset URL doubles up as `.../ui/ui/Panel.js` and 404s.

```js
// ctx.modal = { isOpen, onClose, entity, subtitle }
const { Modal } = window.__qlsm.ui;
return h(Modal, { isOpen: ctx.modal.isOpen, onClose: ctx.modal.onClose, size: '2xl' }, ...);
```

`entity` is the whole host/instance object, not just its id, because a
purpose-built screen usually shows its name and port too. Nothing is rendered
while the bundle loads: the operator clicked a menu entry, and a flash of
placeholder before the real dialog is worse than the dialog simply appearing.

Declare `"ui_api"` in the manifest. A core that does not implement the
version you ask for lists the addon but withholds its UI, with the reason
shown — instead of mounting it and crashing.

**CSS is optional and found by convention, not declared in the manifest.**
If your component is `ui/Panel.js`, drop a `ui/Panel.css` next to it and
QLSM links it into the page automatically when that component mounts — no
manifest field needed. It stays in `document.head` for the page's lifetime
(not removed when the mount point unmounts), so switching a tab or panel in
and out doesn't reload it. See `_examples/css-test-addon` for the smallest
possible example, or `_examples/ui-kit-test-addon` for one that needs no CSS
at all because every visual piece comes from `ctx.ui`.

## Icons and other images

A select field option, a `live_status_columns` entry, and the addon's own
`ui.icon` can point at an image instead of naming one of the fixed icons.
Core itself only renders `icon_url` for a `live_status_columns` column and
its cells so far; on a select option or on `ui` it is validated and passed
through in the manifest for the addon's own components to use, but a
declarative form's `<select>` and the addon's entry on the Addons page do not
show it:

```json
{ "value": "qlstats", "label": "qlstats", "icon_url": "logos/qlstats.svg" }
```

`icon_url` is a path relative to the addon's own `ui/` directory, served
through the same `/api/addons/<id>/ui/<path>` route as a tier-2 component;
`.svg`, `.png` and `.webp` are allowed there alongside `.js`/`.css`/`.map`. An
`.svg` response carries `X-Content-Type-Options: nosniff` and a restrictive
`Content-Security-Policy`, since it is served from the same origin as the
rest of the app and can otherwise carry a script. `icon` and `icon_url` are
mutually exclusive on anything that accepts either.

The same escape rules as a route apply to the path, and the frontend
re-checks them whenever the value arrives in a response rather than in a
manifest -- a `live_status_columns` cell's `icon_url` does, and the manifest
validator never sees it. An escaping path renders no image at all, rather
than becoming a credentialed same-origin request to wherever it points.

## Cross-addon UI contribution (addon-owned hooks)

None of the tiers above cover one addon adding UI elements — actions,
grouping rules, badges — to another addon's **hand-built** (tier 2)
component. An addon-owned hook does: the addon that owns the surface declares
an extension point, dispatches it from its own code, and renders whatever the
other addons contribute.

The examples below use `demo_management.*`, the extension points of a
separately distributed demo-management addon. They are declared in this repo
because core owns the registry of valid hook names (see below), not because
core implements them.

**This is a convention, not a mechanism QLSM enforces.** See "What
`ctx.on`/`dispatch()` actually check" below for exactly where the line falls.

### What makes a hook "addon-owned"

An ordinary hook (`instance.launch_args`, `host.setup`, ...) is declared in
`ui/addons/hooks.py` *and* dispatched from core (`ui/`). An addon-owned hook
is declared in the same `HOOK_SCOPES` dict, but **dispatched from inside the
addon that consumes the contribution**, not from core — the consuming addon
calls `dispatch('<its_id>.<point>', scope_id)` from its own module, the same
way core calls `dispatch('instance.launch_args', instance_id)` from
`ansible_instance_mgmt.py`. Nothing in the registry marks this distinction;
it exists only because the call site lives in the addon instead of `ui/`. Say
so explicitly in the `HOOK_SCOPES` comment for the entry, the way
`demo_management.file_kinds` already does, and add the name to
`tests/test_addon_hooks_are_wired.py`'s `OUT_OF_TREE` set — that test demands
a real dispatch call site inside this repo, and an addon's is not in it.

### Naming convention

`<consuming_addon_id_with_underscores>.<extension_point>` — the addon whose
surface is being extended goes first, using its manifest `id` with hyphens
turned into underscores (`demo-management` -> `demo_management`), then a
short noun for what's being contributed (`file_kinds`, `match_actions`).

The name deliberately does **not** include the contributing addon's id. A
hook belongs to the surface it extends, not to whoever happens to be the only
contributor today; a second contributor registers the same hook name rather
than a new one.

### Expected return shape

`file_kinds` gets away with a flat list of strings because the consumer only
turns it into a regex. A UI contribution (row actions, bulk actions, badges,
menu entries) needs a structured item instead. There is no schema QLSM
validates — until a second real UI-contribution hook exists this is a
recommendation, not code — but shape a contribution like:

```python
@ctx.on('demo_management.match_actions')
def contribute_match_actions():
    return [{
        'id': 'packer-addon.rebuild',     # unique, "<contributor_addon_id>.<action>"
        'label': 'Rebuild',
        'icon': 'refresh-cw',             # name from the ctx.ui icon vocabulary
        'match': lambda demo: demo['name'].endswith('.pack'),
        'action': {'route': 'matches/{name}/rebuild', 'method': 'POST', 'confirm': 'Rebuild this match?'},
    }]
```

- `id` is namespaced by the **contributing** addon's id (the mirror image of
  the hook name itself, which is namespaced by the **consuming** addon) so
  the consumer can key a React list and log which addon a broken contribution
  came from.
- `match` keeps the consumer format-agnostic — it does not need to know what
  a `.pack` file is, only that the contribution applies to rows for which
  `match(demo)` is true. This mirrors how `file_kinds` keeps the consumer
  ignorant of what a contributed extension actually means.
- `action` reuses the tier-1 `row_actions` route/method/confirm shape
  (`AddonTablePanel.jsx`) rather than inventing a second one, since the
  consumer is likely to hand it to a similar route-caller.

### Merge order and conflicts

`dispatch()` (`ui/addons/registry.py`) iterates addons
`sorted(get_addons().values(), key=lambda a: a.id)` — alphabetical by addon
id, deterministic regardless of load/install order. For a hook in
`LIST_HOOKS`, every contributor's return value is concatenated into one flat
list in that order; a handler that raises is logged and dropped, it does not
abort the others. For a UI-contribution hook this means: render contributed
actions in addon-id alphabetical order, after the consumer's own hardcoded
actions (if it has any).

**Nothing dedupes or resolves conflicts.** A flat list of filename
extensions does not need conflict handling, because duplicates are harmless
(a regex alternation with a repeated branch still matches the same set). A UI
contribution does not get that for free — two addons contributing the same
`id`, or two `match` predicates both claiming the same row, will both render
unless the **consumer** guards against it. The consuming addon is
responsible for de-duplicating by `id` (e.g. build a `dict` keyed by `id`
before rendering, log-and-drop the later duplicate) — `dispatch()` gives you
ordering and isolation from a throwing handler, nothing more.

### What `ctx.on`/`dispatch()` actually check (`ui/addons/context.py`, `ui/addons/hooks.py`, `ui/addons/registry.py`)

- **Enforced:** the hook name must be a key in the `HOOK_SCOPES` dict —
  `ctx.on()` calls `validate_hook_name()`, which raises `UnknownHookError` at
  addon **load** time (not dispatch time), so a typo'd hook name breaks the
  addon visibly instead of silently firing at nobody.
- **Enforced:** every declared hook has a real dispatch call site somewhere
  in core or an addon (`tests/test_addon_hooks_are_wired.py`) — a hook can't
  be declared and then forgotten.
- **Enforced:** the scope gate (`global`/`host`/`instance`/`None`) attached
  to the hook in `HOOK_SCOPES` — `_gates_open()` skips a disabled addon's
  handlers even if the hook fires.
- **Enforced:** whether `dispatch()` flattens contributions into one list
  (`LIST_HOOKS` membership) or collects one value per addon — the only
  structural contract the registry knows about.
- **Not enforced — naming convention.** `HOOK_SCOPES` is a flat dict of
  strings; `instance.launch_args` and `demo_management.file_kinds` are
  validated identically. The `<owner>.<point>` convention above is a human
  discipline, not a mechanical rule — nothing stops a new hook from being
  named inconsistently.
- **Not enforced — return shape.** Beyond list-vs-single-value
  (`LIST_HOOKS`), QLSM does not know or check what is inside a contribution.
  The dict shape suggested above is convention between a hook's declarer and
  its contributors, not a validated schema.
- **Not enforced — who "owns" a hook.** `ctx.on()` (subscribe) and
  `dispatch()` (fire) are symmetric from the registry's point of view; there
  is no manifest field or registry table recording which addon dispatches a
  given hook. "Addon-owned" is purely a fact about where the `dispatch(...)`
  call site happens to live in the source tree, documented by convention
  (the `HOOK_SCOPES` comment) and nothing else.
- **Not enforced — conflict resolution across contributors.** See "Merge
  order and conflicts" above; this is entirely on the consuming addon.
