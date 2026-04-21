# Presets And Default Config

A preset is a reusable bundle of config files, plugin selections, and factory file selections. Use presets to spin up new instances with a consistent starting point, or to save a working setup so you can replicate it later.

## What A Preset Contains

- `server.cfg`
- `mappool.txt`
- `access.txt`
- `workshop.txt`
- A set of selected minqlx plugins (checkboxes, not a raw `qlx_plugins` string)
- A set of selected factory files

## Default Preset

Opening **Deploy New Instance** pre-loads config from the `default` preset. It is a baseline template. Treat it as read-only — use **Save As New** to create your own variants.

## Plugin and Factory Selection

Instead of editing `qlx_plugins` manually, presets use checkboxes. Check the plugins you want; uncheck the ones you don't. The same applies to factory files — select the factories that should be included when this preset is deployed.

This means you can have completely different plugin and factory sets per instance. Two instances on the same host can each have their own independent selection.

## Custom Preset Workflow

1. Open **Deploy New Instance** (or **Edit Config** on an existing instance).
2. Adjust config files, plugin selections, and factory selections for your gamemode.
3. Click **Save As Preset** and give it a name.
4. On future deployments, click **Load Preset** and select your saved preset.

## Instance-Specific Ownership

A preset is only input at deploy time. After the instance is created, it keeps its own independent file set.

- Editing an instance's config later affects only that instance.
- Other instances are not affected.
- The original preset files are not modified.

## Related Pages

- [Deploy A New Instance](/docs/getting-started/deploy-new-instance)
- [Instance Actions Menu](/docs/operations/instance-actions-menu)
- [Manage A Running Server](/docs/operations/manage-instance)
