# MinQLX Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a **View MinQLX Logs** action for QLDS instances that displays `/home/ql/qlds-<PORT>/minqlx.log` and rotated `minqlx.log.N` files with Chat Logs-style UI, but only `lines` and `all` filters.

**Architecture:** Copy the existing Chat Logs flow with narrow changes: new frontend modal/hook/API helpers, new backend endpoints/task functions, and two Ansible playbooks. Reuse existing modal styling and log viewer utilities; add a small `allowedModes` prop to `LogFilterControls` so MinQLX can hide `time` without forking the controls.

**Tech Stack:** Flask + Flask-JWT-Extended, SQLAlchemy models, Ansible playbooks, React + Vite + Headless UI + CodeMirror, Vitest, pytest.

---

## Source Documents

- Design spec: `docs/superpowers/specs/2026-07-08-minqlx-logs-design.md`
- Existing reference implementation: Chat Logs flow in `ViewChatLogsModal.jsx`, `fetch_chat_logs.yml`, `list_chat_logs.yml`, `fetch_remote_chat_logs_api`, `fetch_instance_chat_logs`, and `list_instance_chat_logs`.

## Decision Checkpoints

### Decisions already approved

- Use Approach A: copy the Chat Logs flow and change only what MinQLX needs.
- Support rotated MinQLX files: `minqlx.log`, `minqlx.log.1`, `minqlx.log.2`, ...
- Do not support `time` filtering for MinQLX logs. `time` mode is excluded from UI and rejected by the API.

### Unresolved semantics forks

None. Implementation can proceed after the repo's pre-implementation review loop closes.

### Required pre-implementation gate

The repository has `.claude/skills/pre-implementation-review-loop/SKILL.md`. Before product code changes start, run that loop using:

- Spec: `docs/superpowers/specs/2026-07-08-minqlx-logs-design.md`
- Plan: `docs/superpowers/plans/2026-07-08-minqlx-logs.md`

---

## File Structure

### Create

- `ansible/playbooks/fetch_minqlx_logs.yml` — fetch selected MinQLX log file by `lines` or `all`.
- `ansible/playbooks/list_minqlx_logs.yml` — list safe rotated MinQLX log filenames.
- `frontend-react/src/components/instances/ViewMinqlxLogsModal.jsx` — Chat Logs-style modal for MinQLX logs.
- `frontend-react/src/hooks/useViewMinqlxLogs.js` — modal state hook.
- `tests/test_minqlx_logs_validation.py` — backend validation tests.

### Modify

- `ui/routes/instance_routes.py` — add `/minqlx-logs` and `/minqlx-logs/list` endpoints.
- `ui/task_logic/ansible_instance_mgmt.py` — add MinQLX fetch/list task functions.
- `frontend-react/src/services/api.js` — add MinQLX API helpers.
- `frontend-react/src/components/instances/LogFilterControls.jsx` — add `allowedModes` support.
- `frontend-react/src/components/InstanceActionsMenu.jsx` — add **View MinQLX Logs** action.
- `frontend-react/src/components/instances/InstanceRowContent.jsx` — pass MinQLX callback.
- `frontend-react/src/components/instances/InstancesTableRow.jsx` — pass MinQLX callback.
- `frontend-react/src/pages/ServersPage.jsx` — wire hook and modal.
- `frontend-react/src/pages/__tests__/ServersPage.test.jsx` — mock new hook/modal.
- `frontend-react/src/components/__tests__/InstanceActionsMenu.test.jsx` — assert action rendering/callback.

---

## Task 1: Backend validation tests

**Files:**
- Create: `tests/test_minqlx_logs_validation.py`

- [ ] **Step 1: Write failing tests for MinQLX log API validation**

Create `tests/test_minqlx_logs_validation.py`:

```python
"""Validation tests for the minqlx-logs endpoint.

These guard GET /api/instances/<id>/minqlx-logs input handling:
filter_mode is limited to lines/all, filename is limited to minqlx.log
rotations, and rejection paths return 400 before Ansible execution.
"""
from unittest.mock import patch

from flask_jwt_extended import create_access_token

from ui import db
from ui.database import create_host, create_instance
from ui.models import HostStatus


def _make_instance(app):
    with app.app_context():
        host = create_host(name='minqlx-host', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(
            name='minqlx-inst', host_id=host.id, port=27960, hostname='minqlx.host',
        )
        db.session.commit()
        token = create_access_token(identity='testuser')
        return instance.id, token


def _headers(token):
    return {'Authorization': f'Bearer {token}'}


def _get(client, instance_id, token, **params):
    return client.get(
        f'/api/instances/{instance_id}/minqlx-logs',
        query_string=params,
        headers=_headers(token),
    )


def test_invalid_filter_mode_rejected(client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='bogus')
    assert resp.status_code == 400


def test_time_filter_mode_rejected(client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='time')
    assert resp.status_code == 400


def test_path_traversal_filename_rejected(client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='lines', filename='../../../../etc/passwd')
    assert resp.status_code == 400


def test_malformed_filename_rejected(client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='lines', filename='minqlx.log.old')
    assert resp.status_code == 400


@patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs',
       return_value=(True, 'log line', None))
def test_valid_lines_request_passes_validation(mock_fetch, client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='lines', lines=250, filename='minqlx.log.1')
    assert resp.status_code == 200
    assert resp.get_json()['data']['logs'] == 'log line'
    assert mock_fetch.call_args.kwargs['filter_mode'] == 'lines'
    assert mock_fetch.call_args.kwargs['lines'] == 250
    assert mock_fetch.call_args.kwargs['filename'] == 'minqlx.log.1'


@patch('ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs',
       return_value=(True, 'all log lines', None))
def test_valid_all_request_passes_validation(mock_fetch, client, app):
    instance_id, token = _make_instance(app)
    resp = _get(client, instance_id, token, filter_mode='all', lines=1, filename='minqlx.log')
    assert resp.status_code == 200
    assert resp.get_json()['data']['logs'] == 'all log lines'
    assert mock_fetch.call_args.kwargs['filter_mode'] == 'all'
```

- [ ] **Step 2: Run tests and verify they fail because the route/function is missing**

Run:

```bash
pytest tests/test_minqlx_logs_validation.py -v
```

Expected: tests fail with 404 responses or patch import errors for `fetch_instance_minqlx_logs`. This confirms the test is exercising missing behavior, not passing by accident.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_minqlx_logs_validation.py
git commit -m "test(instances): cover minqlx logs validation"
```

---

## Task 2: Add MinQLX Ansible playbooks

**Files:**
- Create: `ansible/playbooks/fetch_minqlx_logs.yml`
- Create: `ansible/playbooks/list_minqlx_logs.yml`

- [ ] **Step 1: Create fetch playbook**

Create `ansible/playbooks/fetch_minqlx_logs.yml`:

```yaml
---
- name: Fetch QLDS MinQLX Logs
  hosts: all
  become: yes
  gather_facts: false

  vars:
    game_port: "{{ port }}"
    log_mode: "{{ filter_mode | default('lines') }}"
    log_lines: "{{ lines | default(500) }}"
    log_filename: "{{ filename | default('minqlx.log') }}"
    log_file: "/home/ql/qlds-{{ game_port }}/{{ log_filename }}"

  tasks:
    - name: Check if MinQLX log file exists
      ansible.builtin.stat:
        path: "{{ log_file }}"
      register: log_stat

    - name: Fetch MinQLX logs by line count
      ansible.builtin.command:
        cmd: "tail -n {{ log_lines }} {{ log_file }}"
      register: minqlx_output_lines
      changed_when: false
      failed_when: false
      when: log_stat.stat.exists and log_mode == 'lines'

    - name: Fetch all MinQLX logs
      ansible.builtin.command:
        cmd: "cat {{ log_file }}"
      register: minqlx_output_all
      changed_when: false
      failed_when: false
      when: log_stat.stat.exists and log_mode == 'all'

    - name: Set output variable
      ansible.builtin.set_fact:
        minqlx_logs_output: >-
          {{ '-- MinQLX log file not found --' if not log_stat.stat.exists
             else (minqlx_output_all.stdout | default('')) if log_mode == 'all'
             else (minqlx_output_lines.stdout | default('')) }}

    - name: Output logs to stdout for capture
      ansible.builtin.debug:
        msg: "{{ minqlx_logs_output if minqlx_logs_output | length > 0 else '-- No entries --' }}"
```

- [ ] **Step 2: Create list playbook**

Create `ansible/playbooks/list_minqlx_logs.yml`:

```yaml
---
- name: List QLDS MinQLX Logs
  hosts: all
  become: yes
  gather_facts: false

  vars:
    game_port: "{{ port }}"
    log_dir: "/home/ql/qlds-{{ game_port }}"

  tasks:
    - name: Check if QLDS instance directory exists
      ansible.builtin.stat:
        path: "{{ log_dir }}"
      register: log_dir_stat

    - name: Find MinQLX log files
      ansible.builtin.find:
        paths: "{{ log_dir }}"
        patterns: "minqlx.log*"
        file_type: file
        recurse: false
      register: minqlx_log_find
      when: log_dir_stat.stat.exists

    - name: Set MinQLX log file list
      ansible.builtin.set_fact:
        minqlx_log_files: >-
          {{ (minqlx_log_find.files | default([])
              | map(attribute='path')
              | map('basename')
              | select('match', '^minqlx\\.log(\\.\\d+)?$')
              | list) }}

    - name: Output MinQLX log files to stdout for capture
      ansible.builtin.debug:
        msg: "{{ minqlx_log_files | default([]) | to_json }}"
```

- [ ] **Step 3: Run syntax checks**

Run:

```bash
ansible-playbook --syntax-check ansible/playbooks/fetch_minqlx_logs.yml
ansible-playbook --syntax-check ansible/playbooks/list_minqlx_logs.yml
```

Expected: both playbooks report `playbook: ...` with exit code 0.

- [ ] **Step 4: Commit playbooks**

```bash
git add ansible/playbooks/fetch_minqlx_logs.yml ansible/playbooks/list_minqlx_logs.yml
git commit -m "feat(ansible): add minqlx log fetch playbooks"
```

---

## Task 3: Add backend task logic and routes

**Files:**
- Modify: `ui/task_logic/ansible_instance_mgmt.py`
- Modify: `ui/routes/instance_routes.py`
- Test: `tests/test_minqlx_logs_validation.py`

- [ ] **Step 1: Add task-logic functions**

In `ui/task_logic/ansible_instance_mgmt.py`, add these functions after `list_instance_chat_logs` or beside the Chat Logs functions:

```python
def fetch_instance_minqlx_logs(instance_id, filter_mode='lines', lines=500, filename='minqlx.log'):
    """
    Fetch MinQLX logs from a remote QLDS instance via Ansible.

    Returns a tuple: (success: bool, logs: str, error_msg: str or None)
    """
    import re
    import json
    import subprocess

    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            log.error(f"Instance with id {instance_id} not found.")
            return False, "", f"Instance {instance_id} not found."

        host = instance.host
        if not host:
            log.error(f"Host not found for instance {instance.id}.")
            return False, "", "Associated host not found."

        if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
            log.error(f"Host {host.id} is missing required details for Ansible.")
            return False, "", "Host details missing (IP, SSH key, or user)."

        playbook_path = os.path.abspath('ansible/playbooks/fetch_minqlx_logs.yml')
        inventory_path = os.path.abspath('ansible/inventory/')

        extravars = {
            'port': instance.port,
            'ansible_ssh_user': host.ssh_user,
            'ansible_ssh_private_key_file': os.path.abspath(host.ssh_key_path),
            'filter_mode': filter_mode,
            'lines': lines,
            'filename': filename,
        }

        env = os.environ.copy()
        env['ANSIBLE_PIPELINING'] = 'True'
        env['ANSIBLE_REMOTE_TMP'] = '/tmp'
        env['ANSIBLE_BECOME_FLAGS'] = '-H -S -n'
        env['ANSIBLE_ALLOW_WORLD_READABLE_TMPFILES'] = 'True'

        cmd = ['ansible-playbook', playbook_path, '-i', inventory_path, '-l', host.name, '-e', json.dumps(extravars)]

        log.info(f"Fetching MinQLX logs for instance {instance_id} on host {host.name}...")

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        stdout, stderr = process.communicate(timeout=60)
        rc = process.returncode

        if rc != 0:
            log.error(f"Ansible failed to fetch MinQLX logs for instance {instance_id}. RC: {rc}. stderr: {stderr[-500:]}")
            return False, "", f"Failed to fetch MinQLX logs (RC: {rc}). Check if the instance exists on the remote host."

        lines_output = stdout.split('\n')
        in_msg = False
        msg_lines = []

        for line in lines_output:
            if '"msg":' in line:
                match = re.search(r'"msg":\s*"(.*)$', line)
                if match:
                    content = match.group(1)
                    if content.endswith('"'):
                        msg_lines.append(content[:-1])
                    else:
                        msg_lines.append(content)
                        in_msg = True
            elif in_msg:
                if line.strip().endswith('"'):
                    msg_lines.append(line.rstrip()[:-1])
                    in_msg = False
                elif line.strip() == '}':
                    in_msg = False
                else:
                    msg_lines.append(line)

        if msg_lines:
            logs = '\n'.join(msg_lines)
            logs = logs.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
        else:
            logs = "Could not parse MinQLX log output. Raw Ansible output:\n" + stdout[-1000:]

        log.info(f"Successfully fetched {len(logs)} bytes of MinQLX logs for instance {instance_id}")
        return True, logs, None

    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        log.error(f"Timeout fetching MinQLX logs for instance {instance_id}")
        return False, "", "Timeout while fetching MinQLX logs from remote host."
    except Exception as e:
        log.exception(f"Exception fetching MinQLX logs for instance {instance_id}: {e}")
        return False, "", str(e)


def list_instance_minqlx_logs(instance_id):
    """
    List available MinQLX log files from a remote QLDS instance.

    Returns a tuple: (success: bool, files: list, error_msg: str or None)
    """
    import re
    import json
    import subprocess

    try:
        instance = db.session.get(QLInstance, instance_id)
        if not instance:
            return False, [], f"Instance {instance_id} not found."

        host = instance.host
        if not host:
            return False, [], "Associated host not found."

        if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
            return False, [], "Host details missing."

        playbook_path = os.path.abspath('ansible/playbooks/list_minqlx_logs.yml')
        inventory_path = os.path.abspath('ansible/inventory/')

        extravars = {
            'port': instance.port,
            'ansible_ssh_user': host.ssh_user,
            'ansible_ssh_private_key_file': os.path.abspath(host.ssh_key_path),
        }

        env = os.environ.copy()
        env['ANSIBLE_PIPELINING'] = 'True'
        env['ANSIBLE_REMOTE_TMP'] = '/tmp'
        env['ANSIBLE_BECOME_FLAGS'] = '-H -S -n'
        env['ANSIBLE_ALLOW_WORLD_READABLE_TMPFILES'] = 'True'
        env['ANSIBLE_NOCOLOR'] = 'True'

        cmd = ['ansible-playbook', playbook_path, '-i', inventory_path, '-l', host.name, '-e', json.dumps(extravars)]

        log.info(f"Listing MinQLX logs for instance {instance_id} on host {host.name}...")

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        stdout, stderr = process.communicate(timeout=30)
        rc = process.returncode

        if rc != 0:
            log.error(f"Ansible failed to list MinQLX logs for instance {instance_id}. RC: {rc}. stderr: {stderr[-500:]}")
            return False, [], f"Failed to list MinQLX logs (RC: {rc})."

        msg_content = ""
        in_msg = False
        msg_lines = []

        for line in stdout.split('\n'):
            if '"msg":' in line:
                match = re.search(r'"msg":\s*"(.*)$', line)
                if match:
                    content = match.group(1)
                    if content.endswith('"'):
                        msg_content = content[:-1]
                    else:
                        msg_lines.append(content)
                        in_msg = True
            elif in_msg:
                if line.strip().endswith('"'):
                    msg_lines.append(line.rstrip()[:-1])
                    in_msg = False
                elif line.strip() == '}':
                    in_msg = False
                else:
                    msg_lines.append(line)

        if msg_lines:
            msg_content = '\n'.join(msg_lines)

        msg_content = msg_content.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
        files = json.loads(msg_content) if msg_content else []
        valid_files = [f for f in files if re.fullmatch(r'minqlx\.log(\.\d+)?', f)]
        valid_files.sort(key=lambda f: 0 if f == 'minqlx.log' else int(f.rsplit('.', 1)[1]))

        return True, valid_files, None

    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        log.error(f"Timeout listing MinQLX logs for instance {instance_id}")
        return False, [], "Timeout while listing MinQLX logs from remote host."
    except Exception as e:
        log.exception(f"Exception listing MinQLX logs for instance {instance_id}: {e}")
        return False, [], str(e)
```

- [ ] **Step 2: Add API routes**

In `ui/routes/instance_routes.py`, add these routes after the Chat Logs routes:

```python
@instance_api_bp.route('/<int:instance_id>/minqlx-logs', methods=['GET'], endpoint='fetch_remote_minqlx_logs_api')
@jwt_required()
def fetch_remote_minqlx_logs_api(instance_id):
    """Fetches MinQLX logs from the remote QLDS instance."""
    from ui.task_logic.ansible_instance_mgmt import fetch_instance_minqlx_logs

    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    if not instance.host:
        return jsonify({"error": {"message": "Instance has no associated host."}}), 400

    filter_mode = request.args.get('filter_mode', 'lines')
    lines = request.args.get('lines', 500, type=int)
    filename = request.args.get('filename', 'minqlx.log')

    if filter_mode not in ('lines', 'all'):
        return jsonify({"error": {"message": "filter_mode must be 'lines' or 'all'"}}), 400

    if not re.fullmatch(r'minqlx\.log(\.\d+)?', filename):
        return jsonify({"error": {"message": "Invalid MinQLX log filename."}}), 400

    if filter_mode != 'all' and (lines < 10 or lines > 10000):
        return jsonify({"error": {"message": "lines must be between 10 and 10000"}}), 400

    current_app.logger.info(
        f"Fetching MinQLX logs for instance {instance_id} ({instance.name}) - "
        f"mode: {filter_mode}, lines: {lines}, filename: {filename}"
    )

    success, logs, error_msg = fetch_instance_minqlx_logs(
        instance_id,
        filter_mode=filter_mode,
        lines=lines,
        filename=filename,
    )

    if success:
        return jsonify({
            "data": {
                "logs": logs,
                "instance_name": instance.name,
                "port": instance.port,
                "filter_mode": filter_mode,
                "lines": lines,
                "filename": filename,
            }
        })

    current_app.logger.error(f"Failed to fetch MinQLX logs for instance {instance_id}: {error_msg}")
    return jsonify({"error": {"message": error_msg}}), 500


@instance_api_bp.route('/<int:instance_id>/minqlx-logs/list', methods=['GET'], endpoint='list_remote_minqlx_logs_api')
@jwt_required()
def list_remote_minqlx_logs_api(instance_id):
    """Lists available MinQLX log files from the remote QLDS instance."""
    from ui.task_logic.ansible_instance_mgmt import list_instance_minqlx_logs

    instance = get_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found."}}), 404

    current_app.logger.info(f"Listing MinQLX logs for instance {instance_id} ({instance.name})")

    success, files, error_msg = list_instance_minqlx_logs(instance_id)

    if success:
        return jsonify({"data": {"files": files, "instance_name": instance.name}})

    current_app.logger.error(f"Failed to list MinQLX logs for instance {instance_id}: {error_msg}")
    return jsonify({"error": {"message": error_msg}}), 500
```

- [ ] **Step 3: Run backend tests**

Run:

```bash
pytest tests/test_minqlx_logs_validation.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Run nearby Chat Logs validation tests to catch route regressions**

Run:

```bash
pytest tests/test_chat_logs_validation.py tests/test_minqlx_logs_validation.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit backend implementation**

```bash
git add ui/routes/instance_routes.py ui/task_logic/ansible_instance_mgmt.py tests/test_minqlx_logs_validation.py
git commit -m "feat(api): add minqlx log endpoints"
```

---

## Task 4: Add frontend API helpers and filter-control mode limiting

**Files:**
- Modify: `frontend-react/src/services/api.js`
- Modify: `frontend-react/src/components/instances/LogFilterControls.jsx`

- [ ] **Step 1: Add API helpers**

In `frontend-react/src/services/api.js`, add after `listInstanceChatLogs`:

```javascript
export const fetchInstanceMinqlxLogs = async (instanceId, options = {}) => {
  try {
    const { filterMode = 'lines', lines = 500, filename = 'minqlx.log' } = options;
    const params = new URLSearchParams({
      filter_mode: filterMode,
      lines: lines.toString(),
      filename: filename
    });
    const response = await apiClient.get(`/instances/${instanceId}/minqlx-logs?${params.toString()}`);
    return response.data.data; // { logs, instance_name, port, filter_mode, lines, filename }
  } catch (error) {
    console.error(`Failed to fetch MinQLX logs for instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch MinQLX logs for instance ${instanceId}`);
  }
};

export const listInstanceMinqlxLogs = async (instanceId) => {
  try {
    const response = await apiClient.get(`/instances/${instanceId}/minqlx-logs/list`);
    return response.data.data; // { files, instance_name }
  } catch (error) {
    console.error(`Failed to list MinQLX logs for instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to list MinQLX logs for instance ${instanceId}`);
  }
};
```

- [ ] **Step 2: Add `allowedModes` to shared filter controls**

Change `frontend-react/src/components/instances/LogFilterControls.jsx` so the function signature includes `allowedModes`, and map only visible modes:

```javascript
function LogFilterControls({
    filterMode,
    setFilterMode,
    lineCount,
    setLineCount,
    timeRange,
    setTimeRange,
    onApply,
    isLoading,
    allowedModes = ['lines', 'time', 'all'],
}) {
    const visibleFilterModes = FILTER_MODES.filter((mode) => allowedModes.includes(mode.value));
```

Then change the radio loop:

```javascript
{visibleFilterModes.map((mode) => (
```

Keep the existing time range rendering guarded by `filterMode === 'time'`. Existing Server Logs and Chat Logs behavior remains unchanged because the default includes all three modes.

- [ ] **Step 3: Run frontend tests that cover existing consumers**

Run:

```bash
cd frontend-react && pnpm test -- InstanceActionsMenu.test.jsx
```

Expected: existing tests pass. If the repo's test runner uses a different script name, inspect `frontend-react/package.json` and use the existing Vitest script; do not start the dev server.

- [ ] **Step 4: Commit frontend API/control changes**

```bash
git add frontend-react/src/services/api.js frontend-react/src/components/instances/LogFilterControls.jsx
git commit -m "feat(frontend): add minqlx log api helpers"
```

---

## Task 5: Add MinQLX frontend modal and hook

**Files:**
- Create: `frontend-react/src/hooks/useViewMinqlxLogs.js`
- Create: `frontend-react/src/components/instances/ViewMinqlxLogsModal.jsx`

- [ ] **Step 1: Create modal state hook**

Create `frontend-react/src/hooks/useViewMinqlxLogs.js`:

```javascript
import { useState } from 'react';

/**
 * Shared hook for view MinQLX logs modal state management.
 * @returns {{
 *   selectedInstanceForMinqlxLogs: object|null,
 *   isViewMinqlxLogsModalOpen: boolean,
 *   openViewMinqlxLogs: (instance: object) => void,
 *   closeViewMinqlxLogs: () => void,
 * }}
 */
export function useViewMinqlxLogs() {
    const [isViewMinqlxLogsModalOpen, setIsViewMinqlxLogsModalOpen] = useState(false);
    const [selectedInstanceForMinqlxLogs, setSelectedInstanceForMinqlxLogs] = useState(null);

    const openViewMinqlxLogs = (instance) => {
        setSelectedInstanceForMinqlxLogs(instance);
        setIsViewMinqlxLogsModalOpen(true);
    };

    const closeViewMinqlxLogs = () => {
        setIsViewMinqlxLogsModalOpen(false);
        setSelectedInstanceForMinqlxLogs(null);
    };

    return { selectedInstanceForMinqlxLogs, isViewMinqlxLogsModalOpen, openViewMinqlxLogs, closeViewMinqlxLogs };
}
```

- [ ] **Step 2: Create MinQLX logs modal by copying Chat Logs behavior**

Create `frontend-react/src/components/instances/ViewMinqlxLogsModal.jsx` by copying `ViewChatLogsModal.jsx` and applying these exact semantic changes:

```javascript
import { fetchInstanceMinqlxLogs, listInstanceMinqlxLogs } from '../../services/api';
```

Use defaults:

```javascript
const [availableFiles, setAvailableFiles] = useState(['minqlx.log']);
const [selectedFile, setSelectedFile] = useState('minqlx.log');
```

Fetch logs with no `since` parameter:

```javascript
const data = await fetchInstanceMinqlxLogs(instance.id, {
    filterMode,
    lines: lineCount,
    filename: selectedFile
});
```

List files with MinQLX filename filtering and sort:

```javascript
const validFiles = data.files.filter(f => f === 'minqlx.log' || /^minqlx\.log\.\d+$/.test(f.trim()));

const sortedFiles = validFiles.sort((a, b) => {
    const sa = a.trim();
    const sb = b.trim();
    if (sa === 'minqlx.log') return -1;
    if (sb === 'minqlx.log') return 1;

    const getNum = (s) => {
        const match = s.match(/minqlx\.log\.(\d+)$/);
        return match ? parseInt(match[1], 10) : Number.MAX_SAFE_INTEGER;
    };

    return getNum(sa) - getNum(sb);
});
```

Reset state on close to:

```javascript
setSelectedFile('minqlx.log');
setAvailableFiles(['minqlx.log']);
setFilterMode('lines');
```

Use title:

```javascript
MinQLX Logs
```

Use the modal class:

```javascript
view-minqlx-logs-modal
```

Use scroll selector:

```javascript
const cmEditor = document.querySelector('.view-minqlx-logs-modal .cm-editor .cm-scroller');
```

Pass only lines/all to controls:

```javascript
<LogFilterControls
    filterMode={filterMode}
    setFilterMode={setFilterMode}
    lineCount={lineCount}
    setLineCount={setLineCount}
    timeRange={timeRange}
    setTimeRange={setTimeRange}
    onApply={fetchLogs}
    isLoading={isLoading}
    allowedModes={['lines', 'all']}
/>
```

Use `logLanguage` rather than `chatLogLanguage`:

```javascript
import { logLanguage } from '../../utils/logLanguage';
```

Then pass:

```javascript
language={logLanguage}
```

- [ ] **Step 3: Run a frontend syntax/lint check for the new files**

Run:

```bash
cd frontend-react && pnpm lint
```

Expected: lint passes, or only pre-existing lint warnings/errors unrelated to touched files appear. If lint fails on touched files, fix before continuing.

- [ ] **Step 4: Commit modal and hook**

```bash
git add frontend-react/src/hooks/useViewMinqlxLogs.js frontend-react/src/components/instances/ViewMinqlxLogsModal.jsx
git commit -m "feat(instances): add minqlx logs modal"
```

---

## Task 6: Wire MinQLX action through the instance table

**Files:**
- Modify: `frontend-react/src/components/InstanceActionsMenu.jsx`
- Modify: `frontend-react/src/components/instances/InstanceRowContent.jsx`
- Modify: `frontend-react/src/components/instances/InstancesTableRow.jsx`
- Modify: `frontend-react/src/pages/ServersPage.jsx`
- Modify: `frontend-react/src/pages/__tests__/ServersPage.test.jsx`

- [ ] **Step 1: Update InstanceActionsMenu props and render action**

In `frontend-react/src/components/InstanceActionsMenu.jsx`, add `ScrollText` or reuse `FileText` from `lucide-react`. Prefer adding `ScrollText` to distinguish MinQLX without changing style:

```javascript
import { Trash2, RefreshCw, SlidersHorizontal, Zap, FileText, ExternalLink, Check, Square, Play, Terminal, MessageSquare, ScrollText } from 'lucide-react';
```

Add prop:

```javascript
function InstanceActionsMenu({ instance, handleRestart, handleDelete, handleStop, handleStart, handleToggleLanRate, onOpenEditConfigModal, onViewInstanceDetails, onViewLogs, onViewChatLogs, onViewMinqlxLogs, onOpenRconConsole }) {
```

Insert after Chat Logs:

```jsx
<Menu.Item>
  {({ active }) => (
    <button onClick={() => onViewMinqlxLogs(instance)}
      disabled={!isActionable}
      className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}>
      <ScrollText size={15} className="mr-3 flex-shrink-0 text-theme-muted" /> View MinQLX Logs
    </button>
  )}
</Menu.Item>
```

- [ ] **Step 2: Thread callback through row components**

In `InstanceRowContent.jsx`, add prop destructuring:

```javascript
onViewMinqlxLogs,
```

Pass it to `InstancesTableRow`:

```jsx
onViewMinqlxLogs={() => onViewMinqlxLogs(inst)}
```

In `InstancesTableRow.jsx`, add prop:

```javascript
onViewMinqlxLogs,
```

Pass it to `InstanceActionsMenu`:

```jsx
onViewMinqlxLogs={onViewMinqlxLogs}
```

- [ ] **Step 3: Wire ServersPage hook and modal**

In `frontend-react/src/pages/ServersPage.jsx`, add imports:

```javascript
import { useViewMinqlxLogs } from '../hooks/useViewMinqlxLogs';
import ViewMinqlxLogsModal from '../components/instances/ViewMinqlxLogsModal';
```

Instantiate hook beside the existing log hooks:

```javascript
const { selectedInstanceForMinqlxLogs, isViewMinqlxLogsModalOpen, openViewMinqlxLogs: handleViewMinqlxLogs, closeViewMinqlxLogs: closeViewMinqlxLogsModal } = useViewMinqlxLogs();
```

Pass `handleViewMinqlxLogs` into the instance table/row component wherever `handleViewChatLogs` is already passed.

Render modal beside existing log modals:

```jsx
<ViewMinqlxLogsModal isOpen={isViewMinqlxLogsModalOpen} onClose={closeViewMinqlxLogsModal} instance={selectedInstanceForMinqlxLogs} />
```

- [ ] **Step 4: Update ServersPage test mocks**

In `frontend-react/src/pages/__tests__/ServersPage.test.jsx`, add hook mock:

```javascript
vi.mock('../../hooks/useViewMinqlxLogs', () => ({
  useViewMinqlxLogs: () => ({
    selectedInstanceForMinqlxLogs: null,
    isViewMinqlxLogsModalOpen: false,
    openViewMinqlxLogs: mocks.noop,
    closeViewMinqlxLogs: mocks.noop,
  }),
}));
```

Add component mock:

```javascript
vi.mock('../../components/instances/ViewMinqlxLogsModal', () => ({ default: mocks.NullComponent }));
```

- [ ] **Step 5: Run page/action tests**

Run:

```bash
cd frontend-react && pnpm test -- InstanceActionsMenu.test.jsx ServersPage.test.jsx
```

Expected: tests pass or fail only because the next task's action-menu assertion has not been added yet. Fix wiring failures before continuing.

- [ ] **Step 6: Commit wiring**

```bash
git add frontend-react/src/components/InstanceActionsMenu.jsx frontend-react/src/components/instances/InstanceRowContent.jsx frontend-react/src/components/instances/InstancesTableRow.jsx frontend-react/src/pages/ServersPage.jsx frontend-react/src/pages/__tests__/ServersPage.test.jsx
git commit -m "feat(instances): wire minqlx logs action"
```

---

## Task 7: Frontend action menu test

**Files:**
- Modify: `frontend-react/src/components/__tests__/InstanceActionsMenu.test.jsx`

- [ ] **Step 1: Make render helper expose `onViewMinqlxLogs`**

Change the helper to create and pass the callback:

```javascript
function renderMenu(instanceOverrides = {}) {
  const handleToggleLanRate = vi.fn();
  const onViewMinqlxLogs = vi.fn();
  render(
    <InstanceActionsMenu
      instance={{
        id: 1,
        name: 'inst-1',
        status: 'running',
        lan_rate_enabled: false,
        host_os_type: 'debian',
        ...instanceOverrides,
      }}
      handleRestart={vi.fn()}
      handleDelete={vi.fn()}
      handleStop={vi.fn()}
      handleStart={vi.fn()}
      handleToggleLanRate={handleToggleLanRate}
      POLLABLE_INSTANCE_STATUSES={[]}
      onOpenEditConfigModal={vi.fn()}
      onViewInstanceDetails={vi.fn()}
      onViewLogs={vi.fn()}
      onViewChatLogs={vi.fn()}
      onViewMinqlxLogs={onViewMinqlxLogs}
      onOpenRconConsole={vi.fn()}
    />
  );

  return { handleToggleLanRate, onViewMinqlxLogs };
}
```

- [ ] **Step 2: Add assertion for the new menu item**

Append test:

```javascript
it('shows View MinQLX Logs and calls the callback with the instance', () => {
  const { onViewMinqlxLogs } = renderMenu();

  const actionButton = screen.getByRole('button', { name: /view minqlx logs/i });
  expect(actionButton).not.toBeDisabled();

  fireEvent.click(actionButton);
  expect(onViewMinqlxLogs).toHaveBeenCalledWith(expect.objectContaining({
    id: 1,
    name: 'inst-1',
  }));
});
```

- [ ] **Step 3: Run the action menu test**

Run:

```bash
cd frontend-react && pnpm test -- InstanceActionsMenu.test.jsx
```

Expected: all action menu tests pass.

- [ ] **Step 4: Commit test**

```bash
git add frontend-react/src/components/__tests__/InstanceActionsMenu.test.jsx
git commit -m "test(instances): cover minqlx logs action"
```

---

## Task 8: Verification and release metadata

**Files:**
- Modify if required by repo release workflow: `VERSION`, `docs/user/version.json`, `docs/user/releases.md`

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
pytest tests/test_chat_logs_validation.py tests/test_minqlx_logs_validation.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Run targeted frontend tests**

Run:

```bash
cd frontend-react && pnpm test -- InstanceActionsMenu.test.jsx ServersPage.test.jsx
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend lint**

Run:

```bash
cd frontend-react && pnpm lint
```

Expected: lint passes. If lint reports pre-existing unrelated failures, record them in the final implementation notes with evidence and ensure touched files are clean.

- [ ] **Step 4: Run git diff review**

Run:

```bash
git diff --stat main...HEAD
git diff main...HEAD -- ui/routes/instance_routes.py ui/task_logic/ansible_instance_mgmt.py frontend-react/src/components/instances/ViewMinqlxLogsModal.jsx
```

Expected: diff only contains MinQLX log feature changes and the earlier spec/plan docs.

- [ ] **Step 5: Update release metadata if this will be PR'd as a user-visible feature**

If following repo PR workflow, bump all three version/release files together in one commit. Use the next patch version after the current `VERSION`. Add a concise release note:

```markdown
- Added MinQLX log viewing from instance actions, including rotated `minqlx.log.N` files.
```

Commit:

```bash
git add VERSION docs/user/version.json docs/user/releases.md
git commit -m "docs(releases): add minqlx logs entry"
```

- [ ] **Step 6: Final status check**

Run:

```bash
git status --short
git log --oneline main..HEAD
```

Expected: working tree clean; commits show test, implementation, and docs/release commits.

---

## Self-Review

### Spec coverage

- New action in Instance Actions: Task 6 and Task 7.
- Chat Logs-style modal with rotated-file dropdown: Task 5.
- No `time` filter: Task 3 API validation, Task 4 `allowedModes`, Task 5 modal config.
- New API endpoints: Task 3.
- New Ansible playbooks: Task 2.
- Backend validation and frontend tests: Task 1, Task 7, Task 8.
- Safe filenames only: Task 1, Task 2, Task 3, Task 5.

### Placeholder scan

No placeholder implementation steps remain. Every task lists exact files, commands, expected outcomes, and concrete code snippets for the code-writing steps.

### Type and name consistency

Names are consistent across tasks:

- API helpers: `fetchInstanceMinqlxLogs`, `listInstanceMinqlxLogs`
- Hook: `useViewMinqlxLogs`
- Modal: `ViewMinqlxLogsModal`
- Backend functions: `fetch_instance_minqlx_logs`, `list_instance_minqlx_logs`
- Routes: `/minqlx-logs`, `/minqlx-logs/list`
- Filename regex: `minqlx\.log(\.\d+)?`

## Execution Gate

Before any product code changes, run `.claude/skills/pre-implementation-review-loop/SKILL.md` against this spec and plan. Fold accepted findings into both documents and commit the review artifacts. Only then start Task 1.
