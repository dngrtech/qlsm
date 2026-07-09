# MinQLX Logs Findings Assessment

Reviewed:
- `/home/rage/qlsm/docs/superpowers/specs/2026-07-08-minqlx-logs-design.md`
- `/home/rage/qlsm/docs/superpowers/plans/2026-07-08-minqlx-logs.md`
- `/home/rage/qlsm/docs/findings/2026-07-08-minqlx-logs-findings.md`

## Assessment

### 1. List endpoint does not implement the spec's missing-host behavior
- **Finding says:** The planned list route lacks the fetch route's `instance.host` check, so a missing host becomes a task-logic failure and route-level 500 instead of the spec's 400.
- **Assessment:** Accept
- **Edge-case validity:** realistic — the spec explicitly defines missing host as a 400 for both endpoints, and the planned list route does not enforce that contract.
- **Pros of fixing:** Keeps API behavior consistent, avoids misclassifying bad instance state as server failure, and gives frontend/tests a deterministic validation response.
- **Cons of fixing:** Small additional route branch and one targeted test.
- **Action:** Fix before implementation
- **Reasoning:** This is a direct spec/plan mismatch with very low fix cost. Add the missing host check to the list route and cover it with a backend test before implementation proceeds.

### 2. Table wiring omits an existing callback hop
- **Finding says:** `InstancesTable.jsx` still threads `onViewLogs` and `onViewChatLogs`; if used, it also needs `onViewMinqlxLogs` or the new action callback can be undefined.
- **Assessment:** Acknowledge
- **Edge-case validity:** speculative but plausible — `InstancesTable.jsx` exists, but a repository search only found self/internal references rather than an obvious production import path.
- **Pros of fixing:** Cheaply keeps a legacy/standalone table component in sync with the row/menu contract and prevents future reuse surprises.
- **Cons of fixing:** Touches apparently unused code and slightly expands the implementation surface for no confirmed current user path.
- **Action:** Optional follow-up
- **Reasoning:** This should not block implementation because the component appears unreachable today. If the implementation touches the table wiring anyway, threading the callback through `InstancesTable.jsx` is low-risk; otherwise documenting it as dead code or leaving it for cleanup is acceptable.

### 3. Tests patch the wrong boundary for route validation confidence
- **Finding says:** The planned tests mostly prove mocked success for fetch, but miss list coverage, missing-host behavior, invalid `lines`, defaults, and assertions that invalid inputs do not call task logic.
- **Assessment:** Accept
- **Edge-case validity:** realistic — the spec includes validation rules beyond the proposed tests, and the feature passes user-controlled values toward Ansible command plumbing.
- **Pros of fixing:** Improves confidence in security-sensitive validation, catches regressions before Ansible execution, and verifies both endpoints rather than only fetch success paths.
- **Cons of fixing:** Adds several focused tests and modest setup helpers; may lengthen the test file but stays within the feature scope.
- **Action:** Fix before implementation
- **Reasoning:** This is not test bloat; it covers stated API contracts and rejection-before-task behavior. Expand Task 1 with invalid line counts/non-integer handling, missing instance/host, list success, and `mock_fetch`/`mock_list` not-called assertions for rejection paths.

### 4. Direct playbook safety relies entirely on the Flask route
- **Finding says:** Task logic/playbooks trust route validation for `filter_mode`, `lines`, `filename`, and `port`, so future non-route callers could invoke Ansible with unsafe or unsupported values.
- **Assessment:** Accept
- **Edge-case validity:** realistic — the task functions are normal module functions, not private route-only code, and they directly build Ansible extra-vars used by shell commands on the remote host.
- **Pros of fixing:** Adds defense in depth at the boundary closest to Ansible, protects future callers, and keeps safety rules co-located with the function that invokes remote commands.
- **Cons of fixing:** Duplicates some route validation and requires a few extra unit assertions; playbook-level asserts may be more ceremony than necessary.
- **Action:** Fix before implementation
- **Reasoning:** The task-logic validation is worth doing because the cost is low and the inputs are security-sensitive. Keep it pragmatic: validate `filter_mode`, `filename`, and line count in `fetch_instance_minqlx_logs`; validate basic instance/port assumptions in list/fetch as appropriate. Playbook `assert` tasks are optional unless the implementer wants belt-and-suspenders validation.

### 5. The list playbook should initialize and type-check its output state
- **Finding says:** The planned list playbook relies on `default([])` and checks only path existence, not `isdir`, before producing the file list.
- **Assessment:** Acknowledge
- **Edge-case validity:** realistic but minor — a missing directory likely works because of `default([])`, while a non-directory path is unusual but possible.
- **Pros of fixing:** Makes the no-directory path explicit, avoids relying on undefined registered results, and handles a malformed remote path more cleanly.
- **Cons of fixing:** Adds a few Ansible lines for a defensive case that probably does not occur in normal managed QLDS instances.
- **Action:** Optional follow-up
- **Reasoning:** This is a good cleanup while creating the playbook, but it should not block implementation. If accepted, add an initial `minqlx_log_files: []` fact and guard `find` with `log_dir_stat.stat.exists and log_dir_stat.stat.isdir`.

### 6. Release metadata step is conditional despite repo workflow guidance
- **Finding says:** The plan makes release metadata conditional, but repository guidance requires `VERSION`, `docs/user/version.json`, and `docs/user/releases.md` to stay in sync for PR merges.
- **Assessment:** Accept
- **Edge-case validity:** realistic — this is a user-visible feature and the repository guidance explicitly says every PR merge must bump all three files together.
- **Pros of fixing:** Prevents version drift, avoids stale update notices/changelog gaps, and gives the implementation agent an unambiguous final step.
- **Cons of fixing:** Adds a small release-doc commit and requires choosing the next patch version during the PR workflow.
- **Action:** Amend plan
- **Reasoning:** The implementation plan should make release metadata mandatory for the PR path, with an explicit exception only if the work is not going through the repo PR/release workflow.

## Bottom Line

4 of 6 findings need action before implementation. Amend the plan for findings 1, 3, 4, and 6 before starting product-code changes; findings 2 and 5 are reasonable low-cost cleanups but should not block the implementation.