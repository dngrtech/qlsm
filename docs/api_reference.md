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
| `/hosts/<id>/qlfilter/install` | POST | Install QLFilter on host |
| `/hosts/<id>/qlfilter/uninstall` | POST | Uninstall QLFilter from host |
| `/hosts/<id>/qlfilter/status` | GET | Check QLFilter status |
| `/hosts/<id>/qlfilter/refresh-status` | POST | Queue QLFilter status refresh task |
| `/hosts/<id>/logs` | GET | Get host task logs |
| `/hosts/<id>/available-ports` | GET | Get available ports on the host |
| `/hosts/<id>/update-workshop` | POST | Force workshop items update on host |
| `/hosts/<id>/auto-restart` | POST | Configure host auto-restart schedule |

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
    "workshop.txt": ""
  }
}
```

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
    "server_cfg": "set sv_hostname \"My Server\"\n...",
    "mappool_txt": "campgrounds\nbloodrun\n...",
    "access_txt": "",
    "workshop_txt": "",
    "factories": {}
  }
}
```

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
  "server_cfg": "set sv_hostname \"Duel Server\"...",
  "mappool_txt": "aerowalk\ncampgrounds\n...",
  "access_txt": "",
  "workshop_txt": "",
  "factories": {}
}
```

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
    "factories": {},
    "scripts": [],
    "checked_plugins": [],
    "last_updated": "2026-01-20T12:00:00",
    "created_at": "2026-01-20T12:00:00"
  }
}
```

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
