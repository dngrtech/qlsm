#!/bin/bash
# ---------------------------------------------------------------------------
# Simplified QLDS + minqlx installer for Debian/Ubuntu           (2025-04-25)
#   • Installs all prerequisites
#   • Creates system user `ql`
#   • Installs SteamCMD and Quake Live dedicated server as that user
#   • Builds and deploys minqlx (binary + Python package)
#   • Optionally installs minqlx-plugins and their Python deps
#   • Creates & starts a systemd service (qlds.service)
#   • Disables UFW, sets iptables default-deny, and opens only required ports
#
# Run with:  sudo ./install.sh
# ---------------------------------------------------------------------------

set -e  # exit immediately on error

# --- Configuration --------------------------------------------------------
QLDS_USER="ql"
QLDS_GROUP="ql"
QLDS_HOME="/home/${QLDS_USER}"
QLDS_DIR="${QLDS_HOME}/qlds"
STEAMCMD_DIR="${QLDS_HOME}/Steam"
MINQLX_BUILD_DIR="/tmp/minqlx-build"
SERVICE_FILE="/etc/systemd/system/qlds.service"
GAME_UDP_PORTS=(27960 27961 27962 27963)
RCON_TCP_PORTS=(28888 28889 28890 28891)
# --------------------------------------------------------------------------

# --- Root check -----------------------------------------------------------
if [[ $(id -u) -ne 0 ]]; then
  echo "This script must be run as root (sudo)." >&2
  exit 1
fi

echo "### Starting QLDS + minqlx installation ###"

# --- 1. Install system packages ------------------------------------------
echo "--> Installing prerequisites..."
dpkg --add-architecture i386
apt-get update
apt-get install -y --no-install-recommends \
  lib32gcc-s1 lib32stdc++6 libc6-i386 \
  wget ca-certificates \
  redis-server \
  git make build-essential \
  python3 python3-dev python3-pip \
  iptables-persistent

# --- 2. Create service account -------------------------------------------
echo "--> Ensuring user '${QLDS_USER}' exists..."
groupadd -f "${QLDS_GROUP}"
id -u "${QLDS_USER}" &>/dev/null || \
  useradd -m -g "${QLDS_GROUP}" -s /bin/bash "${QLDS_USER}"

# --- 3. Remove any root-owned Steam remnants ------------------------------
echo "--> Cleaning stale root-owned Steam files..."
rm -rf /root/.steam /root/Steam 2>/dev/null || true

# --- 4. Install SteamCMD & download Quake Live (as ql) --------------------
echo "--> Installing SteamCMD and QLDS ..."
runuser -u "${QLDS_USER}" -- bash <<'EOF'
set -e
mkdir -p "$HOME/Steam" "$HOME/qlds"
cd "$HOME/Steam"

if [[ ! -f steamcmd.sh ]]; then
  wget -qO steamcmd_linux.tar.gz \
    https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz
  tar xf steamcmd_linux.tar.gz && rm steamcmd_linux.tar.gz
fi

"$HOME/Steam/steamcmd.sh" \
  +force_install_dir "$HOME/qlds" \
  +login anonymous \
  +app_update 349090 validate \
  +quit
EOF

# --- 5. Build minqlx ------------------------------------------------------
echo "--> Building minqlx ..."
rm -rf "${MINQLX_BUILD_DIR}"
git clone --depth 1 https://github.com/MinoMino/minqlx.git "${MINQLX_BUILD_DIR}"
make -C "${MINQLX_BUILD_DIR}"

# --- 6. Deploy minqlx (binary + scripts) ----------------------------------
echo "--> Deploying minqlx binary and helper scripts..."
install -o "${QLDS_USER}" -g "${QLDS_GROUP}" -m 755 \
  "${MINQLX_BUILD_DIR}/bin/minqlx.x64.so"        "${QLDS_DIR}/"
install -o "${QLDS_USER}" -g "${QLDS_GROUP}" -m 755 \
  "${MINQLX_BUILD_DIR}/bin/run_server_x64_minqlx.sh" "${QLDS_DIR}/"

for helper in minqlx-cmd quake_live.sh; do
  if [[ -f "${MINQLX_BUILD_DIR}/${helper}" ]]; then
    install -o "${QLDS_USER}" -g "${QLDS_GROUP}" -m 755 \
      "${MINQLX_BUILD_DIR}/${helper}" "${QLDS_DIR}/"
  fi
done

# --- 7. Deploy minqlx Python package -------------------------------------
echo "--> Deploying minqlx Python package..."
cp -r "${MINQLX_BUILD_DIR}/python/minqlx" "${QLDS_DIR}/"
chown -R "${QLDS_USER}:${QLDS_GROUP}" "${QLDS_DIR}/minqlx"
rm -rf "${MINQLX_BUILD_DIR}"   # cleanup build dir

# --- 8. Optional: minqlx-plugins -----------------------------------------
echo "--> Ensuring minqlx plugins ..."
runuser -u "${QLDS_USER}" -- bash <<'EOF'
set -e
PLUGDIR="$HOME/qlds/minqlx-plugins"

if [[ -d "$PLUGDIR/.git" ]]; then
  echo "    -> plugins repo already present; pulling latest commits..."
  git -C "$PLUGDIR" pull --ff-only
elif [[ -d "$PLUGDIR" ]]; then
  echo "    -> '$PLUGDIR' exists but is not a git repo; skipping clone."
else
  git clone https://github.com/MinoMino/minqlx-plugins.git "$PLUGDIR"
fi
EOF

REQ_FILE="${QLDS_DIR}/minqlx-plugins/requirements.txt"
if [[ -f "${REQ_FILE}" ]]; then
  echo "--> Installing/updating Python deps for plugins ..."
  pip3 install --break-system-packages -r "${REQ_FILE}"
fi

# --- 9. Network and Firewall Configuration -------------------------------
echo "--> Configuring firewall ..."

# 9-a) Disable UFW if it exists
if systemctl list-unit-files | grep -q '^ufw.service'; then
  echo "    -> Disabling UFW"
  systemctl stop ufw  || true
  systemctl disable ufw || true
  ufw --force disable 2>/dev/null || true
fi

# 9-b) sysctl tweak
echo "net.ipv4.conf.all.route_localnet=1" >> /etc/sysctl.conf
sysctl -q -p

# 9-c) NAT rules for local redirection
for port in "${GAME_UDP_PORTS[@]}"; do
  iptables -t nat -A POSTROUTING -p udp -d 127.0.0.1 --dport "$port" -j SNAT --to-source 127.0.0.1
  iptables -t nat -A PREROUTING  -p udp --dport "$port"              -j DNAT --to-destination 127.0.0.1
done
iptables -t nat -A INPUT -d 127.0.0.1 -j SNAT --to-source 127.0.0.1

# 9-d) Default-deny filter rules
echo "    -> Setting default-deny policies"
iptables -P INPUT   DROP
iptables -P FORWARD DROP
iptables -P OUTPUT  ACCEPT

# Flush INPUT to build clean rule-set
iptables -F INPUT

# Allow loopback & established connections
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow SSH
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow game UDP ports
for port in "${GAME_UDP_PORTS[@]}"; do
  iptables -A INPUT -p udp --dport "$port" -j ACCEPT
done

# Allow RCON / query TCP ports
for port in "${RCON_TCP_PORTS[@]}"; do
  iptables -A INPUT -p tcp --dport "$port" -j ACCEPT
done

# Persist rules
netfilter-persistent save

# --- 10. Create & start systemd service ----------------------------------
echo "--> Creating systemd service (qlds.service) ..."
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Quake Live Dedicated Server (minqlx)
After=network.target

[Service]
Type=simple
User=${QLDS_USER}
Group=${QLDS_GROUP}
WorkingDirectory=${QLDS_DIR}
ExecStart=${QLDS_DIR}/run_server_x64_minqlx.sh +set fs_homepath ${QLDS_DIR}
Restart=on-failure
RestartSec=5s
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable --now qlds.service

# --- 11. Done -------------------------------------------------------------
echo
echo "### Installation complete! ###"
echo
echo "• Service **qlds** is now running (sudo systemctl status qlds)."
echo "• Firewall: default-deny with only SSH, game UDP, and RCON TCP ports open."
echo "• Logs & configs:  ${QLDS_DIR}"

