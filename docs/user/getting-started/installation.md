# Install QLSM

There are three ways to get QLSM running, from easiest to most hands-on.

## Option 1 — Vultr Startup Script (No Terminal Required)

The easiest path. Requires a Vultr account.

1. Log in to [Vultr](https://vultr.com) and go to **Manage → Startup Scripts**.
2. Create a new startup script and paste in the QLSM install script (link in the project README).
3. Deploy a new VM and select that startup script during setup.
4. Wait approximately 10 minutes after the VM boots.
5. QLSM will be running at the VM's IP address on port 80.

You never open a terminal. The startup script handles everything.

**Recommended spec:** 1 vCPU, 2 GB RAM, Debian 12. If you want to provision additional game server hosts from within the UI, create a Vultr API key and set `VULTR_API_KEY` in the QLSM environment.

## Option 2 — One-Line Install Script

For any Debian 12 machine where you have SSH access:

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh | bash
```

With a custom domain (enables automatic HTTPS via Caddy):

```bash
SITE_ADDRESS=qlsm.example.com bash <(curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh)
```

With Vultr provisioning enabled from the start:

```bash
VULTR_API_KEY=your_vultr_api_key bash <(curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh)
```

With both a custom domain and Vultr provisioning:

```bash
SITE_ADDRESS=qlsm.example.com VULTR_API_KEY=your_vultr_api_key bash <(curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh)
```

The script:
1. Creates `~/qlsm/` with the required directory structure
2. Downloads `docker-compose.yml` and `Caddyfile`
3. Generates a `.env` file with secure random secrets
4. Pulls the Docker image and starts all services

QLSM will be available at the server's IP (or your domain) when it finishes.

## Option 3 — Docker Compose (Full Control)

Clone the repo and configure everything yourself:

```bash
git clone https://github.com/dngrtech/qlsm.git && cd qlsm
cp .env.example .env
# Edit .env — set SITE_ADDRESS, REDIS_PASSWORD, VULTR_API_KEY if using Vultr
docker compose up -d
```

## First Login

Default credentials: `admin` / `admin`

You will be prompted to change your password on first login.

## Next Steps

- [Add A Host (Cloud Or Standalone)](/docs/getting-started/add-host)
- [Deploy A New Instance](/docs/getting-started/deploy-new-instance)
