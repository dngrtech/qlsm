# Standalone Host Password Bootstrap UX Design

**Date:** 2026-04-11
**Status:** Ready for Implementation

## Context

Standalone host creation is currently key-only:

- the modal requires an SSH private key
- the connection test only supports key-based SSH
- standalone host creation writes the provided private key to `terraform/ssh-keys/`

That matches the rest of the system. After host creation, inventory generation, Ansible execution, instance management, and status polling all assume `Host.ssh_key_path` exists and that QLSM can continue to access the host with a key.

Because of that, "add password auth" is not safely implementable as a UI-only toggle. The product needs a password-based bootstrap path that still lands on the existing key-based operating model.

## Goals

- Add an authentication selector to the standalone host flow.
- Support password-based onboarding for operators who do not already have a usable private key.
- Keep post-create host management on the existing SSH key model.
- Avoid storing standalone host passwords in the database, logs, or long-lived config.
- Keep the standalone host UX clear about what QLSM will do with the selected credential.

## Non-Goals

- No persistent password-based host management after creation.
- No editing existing standalone hosts to switch auth modes.
- No changes to the `self` provider flow.
- No generic credential vault or encrypted secret storage layer.
- No migration of status polling, instance tasks, or Ansible runners to a password-capable credential abstraction.

## Decision

Password authentication is a bootstrap-only mode.

When the operator chooses `Password` for a standalone host:

1. QLSM tests password-based SSH connectivity.
2. On create, QLSM generates its own managed SSH keypair locally.
3. QLSM uses the supplied password once to install the generated public key on the remote host.
4. The host record is stored with the generated private key path.
5. All later automation continues to use the same key-based paths the app already expects.

This preserves the existing host lifecycle model instead of introducing a second long-lived credential type across the backend.

## Why This Approach

Two alternatives were considered:

### 1. Full ongoing password support everywhere

Rejected. It would require broad changes across:

- standalone inventory generation
- host and instance Ansible runners
- status polling SSH commands
- delete-time cleanup logic
- secret storage and redaction rules
- likely runtime dependencies such as `sshpass`

That is too much surface area for the user-facing gain.

### 2. Password bootstrap, then convert to a managed key

Chosen. It keeps the UI improvement narrow while reusing the existing operational model.

## Technical Choice

Use `paramiko` for password-based bootstrap and managed-key cleanup.

Reasons:

- avoids adding `sshpass` to the runtime image
- avoids passing passwords through shell command arguments
- keeps password handling in Python rather than shell glue
- can be reused for managed-key cleanup during standalone host deletion

## UX Model

### Form Layout

The standalone section should keep the current server details first:

1. IP address
2. SSH port
3. SSH username
4. Authentication selector
5. Conditional credential field
6. Operating system
7. Timezone
8. Test connection

The authentication selector should be a visible two-option control, not a dropdown, because this is a high-impact choice with only two modes:

- `SSH key`
- `Password`

Recommended presentation: a small segmented card/radio group with one-line supporting text under each option.

### Credential Fields

#### SSH Key mode

Keep the existing textarea + upload button UX with minimal copy changes.

#### Password mode

Show:

- a password input
- a show/hide toggle
- helper text: `Used once to install a managed QLSM SSH key. Password is not stored.`

Do not show both secret inputs at the same time.

### Non-root User Guidance

Keep the existing expectation that non-root users must already have passwordless `sudo`.

If `ssh_user !== "root"`, show the same warning regardless of auth mode:

- `Must have passwordless sudo on this machine.`

This matters because the later Ansible flow is non-interactive and already assumes that behavior.

### Connection Test Behavior

The connection test remains mandatory before `Add Host` is enabled.

#### SSH Key mode

Keep the current key-based test semantics.

#### Password mode

The test should verify:

- SSH login with the supplied password works
- if the user is not `root`, `sudo -n true` succeeds

The success state can remain the current generic `Connected`.

Failure messages should be actionable:

- invalid password / auth failed
- timed out
- host unreachable
- password login succeeded but passwordless sudo is not configured

### State Reset Rules

Changing any of the following should reset the connection test result:

- IP address
- SSH port
- SSH username
- authentication mode
- active credential input

Changing auth mode should also clear the now-inactive secret field from local component state.

## API Contract

Standalone create and test-connection requests gain an explicit auth method:

```json
{
  "ip_address": "203.0.113.10",
  "ssh_port": 22,
  "ssh_user": "root",
  "ssh_auth_method": "password",
  "ssh_password": "secret",
  "os_type": "debian",
  "timezone": "UTC"
}
```

Key mode remains:

```json
{
  "ip_address": "203.0.113.10",
  "ssh_port": 22,
  "ssh_user": "root",
  "ssh_auth_method": "key",
  "ssh_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...",
  "os_type": "ubuntu",
  "timezone": "UTC"
}
```

Rules:

- exactly one active credential is required
- inactive credentials are ignored
- passwords are never persisted

## Backend Model

No database migration is required.

The existing `Host.ssh_key_path` remains the single persisted access credential path for standalone hosts after creation.

### Key mode

Behavior stays functionally the same:

- validate request
- write the provided key to `terraform/ssh-keys/<name>_standalone_id_rsa`
- create host record with that key path
- queue existing standalone setup task

### Password mode

Behavior becomes:

1. validate request
2. generate managed keypair at `terraform/ssh-keys/<name>_standalone_id_rsa` plus `.pub`
3. use Paramiko to connect with password
4. install the public key into the target user's `~/.ssh/authorized_keys`
5. if non-root, verify passwordless sudo before host creation completes
6. create host record with the generated private key path
7. queue the existing standalone setup task

If any bootstrap step fails, delete the generated local key material before returning an error.

## Managed-Key Cleanup Model

Standalone delete behavior needs one important adjustment.

Today, non-self standalone hosts do not attempt any remote `authorized_keys` cleanup. That is correct for operator-supplied keys, because QLSM should not edit the operator's SSH setup.

For password-bootstrap hosts, QLSM owns the generated keypair and should attempt to remove its public key from the remote `authorized_keys` file before deleting the local key files.

The implementation can distinguish the two cases without a schema change:

- operator-supplied key mode writes only the private key file
- managed password-bootstrap mode creates a local `.pub` sidecar as well

Delete-time rule:

- if the standalone host has a readable `<ssh_key_path>.pub`, treat it as QLSM-managed and attempt remote key removal
- otherwise keep the current non-invasive behavior

If remote key cleanup fails, log a warning and continue deleting the host record. The operator should not be left with a zombie host row because cleanup was partial.

## Security Rules

- Never store `ssh_password` on the host model or anywhere else persistent.
- Never include the password in logs, exception messages, or API responses.
- Prefer generic auth failure messages over echoing remote stderr that may include sensitive context.
- Delete generated local key material on bootstrap failure.
- Keep the existing restricted permissions for persisted private keys.

## Testing Scope

### Backend

- route tests for `/api/hosts/` key mode and password mode
- route tests for `/api/hosts/test-connection` key mode and password mode
- helper tests for Paramiko password login, sudo verification, managed key install, and cleanup paths
- delete-task tests for managed-key remote cleanup vs operator-supplied key preservation

### Frontend

- auth selector rendering and mode switch behavior
- password vs key validation rules
- connection test payload branching
- create-host payload branching
- connection test reset when auth-sensitive fields change

## Docs Impact

Implementation should update at least:

- `docs/architecture.md`
- `docs/api_reference.md`

The post-implementation handoff should explicitly ask the user to review documentation changes, per repo guidance.
