# QLSM — Quake Live Server Management

QLSM is a free, open source web UI for deploying and managing Quake Live dedicated servers without using a terminal. Flask backend, React frontend, Ansible for automation, Terraform for provisioning.

## Start here

- **[What Is QLSM?](getting-started/introduction.md)** — deployment modes, feature overview, where to go next.
- **[Add A Host](getting-started/add-host.md)** — connect a cloud VM, a standalone box, or your local machine.
- **[Deploy A New Instance](getting-started/deploy-new-instance.md)** — spin up your first QLDS instance.

## Core topics

- **Operations** — [Host Actions](operations/host-actions-menu.md), [Instance Actions](operations/instance-actions-menu.md), [Live Status](operations/live-status.md), [RCON Console](operations/rcon-console.md).
- **Features** — [QLFilter](features/qlfilter.md) anti-DDoS, [99k LAN Rate](features/99k-lan-rate.md) NAT trick.
- **Administration** — [User Management & API Keys](administration/user-management.md).

## Install

One-line install (self-host):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh)
```

With Vultr provisioning:

```bash
VULTR_API_KEY=your_vultr_api_key bash <(curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh)
```

See [Installation](getting-started/installation.md) for full requirements and options.

## Links

- Repository: <https://github.com/dngrtech/qlsm>
- Issues and feature requests: <https://github.com/dngrtech/qlsm/issues>
