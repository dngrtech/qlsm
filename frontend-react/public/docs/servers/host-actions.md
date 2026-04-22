# Host Action Menu

Open the host row menu via **Actions** (three-dot button on the right of each host row).

![Host Actions Menu](/docs/images/host-actions-menu.png)

## Action Reference

| Action | What it does | UI availability | Backend constraints |
| --- | --- | --- | --- |
| View Details | Opens the host drawer with metadata, instances, copy IP, and quick actions. | Always enabled. | None. |
| Restart Host | Queues host restart flow. | Enabled when host is actionable and QLFilter is not busy. | API accepts `ACTIVE` hosts only. |
| Configure Auto-Restart | Opens schedule modal (`disabled`, `daily`, `weekly`, `monthly`). | Enabled when host is actionable and QLFilter is not busy. | API accepts `ACTIVE` hosts only. |
| Update Workshop Item | Opens workshop update modal with optional instance restart selection. | Enabled when host is actionable and QLFilter is not busy. | API accepts `ACTIVE` hosts only and requires numeric `workshop_id`. |
| Install QLFilter | Sets QLFilter status to installing and queues install. | Shown for `not_installed`, `error`, `unknown`. | API requires host `ACTIVE`. |
| Uninstall QLFilter | Sets QLFilter status to uninstalling and queues uninstall. | Shown for `active` or `inactive`. | API requires existing host and queues uninstall. |
| Delete / Remove | Queues host deletion/removal task. | Disabled while host is busy (`provisioning`, `deleting`, `rebooting`, `configuring`). | Host deletion is blocked if active instances still exist. |

## Host Actionability Rules in UI

Host menu management actions are enabled when:

- Host status is `active` or `error`.
- Host status is not one of `provisioning`, `deleting`, `rebooting`, `configuring`.
- QLFilter status is not `installing` or `uninstalling`.

## Auto-Restart Schedule Modal

The schedule modal writes a `systemd OnCalendar` expression.

- `Disabled`: clears schedule (`null` payload).
- `Daily`: `*-*-* HH:MM:00`
- `Weekly`: `Mon,Tue,... *-*-* HH:MM:00`
- `Monthly`: `*-*-DD,DD HH:MM:00`

Time is selected in 12-hour format in the modal but submitted as 24-hour `HH:MM:00`.

## Workshop Update Modal

- Requires numeric **Workshop Item ID**.
- Optional restart targets are selected per instance.
- Stopped instances are visible but restart toggle is disabled.
- The request sends `restart_instances` as an array of instance IDs.

Guide: [Update Workshop Item](/docs/operations/update-workshop-item)

## Troubleshooting

- If a restart/update action is visible but fails, check whether host status is truly `ACTIVE` at request time.
- If QLFilter action is spinning, wait until `installing/uninstalling` completes before new host actions.
- If delete is rejected, remove instances first.
