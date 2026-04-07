# Setup Guide

## Requirements

- A Linux VPS (Ubuntu 22.04+ recommended) with `sudo` access
- **Docker** and **Docker Compose** — [install guide](https://docs.docker.com/engine/install/ubuntu/)
- (Optional) A domain name for HTTPS

Install Docker on a fresh Ubuntu server:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

## Installation

### Option 1 — one-liner (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh | bash
```

With a domain (enables automatic HTTPS via Caddy):

```bash
SITE_ADDRESS=qlds.example.com bash <(curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh)
```

The script will:
1. Create `~/qlsm/` with the required directory structure
2. Download `docker-compose.yml` and `Caddyfile`
3. Generate a `.env` file with secure random secrets
4. Pull the Docker image and start all services
5. Wait for the health check to pass

### Option 2 — git clone

```bash
git clone https://github.com/dngrtech/qlsm.git && cd qlsm
cp .env.example .env
# Edit .env — set SITE_ADDRESS, REDIS_PASSWORD, and VULTR_API_KEY if using Vultr
docker compose up -d
```

## First Login

Default credentials: `admin` / `admin`

You will be prompted to change your password on first login.

## Configuration (.env)

| Variable | Description | Default |
|----------|-------------|---------|
| `SITE_ADDRESS` | Domain or `:port` — controls HTTPS | `:80` |
| `REDIS_PASSWORD` | Redis auth password | auto-generated |
| `DEFAULT_ADMIN_USER` | Bootstrap admin username | `admin` |
| `VULTR_API_KEY` | Vultr API key for VM provisioning | (blank) |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `JWT_EXPIRATION_HOURS` | Session length in hours | `24` |

After editing `.env`, restart the stack:

```bash
cd ~/qlsm && docker compose up -d
```

## Updating

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh | bash -s -- --update
```

Downloads the latest `docker-compose.yml`, pulls the new image, and restarts. Your `.env` and data are untouched.

## Services

The Docker Compose stack runs the following containers:

| Container | Purpose |
|-----------|---------|
| `web` | Flask API + RQ worker + status poller |
| `redis` | Task queue and live status cache |
| `caddy` | Reverse proxy + automatic HTTPS |
| `loki` | Log aggregation |
| `promtail` | Log collection |
| `grafana` | Log viewer (optional) |

## Useful Commands

```bash
cd ~/qlsm

docker compose logs -f web      # Follow app logs
docker compose logs -f          # Follow all logs
docker compose down             # Stop everything
docker compose up -d            # Start everything
docker compose restart web      # Restart app only
docker compose ps               # Show running containers
```

## Live Server Status

The `discord_status.py` minqlx plugin must be enabled on each game server instance for live status data (map, players, state) to appear in the UI. Without it, statuses will show as `—`.

## Development

```bash
cp .env.example .env
./run-dev.sh
```

Starts Flask (`:5001`), Vite (`:5173`), RQ worker, RCON service, and status poller together. Requires Redis running locally:

```bash
sudo apt install redis-server && sudo systemctl enable --now redis
```
