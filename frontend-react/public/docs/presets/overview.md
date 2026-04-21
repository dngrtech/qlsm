# Presets And Default Config

## What Loads By Default

Opening **Deploy New Instance** loads config from the `default` preset.

That gives a consistent starting point for:

- `server.cfg`
- `mappool.txt`
- `access.txt`
- `workshop.txt`
- default plugins/factories

## Default Preset Rules

- Treat `default` as read-only baseline.
- Use **Load Preset** for custom templates.
- Use **Save as Preset** or **Save As New** to create your own variants.

## Custom Preset Workflow

1. Load baseline (default or existing preset).
2. Edit config/plugins/factories for your mode.
3. Save as named preset.
4. Reuse that preset on future deployments.

## Instance-Specific Ownership

Preset is only input at deploy time.
After instance creation, each instance keeps its own file set.

- Editing instance config later affects only that instance.
- Preset files are not auto-overwritten by instance edits.

## Related Pages

- [Deploy A New Instance](/docs/getting-started/deploy-new-instance)
- [Instance Actions Menu](/docs/operations/instance-actions-menu)
- [Manage A Running Server](/docs/operations/manage-instance)
