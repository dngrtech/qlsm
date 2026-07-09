# MinQLX Logs

Use **View MinQLX Logs** from the instance action menu to read `minqlx.log` and rotated archives. This is the MinQLX plugin log — player events, chat/console output, votes, and plugin activity — as opposed to service/runtime output ([Server Logs](server-logs.md)) or the dedicated chat history ([Chat Logs](chat-logs.md)).

## File Selection

The modal loads available files and keeps valid names only:

- `minqlx.log`
- `minqlx.log.<number>` (for example `minqlx.log.1`)

Sorting behavior:

1. `minqlx.log` first
2. then numeric archives in ascending order (`.1`, `.2`, ...)

The UI keeps at most 11 entries (current file + 10 archives).

## Line Filtering

Filter modes:

- **Last N Lines** — presets `100`, `250`, `500`, `1000`, `2500`
- **All** — the entire file

Press **Apply** after changing the file or filter.

## Syntax Highlighting

The viewer colors MinQLX log structure to make lines easy to scan:

- **Timestamps** and **log levels** (`DEBUG`, `INFO`, `WARNING`, `ERROR`) are dimmed so the meaningful content stands out.
- **Module** (`minqlx.dispatch`, `minqlx.handle_console_print`, ...) and **event/command names** (`client_command`, `team_switch`, ...) are highlighted.
- **Quoted arguments** (`'score'`, `'spectator'`), **SteamIDs**, **IP addresses**, and secondary **plugin tags** (`[ranked]`, ...) each get a distinct color.
- **Quake color codes** (`^1`–`^7`) are rendered in their real in-game colors on the text that follows, with the `^N` marker itself dimmed to near-invisible.

## Viewer Behavior

- Read-only CodeMirror display
- Auto-scroll to bottom after load
- `Ctrl+F` to search in-place
- **`Refresh`** and **`Apply`** both re-fetch current file + line count

## Related Pages

- [Server Logs](server-logs.md)
- [Chat Logs](chat-logs.md)
- [Use Logs And Chat Logs](logs-and-chat.md)
- [Instance Actions Menu](instance-actions-menu.md)
