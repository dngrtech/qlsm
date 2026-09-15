# Plugin Repositories

**Settings → Plugin Repositories** lets you add third-party plugin sources and download their plugins into QLSM's shared plugin folder.

## Add A Repository

1. Click **Add Repository** and enter a name and the repository's base URL.
2. QLSM fetches `<URL>/qlsm-plugins.json` right away and lists the plugins it describes.

Names must be unique (ignoring case), and a URL can only be added once (ignoring a trailing `/`). Click the sync icon on a repository to fetch its list again.

A repository's `qlsm-plugins.json` looks like this. Every field except `filename` is optional:

```json
{
  "plugins": [
    {
      "filename": "hello_qlsm.py",
      "label": "Hello QLSM",
      "description": "Replies to !hello.",
      "runtime": "minqlxtended",
      "requires_qlsm_version": "1.30.0"
    }
  ]
}
```

A plugin can also ship a `<name>.ql-plugin.json` file next to its `.py` file. QLSM downloads it too, which gives the plugin a label, a description and an editable settings form (see [Plugin Settings](edit-configs.md#plugin-settings-cvars)).

## Download Plugins

1. Expand a repository and tick the plugins you want.
2. A plugin that doesn't declare its runtime needs one picked in its row before **Download selected** is enabled.
3. Click **Download selected**.

- Each plugin goes into the shared plugin folder for its runtime.
- If a file with the same name is already there, QLSM asks before overwriting it.
- A plugin that needs a newer QLSM version than you're running shows a red warning. You can still download it.

## Use A Downloaded Plugin

1. Run [Check for Updates](check-for-updates.md) on each host that should have the plugin. This copies it onto the host.
2. Open the instance's config (or **Deploy A New Instance**) and go to the **Plugins** tab. The plugin appears as a **shared** row (see [Shared Plugins](edit-configs.md#shared-plugins)).
3. Tick it and save.
