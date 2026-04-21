# Server Logs

Use **View Server Logs** from the instance action menu to fetch remote service logs.

![Instance Actions: View Server Logs](/docs/images/instance-actions-menu-view-server-logs.png)

## Data Source

- UI endpoint: `GET /api/instances/<id>/remote-logs`
- Backend source: Ansible playbook + journalctl on remote host
- Response includes logs plus filter metadata (`filter_mode`, `lines`, `since`)

## Filters in UI

### Filter modes

- **Last N Lines**
- **Time Range**

### Line presets

`100`, `250`, `500`, `1000`, `2500`

### Time presets

`15 min`, `30 min`, `1 hour`, `3 hours`, `12 hours`, `24 hours`

## Validation and Limits

Backend validates:

- `filter_mode` must be `lines` or `time`
- `lines` must be between `10` and `10000`

## Viewer Behavior

- Logs are displayed in a read-only CodeMirror panel.
- After load, scroll auto-jumps to bottom.
- Use `Ctrl+F` inside editor for search.
- Refresh and Apply trigger a new fetch.

## Failure Modes

Common errors include host/instance not found, SSH/inventory issues, or command timeout while fetching remote logs.
