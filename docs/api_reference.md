# API Reference

Base URL: `/api`

## Authentication

All endpoints except `/api/auth/login` require authentication via JWT cookie.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/login` | POST | Login with username/password, sets JWT cookie |
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

Password-mode connection tests also verify passwordless sudo for non-root users because the later Ansible flow is non-interactive. Connection tests auto-detect the remote OS from `/etc/os-release` and reject unsupported releases. Ubuntu detections succeed, but the response includes a warning that `99k LAN rate` is not compatible with Ubuntu. That warning is actionable: new `99k LAN rate` enables are allowed only on Debian hosts.

Example success response:

```json
{
  "data": {
    "success": true,
    "message": "Connection successful. Detected OS: Ubuntu 24.04.2 LTS. Warning: 99k LAN rate is not compatible with Ubuntu."
  }
}
```

### Host Name Validation (RFC 1123)
- Max length: 20 characters
- Pattern: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`
- Lowercase letters, numbers, hyphens only
- Must start and end with letter or number

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
| `/instances/<id>/lan-rate` | PUT | Toggle 99k LAN rate mode |
| `/instances/<id>/logs` | GET | Get instance task logs |
| `/instances/<id>/remote-logs` | GET | Fetch live logs via Ansible (`?filter_mode=`, `?since=`, `?lines=`) |
| `/instances/<id>/chat-logs` | GET | Fetch chat logs (`?lines=`, `?filename=`) |
| `/instances/<id>/chat-logs/list` | GET | List available chat log files |

### Create Instance Request
```json
{
  "name": "duel-server-1",
  "host_id": 1,
  "port": 27960,
  "hostname": "My Duel Server",
  "lan_rate_enabled": false,
  "configs": {
    "server.cfg": "...",
    "mappool.txt": "...",
    "access.txt": "...",
    "workshop.txt": "",
    "custom.cfg": "..."
  },
  "checked_plugins": ["balance", "server_status"],
  "draft_id": "79e69985-8998-4881-a8ce-1f4fba712fe9",
  "factories": {
    "duel.factories": "{...}"
  }
}
```

`configs` is a filename-to-content map. Filenames must be flat `.cfg` or `.txt` names. The protected files `server.cfg`, `mappool.txt`, `access.txt`, and `workshop.txt` are always required by update flows; create fills any missing protected file from the default preset. Custom config files are allowed.

`checked_plugins` is a list of plugin names used to build the instance `qlx_plugins` value. `draft_id` is optional and commits a plugin draft workspace into the instance. The legacy `scripts` payload is no longer accepted on create. `factories` is optional; when omitted, QLSM copies default factories for legacy compatibility. When present, QLSM deploys exactly the provided flat `.factories` map.

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
    "port": 27960,
    "hostname": "My Duel Server",
    "lan_rate_enabled": false,
    "qlx_plugins": "plugin1,plugin2",
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

### Config Files Response (GET /instances/<id>/config)
```json
{
  "data": {
    "server.cfg": "set sv_hostname \"My Server\"\n...",
    "mappool.txt": "campgrounds\nbloodrun\n...",
    "access.txt": "",
    "workshop.txt": "",
    "custom.cfg": "...",
    "factories": {
      "duel.factories": "{...}"
    }
  }
}
```

`PUT /instances/<id>/config` accepts the same generic `configs` map plus optional top-level `name`, `hostname`, `lan_rate_enabled`, `checked_plugins`, `draft_id`, `factories`, and `restart`. When `configs` is present, QLSM syncs the managed config set and removes unprotected `.cfg`/`.txt` files omitted from the map. When `factories` is omitted, existing factories are preserved; when it is present, omitted `.factories` files are removed.

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
| `/drafts/<draft_id>/upload` | POST | Upload `.py`, `.txt`, or `.so` into the draft |
| `/drafts/<draft_id>/file` | DELETE | Delete a draft file (`?path=`) |
| `/drafts/<draft_id>/rename` | PATCH | Rename a draft file without changing its extension |
| `/drafts/<draft_id>/commit` | POST | Commit the draft to an instance or preset and delete the draft |
| `/drafts/<draft_id>/binary-meta` | GET | Get the description for a `.so` file in a preset or instance context |
| `/drafts/<draft_id>/binary-meta` | PATCH | Create or update the description for a `.so` file in a preset or instance context |

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

Draft paths must be relative paths inside the draft. Text reads and writes support `.py` and `.txt` up to 256 KB. Uploads support `.py`, `.txt`, and ELF `.so` files; `.so` uploads are capped at 10 MB.

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
| `/presets/<id>` | GET | Get preset with config content (reads from filesystem) |
| `/presets/<id>` | PUT | Update preset |
| `/presets/<id>` | DELETE | Delete preset (removes DB record + folder) |
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
  "binary_meta_source": {
    "context_type": "preset",
    "context_key": "default"
  }
}
```

`configs` is the preferred format for preset writes. It accepts flat `.cfg` and `.txt` filenames and syncs the preset config set, removing unprotected config files omitted from the map. The protected baseline files `server.cfg`, `mappool.txt`, `access.txt`, and `workshop.txt` cannot be removed. The legacy keys `server_cfg`, `mappool_txt`, `access_txt`, and `workshop_txt` are still accepted for compatibility, but they are partial writes and do not support custom files.

`factories` is a flat `.factories` filename-to-content map and syncs the preset factory set. `checked_plugins` must be a list of strings. `checked_factories` must be a list of `.factories` filenames. `draft_id` copies staged plugin files into the preset without deleting the draft, so the form can continue editing after saving.

`binary_meta_source` is optional on `POST /presets` and `PUT /presets/<id>`. When provided, matching `.so` file descriptions are copied from the source context into the target preset context. Use this when saving an instance or another preset as a new preset.

### Preset Response (GET /presets/<id>)
```json
{
  "data": {
    "id": 1,
    "name": "duel-config",
    "description": "Standard duel settings",
    "path": "configs/presets/duel-config",
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
    "last_updated": "2026-01-20T12:00:00",
    "created_at": "2026-01-20T12:00:00"
  }
}
```

For legacy presets, `checked_plugins` or `checked_factories` may be `null`. A `null` `checked_factories` value means the preset predates explicit factory selection, so all files in `factories/` are treated as selected for compatibility.

### Preset Name Validation
- Pattern: `^[a-zA-Z0-9_-]+$` (letters, numbers, hyphens, underscores)
- Reserved names: `default`
- Must be unique

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
