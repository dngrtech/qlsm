# Self-Host Deployment Design

**Date:** 2026-04-10
**Status:** Approved
**Feature:** Deploy QLDS instances on the same physical machine running the QLSM Docker stack

---

## Problem

QLSM currently manages QLDS instances on remote hosts only — either Terraform-provisioned cloud VMs or user-provided standalone servers. There is no way to deploy game servers on the same physical machine that runs the QLSM Docker stack itself.

---

## Constraints

- The QLSM stack (web, worker, rcon, poller, caddy, redis) runs inside Docker containers.
- The RQ worker calls Ansible via `subprocess` from inside Docker.
- `ansible_connection: local` inside the container targets the container OS, not the host OS.
- QLDS instances run as systemd services — systemd on the host cannot be managed from inside a container without SSH or privileged namespace tricks.
- The cleanest path to full systemd access from inside Docker is SSH to the host machine over the Docker bridge network.

---

## Approach: `self` provider — auto-SSH to host gateway

Add a third provider type `self` ("QLSM Host (self)") that:

1. Auto-detects the Docker bridge gateway IP (the host machine's address reachable from inside the container).
2. Generates an SSH key pair automatically.
3. Writes the public key to the host's `~/.ssh/authorized_keys` via a bind mount.
4. Creates the host record and proceeds through the existing standalone setup flow unchanged.

No new Ansible playbooks. No new task logic. No SSH namespace hacks. Downstream instance management (deploy, restart, delete, config sync) is 100% identical to any other host.

---

## Changes Required

### 1. `docker-compose.yml`

Add one bind mount to the `x-app` anchor (shared by all services):

```yaml
- ${HOME}/.ssh:/host-ssh
```

This makes `/host-ssh/authorized_keys` inside the container resolve to `~/.ssh/authorized_keys` on the host at runtime. `${HOME}` is evaluated by Docker Compose on the host, so it always points to the correct user's home directory.

---

### 2. Backend — `ui/routes/host_routes.py`

#### `_detect_docker_host_ip() -> str`

Detects the Docker bridge gateway IP — the host machine's address from the container's perspective.

- Primary: parse `/proc/net/route` for the default gateway entry (flags field `0003`), decode the hex-encoded IP.
- Fallback: `subprocess.run(['ip', 'route', 'show', 'default'], ...)` and parse the `via <ip>` token.
- Raises `ValueError` if no gateway can be determined.

#### `_generate_self_host_keys(name: str) -> tuple[str, str]`

Generates an RSA 4096-bit SSH key pair and configures `authorized_keys`.

1. Key path: `terraform/ssh-keys/<name>_self_id_rsa`
2. Runs: `ssh-keygen -t rsa -b 4096 -f <key_path> -N ""`
3. Reads public key from `<key_path>.pub`
4. Appends public key to `/host-ssh/authorized_keys` (creates file if absent, preserves existing entries)
5. Sets permissions: `authorized_keys` → `0600`
6. Returns `(private_key_path, public_key_string)`

#### `_handle_self_host_creation(name: str, data: dict)`

Called from `add_host_api` when `provider == 'self'`.

**Input:** `name` (pre-validated), `timezone` (required), `ssh_user` (optional, defaults to `"root"`).

**Validation:**
- Timezone: existing `VALID_TIMEZONES` check.
- SSH user: strip, non-empty, no shell-injection characters.
- Uniqueness: reject with `409` if any host with `provider='self'` already exists in the database, regardless of its current status (only one self host allowed at a time; user must delete the existing self host before creating a new one).

**Flow:**
1. Validate timezone and ssh_user.
2. `_detect_docker_host_ip()` — return `500` with descriptive error if detection fails.
3. `_generate_self_host_keys(name)` — return `500` if keygen fails; clean up partial key files on error.
4. `create_host(name, provider='self', ip_address=gateway_ip, ssh_user=ssh_user, ssh_key_path=key_path, ssh_port=22, os_type='debian12', is_standalone=True, timezone=timezone, status=HostStatus.PROVISIONED_PENDING_SETUP)`
5. Return `201` with `host.to_dict()` — same response shape as all other host creation endpoints.

**Note:** Status is set directly to `PROVISIONED_PENDING_SETUP`. No async provisioning task is needed — the host machine already exists. The user clicks **Setup Host** in the UI to trigger `setup_standalone_host_logic`, which runs `setup_host.yml` via SSH to the gateway IP.

---

### 3. Backend — `ui/task_logic/standalone_host_setup.py`

#### `_generate_self_inventory(host: Host) -> str | None`

A sibling to the existing `_generate_standalone_inventory`. Generates an Ansible inventory file at `ansible/inventory/<name>_self_host.yml` using the standard SSH format:

```yaml
all:
  hosts:
    <name>:
      ansible_host: <gateway_ip>
      ansible_user: <ssh_user>
      ansible_ssh_private_key_file: <abs_key_path>
      ansible_port: 22
      ansible_ssh_common_args: '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
```

`setup_standalone_host_logic` detects `host.provider == 'self'` and calls this generator instead of `_generate_standalone_inventory`. No other changes to the task.

---

### 4. Frontend — `frontend-react/src/utils/providerData.js`

Add `self` entry:

```js
self: {
  regions: [],
  sizes: [],
  osTypes: []
}
```

---

### 5. Frontend — `frontend-react/src/components/hosts/AddHostFormFields.jsx`

Add `isSelf` branch (`provider === 'self'`). When active, show only:

- **Timezone selector** (existing component, required)
- **SSH User** text input (default: `"root"`, editable). Helper text: *"Must have passwordless sudo on this machine."* Helper text is hidden when value is `"root"`.

Info banner below provider selector when `self` is selected:

> *"Deploys game servers on this machine. SSH keys are generated and configured automatically."*

Provider label in the dropdown: **"QLSM Host (self)"**

---

### 6. Frontend — `frontend-react/src/components/hosts/AddHostModal.jsx`

Add `else if (provider === 'self')` branch in the submit handler:

- Validate: name (existing), timezone (non-empty), ssh_user (non-empty, defaults to `"root"`).
- No IP, no SSH key, no OS type validation.
- Payload:

```json
{
  "name": "<name>",
  "provider": "self",
  "timezone": "<tz>",
  "ssh_user": "<user>"
}
```

---

## Data Flow

```
User fills: name + timezone + ssh_user (default: root)
    │
    ▼
POST /api/hosts  { provider: "self", name, timezone, ssh_user }
    │
    ▼
_handle_self_host_creation()
    ├── _detect_docker_host_ip()          → e.g. "172.17.0.1"
    ├── _generate_self_host_keys(name)    → writes key + authorized_keys
    └── create_host(...)                  → status: PROVISIONED_PENDING_SETUP
    │
    ▼
Host appears in UI with "Setup" button
    │
    ▼
User clicks Setup
    │
    ▼
setup_standalone_host_logic(host_id)
    ├── _generate_self_inventory(host)    → ansible/inventory/<name>_self_host.yml
    ├── wait_for_connection (Ansible)     → SSH to 172.17.0.1:22
    └── setup_host.yml (is_standalone=true, timezone=<tz>)
    │
    ▼
Host status → ACTIVE
    │
    ▼
Instance deploy / manage — identical to any other host
```

---

## Error Handling

| Failure point | Behaviour |
|---|---|
| Gateway IP not detected | `500` — "Could not detect host machine IP. Ensure Docker bridge networking is active." |
| `ssh-keygen` fails | `500` — "SSH key generation failed." Partial key files cleaned up. |
| `authorized_keys` write fails | `500` — "Could not write to host SSH directory. Check the `/host-ssh` volume mount in docker-compose.yml." |
| Second self host attempted | `409` — "A self host already exists. Only one QLSM Host (self) is allowed." |
| SSH connection fails during setup | Existing standalone error handling — host → `ERROR`, logs preserved |

---

## Constraints & Assumptions

- Only **one** self host is allowed per QLSM installation.
- The `${HOME}/.ssh` directory must exist on the host before the Docker stack starts (standard on any Linux system with SSH installed).
- The SSH user (`root` by default) must be able to SSH in with key-based auth and run commands as root (passwordless sudo required for non-root users).
- `ssh_port` is hardcoded to `22` for self hosts — not user-configurable.
- `os_type` is stored as `debian12` in the database as a default. This is a metadata value only — `setup_host.yml` uses `gather_facts: true` to detect the actual OS at runtime, so Ubuntu 22 hosts are fully supported regardless of the stored value.
- The Docker bridge gateway is always reachable from inside the container on standard Docker bridge networking. Non-standard network configurations (e.g. `host` network mode) are out of scope.

---

## Files Changed

| File | Type of change |
|---|---|
| `docker-compose.yml` | Add one bind mount |
| `ui/routes/host_routes.py` | Add `_detect_docker_host_ip`, `_generate_self_host_keys`, `_handle_self_host_creation` |
| `ui/task_logic/standalone_host_setup.py` | Add `_generate_self_inventory`; branch in `setup_standalone_host_logic` |
| `frontend-react/src/utils/providerData.js` | Add `self` entry |
| `frontend-react/src/components/hosts/AddHostFormFields.jsx` | Add `self` form fields branch |
| `frontend-react/src/components/hosts/AddHostModal.jsx` | Add `self` submit handler branch |
| `docs/architecture.md` | Document `self` provider |
| `docs/api_reference.md` | Document `self` provider fields |

---

## Out of Scope

- Native RQ worker (no-SSH approach) — deferred, can be added later if needed.
- Multiple self hosts.
- Self host on a non-standard Docker network.
- Auto-update of the SSH user from the Docker Compose `${HOME}` resolution (the field is editable by the user).
