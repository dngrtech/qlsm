# Deploy A New Instance

Open from **Servers** -> host row -> **Add QLDS Instance to &lt;host&gt;**.

![](/docs/images/add-new-instance-button.png)   

Prerequisite: [Add A Host](/docs/getting-started/add-host)

Host limit: each host can have a maximum of **4 instances**. If a host already has 4, deploy the new instance to a different host or remove an existing one first.

## Default Preset Behavior

When the add new QLDS instance form opens, config is preloaded from the **default preset**.

- Default preset is a baseline template.
- You can edit the default preset or load another preset, then modify values before deploy.
- Default preset itself is read-only.

Preset details: [Presets And Default Config](/docs/presets/overview)

## Basic Info Block

![](/docs/images/add-new-instance-basic.png)


Required fields:

- **Instance Name**
- **Host Server**
- **Port**
- **Server Hostname** (this is auto-synced with `sv_hostname` value)

Optional toggle:

- [**99k LAN Rate**](/docs/features/99k-lan-rate.md)

`99k LAN Rate` controls LAN-rate profile for the instance.
Changing this later from the actions menu triggers reconfigure/restart.
Reference: [Instance Actions Menu](/docs/operations/instance-actions-menu)

## Main Tabs In Deploy Form

Config editing details live here: [Edit Configs, Plugins, And Factories](/docs/operations/edit-configs)

## Create Instance

1. Review fields and tabs.
2. Click **Create Instance**.
3. Wait until status leaves transitional states and reaches running/healthy state.

## What Happens To Config After Deploy

QLSM deploys QLDS instance and pushes full config snapshot (configs, plugins, and factories) to that instance.

- Later edits affect only that instance.
- Other instances are unchanged.
- Default preset files remain unchanged.

Next pages:

- [Instance Actions Menu](/docs/operations/instance-actions-menu)
- [Host Actions Menu](/docs/operations/host-actions-menu)
- [RCON Console](/docs/operations/rcon-console)
- [Use Logs And Chat Logs](/docs/operations/logs-and-chat)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
