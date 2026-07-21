# Global RCON Pre-Implementation Findings Assessment — Pass 2

## Scope and evidence

This assessment compares the approved design, implementation plan, Pass 1 findings, and the current repository implementation. It applies the pragmatic code-owner standard: address realistic correctness, security, and lifecycle failures before they become implementation defects; avoid adding machinery for unsupported deployment models or hypothetical product capabilities.

Repository facts used in the assessment include:

- `ui/socketio_events.py` currently joins and leaves Socket.IO rooms directly and authenticates events with a valid JWT cookie.
- `ui/models.py` has no user role, capability, or host-scope model; the application gives authenticated users the same management API access.
- `rcon_service.connection_manager.ConnectionManager.send_command()` returns `False` when no connected instance connection exists. A `command` action does not initiate a connection or schedule a retry.
- The production Docker command explicitly runs one Gunicorn worker with 12 threads. Flask-SocketIO is configured with a Redis message queue, but the supported packaged topology is currently single-worker.
- The current release sources agree on `1.14.10`, and repository policy requires version sources to move together for a merged PR.
- The frontend already uses a guarded `crypto.randomUUID()` fallback for notification IDs.

## Critical

### Critical 1. Shared-socket room ownership is not safe between the individual and fleet consoles

- **Finding says:** A Socket.IO room is set membership, not reference-counted ownership. With one SID using the same target through individual and fleet consumers, either consumer can leave the room and disrupt the other. The fleet-only target set cannot prevent that.
- **Assessment:** Accept
- **Edge-case validity:** Real at the proposed shared-transport boundary. The current page structure normally unmounts the Servers-page modal before entering Global RCON, which reduces frequency, but the plan deliberately creates a reusable shared socket and promises cleanup isolation. StrictMode/handoff timing and future simultaneous consumers make owner-blind leave semantics an unsafe foundation. The defect is also easy to exercise directly through the event API, independent of today's page layout.
- **Pros:** A per-SID/per-target owner model makes room and Redis connection lifecycle deterministic, protects the existing individual console during extraction, and directly fulfills the design's cleanup-isolation promise.
- **Cons:** A fully generic reference-counting framework would be unnecessary. It adds state and cleanup paths to sensitive existing handlers.
- **Action:** Fix before implementation
- **Reasoning:** Task 1/2 should establish a small authoritative ownership registry before Task 3 shares the browser socket. It only needs the two known owners (`individual` and `fleet`) and transition-based room/connect/disconnect operations, not a general lease system. Add the simultaneous-owner lifecycle tests identified by the finding. This blocks implementing fleet leave and shared transport on the plan's current ownership model.

### Critical 2. The plan can dispatch using stale readiness after deselection, reconnect, or Socket.IO reconnection

- **Finding says:** Readiness is retained in a `Map` without lifecycle invalidation, so a reselected or reconnected target may be treated as ready before a fresh connection status arrives; old status events may also overwrite new lifecycle state.
- **Assessment:** Accept
- **Edge-case validity:** Real and routine, not speculative. Deselect/reselect and Socket.IO reconnection are normal supported interactions. The sketched hook explicitly retains status state and does not synchronously reset it on these transitions.
- **Pros:** Resetting desired targets to `connecting` on acquisition/reacquisition is small, testable, and protects the central “ready at click time” rule.
- **Cons:** True server-event generation correlation is unavailable because existing status payloads carry no membership generation. A complex generation protocol on every relay event would expand scope.
- **Action:** Fix before implementation
- **Reasoning:** The plan must define lifecycle invalidation before Task 5. On remove, delete/invalidate status; on add, join acknowledgement, transport disconnect, and reconnect, synchronously mark desired targets non-ready before Send can observe them. Filter events by the current desired set and SID lifecycle. Do not promise perfect rejection of already-in-flight old server statuses unless the protocol is extended with a generation; instead make the state ordering and its limits explicit. The basic stale-ready bug blocks implementation.

### Critical 3. Authentication is specified, but operator/target authorization is not

- **Finding says:** Fleet handlers authenticate but do not enforce an operator capability or per-target scope, creating an IDOR if authenticated non-operators or scoped users exist.
- **Assessment:** Acknowledge
- **Edge-case validity:** The security consequence would be real in a scoped multi-role application, but that application model does not exist here. `User` has no role or host-scope fields, inventory and mutating instance APIs expose all targets to any authenticated account, and QLSM is documented/architected as an operator management UI. Inventing fleet-only RBAC would be inconsistent and substantial scope creep.
- **Pros:** Explicitly documenting the authorization invariant prevents ambiguity and ensures malformed/mismatched targets still fail safely.
- **Cons:** Adding roles, capabilities, or per-host ACLs solely for Global RCON would be a new product/security model and would not secure the rest of the already-global management API.
- **Action:** Amend plan
- **Reasoning:** State that, in the current product, possession of an authenticated QLSM account is the operator authorization boundary and all authenticated users have fleet-wide management authority. Tests should cover unauthenticated rejection, host/instance mismatch, and non-disclosure of credentials. Do not create RBAC or scoped authorization in this feature. This clarification does not block implementation once recorded.

## Important

### Important 1. “No delayed retry” is not guaranteed at the Redis/RCON-service boundary

- **Finding says:** A command reaching `rcon_service` while disconnected might be buffered, reconnect, and execute later, contradicting the no-delayed-retry decision.
- **Assessment:** Reject
- **Edge-case validity:** The premise is not supported by the current service. `RconService` handles `command` by calling `ConnectionManager.send_command()`; that method immediately returns `False` if the connection is absent or not marked connected and never calls `connect()`. Redis Pub/Sub itself does not retain the message for later subscribers. A race after a ZMQ send has been accepted is the transport race already disclosed by the design, not an application-level delayed retry.
- **Pros:** A focused regression test confirming disconnected commands are dropped would document current behavior.
- **Cons:** Dispatch tokens cannot provide end-to-end correlation that QLDS does not support, and adding a new command protocol for a behavior already dropped by the service is needless complexity.
- **Action:** No action
- **Reasoning:** The implementation should preserve existing service behavior, but this finding does not require a design or plan change and does not block work. Existing/final regression coverage may assert the drop behavior as part of normal verification; no reconnect guard or token is warranted.

### Important 2. Responses can arrive before the fleet acknowledgement and corrupt run state

- **Finding says:** Because publication precedes the Socket.IO acknowledgement, output or failure can arrive before `applyDispatchAck`; a later acknowledgement can incorrectly downgrade state, and a no-response timer can start before dispatch is acknowledged.
- **Assessment:** Accept
- **Edge-case validity:** Real under normal asynchronous scheduling, especially with a local Redis/RCON path. The plan currently gives no precedence rules between message, status, and acknowledgement events.
- **Pros:** Monotonic reducers and acknowledgement-started timers produce honest UI states and deterministic tests.
- **Cons:** Handling every impossible state combination separately would overcomplicate the UI. The anomaly can be represented while preserving evidence rather than modeled as protocol certainty.
- **Action:** Amend plan
- **Reasoning:** Task 6 should specify monotonic evidence precedence: received output and failure cannot be downgraded to queued; queued starts the five-second timer only when first established; duplicate/late acknowledgements are idempotent; a rejection after output preserves the output and surfaces an anomaly. Add response-before-ack, failure-before-ack, delayed-ack, and duplicate-ack tests.

### Important 3. Connection status is not wired into command-run failure state

- **Finding says:** The session hook returns statuses but no status callback reaches command-run state, so active results can remain queued/receiving/quiet after a known disconnect.
- **Assessment:** Accept
- **Edge-case validity:** Directly demonstrated by the planned hook interfaces and page composition. It contradicts the approved `failed` state semantics.
- **Pros:** An `onStatus` callback or page effect is a narrow interface addition and keeps run state truthful.
- **Cons:** Status propagation must avoid rerender loops and must affect only the target's active attribution window, not old closed runs.
- **Action:** Amend plan
- **Reasoning:** Add `applyTargetStatus(targetKey, status)` (or equivalent) to Task 6 and wire it from Task 5/7. Error/disconnected should fail only the current active result. Reconnection may make the target ready for a future run but must not revive or retry the failed run. Add the proposed transition tests.

### Important 4. Commands are missing from per-instance raw streams

- **Finding says:** The plan appends response messages to raw streams but never appends each dispatched command, contrary to the specified existing-console experience.
- **Assessment:** Accept
- **Edge-case validity:** Certain from the sketched `startRun` and send flow; no command raw event is created.
- **Pros:** Appending a command event during run creation is low cost and restores required ordering/readability.
- **Cons:** Backend rejection after the optimistic command marker can make the raw stream look like execution unless the event is visibly an attempted/dispatched command and result state remains authoritative.
- **Action:** Amend plan
- **Reasoning:** Task 6/7 should append one timestamped command event to each ready target when the run is created, before emission. Do not append to skipped targets. Retain the attempted marker if the backend later rejects it, while showing rejection in the run, because removing history would hide what the operator attempted. Test ordering and skipped/rejected behavior.

### Important 5. Socket acknowledgements have no timeout, disconnect, or malformed-response handling

- **Finding says:** The send Promise may never settle, and the page assumes every acknowledgement is a correctly shaped object.
- **Assessment:** Accept
- **Edge-case validity:** Real for disconnects, server exceptions, authentication expiry, and malformed handlers. Socket.IO callback acknowledgements are not guaranteed to arrive.
- **Pros:** A bounded timeout and central acknowledgement normalization prevent permanently provisional runs and keep Send usable.
- **Cons:** Pending-send bookkeeping and late-callback suppression add modest complexity; very short timeouts could falsely report failure during load.
- **Action:** Amend plan
- **Reasoning:** Task 5 needs one bounded timeout policy, disconnect/unmount settlement, response-shape validation, and idempotent late-callback handling. Convert transport/global failures into per-target failed/rejected presentation without retry. Tests should cover the cases in the finding. This is necessary before relying on `await sendCommand()` in Task 7.

### Important 6. Fleet payload validation lacks resource bounds and robust top-level handling

- **Finding says:** Sketched handlers assume object payloads, accept Python booleans as integers, treat invalid target containers inconsistently, allow malformed entries to abort processing, and set no command/run/target limits.
- **Assessment:** Accept
- **Edge-case validity:** Real and reachable by any authenticated browser or API client. `data.get` on a scalar raises, and `isinstance(True, int)` is true in Python.
- **Pros:** A small schema helper with explicit limits yields deterministic acknowledgements, bounded work, and simpler handler logic.
- **Cons:** Extremely elaborate schema tooling or deep adversarial fuzz infrastructure would be excessive for this internal operator UI.
- **Action:** Amend plan
- **Reasoning:** Task 1/2 should define plain-code validation for object payloads, bounded non-empty string command and run ID, a fleet target cap comfortably above the 15-instance use case, and positive non-boolean integer IDs. Invalid top-level payloads should return one safe error; valid lists may return per-target rejection where identity can be parsed. Avoid command-content logging. Add focused boundaries, not a new validation framework.

### Important 7. Fleet registry concurrency and deployment model are underspecified

- **Finding says:** Registry operations may interleave in the threaded server, and a process-local registry is unsafe if events for a SID can land on different workers.
- **Assessment:** Acknowledge
- **Edge-case validity:** Thread interleaving is realistic because production uses 12 threads. The multi-worker concern is not current: the packaged Docker command explicitly sets `--workers 1`. Redis message-queue configuration does not by itself make per-SID process-local ownership safe under an unsupported worker topology.
- **Pros:** Declaring single-worker support and using short per-SID critical sections makes current behavior understandable and race-resistant.
- **Cons:** Shared authoritative ownership or multi-worker affinity integration testing would be substantial scope for a topology QLSM does not deploy.
- **Action:** Amend plan
- **Reasoning:** Document the supported single-worker topology. Protect owner-set transitions and membership snapshots with short per-SID locking; do not hold locks during DB lookup or Redis publication. Revalidate ownership immediately before publication where needed. Add focused same-process interleaving tests, but do not move ownership to Redis or claim multi-worker support in this feature.

### Important 8. Join/connect publication failure has no defined state or rollback path

- **Finding says:** The plan does not define room/registry behavior when connect publication fails, so targets can remain stuck or rollback can disrupt another owner.
- **Assessment:** Accept
- **Edge-case validity:** Real: Task 1 explicitly changes publication to report zero subscribers/errors, but Task 2 does not specify how `_set_targets` consumes that result.
- **Pros:** A defined acquisition transaction prevents stuck membership and makes explicit recheck retry reliable.
- **Cons:** Perfect transactional rollback across Socket.IO and Redis is impossible; pretending it is atomic would add complexity without a true guarantee.
- **Action:** Amend plan
- **Reasoning:** Define a compensating sequence around the owner registry from Critical 1. Acquire owner, perform the 0→1 room join/connect publication, and on publication failure remove only the just-acquired owner; leave the room only if no owners remain. Return a safe failed/rejected state. An uncheck/recheck then retries cleanly. Add initial and incremental failure tests for zero subscribers and Redis exceptions.

### Important 9. Per-user preference switching can leak or overwrite selections in a shared browser session

- **Finding says:** If the authenticated identity changes without reload, effects may persist user A's in-memory state under user B's key or briefly join A's targets.
- **Assessment:** Reject
- **Edge-case validity:** The hook-level scenario is technically possible in isolation, but it is not a supported application transition. Account changes go through logout, which removes authentication and unmounts protected page content; login then mounts fresh state. There is no in-place account switch while Global RCON remains enabled.
- **Pros:** Identity-transition tests could make a reusable hook more defensive.
- **Cons:** Adding an asynchronous preference-loading phase and fleet gate for an impossible current UI lifecycle complicates immediate localStorage initialization and normal joins.
- **Action:** No action
- **Reasoning:** Per-user keying plus protected-page unmount/remount satisfies the approved requirement. Normal tests should still verify keys and cleanup on unmount. Revisit only if QLSM adds in-place account switching or keeps protected pages mounted through logout.

### Important 10. The hard-coded `1.15.0` release bump is unsupported feature scope

- **Finding says:** The plan invents a release version and date not approved by the feature spec, risking collision with parallel work and coupling implementation to release operations.
- **Assessment:** Reject
- **Edge-case validity:** Parallel version conflicts are ordinary branch integration concerns, not a reason to omit required release synchronization. This repository explicitly requires `VERSION`, `docs/user/version.json`, and `docs/user/releases.md` to move together on every merged PR. A new user-visible feature warrants the planned minor bump from `1.14.10` to `1.15.0`.
- **Pros:** Keeping the release task ensures the footer, update notice, and changelog agree.
- **Cons:** The branch may need to rebase and choose a new version if another release lands first; an exact-version prose test is brittle (addressed under Minor 3).
- **Action:** No action
- **Reasoning:** Retain the synchronized version bump in scope. Before delivery, re-check the target branch and update the planned version if it has been consumed by parallel work. That is normal release hygiene and does not block implementation now.

## Minor

### Minor 1. Output-filter eligibility is contradictory

- **Finding says:** The spec says selected ready targets become filters, while its example and plan imply selected failed targets are also shown; there is no rule for deselected/deleted targets with retained output.
- **Assessment:** Accept
- **Edge-case validity:** Real product ambiguity. Hiding a failed target's filter would make diagnostic raw output inaccessible, and changing selection should not erase current-page history.
- **Pros:** A history-aware filter rule preserves evidence and separates recipient selection from output navigation.
- **Cons:** Keeping every ever-seen target forever would clutter the filter bar, though page-memory bounds and overflow search already constrain presentation.
- **Action:** Amend plan
- **Reasoning:** Populate filters from the union of currently selected targets and targets with retained raw/run history. Status controls readiness but not filter availability. Keep safe ID-based labels for deleted inventory objects. This resolves the spec contradiction without adding persistence.

### Minor 2. `crypto.randomUUID()` needs an explicit browser compatibility decision

- **Finding says:** Direct use can fail in older or non-secure contexts; the plan should set a browser baseline or add a fallback.
- **Assessment:** Acknowledge
- **Edge-case validity:** Limited. Production is expected to run in a secure context and the stack already targets modern React/Vite browsers, where `crypto.randomUUID()` is broadly available. Localhost is also treated as secure. Nevertheless, the repository already uses a guarded fallback in `NotificationProvider.jsx`, showing an established low-cost convention.
- **Pros:** Reusing a tiny opaque-ID helper avoids a send-time crash and keeps tests portable.
- **Cons:** A collision-proof compatibility subsystem or legacy-browser policy exercise would be overengineering; run IDs are client-local correlation labels, not security tokens.
- **Action:** Optional follow-up
- **Reasoning:** Prefer extracting/reusing the existing guarded pattern while implementing the page if convenient. Its absence should not block implementation or delivery under the current browser baseline.

### Minor 3. Documentation tests assert wording rather than behavior or structure

- **Finding says:** Literal `line-by-line` and exact `1.15.0` assertions are brittle and do not prove the documented semantics.
- **Assessment:** Accept
- **Edge-case validity:** Real maintainability issue in the proposed test. Valid editorial changes or a rebase-driven version change would fail for no contract regression.
- **Pros:** Structural checks for canonical event names, navigation, and cross-file version consistency catch durable errors without freezing prose.
- **Cons:** Automated tests cannot fully validate nuanced documentation warnings; human review remains necessary.
- **Action:** Amend plan
- **Reasoning:** Keep the docs test, but assert stable structure and version consistency rather than incidental wording or one forever-fixed release number. Review non-atomic dispatch, no-retry, and read-back guidance semantically during final diff review.

## Verdict and action counts

- **Accept:** 10
- **Acknowledge:** 3
- **Reject:** 3
- **Total findings assessed:** 16
- **Findings needing action before or during implementation:** 12
  - **Fix before implementation:** 2 (Critical 1–2)
  - **Amend plan:** 10 (Critical 3; Important 2–8; Minor 1 and 3)
- **Optional follow-up, not required to proceed:** 1 (Minor 2)
- **No action:** 3 (Important 1, 9, and 10)

**Bottom line:** 12 of 16 findings need action. Fix the two ownership/readiness blockers and incorporate the ten focused plan amendments; reject the proposed RBAC expansion, reconnect-token machinery, unsupported account-switch handling, multi-worker shared registry, and removal of required release synchronization where those exceed the repository's actual product/deployment model.
