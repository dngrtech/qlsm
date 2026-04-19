#!/bin/bash

# Parse arguments
BUILD_NPM=""
DEV_ID=1
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --build-npm)
            BUILD_NPM="$2"
            shift
            ;;
        --id)
            DEV_ID="$2"
            shift
            ;;
        *)
            echo "Unknown parameter passed: $1"
            echo "Usage: $0 [--build-npm yes|no] [--id <number>]"
            exit 1
            ;;
    esac
    shift
done

if [[ -n "$BUILD_NPM" && "$BUILD_NPM" != "yes" && "$BUILD_NPM" != "no" ]]; then
    echo "Error: --build-npm argument must be 'yes' or 'no'"
    exit 1
fi
# Load environment variables from .env first, so CLI args can override them!
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Calculate ports and DBs based on ID
FLASK_PORT=$((5000 + DEV_ID))
REDIS_DB=$DEV_ID

export FLASK_RUN_PORT=$FLASK_PORT
export REDIS_URL="redis://localhost:6379/$REDIS_DB"
export REDIS_PREFIX="rcon-dev-$DEV_ID"
# Export for Vite to pick up
export VITE_API_URL="http://localhost:$FLASK_PORT"

echo "--------------------------------------------------"
echo "Starting DEV Environment #$DEV_ID"
echo "Flask Port: $FLASK_PORT"
echo "Redis DB  : $REDIS_DB"
echo "--------------------------------------------------"

# Guard against re-entrant cleanup if Ctrl+C is pressed repeatedly.
CLEANING_UP=0

# Function to clean up background processes for DEV
cleanup() {
  if [[ "$CLEANING_UP" -eq 1 ]]; then
    return
  fi
  CLEANING_UP=1
  trap - SIGINT SIGTERM

  echo "Stopping development Flask app, RQ worker, RCON service, and status poller..."
  local managed_pids=("$FLASK_PID" "$RQ_PID" "$RCON_PID" "$POLLER_PID")
  local pid

  for pid in "${managed_pids[@]}"; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
    pkill -TERM -P "$pid" 2>/dev/null || true
  done

  # Stop frontend process for this repo if it is still running.
  while IFS= read -r pid; do
    local pwdx_out
    pwdx_out=$(pwdx "$pid" 2>/dev/null)
    if [[ "$pwdx_out" == *"$PWD"* ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done < <(pgrep -u "$(id -u)" -f 'pnpm dev|vite' 2>/dev/null)

  # Wait briefly; force kill if anything is still alive.
  for pid in "${managed_pids[@]}"; do
    local tries=0
    [[ -n "$pid" ]] || continue
    while kill -0 "$pid" 2>/dev/null; do
      sleep 0.2
      tries=$((tries + 1))
      if [[ "$tries" -ge 20 ]]; then
        kill -9 "$pid" 2>/dev/null || true
        pkill -KILL -P "$pid" 2>/dev/null || true
        break
      fi
    done
  done

  # Final sweep for any stragglers tied to this dev config.
  kill_orphans

  echo "Development processes stopped."
  exit 0
}

# Trap SIGINT and SIGTERM
trap cleanup SIGINT SIGTERM

# Activate virtual environment
source .venv/bin/activate
export PYTHONUNBUFFERED=1

# Install missing dependencies only when requirements.txt has changed since last run
STAMP_FILE=".venv/.requirements_stamp"
if [[ ! -f "$STAMP_FILE" || requirements.txt -nt "$STAMP_FILE" ]]; then
  echo "requirements.txt changed — syncing dependencies..."
  pip install -q -r requirements.txt && touch "$STAMP_FILE"
fi

# Kill orphaned processes from previous dev sessions (crashed, SSH disconnect, etc.)
# Only kills processes owned by current user that match this dev environment's config.
kill_orphans() {
  local killed=0

  # Kill orphaned rcon_service processes matching our REDIS_PREFIX
  while IFS= read -r pid; do
    # Verify the process has our REDIS_PREFIX in its environment
    if grep -qz "REDIS_PREFIX=rcon-dev-$DEV_ID" /proc/"$pid"/environ 2>/dev/null; then
      echo "  Killing orphaned rcon_service (PID $pid)"
      kill "$pid" 2>/dev/null
      killed=1
    fi
  done < <(pgrep -u "$(id -u)" -f 'python -m rcon_service' 2>/dev/null)

  # Kill orphaned Flask dev servers on our port
  while IFS= read -r pid; do
    echo "  Killing orphaned Flask server (PID $pid)"
    kill "$pid" 2>/dev/null
    killed=1
  done < <(pgrep -u "$(id -u)" -f "run_dev.py --port=$FLASK_PORT" 2>/dev/null)

  # Kill orphaned RQ workers using our Redis DB
  while IFS= read -r pid; do
    if grep -qz "REDIS_URL=redis://localhost:6379/$REDIS_DB" /proc/"$pid"/environ 2>/dev/null; then
      echo "  Killing orphaned RQ worker (PID $pid)"
      kill "$pid" 2>/dev/null
      killed=1
    fi
  done < <(pgrep -u "$(id -u)" -f 'flask rq worker' 2>/dev/null)

  # Kill orphaned status poller processes using our Redis DB
  while IFS= read -r pid; do
    if grep -qz "REDIS_URL=redis://localhost:6379/$REDIS_DB" /proc/"$pid"/environ 2>/dev/null; then
      echo "  Killing orphaned status poller (PID $pid)"
      kill "$pid" 2>/dev/null
      killed=1
    fi
  done < <(pgrep -u "$(id -u)" -f 'run-status-poller' 2>/dev/null)

  # Kill orphaned frontend processes matching our dev directory
  while IFS= read -r pid; do
    local pwdx_out
    pwdx_out=$(pwdx "$pid" 2>/dev/null)
    if [[ "$pwdx_out" == *"$PWD"* ]]; then
      echo "  Killing orphaned frontend process (PID $pid)"
      kill -9 "$pid" 2>/dev/null
      killed=1
    fi
  done < <(pgrep -u "$(id -u)" -f 'vite|pnpm|esbuild' 2>/dev/null)

  if [[ $killed -eq 1 ]]; then
    echo "  Waiting for orphaned processes to exit..."
    sleep 1
  fi
}

echo "Checking for orphaned dev processes..."
kill_orphans

# Create log directory for dev (Promtail tails these files)
mkdir -p logs/dev

# Start Flask app (dev) in background via custom runner for SocketIO support
echo "Starting development Flask-SocketIO server on port $FLASK_PORT..."
python run_dev.py --port=$FLASK_PORT 2>&1 | tee logs/dev/flask.log &
FLASK_PID=$!

# Start RQ worker (dev) in background
echo "Starting development RQ worker..."
flask rq worker 2>&1 | tee logs/dev/worker.log &
RQ_PID=$!

# Start RCON service in background
echo "Starting RCON service..."
python -m rcon_service 2>&1 | tee logs/dev/rcon.log &
RCON_PID=$!

# Start status poller in background
echo "Starting status poller..."
flask run-status-poller 2>&1 | tee logs/dev/poller.log &
POLLER_PID=$!

# Ask if build is needed
cd frontend-react
if [[ -n "$BUILD_NPM" ]]; then
  if [[ "$BUILD_NPM" == "yes" ]]; then
    pnpm build
  fi
else
  read -p "Run 'pnpm build' before 'pnpm dev'? [y/N]: " do_build
  if [[ "$do_build" =~ ^[Yy]$ ]]; then
    pnpm build
  fi
fi

echo "Starting frontend development server (pnpm dev)..."
pnpm dev

# Wait for background processes (keeps the script alive)
wait $FLASK_PID
wait $RQ_PID
