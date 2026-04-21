# Configure Auto-Restart

Open from **Servers** -> host row **Actions** -> **Configure Auto-Restart**.
Host setup reference: [Add A Host (Cloud Or Standalone)](/docs/getting-started/add-host)

## Why It Is Needed

Running servers do not automatically pull Workshop updates while they stay online.
Scheduled restart provides a controlled window for instances to restart and load updated Workshop content.

## Schedule Modes

- **Disabled**: no scheduled restart.
- **Daily**: every day at selected time.
- **Weekly**: selected weekdays at selected time.
- **Monthly**: selected month days at selected time.

## Timezone Rule

Schedule time is evaluated in the host local timezone.

- Standalone: timezone is the value selected when the host was added.
- Cloud: timezone is tied to selected region.

If timezone is wrong, restart happens at the wrong local time.

## Verification

1. Confirm host timezone in host details.
2. Reopen the auto-restart modal and confirm mode/time.
3. After first schedule window, verify instances came back healthy.

## Related Pages

- [Host Actions Menu](/docs/operations/host-actions-menu)
- [Manage A Running Server](/docs/operations/manage-instance)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
