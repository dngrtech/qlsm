#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# QLSM — uninstaller
#
# Run from the QLSM install directory, or set INSTALL_DIR:
#   bash qlsm-uninstall.sh
#
# Flags:
#   --purge    Also remove named Docker volumes (Redis data, Caddy certs, etc.)
#              and the install directory. Irreversible — data is lost.
#   --yes, -y  Skip confirmation prompts (for automated/scripted use).
#
# Environment variables:
#   INSTALL_DIR   Path to the QLSM install directory (default: ~/qlsm)
#   NO_COLOR      Set to any value to disable colour output
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Flags ─────────────────────────────────────────────────────────────────────
PURGE=0
YES=0
for arg in "$@"; do
    case "$arg" in
        --purge)    PURGE=1 ;;
        --yes|-y)   YES=1 ;;
        --help|-h)
            sed -n '2,/^set/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
    esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; RESET=''
fi
info()    { echo -e "${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
success() { echo -e "${GREEN}✓${RESET}  $*"; }
warn()    { echo -e "${YELLOW}!${RESET}  $*"; }
die()     { echo -e "${RED}✗${RESET}  $*" >&2; exit 1; }

confirm() {
    local prompt="$1"
    if [[ $YES -eq 1 ]]; then return 0; fi
    echo -e "${YELLOW}?${RESET}  ${BOLD}${prompt}${RESET} [y/N] " >&2
    read -r ans </dev/tty
    [[ "$ans" =~ ^[Yy]$ ]]
}

# ── Config ────────────────────────────────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-$HOME/qlsm}"

echo ""
echo -e "${BOLD}  QLSM — Quake Live Server Manager — Uninstaller${RESET}"
echo "  https://github.com/dngrtech/qlsm"
echo ""

if [[ ! -d "$INSTALL_DIR" ]]; then
    die "Install directory not found: ${INSTALL_DIR}
  Set INSTALL_DIR if you installed to a non-default location."
fi

# ── Detect compose command ────────────────────────────────────────────────────
if docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    warn "Docker Compose not found — skipping container teardown."
    COMPOSE=""
fi

# ── 1. Stop and remove containers ─────────────────────────────────────────────
if [[ -n "$COMPOSE" ]]; then
    if [[ -f "${INSTALL_DIR}/docker-compose.yml" ]]; then
        info "Stopping QLSM containers..."
        (cd "${INSTALL_DIR}" && ${COMPOSE} down --remove-orphans) \
            && success "Containers stopped and removed" \
            || warn "docker compose down reported an error (containers may already be stopped)"
    else
        warn "No docker-compose.yml found in ${INSTALL_DIR} — skipping container teardown."
    fi
fi

# ── 2. Remove named Docker volumes (--purge only) ─────────────────────────────
if [[ $PURGE -eq 1 ]]; then
    if [[ -n "$COMPOSE" ]] && [[ -f "${INSTALL_DIR}/docker-compose.yml" ]]; then
        echo ""
        warn "This will permanently delete all QLSM Docker volumes:"
        warn "  Redis data, Caddy TLS certificates and config, Loki/Grafana data."
        if confirm "Remove Docker volumes?"; then
            (cd "${INSTALL_DIR}" && ${COMPOSE} down --volumes) \
                && success "Docker volumes removed" \
                || warn "Volume removal reported an error (may already be gone)"
        else
            info "Skipping volume removal."
        fi
    fi
fi

# ── 3. Remove sshd config added by host-init ──────────────────────────────────
SSHD_CONF="/etc/ssh/sshd_config.d/qlsm.conf"
if [[ -f "$SSHD_CONF" ]]; then
    info "Removing QLSM sshd config (${SSHD_CONF})..."
    if sudo rm -f "$SSHD_CONF"; then
        # Reload sshd — try both service names (Ubuntu: ssh, others: sshd)
        sudo systemctl reload ssh 2>/dev/null \
            || sudo systemctl reload sshd 2>/dev/null \
            || warn "Could not reload sshd — reload manually if needed."
        success "sshd config removed and sshd reloaded"
    else
        warn "Could not remove ${SSHD_CONF} — remove it manually with sudo."
    fi
else
    info "No QLSM sshd config found at ${SSHD_CONF} — skipping."
fi

# ── 4. Remove ~/.qlsm-ssh ─────────────────────────────────────────────────────
QLSM_SSH_DIR="${HOME}/.qlsm-ssh"
if [[ -d "$QLSM_SSH_DIR" ]]; then
    info "Removing ${QLSM_SSH_DIR}..."
    rm -rf "$QLSM_SSH_DIR"
    success "${QLSM_SSH_DIR} removed"
else
    info "${QLSM_SSH_DIR} not found — skipping."
fi

# ── 5. Remove install directory (--purge only) ────────────────────────────────
if [[ $PURGE -eq 1 ]]; then
    echo ""
    warn "This will permanently delete ${INSTALL_DIR} and ALL of its contents:"
    warn "  Database, server configs, Terraform state, Ansible inventory, logs, SSH keys."
    warn "  This CANNOT be undone."
    if confirm "Delete ${INSTALL_DIR}?"; then
        rm -rf "${INSTALL_DIR}"
        success "${INSTALL_DIR} deleted"
    else
        info "Skipping install directory removal."
        info "You can delete it manually: rm -rf ${INSTALL_DIR}"
    fi
else
    echo ""
    warn "Install directory preserved: ${INSTALL_DIR}"
    warn "  It contains your database, configs, SSH keys, and Terraform state."
    warn "  To delete everything, re-run with: bash qlsm-uninstall.sh --purge"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  Uninstall complete.${RESET}"
echo ""
if [[ $PURGE -eq 0 ]]; then
    echo "  Your data is still at: ${INSTALL_DIR}"
    echo ""
fi
