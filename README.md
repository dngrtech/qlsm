# QLSM — Quake Live Server Management

I built this because managing Quake Live dedicated servers without tooling means a lot of SSH sessions, manual config edits, and copy-pasting commands. QLSM wraps that into a web UI — deploy instances, edit configs, restart servers, monitor status, all from a browser.

Bring your own VPS. If you want to provision new hosts on Vultr, there's Terraform for that. Everything else runs over SSH via Ansible.



<img width="1428" height="993" alt="servers_page" src="https://github.com/user-attachments/assets/11894a0e-19df-492e-8da7-d69b5ff01d8a" />


<img width="1258" height="1218" alt="edit_config" src="https://github.com/user-attachments/assets/23cbf0dd-b291-46af-941b-74ad802c746b" />


## Stack

Flask + React + SQLite + Redis + Ansible. Background jobs run through RQ workers. The frontend is a Vite/Tailwind SPA served behind Caddy.

## Requirements

You need a Linux VPS (Ubuntu 22.04 or newer recommended) with:

- **Docker** — [install guide](https://docs.docker.com/engine/install/ubuntu/)
- **Docker Compose** (usually included with Docker)
- A user with `sudo` access

That's it. Everything else (Redis, Caddy, the app itself) runs inside Docker.

To install Docker on a fresh Ubuntu server:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

## Quick start (production)

### Option 1 — one-liner (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh | bash
```

With a domain (enables HTTPS via Caddy):

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

Default login is `admin` / `admin`. You'll be forced to change the password on first login.

## Updating

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh | bash -s -- --update
```

Downloads the latest `docker-compose.yml`, pulls the new image, and restarts. Your `.env` and data are untouched.

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

## License

GPL-3.0
