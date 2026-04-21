# RCON Basics

RCON lets you send live commands to a running server.

## Open RCON

- Go to instance **Actions**.
- Click **RCON Console**.

If the button is disabled, the instance is usually not in a ready state yet.
Action reference: [Instance Actions Menu](/docs/operations/instance-actions-menu)

## Basic Use

1. Type command in the input box.
2. Press **Send**.
3. Read output in the console panel.

## Real-Time Game Events

The console has a **Show real-time game events** checkbox. When enabled, the output panel shows a live stats stream alongside command responses.

Note: this only works when the QLSM backend is running in DEBUG mode. In production mode the subscription is silently ignored.

## Quality-of-Life

- Use Up/Down arrow keys to cycle through the last 50 commands.
- Output auto-trims to ~1000 lines; use `Ctrl+F` to search within it.
- Quake color codes are rendered in the output panel.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| RCON button disabled | Instance not in `running` / `active` / `updated` state |
| "RCON not configured" | Missing IP, port, or password on the instance or host |
| "Not authorized for this instance" | Room join did not complete before command was sent |
| Connection errors | Check Redis service and host reachability |

## Related Pages

- [Use Logs And Chat Logs](/docs/operations/logs-and-chat)
- [Manage A Running Server](/docs/operations/manage-instance)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
