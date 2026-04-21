# Add A Host (Cloud Or Standalone)

Hosts are added from **Servers** -> **Add New Host**.

## Supported OS

Use **Debian 12**.
Ubuntu support is planned, but this guide and production workflow assume Debian 12.

## Cloud Workflow

1. Set **Provider** to your cloud provider (for example `VULTR`).
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
- SSH Private Key
- Operating System (`Debian 12`)
- Timezone
3. Run **Test Connection** and confirm it shows **Connected**.
4. Submit the form.
5. Wait until setup finishes and host is **Active**.

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
