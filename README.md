# QLSM — Quake Live Server Management

Features:
- Three deployment modes (Debian 12 and Ubuntu 22 are tested and recommended):
  * QLSM self-deployment: run QLDS instances on the same machine as QLSM
  * Standalone remote server
  * VULTR cloud provisioning via Terraform
- Optional 99k LAN rate mode. Only Debian 12 supports this feature
- Optional `QLFilter` deployment for supported hosts (anti-DDOS protection)
- Per-instance RCON console with command line and live feed of all server events
- Live server status with current map, gametype, mode/factory, match timer, player list, and scores
- Syntax-aware editors (CodeMirror) for `server.cfg`, `mappool.txt`, `access.txt`, and `workshop.txt`, featuring a Python linter for minqlx plugin's code validation. The editor includes search and replace functionality for easy editing
- Upload common config files, factories, custom minqlx plugins, or `*.so` binary files
- Preset manager to load/save/update/delete qlds presets. Each preset includes custom `server.cfg`, `access.cfg`, `mappool.cfg`, `workshop.txt`, set of minqlx-plugins and `*.factories` files
  - Minqlx plugins can be enabled in the UI by selecting checkboxes. This eliminates the need to manually edit the `qlx_plugins` cvar, as QLSM handles it automatically.
  - UI-driven Factory Management: Enable factories directly via checkboxes
- Chat logs (including rotated archived chat log files) and server logs retrieval with convenient search capability. 
- Daily/weekly/monthly host auto-restart scheduling; scheduled restarts trigger workshop refresh across deployed instances
- Manual workshop item update by Steam Workshop ID, with optional restart of selected instances
- ZMQ RCON Port, ZMQ RCON Password, ZMQ Stats Port, ZMQ Stats Password - all these cvars are auto-generated and shown in the UI
- User management: create users, delete users, and reset passwords
- External API key management for service-to-service access
- External REST API for authenticated instance inventory lookups
- Per-user host/instance ordering and expanded-state preferences stored in browser local storage

Everything runs over SSH via Ansible.


<img width="1428" height="993" alt="servers_page" src="https://github.com/user-attachments/assets/11894a0e-19df-492e-8da7-d69b5ff01d8a" />


<img width="1258" height="1218" alt="edit_config" src="https://github.com/user-attachments/assets/23cbf0dd-b291-46af-941b-74ad802c746b" />


## Stack

Flask + React + SQLite + Redis + Ansible. Background jobs run through RQ workers. The frontend is a Vite/Tailwind SPA served behind Caddy.

## Requirements

Ubuntu 22.04 recommended:

- **Docker** — [install guide](https://docs.docker.com/engine/install/ubuntu/)
- **Docker Compose** (usually included with Docker)
- A user with `sudo` access

Redis, Caddy, the app itself run inside Docker.

To install Docker on a fresh Ubuntu server:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

## Quick start

### Option 1 — one-liner

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh | bash
```

With a custom domain (enables HTTPS via Caddy):

```bash
SITE_ADDRESS=qlds.example.com bash <(curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh)
```

### Option 2 — git clone

```bash
git clone https://github.com/dngrtech/qlsm.git && cd qlsm
cp .env.example .env
# edit .env: set SITE_ADDRESS, REDIS_PASSWORD, and VULTR_API_KEY if using Vultr
docker compose up -d
```

### Option 3 — Vultr (no terminal required)

The easiest option. Register a [Vultr](https://www.vultr.com) account, go to **Orchestration → Startup Scripts**, and add the [vultr-startup-ubuntu22.sh](https://github.com/dngrtech/qlsm/blob/main/vultr-startup-ubuntu22.sh) script. Then deploy a shared CPU VPS (Ubuntu 22.04, $5/month works fine) selecting that startup script in the drop-down menu under the Server Settings — QLSM will be up and running in about 10 minutes with no terminal interaction needed. After deployment, open http://[vultr-provided-ip] in your browser to access the web interface.

Default login is `admin` / `admin`. A password change is enforced on first login.

## Updating

### Default install (`~/qlsm`)

Run a one-time update manually:

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh | bash -s -- --update
```

---

### Vultr / system install (`/opt/qlsm`)

Set up automatic daily updates via cron:

```bash
sudo bash -c '(crontab -l 2>/dev/null | grep -v "qlsm-install.sh"; echo "0 9 * * * curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh | INSTALL_DIR=/opt/qlsm bash -s -- --update >> /var/log/qlsm-update.log 2>&1") | crontab -'
```
Full setup guide: [docs/setup.md](docs/setup.md)

## Development

```bash
cp .env.example .env
./run-dev.sh
```

That starts Flask, Vite, an RQ worker, the RCON service, and a status poller together. Flask ends up on `:5001`, frontend on `:5173`.

Redis needs to be running locally for dev (it's included automatically in the Docker stack for production):

```bash
# Ubuntu/Debian
sudo apt install redis-server && sudo systemctl enable --now redis
```

```bash
pytest tests/
```

## Docs

- [docs/setup.md](docs/setup.md) — install and configure
- [docs/architecture.md](docs/architecture.md) — how it fits together
- [docs/technical.md](docs/technical.md) — implementation details


## Acknowledgements

Huge thanks to **Doomsday** — his deep knowledge of Quake Live dedicated server 
administration has directly shaped a large portion of QLSM's features. Years of 
running servers for the NA [Thunderdome](https://www.thunderdomequake.com) community 
gave him insights that no documentation could replace. He also maintains an excellent 
collection of [minqlx plugins](https://github.com/D00MSDAYDEVICE/minqlx) worth checking out.

Kudos to **mb** for his help configuring and troubleshooting the 99k LAN rate feature.

## License

GPL-3.0
