# Host Actions Menu

Open from host row **Actions** in the Servers page.

![Host Actions Menu](/docs/images/host-actions-menu.png)

## Actions In This Menu

- **View Details**: opens host details drawer.
- **Restart Host**: queues host reboot flow.
- **Configure Auto-Restart**: opens restart schedule modal.
- **Update Workshop Item**: triggers workshop update on this host.
- **Install/Uninstall QLFilter**: depends on current QLFilter state.
- **Delete / Remove**: removes host from management (or destroys cloud host).

## What QLFilter Is

QLFilter is a host-level Quake Live filtering/moderation component.

- It is installed once per host, not per instance.
- All instances on that host use the same QLFilter installation.
- The menu action controls lifecycle only: install or uninstall.

Operationally:

- Use **Install QLFilter** on new hosts before regular production use.
- Use **Uninstall QLFilter** only when you intentionally want it removed from that host.

## QLFilter Behavior In Menu

The QLFilter action changes based on current QLFilter status:

- `not_installed`, `error`, `unknown` -> **Install QLFilter**
- `active`, `inactive` -> **Uninstall QLFilter**
- `installing`, `uninstalling` -> action shows busy state and is locked

While QLFilter is installing/uninstalling, other host management actions are also blocked.

## Update Workshop Item: Practical Use

1. Open **Update Workshop Item** from host actions.
2. Enter numeric Workshop Item ID.
3. Optionally pick running instances for automatic restart after update.
4. Submit and monitor instance status.

This is commonly paired with scheduled restart policy:
[Configure Auto-Restart](/docs/operations/auto-restart)

## Related Pages

- [Instance Actions Menu](/docs/operations/instance-actions-menu)
- [Manage A Running Server](/docs/operations/manage-instance)
- [Use Logs And Chat Logs](/docs/operations/logs-and-chat)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
