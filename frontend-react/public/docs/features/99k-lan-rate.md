# 99k LAN Rate

99k LAN rate mode enables the high-bandwidth LAN rate path for Quake Live internet servers. In practice it means smoother gameplay, especially for weapon-heavy or large servers.

## Background: The 25k Rate Limit

Quake Live internet servers (sv_serverType 2) are capped at 25k rate per client. This cap was designed for internet connections of an earlier era. On modern connections it creates bandwidth bottlenecks: sound choking under load, inconsistent weapon registration, and the familiar "laggy even though ping is fine" feeling.

LAN servers run at 99k rate because they are assumed to be on local network. The 99k LAN rate feature exploits this: NAT rules make the server believe all player traffic is arriving from `127.0.0.1`, which puts it on the LAN rate path even though players are connecting over the internet.

## When It Makes A Real Difference

The improvement is most noticeable when:

- **Lots of LG combat** — Lightning Gun is the most rate-sensitive weapon. On 8+ player LG-heavy servers the difference in registration is significant.
- **Large Clan Arena matches** — multiple simultaneous fights, high sustained bandwidth demand.
- **Large Free For All** — same reasoning. The more simultaneous exchanges, the more the 25k ceiling shows.

On small servers (2–4 players, low-intensity gametypes) the difference is less pronounced.

## OS Requirement

99k LAN rate requires **Debian 12**. It will not work on Ubuntu.

QLSM enforces this: the toggle is disabled for hosts where the detected OS is not Debian. If you try to enable it on an Ubuntu host, the request is rejected.

See [Add A Host](/docs/getting-started/add-host) for how OS detection works during host setup.

## How To Enable

### At deploy time

1. Open [Deploy New Instance](/docs/getting-started/deploy-new-instance).
  2. In the Basic Info block, check **99k LAN Rate**  <img 
  src="/docs/images/99k-lan-rate-toggle.png" width="120" style="display:inline;
  vertical-align:middle; margin:0 4px" />
3. Deploy as normal.

### On an existing instance

1. Open the instance [Actions menu](/docs/operations/instance-actions-menu).
2. Click **99k LAN Rate**.
3. Wait for the reconfigure/restart cycle to complete.

![](/docs/images/instance-actions-menu-99k-lan-rate.png)   

Changing LAN rate on an existing instance triggers a full reconfigure and restart. The server will be briefly unavailable. If it does not come back, see [Deployment Troubleshooting](/docs/help/deployment-troubleshooting).

## How To Disable

Follow the same steps and toggle the setting off. The server reverts to standard 25k internet mode.

## Technical Details

When enabled, QLSM configures:

- `sv_serverType 1` and `sv_lanForceRate 1` in the server args
- iptables NAT rules (PREROUTING DNAT + POSTROUTING SNAT) per instance port
- `net.ipv4.conf.all.route_localnet=1` kernel parameter (host-wide, harmless when set)

The kernel parameter is host-wide. Once any instance on a host has LAN rate enabled it stays set — disabling it when an instance still needs it would break that instance. QLSM manages this automatically.

## Related Pages

- [Deploy A New Instance](/docs/getting-started/deploy-new-instance)
- [Instance Actions Menu](/docs/operations/instance-actions-menu)
- [Add A Host (Cloud Or Standalone)](/docs/getting-started/add-host)
- [Presets And Default Config](/docs/presets/overview)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
