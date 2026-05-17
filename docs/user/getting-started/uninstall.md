# Uninstall QLSM

The uninstall script reverses what the install script did.

## Default (data preserved)

Stops containers, removes the QLSM sshd config (`/etc/ssh/sshd_config.d/qlsm.conf`), and deletes `~/.qlsm-ssh/`. Your install directory (`~/qlsm/`) and all data inside it are left untouched.

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-uninstall.sh | bash
```

## Purge (removes everything)

Also removes named Docker volumes (Redis data, Caddy TLS certificates, Loki/Grafana data) and the install directory. Each destructive step prompts for confirmation:

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-uninstall.sh | bash -s -- --purge
```

Skip confirmation prompts (for scripted use):

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-uninstall.sh | bash -s -- --purge --yes
```

## Vultr / system install (`/opt/qlsm`)

The [Vultr startup script](https://github.com/dngrtech/qlsm/blob/main/vultr-startup.sh) installs to `/opt/qlsm` as root:

```bash
# Data preserved
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-uninstall.sh | sudo INSTALL_DIR=/opt/qlsm bash

# Full removal
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-uninstall.sh | sudo INSTALL_DIR=/opt/qlsm bash -s -- --purge --yes
```

## Custom install directory

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-uninstall.sh | INSTALL_DIR=/path/to/qlsm bash -s -- --purge
```

## What gets removed

| Step | Default | `--purge` |
|------|:-------:|:---------:|
| Stop containers and remove networks | ✓ | ✓ |
| Remove `/etc/ssh/sshd_config.d/qlsm.conf` | ✓ | ✓ |
| Remove `~/.qlsm-ssh/` | ✓ | ✓ |
| Remove Docker volumes (Redis, Caddy, Loki, Grafana) | — | ✓ (confirmed) |
| Remove install directory and all data | — | ✓ (confirmed) |
