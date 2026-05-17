# Uninstall QLSM

The uninstall script reverses what the install script did.

## Default (data preserved)

Stops containers, removes the QLSM sshd config (`/etc/ssh/sshd_config.d/qlsm.conf`), and deletes `~/.qlsm-ssh/`. Your install directory and all data inside it are left untouched.

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-uninstall.sh | bash
```

## Purge (removes everything)

Also removes named Docker volumes (Redis data, Caddy TLS certificates, Loki/Grafana data) and the install directory. Each destructive step prompts for confirmation:

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-uninstall.sh | bash -s -- --purge
```

## Non-default install directory

If QLSM was installed somewhere other than `~/qlsm` (e.g. the Vultr startup script uses `/opt/qlsm`), set `INSTALL_DIR` and use `sudo` if needed:

```bash
curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-uninstall.sh | sudo INSTALL_DIR=/opt/qlsm bash -s -- --purge
```

## What gets removed

| Step | Default | `--purge` |
|------|:-------:|:---------:|
| Stop containers and remove networks | ✓ | ✓ |
| Remove `/etc/ssh/sshd_config.d/qlsm.conf` | ✓ | ✓ |
| Remove `~/.qlsm-ssh/` | ✓ | ✓ |
| Remove Docker volumes (Redis, Caddy, Loki, Grafana) | — | ✓ (confirmed) |
| Remove install directory and all data | — | ✓ (confirmed) |
