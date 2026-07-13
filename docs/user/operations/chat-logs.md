# Chat Logs

Use **View Chat Logs** from the instance action menu to read `chat.log` and rotated chat archives.

![Instance Actions: View Chat Logs](../images/instance-actions-menu-view-chat-logs.png)


## File Selection

The modal loads available files and keeps valid names only:

- `chat.log`
- `chat.log.<number>` (for example `chat.log.1`)

Sorting behavior:

1. `chat.log` first
2. then numeric archives in ascending order (`.1`, `.2`, ...)

The UI keeps at most 11 entries (current file + 10 archives).

## Filtering

Choose a filter mode:

- **Last N Lines** — presets `100`, `250`, `500`, `1000`, `2500`
- **Time Range** — presets `15 min`, `30 min`, `1 hour`, `3 hours`, `12 hours`, `24 hours`
- **All** — the entire selected file

After changing the filter mode or its value, select **Apply** to fetch the selected file with that filter.


![](../images/chat-logs.png)


## Viewer Behavior

- Read-only CodeMirror display
- Auto-scroll to bottom after load
- `Ctrl+F` to search in-place
- Selecting a different archive file reloads it immediately using the active filter
- **Refresh** re-fetches the selected file without changing the active filter
- **Apply** re-fetches the selected file using the currently selected filter controls
