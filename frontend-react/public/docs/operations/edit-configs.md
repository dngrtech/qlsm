# Edit Configs, Plugins, And Factories

Use these editors when you are preparing a new instance in the deploy form or updating an existing instance from **Actions** -> **Edit Config**.

Reference: [Deploy A New Instance](/docs/getting-started/deploy-new-instance) and [Instance Actions Menu](/docs/operations/instance-actions-menu)

## Configuration Files

The config editor has file-level tabs for:

- `server.cfg`
- `mappool.txt`
- `access.txt`
- `workshop.txt`

## Editor Buttons

Each file editor includes these controls:

- Upload file content <img src="/docs/images/file-upload-button.png" width="34" style="display:inline; vertical-align:middle; margin-left:6px" />
- Copy content <img src="/docs/images/file-copy-button.png" width="34" style="display:inline; vertical-align:middle; margin-left:6px" />
- Expand to full-screen editor <img src="/docs/images/expand-fulls-screen-button.png" width="34" style="display:inline; vertical-align:middle; margin-left:6px" />

Use **Upload** when you want to paste in an existing file from another server. Use **Copy** when you want to export the current contents. Use **Expand** when you need more room for editing.

## Linting

- `server.cfg` shows inline lint diagnostics.
- In the deploy form, instance creation is blocked if `server.cfg` has blocking lint errors.

## Plugins

The **Plugins** tab manages Python plugins for this instance:

- file tree plus editor
- checkbox selection for which plugins are included
- **Validate** button runs Python validation and reports line-level errors

## Factories

The **Factories** tab controls factory files included in the deployment bundle.

- Only selected factory files are applied to the instance.
- If you edit a factory file here, the edited version is what gets applied.

## Related Pages

- [Deploy A New Instance](/docs/getting-started/deploy-new-instance)
- [Instance Actions Menu](/docs/operations/instance-actions-menu)
- [Presets And Default Config](/docs/presets/overview)
- [99k LAN Rate](/docs/features/99k-lan-rate)
