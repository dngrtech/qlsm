# Presets And Default Config

A preset is a reusable bundle of config files, plugin selections, and factory file selections. Use presets to spin up new instances with a consistent starting point, or to save a working setup so you can replicate it later.

## What A Preset Contains

- `server.cfg`
- `mappool.txt`
- `access.txt`
- `workshop.txt`
- Any custom flat `.cfg` or `.txt` config files you add
- Plugin files under the preset's plugin tree, including `.py`, `.txt`, and `.so`
- Factory files under the preset's factory set
- LD_PRELOAD user hooks (`.so` files) from the [Hooks tab](../features/hooks.md)
- A set of selected minqlx plugins
- A set of selected factory files

## Built-in Presets

QLSM ships a set of **built-in presets** that provide ready-to-use baselines. Built-in presets **cannot be modified, renamed, or deleted** — they are read-only. The Preset Manager's Save tab treats a built-in name as a new-name validation conflict instead of overwrite mode, and the Load tab disables delete for built-ins.

The `default` preset is always available as the standard baseline. Additional built-in presets may appear in the list depending on your QLSM version.

To customize a built-in preset, load it and save it under a new name from the Preset Manager's **Save / Overwrite** tab.

Use **Save Preset** when you want to turn the current draft into a reusable preset:

<img src="../../images/save-preset-button.png" width="146" />

Use **Load Preset** any time you want to replace the default draft with one of your saved configurations:

<img src="../../images/load-preset-button.png" width="146" />

## Plugin and Factory Selection

Instead of editing `qlx_plugins` manually, presets use checkboxes. Check the plugins you want; uncheck the ones you don't.

<img src="../../images/plugins.png" />

The same applies to factory files — select the factories that should be included when this preset is deployed.

<img src="../../images/factories.png" />

This means you can have completely different plugin and factory sets per instance. Two instances on the same host can each have their own independent selection.

The saved preset keeps both the files and the selection state. A plugin or factory file can exist in the preset without being selected for deployment. When you deploy from that preset, only selected plugins and selected factories are applied.

## Load A Saved Preset

Use **Load Preset** in the deploy form or in **Edit Config** to open the Preset Manager on the **Load Preset** tab:

<img src="../../images/preset-manager-load.png" />

Loading a preset overwrites the current draft with the saved config files, plugin file tree, plugin selections, factory files, and factory selections.

- Built-in presets (e.g., `default`) are always available and cannot be deleted or downloaded.
- User-created presets can be downloaded, renamed, or deleted from the row menu on this tab.

## Export A Preset

Any user-created preset can be downloaded as a ZIP archive from the row menu (⋮) on the **Load Preset** tab:

<img src="../../images/preset-manager-download.png" />

Another way to download a preset is to click **Download** button right after saving one from the **Save / Overwrite** tab:

<img src="../../images/preset-manager-download-button.png" />

Built-in presets cannot be downloaded.

The archive contains the full preset directory: config files (`server.cfg`, `mappool.txt`, `access.txt`, `workshop.txt`, and any custom `.cfg`/`.txt` files), plugin files and factory files, LD_PRELOAD user hooks, checked plugin/factory selections, and export metadata. Use this to back up a preset or move it to another QLSM instance.

## Import A Preset

Click **Import from ZIP** on the **Load Preset** tab and choose a previously exported archive: 

<img src="../../images/preset-manager-import-button.png" />

QLSM validates the archive before writing anything — corrupt or unreadable entries are rejected up front.

If the archive's preset name collides with an existing one, or isn't usable as-is, you're prompted to either **overwrite** the existing preset or **import as new** under a different name.

## Custom Preset Workflow

1. Open **Deploy New Instance** (or **Edit Config** on an existing instance).
2. Adjust config files, plugin files, plugin selections, factory files, and factory selections for your gamemode.
3. Click **Save Preset** and give it a name.
4. On future deployments, click **Load Preset** and select your saved preset.

## Update A Loaded Preset

If you load a user-created preset and then change the draft, click **Save Preset** to open the Preset Manager's **Save / Overwrite** tab. Selecting or typing the existing preset name switches the form into overwrite mode, with a warning border, an **Overwriting** badge, and an **Overwrite Preset** button.

- Built-in presets never enter overwrite mode — they cannot be modified.
- Use a different name to create your own editable copy of any preset, including built-ins.
- The description auto-fills from the matched preset until you edit it manually.

## Instance-Specific Ownership

A preset is only input at deploy time. After the instance is created, it keeps its own independent file set.

- Editing an instance's config later affects only that instance.
- Editing an instance's plugin or factory files later affects only that instance.
- Other instances are not affected.
- The original preset files are not modified.

## Related Pages

- [Deploy A New Instance](../getting-started/deploy-new-instance.md)
- [Instance Actions Menu](../operations/instance-actions-menu.md)
- [LD_PRELOAD Hooks](../features/hooks.md)
