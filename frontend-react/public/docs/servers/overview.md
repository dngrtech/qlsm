# Servers Overview

The **Servers** page is the operational control center for hosts and QLDS instances.

![Servers Page Placeholder](/docs/images/servers-page.png)

> Screenshot placeholder: replace `/docs/images/servers-page.png` with a real capture from the running UI.

## Page Structure

- **Host rows**: provider, region/timezone, IP, host status, host actions.
- **Instance rows**: name, hostname, port, LAN rate mode, players, instance status, instance actions.
- **Global controls**: expand/collapse all, add host.

## Built-in Polling

The page refreshes automatically when operations are in progress.

- Host poll interval: every 3 seconds while host status is transitional (`pending`, `provisioning`, `provisioned_pending_setup`, `deleting`, `rebooting`, `configuring`) or QLFilter is changing (`installing`, `uninstalling`).
- Instance poll interval: every 3 seconds while instance status is transitional (`deploying`, `deleting`, `restarting`, `configuring`, `stopping`, `starting`).
- Live status poll interval: every 15 seconds for player/map status.

## Where To Perform Operations

- Host-level operations: [Host Action Menu](/docs/servers/host-actions)
- Instance-level operations: [Instance Action Menu](/docs/servers/instance-actions)
- Remote command execution: [RCON Console](/docs/operations/rcon-console)
- Logs: [Server Logs](/docs/operations/server-logs) and [Chat Logs](/docs/operations/chat-logs)
- Player/map snapshot: [Live Status](/docs/operations/live-status)

## Common Workflow

1. Verify host status and IP.
2. Expand host and verify instance states.
3. Use instance actions for config/restart/stop/start/logs/RCON.
4. Track status transitions until instances return to `running` or `updated`.
5. Use logs and RCON when investigating failed transitions.
