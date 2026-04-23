#!/usr/bin/env python3
"""Rewrite absolute /docs/... links in markdown files to relative paths.

Run from repo root:
    python scripts/rewrite-doc-paths.py --dry-run
    python scripts/rewrite-doc-paths.py            # apply

Scope: scans docs/user/**/*.md only. Other docs/ trees are left alone.

Rewrites these patterns (absolute -> relative, .md preserved/added):
    [text](/docs/foo/bar)        -> [text](../foo/bar.md)
    [text](/docs/foo/bar.md)     -> [text](../foo/bar.md)
    ![alt](/docs/images/x.png)   -> ![alt](../images/x.png)
    <img src="/docs/images/x.png" ...>  -> <img src="../images/x.png" ...>

Idempotent: running again produces no changes.
Skips anchors that are pure external URLs (http[s]://) and in-page anchors (#...).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = REPO_ROOT / "docs" / "user"

# Match markdown links and images:  [text](/docs/...)  or  ![alt](/docs/...)
MD_LINK_RE = re.compile(
    r"""(!?)\[([^\]]*)\]\((/docs/[^)\s#]+)(#[^)]*)?\)"""
)

# Match <img src="/docs/...">  (and src='...')
HTML_IMG_SRC_RE = re.compile(
    r"""(<img\b[^>]*\bsrc=)(['"])(/docs/[^'"]+)\2""",
    re.IGNORECASE,
)


def compute_relative(from_file: Path, abs_doc_path: str) -> str:
    """Given a source md file and an absolute '/docs/foo/bar[.md]' target,
    return the relative path with .md extension preserved or added."""
    target = abs_doc_path[len("/docs/"):]

    is_image = target.startswith("images/")
    has_ext = "." in target.rsplit("/", 1)[-1]

    if not is_image and not has_ext:
        target = target + ".md"

    target_path = DOCS_ROOT / target
    source_dir = from_file.parent
    rel_str = os.path.relpath(target_path, start=source_dir).replace("\\", "/")
    return rel_str


def rewrite_text(from_file: Path, text: str) -> str:
    def md_sub(m: re.Match) -> str:
        bang, label, abs_path, anchor = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        rel = compute_relative(from_file, abs_path)
        return f"{bang}[{label}]({rel}{anchor})"

    def img_sub(m: re.Match) -> str:
        prefix, quote, abs_path = m.group(1), m.group(2), m.group(3)
        rel = compute_relative(from_file, abs_path)
        return f"{prefix}{quote}{rel}{quote}"

    text = MD_LINK_RE.sub(md_sub, text)
    text = HTML_IMG_SRC_RE.sub(img_sub, text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print diffs but do not write.")
    args = parser.parse_args()

    if not DOCS_ROOT.is_dir():
        print(f"ERROR: {DOCS_ROOT} not found — run from repo root.", file=sys.stderr)
        return 2

    changed_files = 0
    total_subs = 0
    for md_file in sorted(DOCS_ROOT.rglob("*.md")):
        original = md_file.read_text(encoding="utf-8")
        rewritten = rewrite_text(md_file, original)
        if rewritten == original:
            continue
        changed_files += 1
        subs = sum(1 for _ in MD_LINK_RE.finditer(original)) + \
               sum(1 for _ in HTML_IMG_SRC_RE.finditer(original))
        total_subs += subs
        rel_path = md_file.relative_to(REPO_ROOT)
        if args.dry_run:
            print(f"--- would rewrite: {rel_path} ({subs} occurrences)")
        else:
            md_file.write_text(rewritten, encoding="utf-8")
            print(f"--- rewrote: {rel_path} ({subs} occurrences)")

    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"\n{mode}: {changed_files} files with changes, ~{total_subs} candidate occurrences.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
