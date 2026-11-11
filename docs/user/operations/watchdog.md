# Configure Watchdog

Open from **Servers** -> host row **Actions** -> **Configure Watchdog**.

![Host Actions: Configure Watchdog](../images/host-actions-watchdog.png)

The watchdog restarts a server instance whose game has frozen or crashed without exiting. It is set per host: one watchdog covers every instance on that host, including instances added later.

New hosts get the watchdog turned on automatically during setup. Hosts created before v1.56.0 keep whatever they had, which is off unless you enabled it.

## Why It Is Needed

A Quake Live server can occasionally freeze without crashing, or crash without its process exiting. Either way the process stays up, so nothing restarts it, but the game stops running — players time out and the server sits dead until someone restarts it by hand. In QLSM such an instance still shows **Running**, with no live status or player count.

With the watchdog on, QLSM spots the freeze and restarts only the affected instance. Other instances on the host keep running.

## How It Decides An Instance Is Frozen

Every check, the watchdog looks at two things for each running instance:

- **Incoming game traffic is piling up** instead of being read by the server.
- **The server has stopped using CPU** since the previous check.

Both must be true for several checks in a row before it restarts the instance. Traffic alone is not enough — a busy server can briefly fall behind during a slow map load or a burst of traffic, and it keeps using CPU while it does. A frozen server does not.

Newly started instances are left alone for a short grace period while they boot and load the map.

## How It Decides An Instance Has Crashed Without Exiting

A crashed server can get stuck while shutting down. It has already closed its game port, so no traffic piles up, and it still uses a little CPU, so the check above does not see it. A second check covers this case. It restarts an instance only when all of these are true:

- **The server does not answer** a test packet sent to its game port from the host itself.
- **The server has stopped reporting live status** (the map and player data QLSM shows).
- **Both worked earlier** for the same server process.
- **Nothing changed for 3 minutes**, checked every interval.

One sign alone never triggers a restart. A server under heavy traffic may miss the test packet but keeps reporting status; a server whose `serverchecker` plugin is broken or removed stops reporting status but still answers. If the watchdog cannot tell — for example it cannot reach Redis — it does nothing.

This check has two limits:

- An instance without the `serverchecker` plugin is never restarted by it, because the watchdog never sees it report status.
- An instance that crashes before the watchdog has seen it healthy is not caught. This can happen if it crashes right after the watchdog itself was started.

The 3-minute wait is fixed. The check shares the restart limit, dry-run and forensics settings below.

## Turning It On

1. Open **Configure Watchdog** on the host. The host must be **Active**.
2. Switch **Enabled** on.
3. Keep the default settings unless you have a reason to change them.
4. Click **Save**.

<img src="../../images/watchdog-modal-off.png" width="400" />

The host shows **Configuring** while QLSM sets the watchdog up, then returns to **Active**. Once it is on, the menu item shows an **ON** badge.

To turn it off, open the same modal, switch **Enabled** off, and save. QLSM stops the watchdog and removes it from the host.

If the watchdog was already on before you updated QLSM to v1.56.0, open the modal and click **Save** once. That installs the updated watchdog with the crash check on the host.

## Settings

<img src="../../images/watchdog-modal-on.png" width="400" />

| Setting | Default | What it does |
| --- | --- | --- |
| Check Interval (s) | 10 | How often each instance is checked. |
| Recv-Q Threshold (bytes) | 8192 | How much unread game traffic counts as "piling up". A healthy server stays well below this. |
| Strikes Before Restart | 3 | How many checks in a row must look frozen before a restart. With the defaults, a frozen instance is restarted after about 30 seconds. Does not apply to the crash check, which always waits 3 minutes. |
| Boot Grace Period (s) | 90 | How long a newly started instance is ignored. |
| Max Restarts / Window | 3 | The most restarts allowed for one instance within the window below. |
| Rate Limit Window (s) | 900 | The window for the limit above. Once an instance hits the limit, the watchdog stops restarting it and only records the freeze, so a server that keeps freezing can't restart forever. |
| Capture forensics | On | Saves a snapshot of what the frozen server was doing just before restarting it. Useful when reporting the problem. |
| Dry-run | Off | Detects and records freezes but never restarts anything. Use it to see what the watchdog would do on a host before letting it act. |

## Where Restarts Are Recorded

The watchdog keeps its own record on the host, not in QLSM:

- **Events log:** `/var/lib/qlsm/watchdog/events.jsonl` — one line per freeze, restart, or skipped restart. Each restart has a `reason`: `frozen_loop` for a freeze, `engine_dead` for a crash that did not exit.
- **Forensics:** `/var/lib/qlsm/watchdog/forensics/` — one file per captured freeze.
- **Service log:** `sudo journalctl -u ql-watchdog`

The [Host Logs](host-logs.md) only record whether turning the watchdog on or off succeeded.

## Related Pages

- [Host Actions Menu](host-actions-menu.md)
- [Configure Auto-Restart](auto-restart.md)
- [Host Logs](host-logs.md)
