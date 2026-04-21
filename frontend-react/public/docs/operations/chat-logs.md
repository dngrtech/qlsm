# Chat Logs

Use **View Chat Logs** from the instance action menu to read `chat.log` and rotated chat archives.

## Data Source

- File list endpoint: `GET /api/instances/<id>/chat-logs/list`
- Content endpoint: `GET /api/instances/<id>/chat-logs?lines=<n>&filename=<file>`
- Backend source: Ansible playbooks reading remote chat log files

## File Selection

The modal loads available files and keeps valid names only:

- `chat.log`
- `chat.log.<number>` (for example `chat.log.1`)

Sorting behavior:

1. `chat.log` first
2. then numeric archives in ascending order (`.1`, `.2`, ...)

The UI keeps at most 11 entries (current file + 10 archives).

## Line Filtering

Line presets: `100`, `250`, `500`, `1000`, `2500`

Backend accepts line values in range `10` to `10000`.

## Viewer Behavior

- Read-only CodeMirror display
- Auto-scroll to bottom after load
- `Ctrl+F` to search in-place
- Refresh and Apply both re-fetch current file + line count

## Troubleshooting

- Empty file list falls back to `chat.log`.
- Parsing issues can return raw Ansible output snippets.
- Timeout errors indicate remote access or command execution delays.
