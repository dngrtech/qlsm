# QLFilter

QLFilter is an optional host-level anti-DDoS filter for Quake Live servers. It drops reflection garbage before it ever reaches the QLDS process.

## The Problem It Solves

Public game servers attract a specific type of noise: DNS queries, SSDP packets, and other reflection traffic sent to your QLDS UDP ports. These don't come from players — they come from bots probing for amplification targets. At high enough volume they can degrade server performance or fill your bandwidth.

## How It Works

QLFilter operates at a very low level in Linux using **eBPF and XDP** — the eXpress Data Path. XDP hooks into the network driver itself, before the packet even enters the Linux networking stack. Packets that match known junk patterns (DNS, SSDP, and similar reflection garbage) are dropped at wire speed, before they consume CPU or reach QLDS.

The result: your Quake Live server only sees legitimate player traffic.

## Installation

QLFilter is installed per host, not per instance. All instances on a host share one QLFilter installation.

1. Go to **Servers**.
2. Open the host's **Actions** menu.
3. Click **Install QLFilter**.
4. Wait for the status indicator to show **Active**.

While QLFilter is installing, other host management actions are temporarily locked.

## Uninstallation

1. Open the host's **Actions** menu.
2. Click **Uninstall QLFilter**.
3. Wait for the status to return to **Not Installed**.

## Status Reference

| Status | Meaning |
|--------|---------|
| Not Installed | QLFilter is not present on this host |
| Installing | Install in progress — host actions locked |
| Active | QLFilter running and filtering |
| Inactive | Installed but not currently running |
| Uninstalling | Removal in progress |
| Error | Install or uninstall failed — check host logs |

## Requirements

- Debian 12 host
- Host must be in **Active** status before installing

## Related Pages

- [Host Actions Menu](/docs/operations/host-actions-menu)
- [Add A Host (Cloud Or Standalone)](/docs/getting-started/add-host)
