# MinQLX Logs Design

## Goal

Add a new **View MinQLX Logs** action for each QLDS instance. The feature should mirror the existing **View Chat Logs** workflow as closely as possible, including rotated-file selection, line/all filtering, modal layout, read-only CodeMirror display, refresh, and backend Ansible fetch/list plumbing.

The log source is the per-instance minqlx runtime log:

```text
/home/ql/qlds-<PORT>/minqlx.log
/home/ql/qlds-<PORT>/minqlx.log.1
/home/ql/qlds-<PORT>/minqlx.log.2
```

## Non-goals

- No generic log-viewer refactor.
- No new visual design.
- No live tailing or websockets.
- No log download feature.
- No time-range filter for MinQLX logs.
- No support for arbitrary paths or filenames.

## User Experience

`InstanceActionsMenu` gains a read-only action beside the existing log actions:

```text
View Server Logs
View Chat Logs
View MinQLX Logs
View Details
```

Clicking **View MinQLX Logs** opens a new modal that visually follows `ViewChatLogsModal`:

- same 80vh modal shell and raised surface styling;
- title: `MinQLX Logs`;
- subtitle: instance name, port, selected filter description;
- rotated-file dropdown;
- refresh button;
- close button;
- read-only CodeMirror viewer;
- Ctrl+F hint;
- automatic scroll-to-bottom after load.

The dropdown lists only safe MinQLX log filenames:

```text
minqlx.log
minqlx.log.1
minqlx.log.2
...
```

`minqlx.log` appears first, then numbered rotations in ascending numeric order. The UI may cap the list similarly to Chat Logs, e.g. current file plus the first 10 rotations.

## Filtering

MinQLX logs support only:

- `lines` — fetch the last N lines;
- `all` — fetch the full selected file.

The `time` filter is intentionally excluded for MinQLX logs.

Reason: MinQLX lines use time-of-day only:

```text
(09:31:05) [INFO @ minqlx.load_plugin] Loading plugin 'serverchecker'...
```

Unlike Chat Logs, they do not include a date per line:

```text
[2026-07-08 09:31:05] player: message
```

A naive time filter would break across midnight and across multiple minqlx runs in the same file. Parsing `minqlx run @ YYYY-MM-DD HH:MM:SS` headers could reconstruct dates, but that is more logic than this feature needs. For this slice, the honest behavior is: no `time` mode for MinQLX Logs.

The modal should reuse the existing filter-control style where practical, but it must not present a time-range option for MinQLX logs.

## Frontend Design

Add a MinQLX-specific frontend flow by copying the existing Chat Logs shape:

- `frontend-react/src/components/instances/ViewMinqlxLogsModal.jsx`
- `frontend-react/src/hooks/useViewMinqlxLogs.js`
- API helpers in `frontend-react/src/services/api.js`:
  - `fetchInstanceMinqlxLogs(instanceId, options)`
  - `listInstanceMinqlxLogs(instanceId)`

Wire it through:

- `ServersPage.jsx`
- `InstanceRowContent.jsx`
- `InstancesTableRow.jsx`
- `InstanceActionsMenu.jsx`

`InstanceActionsMenu` receives `onViewMinqlxLogs` and renders **View MinQLX Logs** disabled under the same `isActionable` logic used for Server Logs and Chat Logs.

The modal should reuse existing log display utilities:

- `CodeMirrorEditor`
- log language highlighting (`logLanguage` is sufficient)
- shared button classes used by the existing log modals

If the current `LogFilterControls` cannot hide time mode cleanly, add the smallest targeted option to it, such as `allowedModes={['lines', 'all']}`, rather than duplicating the whole controls block.

## Backend API Design

Add two protected endpoints to `ui/routes/instance_routes.py`:

```text
GET /api/instances/<id>/minqlx-logs
GET /api/instances/<id>/minqlx-logs/list
```

The fetch endpoint accepts:

```text
filter_mode=lines|all
lines=500
filename=minqlx.log
```

Validation:

- instance must exist;
- instance must have an associated host;
- `filter_mode` must be `lines` or `all`;
- `lines` must be between `10` and `10000` unless `filter_mode=all`;
- `filename` must match exactly:

```regex
minqlx\.log(\.\d+)?
```

The list endpoint returns:

```json
{
  "data": {
    "files": ["minqlx.log", "minqlx.log.1"],
    "instance_name": "Example"
  }
}
```

Both endpoints keep the existing response shape:

```json
{"data": {...}}
{"error": {"message": "..."}}
```

The list endpoint must perform the same route-level instance and host validation as the fetch endpoint. In particular, `GET /api/instances/<id>/minqlx-logs/list` returns `404` when the instance is missing and `400 {"error":{"message":"Instance has no associated host."}}` when the instance exists without an associated host; it must not defer missing-host handling to task logic and convert it into a 500.

## Backend Task Logic

Add task-logic functions in `ui/task_logic/ansible_instance_mgmt.py`, copying the Chat Logs structure:

- `fetch_instance_minqlx_logs(instance_id, filter_mode='lines', lines=500, filename='minqlx.log')`
- `list_instance_minqlx_logs(instance_id)`

Both use the instance host's existing Ansible details:

- `host.name` as inventory limit;
- `host.ssh_user`;
- `host.ssh_key_path`;
- instance `port`.

The functions execute dedicated playbooks synchronously and parse Ansible debug output the same way Chat Logs does.

Task logic is also a safety boundary before Ansible execution. `fetch_instance_minqlx_logs` must defensively validate its direct inputs before building extra-vars or invoking the playbook:

- `filter_mode` is exactly `lines` or `all`;
- `filename` matches `minqlx\.log(\.\d+)?`;
- when `filter_mode='lines'`, `lines` is an integer between `10` and `10000`;
- the instance exists, has a host, and has a valid port.

`list_instance_minqlx_logs` must likewise validate that the instance exists, has a host, and has a valid port before invoking Ansible. Playbook-level `assert` tasks may be added as extra defense, but the required enforcement point is the Python task logic before Ansible is called.

## Ansible Design

Add two playbooks:

```text
ansible/playbooks/fetch_minqlx_logs.yml
ansible/playbooks/list_minqlx_logs.yml
```

`fetch_minqlx_logs.yml` reads:

```text
/home/ql/qlds-{{ port }}/{{ filename }}
```

Supported modes:

```yaml
lines: tail -n {{ lines }} {{ log_file }}
all: cat {{ log_file }}
```

If the file does not exist, return:

```text
-- MinQLX log file not found --
```

If the file exists but yields no output, return:

```text
-- No entries --
```

`list_minqlx_logs.yml` lists only files whose basename matches:

```regex
^minqlx\.log(\.\d+)?$
```

The playbook output is a JSON list encoded through `debug.msg`, matching the Chat Logs list playbook pattern.

## Error Handling

- Missing instance: 404.
- Missing host: 400.
- Invalid `filter_mode`: 400.
- Invalid `filename`: 400.
- Invalid `lines`: 400.
- Ansible failure: 500 with the existing generic failure message pattern.
- Missing remote file: successful response containing `-- MinQLX log file not found --`.

## Tests

Backend:

- Add validation tests mirroring `tests/test_chat_logs_validation.py`:
  - invalid filter mode rejected;
  - `time` mode rejected;
  - path traversal filename rejected;
  - malformed filename rejected;
  - invalid `lines` rejected for below-minimum, above-maximum, and non-integer values when `filter_mode=lines`;
  - missing instance returns 404 for fetch and list;
  - missing host returns 400 for fetch and list;
  - every rejection path asserts the MinQLX task function was not called;
  - valid `lines` request calls task logic;
  - valid `all` request calls task logic;
  - list success returns sorted safe filenames and `instance_name`.

Frontend:

- Extend `InstanceActionsMenu` tests to assert **View MinQLX Logs** appears and calls `onViewMinqlxLogs`.
- Add or update page-level mocks so `ServersPage` can render with the new hook/modal.

Verification:

- Run targeted backend tests for MinQLX log validation.
- Run targeted frontend tests for the action menu/page wiring.
- Run frontend lint if changes touch shared components.

## Documentation

After implementation, update user-facing docs or release notes for the repo PR/release workflow. Release metadata is mandatory for the PR path unless the work is explicitly not going through the repo PR/release workflow. The design spec itself is the planning artifact for this slice.

---
**Review loop closed:** 2026-07-09
- Findings: `/home/rage/qlsm/docs/findings/2026-07-08-minqlx-logs-findings.md`
- Assessment: `/home/rage/qlsm/docs/assess-review-findings/2026-07-08-minqlx-logs-assessment.md`
- Accepted findings folded in: 1. List endpoint missing-host behavior; 3. Expanded validation/list tests; 4. Task-logic validation before Ansible; 6. Mandatory PR release metadata
- Deferred: 2. InstancesTable.jsx callback hop; 5. List playbook initialization/isdir guard
