# Ent CodeMirror Highlighting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add CodeMirror syntax highlighting and lint diagnostics for user-uploaded `.ent` files.

**Architecture:** Implement a dedicated CodeMirror 6 stream language because `.ent` files use Quake-style quoted key/value pairs, not JSON. Route `.ent` files to the new language and linter through the existing config file-manager hooks in Add Instance and Edit Instance.

**Tech Stack:** React, CodeMirror 6 `StreamLanguage`, CodeMirror lint diagnostics, Vitest.

---

### Task 1: Add The `.ent` Language And Linter

**Files:**
- Create: `frontend-react/src/codemirror-lang-qlent.js`
- Test: `frontend-react/src/codemirror-lang-qlent.test.js`

**Step 1: Write tests**

Add tests for:
- valid entity blocks with quoted key/value pairs produce no diagnostics
- missing closing brace reports an error
- malformed non-empty lines report an error

**Step 2: Implement language and linter**

Create `qlentLanguage` with token styles for comments, braces, keys, values, and invalid text. Export `qlentLinter(view)` for diagnostics.

**Step 3: Verify**

Run: `pnpm exec vitest run src/codemirror-lang-qlent.test.js`

### Task 2: Route `.ent` Files To The New Mode

**Files:**
- Modify: `frontend-react/src/components/addInstance/AddInstanceForm.jsx`
- Modify: `frontend-react/src/components/instances/EditInstanceConfigModal.jsx`
- Test: `frontend-react/src/components/addInstance/__tests__/AddInstanceForm.test.jsx`
- Test: `frontend-react/src/components/instances/__tests__/EditInstanceConfigModal.test.jsx`

**Step 1: Write routing tests**

Add component tests that open an `.ent` config file and assert the file manager receives the `.ent` language and linter.

**Step 2: Implement routing**

Import `qlentLanguage` and `qlentLinter`, return them for filenames ending in `.ent`, and leave existing `.cfg`, `.txt`, factory, and plugin behavior unchanged.

**Step 3: Verify**

Run:
- `pnpm exec vitest run src/codemirror-lang-qlent.test.js`
- `pnpm exec vitest run src/components/addInstance/__tests__/AddInstanceForm.test.jsx src/components/instances/__tests__/EditInstanceConfigModal.test.jsx`

### Task 3: Final Checks

**Files:**
- Review changed files with `git diff`

**Step 1: Run affected frontend tests**

Run the commands from Task 2.

**Step 2: Commit**

Commit docs, implementation, and tests with a focused feature commit.
