#!/bin/sh
# QLDS UI Docker entrypoint
# Handles: auto-generated secrets, DB initialization, Alembic migrations
set -e

# ── Auto-generate SECRET_KEY ───────────────────────────────────────────────────
# SECRET_KEY is Flask-internal (signs JWTs/cookies). Generated once, persisted
# to the qlds-data volume so it survives container restarts and image updates.
# Override by setting SECRET_KEY in .env.
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY_FILE=/app/data/.secret_key
    if [ ! -f "$SECRET_KEY_FILE" ]; then
        if [ "${RUN_MIGRATIONS}" = "true" ]; then
            # Web service: generate the secret key
            python3 -c "import secrets; print(secrets.token_hex(32))" > "$SECRET_KEY_FILE"
            chmod 600 "$SECRET_KEY_FILE"
        else
            # Worker/poller/rcon: wait for web to generate it (up to 30s)
            echo "[entrypoint] Waiting for SECRET_KEY file..."
            for i in $(seq 1 30); do
                [ -f "$SECRET_KEY_FILE" ] && break
                sleep 1
            done
            if [ ! -f "$SECRET_KEY_FILE" ]; then
                echo "[entrypoint] ERROR: SECRET_KEY file not found after 30s"
                exit 1
            fi
        fi
    fi
    SECRET_KEY=$(cat "$SECRET_KEY_FILE")
    export SECRET_KEY
fi

# Flask CLI commands in this entrypoint need an app import target.
export FLASK_APP="${FLASK_APP:-ui:create_app()}"

# ── Seed default preset into runtime configs volume (first run) ───────────────
# /app/configs is a named volume in docker-compose, which masks image files.
# Keep a baked copy under /app/.image-defaults and copy missing files at startup.
DEFAULT_PRESET_SRC=/app/.image-defaults/presets/default
DEFAULT_PRESET_DST=/app/configs/presets/default
if [ -d "$DEFAULT_PRESET_SRC" ]; then
    mkdir -p "$DEFAULT_PRESET_DST"
    cp -an "$DEFAULT_PRESET_SRC/." "$DEFAULT_PRESET_DST/"
fi

# ── Database init + migrations ─────────────────────────────────────────────────
# Only the web service runs migrations (RUN_MIGRATIONS=true set in compose).
# Gating prevents concurrent flask db upgrade calls from worker/poller, which
# would cause "database is locked" errors on SQLite.
if [ "${RUN_MIGRATIONS}" = "true" ]; then
    if [ ! -f /app/data/qlds_ui.db ]; then
        echo "[entrypoint] First run — initializing database..."
        flask init-db
        flask db stamp head
        echo "[entrypoint] Database ready."
    else
        # Guard against partial first-run: DB file exists but schema is missing
        # (e.g. container crashed after SECRET_KEY generation but before
        # flask init-db completed).
        DB_HAS_SCHEMA=$(python3 -c "
import sqlite3
con = sqlite3.connect('/app/data/qlds_ui.db')
tables = [r[0] for r in con.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
con.close()
print('yes' if 'alembic_version' in tables else 'no')
")
        if [ "$DB_HAS_SCHEMA" = "no" ]; then
            echo "[entrypoint] DB file exists but schema is missing — re-initializing..."
            flask init-db
            flask db stamp head
            echo "[entrypoint] Database ready."
        else
            echo "[entrypoint] Running database migrations..."
            flask db upgrade
            echo "[entrypoint] Migrations complete."
        fi
    fi

    USER_COUNT=$(python3 -c "
import sqlite3
con = sqlite3.connect('/app/data/qlds_ui.db')
count = con.execute(\"SELECT COUNT(*) FROM user\").fetchone()[0]
con.close()
print(count)
")
    if [ "$USER_COUNT" = "0" ]; then
        DEFAULT_USER="${DEFAULT_ADMIN_USER:-admin}"
        if flask create-default-admin "$DEFAULT_USER"; then
            echo "[entrypoint] Default admin created (username: $DEFAULT_USER, password: admin)"
            echo "[entrypoint] You will be required to change the password on first login."
        else
            echo "[entrypoint] ERROR: Failed to create default admin '$DEFAULT_USER'."
            exit 1
        fi
    fi
fi

exec "$@"
