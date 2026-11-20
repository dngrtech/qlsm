# Custom runtime lifecycle support

## Goal and authorization

Implement the four requested QLSM changes in one pull request: explicit Custom release updates with rollback; protection of providers used by hosts; correct backup and restore of add-on state; and clear provider labels and runtime guidance. The user has authorized implementation and opening the PR. This work enables the existing generic Custom contract to support a provider such as shinqlx; packaging or publishing a shinqlx add-on is separate work.

## Scope

Custom remains a runtime category for Standalone hosts. Hosts retain their provider ID, immutable release digest, and plugin API. There is no new built-in shinqlx runtime, engine migration, cloud/self Custom support, or change to per-instance dependency installation. Ordinary provider updates continue to leave existing host pins unchanged.

## 1. Explicit release update and rollback

### Operator flow and HTTP contract

A Custom Standalone host offers **Update Custom runtime** in its host drawer. Opening the dialog reads `GET /api/hosts/<id>/custom-runtime-update`. Its `data` object contains:

- `eligibility: {enabled, reason}`; only ACTIVE Standalone Custom hosts with an available enabled provider, valid current bundle, and RUNNING or STOPPED instances are eligible.
- `current`, `target`, and `rollback`: release summaries with `provider_id`, `label`, `build`, `sha256`, `plugin_api`, and `platform`; unavailable choices are null. `target` is the provider's approved release when its digest differs, uses the same plugin API, and matches the pinned release's platform exactly. `rollback` is the retained previous release from the latest successful operation whose provider and destination digest still match this host.
- `instances: [{id, name, status}]`, `fingerprint`, and a `reason` for the absence of an update where useful.

The dialog shows the provider, current and chosen build/digest, affected instances, downtime, preservation of stopped instances, and automatic rollback on failure. It offers the approved update and, where available, an explicit rollback. Confirmation posts `{fingerprint, target_sha256, action}` to the same route, with `action` equal to `update` or `rollback`. The server derives the provider and allowable target itself; it does not accept arbitrary provider IDs or release digests. Malformed input returns 400, unavailable/busy/stale choices return 409, and acceptance returns 202 with `data.operation_id` and `data.status = "configuring"`. Both endpoints require authentication. Secrets and capture internals are never returned.

Confirmation recomputes the capture under the existing host and all-instance execution locks. The fingerprint binds host identity/provider/current digest, target choices, and instance identities and statuses. A committed nonterminal `HostRuntimeUpgradeOperation` reserves the host before enqueueing. Reuse its existing partial unique index, fencing token, RQ dispatch, failure callback, and reconciliation rather than introducing another reservation table. `original_runtime = "custom"` selects the Custom implementation. Existing builtin upgrades retain their behavior. Host reservation messages must describe runtime maintenance generically or distinguish the operation accurately.

### Durable execution

Before downtime, revalidate both bundles and capture, check the actual remote OS, architecture, and Python ABI, and install the new immutable digest directory alongside the current release. Keep old releases. Check that STOPPED instances really have no service or stray engine process. Every remote mutation uses the existing operation lock/fence. A staging failure leaves the original pin and services alone.

Each Custom remote step uses a private inventory containing only the confirmed endpoint under a fixed alias; a display name or a shared inventory group must never expand the target set. Quiescence requires an explicit inactive/failed systemd state and a successful zero-process observation. Missing or transitioning state is unknown. Forward unit replacement preserves the original restrictive permissions and group as well as preserving them on rollback.

Persist `quiescing` intent before stopping any running instance and verify that every instance is inactive before changing units. Persist the pin switch and `configuring` intent atomically. Replace only each instance's root-owned systemd unit, generated with the selected release's launcher, required plugins, preload exclusions, and rate flags. Do not rewrite configs, plugin files, or game data. Use the existing remote inventory/apply/restore mechanism to retain the exact original units. Reload systemd after applying units. Restart only instances captured as RUNNING and require fresh serverchecker status after start. STOPPED instances stay stopped. A host with no instances is supported.

Use existing states (`preparing`, `quiescing`, `configuring`, `rolling_back`, `recovery_required`, and terminal states); use `phase` to distinguish staging and starting without adding a schema/state migration. Record intent before every side effect and verified outcomes after. Successful completion restores ACTIVE and releases the reservation only after remote finalization.

On failure after quiescing, restore the original digest and exact previous units, then the original RUNNING/STOPPED set. Interruptions follow the same idempotent recovery path. Preparation-only recovery cancels without changing live services. Unknown remote state, incomplete restoration, or unreachable hosts remain ERROR with `recovery_required`; keep the mutation reservation and retry through the existing reconciler. Never report a successful rollback until unit restoration and service readiness are verified. Recovery must work from retained pinned bundles and captured information without requiring the new release to remain the provider's approved build. Explicit rollback after success is a new same-provider/API operation with the same safeguards. Its eligibility also checks provider and current digest to avoid confusing unrelated host history.

A durable completion decision is an intent until remote finalization is recorded. Replaying it must verify the expected pin and current service/readiness state before releasing the reservation. A finalized remote receipt must remain closed; drift after a receipt must not reopen an old operation or be reported as verified completion.

## 2. Protect referenced runtime providers

Any Custom host referencing a provider protects that provider, regardless of host status or number of instances. Reject global disable, uninstall, and package replacement that removes its `custom_runtime` capability. Report HTTP 409 with a useful message and dependent host IDs/names. Apply checks below route-only code so ZIP and repository installation paths share the rule. Scoped settings edits and ordinary compatible provider updates remain allowed. Do not silently migrate, repin, delete, or disable hosts. Retained release files must survive allowed replacements. Use a common lifecycle synchronization boundary with Custom host creation/update reservation where needed to prevent check-then-act races; fail closed when safe coordination is unavailable.

The installed manifest must match the checked manifest, with duplicate canonical archive destinations rejected. Destructive package changes require a database context. Scoped settings validation and writes share the transaction-held maintenance fence, and bulk cleanup is limited to deleted host/instance scopes. Standalone creation fences permanent SSH key work and cleanup against restore and serializes requests for the same name; builtin and Custom requests share those key paths.

## 3. Back up and restore AddonState

Export global `AddonState` rows and host/instance-scoped rows whose targets appear in the serialized host/instance snapshot: add-on ID, scope, scope ID, enabled flag, settings JSON, and any existing timestamps needed for faithful restoration. Omit orphaned host/instance scopes without changing the source database, and retain valid settings even for add-ons that are no longer installed. Restore them transactionally with the database and filesystem swap, replacing destination state rather than merging it. Validate row shapes, IDs/scopes, booleans, settings objects, duplicate logical keys, and host/instance scope references before deleting current data. Preserve secrets using the archive's existing encryption and do not expose settings in logs or response messages.

Keep archive format compatibility: `addon_states` is an optional collection in version 1. An older archive without it clears destination add-on state, leaving restored providers disabled by default; explicitly tell the operator to enable and configure them after restart. Never retain destination scoped rows that could bind to restored/reused host IDs. New archives restore enabled state and scoped overrides exactly. Existing package and retained release backup coverage remains in place.

The in-memory add-on registry and imported Python modules are not hot-reloaded after filesystem restoration. Successful restore must clearly require restarting QLSM (all application/worker processes) before managing restored hosts, and distinguish older archives missing add-on state. Wire this through the restore response and UI feedback without revealing settings.

Archive capture/restoration excludes concurrent package and settings writes. Respect the configured add-on package directory, but reject layouts that overlap other backup trees or use symbolic links or `..` components in the package/lock directory paths before snapshotting or staging. Preserve the existing explicitly separated configs/presets layout. Core backup-hook exception logging includes the add-on, hook and exception type, never exception values or tracebacks containing settings.

## 4. UI and documentation corrections

Display the selected Custom provider's name and build prominently in Add Host; preserve the generic Custom category and existing API fields. Only builtin hosts see the minqlx-to-minqlxtended conversion guidance. Custom guidance explains pinning and the explicit release update/rollback action. Use generic provider labels, not shinqlx special cases. Document the update lifecycle, downtime/readiness/recovery behavior, provider-in-use restrictions, and restore/restart/legacy-archive behavior in the existing user and add-on documentation.

## Verification and limits

Add meaningful regression tests for archive round trips and replacement/legacy handling; provider protection through all mutation paths; API authentication/validation/staleness/reservation; immutable staging, changed launcher arguments, running/stopped/empty hosts, automatic and explicit rollback; interrupted/partial rollback and fencing; and UI selection/confirmation/errors. Keep builtin upgrade and existing Custom creation/setup tests green. Run the backend suite and frontend tests/build required by CI. Validate Ansible/YAML integration with existing test harnesses and syntax checks where available.

No live Quake Live host or shinqlx binary is assumed available. Report that limitation; automated remote orchestration tests cannot establish actual shinqlx binary compatibility.
