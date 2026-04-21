---
paths:
  - "ui/**/*"
  - "ansible/**/*"
  - "terraform/**/*"
---

# Backend & Infrastructure Rules

## Ansible

- Always quote Jinja variables in YAML: `port: "{{ ssh_port }}"` not `port: {{ ssh_port }}`
- Variable names in templates must match `--extra-vars` passed from Python
- Use `--extra-vars` in JSON format for complex values

## Systemd templates

Wrap `ExecStart` in double quotes when args contain spaces:
```
ExecStart="/path/script.sh {{ qlds_args }}"
```

## Task status flow

Set transitional status → Execute operation → Set final status → Commit

Status enums are in `ui/models.py`:
- `HostStatus`: PENDING, PROVISIONING, PROVISIONED_PENDING_SETUP, ACTIVE, CONFIGURING, DELETING, REBOOTING, ERROR, UNKNOWN
- `InstanceStatus`: IDLE, DEPLOYING, DELETING, RUNNING, STOPPING, STOPPED, STARTING, RESTARTING, CONFIGURING, UPDATED, ERROR, UNKNOWN
- `QLFilterStatus`: NOT_INSTALLED, INSTALLING, ACTIVE, INACTIVE, UNINSTALLING, ERROR, UNKNOWN

## Deployment

Always run `flask db upgrade` as part of production deployments when database migrations are involved.

## System administration

Use `sudo` when reading system journals or logs on remote servers.
