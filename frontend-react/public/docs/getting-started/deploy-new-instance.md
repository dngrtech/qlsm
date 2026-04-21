# Deploy A New Instance

Open from **Servers** -> host row -> **Add QLDS Instance to &lt;host&gt;**.

![](/docs/images/add-new-instance-button.png)   

Prerequisite: [Add A Host (Cloud Or Standalone)](/docs/getting-started/add-host)

## Default Preset Behavior

When the deploy form opens, config is preloaded from the **default preset**.

- Default preset is a baseline template.
- You can load another preset, then modify values before deploy.
- Default preset itself is read-only from the deploy workflow.

Preset details: [Presets And Default Config](/docs/presets/overview)

## Basic Info Block

![](/docs/images/add-new-instance-basic.png)


Required fields:

- **Instance Name**
- **Host Server**
- **Port**
- **Server Hostname**

Optional toggle:

- [**99k LAN Rate**](/docs/features/99k-lan-rate)

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

Deployment writes a full config snapshot for that instance under `configs/<host>/<instance_id>/`.

- Later edits affect only that instance.
- Other instances are unchanged.
- Default preset files remain unchanged.

Next pages:

- [Instance Actions Menu](/docs/operations/instance-actions-menu)
- [Host Actions Menu](/docs/operations/host-actions-menu)
- [RCON Console](/docs/operations/rcon-console)
- [Use Logs And Chat Logs](/docs/operations/logs-and-chat)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
