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

## Self-Host Provider

QLSM can deploy game servers on the same machine that runs the QLSM Docker
stack via the **self-host provider**. This is useful when you already have a
spare Linux box and don't want to bring up a second VM just to run one or two
Quake Live instances.

The web container manages self-host SSH keys through a dedicated directory at
`~/.qlsm-ssh/`. It is deliberately **not** mounted against `~/.ssh` — the
container has no business seeing the operator's personal private keys. Two
one-time host-side steps are required to enable self-host deployment:

### 1. Create the directory

The install script creates this automatically; if you're setting up by hand:

```bash
mkdir -p ~/.qlsm-ssh
chmod 700 ~/.qlsm-ssh
touch ~/.qlsm-ssh/authorized_keys
chmod 600 ~/.qlsm-ssh/authorized_keys
```

### 2. Tell `sshd` to read it

Add the dedicated `authorized_keys` file to `sshd`'s authorized-keys search
path. Edit `/etc/ssh/sshd_config` (as root) and add:

```sshd_config
AuthorizedKeysFile .ssh/authorized_keys .qlsm-ssh/authorized_keys
```

Then reload sshd:

```bash
sudo sshd -t && sudo systemctl reload ssh
```

Verify the new path is active:

```bash
sudo sshd -T | grep authorizedkeysfile
# authorizedkeysfile .ssh/authorized_keys .qlsm-ssh/authorized_keys
```

That's it — the next time you add a **QLSM Host (self)** from the UI, the web
container will drop a generated public key into `~/.qlsm-ssh/authorized_keys`
and connect to `172.17.0.1` (the Docker bridge gateway) as your shell user.

> **Note:** The self-host SSH user defaults to whoever owns the
> `~/.qlsm-ssh/` directory. If you run the stack as root but want self-host
> SSH to land as a different user, set `QLSM_HOST_USER` in `.env`.

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
