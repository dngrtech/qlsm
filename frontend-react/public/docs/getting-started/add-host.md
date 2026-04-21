# Add A Host (Cloud Or Standalone)

Hosts are added from **Servers** -> **Add New Host**.

## Supported OS

Use **Debian 12**.
Ubuntu is support as well, but [99k LAN rate](/docs/features/99k-lan-rate.md) is not compatible with Ubuntu. This guide and production workflow assume Debian 12.

## Vultr Cloud Workflow

1. Set **Provider** to `VULTR` cloud provider.
2. Select **Continent**, **Region**, and **Machine Size / Plan**.
3. Submit the form.
4. Wait until host status reaches **Active**.

Cloud hosts inherit timezone from selected region. That timezone is later used by [Configure Auto-Restart](/docs/operations/auto-restart).

## Standalone Workflow

1. Set **Provider** to `Standalone`.
2. Fill:
   - Host Name
   - IP Address
   - SSH Port
   - SSH Username
   - SSH Private Key (or password for bootstrap — QLSM installs a managed key then discards the password)
   - Timezone
3. Run **Test Connection** and confirm it shows **Connected**. OS is auto-detected during the connection test.
4. Submit the form.
5. Wait until setup finishes and host is **Active**.

## Self-Host Workflow

The **QLSM Host (self)** provider runs game servers on the same machine that runs the QLSM Docker stack. Useful when you already have a spare Linux box and don't want a separate VM just for game servers.

1. Set **Provider** to `QLSM Host (self)`.
2. The form pre-fills the detected IP address, OS, and SSH user — verify these are correct.
3. Set **Timezone**.
4. Submit the form.
5. Wait until setup finishes and host is **Active**.

QLSM generates and manages its own SSH key for self-host automation. Your personal SSH keys are never accessed.

Only one self host may exist at a time.

## Timezone Requirement

Timezone is operational, not cosmetic.

- [Configure Auto-Restart](/docs/operations/auto-restart) executes in host local timezone.
- Wrong timezone means restart at the wrong local hour.
- Wrong restart time delays Workshop item refresh on running servers.

Continue with: [Configure Auto-Restart](/docs/operations/auto-restart)

## Related Pages

- [Deploy A New Instance](/docs/getting-started/deploy-new-instance)
- [Host Actions Menu](/docs/operations/host-actions-menu)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
