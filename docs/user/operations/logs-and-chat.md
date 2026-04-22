# Use Logs And Chat Logs

Logs are the fastest way to find out why a deployment or restart failed.

## Open Logs

From instance **Actions** menu:

- **View Server Logs** for service/runtime output
- **View Chat Logs** for player chat history

Action reference: [Instance Actions Menu](/docs/operations/instance-actions-menu)

## Server Logs: Practical Usage

- Start with **Last 500 lines**.
- If needed, switch to a time range (for example last 1 hour).
- Press **Apply**.
- Use `Ctrl+F` inside the log viewer.

## Chat Logs: Practical Usage

- Keep `chat.log` selected for current activity.
- Select rotated files (`chat.log.1`, etc.) for older history.
- Start with 500 lines and adjust.

## What To Do When You See Errors

1. Copy the exact error line.
2. Retry once (restart or re-save config).
3. If same error repeats, escalate with the copied line and instance name.

## Related Pages

- [Server Logs](/docs/operations/server-logs.md)
- [Chat Logs](/docs/operations/chat-logs.md)
- [RCON Console](/docs/operations/rcon-console)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
