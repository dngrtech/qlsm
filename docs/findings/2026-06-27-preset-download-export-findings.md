# Preset Download Export Review Findings

Reviewed:
- `/home/rage/qlsm/docs/superpowers/specs/2026-06-27-preset-download-export-design.md`
- `/home/rage/qlsm/docs/superpowers/plans/2026-06-27-preset-download-export.md`

## Critical
### Archive path containment does not handle symlinks
The design requires the endpoint to walk only under `preset.path` and keep runtime/secrets out of the export. The planned `_build_preset_export_zip()` checks `os.path.abspath()` and then calls `archive.write(full_path, rel_path)`. That does not prove the file target is under the preset root: a symlink inside the preset directory can point to a database, log, SSH key, or any readable host file outside the preset tree, and `zipfile.write()` will follow the link target. This can leak sensitive host/runtime state despite the preset-root walk.
Required fix: Change the plan to either skip all symlinks (`os.path.islink(full_path)` and symlink dirs) or validate `os.path.realpath(full_path)` is under `os.path.realpath(root)` before writing. Add a backend test with a symlink inside the preset directory pointing outside the preset root and assert the ZIP excludes it.

## Important
### Duplicate save is still possible from the Enter key after success
The plan disables the Save button when `savedPreset` is set, but `SavePresetModal`'s current `handleKeyDown` still calls `handleSave()` when Enter is pressed as long as `!isSaving && !isValidating && presetName.trim()`. After the success panel appears, the old preset name remains in state, so pressing Enter can call `onSave` again even though the UI intends duplicate saving to be disabled. That can create a confusing second validation/save attempt or surface a duplicate-name error in the success state.
Required fix: Update the plan to include `!savedPreset` in `handleKeyDown` and/or add an early return in `handleSave` when `savedPreset` is set. Add a frontend test that pressing Enter after save success does not call `createPreset` a second time.

### Download filename sanitization is specified but not enforced in the plan
The spec says the attachment name must be `<safe-preset-name>.zip`. The plan uses `download_name=f'{preset.name}.zip'` on the backend and `${preset.name || 'preset'}.zip` in the frontend. Current user-created preset validation appears restrictive, but builtin/imported/legacy database rows or future name changes could still contain characters that are unsafe or awkward in `Content-Disposition` or the browser download attribute. This is a compatibility/security boundary in the export endpoint, not just a UI concern.
Required fix: Add an explicit filename-safe helper in the backend route and matching frontend fallback behavior, or document that all persisted preset names are guaranteed safe. Add tests for names containing spaces/path separators/control-ish characters if such rows can exist, asserting the attachment filename and browser download name are sanitized.

### Plan does not define behavior for concurrent preset mutation during ZIP generation
The archive is built by walking the live preset directory while the same preset can potentially be updated, renamed, or deleted by another request. That can produce a partial ZIP, a 500 midway through download, or a manifest that describes one preset state while files come from another. This matters because export is intended to be a portable backup artifact.
Required fix: Add an implementation step that snapshots the preset directory to a temporary directory before zipping, or clearly accepts best-effort live export and handles disappeared files deterministically by skipping/logging them. Add a backend test or helper-level test that a file disappearing during traversal does not leak a traceback or produce a corrupt response.

### Binary metadata export shape is narrower than the spec's preservation requirement
The spec requires preserving hook descriptions/metadata needed to understand exported hooks. The plan writes `binary_metadata.json` with only `file_path` and `description`. If `BinaryMetadata` later contains, or already requires, additional fields for hook identity/context, format versioning, or restore/import alignment, this export will be lossy and hard to evolve. The plan also always marks `includes.binary_metadata` true even when metadata export is empty.
Required fix: Define the `binary_metadata.json` schema in the spec/plan, including whether empty metadata should be emitted and whether `includes.binary_metadata` means “supported” or “present”. If the model has only `file_path` and `description`, state that explicitly and add a schema/version field or manifest count for forward compatibility.

## Minor
### Backend tests do not assert authentication is required
The spec requires `@jwt_required()` like other preset routes, but the planned backend tests only cover authenticated success/error paths. A missing decorator would still leave most tests meaningful except the route would be exposed.
Suggested fix: Add a backend test that `GET /api/presets/<id>/download` without credentials returns the app's unauthorized status and no ZIP body.

### Frontend object URL cleanup should be robust if click setup throws
The plan revokes the object URL immediately after `a.click()`, but not in a `finally` around DOM append/click/remove/revoke. If DOM manipulation throws in tests or unusual browsers, the object URL can leak for the page lifetime.
Suggested fix: Wrap anchor creation/click/removal in `try/finally`, revoking the URL and removing the anchor if it was appended. Add a focused test for the happy-path cleanup already planned; optionally add a failure-path test.

### Plan includes release/version and PR workflow tasks in the implementation plan
For a focused pre-implementation plan, the release metadata bump and PR creation steps add process scope that can slow or complicate the feature implementation. They may be required by repo policy, but they are not part of proving the feature behavior and can create merge conflicts unrelated to the export code.
Suggested fix: Keep docs/version/PR steps clearly separated as release workflow tasks after feature tests pass, or mark them as repo-policy tasks rather than feature implementation tasks.

## Open Questions
- Should symlinks inside preset directories be skipped entirely, stored as symlink entries, or followed only when their resolved target remains under the preset root?
- Is `binary_metadata.json` intended to be a stable future import/restore contract, or only human-readable supplemental export metadata for this no-import version?
- Should the download endpoint support builtin presets as well as user-created presets, and are builtin preset names guaranteed to satisfy the same filename-safety constraints?

## Tests To Add
- Backend: preset directory contains a symlink to a file outside `preset.path`; ZIP must not include the outside file contents.
- Backend: unauthenticated download request is rejected.
- Backend: unsafe or legacy preset names produce a sanitized attachment filename, if such names can exist.
- Backend/helper: file removed during archive generation is handled deterministically without a corrupt response or traceback leak.
- Frontend: pressing Enter after the save success/download state does not call `createPreset` again.
- Frontend: download helper cleans up object URLs and temporary anchors even when the click path fails.
