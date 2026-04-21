# Live Status

Live status shows near-real-time player and match state for each running instance.

## Where to Open

- Player count pill in instance row (for example `3/16`)
- Instance details drawer -> Live Status section

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
