# Live Status

Live status shows near-real-time player and match state for each running instance.

## Open Live Status

1. In the **Servers** page, click the player count pill in the instance row: <img class="docs-inline-icon" src="/docs/images/player-count.png" width="80" />.
2. QLSM opens the full **Live Status** drawer.

![Instance Live Status](/docs/images/instance-live-status.png)

You can also open **View Details** for an instance and use the **Live Status** section there. Clicking the **Players** count pill in that section opens the same Live Status drawer.

## Refresh Model

- UI polls `/api/server-status` every 15 seconds.
- If a specific instance has no live payload, UI shows an offline/empty state.

## What You See

- Map preview (standard map art or workshop preview when available)
- Gametype/map/score/time metadata
- Player list with team-aware grouping/sorting rules
- Colored Quake names rendered in UI

## Player Sorting Logic

Team modes (CA/CTF/TDM/etc.):

- Red team first, then Blue, then Spectator, then Free
- Players sorted by score within competitive teams

Non-team modes:

- Active players by score
- Spectators placed after active players

## Map Preview Fallback Chain

1. Standard preview mapping for known map names
2. Workshop preview URL (if workshop item exists)
3. Direct standard map filename guess
4. Default fallback preview image

## Notes

Live status is observational data. Operational actions (restart/stop/logs/RCON) remain in the instance action menu.

## Related Pages

- [Instance Actions Menu](/docs/operations/instance-actions-menu)
- [Server Logs](/docs/operations/server-logs)
- [Chat Logs](/docs/operations/chat-logs)
