# Add A Host (Cloud Or Standalone)

Hosts are added from **Servers** -> **Add New Host**. <img src="../../images/add-new-host-button.png" width="120" style="display:inline; vertical-align:middle; margin:0 4px" />

## Server Runtime

Every host runs one of two Quake Live server runtimes, chosen from the **Server Runtime** picker on the Add Host form, right below **Provider**:

- **minqlx** — the original runtime, and every plugin QLSM ships today. Provisions/expects **Debian 12**.
- **minqlxtended** — a hard fork with no plugin compatibility with minqlx. Provisions/expects **Ubuntu 24.04**, and requires **Python 3.12 or newer** on the target machine.

For Vultr cloud hosts, QLSM provisions the matching OS image automatically — there's no separate OS choice.

For **standalone** hosts, the target machine's OS is auto-detected during connection testing, and creating a minqlxtended host additionally requires the detected Python to already be 3.12 or newer — the Add Host form rejects the submission with an explanation if it isn't.

For a **self** host, there's no equivalent inline check: QLSM has no way to detect the local machine's Python version before creating the host record. The form accepts the submission, the host is created, and setup runs in the background — if the machine's Python turns out to be older than 3.12, setup fails and the host lands in **Error** status instead of **Active**. If you're creating a minqlxtended self host, confirm `python3 --version` is 3.12 or newer on that machine yourself before you submit the form.

**This choice is permanent.** There is no setting to change it later. Moving a host to the other runtime means saving a preset from the existing host and deploying a brand-new host with the other runtime selected.

**Presets do not carry across runtimes.** A preset saved from a minqlx instance cannot be loaded onto a minqlxtended host, and vice versa, because the plugins in one do not run on the other. The Preset Manager's Load tab shows an incompatible preset greyed out, labeled with the runtime it was saved from, and does nothing if you click it. See [Presets And Default Config](../presets/overview.md).

## Self-Host Deployment

The **QLSM Host (self)** provider runs game servers on the same machine that runs the QLSM Docker stack. Useful when you already have a spare Linux box and don't want a separate VM just for game servers.

1. Set **Provider** to `QLSM Host (self)`.
2. The form shows the detected OS, pre-fills the inferred SSH user, and may pre-fill **Server address** if `QLSM_HOST_IP` is configured. Verify these values before continuing.
3. Set **Timezone**.
4. Click `Add Host` button to submit the form.
5. Wait until setup finishes and host is **Active**.

![](../images/qlsm-self-deployment.png)


QLSM generates and manages its own SSH key for self-host automation. Your personal SSH keys are never accessed.

For self-host setup, the SSH user can be `root` or another account with passwordless `sudo` privileges. QLSM uses that account as the management login for automation tasks.

During setup, QLSM creates a dedicated `ql` system user for Quake Live files and services. Game server assets and processes run under `ql`, but QLSM continues to connect as the configured management account when it needs to automate the host later.

Only one `QLSM Host (self)` deployment may exist at a time.

## Standalone Workflow

1. Set **Provider** to `Standalone`.
2. Fill:
   * Host Name
   * IP Address
   * SSH Port
   * SSH Username
   * SSH Private Key (or password for bootstrap — QLSM installs a managed key then discards the password)
   * Timezone
3. Run **Test Connection** and confirm it shows **Connected**. OS is auto-detected during the connection test.
4. Click `Add Host` button to submit the form.
5. Wait until setup finishes and host is **Active**.

![](../images/qlsm-standalone-deployment.png)


## Vultr Cloud Deployment

### Prerequisites

Create a Vultr API key by following Vultr's official guide: [Create New API Key](https://docs.vultr.com/platform/other/api/other-user/create-api-key). Copy and store the key immediately because Vultr only shows it once.

Set `VULTR_API_KEY` in the QLSM environment before using Vultr provisioning.

**One-liner install** — pass the key inline:

```bash
VULTR_API_KEY=your_vultr_api_key bash <(curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh)
```

**Git clone / manual install** — edit `.env` before starting:

```bash
# In .env, find and uncomment this line:
VULTR_API_KEY=your_vultr_api_key
```

Then start with `docker compose up -d`.

You can also set or change the Vultr API key later without editing `.env`, from **Settings → Vultr API Key**. A key saved there takes precedence over `.env` and travels with a [global backup](../administration/backup-restore.md).

One-line install example with both a domain and Vultr provisioning:

```bash
SITE_ADDRESS=qlsm.example.com VULTR_API_KEY=your_vultr_api_key bash <(curl -fsSL https://raw.githubusercontent.com/dngrtech/qlsm/main/qlsm-install.sh)
```

### Workflow

1. Set **Provider** to `VULTR` cloud provider.
2. Select **Continent**, **Region**, and **Machine Size / Plan**.
3. Click `Add Host` button to submit the form.
4. Wait until host status reaches **Active**.

![](../images/qlsm-vultr-deployment.png)

Cloud hosts inherit timezone from selected region. That timezone is later used by [Configure Auto-Restart](../operations/auto-restart.md).

## Timezone Requirement

Timezone is operational, not cosmetic.

- [Configure Auto-Restart](../operations/auto-restart.md) executes in host local timezone.
- Wrong timezone means restart at the wrong local hour.
- Wrong restart time delays Workshop item refresh on running servers.

Continue with: [Configure Auto-Restart](../operations/auto-restart.md)

## Related Pages

- [Deploy A New Instance](deploy-new-instance.md)
- [Presets And Default Config](../presets/overview.md)
- [Host Actions Menu](../operations/host-actions-menu.md)
- [Deployment Troubleshooting](../help/deployment-troubleshooting.md)
