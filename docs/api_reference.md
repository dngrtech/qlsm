# API Reference

Base URL: `/api`

## Authentication

All endpoints except `/api/auth/login` require authentication via JWT cookie.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/login` | POST | Login with username/password, sets JWT cookie; optional `rememberMe` extends the cookie/token lifetime |
| `/auth/logout` | POST | Logout, clears JWT cookie |
| `/auth/status` | GET | Check authentication status |
| `/auth/change-password` | POST | Change the authenticated user's password and clear forced rotation |

`/auth/login` and `/auth/status` both return `data.user.passwordChangeRequired` so the SPA can hard-block access until a bootstrap password is rotated.

## Hosts

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/hosts` | GET | List all hosts |
| `/hosts` | POST | Create host (triggers Terraform provisioning) |
| `/hosts/self/defaults` | GET | Get detected defaults for the self-host provider |
| `/hosts/test-connection` | POST | Test standalone SSH connectivity before host creation |
| `/hosts/<id>` | GET | Get host details with instances |
| `/hosts/<id>` | PUT | Update host (e.g., rename - triggers rename task) |
| `/hosts/<id>` | DELETE | Delete host (triggers Terraform destroy) |
| `/hosts/<id>/restart` | POST | Restart/reboot host |
| `/hosts/<id>/resize` | POST | Resize a Vultr host to a larger same-family plan |
| `/hosts/<id>/qlfilter/install` | POST | Install QLFilter on host |
| `/hosts/<id>/qlfilter/uninstall` | POST | Uninstall QLFilter from host |
| `/hosts/<id>/qlfilter/status` | GET | Check QLFilter status |
| `/hosts/<id>/qlfilter/refresh-status` | POST | Queue QLFilter status refresh task |
| `/hosts/<id>/logs` | GET | Get host task logs |
| `/hosts/<id>/available-ports` | GET | Get available ports on the host |
| `/hosts/<id>/update-workshop` | POST | Force workshop items update on host |
| `/hosts/<id>/auto-restart` | POST | Configure host auto-restart schedule |

### Resize Host

```
POST /api/hosts/<id>/resize
```

Initiates a Vultr plan upgrade for an active host by re-running Terraform in the
host's existing workspace.

Constraints:

- Host provider must be `vultr`.
- Host status must be `active`.
- `new_plan` must be a known Vultr plan ID.
- `new_plan` must be a same-family upgrade with a strictly higher monthly price.
- Downgrades, identical plans, and cross-family resizes are rejected.

Request:

```json
{
  "new_plan": "vc2-2c-4gb"
}
```

Success response (`202 Accepted`):

```json
{
  "message": "Host resize task queued: vc2-1c-2gb -> vc2-2c-4gb.",
  "data": {
    "new_plan": "vc2-2c-4gb",
    "current_plan": "vc2-1c-2gb"
  }
}
```

Error responses:

- `400` for missing/invalid JSON, unknown plan, identical plan, downgrade, or cross-family resize.
- `404` when the host does not exist.
- `409` when the host is non-Vultr, not active, or another operation holds the host lock.

The resize task sets the host to `configuring`, runs `terraform apply` with
`vultr_plan=<new_plan>`, then returns the host to `active` on success. Vultr may
reboot the VM during the resize; QLDS services are expected to auto-restart.

### Create Host Request
Cloud provider:

```json
{
  "name": "my-host-1",
  "provider": "vultr",
  "region": "ewr",
  "machine_size": "vc2-1c-1gb"
}
```

Standalone provider with SSH key:

```json
{
  "name": "standalone-key-host",
  "provider": "standalone",
  "ip_address": "203.0.113.10",
  "ssh_port": 22,
  "ssh_user": "root",
  "ssh_auth_method": "key",
  "ssh_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
  "timezone": "UTC"
}
```

Standalone provider with password bootstrap:

```json
{
  "name": "standalone-password-host",
  "provider": "standalone",
  "ip_address": "203.0.113.10",
  "ssh_port": 22,
  "ssh_user": "root",
  "ssh_auth_method": "password",
  "ssh_password": "bootstrap-secret",
  "timezone": "UTC"
}
```

Password bootstrap never stores `ssh_password`. QLSM uses it once to install a managed SSH key and then persists only the generated key path on the host record. If `ssh_user` is not `root`, passwordless sudo is required. Standalone host OS is detected automatically over SSH during connection testing and host creation; the stored `Host.os_type` is the normalized detected family (`debian` or `ubuntu`).

Self provider:

```json
{
  "name": "self-host",
  "provider": "self",
  "ip_address": "203.0.113.10",
  "timezone": "UTC",
  "ssh_user": "rage"
}
```

Self hosts create a standalone-style host record on the same physical machine that runs the Docker stack. Only one self host may exist. During creation, QLSM snapshots local OS detection into `Host.os_type` when available; if detection fails, `os_type` remains `null`.

All three provider payloads above accept an optional `runtime` field: `"minqlx"` (default) or `"minqlxtended"`. It is rejected with `400` if present and not one of those two values, and it is **immutable** — there is no field or endpoint to change it after the host is created. For cloud hosts, `runtime` also selects the Terraform OS image (minqlx provisions Debian 12; minqlxtended provisions Ubuntu 24.04, the only image with the Python 3.12 the build links against).

The Python 3.12 floor for `runtime: "minqlxtended"` is enforced differently per provider, because QLSM doesn't have the same evidence available at creation time for each:

- **Standalone:** enforced synchronously. `POST /api/hosts` runs an SSH-based OS/Python detection before creating the row, and returns `400` immediately if the detected Python is older than 3.12 (or undetectable).
- **Self:** *not* enforced at creation. Self-host creation only reads local `/etc/os-release`-style detection, which carries no Python version — there is no SSH session to probe, since the host *is* the QLSM server's own reachable target. `POST /api/hosts` returns `201` regardless of the host's actual Python version, the record is created, and asynchronous setup is queued. `ansible/playbooks/setup_host.yml` is the actual gate: it asserts the Python floor before building, and a self host whose Python is too old reaches `ERROR` status once that setup task runs and fails — after creation returned successfully, not instead of it.

### Self-Host Defaults

```
GET /api/hosts/self/defaults
```

Response:

```json
{
  "data": {
    "ssh_user": "rage",
    "host_ip": "203.0.113.10",
    "os_info": {
      "pretty_name": "Debian GNU/Linux 12 (bookworm)",
      "os_type": "debian"
    },
    "provider_capabilities": {
      "vultr": {
        "configured": true
      }
    }
  }
}
```

`host_ip` may be `null` if `QLSM_HOST_IP` is not set. `os_info` may also be `null` if local OS detection is unavailable.

Self-host error cases:

- `400` when timezone or SSH username validation fails.
- `409` when a self host already exists.
- `500` when SSH key setup fails.

### Standalone Connection Test

```
POST /api/hosts/test-connection
```

Key mode:

```json
{
  "ip_address": "203.0.113.10",
  "ssh_port": 22,
  "ssh_user": "root",
  "ssh_auth_method": "key",
  "ssh_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----"
}
```

Password mode:

```json
{
  "ip_address": "203.0.113.10",
  "ssh_port": 22,
  "ssh_user": "deploy",
  "ssh_auth_method": "password",
  "ssh_password": "bootstrap-secret"
}
```

Password-mode connection tests also verify passwordless sudo for non-root users because the later Ansible flow is non-interactive. Connection tests auto-detect the remote OS from `/etc/os-release` and reject unsupported releases. Ubuntu detections succeed, but the response includes a note that 99k LAN Rate support depends on the host migration status. See the 99k LAN Rate migration docs for how to enable it on older hosts.

Example success response:

```json
{
  "data": {
    "success": true,
    "message": "Connection successful. Detected OS: Ubuntu 24.04.2 LTS."
  }
}
```

### Host Name Validation (RFC 1123)
- Max length: 20 characters
- Pattern: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`
- Lowercase letters, numbers, hyphens only
- Must start and end with letter or number

### Host Response (GET /api/hosts/<id>)
```json
{
  "data": {
    "id": 1,
    "name": "my-host-1",
    "ip_address": "144.202.73.249",
    "provider": "vultr",
    "region": "ewr",
    "machine_size": "vc2-1c-1gb",
    "ssh_user": "ansible",
    "ssh_port": 22,
    "os_type": "debian",
    "runtime": "minqlx",
    "is_standalone": false,
    "timezone": "America/New_York",
    "cpu_count": 1,
    "auto_restart_schedule": null,
    "lan_rate_uses_hook": false,
    "firewall_pool_v2": false,
    "status": "active",
    "qlfilter_status": "unknown",
    "logs": "...",
    "instances": [
      {
        "id": 1,
        "name": "duel-server-1",
        "port": 27960,
        "status": "running"
      }
    ],
    "created_at": "2026-01-20T12:00:00",
    "last_updated": "2026-01-20T12:00:00"
  }
}
```

`lan_rate_uses_hook: false` means the host uses the legacy iptables/sysctl mechanism for 99k LAN Rate. After running "Re-run Host Setup", `lan_rate_uses_hook` becomes `true` and instances can use the new hook-based mechanism on any OS.

`firewall_pool_v2: false` means the host's firewall allow-list was rendered before the game/RCON port pool was widened, so the higher instance slots may not be reachable. A successful host setup run — initial or "Re-run Host Setup" — sets it to `true`.

`runtime` is `"minqlx"` or `"minqlxtended"`, set at creation and never changed afterward. `NULL`/legacy rows normalize to `"minqlx"`.

## Instances

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/instances` | GET | List all instances |
| `/instances` | POST | Create instance (triggers Ansible deploy) |
| `/instances/ping` | GET | Health check (no auth required) |
| `/instances/check-name` | GET | Check name availability (no auth required) |
| `/instances/<id>` | GET | Get instance details |
| `/instances/<id>` | DELETE | Delete instance |
| `/instances/<id>/restart` | POST | Restart instance service |
| `/instances/<id>/start` | POST | Start instance service |
| `/instances/<id>/stop` | POST | Stop instance service |
| `/instances/<id>/config` | GET | Get instance config files |
| `/instances/<id>/config` | PUT | Update config and apply (triggers Ansible sync) |
| `/instances/<id>/hooks` | GET | List available LD_PRELOAD hook shared objects |
| `/instances/<id>/hooks/files` | POST | Upload a new hook `.so` file |
| `/instances/<id>/hooks/files/<filename>` | GET/PUT/PATCH/DELETE | Download, replace, rename, or delete a hook file |
| `/instances/<id>/hooks/files/<filename>/description` | PATCH | Set a hook file description |
| `/instances/<id>/lan-rate` | PUT | Toggle 99k LAN rate mode |
| `/instances/<id>/logs` | GET | Get instance task logs |
| `/instances/<id>/remote-logs` | GET | Fetch server logs via Ansible (`?filter_mode=`, `?since=`, `?lines=`, `?filename=`) |
| `/instances/<id>/remote-logs/list` | GET | List available server-log archive files |
| `/instances/<id>/chat-logs` | GET | Fetch chat logs (`?filter_mode=`, `?since=`, `?lines=`, `?filename=`) |
| `/instances/<id>/chat-logs/list` | GET | List available chat log files |

`filename` on `/instances/<id>/remote-logs` defaults to `server.log` and must match `\Aserver\.log(-\d{8}-\d{6}(\.gz)?)?\Z` — the exact set of names logrotate produces for the rotated server log. The anchors are `\A`/`\Z` rather than `^`/`$` deliberately: with `.match()` (used by the Ansible/Jinja listing filter), `$` still accepts a trailing newline, which `\Z` does not. For `server.log`, `filter_mode=lines` and `filter_mode=time` query journald, while `filter_mode=all` reads the current size-bounded exported file. For a dated archive, `lines` and `all` read the selected file; `time` is rejected with 400 because a rotated file has no journald time range to query.

### Create Instance Request
```json
{
  "name": "duel-server-1",
  "host_id": 1,
  "port": 27960,
  "hostname": "My Duel Server",
  "lan_rate_enabled": false,
  "redis_db": 3,
  "zmq_stats_password": "Kp3-xR_9vT=2wQ",
  "zmq_rcon_password": "aB7_zQ2-mN4kLp",
  "configs": {
    "server.cfg": "...",
    "mappool.txt": "...",
    "access.txt": "...",
    "workshop.txt": "",
    "custom.cfg": "...",
    "custom_entities/items.ent": "..."
  },
  "config_folders": ["custom_entities"],
  "checked_plugins": ["balance", "server_status"],
  "draft_id": "79e69985-8998-4881-a8ce-1f4fba712fe9",
  "enabled_hooks": ["ql_netfix.so"],
  "factories": {
    "duel.factories": "{...}"
  }
}
```

`configs` is a filename-to-content map. Flat filenames use `.cfg` or `.txt` extensions. Nested paths (up to 3 folders deep, e.g. `a/b/c/items.ent` — 4 path segments total including the filename) use the `.ent` extension and are written inside the corresponding subfolder. The protected files `server.cfg`, `mappool.txt`, `access.txt`, and `workshop.txt` are always required by update flows; create fills any missing protected file from the default preset. Custom config files are allowed.

`config_folders` is an optional list of folder paths (nested up to 3 path segments deep) to create alongside the `configs` map. Folder names must not collide with the reserved names `scripts`, `factories`, or `user-hooks` — checked at every segment, not just the top level — and may not start with `.`. If omitted by an older client, existing folders on disk are left untouched. Invalid `config_folders` are rejected with 400 before any database write occurs.

`checked_plugins` is a list of plugin names used to build the instance `qlx_plugins` value. `draft_id` is optional and commits a plugin draft workspace into the instance — its sibling `user-hooks/` directory is copied to the instance's `user-hooks/` directory alongside `scripts/`. The legacy `scripts` payload is no longer accepted on create. `factories` is optional; when omitted, QLSM copies default factories for legacy compatibility. When present, QLSM deploys exactly the provided flat `.factories` map.

`enabled_hooks` is an optional list of `.so` filenames (typically a preset's `enabled_hooks`) to enable in LD_PRELOAD order. QLSM filters it to hook files that actually exist in the instance's `user-hooks/` directory after the draft copy step and fully replaces `ld_preload_hooks` with the filtered list — filenames that don't correspond to a copied hook file are silently dropped, never surfaced as an error.

`redis_db` is an optional integer, range 1-8 (`MAX_INSTANCES_PER_HOST`). Omitted means the instance's Redis DB is derived from its port at read time (`resolve_redis_db()`), matching every instance created before this field existed. Out-of-range or non-integer values are rejected with 400. Duplicates on the same host are allowed — there is no uniqueness check, since sharing a DB across instances is a deliberate, supported choice. Selection happens only at creation; there is no path to change it afterward.

`zmq_stats_password` and `zmq_rcon_password` are optional. When both are omitted or blank, QLSM generates them at deploy time, which is the behavior of every instance created before these fields existed. When supplied they are stored on the instance at creation and the deploy-time generator leaves them untouched. Both must be supplied together — sending only one is rejected with 400. Each must be 8 to 64 characters drawn from letters, digits, `-`, `_`, and `=`; that is the same alphabet QLSM's generator uses, chosen because a wider set gets mangled by the shell, Ansible extra-vars, or Quake argument parsing on the way to the systemd unit. The two values are allowed to be identical.

### Update LAN Rate Request
```json
{
  "lan_rate_enabled": true
}
```

`lan_rate_enabled: true` is accepted only when the instance host has detected `host_os_type = "debian"`. Ubuntu hosts and hosts with missing or unrecognized OS type reject new enables. Legacy instances that already have `lan_rate_enabled = true` can still disable it through the same endpoint or the config-save flow.

### Update LAN Rate Response (202 Accepted)
```json
{
  "message": "LAN rate mode enabled for instance \"duel-server-1\". Reconfiguration task queued.",
  "data": {
    "id": 1,
    "name": "duel-server-1",
    "lan_rate_enabled": true,
    "status": "configuring",
    ...
  }
}
```

### Instance Response (GET /instances/<id>)
```json
{
  "data": {
    "id": 1,
    "name": "duel-server-1",
    "host_id": 1,
    "host_name": "my-host-1",
    "host_ip_address": "144.202.73.249",
    "host_os_type": "debian",
    "host_runtime": "minqlx",
    "port": 27960,
    "hostname": "My Duel Server",
    "lan_rate_enabled": false,
    "qlx_plugins": "plugin1,plugin2",
    "ld_preload_hooks": "highfps_hook.so,timer_hook.so",
    "redis_db": 1,
    "zmq_rcon_port": 27961,
    "zmq_rcon_password": "...",
    "zmq_stats_port": 27962,
    "zmq_stats_password": "...",
    "config": null,
    "status": "running",
    "logs": "...",
    "created_at": "2026-01-20T12:00:00",
    "last_updated": "2026-01-20T12:00:00"
  }
}
```

`host_runtime` is read-only, mirrors the parent host's `runtime`, and is not a column on the instance itself — it exists so the frontend can show which minqlx fork the instance runs without a second lookup.

### Config Files Response (GET /instances/<id>/config)
```json
{
  "data": {
    "server.cfg": "set sv_hostname \"My Server\"\n...",
    "mappool.txt": "campgrounds\nbloodrun\n...",
    "access.txt": "",
    "workshop.txt": "",
    "custom.cfg": "...",
    "custom_entities/items.ent": "...",
    "config_folders": ["custom_entities", "empty_dir"],
    "factories": {
      "duel.factories": "{...}"
    }
  }
}
```

`config_folders` is returned alongside the flat `configs` map. It lists every managed subfolder present in the instance config directory, nested up to 3 levels deep (excluding the reserved `scripts`, `factories`, and `user-hooks` folders).

`PUT /instances/<id>/config` accepts the same generic `configs` map plus optional top-level `name`, `hostname`, `lan_rate_enabled`, `checked_plugins`, `draft_id`, `enabled_hooks`, `factories`, `config_folders`, and `restart`. When `configs` is present, QLSM syncs the managed config set and removes unprotected `.cfg`/`.txt` files omitted from the map. When `config_folders` is present, QLSM reconciles subfolders at any depth up to 3 levels: creating any listed that are missing, and removing any that are no longer listed (provided they contain only managed `.ent`/`.cfg`/`.txt` files — folders with unmanaged content are preserved). When `config_folders` is omitted entirely, existing subfolders are left untouched. When `factories` is omitted, existing factories are preserved; when it is present, omitted `.factories` files are removed. When `draft_id` is present, its `user-hooks/` directory is copied into the instance's `user-hooks/` directory. When `enabled_hooks` is present (typically from a loaded preset), `ld_preload_hooks` is fully replaced with that list filtered to hooks that actually exist on disk after the copy — same replace-on-load semantics as `checked_plugins`/`checked_factories`. When `enabled_hooks` is omitted, the instance's current hook enablement (managed separately via the Hooks tab) is left untouched.

### LD_PRELOAD Hooks

```
GET /api/instances/<id>/hooks
```

Returns `.so` files in the instance `user-hooks/` directory (falling back to
`scripts/` for legacy instances) with enabled state, order, file metadata,
BinaryMetadata description, and active system hooks.

```json
{
  "data": {
    "available": [
      {
        "filename": "highfps_hook.so",
        "size": 16384,
        "modified": 1716300000,
        "enabled": true,
        "order": 1,
        "description": "High FPS timing hook"
      }
    ],
    "system_hooks_active": []
  }
}
```

Hook enable/order changes are saved through the shared config endpoint:

```http
PUT /api/instances/<id>/config
```

```json
{
  "configs": { "server.cfg": "...", "mappool.txt": "...", "access.txt": "...", "workshop.txt": "..." },
  "enabled_hooks": ["highfps_hook.so", "timer_hook.so"],
  "restart": true
}
```

`enabled_hooks` replaces the ordered LD_PRELOAD hook list after filtering to
`.so` basenames that exist in the instance `user-hooks/` directory. Running
instances with changed hooks are forced to restart even if a client submits
`"restart": false`; stopped instances with hook-only changes are applied with
`restart=false` and remain stopped.

### Hook File CRUD

Per-file operations on `user-hooks/` files. All mutating endpoints hold a
30-second per-instance lock and return `409` if the lock is unavailable.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/instances/<id>/hooks/files` | POST | Upload a new `.so` file (multipart `file` field) |
| `/instances/<id>/hooks/files/<filename>` | PUT | Replace an existing hook file |
| `/instances/<id>/hooks/files/<filename>` | GET | Download a hook file |
| `/instances/<id>/hooks/files/<filename>` | PATCH | Rename a hook file (JSON `{"new_name": "..."}`) |
| `/instances/<id>/hooks/files/<filename>` | DELETE | Delete a hook file |
| `/instances/<id>/hooks/files/<filename>/description` | PATCH | Set description (JSON `{"description": "..."}`) |

Upload and replace validate ELF magic (`\x7fELF`) and reject files exceeding
the binary size limit. Rename cascades to `ld_preload_hooks` and
`BinaryMetadata`. Delete also cascades. Description updates do not require a
lock and return `200` immediately.

## Server Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/server-status` | GET | Live status map keyed by instance ID |
| `/server-status/workshop-preview/<workshop_id>` | GET | Resolve Steam workshop preview URL (cached) |

### Server Status Response
```json
{
  "data": {
    "5": {
      "map": "uprise",
      "gametype": "ca",
      "state": "warmup",
      "maxplayers": 16,
      "players": [],
      "workshop_item_id": "2358556636",
      "updated": 1772870000
    }
  }
}
```

### Workshop Preview Response
```json
{
  "data": {
    "workshop_id": "2358556636",
    "preview_url": "https://images.steamusercontent.com/ugc/...",
    "source": "cache"
  }
}
```

## Draft Workspaces

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/drafts` | POST | Create a plugin draft seeded from a preset or instance |
| `/drafts/<draft_id>` | DELETE | Discard a draft workspace |
| `/drafts/<draft_id>/touch` | POST | Refresh draft mtime during long edit sessions |
| `/drafts/<draft_id>/tree` | GET | Get the draft plugin file tree |
| `/drafts/<draft_id>/content` | GET | Read a draft `.py` or `.txt` file (`?path=`) |
| `/drafts/<draft_id>/content` | PUT | Write a draft `.py` or `.txt` file |
| `/drafts/<draft_id>/upload` | POST | Upload `.py`, `.txt`, `.so`, or a font file into the draft |
| `/drafts/<draft_id>/file` | GET | Download an allowed draft file as raw bytes (`?path=`) |
| `/drafts/<draft_id>/file` | DELETE | Delete a draft file (`?path=`) |
| `/drafts/<draft_id>/rename` | PATCH | Rename a draft file without changing its extension |
| `/drafts/<draft_id>/folders` | POST | Create a folder inside the draft scripts directory |
| `/drafts/<draft_id>/folders` | DELETE | Delete a folder (recursive) inside the draft scripts directory |
| `/drafts/<draft_id>/folders` | PATCH | Rename a folder inside the draft scripts directory |
| `/drafts/<draft_id>/commit` | POST | Commit the draft to an instance or preset and delete the draft |
| `/drafts/<draft_id>/binary-meta` | GET | Get the description for a `.so` file in a preset or instance context |
| `/drafts/<draft_id>/binary-meta` | PATCH | Create or update the description for a `.so` file in a preset or instance context |
| `/drafts/<draft_id>/hooks` | POST | Upload a `.so` `LD_PRELOAD` user-hook into the draft's `user-hooks/` dir |
| `/drafts/<draft_id>/hooks/<filename>` | DELETE | Remove a `.so` user-hook from the draft's `user-hooks/` dir |

Drafts are temporary server-side plugin workspaces under `/tmp/qlds-drafts/<uuid>/scripts/`. They are used by the unified plugin file manager so file changes can be staged before an instance or preset save commits them. Stale drafts are cleaned up after one hour unless touched.

### Create Draft Request
```json
{
  "source": "preset",
  "preset": "default"
}
```

Instance source:

```json
{
  "source": "instance",
  "host": "duel-host",
  "instance_id": 3
}
```

### Create Draft Response (201 Created)
```json
{
  "data": {
    "draft_id": "79e69985-8998-4881-a8ce-1f4fba712fe9"
  }
}
```

### Draft File Tree Response
```json
{
  "data": [
    {
      "name": "balance.py",
      "type": "file",
      "path": "balance.py",
      "file_type": "python",
      "size": 1234,
      "last_modified": 1772870000.0
    },
    {
      "name": "native",
      "type": "folder",
      "path": "native",
      "children": [
        {
          "name": "hook.so",
          "type": "file",
          "path": "native/hook.so",
          "file_type": "binary",
          "size": 4096,
          "last_modified": 1772870000.0
        }
      ]
    }
  ]
}
```

Draft paths must be relative paths inside the draft. Text reads and writes support `.py` and `.txt` up to 256 KB. Raw file downloads preserve the stored bytes and return the file as an attachment. Uploads support `.py`, `.txt`, and ELF `.so` files (`.so` capped at 10 MB), plus 13 font extensions — `.ttf`, `.otf`, `.ttc`, `.otc`, `.woff`, `.woff2`, `.eot`, `.fon`, `.fnt`, `.pfb`, `.pfa`, `.pfm`, `.afm` — capped at 25 MB each. `.ttf`/`.otf`/`.ttc`/`.otc`/`.woff`/`.woff2`/`.pfb`/`.afm` uploads are additionally checked against their expected file signature; the remaining font extensions have no reliable signature and are validated by extension and size only. File paths (content, download, upload, rename, delete) may have at most 4 path segments (3 folders + filename); folder-only paths (the `/folders` endpoints below) may have at most 3 segments.

### Rename Draft File Request
```json
{
  "old_path": "native/old_hook.so",
  "new_path": "native/new_hook.so",
  "context_type": "preset",
  "context_key": "default"
}
```

`context_type` and `context_key` are required only when renaming `.so` files so binary metadata can be moved with the file. Renames cannot change file extensions and cannot overwrite an existing path.

### Draft Folder Endpoints

```
POST /drafts/<draft_id>/folders
{"path": "a/b/c"}
```

```
DELETE /drafts/<draft_id>/folders?path=a/b/c
```

```
PATCH /drafts/<draft_id>/folders
{"old_path": "a/b/c", "new_path": "a/b/d"}
```

Folder paths are limited to 3 path segments (e.g. `a/b/c`). Each segment must
match `[A-Za-z0-9._-]+`, be 64 characters or fewer, and not start with `.`.
Create returns `201` with `{"data": {"path": "..."}}`; delete recursively
removes the folder and returns `200`; rename returns `200` with
`{"data": {"old_path": "...", "new_path": "..."}}`. Errors: `400` (invalid
draft id or path), `404` (draft or folder not found), `409` (create/rename
target already exists).

### Commit Draft Request
```json
{
  "target": "instance",
  "host": "duel-host",
  "instance_id": 3
}
```

Preset target:

```json
{
  "target": "preset",
  "preset": "duel-config"
}
```

### Get Binary Metadata Request
```
GET /drafts/<draft_id>/binary-meta?path=plugins/hook.so&context_type=preset&context_key=default
```

Returns an empty description when no row exists.

```json
{
  "data": {
    "description": ""
  }
}
```

### Save Binary Metadata Request
```json
{
  "path": "plugins/hook.so",
  "description": "Fast movement hook",
  "context_type": "instance",
  "context_key": "3"
}
```

Descriptions are trimmed, may be empty, must be 1000 characters or fewer, and cannot contain `<`, `>`, `{`, `}`, or `"`. `context_type` must be `preset` or `instance`; `context_key` cannot contain path separators or `..`; `path` must end in `.so`.

### Upload Draft User-Hook Request

```
POST /drafts/<draft_id>/hooks
Content-Type: multipart/form-data

file=<binary .so upload>
```

Stages an `LD_PRELOAD` `.so` hook in the draft's `user-hooks/` directory before an instance exists (the directory is copied into the instance on create). Reuses the same filename rules as instance hook uploads (`.so` extension, no path/control characters, not one of `RESERVED_HOOK_FILENAMES`) and the same 10 MB / ELF-header validation as other draft binary uploads.

### Upload Draft User-Hook Response (201 Created)
```json
{
  "data": {
    "filename": "hook.so",
    "size": 4096,
    "modified": 1772870000,
    "enabled": false,
    "order": null,
    "description": ""
  }
}
```

Errors: `400` (invalid draft id, bad filename/extension, non-ELF content, empty file, oversize file), `404` (draft not found), `409` (a hook with that filename already exists in the draft).

### Delete Draft User-Hook

```
DELETE /drafts/<draft_id>/hooks/<filename>
```

Removes a `.so` file from the draft's `user-hooks/` directory. Returns `204 No Content` on success, `400` for an invalid draft id or filename, `404` if the draft or the file does not exist.

## Factory Files

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/factories/tree` | GET | List available `.factories` files for a preset or instance |
| `/factories/content` | GET | Read one `.factories` file |

Factory reads are used by the file manager to browse a preset or instance factory set before the user selects or edits files.

```
GET /factories/tree?preset=default
GET /factories/tree?host=duel-host&instance_id=3
GET /factories/content?preset=default&path=duel.factories
```

### Factory Content Response
```json
{
  "data": {
    "path": "duel.factories",
    "content": "{...}"
  }
}
```

## Presets

Config presets are stored on the filesystem at `configs/presets/<name>/`. The database stores metadata (name, description, path) while config files are read/written to disk.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/presets` | GET | List all presets (metadata only) |
| `/presets` | POST | Create preset (saves to filesystem) |
| `/presets/<id>` | GET | Get preset with config content (reads from filesystem); accepts optional `target_runtime` to filter plugins for cross-runtime compatibility (see below) |
| `/presets/<id>` | PUT | Update preset |
| `/presets/<id>` | DELETE | Delete preset (removes DB record + folder) |
| `/presets/<id>/download` | GET | Download preset export |
| `/presets/import` | POST | Import preset from export ZIP |
| `/presets/validate-name` | GET | Check preset name availability |

### Validate Name Request
```
GET /presets/validate-name?name=my-preset
```

### Validate Name Response
```json
{
  "data": {
    "is_valid": true,
    "error": null
  }
}
```

### Create Preset Request
```json
{
  "name": "duel-config",
  "description": "Standard duel settings",
  "configs": {
    "server.cfg": "set sv_hostname \"Duel Server\"...",
    "mappool.txt": "aerowalk\ncampgrounds\n...",
    "access.txt": "",
    "workshop.txt": "",
    "duel.cfg": "..."
  },
  "draft_id": "79e69985-8998-4881-a8ce-1f4fba712fe9",
  "checked_plugins": ["balance.py", "server_status.py"],
  "factories": {
    "duel.factories": "{...}"
  },
  "checked_factories": ["duel.factories"],
  "enabled_hooks": ["ql_netfix.so"],
  "lan_rate_enabled": true,
  "runtime": "minqlx",
  "binary_meta_source": {
    "context_type": "preset",
    "context_key": "default"
  }
}
```

`configs` is the preferred format for preset writes. It accepts flat `.cfg` and `.txt` filenames and syncs the preset config set, removing unprotected config files omitted from the map. The protected baseline files `server.cfg`, `mappool.txt`, `access.txt`, and `workshop.txt` cannot be removed. The legacy keys `server_cfg`, `mappool_txt`, `access_txt`, and `workshop_txt` are still accepted for compatibility, but they are partial writes and do not support custom files.

`factories` is a flat `.factories` filename-to-content map and syncs the preset factory set. `checked_plugins` must be a list of strings; entries that are not root-level `.py` files (anything containing `/`, or `__init__.py`) are silently stripped rather than rejected, because minqlx loads every `qlx_plugins` entry as a top-level module and cannot load those. This stripping applies uniformly to preset create, update, and import. `checked_factories` must be a list of `.factories` filenames. `draft_id` copies staged plugin files into the preset without deleting the draft, so the form can continue editing after saving — its sibling `user-hooks/` directory is merge-copied into the preset's `user-hooks/` directory the same way. On `PUT /presets/<id>`, a draft that was created with a `target_runtime` differing from its source (see [Cross-Runtime Compatibility](#cross-runtime-compatibility-target_runtime)) holds the *target* runtime's plugin set, not the preset's; overwriting a preset with such a draft returns `400 Bad Request` rather than silently replacing a minqlx preset's plugins with minqlxtended ones. Save it as a new preset instead.

`enabled_hooks` is an optional list of `.so` filenames (LD_PRELOAD order) recording which of the preset's `user-hooks/` files should be enabled when the preset is loaded onto an instance. It must be a list of `.so` filenames. When saving a preset from an instance's current state, the frontend populates this from that instance's currently-enabled hooks. `null`/absent means the preset predates this feature or was saved without any hooks captured.

`lan_rate_enabled` is an optional boolean recording whether [99k LAN Rate](user/features/99k-lan-rate.md) was enabled on the instance the preset was saved from. It must be `true` or `false` if present. `null`/absent means the preset predates this feature. On load, the frontend applies the saved value to the target's LAN rate toggle unless the value is `null`, in which case the target's current toggle is left untouched.

`binary_meta_source` is optional on `POST /presets` and `PUT /presets/<id>`. When provided, matching `.so` file descriptions are copied from the source context into the target preset context. Use this when saving an instance or another preset as a new preset.

`runtime` is optional and records which minqlx fork (`"minqlx"` or `"minqlxtended"`) the preset was saved from — the frontend sends the host or instance's current runtime here. `400` if present and not one of the two valid values. On `POST /presets` (create), an absent value defaults to `"minqlx"`. On `PUT /presets/<id>` (update), the semantics are different and deliberately so: an absent `runtime` key means **leave unchanged**, not "reset to minqlx" — `update_preset_api` also serves plain rename/description edits that carry no originating host and no `runtime` key at all, and defaulting an absent value there would silently downgrade an existing minqlxtended preset back to minqlx on an unrelated save. Send the key only when you intend to set it.

### Download Preset Export

`GET /api/presets/{preset_id}/download`

Downloads the saved preset as a ZIP archive. The archive contains the full saved preset directory, including configuration files, custom config folders, factories, scripts, user hooks, selection JSON files (`checked_plugins.json`, `checked_factories.json`, `enabled_hooks.json`, `lan_rate_enabled.json`), and generated export metadata — the `manifest.json`'s `preset` object includes `runtime`, so an imported archive round-trips which fork the preset was saved from.

Responses:

- `200 OK` — `application/zip` attachment named `<safe-preset-name>.zip`
- `403 Forbidden` — built-in presets cannot be downloaded
- `404 Not Found` — preset id does not exist
- `500 Internal Server Error` — preset directory is missing, invalid, or archive generation failed

### Import Preset Export

`POST /api/presets/import`

Imports a preset from a previously exported ZIP archive. The archive must contain a `manifest.json` with `type: "qlsm-preset-export"` and all four base config files: `server.cfg`, `mappool.txt`, `access.txt`, and `workshop.txt`. The archive's `checked_plugins.json` goes through the same root-level-only stripping described above, so an older export containing subfolder or `__init__.py` entries comes back with those dropped.

Multipart form fields:

- `file` (required) — `.zip` archive, maximum 150 MB.
- `name` (optional) — import under this preset name instead of the manifest name.
- `overwrite_preset_id` (optional) — replace an existing non-built-in preset's contents.

Responses:

- `201 Created` — new preset created. Body matches the preset response shape, including metadata, configs, scripts, factories, and checked selections.
- `200 OK` — existing preset overwritten. Body matches the preset response shape.
- `400 Bad Request` — invalid request, corrupt archive, failed archive validation, or invalid explicit `name`.
- `403 Forbidden` — `overwrite_preset_id` targets a built-in preset.
- `404 Not Found` — `overwrite_preset_id` targets a missing preset.
- `409 Conflict` — manifest name conflicts or is invalid. Body includes `conflict`: `{"type": "duplicate"|"builtin"|"invalid", "name": "...", "preset_id": <id>}` where `preset_id` is present only for duplicate user presets. Resubmit with `name` or `overwrite_preset_id`.

### Preset Response (GET /presets/<id>)
```json
{
  "data": {
    "id": 1,
    "name": "duel-config",
    "description": "Standard duel settings",
    "path": "configs/presets/duel-config",
    "runtime": "minqlx",
    "server_cfg": "...",
    "mappool_txt": "...",
    "access_txt": "...",
    "workshop_txt": "",
    "configs": {
      "server.cfg": "...",
      "mappool.txt": "...",
      "access.txt": "...",
      "workshop.txt": "",
      "duel.cfg": "..."
    },
    "factories": {
      "duel.factories": "{...}"
    },
    "scripts": {
      "balance.py": "..."
    },
    "checked_plugins": [],
    "checked_factories": [],
    "enabled_hooks": [],
    "lan_rate_enabled": null,
    "user_hooks": [
      { "filename": "ql_netfix.so", "size": 15880, "modified": 1737374400, "description": "", "enabled": false, "order": null, "missing": false }
    ],
    "last_updated": "2026-01-20T12:00:00",
    "created_at": "2026-01-20T12:00:00"
  }
}
```

`user_hooks` lists the `.so` files present in the preset's `user-hooks/` directory (shape mirrors the per-instance hooks endpoint; `enabled`/`order` are always unset here — the client derives enabled state from `enabled_hooks`). It is `[]` when the preset has no `user-hooks/` directory. The Add-Instance Hooks tab uses this list — together with `enabled_hooks` — to show a preset's hooks, their order, and enabled/disabled status before any instance exists.

For legacy presets, `checked_plugins`, `checked_factories`, or `enabled_hooks` may be `null`. A `null` `checked_factories` value means the preset predates explicit factory selection, so all files in `factories/` are treated as selected for compatibility. A `null` `enabled_hooks` value means the preset was saved without recording hook enablement — loading it does not touch the target instance's current `ld_preload_hooks`.

`scripts` values are UTF-8 text for `.py`/`.txt` files. `.so` plugin files and font files are binary, so their values are base64-encoded; write requests must send `.so` and font content the same way (raw bytes are only accepted for `.so` plugin files and font files arriving through preset ZIP import, not through this JSON API).

#### Cross-Runtime Compatibility (`target_runtime`)

`GET /api/presets/{preset_id}` accepts an optional `target_runtime` query parameter (`?target_runtime=minqlxtended`) naming the runtime the preset is about to be loaded onto. `400 Bad Request` if present and not one of `"minqlx"` / `"minqlxtended"`. Omitting it, or passing the same value as the preset's own `runtime`, returns the response exactly as documented above — `scripts` and `checked_plugins` are the preset's stored contents, and there is no `compatibility` key.

When `target_runtime` differs from the preset's `runtime`, `scripts` contains only the plugin files kept for the target runtime, `checked_plugins` drops any that were removed, and the response gains a `compatibility` block:

```json
"compatibility": {
  "preset_runtime": "minqlx",
  "target_runtime": "minqlxtended",
  "stripped": [
    {
      "path": "balance.py",
      "verdict": "incompatible",
      "reasons": ["line 1: imports the minqlx module"],
      "replacement": "balance.py"
    },
    {
      "path": "discord_extensions/admin.py",
      "verdict": "incompatible",
      "reasons": ["line 11: imports the minqlx module"],
      "replacement": null
    }
  ],
  "replacements": {
    "balance.py": "... file contents ..."
  }
}
```

Every `.py` file is classified, including files inside the preset's plugin subfolders (`discord_extensions/`, `extras/`) — those are stripped and reported by their full relative path, as the example above shows. `.so` hook binaries, `.txt` files, and fonts are always kept as-is. `stripped` lists every removed plugin file, sorted by path. `verdict` is `"incompatible"` when a specific reason was found, or `"unknown"` when nothing conclusive was found and the file was removed rather than assumed safe (`reasons` is `[]` in that case).

`replacement` is only ever the entry's **own** filename, offered when the target runtime ships a plugin by that exact name, and `null` otherwise. A replacement is never a differently-named plugin: `mybalance.py` is not offered `balance.py`, because they are not the same plugin. Only root-level files are ever offered one — a file inside a plugin subfolder always reports `replacement: null`, since swapping in the target's root-level `balance.py` for a stripped `extras/balance.py` would relocate the file as well as replace it. `replacements` maps each offered filename to its file content, so the caller can apply it without a second request.

### Preset Name Validation
- Pattern: `^[a-zA-Z0-9_-]+$` (letters, numbers, hyphens, underscores)
- Reserved names: `default`
- Must be unique

## Settings

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/settings/api-key` | GET | Get the current external API key (`null` if none exists) |
| `/settings/api-key` | POST | Delete any existing key and generate a new one |
| `/settings/api-key` | DELETE | Revoke (delete) the current API key |
| `/settings/vultr-key` | GET | Get the configured Vultr API key |
| `/settings/vultr-key` | PUT | Set (or clear) the Vultr API key |
| `/settings/backup/export` | POST | Export the full instance state as a downloadable `.qlsmbak` archive |
| `/settings/backup/import` | POST | Wipe and restore the full instance state from an uploaded `.qlsmbak` archive |

### Get / Set Vultr API Key

```
GET /api/settings/vultr-key
PUT /api/settings/vultr-key
```

`GET` returns the key currently in effect — the DB-backed value if one has been saved, otherwise the `VULTR_API_KEY` value from `.env` (see [Vultr Cloud Deployment](user/getting-started/add-host.md)):

```json
{
  "data": { "key": "ABCDEF0123456789..." }
}
```

`key` is `null` if neither a DB value nor an `.env` value is set. `PUT` request body:

```json
{
  "key": "ABCDEF0123456789..."
}
```

An empty string clears the DB-backed value, falling back to `.env` again (if set). `400` if `key` is not a string. Saving through this endpoint is what makes the Vultr key travel with a [backup export](#export-backup).

### Export Backup

```
POST /api/settings/backup/export
```

Request body — password is optional:

```json
{
  "password": "correct horse battery staple"
}
```

Omit `password` or send `null`/`""` to export unencrypted. On success, returns the archive itself as a `application/octet-stream` file download (`Content-Disposition: attachment; filename="qlsm-backup-<timestamp>.qlsmbak"`), not a JSON body.

The archive contains the full database (hosts, instances, users, preset metadata, the external API key, app settings including the Vultr API key, plugin binary metadata) plus SSH keys, Terraform state, instance configs, non-builtin presets, and plugin binaries from disk. `REDIS_PASSWORD` and `SECRET_KEY` are intentionally excluded — each host generates its own, and a mismatch after restore only requires signing in again.

Responses:

- `200 OK` — archive file download.
- `400 Bad Request` — `password` was provided but is not a string.
- `409 Conflict` — a background task currently holds a lock (e.g. Terraform/Ansible mid-run); retry once it finishes.
- `500 Internal Server Error` — archive build failed.

### Import Backup

```
POST /api/settings/backup/import
Content-Type: multipart/form-data
```

Multipart form fields:

- `file` (required) — a `.qlsmbak` archive, maximum 500 MB.
- `password` (optional) — required only if the archive was exported with one.

This **wipes and replaces** this QLSM instance's entire database and every managed file tree listed under [Export Backup](#export-backup) with the contents of the archive. A local pre-restore safety snapshot is written to `backup_snapshots/` on the server first, but there is no way to trigger a rollback to it from the UI. All existing sessions are invalidated by the restored credentials, so the caller must log in again afterward.

Success response (`200 OK`):

```json
{
  "data": {
    "qlsm_version": "1.14.0",
    "created_at": "2026-08-01T12:00:00Z"
  },
  "message": "Backup restored successfully."
}
```

`qlsm_version`/`created_at` are read from the archive's manifest, letting the caller warn if the backup came from a different QLSM version than the one running.

Responses:

- `200 OK` — restore succeeded; body as above.
- `400 Bad Request` — no file/empty file, file exceeds 500 MB, wrong password, or the archive is corrupt/not a QLSM backup (`BackupDecryptError`/`BackupRestoreError`/`BackupImportError` messages are returned as-is).
- `409 Conflict` — a background task currently holds a lock; retry once it finishes.
- `500 Internal Server Error` — restore failed after validation passed; already-swapped files and the database are rolled back to their pre-restore state.

## Socket.IO RCON Events

RCON runs over the **default Socket.IO namespace** (`/`), not a dedicated
`/rcon` namespace, and there are no REST endpoints for sending RCON commands.
Every handler requires an authenticated session.

Each target is a `(host_id, instance_id)` pair. The server keeps one room per
target, `rcon:<host_id>:<instance_id>`, and relays Redis traffic from that
instance into it. Fan-out is **per instance** — commands are published to each
instance's own Redis command channel. There is no global command channel.

### Client to server

| Event | Payload | Purpose |
|-------|---------|---------|
| `rcon:join` | `{host_id, instance_id}` | Open an individual console session for one target |
| `rcon:leave` | `{host_id, instance_id}` | Close that individual session |
| `rcon:command` | `{host_id, instance_id, cmd}` | Send one command to one joined target |
| `rcon:subscribe_stats` | `{host_id, instance_id}` | Start the live game-event stream (individual console only) |
| `rcon:unsubscribe_stats` | `{host_id, instance_id}` | Stop the live game-event stream |
| `rcon:fleet_join` | `{targets: [{host_id, instance_id}]}` | Declare this connection's complete Global RCON selection |
| `rcon:fleet_targets` | `{targets: [{host_id, instance_id}]}` | Reconcile to a new complete selection |
| `rcon:fleet_command` | `{run_id, cmd, targets: [...]}` | Send one command to many joined targets |
| `rcon:fleet_leave` | `{}` | Release every fleet target held by this connection |

Fleet ownership is tracked per Socket.IO connection (SID). `rcon:fleet_join`
and `rcon:fleet_targets` are both **full reconciliations**: targets missing
from the payload are left, new ones are joined. Individual and fleet ownership
are separate, so a Global RCON session never tears down an open per-instance
console.

### Server to client

| Event | Payload | Notes |
|-------|---------|-------|
| `rcon:joined` | `{room, host_id, instance_id}` | Individual join acknowledged |
| `rcon:left` | `{room}` | Individual leave acknowledged |
| `rcon:status` | `{host_id, instance_id, status}` | `connected`, `disconnected`, or `error` |
| `rcon:message` | `{host_id, instance_id, content}` | One line of output, delivered as it arrives |
| `rcon:stats` | `{host_id, instance_id, event}` | Live game event (stats subscription only) |
| `rcon:error` | `{error, host_id, instance_id}` | Target-tagged failure |

Output is streamed **line by line** in `content`; there is no whole-response
payload and no `text` field. Messages carry no command correlation ID, so
clients attribute output by target and arrival order, not by run.

### Acknowledgements

`rcon:fleet_join`, `rcon:fleet_targets`, and `rcon:fleet_command` reply through
the Socket.IO callback with a per-target result list. `rcon:fleet_command` also
echoes the client-supplied `run_id`:

```json
{
  "run_id": "0f2c…",
  "targets": [
    {"host_id": 1, "instance_id": 11, "state": "queued"},
    {"host_id": 1, "instance_id": 12, "state": "rejected", "reason": "Fleet target is not joined"}
  ]
}
```

Dispatch is not atomic: each target is resolved and published independently,
so a single run can mix `queued` and `rejected` results. `queued` means the
command was published for delivery — it is not evidence that the command
succeeded on the server. Rejected targets are not retried.

Credentials are never included in any payload.

## External API

Base URL: `/api/v1`

The external API uses **Bearer token authentication** (not JWT cookies). Tokens are managed via the Settings page and stored as `ApiKey` records.

```
Authorization: Bearer <api_key>
```

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/instances` | GET | Bearer token | List all instances for external service integration |

- Rate limited: 200 requests/minute
- Excludes sensitive fields: `zmq_rcon_port`, `zmq_rcon_password`, `zmq_stats_port`, `zmq_stats_password`, `logs`, `config`

## Response Formats

### Success Response
```json
{
  "data": { ... },
  "message": "Optional success message"
}
```

### Error Response
```json
{
  "error": {
    "message": "Description of the error"
  }
}
```

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 202 | Accepted (async task queued) |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized |
| 404 | Not Found |
| 409 | Conflict (duplicate name, invalid state) |
| 500 | Server Error |

## Status Enums

### HostStatus
- `pending` - Initial state
- `provisioning` - Terraform running
- `provisioned_pending_setup` - Terraform done, awaiting Ansible setup
- `active` - Ready for use
- `rebooting` - Restart in progress
- `configuring` - Configuration change in progress
- `deleting` - Terraform destroy running
- `error` - Operation failed
- `unknown` - Status check failed

### InstanceStatus
- `idle` - Deployed, not running
- `deploying` - Ansible deploying
- `running` - Active and running
- `stopping` - Stop in progress
- `stopped` - Manually stopped
- `starting` - Start in progress
- `restarting` - Restart in progress
- `configuring` - Config or LAN rate change in progress
- `updated` - Config synced but service not restarted
- `deleting` - Being removed
- `error` - Operation failed
- `unknown` - Status check failed

### QLFilterStatus
- `not_installed` - QLFilter not present
- `installing` - Installation in progress
- `active` - QLFilter running
- `inactive` - QLFilter installed but not active
- `uninstalling` - Removal in progress
- `error` - Operation failed
- `unknown` - Status check failed
