# Standalone Password Bootstrap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a standalone-host authentication selector that supports password-based onboarding by installing a QLSM-managed SSH key, while keeping all ongoing host management on the existing key-based path.

**Architecture:** The frontend adds an explicit `SSH key` vs `Password` selector for standalone hosts. The backend branches only at standalone host creation and connection testing: key mode keeps the current behavior, while password mode uses Paramiko to verify login, install a generated public key, and then stores only the generated private key path. Downstream inventory, Ansible, instance management, and status polling stay key-based.

**Tech Stack:** React, Vite, Vitest, Flask, SQLAlchemy, Flask-JWT-Extended, RQ, Ansible, Paramiko

---

## Notes For The Implementer

- Use the `@github` workflow for branch, commit, push, and PR handling if implementation starts. Do not merge without explicit user approval.
- `frontend-react/src/components/hosts/AddHostModal.jsx`, `frontend-react/src/components/hosts/AddHostFormFields.jsx`, and `ui/routes/host_routes.py` are already large. Keep direct edits there small and move new behavior into focused helpers/components.
- Do not add persistent password storage. `ssh_password` must exist only for the request lifecycle.
- Ask the user to review documentation updates after implementation.

### Task 1: Add Standalone SSH Bootstrap Helper

**Files:**
- Create: `ui/standalone_ssh.py`
- Modify: `requirements.txt`
- Test: `tests/test_standalone_ssh.py`

**Step 1: Write the failing tests**

Create focused tests for password login, passwordless-sudo validation, managed-key install, and managed-key cleanup using mocked Paramiko clients.

```python
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ui import standalone_ssh


def test_validate_password_login_rejects_empty_password():
    with pytest.raises(ValueError, match="SSH password is required"):
        standalone_ssh.validate_password_auth_input("")


def test_test_password_connection_requires_passwordless_sudo_for_non_root(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(standalone_ssh, "_connect_with_password", lambda **kwargs: client)
    client.exec_command.return_value = (None, MagicMock(read=lambda: b""), MagicMock(read=lambda: b"sudo failed"))
    client.recv_exit_status.return_value = 1

    ok, message = standalone_ssh.test_password_connection(
        host="203.0.113.10",
        port=22,
        username="ql",
        password="secret",
    )

    assert ok is False
    assert "passwordless sudo" in message


def test_install_managed_key_appends_public_key(monkeypatch, tmp_path):
    key_path = tmp_path / "managed_id_rsa"
    pub_path = Path(str(key_path) + ".pub")
    key_path.write_text("private")
    pub_path.write_text("ssh-rsa generated-key\n")
    client = MagicMock()
    monkeypatch.setattr(standalone_ssh, "_connect_with_password", lambda **kwargs: client)

    standalone_ssh.install_managed_key_via_password(
        host="203.0.113.10",
        port=22,
        username="root",
        password="secret",
        private_key_path=key_path,
    )

    client.exec_command.assert_called()


def test_remove_managed_key_uses_public_key_sidecar(monkeypatch, tmp_path):
    key_path = tmp_path / "managed_id_rsa"
    pub_path = Path(str(key_path) + ".pub")
    key_path.write_text("private")
    pub_path.write_text("ssh-rsa generated-key\n")
    client = MagicMock()
    monkeypatch.setattr(standalone_ssh, "_connect_with_key", lambda **kwargs: client)

    removed = standalone_ssh.remove_managed_key_via_key(
        host="203.0.113.10",
        port=22,
        username="root",
        private_key_path=key_path,
    )

    assert removed is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_standalone_ssh.py -v`

Expected: FAIL because `ui.standalone_ssh` does not exist.

**Step 3: Write minimal implementation**

Create `ui/standalone_ssh.py` with:

- Paramiko-based password connection helper
- Paramiko-based key connection helper
- password auth validation
- password login test with non-root `sudo -n true` verification
- managed public-key install into `~/.ssh/authorized_keys`
- managed-key removal using the local `.pub` sidecar

Key implementation points:

```python
import paramiko


def test_password_connection(host, port, username, password):
    client = _connect_with_password(host=host, port=port, username=username, password=password)
    try:
        if username != "root":
            _require_passwordless_sudo(client)
        return True, "Connection successful"
    except RuntimeError as exc:
        return False, str(exc)
    finally:
        client.close()


def install_managed_key_via_password(host, port, username, password, private_key_path):
    public_key = Path(f"{private_key_path}.pub").read_text().strip()
    client = _connect_with_password(host=host, port=port, username=username, password=password)
    try:
        if username != "root":
            _require_passwordless_sudo(client)
        _append_authorized_key(client, public_key)
    finally:
        client.close()
```

Add `paramiko>=3.4.0` to `requirements.txt`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_standalone_ssh.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add requirements.txt ui/standalone_ssh.py tests/test_standalone_ssh.py
git commit -m "feat: add standalone ssh bootstrap helpers"
```

### Task 2: Add Backend Route Support For Key And Password Modes

**Files:**
- Modify: `ui/routes/host_routes.py`
- Test: `tests/test_host_api_routes.py`

**Step 1: Write the failing tests**

Add tests covering:

- standalone create in key mode still works
- standalone create in password mode generates a managed key and never persists the password
- standalone create rejects missing `ssh_password` in password mode
- standalone create rejects missing `ssh_key` in key mode
- `/api/hosts/test-connection` branches by auth mode
- non-root password mode failure surfaces a passwordless-sudo message

Representative tests:

```python
@patch("ui.routes.host_routes.install_managed_key_via_password")
@patch("ui.routes.host_routes.generate_managed_standalone_keypair", return_value=("/tmp/managed", "/tmp/managed.pub"))
@patch("ui.routes.host_routes.enqueue_task")
@patch("ui.routes.host_routes.acquire_lock", return_value=True)
def test_create_standalone_host_password_bootstrap_success(...):
    response = client.post("/api/hosts/", headers=headers, json={
        "name": "password-host",
        "provider": "standalone",
        "ip_address": "203.0.113.10",
        "ssh_port": 22,
        "ssh_user": "root",
        "ssh_auth_method": "password",
        "ssh_password": "secret",
        "os_type": "debian12",
        "timezone": "UTC",
    })

    assert response.status_code == 201
    assert response.get_json()["data"]["ssh_key_path"] == "/tmp/managed"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_host_api_routes.py -k "standalone or test_connection" -v`

Expected: FAIL because the routes still assume `ssh_key`.

**Step 3: Write minimal implementation**

In `ui/routes/host_routes.py`:

- add `VALID_STANDALONE_AUTH_METHODS = {"key", "password"}`
- parse `ssh_auth_method = (data.get("ssh_auth_method") or "key").strip().lower()`
- validate exactly one active credential
- key mode: preserve current write-key behavior
- password mode:
  - generate managed keypair in `terraform/ssh-keys/<name>_standalone_id_rsa`
  - install the generated key using `install_managed_key_via_password(...)`
  - create the host with the generated private key path
  - delete generated key files on failure
- update `/test-connection` to:
  - key mode: keep the current Ansible ping path
  - password mode: call `test_password_connection(...)`

Keep the route thin by extracting small local helpers inside the module if needed:

```python
def _standalone_auth_method(data):
    method = str(data.get("ssh_auth_method", "key")).strip().lower()
    if method not in VALID_STANDALONE_AUTH_METHODS:
        return None, {"message": "SSH auth method must be 'key' or 'password'.", "status_code": 400}
    return method, None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_host_api_routes.py -k "standalone or test_connection" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add ui/routes/host_routes.py tests/test_host_api_routes.py
git commit -m "feat: support password bootstrap for standalone hosts"
```

### Task 3: Clean Up Managed Standalone Keys On Delete

**Files:**
- Modify: `ui/task_logic/standalone_host_remove.py`
- Modify: `tests/test_standalone_host_remove.py`
- Reuse: `ui/standalone_ssh.py`

**Step 1: Write the failing tests**

Add tests for:

- managed standalone host with local `.pub` attempts remote key removal before deleting the private key
- standalone host without `.pub` keeps current behavior
- remote managed-key cleanup failure only logs a warning and still deletes the row

Example:

```python
@patch("ui.task_logic.standalone_host_remove.remove_managed_key_via_key", return_value=True)
def test_remove_standalone_host_removes_managed_remote_key(mock_remove, app, tmp_path):
    key_path = tmp_path / "managed_id_rsa"
    key_path.write_text("private")
    Path(str(key_path) + ".pub").write_text("ssh-rsa generated-key\n")
    ...
    remove_standalone_host_logic(host_id)
    mock_remove.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_standalone_host_remove.py -v`

Expected: FAIL because non-self standalone delete does not yet attempt remote cleanup.

**Step 3: Write minimal implementation**

In `ui/task_logic/standalone_host_remove.py`:

- before deleting `ssh_key_path`, check for `Path(f"{ssh_key_path}.pub")`
- if the host is `provider == "standalone"` and the `.pub` file exists:
  - call `remove_managed_key_via_key(...)`
  - log success or warning
- keep self-host cleanup behavior unchanged
- continue deleting the DB row even if remote cleanup fails

Important ordering:

1. remote managed-key cleanup
2. local private key deletion
3. local `.pub` deletion
4. inventory cleanup
5. config cleanup
6. DB delete

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_standalone_host_remove.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add ui/task_logic/standalone_host_remove.py tests/test_standalone_host_remove.py
git commit -m "feat: clean up managed standalone ssh keys on delete"
```

### Task 4: Add Frontend Auth Selector And Payload Branching

**Files:**
- Create: `frontend-react/src/components/hosts/StandaloneAuthSection.jsx`
- Modify: `frontend-react/src/components/hosts/AddHostFormFields.jsx`
- Modify: `frontend-react/src/components/hosts/AddHostModal.jsx`
- Modify: `frontend-react/src/services/api.js`
- Create: `frontend-react/src/components/hosts/__tests__/StandaloneAuthSection.test.jsx`
- Modify: `frontend-react/src/components/hosts/__tests__/AddHostModal.test.jsx`

**Step 1: Write the failing tests**

Add frontend tests for:

- selector renders `SSH key` and `Password`
- password mode hides the key textarea and shows the password field
- switching auth mode resets connection state
- password mode sends `ssh_auth_method: "password"` and `ssh_password`
- key mode still sends `ssh_auth_method: "key"` and `ssh_key`

Representative tests:

```jsx
it("sends password bootstrap payload for standalone hosts", async () => {
  mocks.testHostConnection.mockResolvedValue({ success: true, message: "Connection successful" });
  mocks.createHost.mockResolvedValue({ message: "Standalone host queued." });
  render(<AddHostModal isOpen={true} onClose={vi.fn()} onHostAdded={vi.fn()} />);

  // choose standalone, fill base fields, choose password auth
  // run test connection, submit

  await waitFor(() => expect(mocks.createHost).toHaveBeenCalledWith(
    expect.objectContaining({
      provider: "standalone",
      ssh_auth_method: "password",
      ssh_password: "secret",
    })
  ));
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend-react && pnpm test -- AddHostModal StandaloneAuthSection`

Expected: FAIL because the selector and payload branching do not exist.

**Step 3: Write minimal implementation**

Create `StandaloneAuthSection.jsx` to render:

- auth mode selector
- conditional credential input
- helper copy
- test connection button and status display

Then wire it into `AddHostFormFields.jsx` so that file does not grow much more.

In `AddHostModal.jsx`:

- add `sshAuthMethod` state defaulting to `"key"`
- add `sshPassword` state defaulting to `""`
- reset connection state when auth-sensitive fields change
- clear inactive secret state on auth switch
- branch `handleTestConnection()` payload
- branch standalone submit validation
- branch standalone create payload

Expected create payloads:

```js
{
  name,
  provider: "standalone",
  ip_address,
  ssh_port,
  ssh_user,
  ssh_auth_method: "password",
  ssh_password,
  os_type,
  timezone,
}
```

```js
{
  name,
  provider: "standalone",
  ip_address,
  ssh_port,
  ssh_user,
  ssh_auth_method: "key",
  ssh_key,
  os_type,
  timezone,
}
```

`frontend-react/src/services/api.js` only needs to continue forwarding the payloads as given.

**Step 4: Run test to verify it passes**

Run: `cd frontend-react && pnpm test -- AddHostModal StandaloneAuthSection`

Expected: PASS

**Step 5: Run lint**

Run: `cd frontend-react && pnpm lint`

Expected: PASS

**Step 6: Commit**

```bash
git add frontend-react/src/components/hosts/StandaloneAuthSection.jsx frontend-react/src/components/hosts/AddHostFormFields.jsx frontend-react/src/components/hosts/AddHostModal.jsx frontend-react/src/services/api.js frontend-react/src/components/hosts/__tests__/StandaloneAuthSection.test.jsx frontend-react/src/components/hosts/__tests__/AddHostModal.test.jsx
git commit -m "feat: add standalone password bootstrap ui"
```

### Task 5: Update Docs And Run End-To-End Verification

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/api_reference.md`
- Reference: `docs/plans/2026-04-11-standalone-password-bootstrap-design.md`

**Step 1: Update architecture docs**

Document:

- standalone auth selector behavior
- password bootstrap installs a managed SSH key
- passwords are not persisted
- delete-time managed-key cleanup behavior

**Step 2: Update API reference**

Document `ssh_auth_method`, `ssh_password`, and the test-connection branching behavior.

**Step 3: Run backend verification**

Run: `pytest tests/test_standalone_ssh.py tests/test_host_api_routes.py tests/test_standalone_host_remove.py -v`

Expected: PASS

**Step 4: Run frontend verification**

Run: `cd frontend-react && pnpm test -- AddHostModal StandaloneAuthSection`

Expected: PASS

Run: `cd frontend-react && pnpm lint`

Expected: PASS

**Step 5: Commit**

```bash
git add docs/architecture.md docs/api_reference.md
git commit -m "docs: document standalone password bootstrap flow"
```
