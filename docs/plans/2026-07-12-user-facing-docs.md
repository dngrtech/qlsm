# User-Facing Documentation Corrections Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Correct the README and linked operator guides for recently added log filtering, pre-deployment hooks, and MinQLX damage-event support.

**Architecture:** Keep the README concise and move operating detail into the existing Diátaxis-aligned user-guide pages. Reuse current terminology and links; do not change behavior, release metadata, or version metadata.

**Tech Stack:** Markdown, MkDocs

---

### Task 1: Update the README feature summary

**Files:**
- Modify: `README.md:16-22`

1. Add MinQLX `damage` event support to the plugin-management text.
2. Describe Last N Lines, Time Range, and All filters for server and chat logs.
3. Run `git diff --check` and expect no output.

### Task 2: Correct the Chat Logs how-to guide

**Files:**
- Modify: `docs/user/operations/chat-logs.md:22-35`

1. Replace the line-only description with all three filter modes.
2. Explain that filter changes take effect when the operator selects **Apply**.
3. Correct the Refresh/Apply behavior description so it refers to the selected filter rather than only a line count.

### Task 3: Document pre-deployment hook selection

**Files:**
- Modify: `docs/user/getting-started/deploy-new-instance.md:36-48`
- Modify: `docs/user/features/hooks.md:22-80`

1. Add the Hooks tab to the deploy-form overview.
2. Explain preset-derived hook visibility, enablement, and drag ordering.
3. State that upload, rename, and delete actions require an existing instance.
4. Include hook files and enabled order in the deployed configuration snapshot.

### Task 4: Validate and publish

**Files:**
- Test: `README.md`
- Test: `docs/user/operations/chat-logs.md`
- Test: `docs/user/getting-started/deploy-new-instance.md`
- Test: `docs/user/features/hooks.md`

1. Run `git diff --check`; expect no output.
2. Run the repository's strict MkDocs build command; expect success.
3. Review the final diff against the approved design.
4. Commit the documentation changes, push `docs/update-user-facing-guides`, and open a pull request targeting `main`.
5. Stop after reporting the PR URL; do not merge without explicit user approval.
