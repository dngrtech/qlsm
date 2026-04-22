# Host Actions Menu

Open from host row **Actions** in the Servers page.

![Host Actions Menu](/docs/images/host-actions-menu.png)

## Actions In This Menu

- **View Details**: opens host details drawer.
- **Restart Host**: queues host reboot flow.
- **[Configure Auto-Restart](/docs/operations/auto-restart)**: opens restart schedule modal.
- **[Update Workshop Item](/docs/operations/update-workshop-item)**: triggers workshop update on this host.
- **[Install/Uninstall QLFilter](/docs/features/qlfilter)**: depends on current QLFilter state.
- **Delete / Remove**: removes host from management (or destroys cloud host).

## What QLFilter Is

QLFilter is a host-level anti-DDoS filter. It uses eBPF/XDP to drop reflection garbage (DNS, SSDP, and similar noise) at the network driver level before it ever reaches QLDS. One installation covers all instances on the host.

For a full explanation: [QLFilter](/docs/features/qlfilter)

Operationally:

- Use **Install QLFilter** on new production hosts.
- Use **Uninstall QLFilter** only when you intentionally want it removed.

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

Full guide: [Update Workshop Item](/docs/operations/update-workshop-item)

This is commonly paired with scheduled restart policy:
[Configure Auto-Restart](/docs/operations/auto-restart)

## Related Pages

- [Instance Actions Menu](/docs/operations/instance-actions-menu)
- [Update Workshop Item](/docs/operations/update-workshop-item)
- [Use Logs And Chat Logs](/docs/operations/logs-and-chat)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
