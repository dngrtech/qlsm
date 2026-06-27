# Preset Download Export Design

## Summary

Add a download/export capability to the existing preset save flow. The feature reuses QLSM's current preset manager as the source of truth: users save an instance configuration as a preset, then download that saved preset as a portable ZIP archive from the same modal.

This deliberately avoids a second, parallel "instance export" system. Two exporters with subtly different file rules would be backup theater and future restore pain.

## Goals

- Let users download a saved preset archive immediately after saving it from the existing `SavePresetModal`.
- Archive the full saved preset directory, not a hand-written short list of files.
- Include every user-managed Configuration Files tab file saved into the preset:
  - root-level `.cfg`, `.txt`, `.ent`
  - one-level custom folder files such as `custom/foo.cfg`, `notes/readme.txt`, `maps/foo.ent`
  - built-in protected files such as `server.cfg`, `mappool.txt`, `access.txt`, `workshop.txt`, `motd.cfg` when present
- Include preset factories, minqlx plugin scripts, user hooks, checked plugin/factory selections, and binary metadata that are already part of the preset representation.
- Keep runtime-only or sensitive instance state out of the export.

## Non-goals

- No direct "download unsaved current editor state" flow in the first version.
- No restore/import flow in this design.
- No export of live host state, logs, instance status, IP address, RCON/ZMQ passwords, database rows, or task queue state.
- No second preset serialization format separate from the on-disk preset folder.

## Existing behavior

### Frontend

`EditInstanceConfigModal.jsx` already supports saving the current edited instance configuration as a preset through `SavePresetModal`.

The save flow builds a `presetData` payload with:

- `configs`: serialized config files from the Configuration Files tab
- `config_folders`: serialized top-level custom config folders
- `factories`: serialized selected factory files
- `checked_factories`
- `draft_id` when plugin/hook draft content exists
- `checked_plugins`
- `binary_meta_source: { context_type: 'instance', context_key: String(instanceId) }`

`useStateAdapter.serialize()` returns all files currently tracked by the file manager, not only the protected built-ins:

```js
{
  files: { ...files },
  folders: [...folders],
}
```

### Backend

`POST /presets/` in `ui/routes/preset_api_routes.py` already writes the preset to disk:

- config files and folders
- factories
- `checked_plugins.json`
- `checked_factories.json`
- scripts from draft workspace
- `user-hooks/` from draft workspace
- binary metadata copied from the requested source

The preset directory is therefore the canonical export source.

## User flow

1. User edits an instance config.
2. User clicks **Save Preset** in the existing modal flow.
3. User enters preset name/description and confirms save.
4. After `createPreset()` succeeds, the modal remains open in a success state.
5. The modal shows **Download Preset**.
6. Clicking **Download Preset** downloads `<preset-name>.zip`.
7. User can close the modal after download or without downloading.

## Backend API

Add:

```http
GET /api/presets/<preset_id>/download
```

Auth:

- protected with `@jwt_required()` like other preset routes.

Success:

- returns a ZIP file via `send_file(...)`
- download name: `<safe-preset-name>.zip`
- MIME type: `application/zip`

Errors:

- `404` if preset id does not exist
- `500` if preset path is missing on disk
- `500` if archive generation fails unexpectedly

## Archive layout

Archive root should contain the preset contents directly plus a generated manifest:

```text
manifest.json
server.cfg
motd.cfg
access.txt
mappool.txt
workshop.txt
<custom-config-folder>/*.cfg
<custom-config-folder>/*.txt
<custom-config-folder>/*.ent
factories/*.factories
scripts/**
user-hooks/**
checked_plugins.json
checked_factories.json
```

Important: the config list above is illustrative, not a whitelist. The implementation must recursively archive the preset directory contents, subject only to safe exclusions. That guarantees user-created files from Configuration Files tab are included.

## Manifest

Add a generated `manifest.json` to the archive. It should not be written back into the preset directory.

Suggested shape:

```json
{
  "type": "qlsm-preset-export",
  "format_version": 1,
  "preset": {
    "id": 123,
    "name": "example",
    "description": "Example preset",
    "is_builtin": false,
    "created_at": "...",
    "last_updated": "..."
  },
  "includes": {
    "preset_directory": true,
    "configs": true,
    "factories": true,
    "scripts": true,
    "user_hooks": true,
    "checked_plugins": true,
    "checked_factories": true,
    "binary_metadata": true
  }
}
```

If binary metadata is not naturally stored as files inside the preset directory, the download endpoint should include it in the manifest or a separate `binary_metadata.json`. The exact placement can be chosen during implementation, but the archive must preserve hook descriptions/metadata needed to understand the exported hooks.

## Archive safety rules

The endpoint must walk only under `preset.path` and write archive names relative to that root.

Exclude generated/editor/runtime junk:

- `__pycache__/`
- `*.pyc`
- `*.pyo`
- `.DS_Store`
- editor swap/temp files such as `*.swp`, `*.tmp`, `*~`

Do not include:

- QLSM SQLite databases
- logs
- host inventory secrets
- RCON/ZMQ passwords
- instance runtime status
- host IP/provider/runtime metadata

## Frontend changes

### API client

Add `downloadPreset(presetId)` to `frontend-react/src/services/api.js`:

- `GET /presets/${presetId}/download`
- `responseType: 'blob'`

### SavePresetModal behavior

Extend `SavePresetModal` so it can display a post-save success state with a **Download Preset** button.

The parent remains responsible for saving. After `createPreset()` succeeds, `EditInstanceConfigModal` should retain the returned preset id/name and pass them to the modal.

Minimal state in parent:

- `savedPresetForDownload: null | { id, name }`

On save success:

- do not close the modal immediately
- set `savedPresetForDownload`
- show success notification as today

On modal close/open reset:

- clear `savedPresetForDownload`

Download button:

- calls `downloadPreset(savedPresetForDownload.id)`
- creates object URL
- uses `<a download>` with `<preset-name>.zip`
- revokes URL after click

## Tests

Backend tests:

- `GET /presets/<id>/download` returns a ZIP for an existing preset.
- ZIP contains all root config files.
- ZIP contains custom config files in custom top-level folders.
- ZIP contains `factories/`, `scripts/`, `user-hooks/` when present.
- ZIP contains `checked_plugins.json` and `checked_factories.json` when present.
- ZIP contains generated `manifest.json`.
- ZIP excludes `__pycache__` and `.pyc` files.
- Missing preset returns `404`.
- Missing preset directory returns error.

Frontend tests:

- Saving a preset from edit mode leaves the save modal open in success/download state.
- Download button calls `downloadPreset` with the returned preset id.
- Existing save payload still includes all serialized config files/folders, factories, checked plugins, and draft id.

## Acceptance criteria

- A user can save a preset from an instance and immediately download it from the same modal.
- The downloaded ZIP includes every file saved in the preset directory, including user-created config files from Configuration Files tab.
- No sensitive runtime-only instance values are exported.
- Existing save/load preset behavior remains unchanged.
- Tests prove custom config files are not dropped.
