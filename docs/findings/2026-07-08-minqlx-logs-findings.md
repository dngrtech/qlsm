# MinQLX Logs Review Findings

Reviewed:
- `/home/rage/qlsm/docs/superpowers/specs/2026-07-08-minqlx-logs-design.md`
- `/home/rage/qlsm/docs/superpowers/plans/2026-07-08-minqlx-logs.md`

## Important
### List endpoint does not implement the spec's missing-host behavior
The spec says both endpoints require an associated host and lists missing host as a 400 error. The plan's fetch route checks `if not instance.host`, but the planned `/minqlx-logs/list` route does not. It calls `list_instance_minqlx_logs`, which returns failure for missing host, and the route converts that into a 500. That contradicts the API contract and makes a client/data issue look like a server failure.
Required fix: Update Task 3's list route to check `if not instance.host` and return `400 {"error":{"message":"Instance has no associated host."}}` before task logic. Add a backend test for `/api/instances/<id>/minqlx-logs/list` with no host.

### Table wiring omits an existing callback hop
The plan wires `ServersPage`, `InstanceRowContent`, `InstancesTableRow`, and `InstanceActionsMenu`, but the repository also has `frontend-react/src/components/instances/InstancesTable.jsx`, which currently threads `onViewLogs` and `onViewChatLogs` down to `InstancesTableRow`. If that component is still used by any route/test/story or reintroduced later, the new MinQLX action will receive an undefined callback and clicking it can throw instead of opening the modal.
Required fix: Add `frontend-react/src/components/instances/InstancesTable.jsx` to the modify list and Task 6. Thread `onViewMinqlxLogs` through it exactly like `onViewChatLogs`, or explicitly document that `InstancesTable.jsx` is dead code and remove/ignore it in the plan.

### Tests patch the wrong boundary for route validation confidence
The planned backend tests patch `ui.task_logic.ansible_instance_mgmt.fetch_instance_minqlx_logs` for valid requests, which is fine for avoiding Ansible, but the proposed assertions mostly prove the route returns 200 when the task function is mocked. They do not cover the list endpoint, missing host behavior, default parameters, invalid/non-integer `lines`, or that invalid input returns before task logic is called. Because this feature is security-sensitive path/command plumbing, those gaps could allow regressions in validation while tests still pass.
Required fix: Expand Task 1 to assert rejection paths do not call task logic, add malformed/non-integer/out-of-range `lines` cases, add missing instance and missing host cases for both fetch and list endpoints, and add a list endpoint success test.

### Direct playbook safety relies entirely on the Flask route
The fetch playbook interpolates `log_lines` and `log_filename` into command arguments and the list playbook accepts `port` directly. The Flask route constrains `filename` and `lines`, but the playbooks themselves do not assert those constraints. If task logic is called from another entry point, a maintenance script, or a future route without the same validation, the playbooks could be invoked with unsupported filenames/modes/line counts and read unexpected paths or fail unpredictably.
Required fix: Add defensive validation in `fetch_instance_minqlx_logs`/`list_instance_minqlx_logs` before invoking Ansible, matching the API rules (`filter_mode`, `lines`, and `filename`). Optionally add `assert` tasks in the playbook for `log_mode`, numeric `log_lines`, and `log_filename`.

## Minor
### The list playbook should initialize and type-check its output state
Unlike the existing chat list playbook, the planned MinQLX list playbook does not initialize `minqlx_log_files` before checking the directory and does not require `log_dir_stat.stat.isdir`. `default([])` likely prevents missing-directory failures, but explicit initialization makes the no-directory path clearer and avoids surprises if `/home/ql/qlds-<port>` exists but is not a directory.
Suggested fix: Add an initial `set_fact: minqlx_log_files: []`; run `find` only when `log_dir_stat.stat.exists and log_dir_stat.stat.isdir`; only overwrite the fact from find results under the same condition.

### Release metadata step is conditional despite repo workflow guidance
The plan says release metadata is modified "if required" / "if this will be PR'd as a user-visible feature." Repository guidance says every PR merge must keep `VERSION`, `docs/user/version.json`, and `docs/user/releases.md` in sync. Leaving this conditional can cause implementation agents to skip required release files for a user-visible feature.
Suggested fix: Make Task 8's release metadata update mandatory for the implementation PR, unless the feature is explicitly not going through the repo PR workflow.

## Open Questions
- Is `frontend-react/src/components/instances/InstancesTable.jsx` still reachable in the app, or is `SortableInstanceList`/`InstanceRowContent` now the only production path? This determines whether the omitted callback hop is a required implementation change or dead-code cleanup.
- Should the UI cap MinQLX rotations at current + 10 files as Chat Logs does? The spec says the UI may cap similarly; the plan snippets imply slicing behavior only by copying Chat Logs, but should state the exact cap to avoid inconsistent frontend/backend expectations.

## Tests To Add
- Fetch endpoint missing-host test returns 400 and does not call task logic.
- List endpoint missing-host test returns 400 and does not call task logic.
- List endpoint success test returns sorted safe filenames and `instance_name`.
- Invalid `lines` tests: below 10, above 10000, and non-integer/missing parsed value behavior for `filter_mode=lines`.
- Rejection tests assert the MinQLX task function is not called for invalid `filter_mode`, `time`, path traversal, malformed filename, and invalid lines.
- Frontend test that `LogFilterControls` with `allowedModes={['lines', 'all']}` does not render the time option and still defaults existing consumers to all modes.
- Frontend wiring test for the path that renders `InstanceRowContent`/`InstanceActionsMenu`, verifying **View MinQLX Logs** calls the page-level open handler with the instance.
- Ansible syntax checks plus a mocked/local playbook scenario for missing file returning `-- MinQLX log file not found --`, empty file returning `-- No entries --`, and list output excluding unsafe names like `minqlx.log.old` and `../minqlx.log`.
