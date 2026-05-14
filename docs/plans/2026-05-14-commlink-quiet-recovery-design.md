# CommLink Quiet Recovery Design

## Goal

Keep CommLink useful for cross-server player presence and chat while preventing
external IRC, DNS, or HTTP failures from spamming Quake Live chat, console logs,
or minqlx tracebacks.

## Current Failure Mode

The plugin treats transport lifecycle as player-visible state:

- Startup prints "Connecting" and successful IRC registration prints "Connected".
- Any disconnect or exception logs a traceback and prints a reconnecting message.
- DNS lookup failures, connection resets, remote closes, and service failures all
  repeat every reconnect attempt.
- The external IP lookup has no timeout, so plugin startup can block on an
  external HTTP service.

On a small host this creates avoidable noise and work during exactly the period
where the external services are already unreliable.

## Approved Behavior

When CommLink is connected and healthy:

- Forward player connect and disconnect events to the CommLink channel.
- Forward `!world`, `!say_world`, `!need`, and `!status` output.
- Print incoming CommLink messages to players.
- Do not print IRC transport lifecycle messages such as "connecting",
  "connected", "disconnected", or "reconnecting".

When CommLink cannot connect or loses the connection:

- Do not print global chat messages.
- Do not emit traceback spam for expected network failures.
- Do not log repeated reconnect lifecycle messages.
- Mark the transport offline.
- Drop missed player connect and disconnect events silently.
- For player/admin commands that require CommLink, reply only to the command
  caller with a short unavailable message.

## Recovery Model

Reconnect quietly in the background with bounded backoff:

- First retry: 30 seconds.
- Then 60 seconds.
- Then 120 seconds.
- Cap retries at 300 seconds.
- Reset the backoff after a successful IRC registration.

The plugin does not queue or replay presence events while offline. Once the IRC
transport is healthy again, it resumes forwarding new events.

## Error Detection

Treat these as expected transport failures:

- DNS failures from `socket.gaierror`.
- Connection resets, refused connections, aborted connections, and timeouts.
- EOF or empty reads from the IRC socket.
- Failed writes caused by a closed or resetting socket.
- HTTP failures or timeouts from the external IP lookup.
- Malformed or incomplete IRC lines.

Expected transport failures update local connection state and trigger quiet
retry. Unexpected programming errors may still be logged once because they are
bugs, not service availability problems.

## Stability Fixes

- Add timeouts to IRC connect and external IP lookup.
- Guard all IRC writes so a dead socket cannot raise into minqlx event hooks.
- Guard IRC parsing so malformed lines are ignored.
- Avoid plugin startup depending on `checkip.amazonaws.com`; use a fallback IP
  value if lookup fails.
- Keep reconnect logic inside the existing background thread.

## Non-Goals

- Do not replace IRC with another transport.
- Do not add persistent queues.
- Do not add health dashboards or admin commands for transport state.
- Do not replay missed connect/disconnect events after recovery.
