# Deploy A New Instance

Open from **Servers** -> host row -> **Add QLDS Instance to &lt;host&gt;**.

Host not ready yet: [Add A Host (Cloud Or Standalone)](/docs/getting-started/add-host)

## Default Preset Behavior

When the deploy form opens, config is preloaded from the **default preset**.

- Default preset is a baseline template.
- You can load another preset, then modify values before deploy.
- Default preset itself is read-only from the deploy workflow.

Preset details: [Presets And Default Config](/docs/presets/overview)

## Basic Info Block

Required fields:

- **Instance Name**
- **Host Server**
- **Port**
- **Server Hostname**

Optional toggle:

- **99k LAN Rate**

`99k LAN Rate` controls LAN-rate profile for the instance.
Changing this later from the actions menu triggers reconfigure/restart.
Reference: [Instance Actions Menu](/docs/operations/instance-actions-menu)

## Main Tabs In Deploy Form

### Configuration Files

This tab has file-level sub-tabs:

- `server.cfg`
- `mappool.txt`
- `access.txt`
- `workshop.txt`

Editor controls per file:

- Upload file content
- Copy content
- Expand to full-screen editor

Linting:

- `server.cfg` shows inline lint diagnostics.
- Deploy is blocked if `server.cfg` has blocking lint errors.

### Plugins

Python plugin management for this instance:

- File tree + editor
- Checkbox selection for which plugins are included
- **Validate** button runs Python validation and reports line-level errors

### Factories

Factory files included in the deployment bundle.
Only selected/edited factory files are applied to the new instance.

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
