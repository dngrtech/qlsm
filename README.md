# QLSM — Quake Live Server Management

I built this because managing Quake Live dedicated servers without tooling means a lot of SSH sessions, manual config edits, and copy-pasting commands. QLSM wraps that into a web UI — deploy instances, edit configs, restart servers, monitor status, all from a browser.

Bring your own VPS. If you want to provision new hosts on Vultr, there's Terraform for that. Everything else runs over SSH via Ansible.

## Stack

Flask + React + SQLite + Redis + Ansible. Background jobs run through RQ workers. The frontend is a Vite/Tailwind SPA served behind Caddy.

## Quick start (production)

```bash
git clone https://github.com/dngrtech/qlsm.git && cd qlsm
cp .env.example .env
# edit .env: set SITE_ADDRESS, REDIS_PASSWORD, and VULTR_API_KEY if using Vultr
docker compose up -d
```

Default login is `admin` / `admin`. You'll be forced to change the password on first login.

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
