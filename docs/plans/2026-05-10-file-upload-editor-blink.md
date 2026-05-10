# File Upload Editor Blink Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop uploaded files from blinking or being overwritten when the inline CodeMirror editor auto-opens them.

**Architecture:** Keep upload auto-selection in the file manager, but fix the shared editor contract. `CodeMirrorEditor` should update its document from props without emitting `onChange`; only user edits should flow back to the parent.

**Tech Stack:** React, CodeMirror 6, Vitest, Testing Library, jsdom.

---

### Task 1: Add Editor Regression Coverage

**Files:**
- Create: `frontend-react/src/components/__tests__/CodeMirrorEditor.test.jsx`

**Step 1: Write the failing test**

Create a test that renders `CodeMirrorEditor` inside `ThemeProvider` with `value=""`, rerenders it with `value="uploaded content"`, and asserts `onChange` was not called by the prop-driven update.

**Step 2: Run test to verify it fails**

Run: `cd frontend-react && pnpm exec vitest run src/components/__tests__/CodeMirrorEditor.test.jsx`

Expected: FAIL because the current update listener reports programmatic `setValue` transactions through `onChange`.

### Task 2: Ignore Programmatic Set-Value Updates

**Files:**
- Modify: `frontend-react/src/components/CodeMirrorEditor.jsx`

**Step 1: Implement the minimal fix**

In the `EditorView.updateListener`, skip updates where `update.transactions` contains a transaction with `tr.isUserEvent('setValue')`.

**Step 2: Run the focused editor test**

Run: `cd frontend-react && pnpm exec vitest run src/components/__tests__/CodeMirrorEditor.test.jsx`

Expected: PASS.

### Task 3: Verify File Manager Upload Path

**Files:**
- Existing test: `frontend-react/src/components/fileManager/__tests__/useFileManagerController.test.js`

**Step 1: Run upload/controller coverage**

Run: `cd frontend-react && pnpm exec vitest run src/components/fileManager/__tests__/useFileManagerController.test.js`

Expected: PASS, including the existing "selects and opens the uploaded file" case.

### Task 4: Commit

**Files:**
- `docs/plans/2026-05-10-file-upload-editor-blink-design.md`
- `docs/plans/2026-05-10-file-upload-editor-blink.md`
- `frontend-react/src/components/CodeMirrorEditor.jsx`
- `frontend-react/src/components/__tests__/CodeMirrorEditor.test.jsx`

**Step 1: Inspect diff**

Run: `git status --short` and `git diff --stat`.

**Step 2: Commit**

Run:

```bash
git add docs/plans/2026-05-10-file-upload-editor-blink-design.md docs/plans/2026-05-10-file-upload-editor-blink.md frontend-react/src/components/CodeMirrorEditor.jsx frontend-react/src/components/__tests__/CodeMirrorEditor.test.jsx
git commit -m "bug: stop upload editor content feedback"
```
