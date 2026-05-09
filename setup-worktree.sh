#!/usr/bin/env bash
set -euo pipefail

log() {
    printf '[setup-worktree] %s\n' "$*"
}

warn() {
    printf '[setup-worktree] WARNING: %s\n' "$*" >&2
}

die() {
    printf '[setup-worktree] ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

log "Setting up QLSM worktree at $script_dir"

require_command git
require_command python3

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "Run this script from inside a QLSM git worktree."
fi

primary_worktree="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
source_worktree="${QLSM_SOURCE_WORKTREE:-$primary_worktree}"

if [[ -n "$source_worktree" && "$source_worktree" != "$script_dir" ]]; then
    if [[ ! -f .env && -f "$source_worktree/.env" ]]; then
        log "Copying .env from $source_worktree"
        cp "$source_worktree/.env" .env
        chmod 600 .env
    elif [[ -f .env ]]; then
        log ".env already exists."
    else
        warn "No .env found in this worktree or $source_worktree."
    fi

    if [[ -d "$source_worktree/configs" ]]; then
        log "Copying missing local configs from $source_worktree"
        mkdir -p configs
        cp -an "$source_worktree/configs/." configs/
    fi
else
    [[ -f .env ]] && log ".env already exists." || warn "No .env found."
fi

if [[ -f .env ]]; then
    set -a
    set +u
    # shellcheck disable=SC1091
    source .env
    set -u
    set +a
fi

export FLASK_ENV="${FLASK_ENV:-development}"
export SECRET_KEY="${SECRET_KEY:-dev-key-for-development-only}"
export FLASK_APP="${FLASK_APP:-ui:create_app()}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

if [[ ! -d .venv ]]; then
    log "Creating Python virtual environment."
    python3 -m venv .venv
else
    log ".venv already exists."
fi

# shellcheck disable=SC1091
source .venv/bin/activate

log "Installing Python dependencies."
python -m pip install --upgrade pip
if [[ -f requirements.txt ]]; then
    python -m pip install -r requirements.txt
else
    warn "requirements.txt not found."
fi

if [[ -d frontend-react ]]; then
    require_command pnpm
    log "Installing frontend dependencies."
    (cd frontend-react && pnpm install)
else
    warn "frontend-react directory not found."
fi

sqlite_db_path="$(
python - <<'PY'
from pathlib import Path
from urllib.parse import unquote
import os

from flask import Flask

os.environ.setdefault("SECRET_KEY", "dev-key-for-development-only")

from ui.config import Config

uri = Config.SQLALCHEMY_DATABASE_URI
if not uri.startswith("sqlite:///"):
    print("")
    raise SystemExit

path_value = uri[len("sqlite:///"):].split("?", 1)[0]
if path_value == ":memory:":
    print("")
    raise SystemExit

path = Path(unquote(path_value))
if not path.is_absolute():
    app = Flask("ui", instance_relative_config=True)
    path = Path(app.instance_path) / path

print(path)
PY
)"

first_run=0
if [[ -n "$sqlite_db_path" ]]; then
    mkdir -p "$(dirname "$sqlite_db_path")"
    if [[ ! -f "$sqlite_db_path" ]]; then
        first_run=1
        log "Initializing new database at $sqlite_db_path"
        python -m flask init-db
        python -m flask db stamp head
    else
        log "Applying database migrations."
        python -m flask db upgrade
    fi
else
    log "Applying database migrations."
    python -m flask db upgrade
fi

log "Syncing built-in presets."
python -m flask sync-builtin-presets

if [[ "$first_run" -eq 1 ]]; then
    default_admin_user="${DEFAULT_ADMIN_USER:-admin}"
    log "Creating default admin user '$default_admin_user' with password 'admin'."
    if ! python -m flask create-default-admin "$default_admin_user"; then
        warn "Could not create default admin user. It may already exist."
    fi
    warn "Default credentials are $default_admin_user/admin; change the password after first login."
fi

log "Worktree setup complete. Run ./run-dev.sh to start development services."
