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

## minqlxtended Hosts

On hosts running the **minqlxtended** runtime, QLSM runs every instance at 99k LAN rate and does not offer 25k. The toggle shows as on and cannot be changed — in the Deploy New Instance form, the instance Actions menu, the instance details panel and the Edit Config modal — and the Rate column reads **99k** for those instances. This is a QLSM product decision for that runtime, so there is nothing to turn on or off.

Hosts running the standard **minqlx** runtime are unaffected: the toggle stays yours to set, per instance, exactly as described below.

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
- Registers `force_rate.so` as a managed **system hook** for the instance and loads it via `LD_PRELOAD`. The library patches `Sys_IsLANAddress` inside qzeroded.x64 so the engine treats every client as a LAN client, which (in combination with `sv_lanForceRate 1`) forces `rate=99999` for all clients.

The hook binary lives on each instance host at `/home/ql/qlds-<port>/system-hooks/force_rate.so`, synced from QLSM's `ql-assets/data/system-hooks/`. You can see it listed as a read-only system hook in the instance's **Hooks** tab — see [LD_PRELOAD Hooks](hooks.md).

## Presets

Saving an instance's config as a [preset](../presets/overview.md) also records whether 99k LAN Rate was enabled at the time. Loading that preset applies the same toggle state — subject to the target host supporting it; if it doesn't, the preset's saved value is ignored and the toggle stays as it was. Presets saved before this feature existed don't have a recorded LAN rate preference, so loading one leaves the current toggle untouched.

A preset saved from a minqlxtended instance records whatever the instance's own setting was, not the fixed-on state QLSM runs it at. That way loading it onto a minqlx host doesn't switch 99k on there without you asking.

## Related Pages

- [Deploy A New Instance](../getting-started/deploy-new-instance.md)
- [Instance Actions Menu](../operations/instance-actions-menu.md)
- [Add A Host (Cloud Or Standalone)](../getting-started/add-host.md)
- [Deployment Troubleshooting](../help/deployment-troubleshooting.md)
- [Presets And Default Config](../presets/overview.md)
