# Setup Prerequisites

This document lists the prerequisites required for setting up the development environment and deploying the QLSM application.

## System Prerequisites

*   VPS access (Linux/Ubuntu recommended), with `sudo` privileges and SSH key access configured.
*   Ansible installed on the VPS.
*   Terraform installed on the VPS.
*   Existing Ansible playbooks and templates accessible on the VPS (e.g., within the `ansible/` directory of the project).
*   Ansible Inventory (`ansible/hosts.yml`) populated with target Quake Live server details.
*   SSH connectivity configured from the VPS to the target Quake Live Host Servers (key-based authentication recommended).
*   Git installed on the VPS.
*   (Optional) A domain name for accessing the UI.

## Python Environment Setup

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   Create a `.env` file in the project root with the following variables (adjust as needed):
   ```
   # Flask Configuration
   FLASK_APP=ui:create_app()
   FLASK_ENV=development # Change to 'production' for deployment
   SECRET_KEY='your-secret-key' # Replace with a real secret key

   # Database Configuration
   DATABASE_URL=sqlite:///qlds_ui.db

   # Redis / RQ Configuration
   REDIS_URL=redis://localhost:6379/0
   # If you set a password in redis.conf, uncomment and set the following:
   # REDIS_PASSWORD='your-redis-password'
   RQ_DEFAULT_RESULT_TTL=86400 # Keep job results for 1 day

   # Ansible Runner Configuration (Adjust paths if needed)
   ANSIBLE_RUNNER_PRIVATE_DATA_DIR=./ansible_runner_data # Directory for ansible-runner artifacts
   ```

## Database Initialization

After setting up the Python environment, initialize the database:

```bash
flask init-db
```

This will create the SQLite database file and set up the required tables.

## Running the Development Server

For development purposes, you can run the Flask development server:

```bash
flask run
```

For production deployment, follow the instructions in the README.md for setting up Gunicorn, Systemd, and Nginx.

## Status Poller Service

The live server status feature requires a background daemon that polls game hosts every 15s via SSH, reads instance Redis DBs, and caches results in management Redis.

Create `/etc/systemd/system/qlds-status-poller.service`:

```ini
[Unit]
Description=QLDS UI Status Poller
After=network.target redis.service qlds-ui.service
Requires=redis.service

[Service]
User=www-data
WorkingDirectory=/path/to/qlds-ui
Environment=FLASK_APP=ui
EnvironmentFile=/path/to/qlds-ui/.env
ExecStart=/path/to/qlds-ui/.venv/bin/flask run-status-poller
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable qlds-status-poller
sudo systemctl start qlds-status-poller
sudo journalctl -u qlds-status-poller -f  # Follow logs
```

**Prerequisites:**
- The `discord_status.py` minqlx plugin must be enabled on each game server instance for status data to appear. Without it, the poller succeeds but all statuses will be `null` (displayed as `—` in the UI).
- SSH access from the management server to all game hosts must work with the key at `host.ssh_key_path` (already configured by Terraform/Ansible).
