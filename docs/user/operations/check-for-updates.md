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
- **Restart to apply** is ticked for running instances. An instance only picks up plugin changes when it restarts, and only instances with at least one ticked file are restarted.

Click **Update Selected** to apply your choices.

## When Changes Take Effect

- **Instance files** take effect when the instance restarts. If you leave **restart to apply** unticked, they apply on the next manual or [scheduled restart](auto-restart.md).
- **The common plugin pool** refreshes on the host right away, but running instances don't restart for it. Each instance picks up the refreshed pool on its next restart.
- Stopped instances are never restarted. They use the updated files the next time you start them.

## Verification

1. Open [Host Logs](host-logs.md). A successful run logs **Common plugin pool refreshed.** and a **staged** line for each instance that received files.
2. If you restarted instances, wait for them to return to **Running**.
3. Run **Check for Updates** again. The files you updated should no longer be listed.

## If Something Goes Wrong

- **"Common pool check failed"** in the modal means QLSM couldn't read the host's plugin pool, usually because the host is unreachable. The per-instance results are still accurate, because QLSM reads those locally.
- If refreshing the common plugin pool fails, the host goes to **Error** and no instance files are changed. Check [Host Logs](host-logs.md) for the reason.

## Bulk actions: Update plugins

To check every host at once, click **Bulk actions** in the header of the **Servers** page and stay on the **Update plugins** tab. Click **Check for updates** to run the same check as above on every **Active** host, four hosts at a time; nothing is checked until you click it. The results stay while the dialog is open, also when you switch to **Apply preset** and back; **Check again** runs the check anew. Closing the dialog stops the hosts not checked yet and drops the results. Presets are not part of this tab; update them under [Presets](#presets).

- Each host has its own box with the same choices as the single-host window: the **Common plugin pool**, the changed files of each instance, and **Restart to apply** per instance. Everything outdated is ticked at first, and **Restart to apply** starts off for stopped instances and for every instance when **Defer restarts** is on in Settings.
- A host that already matches says **up to date**.
- Click **Update Selected** to send the ticked updates. Up to four hosts are processed at a time.
- Each host reports on its own row. A failure on one row does not stop the others. A host that was sent shows **queued** and is unticked, so a second click does not send it again. Updating a file replaces the copy, including your edits, exactly as in the single-host window; untick files you want to keep.

Verify the result the same way as for a single host, under [Verification](#verification).

## Presets

A preset keeps its own copies of the plugins it was saved with, and every new instance created from it gets those copies. Check them the same way:

1. Open **Settings > Presets**.
2. Click **Plugin Updates** on a preset card. The button shows a count when some of the preset's plugins differ from the version QLSM has in its plugin pool. **Plugins & Updates** on the preset's edit page opens the same window.
3. The window lists every plugin file in the preset: **update available**, **up to date**, or **not in plugin pool** (a plugin only this preset has; it is never touched).
4. Tick the files to refresh and click **Update Selected**. The preset's copies are replaced right away, including any edits you made to them. Existing instances are not changed; use the host check above for those.

Built-in presets are updated with QLSM releases and have no **Plugin Updates** button.

## Related Pages

- [Host Actions Menu](host-actions-menu.md)
- [Edit Configs, Plugins, Factories, And Hooks](edit-configs.md)
- [Configure Auto-Restart](auto-restart.md)
- [Host Logs](host-logs.md)
