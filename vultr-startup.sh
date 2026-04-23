#!/usr/bin/env bash
set -euxo pipefail

exec > >(tee -a /var/log/qlsm-startup.log) 2>&1

export DEBIAN_FRONTEND=noninteractive
export HOME=/root
export USER=root
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

export SITE_ADDRESS=":80"        # or "qlsm.customdomain.com" if you have a domain name 
export INSTALL_DIR="/opt/qlsm"
export ADMIN_USER="admin"
# export VULTR_API_KEY=""

apt-get update -y
apt-get install -y ca-certificates curl openssl

curl -fsSL https://get.docker.com | sh
apt-get update -y
apt-get install -y docker-compose-plugin
systemctl enable --now docker

until docker info >/dev/null 2>&1; do
  sleep 2
done

curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh -o /tmp/qlsm-install.sh
chmod +x /tmp/qlsm-install.sh

/tmp/qlsm-install.sh