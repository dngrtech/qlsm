# Check For Plugin Updates

QLSM ships a built-in set of minqlx plugins. When a new QLSM version fixes or adds a plugin, a host and its instances keep their existing copies until you update them. **Check for Updates** shows exactly which plugin files differ from the version QLSM ships, and lets you choose which ones to update.

The check itself changes nothing. Files are only replaced after you click **Update Selected**.

## Open The Check

1. Go to the **Servers** page.
2. Open the host row **Actions** menu.
3. Click **Check for Updates**.

<img src="../../images/host-actions-check-for-updates.png" />

The host must be **Active**. The check connects to the host, so it can take a few seconds.

## Read The Results

<img src="../../images/check-for-updates-modal.png" width="512" />

The modal has two kinds of sections.

**Common plugin pool.** This is the host's shared copy of QLSM's built-in plugins and of any plugin you downloaded from a [plugin repository](plugin-repositories.md). A freshly downloaded plugin shows here as **added** until you push it. Every instance on the host gets these files unless its own plugin set already includes a file with the same name.

**One box per instance.** These are the plugin files that belong to that instance, the same ones you see on its **Plugins** tab. A file is listed as **updated** when the instance has its own copy and QLSM ships a different version. Plugins the instance doesn't have its own copy of aren't listed, because the instance already gets them from the common plugin pool.

If everything already matches, the modal says **no updates available**.

## Choose What To Update

- **Common plugin pool** is ticked when it has changes.
- **Updated** files are ticked. Updating them replaces the instance's copy, **including any edits you made to that file in the plugin editor**. Untick a file you've customized and want to keep.
- **Restart to apply** is ticked for running instances, unless **Defer restarts** is on under **Settings** → **Instance Restarts**: then it starts unticked for every instance. It is always unticked and greyed out for stopped instances. An instance only picks up plugin changes when it restarts, and only instances with at least one ticked file are restarted.
- **Update Selected** stays off until QLSM has read the **Defer restarts** setting, so the ticks you see are the ones that will be sent.

Click **Update Selected** to apply your choices.

## When Changes Take Effect

- **Instance files** take effect when the instance restarts. If you leave **restart to apply** unticked on a running instance, QLSM syncs the files to the host right away and the instance shows **Updated** until its next manual or [scheduled restart](auto-restart.md). Click the **Updated** badge to see the pending plugin files with a diff, and **Restart now** to apply them (see [Pending changes](edit-configs.md#pending-changes)). If the instance is busy with another operation, the files stay staged in QLSM and apply on its next restart.
- **The common plugin pool** refreshes on the host right away, but running instances don't restart for it. Each instance picks up the refreshed pool on its next restart.
- Stopped instances are never restarted. They use the updated files the next time you start them.

## Verification

1. Open [Host Logs](host-logs.md). A successful run logs **Common plugin pool refreshed.** and a **staged** line for each instance that received files.
2. If you restarted instances, wait for them to return to **Running**.
3. Run **Check for Updates** again. The files you updated should no longer be listed.

## Presets

A preset keeps its own copies of the plugins it was saved with, and every new instance created from it gets those copies. Check them the same way:

1. Open **Settings > Presets**.
2. Click **Plugin Updates** on a preset card. The button shows a count when some of the preset's plugins differ from the version QLSM has in its plugin pool. **Plugins & Updates** on the preset's edit page opens the same window.
3. The window lists every plugin file in the preset: **update available**, **up to date**, or **not in plugin pool** (a plugin only this preset has; it is never touched).
   A plugin that keeps helper modules in a folder of its own (for example `match_restore.py` with `restore/`) also lists the changed helper files, marked **helper file**. They are ticked with the rest, so a refreshed plugin never ends up next to an old helper.
4. Tick the files to refresh and click **Update Selected**. The preset's copies are replaced right away, including any edits you made to them. Existing instances are not changed; use the host check above for those.

Built-in presets are updated with QLSM releases and have no **Plugin Updates** button.

## If Something Goes Wrong

- **"Common pool check failed"** in the modal means QLSM couldn't read the host's plugin pool, usually because the host is unreachable. The per-instance results are still accurate, because QLSM reads those locally.
- If refreshing the common plugin pool fails, the host goes to **Error** and no instance files are changed. Check [Host Logs](host-logs.md) for the reason.

## Related Pages

- [Host Actions Menu](host-actions-menu.md)
- [Edit Configs, Plugins, Factories, And Hooks](edit-configs.md)
- [Configure Auto-Restart](auto-restart.md)
- [Host Logs](host-logs.md)
