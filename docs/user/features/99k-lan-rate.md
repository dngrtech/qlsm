# 99k LAN Rate

99k LAN rate mode enables the high-bandwidth LAN rate path for Quake Live internet servers. In practice it means smoother gameplay, especially for weapon-heavy or large servers.

## Background: The 25k Rate Limit

Quake Live internet servers are capped at 25k rate per client. This cap was designed for the internet connections of an earlier era. On modern connections it creates bandwidth bottlenecks: sound choking under load, inconsistent weapon registration, and the familiar "laggy even though ping is fine" feeling.

LAN servers run at 99k rate because they are assumed to be on local network. The 99k LAN rate feature loads a tiny LD_PRELOAD library (`force_rate.so`) into the qlds process. The library patches the server's LAN-detection function to always return true, so the engine treats every connecting client as a LAN client and forces `rate=99999` for all of them.

## When It Makes A Real Difference

The improvement is most noticeable when:

- **Lots of LG combat** — Lightning Gun is the most rate-sensitive weapon. On 8+ player LG-heavy servers the difference in registration is significant.
- **Large Clan Arena matches** — multiple simultaneous fights, high sustained bandwidth demand.
- **Large Free For All** — same reasoning. The more simultaneous exchanges, the more the 25k ceiling shows.

On small servers (2–4 players, low-intensity gametypes) there is effectively no practical difference.

## OS Support

99k LAN rate works on any supported host OS — the LD_PRELOAD library is OS-independent.

## How To Enable

### At deploy time

1. Open [Deploy New Instance](../getting-started/deploy-new-instance.md).
2. In the Basic Info block, check **99k LAN Rate**
3. Deploy as normal.

### On an existing instance

1. Open the instance [Actions menu](../operations/instance-actions-menu.md).
2. Click **99k LAN Rate**.
3. Wait for the reconfigure/restart cycle to complete.

Changing 99k LAN Rate on an existing instance triggers a hooks reconfigure and service restart. The server will be briefly unavailable. If it does not come back, see [Deployment Troubleshooting](../help/deployment-troubleshooting.md).

## How To Disable

Follow the same steps and toggle the setting off. The server reverts to standard 25k internet mode.

## Technical Details

When enabled, QLSM:

- Adds `+set sv_lanForceRate 1` to the qlds startup arguments
- Loads `force_rate.so` via `LD_PRELOAD`. The library patches `Sys_IsLANAddress` inside qzeroded.x64 so the engine treats every client as a LAN client, which (in combination with `sv_lanForceRate 1`) forces `rate=99999` for all clients.

The hook binary lives on each instance host at `/home/ql/qlds-<port>/system-hooks/force_rate.so`, synced from QLSM's `ql-assets/data/system-hooks/`.

## Migration From Older QLSM Hosts

If your host was set up before this implementation shipped, the toggle may still be restricted to Debian and may use the older iptables-based mechanism. To migrate the host in place:

1. Open the host's Actions menu.
2. Click **Re-run Host Setup**.
3. After the run completes, the toggle works on any OS, and any instance that already had 99k LAN Rate enabled is restarted with the new hook automatically.

## Related Pages

- [Deploy A New Instance](../getting-started/deploy-new-instance.md)
- [Instance Actions Menu](../operations/instance-actions-menu.md)
- [Add A Host (Cloud Or Standalone)](../getting-started/add-host.md)
- [Deployment Troubleshooting](../help/deployment-troubleshooting.md)
