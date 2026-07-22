# Global RCON — Handoff

**Repository:** `/home/rage/qlsm-global-rcon`  
**Branch:** `feature/global-rcon`  
**Current HEAD:** `d856fab feat: add Global RCON page`  
**Working tree:** clean when this handoff was written.  
**Date:** 2026-07-21

## Scope and hard constraints

- Do not push, merge, create a PR, or start/restart a dev server without explicit instruction.
- Do not retain or expose RCON credentials.
- Production source target: <=300 nonblank/noncomment lines per module; Task 5 and 6 satisfy this accounting.
- Backend fleet work and Tasks 1–6 are approved. Task 7 is implemented and targeted-tested, but has not had a final fresh spec/quality approval after its last amendments.
- Visual verification is blocked: `http://localhost:5173/global-rcon` returned `ERR_CONNECTION_REFUSED`. Do not start a server merely to satisfy visual verification.

## Commit lineage

```text
f76da01  Task 1 backend target gate / SID lifecycle (historical)
3d36914  Task 2 fleet backend Socket.IO lifecycle and fan-out
5887a05  Task 5 fleet browser session hook (amended over time)
84a8e98  Task 6 command runs/output, including StrictMode replay fix
 d856fab Task 7 Global RCON page, route, navbar, responsive styles/tests
```

`d856fab` is the current Task 7 commit; Tasks 3–6 were repeatedly amended, so use the current tree and commit range rather than stale intermediate SHA references.

## Status by task

### Task 1 — backend target gate and ownership helpers
**Status: APPROVED**

Key files:
- `ui/rcon_target_gate.py`
- `ui/socketio_events.py`
- backend target-gate tests under `tests/`

Implemented target/SID lifecycle gating and command-stat ordering.

### Task 2 — backend fleet Socket.IO lifecycle/fan-out
**Status: APPROVED**

Key files:
- `ui/rcon_fleet_events.py`
- `ui/rcon_fleet_gate.py`
- `ui/rcon_transport.py`
- `ui/socketio_events.py`
- backend fleet tests: `tests/test_socketio_events.py`, `tests/test_socketio_rcon_integration.py`, `tests/test_rcon_fleet_events.py`, `tests/test_rcon_transport.py`

Semantics:
- fleet desired-target reconciliation uses striped FIFO ownership handling;
- failed joins roll back ownership; failed final leaves restore it;
- per-target failures do not stop reconciliation;
- no credentials are emitted.

Focused backend RCON suite previously passed **110 tests**. A repository-wide backend run later had unrelated environment failures: Flask-SocketIO test client rejects configured message queues and Redis returned `Authentication required`.

### Task 3 — shared browser transport + individual console primitives
**Status: APPROVED**

Key files:
- `frontend-react/src/hooks/rconSocketTransport.js`
- `frontend-react/src/hooks/useRconSocket.js`
- `frontend-react/src/components/RconConsoleModal.jsx`
- `frontend-react/src/components/rcon/RconCommandInput.jsx`
- `frontend-react/src/components/rcon/RconRawOutputViewer.jsx`
- related tests in `frontend-react/src/hooks/__tests__/` and `frontend-react/src/components/**/__tests__/`

Critical semantics:
- transport owns shared socket acquisition/release/refcount and delayed final disconnect;
- individual cleanup order is unconditional: `rcon:unsubscribe_stats` -> `rcon:leave` -> transport release;
- target status/message/stats/error events require exact `host_id` and `instance_id`;
- backend individual `rcon:error` payloads are target-tagged `{error, host_id, instance_id}`;
- raw viewer uses incremental append/truncation, max 1,000 rendered lines.

### Task 4 — persistent target model/tree
**Status: APPROVED**

Key files:
- `frontend-react/src/utils/rconTargets.js`
- `frontend-react/src/hooks/useGlobalRconPreferences.js`
- `frontend-react/src/components/rcon/RconTargetTree.jsx`
- tests beside each module

Critical semantics:
- stable keys are positive integer `host_id:instance_id`;
- eligibility = `running` or `updated` plus a positive `zmq_rcon_port` (`active` is deliberately not eligible);
- preference keys:
  - `qlsm-global-rcon-targets-<user_id>`
  - `qlsm-global-rcon-expanded-hosts-<user_id>`
- `inventoryReady` must be `!loading && !error`; destructive reconciliation must never run during empty async loading state;
- unavailable selections remain remembered; Select None clears all remembered selections;
- target tree supports tri-state hosts, disabled unavailable children, and separate runtime state.

### Task 5 — fleet browser session hook
**Status: APPROVED**

Key file:
- `frontend-react/src/hooks/useFleetRconSession.js`
- `frontend-react/src/hooks/__tests__/useFleetRconSession.test.jsx`

Public contract:
```js
useFleetRconSession({ targets, enabled, onMessage, onStatus })
sendCommand(runId, cmd, readyTargets)
FLEET_ACK_TIMEOUT_MS === 10_000
```

Critical semantics:
- shared transport ownership only; hook owns its own listeners;
- current desired targets only; strict target filtering for status/message/error;
- disconnect fails desired targets and settles pending commands; reconnect resets targets to connecting then rejoins;
- pending sends normalize ACKs, timeout after 10 seconds, ignore late callbacks, preserve immediate not-ready results in mixed snapshots;
- `rcon:error` calls `onMessage` before failed `onStatus`, preserving active-run error evidence.

### Task 6 — command runs, output, filters
**Status: APPROVED**

Key files:
- `frontend-react/src/hooks/useRconCommandRuns.js`
- `frontend-react/src/components/rcon/RconCommandRun.jsx`
- `frontend-react/src/components/rcon/RconOutputFilters.jsx`
- `frontend-react/src/components/rcon/GlobalRconOutput.jsx`
- `frontend-react/src/components/rcon/RconRawOutputViewer.jsx`
- `frontend-react/src/components/rcon/useIncrementalViewerReplay.js`
- `frontend-react/src/components/rcon/QuakeColoredText.jsx`
- `frontend-react/src/utils/quakeColors.js`

Critical semantics:
- constants: `QUIET_AFTER_MS`, `NO_RESPONSE_AFTER_MS`, `MAX_RUNS`, `MAX_RAW_LINES`;
- raw and grouped result output are bounded to 1,000 physical content lines;
- command markers use `{type:'command', attempted:true}`;
- timer handles are per `(runId, targetKey)`, so superseded runs still transition quiet/no-response without touching newer runs;
- terminal failed/rejected/malformed/missing dispatch outcomes close matching attribution only;
- compact output is lightweight Quake-colored rendering; CodeMirror search is opt-in;
- CodeMirror replay is incremental, with a StrictMode real-editor regression test so editor recreation does not lose retained history;
- output filters are selected + retained run + raw-history union, with bounded direct list and searchable overflow.

Focused Task 6/RCON test set last observed: **108 passing**.

### Task 7 — Global RCON page, route, navbar, styles
**Status: IMPLEMENTED / TARGETED-TESTED — NEEDS FINAL REVIEW**

Current commit: `d856fab`.

Key files:
- `frontend-react/src/pages/GlobalRconPage.jsx`
- `frontend-react/src/pages/__tests__/GlobalRconPage.test.jsx`
- `frontend-react/src/App.jsx`
- `frontend-react/src/components/Navbar.jsx`
- `frontend-react/src/components/__tests__/Navbar.test.jsx`
- `frontend-react/src/index.css` (scoped `.global-rcon-*` styles)

Implemented:
- protected `/global-rcon` route;
- desktop and mobile navigation position: Servers -> Global RCON -> Docs;
- live `useServers` inventory -> `useHostOrder` -> `useGlobalRconPreferences` -> fleet session -> command runs;
- eligibility/desire and ready snapshot handling;
- corrected send payload mapping: derived tree items carry `id`, so send maps `instance_id ?? id`;
- no stats control or confirmation dialog;
- mobile accessible Targets Hide/Show toggle;
- output pane has bounded flex layout and command input is inside its non-scrolling bottom area.

Current targeted tests:
```bash
cd /home/rage/qlsm-global-rcon/frontend-react
pnpm exec vitest run src/pages/__tests__/GlobalRconPage.test.jsx src/components/__tests__/Navbar.test.jsx
```
Last result: **5/5 passing**.

Page test coverage currently includes:
- ready/skipped send snapshot and exact payload;
- zero-ready disabled send;
- inventory error rendering;
- target-pane toggle.

Navbar test coverage currently includes:
- desktop ordering/href;
- mobile ordering/href after opening Headless UI menu.

Still worth doing before calling Task 7 approved:
- fresh independent spec/quality review of `84a8e98..d856fab`;
- optionally add explicit ProtectedRoute/App route test and an `onStatus` current-run/no-revive integration assertion;
- re-run full targeted RCON/page/navigation tests after any amendment;
- visual verification remains blocked unless the user supplies an already-running environment.

### Task 8 — docs/version
**Status: NOT STARTED**

Expected files:
- `docs/rcon_integration.md`
- `docs/user/operations/rcon-console.md`
- `mkdocs.yml`
- `docs/user/index.md`
- `VERSION`
- `docs/user/version.json`
- `docs/user/releases.md`
- new `tests/test_global_rcon_docs.py`

Plan target version: `1.15.0`.

### Task 9 — final verification/delivery
**Status: NOT STARTED**

## Known verification results / caveats

### Green targeted checks
- Task 6/RCON suite: last observed **108 passing**.
- Task 7 page/navbar suite: **5 passing**.
- Production frontend build passes repeatedly.
- Targeted ESLint for changed Global RCON files passes.
- `git diff --check` passed at completed checkpoints.

### Known unrelated failures/warnings
- Full frontend run previously: **384 passed, 3 failed**, all `src/components/instances/__tests__/HooksTab.test.jsx`. Those tests expect an action-menu `menuitem Delete`, while current UI exposes a regular `Delete a.so` button. Unrelated to Global RCON.
- Build warnings: old Browserslist database; mixed dynamic/static clipboard import; large bundle warning.
- Full backend test run is environment-blocked by Socket.IO message queue test-client incompatibility and Redis authentication. Do not claim full backend suite green without repairing environment/configuration first.

## Visual verification

Checked existing environment only:
```text
http://localhost:5173/global-rcon -> ERR_CONNECTION_REFUSED
```

No server was started. Visual desktop/narrow/theme verification remains blocked.

## Recommended resume order

1. Run a fresh review on Task 7 (`84a8e98..d856fab`); fix any findings.
2. Run target test command above, targeted ESLint, `pnpm build`, and `git diff --check`.
3. Complete Task 8 docs/version with `tests/test_global_rcon_docs.py`.
4. Complete Task 9 final validation; state unrelated full-suite/environment blockers precisely.
5. Do not push/merge unless explicitly asked.
