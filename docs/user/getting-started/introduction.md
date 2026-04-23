# What Is QLSM?

QLSM (Quake Live Server Management) is a free, open source web UI for deploying and managing Quake Live dedicated servers without using terminal.


## Three Deployment Modes

QLSM supports three ways to run your Quake Live servers:

- **Local (self-host)** — run game servers on the same machine as QLSM itself. Good for a spare Linux box or home server.
- **Standalone** — connect QLSM to any remote host: bare metal, a VPS, or a LAN server. You bring the machine; QLSM handles the rest over SSH.
- **Cloud (Vultr)** — provision VMs directly from the UI using Terraform. No external tooling needed.

## Key Features

- **Live server status** — current map, gametype, match state, players, and scores visible at a glance. ZMQ credentials auto-generated and displayed.
- **In-browser config editors** — CodeMirror-powered editors for `server.cfg`, `mappool.txt`, `access.txt`, and `workshop.txt`. Syntax highlighting, search/replace, and inline validation.
- **minqlx plugin management** — enable plugins with checkboxes. Python validation built in.
- **Factory file management** — select which factory files deploy to each instance.
- **[Presets](../presets/overview.md)** — save a full config/plugin/factory set as a reusable preset. Spin up new instances with consistent baselines.
- **[RCON Console](../operations/rcon-console.md)** — send commands and watch live server events in the browser.
- **Logs** — [server logs](../operations/server-logs.md) and [chat logs](../operations/chat-logs.md) (including rotated archives), searchable.
- **Workshop management** — push updates manually or schedule [automatic restarts](../operations/auto-restart.md) that also pull the latest Steam Workshop content.
- **[QLFilter](../features/qlfilter.md)** — optional eBPF/XDP anti-DDoS filter that drops reflection garbage before it reaches your QLDS ports.
- **[99k LAN rate mode](../features/99k-lan-rate.md)** — NAT-based trick that enables the high-bandwidth LAN rate path for internet servers. Real improvement for LG-heavy or large CA/FFA servers.
- **[User and API management](../administration/user-management.md)** — multi-user support, API keys, external REST API.

## Where To Start

- [Add A Host](add-host.md)
- [Deploy A New Instance](deploy-new-instance.md)
