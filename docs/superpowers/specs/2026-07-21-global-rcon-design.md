---
title: Global RCON
date: 2026-07-21
status: approved
---

# Global RCON

## Goal

Add a top-level **Global RCON** page that lets an authenticated QLSM operator select multiple eligible QLDS instances, connect to them concurrently, send one RCON command to every ready target, and inspect per-target output without losing multiline readability.

The primary production use case is fleet-wide minqlx administration across deployments such as the 15-instance x76 fleet, for example:

```text
qlx !setperm <steamid64> 5
qlx !getperm <steamid64>
```

The feature extends the existing Flask-SocketIO → Redis Pub/Sub → `rcon_service` → ZMQ pipeline. It does not introduce a second RCON transport or an implicit global Redis broadcast channel.

## Approved Product Decisions

- Add a top-level **Global RCON** navigation item between **Servers** and **Docs**.
- Route the page at `/global-rcon`.
- Use a host/instance checkbox tree inspired by the existing File Manager tree.
- Persist checked targets and expanded hosts per browser user in `localStorage`.
- Show unavailable instances, but disable their checkboxes and display the reason.
- Connect selected eligible targets immediately when the page opens or selection changes.
- Send immediately without a confirmation modal.
- At send time, target only selected instances currently reported as ready.
- Mark selected connecting or failed targets as skipped; never execute a delayed automatic retry.
- Do not subscribe to or display real-time stats/game events on Global RCON.
- Use grouped command runs in the All view and raw continuous output in per-instance views.
- Keep command/output history in frontend memory only; reload clears it.
- Reuse and update the existing RCON architecture and documentation.
- Treat every authenticated QLSM account as a fleet operator with fleet-wide management authority, matching the current product-wide authorization model; Global RCON does not introduce RBAC or host-scoped ACLs.
- Support the packaged single-worker, threaded Socket.IO topology. Multi-worker ownership coordination is not part of this feature.

## Scope

### In scope

- Global RCON page and navigation entry.
- Persisted target selection and expansion state.
- Immediate multi-instance connection management.
- Server-side fleet target validation and command fan-out.
- Per-target connection and dispatch states.
- One-line and multiline command-result presentation.
- All-output and per-instance output filters.
- Command history for the current page lifetime.
- Reusable extraction from the existing individual RCON console.
- Backend, frontend, transport regression, and documentation tests.
- Synchronizing `docs/rcon_integration.md` with the implementation.

### Out of scope

- Persistent database-backed command runs or audit history.
- Scheduled commands.
- Delayed retries after an instance reconnects.
- Command-specific parsing or special permission-management forms.
- Atomic all-or-nothing fleet execution; QLDS RCON cannot provide that guarantee.
- A new `rcon:cmd:global` Redis channel.
- Live ZMQ stats/game-event subscriptions.
- Replacing the existing per-instance RCON modal.
- Claiming semantic command success without an independent verification command.

# 1. Architecture and Data Flow

## Existing transport remains authoritative

```text
GlobalRconPage
      |
      | rcon:fleet_join / rcon:fleet_command / rcon:fleet_leave
      v
Flask-SocketIO fleet handlers
      |
      | validate DB targets, resolve credentials, join existing rooms
      | publish one message per accepted instance
      v
rcon:cmd:<host_id>:<instance_id>
      |
      v
existing rcon_service
      |
      v
per-instance ZMQ DEALER connection
      |
      v
QLDS instance
```

Responses retain the existing addressing:

```text
rcon:response:<host_id>:<instance_id>
rcon:status:<host_id>:<instance_id>
```

The existing Redis listener continues to emit `rcon:message` and `rcon:status` with `host_id` and `instance_id`. Those identifiers let the fleet frontend route every line and status to the correct target.

## Reuse boundary

### Reused as-is or with narrow extraction

- `rcon_service/connection_manager.py`: concurrent connection registry keyed by `(host_id, instance_id)`.
- `rcon_service/instance_connection.py`: ZMQ setup, command sending, line buffering, and message callbacks.
- `rcon_service/redis_client.py`: async pattern subscription and publishing.
- Per-instance Redis command, response, and status channels.
- `ui/redis_listener.py`: response/status relay carrying host and instance IDs.
- Quake color rendering and RCON CodeMirror theme.
- Existing SocketIO authentication and server-side credential lookup.

### New or generalized

- Fleet SocketIO handlers and shared backend target helpers.
- A transport hook that supports one socket joined to multiple instance rooms.
- Fleet session state and command-run state in the frontend.
- Target tree, output filters, command-run blocks, and shared command input/output primitives.

The implementation must extract common backend logic from the existing single-instance handlers rather than copying credential lookup, room naming, participant checks, and Redis payload construction.

## Fleet session lifecycle

Opening `/global-rcon`:

1. Fetch hosts and instances using the existing server inventory APIs/hooks.
2. Restore per-user checked instance IDs and expanded host IDs from `localStorage`.
3. Reconcile persisted IDs with current inventory.
4. Join/connect every selected instance that is currently eligible.
5. Track each selected target as `connecting`, `ready`, or `failed`.

Changing selection:

- Checking an eligible instance joins its existing instance room and triggers the existing connect action.
- Unchecking an instance leaves its room. The backend publishes disconnect only when no room participants remain, preserving current multi-client behavior.
- Host tri-state checkboxes select or deselect all eligible child instances.
- `Select All` selects every eligible instance; `Select None` clears all selections.
- Selection changes affect future commands only. Existing command runs retain their target snapshot and output.

Readiness is scoped to the current desired-membership/SID lifecycle. Removing a target deletes its readiness immediately. Adding or re-adding a target, receiving a join acknowledgement, losing the transport, or reconnecting with a new SID synchronously sets the target to `connecting` before Send can observe it; only a subsequent `connected` status for a target still in the current desired set changes it to `ready`. Event handlers filter against the current desired set and current socket lifecycle. Existing status messages have no generation field, so the UI cannot prove that every already-in-flight status belongs to the newest membership generation; the required ordering prevents retained stale readiness but does not claim protocol-level generation correlation.

Leaving the page emits fleet leave for joined targets and releases the browser session. Existing participant-count logic prevents a fleet page from disconnecting a socket still used by another browser client.

## Fleet command lifecycle

When the operator clicks `Send to N ready targets`:

1. The frontend trims and validates the non-empty command.
2. It generates a client-side `run_id` and snapshots all selected targets.
3. Targets whose latest frontend status is not `ready` are added to the run as `skipped` and are not sent to the backend.
4. The frontend emits one `rcon:fleet_command` event containing the command, run ID, and ready target IDs.
5. The backend deduplicates targets, validates each host/instance relationship, confirms the SID's fleet owner still owns each target and the SID remains in each instance room, and checks current DB eligibility/configuration. Connection readiness is based on the frontend's latest `rcon:status` snapshot; a disconnect racing with dispatch remains possible and is reported through subsequent target status/output rather than hidden behind the acknowledgement.
6. For each accepted target, the backend publishes the existing `{action: "command", cmd: "..."}` payload on its per-instance Redis channel.
7. The SocketIO acknowledgement returns a result for every requested target: `queued` or `rejected` with a safe reason.
8. Run creation appends one timestamped `command` event to every ready/dispatched target's raw stream before emission; skipped targets receive no command marker. A backend-rejected target retains the visibly attempted command marker while its run result shows rejection. Incoming RCON lines are then routed into that target's active command-run block and raw per-instance stream.

Fan-out is not serialized across the fleet. The existing RCON service processes per-instance actions independently under per-instance locks, so one slow target does not block the other targets.

## Dispatch and response semantics

QLDS does not echo a command ID and does not provide a reliable response-complete marker. The UI must use honest transport-oriented states:

```text
skipped -> not dispatched because target was not ready
queued  -> accepted and published toward rcon_service
receiving -> at least one response line arrived
quiet -> no new response lines for the UI inactivity interval
rejected -> backend validation or Redis publication failed
failed -> connection status changed to error/disconnected during the run
```

`queued`, `receiving`, and `quiet` do not prove that a mutation was applied. After 1.5 seconds without a new line, a receiving block becomes `quiet`. A queued target with no line after 5 seconds displays `no response yet`. A late line in either state changes the block back to receiving. These timers are presentation hints, not protocol completion signals.

Run state is monotonic with respect to evidence. Output or a connection failure received before an acknowledgement cannot be downgraded by a later `queued` acknowledgement. The five-second no-response timer starts only when `queued` is first established; duplicate and late acknowledgements are idempotent. A rejection received after output preserves the lines and displays an acknowledgement anomaly rather than erasing evidence. An `error` or `disconnected` status fails only that target's current active attribution window; a later reconnect can make the target ready for a future run but never revives or retries the failed run.

Fleet command acknowledgements have a 10-second client timeout. Transport disconnect or hook unmount settles all pending sends immediately. Missing, malformed, or top-level-error acknowledgements become safe per-target failed/rejected results, late callbacks are ignored, no automatic retry occurs, and the command input remains usable.

The newest command is the active attribution window for subsequent lines on an instance. Sending another command closes the prior run's attribution window. Because QLDS supplies no correlation ID, delayed output can be indistinguishable from output for the newer command; the raw instance stream remains the source for diagnosing such overlap.

For mutations such as permissions, the documented workflow is mutation followed by an independent read-back broadcast:

```text
qlx !setperm <steamid64> 5
qlx !getperm <steamid64>
```

# 2. User Interface and Interaction

## Navigation and page shell

Desktop navigation order:

```text
Servers | Global RCON | Docs | Settings
```

The authenticated mobile navigation contains the same Global RCON destination. The page uses the standard QLSM max-width shell, theme tokens, typography, buttons, and status indicators.

## Page layout

```text
+----------------------------------------------------------+
| GLOBAL RCON                 15 selected | 14 ready        |
+-------------------+--------------------------------------+
| TARGETS           | OUTPUT                               |
| [All] [None]      | [ALL] [PARIS-1] [PARIS-2] [+ 12]    |
|                   +--------------------------------------+
| v [~] Paris       | > qlx !setperm ... 5                |
|   [x] PARIS-1     | PARIS-1  Player permission set to 5 |
|   [x] PARIS-2     | PARIS-2  Player permission set to 5 |
|                   | NJ-1      skipped: connection error |
| > [x] New Jersey  |                                      |
|                   +--------------------------------------+
| 15 selected       | RCON> ...       [Send to 14 targets]|
+-------------------+--------------------------------------+
```

The left tree controls command recipients. The top output filters control only which output is visible. Changing an output filter must never change command targets.

## Target tree

Host rows:

- Expand/collapse control.
- Tri-state checkbox: none, some, or all eligible children selected.
- Host name and optional compact selected/eligible count.
- Host ordering follows the existing persisted Servers host order; Global RCON does not add a second independent drag order.

Instance rows:

- Checkbox.
- Connection/status indicator.
- Instance name.
- Disabled reason where applicable.

Eligibility follows the existing individual RCON action contract:

- Instance status is `running` or `updated`, matching the backend `InstanceStatus` enum. The frontend's legacy `active` label is not a persisted QL instance state and must not broaden backend eligibility.
- `zmq_rcon_port` is configured in inventory.
- Backend credential and target resolution succeeds.

The frontend may optimistically classify eligibility from inventory, but the backend remains authoritative because passwords and final network targets are server-side.

Inventory-unavailable examples:

```text
[ ] FFA Paris       stopped
[ ] Test Server     RCON not configured
```

Stopped or unconfigured rows are disabled. A selected target that suffers a runtime connection failure remains checked and its checkbox remains usable so the operator can uncheck/recheck it to reconnect. It is not ready and is skipped at send time. No command is retained for later execution.

## Persistence

Use dedicated per-user `localStorage` keys, following `useHostOrder` and `useExpandState` conventions:

```text
qlsm-global-rcon-targets-<user_id>
qlsm-global-rcon-expanded-hosts-<user_id>
```

Requirements:

- Persist checkbox changes immediately.
- Persist expansion changes immediately.
- Deleted host and instance IDs are removed during reconciliation.
- Newly created instances begin unchecked.
- Temporarily stopped, unconfigured, or failed instances retain their checked preference and become active again when eligible/ready on a later visit.
- Storage errors degrade to in-memory state without blocking the page.
- One user's preferences must not leak into another user's browser session.

## Output modes

### All view

The All view is command-oriented. One submitted command creates a run with one result block per target snapshot.

One-line responses remain compact:

```text
> qlx !setperm 7656119... 5

PARIS-1  Player permission level set to 5
PARIS-2  Player permission level set to 5
NJ-1     skipped: target not ready
```

Multiline responses use expandable per-target blocks. The target name appears once in the header, not on every line:

```text
v PARIS-1                         33 lines | quiet
  ==== ShutdownGame ====
  Server Initialization
  Hunk_Clear: reset the hunk ok
  Server: thunderstruck
  ...

> PARIS-2                         31 lines | quiet
  Server: thunderstruck | Show output
```

Adaptive behavior:

- One-line output is always visible.
- Output up to five lines is visible inline.
- Longer output uses a collapsed preview by default.
- Failed/error blocks expand automatically.
- Provide `Expand all`, `Collapse all`, and copy controls.
- Preserve Quake colors, line breaks, selection, search, and copy behavior.
- Block headers show target name, state, and line count.

### Per-instance view

Output filters are populated from the union of currently selected targets and targets that still have retained raw-stream or command-run history:

```text
[ALL] [PARIS-1] [PARIS-2] [NJ-1] [+ 12 more]
```

Only a bounded number of filters render directly. Overflow targets use a searchable menu. Readiness controls dispatch, not filter availability, so failed, connecting, or deselected targets remain inspectable while their page-lifetime history exists. Deleted inventory objects use a safe ID-based label. Clicking a target label in the All view selects that instance filter.

A per-instance view shows the raw continuous stream using the existing console rendering model, including commands, timestamps, multiline output, Quake colors, search, and line numbers. It does not change recipients.

Unsolicited RCON text received when no command run is active appears in the raw per-instance stream, not as a fabricated command result. Unrelated server prints may still appear during an active run because the protocol cannot distinguish them from command output.

## Command input

- Fixed at the bottom of the output pane.
- Label/button always displays the ready recipient count: `Send to N targets`.
- Disabled for empty input or zero ready selected targets.
- No confirmation modal for any command.
- Up/Down navigates the last 50 commands from the current page lifetime.
- After send, clear the input and keep focus.
- The command appears once in the All run and in each dispatched target's raw stream.

## Memory bounds

To prevent an open fleet console from growing without limit:

- Keep at most 50 command runs in the All view.
- Keep at most 1,000 lines per raw instance stream, matching the existing individual console behavior.
- Truncation removes oldest content and must not break the newest active run.

# 3. Components and Backend Interfaces

## Frontend component boundaries

```text
GlobalRconPage
├── RconTargetTree
│   ├── RconHostTargetRow
│   └── RconInstanceTargetRow
├── RconOutputFilters
├── GlobalRconOutput
│   └── RconCommandRun
│       └── RconTargetResultBlock
├── RconRawOutputViewer
└── RconCommandInput
```

Shared hooks/utilities:

```text
useRconSocketTransport   one authenticated shared SocketIO transport
useFleetRconSession      target joins, leaves, statuses, sends, acknowledgements
useGlobalRconPreferences per-user checked and expanded persistence/reconciliation
useRconCommandRuns       run snapshots, line routing, quiet/no-response display state
```

The backend keeps one authoritative per-SocketIO-SID/per-target ownership registry shared by individual and fleet handlers. Each `(host_id, instance_id)` entry contains only the known owner names `individual` and `fleet` in an owner set, never credentials. Acquisition is idempotent for an owner. Acquiring the first owner performs the 0→1 room join and connect publication; releasing the final owner performs the 1→0 room leave and participant-safe disconnect publication. Releasing either owner while the other remains must not leave the room or disconnect the service.

Registry transitions and command-membership snapshots use short per-SID critical sections under the supported single-worker, 12-thread deployment. Locks are never held during database resolution or Redis publication. Ownership is revalidated immediately before command publication. A process-local registry is not supported for a non-sticky multi-worker deployment; enabling such a topology requires a separate shared-ownership design.

The existing individual console should consume extracted shared primitives where practical:

- `RconRawOutputViewer` for CodeMirror setup and append/truncation behavior.
- `RconCommandInput` for input, focus, and command-history behavior where its API remains simple.
- Socket transport creation/listener plumbing underneath instance- and fleet-specific hooks.

Do not force hosts and instances through the file adapter/editor abstraction. Reuse File Manager visual/tree conventions or small generic tree primitives, not its file CRUD controller.

No new source file should exceed repository size limits. The existing 341-line `RconConsoleModal.jsx` is already over the preferred 300-line limit; extraction should reduce it rather than adding more responsibility.

## SocketIO events

All events remain on the current default SocketIO namespace.

### `rcon:fleet_join`

Request:

```json
{
  "targets": [
    {"host_id": 14, "instance_id": 29},
    {"host_id": 14, "instance_id": 31}
  ]
}
```

Behavior:

- Authenticate using the existing SocketIO decorator.
- Validate and deduplicate targets.
- Resolve each instance and credentials server-side.
- Join the existing `rcon:<host_id>:<instance_id>` room.
- Publish the existing connect action per accepted target.

Acquisition ordering is exact: validate payload and resolve the target without a registry lock; acquire the `fleet` owner in a short per-SID critical section; if this is the first owner, join the room and publish connect; then acknowledge `connecting`. If first-owner connect publication returns zero subscribers or raises, remove only the owner just acquired, leave the room only when no owner remains, and return a safe `rejected` result. Existing individual ownership is never rolled back. An explicit uncheck/recheck performs a fresh acquisition attempt.

Acknowledgement:

```json
{
  "targets": [
    {"host_id": 14, "instance_id": 29, "state": "connecting"},
    {"host_id": 14, "instance_id": 31, "state": "rejected", "reason": "RCON not configured"}
  ]
}
```

### `rcon:fleet_targets`

Used for incremental selection changes. The request supplies the desired joined target set. The backend computes joins and leaves for that browser SID, reusing the same helpers and room participant rules. This avoids frontend races from independently emitting many single-target join/leave operations.

### `rcon:fleet_command`

Request:

```json
{
  "run_id": "client-generated-opaque-id",
  "cmd": "qlx !setperm 7656119... 5",
  "targets": [
    {"host_id": 14, "instance_id": 29},
    {"host_id": 14, "instance_id": 31}
  ]
}
```

Behavior:

- Validate the strict fleet schema before target work: the event payload must be an object; `run_id` must be a non-empty opaque string of at most 128 characters; `cmd`, after trimming, must be non-empty and at most 4,096 UTF-8 bytes; `targets` must be an array of at most 100 entries; and each ID must be a positive integer but not a boolean. Invalid top-level payloads return one bounded safe error. In an otherwise valid list, an entry whose identity can be parsed may receive a per-target rejection; malformed entries never raise out of the handler.
- Deduplicate targets.
- Verify the sender is joined to each instance room.
- Re-query instances and validate host relationship and current RCON eligibility.
- Publish one existing command payload per accepted target. The shared Redis publish helper must return a success/failure result so the fleet acknowledgement can distinguish publication from failure; it must preserve the existing safe error emission behavior for the individual console.
- Never queue a future retry for rejected, disconnected, or unavailable targets.
- Do not send credentials or secret values in acknowledgements or logs.
- Do not log command contents.

Acknowledgement:

```json
{
  "run_id": "client-generated-opaque-id",
  "targets": [
    {"host_id": 14, "instance_id": 29, "state": "queued"},
    {"host_id": 14, "instance_id": 31, "state": "rejected", "reason": "Target no longer eligible"}
  ]
}
```

The acknowledgement is a dispatch report, not command completion.

### `rcon:fleet_leave`

Leaves all fleet-managed instance rooms for the current SID and applies the existing disconnect-if-no-participants behavior.

## Existing events remain compatible

The existing individual modal continues using:

```text
rcon:join
rcon:command
rcon:leave
rcon:subscribe_stats
rcon:unsubscribe_stats
```

Global RCON never emits stats subscription events. Existing server-to-client `rcon:message`, `rcon:status`, and `rcon:error` payloads already carry enough target identity and remain backward compatible.

# 4. Error Handling, Testing, and Documentation

## Error handling

### Inventory and persistence

- Inventory load failure shows the standard page-level error and sends nothing.
- Malformed local storage falls back safely and is replaced on the next user change.
- Deleted IDs are pruned without surfacing an error.

### Connection

- A failed target remains selected but displays a failed/not-ready state.
- A connection failure does not block ready targets.
- If a target reconnects, it becomes eligible for the next command only.
- Leaving the page must not disconnect connections still used by other room participants.

### Command dispatch

- Empty commands are rejected client-side and server-side.
- Invalid, duplicate, mismatched, deleted, unavailable, or unauthorized targets receive per-target rejection results.
- Redis publication failure is reported per target without claiming dispatch.
- Partial dispatch is expected and represented explicitly.
- No target rejected or skipped during a run is silently retried.

### Output

- Late lines reopen a quiet target block.
- Lines for unknown/deleted target IDs retain a safe fallback label based on IDs.
- Multiline output is appended without flattening line breaks.
- Excess output is truncated from the oldest edge.
- Because QLDS has no correlation IDs, overlapping command output is documented rather than falsely disambiguated.

## Backend tests

Add focused tests for:

- Authentication on every fleet event.
- Target payload validation and deduplication.
- Host/instance relationship validation.
- Eligibility and missing RCON configuration.
- Credentials resolved only from the database and never returned.
- Joining multiple existing instance rooms.
- Incremental desired-target reconciliation.
- Participant-safe leave/disconnect behavior.
- Fan-out publication to every accepted per-instance channel.
- Partial queued/rejected acknowledgements preserving `run_id`.
- No publication for skipped/rejected targets.
- Redis failure isolation per target.
- Existing individual RCON behavior remaining unchanged.
- Same SID individual-plus-fleet ownership in every leave order, including another SID participant; only the final owner/participant leaves and publishes disconnect.
- Initial and incremental connect-publication zero-subscriber/Redis-error compensation without removing another owner, followed by successful explicit recheck.
- Null/scalar payloads, non-array/oversized target lists, malformed entries, boolean/zero/negative IDs, overlong UTF-8 commands, and overlong/empty run IDs.
- Supported single-process threaded interleavings of reconcile, command, leave, and disconnect cleanup preserve ownership and revalidate before publication.
- Current authorization invariant: every authenticated account may use fleet events; unauthenticated requests fail, mismatched IDs fail safely, and credentials are never disclosed.

If `rcon_service` requires no semantic modification, preserve its tests and add only regression coverage proving concurrent per-instance command handling. Do not invent a global channel test because no global channel should exist.

## Frontend tests

Add tests for:

- Global RCON route and desktop/mobile navigation position.
- Per-user preference keys.
- Restoring and reconciling checked and expanded IDs.
- New instances starting unchecked.
- Temporarily unavailable selected instances retaining preference.
- Host tri-state checkbox behavior.
- Select All selecting only eligible instances.
- Disabled rows and reason labels.
- Immediate join/connect on restored or newly selected targets.
- Leaving/deselecting targets.
- Send button count reflecting ready targets only.
- Skipped snapshot entries for selected non-ready targets.
- No confirmation modal.
- No stats subscription.
- One backend fleet command event for many ready targets.
- One-line compact results.
- Multiline grouped/collapsible results.
- Late output reopening quiet blocks.
- All filter versus per-instance raw filter semantics.
- Output filtering never changing command recipients.
- Command and line retention bounds.
- Existing `RconConsoleModal` regression behavior after shared-component extraction.
- Readiness ordering for ready → deselect → reselect, transport disconnect → reconnect/new SID, join acknowledgement, and filtered late events; Send remains disabled until a fresh connected status.
- Response-before-ack, failure-before-ack, delayed/duplicate acknowledgements, rejection-after-output anomaly, and no-response timer starting only on first queued acknowledgement.
- Queued/receiving/quiet → failed for the current run, reconnect not reviving it, and failures with no active run.
- Raw command marker precedes output for ready targets, is absent for skipped targets, and remains visibly attempted when backend-rejected.
- Ten-second acknowledgement timeout, disconnect/unmount settlement, malformed/top-level-error acknowledgement normalization, and ignored late callback.
- Filters include current selection plus retained-history targets, including failed, deselected, and deleted-ID fallback cases.

## Documentation

Update:

- `docs/rcon_integration.md` to describe the actual default namespace, current event names, `content` response field, line-by-line response behavior, implemented fleet events, and the absence of the originally proposed REST routes.
- `docs/user/operations/rcon-console.md` to distinguish individual and Global RCON workflows.
- User navigation/action references for the new top-level page.
- Screenshots only after the final UI exists.

The documentation must explicitly state that fleet dispatch is non-atomic and that administrative mutations should be followed by an independent read-back command.

## Success Criteria

- Global RCON appears between Servers and Docs on desktop and in mobile navigation.
- A user can persistently select all 15 x76 instances and restore that selection on a later visit.
- Eligible selected targets connect concurrently on page entry.
- Unavailable targets remain visible, disabled, and explained.
- One command event results in per-instance Redis publications for every ready accepted target.
- A failed/connecting selected target is skipped and never receives a delayed command.
- One-line permission responses are readable across the fleet.
- Multiline map output remains grouped by target and can be expanded without interleaving prefixes on every line.
- Per-instance filters preserve the existing raw console experience.
- Global RCON never subscribes to game stats.
- Existing individual RCON behavior remains functional.
- UI states never overclaim command success beyond available transport evidence.
- Tests and synchronized RCON/user documentation pass review.

---
**Review loop closed:** 2026-07-21
- Findings: `docs/findings/2026-07-21-global-rcon-findings.md`
- Assessment: `docs/assess-review-findings/2026-07-21-global-rcon-assessment.md`
- Accepted findings folded in: Critical 1–3; Important 2–8; Minor 1 and 3.
- Deferred: Minor 2 (`crypto.randomUUID()` guarded fallback), optional and non-blocking.
