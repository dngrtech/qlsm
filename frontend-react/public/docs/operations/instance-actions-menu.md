# Instance Actions Menu

Open from instance row **Actions** in the Servers page.

![Instance Actions Menu](/docs/images/instance-actions-menu-general.png)

## Actions In This Menu

- **Edit Config**
- **RCON Console**
- **View Server Logs**
- **View Chat Logs**
- **View Details**
- **99k LAN Rate**
- **Restart**
- **Start / Stop**
- **Delete**

## Visual Reference By Action

### Edit Config

![Instance Actions: Edit Config](/docs/images/instance-actions-menu-edit-config.png)
![Instance Edit Config Modal](/docs/images/instance-edit-config.png)

### RCON Console

![Instance Actions: RCON](/docs/images/instance-actions-menu-rcon.png)

### View Server Logs

![Instance Actions: View Server Logs](/docs/images/instance-actions-menu-view-server-logs.png)

### View Chat Logs

![Instance Actions: View Chat Logs](/docs/images/instance-actions-menu-view-chat-logs.png)

### View Details

![Instance Actions: View Details](/docs/images/instance-actions-menu-view-details.png)

## 99k LAN Rate

`99k LAN Rate` is a per-instance setting.

- **On**: high LAN-rate profile.
- **Off**: standard profile.
- Changing it triggers reconfigure/restart flow.

![Instance Actions: 99k LAN Rate](/docs/images/instance-actions-menu-99k-lan-rate.png)

## Edit Config Scope

Config edits from this menu are instance-local.
Changes do not modify other instances and do not modify default preset files.

## File Upload In Edit Config

Each config tab (server.cfg, mappool.txt, access.txt, workshop.txt) has an **Upload** button. Use it to drop in a file from your machine instead of typing or pasting.

You can also upload:

- **Plugin files** — `.py` files for custom minqlx plugins, uploaded via the Plugins tab
- **Factory files** — `.factories` files, uploaded via the Factories tab
- **Plugin binaries** — `.so` shared library files for native minqlx extensions

This makes it easy to migrate an existing server setup: if you already have a working config and plugin pack, upload everything through the UI rather than manually copying files over SSH.

## Related Pages

- [Deploy A New Instance](/docs/getting-started/deploy-new-instance)
- [Presets And Default Config](/docs/presets/overview)
- [Use Logs And Chat Logs](/docs/operations/logs-and-chat)
- [RCON Basics](/docs/operations/rcon-basics)
- [Deployment Troubleshooting](/docs/help/deployment-troubleshooting)
