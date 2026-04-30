# Process Affinity Design

## Goal

Automatically pin Quake Live dedicated server instances to separate host CPUs when a host has more than one CPU, while keeping the feature transparent to the operator and safe for existing production deployments.

## Current Context

QLSM deploys QLDS instances through RQ tasks that call Ansible playbooks. The playbooks render `/etc/systemd/system/qlds@<port>.service` from `ansible/templates/qlds@.service.j2`, then start or restart the systemd service.

The current models do not store host CPU count or per-instance CPU affinity. Vultr plan metadata already includes `vcpu`, so cloud hosts can infer CPU count from `Host.machine_size`. Standalone and self hosts need runtime CPU detection.

## Decision

Use persisted least-used hard pinning.

Hard pinning means a QLDS service is constrained to a specific Linux CPU index. QLSM should implement this with systemd `CPUAffinity=` instead of wrapping `ExecStart` in `taskset`.

Persisted least-used assignment means:

1. Store the host CPU count on `Host.cpu_count`.
2. Store the assigned CPU on `QLInstance.cpu_affinity`.
3. When assigning a new instance, count existing assigned instances on the same host.
4. Pick the CPU with the fewest assigned instances.
5. Break ties by lowest CPU index.
6. Persist that assignment and render it into the service file.

This avoids the skipped-port bug where a direct port-based rule would pin `27960` and `27962` to the same CPU on a 2 vCPU host.

Example on a 2 vCPU host:

```text
deploy 27960 -> CPU 0
deploy 27962 -> CPU 1
deploy 27961 -> CPU 0
deploy 27963 -> CPU 1
```

## One CPU Hosts

When a host has one CPU, or CPU count is unknown, QLSM should omit `CPUAffinity=` entirely. The instance continues to use the Linux scheduler exactly as it does today.

In the UI, unset affinity should display as `Automatic`.

## CPU Count Discovery

For Vultr hosts, infer `cpu_count` from `ui/vultr_plans.py` using `Host.machine_size`.

For standalone and self hosts, detect CPU count with `nproc` during host setup or before the first affinity assignment. If detection fails, leave `cpu_count` unset, omit affinity, continue deployment, and log a warning.

## Service Rendering

Add an optional `cpu_affinity` Ansible variable to playbooks that render `qlds@.service.j2`.

Render this line only when `cpu_affinity` is an integer:

```ini
CPUAffinity={{ cpu_affinity }}
```

Affected flows:

- Deploy instance
- Restart instance
- Apply instance config
- Reconfigure LAN rate

Start and stop flows do not need to re-render the service. Starting an already-rendered service will use the service file already present on disk.

## Existing Production Hosts

Upgrading QLSM must not restart existing QLDS instances or rewrite service files automatically.

Migration behavior:

- Existing `Host.cpu_count` values are initially null unless backfilled from provider metadata.
- Existing `QLInstance.cpu_affinity` values are null.
- Existing running services continue unchanged.
- The instance details drawer shows `CPU Affinity: Automatic`.
- New instances get affinity immediately when CPU count is known and greater than one.
- Existing instances get affinity the next time QLSM re-renders their service, such as restart, config apply with restart, or LAN rate reconfiguration.

For the current single production environment, the preferred manual migration path is:

1. Deploy the updated code and run migrations.
2. Manually set `cpu_affinity` values in the QLSM database for existing instances.
3. Restart each QLDS instance one at a time from QLSM.

This keeps QLSM as the source of truth and avoids direct service-file edits that could later be overwritten.

## UI

Expose the assigned CPU only in the instance details drawer, inside the existing `Details` section.

Field behavior:

- Label: `CPU Affinity`
- If `instance.cpu_affinity` is an integer: display `CPU <n>`
- If `instance.cpu_affinity` is null or missing: display `Automatic`

Do not show CPU affinity in:

- Host rows
- Instance rows
- Add/edit forms
- Live status
- Host drawer deployed-instance lists

The API should include `cpu_affinity` in `QLInstance.to_dict()` so `getInstanceById()` can populate the drawer without a new endpoint.

## Error Handling

Unknown CPU count should not block deploys or restarts. QLSM should log the condition and omit systemd affinity.

If a saved `cpu_affinity` is out of range for the current CPU count, QLSM should repair it on the next service render by choosing the least-used valid CPU.

If systemd or Ansible fails after rendering affinity, existing task error handling applies and marks the instance `ERROR`.

## Testing

Backend tests should cover:

- One CPU hosts return no affinity.
- Unknown CPU count returns no affinity.
- Skipped ports spread across CPUs based on actual instances.
- Least-used assignment with stable persisted values.
- Existing assignments are not changed unnecessarily.
- Out-of-range assignments are repaired.
- Deploy, restart, config apply, and LAN-rate reconfiguration pass `cpu_affinity` to Ansible.
- `QLInstance.to_dict()` includes `cpu_affinity`.

Template/playbook tests should cover:

- `qlds@.service.j2` omits `CPUAffinity` when unset.
- `qlds@.service.j2` renders `CPUAffinity=<n>` when set.

Frontend tests should cover:

- Instance details drawer shows `CPU Affinity: CPU <n>` when assigned.
- Instance details drawer shows `CPU Affinity: Automatic` when unset.
