# What Is QLSM?

QLSM (Quake Live Server Management) is a free, open source web UI for deploying and managing Quake Live dedicated servers without using terminal.

<img width="1312" height="936" alt="qlsm-main" src="https://github.com/user-attachments/assets/f3ebc318-d429-42d3-bbee-aa7fdda3b797" />

## Three Deployment Modes

QLSM supports three ways to run your Quake Live servers:

- **Local (self-host)** — run game servers on the same machine as QLSM itself. Good for a spare Linux box or home server.
- **Standalone** — connect QLSM to any remote host: bare metal, a VPS, or a LAN server. You bring the machine; QLSM handles the rest over SSH.
- **Cloud (Vultr)** — provision VMs directly from the UI using Terraform. No external tooling needed.

## Key Features

- **[Choice of server runtime](add-host.md#server-runtime)** — each host runs either **[minqlx](https://github.com/MinoMino/minqlx.git)** or **[minqlxtended](https://github.com/tjone270/minqlxtended.git)**, picked when the host is created. Neither is pre-selected and the choice is permanent, so QLSM asks rather than guessing. Plugins are not interchangeable between the two; QLSM ships a plugin baseline for each and converts what it can when you load a preset across runtimes.
- **[Live server status](https://dngrtech.github.io/qlsm/operations/live-status/)** — current map, gametype, match state, players, and scores visible at a glance. ZMQ credentials auto-generated and displayed.
- **[99k LAN rate mode](../features/99k-lan-rate.md)** — every client is treated as LAN, enabling the high-bandwidth rate path. Real improvement for LG-heavy or large CA/FFA servers. On minqlx hosts this is a per-instance toggle implemented by patching the QLDS via LD_PRELOAD; on minqlxtended hosts it is always on and native to the runtime.
- **[LD_PRELOAD hooks](../features/hooks.md)** — upload custom native `.so` libraries loaded into each QLDS process at launch. System hooks (like `force_rate.so`, used only on minqlx hosts) are managed automatically.
- **In-browser [config editors](https://dngrtech.github.io/qlsm/operations/edit-configs/)** — CodeMirror-powered editors for `server.cfg`, `mappool.txt`, `access.txt`, and `workshop.txt`. Syntax highlighting, search/replace, and inline validation.
- **minqlx [plugin management](https://dngrtech.github.io/qlsm/operations/edit-configs/)** — enable plugins with checkboxes. Python validation built in.
- **[Factory](https://dngrtech.github.io/qlsm/operations/edit-configs/#factories) file management** — select which factory files deploy to each instance.
- **[Presets](../presets/overview.md)** — save a full config/plugin/factory set as a reusable preset. Export/import presets as ZIP archives to backup/restore configuration or move setups between QLSM installs.
- **[RCON Console](../operations/rcon-console.md)** — send commands and watch live server events in the browser.
- **Global [RCON Console](https://dngrtech.github.io/qlsm/operations/global-rcon/)** — send one command to many instances at once and shows each instance's reply separately.
- **Logs Retrieval** — [server logs](../operations/server-logs.md), [chat logs](../operations/chat-logs.md), and [minqlx logs](../operations/minqlx-logs.md) (including rotated archives), searchable.
- **[Workshop management](https://dngrtech.github.io/qlsm/operations/update-workshop-item/)** — pull Steam Workshop content updates [manually](../operations/update-workshop-item.md) or schedule [automatic restarts](../operations/auto-restart.md) that also pull the latest Steam Workshop content for all deployed instances.
- **Redis DB selection when deploying an instance** — give each QLDS instance its own DB, or share one DB across instances that need to share plugin state.
- **[QLFilter](../features/qlfilter.md)** — optional eBPF/XDP anti-DDoS filter that drops reflection garbage before it reaches your QLDS ports.
- **[User and API management](../administration/user-management.md)** — multi-user support, API keys, external REST API.
- **minqlx damage hook** — QLSM ships minqlx with the `damage` event/dispatcher backported from the [mgaertne/minqlx fork](https://github.com/MinoMino/minqlx/compare/master...mgaertne:minqlx:master), available for plugins to hook.
  
## Where To Start

- [Add A Host](add-host.md)
- [Deploy A New Instance](deploy-new-instance.md)
