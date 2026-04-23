# Configure Auto-Restart

Open from **Servers** -> host row **Actions** -> **Configure Auto-Restart**.

<img src="../../images/host-actions-auto-restart.png" />



## Why It Is Needed

Scheduled restarts serve two purposes:

**1. Workshop updates.** Running servers do not automatically pull Steam Workshop updates while they stay online. A restart is the only way to load updated Workshop content. QLSM auto-restarts also trigger a full Workshop update pull across all instances on that host — so once a Workshop item owner publishes an update, your servers will pick it up on the next scheduled restart without any manual intervention.

**2. General maintenance.** Long-running game server processes can accumulate state. A scheduled daily or weekly restart gives a clean slate.

## Schedule Modes

- **Disabled**: no scheduled restart.
- **Daily**: every day at selected time.

<img src="../../images/auto-restart-daily.png" width="400" />

- **Weekly**: selected weekdays at selected time.

<img src="../../images/auto-restart-weekly.png" width="400" />

- **Monthly**: selected month days at selected time.

<img src="../../images/auto-restart-monthly.png" width="400" />


## Timezone Rule

Schedule time is evaluated in the host local timezone.

- Standalone and QLSM (self): timezone is the value selected when the host was added.
- Vultr Cloud: timezone is tied to selected `Region`.

If timezone is wrong, restart happens at the wrong local time.

## Verification

1. Confirm host timezone in host details.
2. Reopen the auto-restart modal and confirm mode/time.
3. After first schedule window, verify instances came back healthy.

## Related Pages

- [Host Actions Menu](host-actions-menu.md)
- [Deployment Troubleshooting](../help/deployment-troubleshooting.md)
