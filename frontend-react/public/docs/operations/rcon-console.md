# RCON Console

The RCON console provides interactive command execution against a running instance.

## How to Open

`Servers -> instance row -> Actions -> RCON Console`

The menu option is enabled only when:

- Instance status is `running`, `active`, or `updated`
- `zmq_rcon_port` is present on the instance

## Connection Model

- Frontend uses Socket.IO (`useRconSocket` hook).
- Authentication is cookie-based JWT; no RCON credentials are sent from browser forms.
- Backend resolves host IP and RCON credentials from DB on `rcon:join`.
- Commands are bridged through Redis channels to the RCON service.

## Console Features

- Command input with **Send** button.
- Up/Down arrow command history (last 50 commands).
- Read-only output viewer with Quake color rendering.
- Output buffer auto-trims to ~1000 lines.
- Connection status badge: `disconnected`, `connecting`, `connected`, `error`.

## Real-Time Game Events

The **Show real-time game events** checkbox subscribes to stats stream.

Important: stats streaming is enabled only when backend logging is in DEBUG mode. In non-DEBUG mode, subscribe events are ignored by server logic.

## Troubleshooting

- `RCON not configured for this instance`: missing IP/port/password on instance/host data.
- `Not authorized for this instance`: room join did not complete before command send.
- Connection errors: verify Redis/RCON services and host reachability.
