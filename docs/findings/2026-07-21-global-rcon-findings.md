# Global RCON Pre-Implementation Findings — Pass 1

## Critical

### 1. Shared-socket room ownership is not safe between the individual and fleet consoles

The design requires one shared Socket.IO transport and says fleet cleanup must not disturb unrelated room membership, but Socket.IO room membership is a set, not reference-counted. If an individual console and Global RCON use the shared socket (the same SID) for the same instance, `rcon:fleet_leave` can call `leave_room` and remove the individual console's membership; conversely, the individual `rcon:leave` can remove the fleet membership. The proposed fleet-only `_fleet_targets` set cannot detect the other owner. This can silently stop output delivery or publish a disconnect while one UI still needs the connection.

**Required fix:** Define one authoritative per-SID/per-target ownership registry with owner/refcount information for both individual and fleet joins. Refactor every join/leave/disconnect path to acquire or release an owner and call `join_room`, `leave_room`, and participant-safe Redis disconnect only on the corresponding 0→1 or 1→0 transitions. Add simultaneous individual-plus-fleet lifecycle tests before extracting the shared browser socket.

### 2. The plan can dispatch using stale readiness after deselection, reconnect, or Socket.IO reconnection

`useFleetRconSession` stores statuses in a `Map`, but the plan does not clear or reset a target's status when it leaves the desired set, is re-added, receives a new join acknowledgement, or the socket reconnects with a new SID. A previously ready target can therefore be immediately counted as ready and receive a command before the new room/connect lifecycle reports readiness. Late status events from an earlier lifecycle can also overwrite the current lifecycle. This violates the core rule that only targets currently reported ready may receive a command and is especially risky for administrative mutations.

**Required fix:** Specify a target membership generation/state machine. Removing a target must invalidate its readiness; adding/rejoining or reconnecting the socket must synchronously set it to `connecting` before Send can observe it. Ignore status events that cannot belong to the current membership generation where possible, and make the backend join acknowledgement establish only `connecting`, never ready. Add tests for ready→deselect→reselect, transport disconnect→reconnect, and late old-lifecycle status events.

### 3. Authentication is specified, but operator/target authorization is not

The goal says an authenticated QLSM operator can control the fleet, and error handling promises rejection of unauthorized targets. The backend plan, however, applies only the existing `authenticated_only` decorator and resolves arbitrary numeric host/instance IDs directly from the database. No role/capability check or per-target visibility/control rule is defined. If QLSM has any authenticated non-operator or scoped users, this is an IDOR that exposes RCON output and command execution on every instance whose IDs can be guessed.

**Required fix:** Define the exact authorization policy before implementation (for example, a global RCON capability plus the existing per-host access predicate). Enforce the same policy in fleet join, desired-target reconciliation, command, and any individual helper refactor; reject safely without revealing target existence. Add tests for authenticated-but-unauthorized users and mixed authorized/unauthorized target lists. If every authenticated account is intentionally a fleet operator, state and test that invariant explicitly.

## Important

### 1. “No delayed retry” is not guaranteed at the Redis/RCON-service boundary

The frontend readiness snapshot and DB eligibility check do not prove that the per-instance connection is still ready when `{action: "command"}` reaches `rcon_service`. The spec acknowledges a disconnect race but does not define whether the existing service drops, buffers, reconnects for, or later executes a command received while disconnected. The plan proposes only generic concurrent handling regression coverage. A buffered administrative command could execute after reconnection, directly contradicting the no-delayed-retry decision.

**Required fix:** Document and verify the existing `rcon_service` command-on-disconnected behavior. If it can retain or reconnect-and-send commands, add an explicit dispatch token/readiness guard or a command action that is dropped when the connection is not ready. Test that a command racing with disconnect is either sent immediately on the current connection or rejected/dropped and is never executed after a later reconnect.

### 2. Responses can arrive before the fleet acknowledgement and corrupt run state

Redis publication occurs before the Socket.IO acknowledgement is returned, so `rcon:message` can arrive while a target is still in its provisional state. The planned `applyDispatchAck` can then overwrite `receiving` with `queued`. Likewise, the five-second no-response timer appears to begin in `startRun`, even though dispatch may not yet have been acknowledged. This can downgrade truthful state or show “no response yet” before the target was known to be queued.

**Required fix:** Define monotonic state transitions and start dispatch timers only when a target is acknowledged `queued`. `applyDispatchAck` must not downgrade a target that has already received output or failed. Preserve early lines, and treat a later rejection after early output as an explicit anomalous state rather than deleting evidence. Add response-before-ack, failure-before-ack, delayed-ack, and duplicate-ack tests.

### 3. Connection status is not wired into command-run failure state

The spec requires an active target result to become `failed` when its connection changes to error/disconnected. `useFleetRconSession` returns only `statuses` and `sendCommand`, while `useRconCommandRuns` receives messages and acknowledgements but no status transition. The page composition does not describe an effect or callback that forwards target failures into active runs. As written, result blocks can remain queued/receiving/quiet after a known disconnect.

**Required fix:** Add an explicit status-event flow from the socket session into command-run state (for example, `onStatus`/`applyTargetStatus`). Define which active run is affected and ensure later reconnect does not resurrect or retry that run. Test queued→failed, receiving→failed, reconnect-after-failed, and failure for a target with no active run.

### 4. Commands are missing from per-instance raw streams

The spec requires each dispatched command to appear in the target's raw stream. The planned command-run hook says `appendMessage` always appends incoming response lines, but neither `startRun` nor the page send flow appends a command event to each ready target's raw stream. The per-instance view would therefore not preserve the existing console model.

**Required fix:** On run creation, append one command event—with timestamp and command event type—to every dispatched target's raw stream before emitting. Do not append it to skipped targets; decide and document whether backend-rejected targets retain the attempted command marker. Add raw-stream command ordering and skipped/rejected behavior tests.

### 5. Socket acknowledgements have no timeout, disconnect, or malformed-response handling

`sendCommand` returns a Promise that resolves only through the acknowledgement callback. A dropped packet, server exception, authentication failure, or disconnect can leave `handleSend` pending forever and run targets in provisional states. Calls such as `applyDispatchAck(id, ack)` also assume a correctly shaped object.

**Required fix:** Add a bounded acknowledgement timeout and settle pending sends on socket disconnect/unmount. Validate acknowledgement shape and convert timeout/malformed/global errors into per-target safe rejection/failure states without retrying. Ensure the input remains usable. Add tests for no callback, disconnect before callback, callback after timeout, top-level server error, and malformed acknowledgement.

### 6. Fleet payload validation lacks resource bounds and robust top-level handling

The sketched handlers call `data.get(...)` without proving `data` is a dict, silently treat a non-list `targets` value as empty, accept booleans as Python integers, and do not bound command length, `run_id`, or target count. One malformed element can raise out of the generator and abort the event without a safe acknowledgement. An authenticated client can also submit huge target lists or commands, causing database/Redis work and oversized logs/messages.

**Required fix:** Define a strict event schema: object payload, opaque string `run_id` with a length bound, trimmed command with a protocol-appropriate byte/character bound, a fleet-size target cap, and positive non-boolean integer IDs. Return a deterministic safe top-level error or per-entry rejection rather than raising. Avoid logging command contents/secrets. Add boundary and adversarial payload tests.

### 7. Fleet registry concurrency and deployment model are underspecified

The registry is a process-local `defaultdict(set)` guarded by an `RLock`, but the plan does not state that reconciliation, command membership checks, and disconnect cleanup are atomic with respect to one another. It also does not state whether production may run multiple Socket.IO workers and, if so, what sticky-session/message-queue guarantees keep all events for one SID on the process that owns the registry. Concurrent target updates and commands can otherwise publish after a leave or lose cleanup state.

**Required fix:** Document the supported Socket.IO worker topology. Serialize per-SID desired-set reconciliation, owner transitions, command membership checks, and cleanup, or move authoritative ownership to shared state if routing cannot guarantee process affinity. Define lock boundaries without holding a global lock across slow DB/Redis operations. Add concurrent reconciliation/command/leave tests and, if multi-worker is supported, an integration test for SID affinity/cleanup.

### 8. Join/connect publication failure has no defined state or rollback path

`rcon:fleet_join` is supposed to return `connecting` only for accepted targets, but `_set_targets` ordering and behavior are not defined when room join succeeds and Redis connect publication returns zero subscribers or raises. Retaining the room/registry can leave a target permanently desired without another connect attempt; rolling back incorrectly can race with another owner. The frontend also has no specified way to distinguish this from ordinary connection failure.

**Required fix:** Specify the transaction/state sequence for ownership acquisition, room join, connect publication, acknowledgement, and rollback. A publication failure must return a safe per-target failure and leave ownership in a state where explicit uncheck/recheck can make a fresh attempt, without disrupting other owners. Test zero subscribers and Redis exception on both initial join and incremental reconciliation.

### 9. Per-user preference switching can leak or overwrite selections in a shared browser session

Per-user key names alone do not make the hook safe when the authenticated user changes without a full page reload. A persistence effect can write the previous user's in-memory selections under the new user's key before the new key is loaded, and old selections can briefly drive fleet joins. The plan tests fixed user ID keys but not account transitions.

**Required fix:** Key preference state initialization and effects by a stable authenticated user ID, block fleet enablement while preferences for that identity are loading/reconciling, and atomically reset state on identity change before any persistence or joins. Add user A→logout→user B and missing-user-ID tests.

### 10. The hard-coded `1.15.0` release bump is unsupported feature scope

The approved spec requires synchronized documentation but does not approve a release number or release-manifest update. The plan invents version `1.15.0`, a dated release row, and a test permanently asserting that exact version. This can collide with parallel work or the repository's actual release process and turns a feature implementation into a release operation.

**Required fix:** Remove the version bump and exact-version assertion from this implementation unless a separate release decision confirms `1.15.0`. If version synchronization is mandatory repository policy, derive/check consistency among current version sources rather than hard-coding a feature-specific future version, and perform the bump in a release-owned task.

## Minor

### 1. Output-filter eligibility is contradictory

The spec says “Selected ready targets” appear as filters, but its example includes `NJ-1` while the surrounding example shows that target skipped for connection error. The plan passes all `selectedTargets` to filters. This affects whether operators can inspect retained raw output for failed, connecting, deselected, or deleted targets.

**Required fix:** Choose and document one filter population rule. Prefer targets with retained raw/run history plus currently selected targets, with status shown separately from filter availability, so failure does not hide diagnostic output.

### 2. `crypto.randomUUID()` needs an explicit browser compatibility decision

The page plan calls `crypto.randomUUID()` directly without a fallback or compatibility test. It is unavailable in some older/non-secure browser contexts, which would make Send fail before run creation.

**Required fix:** Confirm the supported browser/secure-context baseline or use a small tested opaque-ID helper with a collision-resistant fallback. Test the absent-`randomUUID` path if such environments are supported.

### 3. Documentation tests assert wording rather than behavior or structure

Assertions such as requiring the literal phrase `line-by-line` and exact version `1.15.0` are brittle and can fail valid documentation edits while missing contract errors.

**Required fix:** Limit automated checks to stable structural requirements (files/nav entries and canonical event names) and review semantic warnings as documentation content. Do not bind prose to incidental wording or an unapproved release number.

## Open Questions

1. Are all authenticated QLSM users intentionally authorized to execute RCON on every host, or is there an operator/admin capability or host scope that fleet handlers must enforce?
2. What does the current `rcon_service` do when a command action arrives while its instance connection is disconnected or reconnecting: drop, buffer, reconnect, or send later?
3. Is production Flask-SocketIO single-worker, sticky-session multi-worker, or non-sticky multi-worker, and where must per-SID ownership live for that topology?
4. When connect publication fails, should the target remain joined/selected in a failed state awaiting an explicit uncheck/recheck, or should backend membership be rolled back immediately?
5. Should raw output remain selectable after a target is deselected or deleted if the current page still retains its command runs/stream?
6. Is `1.15.0` an independently approved release version, or should this feature avoid release metadata changes?

## Tests To Add

- Same SID opens an individual console and Global RCON for the same target; leaving either owner preserves the other's room, messages, and service connection.
- Two owners on one SID plus another SID exercise all leave/disconnect orders and publish exactly one final disconnect.
- Ready target is deselected/reselected and cannot be sent to until a fresh connected status arrives.
- Socket reconnect with a new SID resets all readiness, rejoins desired targets, and ignores stale lifecycle status.
- Command racing with service disconnect is never executed after a later reconnect.
- Response/status arrives before dispatch acknowledgement; acknowledgement cannot downgrade receiving/failed state.
- No-response timer starts only after queued acknowledgement; delayed/missing/malformed acknowledgements settle safely.
- Active run transitions queued/receiving/quiet→failed on disconnect and is not revived or retried on reconnect.
- Each dispatched command appears once in each dispatched target's raw stream and not in skipped targets' streams.
- Authenticated unauthorized user and mixed-scope fleet requests cannot join rooms, receive output, or publish commands.
- Null, scalar, oversized, deeply duplicated, boolean-ID, negative-ID, overlong-command, and overlong-`run_id` payloads return bounded safe errors.
- Initial and incremental connect publication failures have deterministic ownership/room rollback behavior and permit an explicit later retry.
- Concurrent `fleet_targets`, `fleet_command`, `fleet_leave`, and disconnect cleanup preserve registry/room invariants.
- User identity changes in one browser session never persist, display, or join the previous user's selected targets.
- Failed/connecting/deselected target output remains reachable according to the chosen filter-retention rule.
