# System Architecture

This document describes the architecture of the QLSM application.

## Overview

QLSM is designed as a simple monolithic web application running on a Linux VPS. Its primary goal is to provide a user interface for managing existing Quake Live dedicated server instances (deployed directly on hosts) on remote servers by triggering Ansible playbooks asynchronously. Key components include a Flask backend, an RQ task queue with Redis, and integration with Ansible (via direct CLI calls).

## Architecture Diagram

```mermaid
graph TD
    %% External User
    User[👤 User] -->|🌐 HTTP or HTTPS| Nginx[Nginx]

    %% Client-Side
    subgraph "Client-Side (Browser)"
        ReactApp[⚛️ React Frontend App]
    end
    Nginx -- "Serves Static Assets (JS, CSS, HTML)" --> ReactApp
    ReactApp -- "API Calls (Auth, Data, Actions)" --> Nginx


    %% qlds-ui Runtime Server (Backend API & Task Processing)
    subgraph "QLSM Backend Server"
        Nginx -->|🔁 Reverse Proxy API Requests| Gunicorn[Gunicorn]
        Gunicorn -->|WSGI| FlaskApp[🧩 Flask API Backend]

        FlaskApp -->|🔄 Reads/Writes Host & Instance Data| SQLite["🗄️ SQLite DB <br> - Host (name, ip, provider, region, size, status, qlfilter_status, ssh_key_path, logs) <br> - QLInstance (name, port, hostname, status, host_id, logs) <br> - ConfigPreset (...)"]
        FlaskApp -->|💾 Reads/Writes Instance Config Files| FileSystem["📁 Filesystem <br> (configs/<host>/<instance_id>/*)"]
        FlaskApp -->|📤 Enqueues Ansible or Terraform Tasks| Redis["🧠 Redis"]
        FlaskApp -->|⚙️ Reads/Writes| DotEnv["⚙️ Dotenv Config"]

        RQWorker[RQ Worker] -->|📥 Dequeues Tasks| Redis
        RQWorker -->|🚀 Executes Terraform & Ansible| AutomationRunner["🛠️ Automation Runner <br> (Terraform & Ansible CLI)"]
        AutomationRunner -->|📝 Updates Host/Instance Status & Logs| SQLite
        AutomationRunner -->|📂 Reads| DotEnv
    end

    %% Target Hosts (Provisioned by Terraform, Managed by Ansible)
    subgraph "Target Host Servers (Managed)"
        AutomationRunner -- "1. Terraform Apply (Provision Host)" --> NewHost["💻 New Host VM <br> (Region, Size)"]
        NewHost -- "Get IP and SSH Key" --> AutomationRunner
        AutomationRunner -- "2. Ansible: setup_host.yml (Initial Setup)" -->|🔐 SSH| NewHost

        AutomationRunner -- "Ansible: add_qlds_instance.yml (Add Instance)" -->|🔐 SSH| ManagedHost1["💻 Managed Host 1<br>(/home/ql/qlds-*)"]
        AutomationRunner -- "Ansible: add_qlds_instance.yml (Add Instance)" -->|🔐 SSH| ManagedHostN["💻 Managed Host N<br>(/home/ql/qlds-*)"]
        AutomationRunner -- "Ansible: setup_qlfilter.yml (Install QLFilter)" -->|🔐 SSH| ManagedHost1
        AutomationRunner -- "Ansible: remove_qlfilter.yml (Uninstall QLFilter)" -->|🔐 SSH| ManagedHost1
    end

```

## Component Descriptions

*   **User:** Interacts with the application via a web browser over HTTP/S.
*   **Nginx:** Acts as a reverse proxy for the backend API (Gunicorn/Flask) and serves the static assets (HTML, CSS, JavaScript) for the React frontend application. It can also handle SSL termination.
*   **React Frontend App:** A single-page application (SPA) built with React, running in the user's browser. It handles all user interface rendering, client-side routing, state management, and client-side table sorting. It communicates with the Flask backend via API calls to fetch data, trigger actions, and authenticate. It utilizes libraries like Tailwind CSS for styling, Headless UI for accessible UI components (like those used in `HostActionsMenu.jsx` and `InstanceActionsMenu.jsx`), and `@floating-ui/react-dom` for robust positioning of elements like dropdown menus.
*   **Gunicorn:** A WSGI HTTP server that runs the Flask API backend. It manages multiple worker processes to handle concurrent API requests.
*   **Flask API Backend (ui):** The core backend application built with Flask. It now primarily serves as an API provider for the React frontend. It handles API requests, interacts with the database, manages authentication (using `Flask-JWT-Extended` with `HttpOnly` cookies), and enqueues background tasks.
    * **App Factory (`ui/__init__.py`):** Creates and configures the Flask application, including CORS setup for the React frontend and initialization of `Flask-JWT-Extended`.
    * **Configuration (`ui/config.py`):** Manages application settings, including those for `Flask-JWT-Extended` (cookie name, security attributes, token location).
    * **Database Models (`ui/models.py`):** Defines the `User`, `Host`, `QLInstance`, `ConfigPreset`, `ApiKey`, and `AppSetting` data structures using SQLAlchemy ORM.
    * **Database Helpers (`ui/database.py`):** Provides CRUD operations for models and database initialization.
    * **CLI Modules (`ui/user_cli.py`, `ui/preset_cli.py`):** Register focused Flask CLI commands for user bootstrap and preset management.
    * **API Routes (`ui/routes/` package):** Defines API endpoints, organized into blueprints. These endpoints return JSON responses. Key route modules: `auth_api_routes.py`, `host_routes.py`, `instance_routes.py`, `preset_api_routes.py`, `server_status_routes.py`, `settings_routes.py`, `user_routes.py`, `draft_routes.py`, `script_routes.py`, `factory_routes.py`, and `external_api_routes.py` (versioned external API at `/api/v1/`).
*   **SQLite DB:** A simple file-based database storing application metadata:
    * **Host Model:** Stores information about target servers: name, provisioned IP address, provider, region/size, status (Enum), `qlfilter_status` (Enum), SSH key path, `ssh_port`, `os_type`, `is_standalone`, `timezone`, `auto_restart_schedule`, and logs.
    * **QLInstance Model:** Stores information about Quake Live server instances: name, port, hostname, `lan_rate_enabled`, `qlx_plugins`, ZMQ connection fields (`zmq_rcon_port`, `zmq_rcon_password`, `zmq_stats_port`, `zmq_stats_password`), status (Enum), logs, and a foreign key (`host_id`) linking it to its parent `Host`. Config files are stored on the filesystem.
    * **ConfigPreset Model:** Stores reusable configuration preset metadata. Config file contents are stored on the filesystem; the model holds a `path` pointer.
    * **ApiKey Model:** Stores API keys for external service authentication (Bearer token auth for `/api/v1/` endpoints).
    * **AppSetting Model:** Generic key-value store for application settings (e.g., rate limit configuration).
*   **FileSystem (Instance Configs):** Instance-specific configuration files (e.g., `server.cfg`, `mappool.txt`) are stored directly on the application server's filesystem under `configs/<host_name>/<instance_id>/`.
*   **Redis:** An in-memory data store used as the message broker for the RQ task queue.
*   **RQ Worker:** A separate process that listens to the Redis queue for tasks defined in `ui/tasks.py`. It dequeues tasks for host provisioning/setup and instance management.
*   **Automation Runner:** Represents the logic within the RQ worker responsible for executing the automation tools, now refactored into the `ui/task_logic/` package:
    * **Terraform Execution:**
        * `ui/task_logic/terraform_runner.py`: Contains the helper function (`_run_terraform_command`) for executing Terraform CLI commands via `subprocess`.
        * `ui/task_logic/terraform_provision.py`: Contains the `provision_host_logic` function, orchestrating Terraform `apply`, output handling, and enqueuing the Ansible setup task.
        * `ui/task_logic/terraform_destroy.py`: Contains the `destroy_host_logic` function, orchestrating Terraform `destroy` and associated cleanup.
    * **Ansible Execution:**
        * `ui/task_logic/ansible_runner.py`: Helper functions for executing Ansible playbooks via `subprocess`.
        * `ui/task_logic/ansible_host_setup.py`: Initial host setup (`setup_host.yml`).
        * `ui/task_logic/ansible_host_rename.py`: Host rename (inventory + config folder).
        * `ui/task_logic/ansible_host_restart.py`: Host reboot.
        * `ui/task_logic/ansible_host_auto_restart.py`: Configure host auto-restart scheduling.
        * `ui/task_logic/ansible_instance_mgmt.py`: Instance deploy/restart/delete/config-sync logic.
        * `ui/task_logic/ansible_qlfilter_mgmt.py`: QLFilter install/uninstall/check.
        * `ui/task_logic/ansible_workshop_update.py`: Force workshop item update on host.
        * `ui/task_logic/standalone_host_setup.py` / `standalone_host_remove.py`: Lifecycle for user-provided (non-Terraform) hosts.
    * **Supporting Modules:**
        * `ui/task_logic/zmq_utils.py`: ZMQ connection utilities for RCON service.
        * `ui/task_logic/job_failure_handlers.py`: RQ failure callbacks.
        * `ui/task_logic/task_lock.py`: Distributed lock mechanism preventing concurrent task execution on the same resource.
*   **RCON Service (`rcon_service/`):** A set of modules providing remote console and live stats access over ZMQ. Used by the frontend's RCON console modal and live status polling.
*   **WebSocket (Flask-SocketIO):** Provides real-time push capability from server to browser for live status updates.
*   **Target Host Servers:** The remote Linux servers provisioned by Terraform and subsequently set up and managed by Ansible. QLDS instances run directly on these hosts (e.g., under `/home/ql/qlds-{id}`), utilizing shared base installations in `/home/ql/qlds-base`, `/home/ql/minqlx-shared`, etc. QLFilter can also be managed on these hosts.
*   **.env / DotEnv Config:** Stores configuration settings like database paths, Redis connection details, cloud provider credentials (needs secure handling), and paths for Terraform/Ansible artifacts.

## Key Architectural Decisions

*   **Frontend/Backend Separation:** The application has transitioned to a decoupled architecture with a React single-page application (SPA) frontend and a Flask API backend. This allows for independent development and scaling of the frontend and backend.
*   **API-Driven Communication:** The React frontend communicates with the Flask backend exclusively through a JSON-based RESTful API.
*   **Application Factory Pattern (Backend):** The Flask backend uses the factory pattern for modularity, testability, and environment-specific configuration.
*   **SQLAlchemy ORM (Backend):** Database operations in the backend are abstracted using SQLAlchemy ORM.
*   **CLI Commands (Backend):** Database initialization and other administrative tasks for the backend are exposed as Flask CLI commands.
*   **Asynchronous Task Execution (Backend):** Long-running operations are handled asynchronously by the backend using RQ and Redis.
*   **Automation Tool Integration:** Uses direct `subprocess` calls for executing Ansible and Terraform playbooks/commands.
*   **Split Ansible Playbooks:** Playbooks are split by responsibility: `setup_host.yml` (one-time host setup after Terraform), `add_qlds_instance.yml` (per-instance deploy), and dedicated playbooks for rename, restart, LAN rate, workshop update, auto-restart, log fetching, and QLFilter management.
*   **Data Model Relationship:** Establishes a clear one-to-many relationship between Hosts and QLInstances in the database.
*   **Standard Deployment Stack:** Uses common tools like Gunicorn, Systemd, and Nginx.
*   **Comprehensive Testing:** Requires expansion of the test suite to cover Host CRUD, Terraform task queueing/execution (mocked), Ansible host setup task integration, and updated Instance tests reflecting the Host relationship and new Ansible playbooks.

## Directory Structure

```
qlds-ui/
├── ui/                          # Flask backend
│   ├── __init__.py              # App factory
│   ├── models.py                # SQLAlchemy models (Host, QLInstance, ConfigPreset)
│   ├── database.py              # DB helpers and CRUD operations
│   ├── tasks.py                 # RQ task definitions (entry points)
│   ├── task_context.py          # @with_app_context decorator
│   ├── routes/                  # API endpoints
│   │   ├── host_routes.py       # Host CRUD + actions (restart, qlfilter)
│   │   ├── instance_routes.py   # Instance CRUD + config management
│   │   ├── auth_api_routes.py   # JWT authentication
│   │   └── preset_api_routes.py # Config presets
│   └── task_logic/              # Background task implementations
│       ├── ansible_runner.py        # Ansible execution helper
│       ├── ansible_host_setup.py    # Initial host setup
│       ├── ansible_host_rename.py   # Host rename (inventory + config folder)
│       ├── ansible_host_restart.py  # Host reboot
│       ├── ansible_host_auto_restart.py # Auto-restart scheduling
│       ├── ansible_instance_mgmt.py # Instance deploy/restart/delete/config-sync
│       ├── ansible_qlfilter_mgmt.py # QLFilter install/uninstall
│       ├── ansible_workshop_update.py # Force workshop update
│       ├── standalone_host_setup.py # Setup user-provided hosts
│       ├── standalone_host_remove.py # Remove user-provided hosts
│       ├── terraform_provision.py   # VM provisioning
│       ├── terraform_destroy.py     # VM destruction
│       ├── task_lock.py             # Distributed lock for concurrent task prevention
│       ├── job_failure_handlers.py  # RQ failure callbacks
│       ├── zmq_utils.py             # ZMQ utilities for RCON
│       └── common.py            # Shared utilities (append_log, etc.)
│
├── frontend-react/src/          # React SPA
│   ├── pages/                   # Page components (ServersPage, SettingsPage, etc.)
│   ├── components/              # Reusable components
│   │   ├── hosts/               # Host-specific (HostDetailDrawer, AddHostModal)
│   │   └── instances/           # Instance-specific (RconConsoleModal, LiveServerStatusModal)
│   ├── services/api.js          # Axios API client
│   ├── contexts/                # React contexts (AuthContext, ThemeContext, LoadingContext)
│   ├── hooks/                   # Custom React hooks
│   ├── constants/               # Shared constants
│   └── utils/                   # Utilities (resourceValidation.js, statusEnums.js)
│
├── ansible/                     # Ansible automation
│   ├── playbooks/               # Playbooks (setup_host.yml, add_qlds_instance.yml, etc.)
│   ├── inventory/               # Host inventories (<hostname>_vultr_host.yml)
│   └── templates/               # Jinja2 templates (systemd service, etc.)
│
├── terraform/                   # Infrastructure-as-code
│   ├── modules/                 # Reusable modules (vultr_instance, gcp_instance)
│   └── <instance-name>/         # Per-host Terraform state and config
│
├── configs/                     # Instance configurations (on management server)
│   └── <host_name>/             # Per-host folder
│       └── <instance_id>/       # Per-instance configs
│           ├── server.cfg       # Main QLDS config
│           ├── mappool.txt      # Map rotation
│           ├── access.txt       # Access control
│           └── workshop.txt     # Workshop items
│
└── docs/                        # Documentation
```

## Data Flow

### Host Provisioning
1. User submits form → `POST /api/hosts`
2. Host record created (status: PENDING → PROVISIONING)
3. RQ task queued → `provision_host_logic()`
4. Terraform apply → VM created, IP returned
5. Ansible `setup_host.yml` → Initial configuration (QLDS base, minqlx, etc.)
6. Host status → ACTIVE

### Instance Deployment
1. User submits form → `POST /api/instances`
2. Instance record created, config files written to `configs/<host>/<id>/`
3. RQ task queued → `deploy_instance_logic()`
4. Ansible `add_qlds_instance.yml` → Deploys to host
5. Instance status → RUNNING

### Instance Config Update
1. User edits config → `PUT /api/instances/<id>/config`
2. Config files updated in `configs/<host>/<id>/`
3. RQ task queued → `apply_instance_config_logic()`
4. Ansible `sync_instance_configs_and_restart.yml` → Syncs configs and restarts
5. Instance status → RUNNING

### Host Rename
1. User edits name → `PUT /api/hosts/<id>`
2. Database updated immediately
3. RQ task queued → `rename_host_logic()`
4. Inventory file renamed (`ansible/inventory/<old>_vultr_host.yml` → `<new>_vultr_host.yml`)
5. Config folder renamed (`configs/<old>` → `configs/<new>`)
6. Ansible `rename_host.yml` → Updates remote hostname
7. Host status → ACTIVE

### Live Status and Workshop Preview
1. `serverchecker` plugin on each game instance writes live status to instance Redis key `minqlx:server_status:<port>`.
2. Poller (`ui/task_logic/server_status_poll.py`) SSHes hosts, reads per-instance status, and writes to management Redis keys `server:status:<host_id>:<instance_id>`.
3. Frontend polls `GET /api/server-status` for live map/player/state data.
4. Status payload now includes `workshop_item_id` when the current map can be resolved to a workshop item.
5. Frontend may call `GET /api/server-status/workshop-preview/<workshop_id>` to resolve/cached Steam `preview_url`.
