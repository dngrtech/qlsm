# Deployment Troubleshooting

Use this page when a new instance does not become playable or stable.

## Problem: No host available in add-instance form

- Add a host first: [Add A Host (Cloud Or Standalone)](../getting-started/add-host.md)
- Wait until host status is **Active**.

## Problem: No ports available

- Another instance is using all listed ports on that host.
- Stop/delete old instances or choose another host.

## Problem: Instance stuck in deploying/restarting/configuring

1. Wait a bit and refresh.
2. Open **View Server Logs**: [Use Logs And Chat Logs](../operations/logs-and-chat.md)
3. Check for clear error lines.
4. Retry once only after reading logs.

## Problem: RCON button is disabled

- Instance is not fully ready yet.
- Check action availability rules: [Instance Actions Menu](../operations/instance-actions-menu.md)
- Wait for healthy status, then try again.

## Problem: You changed config but game behavior did not change

- Confirm you saved changes.
- Restart instance.
- Re-check with logs/live status: [Use Logs And Chat Logs](../operations/logs-and-chat.md)

## Problem: Workshop item updated in Steam, but server still runs old content

- Use host **Actions** -> **Update Workshop Item** and provide numeric item ID: [Update Workshop Item](../operations/update-workshop-item.md)
- Restart affected instances (manual or from the workshop update modal).
- Configure scheduled host restart to keep updates consistent: [Configure Auto-Restart](../operations/auto-restart.md)

## Problem: Auto-restart runs at the wrong local time

- Auto-restart follows host local timezone.
- For standalone hosts, this is the timezone set when host was added.
- Verify timezone in host details before trusting schedule time.

See: [Configure Auto-Restart](../operations/auto-restart.md)

## Related Pages

- [Host Actions Menu](../operations/host-actions-menu.md)
- [Instance Actions Menu](../operations/instance-actions-menu.md)
- [Deploy A New Instance](../getting-started/deploy-new-instance.md)

## Escalation Bundle (What to collect)

When asking for help, include:

- Host name
- Instance name
- Current status
- Exact error line from logs
- What action you performed right before the issue
