# Update Workshop Item


Use this when a Steam Workshop item was updated and you want QLSM to pull the latest version on a host without waiting for the next [scheduled restart](/docs/operations/auto-restart).

## Open The Update Modal

1. Go to the **Servers** page.
2. Open the host row **Actions** menu.
3. Click **Update Workshop Item**.

<img src="/docs/images/host-actions-update-workshop-item.png" />

## Fill The Modal

1. Enter the numeric **Workshop Item ID**.
2. Optionally enable **Auto-Restart Instances** for running servers that should restart right after the workshop update finishes.
3. Click **Update Workshop**.

<img src="/docs/images/update-workshop-item.png" width="420" />

## What The Restart Toggles Mean

- Running instances can be selected for automatic restart.
- Stopped instances may still appear in the list, but their restart toggle is disabled.
- If you skip restart, the updated Workshop content may not be picked up until the next manual or scheduled restart.

## When To Use This

- A Workshop map or content pack was updated in Steam.
- A server is still using older Workshop content.
- You want to refresh selected servers now instead of waiting for auto-restart.

## Verification

1. Watch the affected instance statuses.
2. If you enabled auto-restart, wait for selected instances to return healthy.
3. If needed, confirm behavior in-game or with [Server Logs](/docs/operations/server-logs).

## Related Pages

- [Host Actions Menu](/docs/operations/host-actions-menu)
- [Configure Auto-Restart](/docs/operations/auto-restart)
- [Use Logs And Chat Logs](/docs/operations/logs-and-chat)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
