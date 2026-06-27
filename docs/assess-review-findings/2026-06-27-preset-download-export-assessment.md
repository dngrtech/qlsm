# Preset Download Export Findings Assessment

Reviewed:
- `/home/rage/qlsm/docs/superpowers/specs/2026-06-27-preset-download-export-design.md`
- `/home/rage/qlsm/docs/superpowers/plans/2026-06-27-preset-download-export.md`
- `/home/rage/qlsm/docs/findings/2026-06-27-preset-download-export-findings.md`

## Assessment

### 1. Archive path containment does not handle symlinks
- **Finding says:** The planned ZIP walk can follow symlinks inside `preset.path` and include readable files outside the preset directory.
- **Assessment:** Accept
- **Edge-case validity:** realistic — preset directories are filesystem trees, and a symlink under the preset root would pass the planned `abspath`/relative-name checks while potentially exposing secrets or runtime files.
- **Pros of fixing:** Preserves the design's explicit containment and no-secrets guarantees; prevents an export endpoint from becoming a local file disclosure path; easy to test with one symlink fixture.
- **Cons of fixing:** Slightly more archive-walk logic and a policy choice between skipping symlinks or preserving safe internal links.
- **Action:** Fix before implementation
- **Reasoning:** This is a real security/correctness issue at the export boundary, not speculative hardening. The minimal safe fix is to skip symlink files and directories, or require `realpath` containment before writing.

### 2. Duplicate save is still possible from the Enter key after success
- **Finding says:** The plan disables the Save button after success but leaves the Enter key path able to call `handleSave()` again.
- **Assessment:** Accept
- **Edge-case validity:** realistic — keyboard submission is part of the existing modal behavior, and the success state intentionally leaves the modal open with the old name still present.
- **Pros of fixing:** Prevents duplicate-name errors or accidental second saves in the success/download state; aligns keyboard behavior with the disabled button UI; cheap frontend test coverage.
- **Cons of fixing:** Small additional condition in `handleKeyDown` or `handleSave`; one extra test assertion.
- **Action:** Fix before implementation
- **Reasoning:** The new success state changes the modal lifecycle, so all submit paths need the same guard. This is a focused fix with low cost and clear user-facing benefit.

### 3. Download filename sanitization is specified but not enforced in the plan
- **Finding says:** The spec requires `<safe-preset-name>.zip`, but the plan uses raw preset names in backend and frontend download filenames.
- **Assessment:** Accept
- **Edge-case validity:** realistic — current validation may usually constrain user-created names, but the endpoint is responsible for persisted rows including builtin, legacy, imported, or future-created names.
- **Pros of fixing:** Matches the spec exactly; avoids path separators, control characters, odd `Content-Disposition` behavior, and inconsistent browser downloads; small helper/test addition.
- **Cons of fixing:** Requires defining the sanitization rule and ensuring frontend display/download fallback matches backend expectations.
- **Action:** Fix before implementation
- **Reasoning:** This is a contract mismatch in the plan. It is inexpensive to add an explicit safe filename helper now and avoids relying on assumptions about all current and future preset rows.

### 4. Plan does not define behavior for concurrent preset mutation during ZIP generation
- **Finding says:** Walking the live preset directory while another request updates, renames, or deletes files can produce a partial or failed export.
- **Assessment:** Acknowledge
- **Edge-case validity:** realistic but uncommon — concurrent mutation can happen, but this single-user app and short archive generation make it less likely than the security and UI issues above.
- **Pros of fixing:** A snapshot or deterministic missing-file policy would make exports more stable and easier to reason about under races.
- **Cons of fixing:** Snapshotting adds temp-directory management, cleanup, disk usage, and more implementation surface. Fully solving consistency may require locking around preset writes, which is broader than this feature.
- **Action:** Amend plan
- **Reasoning:** This should not block the feature on a full snapshot design, but the plan should at least define deterministic best-effort behavior: skip/log files that disappear during traversal and return a controlled 500 if archive generation cannot produce a valid ZIP. A lightweight helper-level test is useful if easy, but broad locking/snapshotting is scope growth.

### 5. Binary metadata export shape is narrower than the spec's preservation requirement
- **Finding says:** The plan exports only `file_path` and `description`, always marks binary metadata included, and does not define a stable schema.
- **Assessment:** Acknowledge
- **Edge-case validity:** partially realistic — the spec asks to preserve hook descriptions/metadata needed to understand exported hooks, but this version explicitly has no import/restore flow.
- **Pros of fixing:** Clarifies the artifact contract; makes future import work less ambiguous; avoids overclaiming that metadata is present when the export is empty.
- **Cons of fixing:** Designing a future-proof metadata format can become premature import/restore work, which is outside this design's non-goals.
- **Action:** Amend plan
- **Reasoning:** Do not expand into a full restore-ready schema now. The pragmatic fix is to state the current `BinaryMetadata` fields being exported, include a simple `format_version` or count if desired, and clarify whether `includes.binary_metadata` means supported versus present.

### 6. Backend tests do not assert authentication is required
- **Finding says:** The spec requires `@jwt_required()`, but planned tests do not prove unauthenticated requests are rejected.
- **Assessment:** Accept
- **Edge-case validity:** realistic — omitting the decorator would expose the route while authenticated success/error tests still pass.
- **Pros of fixing:** Directly verifies an explicit API security requirement with a small test; prevents accidental public download access.
- **Cons of fixing:** Minimal test maintenance cost.
- **Action:** Fix before implementation
- **Reasoning:** This is not test bloat; it covers a stated auth contract on a download endpoint that can expose user-managed files.

### 7. Frontend object URL cleanup should be robust if click setup throws
- **Finding says:** The plan revokes the object URL only on the happy path after `a.click()`, so DOM/click errors can leak the URL until page lifetime.
- **Assessment:** Acknowledge
- **Edge-case validity:** speculative — DOM append/click failures are unusual in normal browsers, and the leak is temporary/in-page rather than persistent data loss.
- **Pros of fixing:** Cleaner resource management; simple `try/finally` implementation; avoids brittle tests around cleanup.
- **Cons of fixing:** Adds small complexity to straightforward browser-download code; failure-path test may overfit implementation details.
- **Action:** Optional follow-up
- **Reasoning:** A `try/finally` cleanup is cheap and reasonable if touching the code, but it should not block implementation. The planned happy-path cleanup already covers the normal user flow.

### 8. Plan includes release/version and PR workflow tasks in the implementation plan
- **Finding says:** Release metadata bumps and PR creation steps add process scope to a focused feature plan.
- **Assessment:** Reject
- **Edge-case validity:** already covered — the repository instructions explicitly require version files to be bumped together and PR workflow discipline for implementation work.
- **Pros of fixing:** Separating policy tasks could make the feature implementation section shorter.
- **Cons of fixing:** Removing or deemphasizing these steps risks violating repo policy and producing an incomplete implementation PR.
- **Action:** No action needed
- **Reasoning:** These tasks are intentionally included because repo policy requires them. They are process work, but not inappropriate scope for an implementation plan in this repository.

## Bottom Line

4 of 8 findings need action before implementation. Recommended next step: amend the plan before coding to require symlink-safe archive containment, block Enter-key duplicate saves after success, sanitize download filenames, and add an unauthenticated backend test; also clarify concurrent-mutation and binary-metadata behavior without expanding into a full snapshot/import design.
