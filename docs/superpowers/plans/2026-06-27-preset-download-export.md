# Preset Download Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Download Preset ZIP action to the existing Save Preset modal after a preset is successfully saved.

**Architecture:** Reuse the existing preset save flow as the only serialization path. The backend adds a focused ZIP export helper and `GET /api/presets/<id>/download`; the frontend adds an API client helper and post-save download state in the existing modal. The archive walks the saved preset directory recursively so user-created Configuration Files tab files are included instead of relying on a brittle whitelist.

**Tech Stack:** Flask, SQLAlchemy, Flask-JWT-Extended, Python stdlib `zipfile`, React, Vite/Vitest, Axios, Testing Library.

---

## Decision Checkpoints

No unresolved user-visible semantics forks remain.

Approved decisions:

- Download happens after Save Preset succeeds, from the existing modal.
- The archive source is the saved preset directory.
- The archive includes all files in the preset directory except explicit junk exclusions.
- No direct unsaved-state export in this version.
- No restore/import flow in this version.
- No runtime-only secrets/state in the archive.

Implementation can proceed autonomously through all tasks.

## File Structure

Modify:

- `ui/routes/preset_api_routes.py` — add ZIP export helper functions and `GET /<preset_id>/download` route near existing preset routes.
- `tests/test_preset_download_routes.py` — new backend route tests for archive content, manifest, exclusions, and errors.
- `frontend-react/src/services/api.js` — add `downloadPreset(presetId)` returning a Blob.
- `frontend-react/src/components/addInstance/SavePresetModal.jsx` — add optional post-save download state UI and button callback props.
- `frontend-react/src/components/instances/EditInstanceConfigModal.jsx` — keep the modal open after save, store returned preset id/name, wire download action.
- `frontend-react/src/components/instances/__tests__/EditInstanceConfigModal.test.jsx` — update mocks and add modal/download wiring tests.
- `docs/api_reference.md` — document the new preset download endpoint if this file is tracked in the repo.
- `docs/user/releases.md`, `docs/user/version.json`, `VERSION` — bump release metadata in the implementation PR, per repo policy.

Do not start/restart dev servers. Run tests only.

---

### Task 1: Backend failing tests for preset ZIP export

**Files:**

- Create: `tests/test_preset_download_routes.py`
- Modify: none
- Test: `tests/test_preset_download_routes.py`

- [ ] **Step 1: Write failing backend tests**

Create `tests/test_preset_download_routes.py` with this content:

```python
import io
import json
import os
import zipfile

from flask_jwt_extended import create_access_token

from ui import db
from ui.models import BinaryMetadata, ConfigPreset


def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity='tester')
    return {'Authorization': f'Bearer {token}'}


def write_file(path, content, mode='w'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as handle:
        handle.write(content)


def create_preset(app, tmp_path, name='export-me'):
    preset_dir = tmp_path / 'configs' / 'presets' / name
    write_file(preset_dir / 'server.cfg', 'set sv_hostname "Export Me"\n')
    write_file(preset_dir / 'motd.cfg', 'hello\n')
    write_file(preset_dir / 'notes' / 'readme.txt', 'custom note\n')
    write_file(preset_dir / 'maps' / 'arena.ent', '{ entities }\n')
    write_file(preset_dir / 'factories' / 'ca.factories', '{"factory": true}\n')
    write_file(preset_dir / 'scripts' / 'discord_extensions' / 'balance.py', 'class balance: pass\n')
    write_file(preset_dir / 'scripts' / 'requirements.txt', 'redis==5.0.0\n')
    write_file(preset_dir / 'user-hooks' / 'force_rate.so', b'\x7fELFfake', mode='wb')
    write_file(preset_dir / 'checked_plugins.json', json.dumps(['discord_extensions/balance.py']))
    write_file(preset_dir / 'checked_factories.json', json.dumps(['ca.factories']))
    write_file(preset_dir / 'scripts' / '__pycache__' / 'balance.cpython-311.pyc', b'junk', mode='wb')
    write_file(preset_dir / 'scripts' / 'temp.tmp', 'junk\n')

    with app.app_context():
        preset = ConfigPreset(
            name=name,
            description='Export test preset',
            path=str(preset_dir),
            is_builtin=False,
        )
        db.session.add(preset)
        db.session.commit()
        preset_id = preset.id
    return preset_id, preset_dir


def read_zip(response):
    return zipfile.ZipFile(io.BytesIO(response.data))


def test_download_preset_returns_zip_with_full_preset_directory(client, app, tmp_path):
    preset_id, _preset_dir = create_preset(app, tmp_path)

    response = client.get(
        f'/api/presets/{preset_id}/download',
        headers=auth_headers(app),
    )

    assert response.status_code == 200
    assert response.mimetype == 'application/zip'
    assert 'attachment;' in response.headers['Content-Disposition']
    assert 'export-me.zip' in response.headers['Content-Disposition']

    with read_zip(response) as archive:
        names = set(archive.namelist())
        assert 'manifest.json' in names
        assert 'server.cfg' in names
        assert 'motd.cfg' in names
        assert 'notes/readme.txt' in names
        assert 'maps/arena.ent' in names
        assert 'factories/ca.factories' in names
        assert 'scripts/discord_extensions/balance.py' in names
        assert 'scripts/requirements.txt' in names
        assert 'user-hooks/force_rate.so' in names
        assert 'checked_plugins.json' in names
        assert 'checked_factories.json' in names
        assert 'scripts/__pycache__/balance.cpython-311.pyc' not in names
        assert 'scripts/temp.tmp' not in names

        manifest = json.loads(archive.read('manifest.json').decode('utf-8'))
        assert manifest['type'] == 'qlsm-preset-export'
        assert manifest['format_version'] == 1
        assert manifest['preset']['id'] == preset_id
        assert manifest['preset']['name'] == 'export-me'
        assert manifest['preset']['description'] == 'Export test preset'
        assert manifest['includes']['preset_directory'] is True
        assert manifest['includes']['configs'] is True
        assert manifest['includes']['factories'] is True
        assert manifest['includes']['scripts'] is True
        assert manifest['includes']['user_hooks'] is True
        assert manifest['includes']['checked_plugins'] is True
        assert manifest['includes']['checked_factories'] is True


def test_download_preset_includes_binary_metadata_json(client, app, tmp_path):
    preset_id, _preset_dir = create_preset(app, tmp_path, name='hook-meta')
    with app.app_context():
        db.session.add(BinaryMetadata(
            context_type='preset',
            context_key='hook-meta',
            file_path='force_rate.so',
            description='99k LAN rate hook',
        ))
        db.session.commit()

    response = client.get(
        f'/api/presets/{preset_id}/download',
        headers=auth_headers(app),
    )

    assert response.status_code == 200
    with read_zip(response) as archive:
        metadata = json.loads(archive.read('binary_metadata.json').decode('utf-8'))
        assert metadata == [
            {
                'file_path': 'force_rate.so',
                'description': '99k LAN rate hook',
            }
        ]


def test_download_missing_preset_returns_404(client, app):
    response = client.get('/api/presets/9999/download', headers=auth_headers(app))

    assert response.status_code == 404
    assert response.get_json()['error']['message'] == 'Preset not found.'


def test_download_preset_missing_directory_returns_500(client, app, tmp_path):
    missing_path = tmp_path / 'missing-preset-dir'
    with app.app_context():
        preset = ConfigPreset(
            name='missing-dir',
            description='Missing dir',
            path=str(missing_path),
            is_builtin=False,
        )
        db.session.add(preset)
        db.session.commit()
        preset_id = preset.id

    response = client.get(
        f'/api/presets/{preset_id}/download',
        headers=auth_headers(app),
    )

    assert response.status_code == 500
    assert response.get_json()['error']['message'] == 'Preset configuration files not found.'
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_preset_download_routes.py -v
```

Expected: tests fail with `404 NOT FOUND` for `/api/presets/<id>/download` or missing implementation errors. If auth setup fails instead, fix the test auth helper before touching production code.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_preset_download_routes.py
git commit -m "test: cover preset download export route"
```

---

### Task 2: Implement backend ZIP export route

**Files:**

- Modify: `ui/routes/preset_api_routes.py`
- Test: `tests/test_preset_download_routes.py`

- [ ] **Step 1: Add imports**

In `ui/routes/preset_api_routes.py`, replace the current top imports:

```python
import json
import os
import shutil
from flask import Blueprint, request, jsonify, current_app
```

with:

```python
import fnmatch
import io
import json
import os
import shutil
import zipfile
from flask import Blueprint, request, jsonify, current_app, send_file
```

- [ ] **Step 2: Add archive helper constants and functions**

In `ui/routes/preset_api_routes.py`, after `MAX_CONFIG_PATH_DEPTH = 2`, add:

```python
EXPORT_FORMAT_VERSION = 1
EXPORT_EXCLUDED_DIRS = {'__pycache__'}
EXPORT_EXCLUDED_FILES = {'.DS_Store'}
EXPORT_EXCLUDED_PATTERNS = ('*.pyc', '*.pyo', '*.swp', '*.tmp', '*~')


def _should_skip_export_path(relative_path, is_dir=False):
    """Return True for generated/editor junk that should not enter exports."""
    parts = relative_path.replace(os.sep, '/').split('/')
    if any(part in EXPORT_EXCLUDED_DIRS for part in parts):
        return True
    name = parts[-1]
    if is_dir:
        return name in EXPORT_EXCLUDED_DIRS
    if name in EXPORT_EXCLUDED_FILES:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXPORT_EXCLUDED_PATTERNS)


def _preset_export_manifest(preset):
    return {
        'type': 'qlsm-preset-export',
        'format_version': EXPORT_FORMAT_VERSION,
        'preset': {
            'id': preset.id,
            'name': preset.name,
            'description': preset.description,
            'is_builtin': bool(preset.is_builtin),
            'created_at': preset.created_at.isoformat() if preset.created_at else None,
            'last_updated': preset.last_updated.isoformat() if preset.last_updated else None,
        },
        'includes': {
            'preset_directory': True,
            'configs': True,
            'factories': True,
            'scripts': True,
            'user_hooks': True,
            'checked_plugins': True,
            'checked_factories': True,
            'binary_metadata': True,
        },
    }


def _preset_binary_metadata_export(preset_name):
    rows = BinaryMetadata.query.filter_by(
        context_type='preset',
        context_key=preset_name,
    ).order_by(BinaryMetadata.file_path.asc()).all()
    return [
        {
            'file_path': row.file_path,
            'description': row.description or '',
        }
        for row in rows
    ]


def _build_preset_export_zip(preset):
    """Build an in-memory ZIP containing preset.path plus export metadata."""
    root = os.path.abspath(preset.path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            'manifest.json',
            json.dumps(_preset_export_manifest(preset), indent=2, sort_keys=True) + '\n',
        )
        binary_metadata = _preset_binary_metadata_export(preset.name)
        archive.writestr(
            'binary_metadata.json',
            json.dumps(binary_metadata, indent=2, sort_keys=True) + '\n',
        )

        for current_root, dirs, files in os.walk(root):
            dirs[:] = [
                dirname for dirname in dirs
                if not _should_skip_export_path(
                    os.path.relpath(os.path.join(current_root, dirname), root),
                    is_dir=True,
                )
            ]
            for filename in sorted(files):
                full_path = os.path.abspath(os.path.join(current_root, filename))
                rel_path = os.path.relpath(full_path, root).replace(os.sep, '/')
                if not full_path.startswith(root + os.sep) and full_path != root:
                    current_app.logger.warning(
                        'Skipping preset export path outside root: %s', full_path
                    )
                    continue
                if _should_skip_export_path(rel_path):
                    continue
                if rel_path in {'manifest.json', 'binary_metadata.json'}:
                    continue
                archive.write(full_path, rel_path)

    buffer.seek(0)
    return buffer
```

- [ ] **Step 3: Add route**

In `ui/routes/preset_api_routes.py`, after `get_preset_api()` and before `update_preset_api()`, add:

```python
@preset_api_bp.route('/<int:preset_id>/download', methods=['GET'], endpoint='download_preset_api')
@jwt_required()
def download_preset_api(preset_id):
    """Download a saved preset directory as a portable ZIP archive."""
    preset = get_preset(preset_id)
    if not preset:
        return jsonify({"error": {"message": "Preset not found."}}), 404

    if not os.path.isdir(preset.path):
        current_app.logger.error(
            "Preset folder missing for preset %s: %s", preset_id, preset.path
        )
        return jsonify({"error": {"message": "Preset configuration files not found."}}), 500

    try:
        archive = _build_preset_export_zip(preset)
        return send_file(
            archive,
            as_attachment=True,
            download_name=f'{preset.name}.zip',
            mimetype='application/zip',
        )
    except Exception as e:
        current_app.logger.error(
            "Error exporting preset %s: %s", preset_id, e, exc_info=True
        )
        return jsonify({"error": {"message": f"Error exporting preset: {str(e)}"}}), 500
```

- [ ] **Step 4: Run backend tests**

Run:

```bash
pytest tests/test_preset_download_routes.py -v
```

Expected: all tests in `tests/test_preset_download_routes.py` pass.

- [ ] **Step 5: Run existing preset-related backend tests**

Run:

```bash
pytest tests/test_builtin_presets_cli.py tests/test_instance_hooks_routes.py tests/test_instance_hooks_files.py -v
```

Expected: all selected tests pass. If unrelated pre-existing failures appear, capture exact output before changing anything.

- [ ] **Step 6: Commit backend implementation**

```bash
git add ui/routes/preset_api_routes.py tests/test_preset_download_routes.py
git commit -m "feat: add preset download export route"
```

---

### Task 3: Frontend API client helper

**Files:**

- Modify: `frontend-react/src/services/api.js`
- Test: covered by component tests in later task

- [ ] **Step 1: Add `downloadPreset` helper**

In `frontend-react/src/services/api.js`, after `deletePreset` and before `validatePresetName`, add:

```js
export const downloadPreset = async (presetId) => {
  try {
    const response = await apiClient.get(`/presets/${presetId}/download`, {
      responseType: 'blob',
    });
    return response.data;
  } catch (error) {
    console.error(`Failed to download preset ${presetId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to download preset');
  }
};
```

- [ ] **Step 2: Commit API helper**

```bash
git add frontend-react/src/services/api.js
git commit -m "feat: add preset download api client"
```

---

### Task 4: SavePresetModal download state

**Files:**

- Modify: `frontend-react/src/components/addInstance/SavePresetModal.jsx`
- Test: `frontend-react/src/components/instances/__tests__/EditInstanceConfigModal.test.jsx`

- [ ] **Step 1: Extend modal props**

In `SavePresetModal.jsx`, change the function signature from:

```js
function SavePresetModal({
  isOpen,
  onClose,
  onSave,
  isSaving = false,
  zIndexClass = 'z-50',
  initialDescription = ''
}) {
```

to:

```js
function SavePresetModal({
  isOpen,
  onClose,
  onSave,
  isSaving = false,
  zIndexClass = 'z-50',
  initialDescription = '',
  savedPreset = null,
  onDownload = null,
  isDownloading = false,
}) {
```

- [ ] **Step 2: Keep existing reset behavior for form fields**

Leave the existing `useEffect` reset in place:

```js
useEffect(() => {
  if (isOpen) {
    setPresetName('');
    setDescription(initialDescription || '');
    setValidationError(null);
    setIsValidating(false);
  }
}, [isOpen, initialDescription]);
```

Do not reset `savedPreset` inside this modal; parent owns that state.

- [ ] **Step 3: Add success/download panel above the form fields**

In the JSX, immediately after `</Dialog.Title>` and before the current `<div className="relative z-10 mt-4">` containing the `Preset Name` label, insert:

```jsx
                {savedPreset && (
                  <div className="relative z-10 mb-4 rounded border border-[var(--accent-success)]/40 bg-[var(--accent-success)]/10 p-3 text-sm text-[var(--text-primary)]">
                    <div className="font-semibold">Preset saved: {savedPreset.name}</div>
                    <div className="mt-1 text-[var(--text-secondary)]">
                      You can download the saved preset archive now, or close this dialog.
                    </div>
                    <button
                      type="button"
                      onClick={() => onDownload?.(savedPreset)}
                      disabled={isDownloading || !onDownload}
                      className="btn btn-secondary mt-3"
                    >
                      {isDownloading ? (
                        <LoaderCircle className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4 mr-2" />
                      )}
                      {isDownloading ? 'Downloading...' : 'Download Preset'}
                    </button>
                  </div>
                )}
```

- [ ] **Step 4: Disable duplicate save after success**

Change:

```js
const isSubmitDisabled = isSaving || isValidating || !presetName.trim() || !!validateNameLocally(presetName);
```

to:

```js
const isSubmitDisabled = Boolean(savedPreset) || isSaving || isValidating || !presetName.trim() || !!validateNameLocally(presetName);
```

- [ ] **Step 5: Commit modal UI changes**

```bash
git add frontend-react/src/components/addInstance/SavePresetModal.jsx
git commit -m "feat: show preset download action after save"
```

---

### Task 5: Wire download behavior in EditInstanceConfigModal

**Files:**

- Modify: `frontend-react/src/components/instances/EditInstanceConfigModal.jsx`
- Test: `frontend-react/src/components/instances/__tests__/EditInstanceConfigModal.test.jsx`

- [ ] **Step 1: Import `downloadPreset`**

Change the import from `../../services/api` in `EditInstanceConfigModal.jsx` from:

```js
import { getInstanceConfig, updateInstanceConfig, getInstanceById, getPresets, getPresetById, createPreset, getFactoryTree, getFactoryContent } from '../../services/api';
```

to:

```js
import { getInstanceConfig, updateInstanceConfig, getInstanceById, getPresets, getPresetById, createPreset, downloadPreset, getFactoryTree, getFactoryContent } from '../../services/api';
```

- [ ] **Step 2: Add state**

After:

```js
const [isSavePresetModalOpen, setIsSavePresetModalOpen] = useState(false);
const [isSavingPreset, setIsSavingPreset] = useState(false);
```

add:

```js
const [savedPresetForDownload, setSavedPresetForDownload] = useState(null);
const [isDownloadingPreset, setIsDownloadingPreset] = useState(false);
```

- [ ] **Step 3: Update save success behavior**

In `handleSavePreset`, replace:

```js
const response = await createPreset(presetData);

// Update presets list
const updatedPresets = await getPresets();
setPresets(updatedPresets || []);

setIsSavePresetModalOpen(false);
showSuccess(response.message || `Preset "${name}" saved successfully.`);
```

with:

```js
const response = await createPreset(presetData);
const savedPreset = response.data;

// Update presets list
const updatedPresets = await getPresets();
setPresets(updatedPresets || []);

setSavedPresetForDownload({
  id: savedPreset.id,
  name: savedPreset.name || name.trim(),
});
showSuccess(response.message || `Preset "${name}" saved successfully.`);
```

This intentionally keeps the modal open.

- [ ] **Step 4: Add modal close helper**

Before the `return (` in `EditInstanceConfigModal.jsx`, add:

```js
const handleSavePresetModalClose = useCallback(() => {
  setIsSavePresetModalOpen(false);
  setSavedPresetForDownload(null);
  setPresetError(null);
}, []);
```

- [ ] **Step 5: Add archive download helper**

Before the `return (` in `EditInstanceConfigModal.jsx`, add:

```js
const handleDownloadSavedPreset = useCallback(async (preset) => {
  if (!preset?.id) return;
  setIsDownloadingPreset(true);
  try {
    const blob = await downloadPreset(preset.id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${preset.name || 'preset'}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    const message = err.error?.message || err.message || 'Failed to download preset.';
    setPresetError(message);
    showError(message);
  } finally {
    setIsDownloadingPreset(false);
  }
}, [showError]);
```

- [ ] **Step 6: Reset saved download state when opening save modal**

Replace the Save Preset button handler:

```jsx
<button type="button" onClick={() => setIsSavePresetModalOpen(true)} className="btn btn-secondary">
```

with:

```jsx
<button
  type="button"
  onClick={() => {
    setSavedPresetForDownload(null);
    setPresetError(null);
    setIsSavePresetModalOpen(true);
  }}
  className="btn btn-secondary"
>
```

- [ ] **Step 7: Pass props to SavePresetModal**

Replace:

```jsx
<SavePresetModal
  isOpen={isSavePresetModalOpen}
  onClose={() => setIsSavePresetModalOpen(false)}
  onSave={handleSavePreset}
  isSaving={isSavingPreset}
/>
```

with:

```jsx
<SavePresetModal
  isOpen={isSavePresetModalOpen}
  onClose={handleSavePresetModalClose}
  onSave={handleSavePreset}
  isSaving={isSavingPreset}
  savedPreset={savedPresetForDownload}
  onDownload={handleDownloadSavedPreset}
  isDownloading={isDownloadingPreset}
/>
```

- [ ] **Step 8: Commit wiring**

```bash
git add frontend-react/src/components/instances/EditInstanceConfigModal.jsx
git commit -m "feat: wire preset download from edit modal"
```

---

### Task 6: Frontend tests for save/download modal flow

**Files:**

- Modify: `frontend-react/src/components/instances/__tests__/EditInstanceConfigModal.test.jsx`
- Test: same file

- [ ] **Step 1: Add `downloadPreset` mock**

In the hoisted `mocks` object, after `createPreset: vi.fn(),`, add:

```js
downloadPreset: vi.fn(),
```

In the `vi.mock('../../../services/api', ...)` block, after `createPreset: mocks.createPreset,`, add:

```js
downloadPreset: mocks.downloadPreset,
```

- [ ] **Step 2: Replace mocked SavePresetModal to expose download props**

Replace the existing mocked `SavePresetModal` block:

```js
vi.mock('../../addInstance/SavePresetModal', () => ({
  default: ({ isOpen, onSave }) => (
    isOpen ? (
      <button
        type="button"
        onClick={() => onSave({ name: 'saved-from-edit', description: 'copy' })}
      >
        Confirm Save Preset
      </button>
    ) : null
  ),
}));
```

with:

```js
vi.mock('../../addInstance/SavePresetModal', () => ({
  default: ({ isOpen, onSave, savedPreset, onDownload }) => (
    isOpen ? (
      <div>
        <button
          type="button"
          onClick={() => onSave({ name: 'saved-from-edit', description: 'copy' })}
        >
          Confirm Save Preset
        </button>
        {savedPreset && (
          <button
            type="button"
            onClick={() => onDownload(savedPreset)}
          >
            Download Preset
          </button>
        )}
      </div>
    ) : null
  ),
}));
```

- [ ] **Step 3: Reset new mock defaults in `beforeEach`**

In `beforeEach`, after:

```js
mocks.createPreset.mockResolvedValue({ message: 'saved' });
```

replace it with:

```js
mocks.createPreset.mockResolvedValue({
  message: 'saved',
  data: { id: 42, name: 'saved-from-edit' },
});
mocks.downloadPreset.mockResolvedValue(new Blob(['zip-bytes'], { type: 'application/zip' }));
```

If `beforeEach` still needs a plain `message` for older tests, this response shape remains compatible because existing code reads `response.message`.

- [ ] **Step 4: Stub object URL and anchor click**

Inside the same `beforeEach`, add:

```js
global.URL.createObjectURL = vi.fn(() => 'blob:qlsm-preset');
global.URL.revokeObjectURL = vi.fn();
vi.spyOn(document.body, 'appendChild');
```

Do not assert on `appendChild` globally unless a test needs it.

- [ ] **Step 5: Add test for download after save**

Add this test after `preserves checked plugin file paths when saving a preset from edit mode`:

```jsx
it('keeps save preset modal open and downloads the saved preset archive', async () => {
  render(
    <EditInstanceConfigModal
      isOpen={true}
      onClose={vi.fn()}
      instanceId={1}
      instanceName="Test123"
      onConfigSaved={vi.fn()}
    />
  );

  await waitFor(() => expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
  fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

  await waitFor(() => expect(mocks.createPreset).toHaveBeenCalledTimes(1));
  expect(await screen.findByRole('button', { name: /download preset/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /download preset/i }));

  await waitFor(() => expect(mocks.downloadPreset).toHaveBeenCalledWith(42));
  expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:qlsm-preset');
});
```

- [ ] **Step 6: Run frontend test file**

Run:

```bash
cd frontend-react && pnpm test -- src/components/instances/__tests__/EditInstanceConfigModal.test.jsx --runInBand
```

If Vitest rejects `--runInBand`, run:

```bash
cd frontend-react && pnpm test -- src/components/instances/__tests__/EditInstanceConfigModal.test.jsx
```

Expected: all tests in the file pass.

- [ ] **Step 7: Commit frontend tests**

```bash
git add frontend-react/src/components/instances/__tests__/EditInstanceConfigModal.test.jsx
git commit -m "test: cover preset download from save modal"
```

---

### Task 7: Integration test run and docs/version updates

**Files:**

- Modify: `docs/api_reference.md`
- Modify: `docs/user/releases.md`
- Modify: `docs/user/version.json`
- Modify: `VERSION`

- [ ] **Step 1: Document API endpoint**

In `docs/api_reference.md`, add this endpoint under the preset endpoints section:

```markdown
### Download Preset Export

`GET /api/presets/{preset_id}/download`

Downloads the saved preset as a ZIP archive. The archive contains the full saved preset directory, including configuration files, custom config folders, factories, scripts, user hooks, checked selection JSON files, and generated export metadata.

Responses:

- `200 OK` — `application/zip` attachment named `<preset-name>.zip`
- `404 Not Found` — preset id does not exist
- `500 Internal Server Error` — preset directory is missing or archive generation failed
```

- [ ] **Step 2: Bump version files together**

Read the current version:

```bash
cat VERSION
```

If current version is `1.12.13`, set the next patch version to `1.12.14`.

Update `VERSION` to:

```text
1.12.14
```

Update `docs/user/version.json` so the version field is `1.12.14`. Preserve the existing JSON shape.

Add a top row to `docs/user/releases.md`:

```markdown
| `v1.12.14` | 2026-06-27 | — | Add preset ZIP export from the existing Save Preset flow. After saving a preset from an instance, the modal offers Download Preset; the archive includes the full saved preset directory, including custom config files, factories, scripts, user hooks, checked selections, and export metadata. |
```

- [ ] **Step 3: Run backend and frontend focused tests**

Run:

```bash
pytest tests/test_preset_download_routes.py tests/test_builtin_presets_cli.py tests/test_instance_hooks_routes.py tests/test_instance_hooks_files.py -v
```

Run:

```bash
cd frontend-react && pnpm test -- src/components/instances/__tests__/EditInstanceConfigModal.test.jsx src/components/addInstance/__tests__/AddInstanceForm.test.jsx
```

Expected: all selected backend and frontend tests pass.

- [ ] **Step 4: Run lint if package scripts support it**

Run:

```bash
cd frontend-react && pnpm lint
```

Expected: lint passes. If lint reports unrelated pre-existing issues, record the exact output and do not broaden the scope without user approval.

- [ ] **Step 5: Commit docs/version updates**

```bash
git add docs/api_reference.md docs/user/releases.md docs/user/version.json VERSION
git commit -m "docs: document preset download export"
```

---

### Task 8: Final verification and PR preparation

**Files:**

- Modify: none unless tests expose a real bug
- Test: full focused suite

- [ ] **Step 1: Inspect git history and diff**

Run:

```bash
git status --short
git log --oneline --decorate -8
git diff origin/main...HEAD --stat
```

Expected: working tree clean after all commits; diff only includes planned files.

- [ ] **Step 2: Run final focused verification**

Run:

```bash
pytest tests/test_preset_download_routes.py -v
```

Run:

```bash
cd frontend-react && pnpm test -- src/components/instances/__tests__/EditInstanceConfigModal.test.jsx
```

Expected: both pass.

- [ ] **Step 3: Create PR, do not merge**

Use the repo's GitHub workflow. Do not merge without explicit user approval.

```bash
gh pr create \
  --title "Add preset download export" \
  --body "Adds Download Preset ZIP export to the existing Save Preset modal after save. The backend exports the full saved preset directory with manifest metadata, preserving custom config files, factories, scripts, user hooks, and checked selections."
```

Expected: command returns a PR URL.

- [ ] **Step 4: Report results**

Report:

- PR URL
- tests run and pass/fail status
- final branch name
- any known limitations: no import/restore flow, no unsaved-state export

Stop and wait for explicit merge approval.

---

## Self-Review

Spec coverage:

- Existing Save Preset modal flow reused: Tasks 4–6.
- Backend `GET /api/presets/<id>/download`: Tasks 1–2.
- Full preset directory export instead of whitelist: Task 2 tests and implementation.
- Custom config files included: Task 1 asserts `notes/readme.txt` and `maps/arena.ent`.
- Factories/scripts/user-hooks/checked JSON included: Task 1 asserts all of them.
- Manifest generated: Task 1 and Task 2.
- Binary metadata preserved: Task 1 and Task 2 add `binary_metadata.json`.
- Runtime secrets excluded: design enforced by exporting only preset directory plus generated metadata, not DB/runtime state.
- Frontend blob download: Tasks 3, 5, 6.
- Tests and docs/version: Tasks 1, 6, 7, 8.

Red-flag scan:

- No unresolved fill-in markers are intentionally left in the implementation tasks.
- The only conditional is version bump calculation, with concrete expected value for current `1.12.13`.

Type consistency:

- `savedPresetForDownload` shape is consistently `{ id, name }`.
- `downloadPreset(presetId)` consistently returns Blob.
- Backend route consistently uses `preset_id` and returns `application/zip`.
