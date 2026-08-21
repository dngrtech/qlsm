# Deployment Troubleshooting

Use this page when a new instance does not become playable or stable.


If something isn't working, start by clicking "Re-run host setup" from the [host actions menu](../operations/host-actions-menu.md). If the issue persists, restart the instance. 


## Problem: Instance stuck in deploying/restarting/configuring

1. Wait a bit and refresh.
2. Open **View Server Logs**: [Use Logs And Chat Logs](../operations/logs-and-chat.md)
3. Check for clear error lines.
4. Retry once only after reading logs.

## Problem: RCON button is disabled

- Instance is not fully ready yet.
- Check action availability rules: [Instance Actions Menu](../operations/instance-actions-menu.md)
- Wait for healthy status, then try again.

## Problem: You changed config but game behavior did not change

- Confirm you saved changes.
- Restart instance.
- Re-check with logs/live status: [Use Logs And Chat Logs](../operations/logs-and-chat.md)

## Problem: Workshop item updated in Steam, but server still runs old content

- Use host **Actions** -> **Update Workshop Item** and provide numeric item ID: [Update Workshop Item](../operations/update-workshop-item.md)
- Restart affected instances (manual or from the workshop update modal).
- Configure scheduled host restart to keep updates consistent: [Configure Auto-Restart](../operations/auto-restart.md)

## Problem: A minqlxtended host fails setup and lands in Error

minqlxtended is compiled on the host itself and links against Python 3.12, so the machine's
distribution must already provide it. **Host setup does not install a Python version** — it
installs the distribution's own `python3`, whatever that happens to be — so a machine below the
floor cannot be rescued by re-running setup. Setup checks the version first and stops before
changing anything.

Where you find out depends on the provider:

- **Cloud hosts** — cannot hit this. QLSM provisions Ubuntu 24.04 for the minqlxtended runtime.
- **Standalone hosts** — the Add Host form checks the detected version and refuses the
  submission with an explanation, so the host is never created. An *undetectable* version is
  also refused, deliberately: the runtime choice cannot be undone later.
- **Self hosts** — there is no pre-check. The host record is created, setup fails on the version
  check, and the host lands in **Error**.

The fix is the distribution, not the package: Debian 12 has no `python3.12` in its archive, so
installing one by hand is a dead end. Use **Ubuntu 24.04 or newer**, or create the host with the
**minqlx** runtime, which has no version floor. Because the runtime is permanent, an Error host
here has to be deleted and recreated. See [Server Runtime](../getting-started/add-host.md#server-runtime).

## Problem: Self-host stuck in REBOOTING state

- QLSM auto-recovers this state on container startup — no manual action is needed.
- If the host is still REBOOTING after QLSM restarts, check that the underlying machine finished booting and is reachable over SSH.

## Problem: Auto-restart runs at the wrong local time

- Auto-restart follows host local timezone.
- For standalone hosts, this is the timezone set when host was added.
- Verify timezone in host details before trusting schedule time.

See: [Configure Auto-Restart](../operations/auto-restart.md)

## Related Pages

- [Host Actions Menu](../operations/host-actions-menu.md)
- [Instance Actions Menu](../operations/instance-actions-menu.md)
- [Deploy A New Instance](../getting-started/deploy-new-instance.md)