# Presets And Default Config

A preset is a reusable bundle of config files, plugin selections, and factory file selections. Use presets to spin up new instances with a consistent starting point, or to save a working setup so you can replicate it later.

## What A Preset Contains

- `server.cfg`
- `mappool.txt`
- `access.txt`
- `workshop.txt`
- A set of selected minqlx plugins (checkboxes, not a raw `qlx_plugins` string)
- A set of selected factory files

## Built-in Presets

QLSM ships a set of **built-in presets** that provide ready-to-use baselines. Built-in presets **cannot be modified, renamed, or deleted** — they are read-only. The **Update Preset** button is hidden when a built-in preset is loaded, and the Load Preset picker does not show a delete option for them.

The `default` preset is always available as the standard baseline. Additional built-in presets may appear in the list depending on your QLSM version.

To customize a built-in preset, load it and use **Save As New** to create your own editable copy.

<img src="../../images/save-preset-button.png" width="146" />

Use **Save as Preset** or **Save As New** when you want to turn the current draft into a reusable preset.

<img src="../../images/load-preset-button.png" width="146" />

Use **Load Preset** any time you want to replace the default draft with one of your saved configurations.

## Plugin and Factory Selection

Instead of editing `qlx_plugins` manually, presets use checkboxes. Check the plugins you want; uncheck the ones you don't.

<img src="../../images/plugins.png" />

The same applies to factory files — select the factories that should be included when this preset is deployed.

<img src="../../images/factories.png" />

This means you can have completely different plugin and factory sets per instance. Two instances on the same host can each have their own independent selection.

## Load A Saved Preset

Use **Load Preset** in the deploy form or in **Edit Config** to open the preset picker.

<img src="../../images/load-preset-modal.png" width="463" />

Loading a preset overwrites the current draft config with the saved preset contents.

- Built-in presets (e.g., `default`) are always available and cannot be deleted.
- User-created presets can be deleted from this modal.

## Custom Preset Workflow

1. Open **Deploy New Instance** (or **Edit Config** on an existing instance).
2. Adjust config files, plugin selections, and factory selections for your gamemode.
3. Click **Save as Preset** or **Save As New** and give it a name.
4. On future deployments, click **Load Preset** and select your saved preset.

## Update A Loaded Preset

If you load a user-created preset and then change the draft, the form exposes an **Update Preset** button.

<img src="../../images/update-preset-button.png" width="230" />

Use **Update Preset** to overwrite the saved preset with your current draft.

- The button stays disabled (greyed out) until the loaded preset has unsaved changes.
- The **Update Preset** button is not shown at all for built-in presets — they cannot be modified.
- Use **Save As New** to create your own editable copy of any preset, including built-ins.

## Instance-Specific Ownership

A preset is only input at deploy time. After the instance is created, it keeps its own independent file set.

- Editing an instance's config later affects only that instance.
- Other instances are not affected.
- The original preset files are not modified.

## Related Pages

- [Deploy A New Instance](../getting-started/deploy-new-instance.md)
- [Instance Actions Menu](../operations/instance-actions-menu.md)
