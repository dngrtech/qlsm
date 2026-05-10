# File Upload Editor Blink Design

## Problem

Uploading a text file into the file manager auto-opens it in the inline CodeMirror editor, but the editor blinks rapidly, cannot be typed into, and can later show the uploaded file as blank. Deleting a file while it is in this bad state can leave a stale tree row that cannot be selected.

## Root Cause

`CodeMirrorEditor` dispatches a full-document replacement when its `value` prop changes. That transaction is tagged as `userEvent: 'setValue'`, but the shared update listener only checks `update.docChanged`, so it forwards the programmatic replacement back through `onChange` as if the user typed it.

During upload auto-selection, the parent may briefly render the editor with temporary or stale content while the adapter finishes reading the uploaded file. The editor then writes that transient value back into the adapter, which can erase the uploaded content and create a render/write feedback loop.

## Chosen Approach

Teach `CodeMirrorEditor` to ignore programmatic value-sync transactions and only call `onChange` for real user edits. This fixes the shared editor contract instead of special-casing upload selection in the file manager.

## Alternatives Considered

- Delay upload selection until the adapter tree refreshes. This reduces one race, but leaves the editor able to write parent-driven replacements back into state.
- Special-case uploaded files in `useFileManagerController`. This is narrower, but still allows the same feedback bug when any parent-driven content update reaches CodeMirror.

## Testing

Add focused regression coverage that proves a programmatic editor value update does not call `onChange`. Keep the existing file manager upload selection test to cover the controller behavior that auto-opens uploaded files.
