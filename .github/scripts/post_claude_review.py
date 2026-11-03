"""Render and post the Claude Code Review from the verifier's structured output.

This script decides the verdict, not the model:
- any scheduled finder without a valid findings file -> "Review incomplete"
- otherwise any accepted finding -> "Fix N items before merge"
- otherwise -> "Ready to merge"

Every model-written string is collapsed to one line, so finding text can't
forge a heading or a second verdict line in the review body.

Env: PR, REPO, HEAD_SHA, LENSES (JSON list), FINDINGS_DIR, VERDICT_JSON, MODEL.
"""
import json
import os
import re
import subprocess
import sys


def one_line(value, limit=600):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def load_finders(findings_dir, lenses):
    failed = []
    for lens in lenses:
        path = os.path.join(findings_dir, f"{lens}.json")
        try:
            with open(path) as fh:
                data = json.load(fh)
            if not isinstance(data.get("findings"), list):
                raise ValueError("no findings list")
        except (OSError, ValueError, AttributeError):
            failed.append(lens)
    return failed


def load_verdict(raw):
    try:
        data = json.loads(raw)
        accepted = data["accepted"]
        filtered = data["filtered"]
        if isinstance(accepted, list) and isinstance(filtered, list):
            return accepted, filtered, True
    except (ValueError, KeyError, TypeError):
        pass
    return [], [], False


def render(accepted, filtered, failed, verifier_ok, lenses, model):
    if not verifier_ok:
        verdict = "Review incomplete: verifier failed"
    elif failed:
        verdict = "Review incomplete: " + ", ".join(failed) + " finder failed"
    elif accepted:
        verdict = f"Fix {len(accepted)} items before merge"
    else:
        verdict = "Ready to merge"

    lines = ["## Claude Code Review", "", f"**Verdict:** {verdict}", ""]
    lines.append(f"### Accepted ({len(accepted)})")
    if not accepted:
        lines.append("None.")
    for i, f in enumerate(accepted, 1):
        loc = f"`{one_line(f.get('file'), 200)}:{f.get('line')}`"
        lines.append(f"{i}. **[{one_line(f.get('severity'), 20)}] {one_line(f.get('title'), 200)}** — {loc}")
        lines.append(f"   What breaks: {one_line(f.get('what_breaks'))}")
        lines.append(f"   Fix: {one_line(f.get('fix'))}")
    lines += ["", f"<details><summary>Filtered out ({len(filtered)})</summary>", ""]
    for f in filtered:
        loc = f"`{one_line(f.get('file'), 200)}:{f.get('line')}`"
        decision = one_line(f.get("decision"), 20).capitalize()
        lines.append(f"- {one_line(f.get('title'), 200)} ({loc}) — {decision}: {one_line(f.get('reason'))}")
    lines += ["", "</details>", ""]
    ran = [lens for lens in lenses if lens not in failed]
    footer = f"Finders: {', '.join(ran) or 'none'}"
    if failed:
        footer += f" · failed: {', '.join(failed)}"
    lines.append(f"<sub>{footer} · verifier: {model}</sub>")
    return "\n".join(lines) + "\n"


def gh(*args, stdin=None):
    return subprocess.run(["gh", *args], input=stdin, text=True, capture_output=True)


def main():
    pr, repo, head_sha = os.environ["PR"], os.environ["REPO"], os.environ["HEAD_SHA"]
    lenses = json.loads(os.environ["LENSES"])
    failed = load_finders(os.environ["FINDINGS_DIR"], lenses)
    accepted, filtered, verifier_ok = load_verdict(os.environ.get("VERDICT_JSON", ""))
    body = render(accepted, filtered, failed, verifier_ok, lenses, os.environ.get("MODEL", "?"))
    print(body)

    result = gh("pr", "review", pr, "--comment", "--body-file", "-", stdin=body)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return 1

    # Inline comments are best effort: a line outside the diff is rejected (422).
    for f in accepted:
        payload = json.dumps({
            "body": f"**[{one_line(f.get('severity'), 20)}] {one_line(f.get('title'), 200)}**\n\n"
                    f"What breaks: {one_line(f.get('what_breaks'))}\n\nFix: {one_line(f.get('fix'))}",
            "commit_id": head_sha,
            "path": one_line(f.get("file"), 300),
            "line": f.get("line"),
            "side": "RIGHT",
        })
        res = gh("api", f"repos/{repo}/pulls/{pr}/comments", "-X", "POST", "--input", "-", stdin=payload)
        if res.returncode != 0:
            print(f"inline comment skipped for {f.get('file')}:{f.get('line')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
