#!/bin/sh
set -e

# Set up ~/.qlsm-ssh/ on the host and configure sshd to accept keys from it.
# Idempotent — safe to run on every `docker compose up`.

mkdir -p /qlsm-ssh
chmod 700 /qlsm-ssh
touch /qlsm-ssh/authorized_keys
chmod 600 /qlsm-ssh/authorized_keys

nsenter -t 1 -m -u -i -n -p -- /bin/sh -c '
  mkdir -p /etc/ssh/sshd_config.d
  printf "AuthorizedKeysFile .ssh/authorized_keys .qlsm-ssh/authorized_keys\n" \
    > /etc/ssh/sshd_config.d/qlsm.conf
  systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
'

# Detect host OS type and write JSON for the app to consume.
# The web container reads this from /host-ssh/host-os-type (same volume, different mount path).
HOST_OS_RELEASE=$(nsenter -t 1 -m -- cat /etc/os-release 2>/dev/null || echo "")
HOST_OS_ID=$(printf '%s\n' "$HOST_OS_RELEASE" | grep "^ID=" | cut -d= -f2 | tr -d '"')
HOST_OS_PRETTY=$(printf '%s\n' "$HOST_OS_RELEASE" | grep "^PRETTY_NAME=" | cut -d= -f2- | tr -d '"')

case "${HOST_OS_ID:-}" in
  debian) HOST_OS_TYPE="debian" ;;
  ubuntu) HOST_OS_TYPE="ubuntu" ;;
  *)      HOST_OS_TYPE="" ;;
esac

printf '{"os_type":"%s","pretty_name":"%s"}\n' "$HOST_OS_TYPE" "$HOST_OS_PRETTY" \
  > /qlsm-ssh/host-os-type || true
