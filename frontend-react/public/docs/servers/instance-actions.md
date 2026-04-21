# Instance Action Menu

Open the instance row menu via **Actions** (three-dot button on the right of each instance row).

<img src="/docs/images/instance-actions-menu-general.png" width="263" />

## Action Reference

| Action | What it does | UI availability | Backend constraints |
| --- | --- | --- | --- |
| Edit Config | Opens config editor modal for server.cfg/mappool/access/workshop/scripts/factories. | Disabled in `deploying` and `configuring`. | Save queues config apply task. |
| RCON Console | Opens live command console over WebSocket bridge. | Enabled only if status is `running`/`active`/`updated` and `zmq_rcon_port` exists. | Requires RCON credentials on backend instance model. |
| View Server Logs | Opens remote log modal with filters (lines/time). | Enabled in actionable states. | Fetches `/instances/<id>/remote-logs`. |
| View Chat Logs | Opens remote chat log modal with file selector and line filter. | Enabled in actionable states. | Fetches `/instances/<id>/chat-logs` and `/chat-logs/list`. |
| View Details | Opens instance details drawer. | Always enabled. | None. |
| 99k LAN Rate | Toggles LAN mode and queues reconfiguration/restart. | Enabled in actionable states. | Backend rejects while busy; successful update queues task. |
| Restart | Queues instance restart task. | Enabled in actionable states. | Backend rejects while busy. |
| Start / Stop | Starts stopped instances or stops running ones. | Disabled while busy; disabled in `idle`. | Backend validates start/stop eligibility. |
| Delete | Queues instance deletion task. | Disabled in `deleting`, `deploying`, `configuring`. | Backend rejects if instance is busy. |

## Actionable States (UI)

`running`, `active`, `updated`, `error`, `stopped`, `idle`

Busy states (actions mostly disabled):

`deploying`, `configuring`, `restarting`, `deleting`, `stopping`, `starting`

## Start/Stop Behavior

- If current status is `stopped`, button shows **Start**.
- Otherwise button shows **Stop**.
- Start/Stop is not allowed while transitional tasks are running.

## LAN Rate Toggle

The toggle switches between:

- `25k` mode (`lan_rate_enabled = false`)
- `99k` mode (`lan_rate_enabled = true`)

Changing this setting queues reconfiguration and instance restart.

## Related Pages

- [RCON Console](/docs/operations/rcon-console)
- [Server Logs](/docs/operations/server-logs)
- [Chat Logs](/docs/operations/chat-logs)
- [Live Status](/docs/operations/live-status)
