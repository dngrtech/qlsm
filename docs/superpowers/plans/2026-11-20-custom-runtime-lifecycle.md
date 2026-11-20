# Custom Runtime Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for delegated implementation, or superpowers:executing-plans for inline integration. User authorization covers implementing this plan and opening one PR.

**Goal:** Make generic Custom runtime providers safe to update, retain, and restore, and explain the workflow accurately in the UI and documentation.

**Architecture:** Extend the existing host runtime operation/reservation and recovery system for same-provider immutable release changes. Keep provider lifecycle protection in shared services. Serialize add-on state with the existing transactional encrypted backup. The frontend consumes a dedicated Custom update preview/confirmation API.

**Tech Stack:** Flask, SQLAlchemy/SQLite, Redis/RQ, Ansible/systemd, React, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-20-custom-runtime-lifecycle-design.md`

## Global Constraints

- All work is on isolated feature branches and is integrated into one PR against `main`; do not merge or operate on live game hosts.
- Custom remains Standalone-only, pinned to one provider and plugin API. Do not add a built-in shinqlx runtime or implement an upstream add-on.
- Existing hosts never follow a provider's new approved digest automatically. Retain old bundles. Do not install old builtin dependency requirements into Custom instances.
- Preserve instance configs, plugins, and data; restart only instances originally RUNNING. Verify readiness after every required restart.
- Persist intent before remote effects, fence execution, and keep the reservation while recovery is incomplete.
- Never expose captured secrets or add-on settings in errors, logs, preview JSON, or reports.
- Version-1 backups without `addon_states` remain accepted, clear destination add-on state, and produce explicit restart/re-enable guidance.
- Configured package and lifecycle-lock directories must be direct, nonoverlapping paths; reject unsupported layouts before backup writes. The existing configs/presets split remains supported.
- Use meaningful failing regression tests before behavior changes. Copy-only wording changes do not need standalone tests.

## Review Focus

Inspect rollback after partial unit replacement/start, recovery dispatch before builtin-specific code, stale confirmation and job ownership, provider removal races, legacy backup semantics, and new UI/API agreement. Verify existing builtin upgrades and Custom creation/setup behavior remain intact. Report live-host validation limits plainly.

## Task 1: Restore complete add-on state

**Ownership:** `ui/task_logic/backup_db_export.py`, `backup_db_import.py`, `backup_import.py`, `ui/routes/backup_routes.py`, related backup tests. Do not edit frontend or docs in this task.

1. Add regression tests to `tests/test_backup_db_serializers.py` and import tests for global/host/instance state, enabled/disabled flags, nested settings, timestamps, replacement of stale destination rows, older backups, and malformed/duplicate/orphaned state. A failed import must leave existing state intact through the caller's rollback.
2. Export `addon_states` in the existing format version. Restore validated rows transactionally, clearing destination rows even when the archive predates the collection. Preserve package/release tree behavior.
3. Return explicit restore metadata without settings: `restart_required: true`, `addon_state_restored: boolean`, plus an operator-facing message requiring all QLSM application and worker processes to restart. Older archives additionally require enabling/configuring add-ons afterward. Preserve existing response fields and authentication behavior.
4. Hold `addon_lifecycle_maintenance_lock` around public archive export and restore so package/settings writes cannot race the snapshot or swap. Map lifecycle conflicts to HTTP 409. Run targeted serializer/import/route/swap tests. Report exact commands and results; the controller runs the full suite after integration.

**Acceptance:** A new archive restores Custom provider enablement/settings; an old archive cannot inherit target state. Database/filesystem failures roll back both. No settings leak into output.

## Task 2: Protect providers used by hosts

**Ownership:** new `ui/addons/runtime_protection.py`, `ui/addons/install.py`, `ui/addons/settings.py`, `ui/routes/addon_routes.py`, the Custom creation critical section in `ui/routes/host_routes.py`, and provider protection tests. Do not change backup files, runtime worker, or frontend.

1. Add behavior tests for disable/uninstall/replacement of a provider referenced by a Custom host, including stopped/error/empty hosts. Verify safe scoped settings edits and valid provider updates still work. Exercise ZIP and repository paths through shared install logic.
2. Introduce one shared protection exception carrying dependent host IDs/names and a useful message, mapped to HTTP 409 by affected routes. Enforce checks in shared settings/install/uninstall services, not solely endpoints.
3. Serialize provider lifecycle mutations and Custom host creation so a provider cannot be removed between validation and pin insertion. Use a bounded cross-process file lock beside the persistent package root (no Redis dependency for local package lifecycle). Provide `provider_lifecycle_lock(provider_id)` for runtime confirmation to use. Place mutation checks inside the lock and repeat the active-provider/release check for Custom host creation before committing its pin. Lock timeout is a clear conflict, not a silent bypass.
4. Reject removal of `custom_runtime` while hosts reference the add-on; allow ordinary valid replacement retaining capability and retained release files. Inspect pending-on-disk manifests where relevant so a pre-restart change cannot bypass the rule.
5. Run add-on install/routes/settings and Custom host tests; report commands and evidence.

**Shared interface:** `provider_lifecycle_lock(provider_id)` and a `RuntimeProviderInUse` (or clearly named equivalent) exception in `ui/addons/runtime_protection.py`. No host pin transition is performed by this task.

## Task 3: Implement Custom release operations

**Ownership:** new `ui/custom_runtime_update.py`, `ui/routes/custom_runtime_update_routes.py`, `ui/task_logic/custom_runtime_update.py`, remote helpers/playbooks as needed; minimal dispatch changes to `host_runtime_upgrade.py`, `host_runtime_upgrade_recovery.py`, shared operation model/docstring/guard, and blueprint registration in `ui/__init__.py`; runtime operation tests. Do not edit add-on lifecycle services, backup files, frontend, or user docs.

1. Read the existing `Execution`, `UpgradeDeps`, `qlsm_runtime_op.py` inventory/fence implementation, and runtime operation harness. Add failing tests for the specified GET/POST contract, same-provider/API/platform choices, stale fingerprints, authentication, busy state, and immutable confirmation capture. Use the spec's exact JSON names.
2. Build preview and reservation logic. The approved target and retained previous successful target are the only allowed choices. Include host creation identity in the fingerprint/history checks where needed to prevent reused-ID confusion. Acquire provider lifecycle synchronization, host lock, then all instance locks; revalidate and commit the existing operation reservation. Return 202 with operation ID and configuring status; reuse existing RQ enqueue/failure/reconcile paths.
3. Dispatch `original_runtime == "custom"` into a separate Custom worker/recovery implementation before builtin-only validation/snapshot/rollback. Reuse existing states, `phase` for staging/starting, fencing token/CAS, durable intents, and shared service probes. Make blocked-message wording accurate for both operations.
4. Stage the target release under the existing remote operation fence; verify remote platform before downtime and preserve the current immutable directory. Generate new units using the selected release and current instance configuration. Use existing remote inventory/apply/restore to capture exact original units. Avoid any config/plugin/game-data replacement. Implement empty-host support.
5. Quiesce and verify inactive state, atomically switch the host pin/configuring intent, install units, start only originally RUNNING services, require fresh readiness, and finalize remotely before success. Failure/interrupt recovery restores the original pin, exact units, and service states. Keep ERROR plus `recovery_required` and reservation if incomplete. Preparation cancellation changes no live services.
6. Add failure-injection tests for second-unit failure, failed/stale readiness, interruption after intent, idempotent partial rollback, unreachable hosts, stale workers, stopped/empty hosts, changed launcher/required plugin/rate/preload values, and explicit rollback. Confirm old bundles can be used without being currently approved.
7. Run the runtime operation/Custom/guard/recovery suites and relevant Ansible syntax/harness checks. Report verification and live-host limitations.

**Integration:** Task 2 supplies `provider_lifecycle_lock(provider_id)`; if developing independently, import it lazily in confirmation and validate after integration. UI uses the spec's GET/POST response; it monitors completion using existing host status/log refresh.

## Task 4: Present the lifecycle and correct documentation

**Ownership:** frontend components/services/tests, `docs/user/getting-started/add-host.md`, existing backup/add-on user docs, and `addons/README.md`. Do not edit backend modules or spec/plan.

1. Show the selected Custom provider label/build prominently in Add Host. Condition the builtin conversion warning appropriately; Custom guidance explains pinning and explicit release updates.
2. Add a Custom release dialog/action in `HostDetailDrawer.jsx`, with dedicated small service/component modules. Follow the spec's exact preview and confirmation contract. Show pinned/selected build and digest, affected instances/downtime, preserve-stopped guidance, automatic rollback, target/previous choice, and no-update/ineligible/stale/error states. Disable duplicate submission and refresh host status after acceptance. Keep builtin upgrade dialog/action behavior.
3. Consume restore metadata (`restart_required`, `addon_state_restored`) from Task 1 and show persistent, clear restart instructions including re-enable/configure guidance for older archives. Do not clear the warning before the operator can read it.
4. Add focused UI tests for provider selection, preview/choice/confirmation payloads, busy/ineligible/error handling, and restore guidance where behavior changes. Do not write tests solely to mirror a sentence.
5. Update existing user and add-on docs for release pinning/update/rollback, provider-in-use rejection, backup state, and restart/legacy semantics. Use generic provider names; shinqlx-specific integration is separate.
6. Run relevant Vitest tests, lint, and build; report results.

## Task 5: Integrate, review, and open the PR

**Review refinements:** The spec records concrete review findings: private one-host inventories, explicit systemd quiescence, revalidation of saved completion decisions, permission-preserving forward unit installation, staged manifest consistency, scoped-state/credential fences, and stable backup paths. Their focused regressions are part of the owning tasks; they do not add a new runtime category or deployment target.

**Ownership:** controller; task implementers fix review findings in their scope.

1. Record plan progress in a git-ignored ledger with task base/head commits, decisions, and test evidence. Review the spec once for important ambiguity before code. Review each task for spec compliance and code quality, then perform one complete-branch review focused on the risks above.
2. Integrate disjoint task branches sequentially. Resolve interface conflicts explicitly and test the integrated code; do not copy uncommitted unrelated changes.
3. Run the backend CI suite (`SECRET_KEY=ci-test-secret-key-not-for-production python -m pytest tests/`), frontend lint/test/build, and focused Ansible validation. Investigate concrete failures; do not broaden optional checks indefinitely.
4. Commit the spec/plan and implementations, push the feature branch, and open one non-draft PR so the required CI jobs run. The user has already authorized this. Do not merge. Check the PR's checks and report observed results, any remaining limitations, and its URL.
