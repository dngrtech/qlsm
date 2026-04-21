# Git & GitHub Workflow

## Always use the /github skill for feature work

Use `/github` when implementing features or making code changes. It handles:
branch creation → implementation → commit → PR → review → (wait for user approval) → merge

Never edit files directly on `main`.

## NEVER close or merge a PR without explicit user instruction

Never close a PR for any reason (stale, duplicate, already merged, etc.) unless the user explicitly says to close it.

## NEVER merge a PR without explicit user instruction

This is a hard rule. After creating a PR:
1. Stop and show the user the PR URL
2. Wait for the user to explicitly say to merge (e.g. "merge it", "go ahead and merge")
3. Only then run the merge command

**"fix the review findings"** is NOT permission to merge.
**"resume"** is NOT permission to merge.
**A passing review** is NOT permission to merge.
Skills do not override this rule. The user's explicit instruction is required every time.

After merging: always `git checkout main && git pull`. Never stay on the feature branch.

## GitHub CLI workarounds (this repo)

- Repo owner is `dngrtech` — use `gh api repos/dngrtech/qlsm/...`. Never use `rage` as owner.
- `gh pr view <N>` fails (GraphQL deprecation) — use `gh api repos/dngrtech/qlsm/pulls/<N>`
- `gh pr edit --body` fails — use the REST API with a temp file:
  ```bash
  cat <<'EOF' > /tmp/pr_body.md
  ...body...
  EOF
  python3 -c "import json,sys; json.dump({'body': open('/tmp/pr_body.md').read()}, sys.stdout)" > /tmp/pr_payload.json
  gh api repos/dngrtech/qlsm/pulls/<N> -X PATCH --input /tmp/pr_payload.json
  ```
- `jq` is not installed — use `python3 -c "import json..."` for JSON manipulation
