"""The runtime compatibility filter over a plugin directory.

One implementation, two callers: the draft workspace (ui/routes/draft_routes.py
_apply_runtime_filter, fed from the live shipped assets) and the host runtime
upgrade (ui/runtime_upgrade_conversion.py, fed from the operation's immutable
materialized copies of the same assets). The caller decides WHAT the target
ships; this module decides what happens to each file.
"""
import os

from ui.plugin_compat import VERDICT_COMPATIBLE, baseline_digest, classify


def filter_scripts_for_target(draft_scripts_path, target, *, hashes, candidates,
                              shipped_by_target, accepted_replacements):
    """Delete what cannot run on `target`; write accepted replacements.

    hashes: filename -> sha256 of the target's vendored baseline
    (preset_compat.baseline_hashes); candidates: flat filename -> text the
    target offers as replacements (replacement_scripts); shipped_by_target:
    relpath -> text of every .py the target's default preset ships
    (shipped_scripts). Returns (relative paths removed, relative paths restored).
    """
    shipped_digests = {rel: baseline_digest(text)
                       for rel, text in shipped_by_target.items()}
    removed = []
    restored = []

    for root, _dirs, filenames in os.walk(draft_scripts_path):
        for filename in filenames:
            if not filename.lower().endswith('.py'):
                continue  # .so hooks and .txt data are runtime-agnostic
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, draft_scripts_path)
            try:
                with open(full_path, 'r', encoding='utf-8') as handle:
                    text = handle.read()
            except (OSError, ValueError):
                # Unreadable, or not valid UTF-8 (ValueError covers
                # UnicodeDecodeError): _read_preset_scripts() on the GET path
                # hits this exact failure and silently omits the file from
                # what the operator is shown, instead of reporting it
                # stripped. Deleting a file the dialog never displayed as
                # incompatible would widen the strip past what was promised.
                continue
            if not text.strip():
                # An empty file (a bare __init__.py marking a package) cannot
                # be incompatible with anything, and removing it breaks
                # imports for every sibling module that did survive.
                continue
            if shipped_digests.get(rel_path) == baseline_digest(text):
                # This file is byte-for-byte the one the TARGET runtime's own
                # default preset ships at this path -- almost always because
                # _seed_draft laid it down itself moments ago. Deleting the
                # target's own baseline is never right, and the operator was
                # never shown it: the dialog lists the SOURCE preset's files.
                # Compared by content, not by name, so a source file that
                # merely reuses a shipped filename is still classified below.
                continue
            verdict, _reasons = classify(
                text, target, baseline_sha256=hashes.get(filename))
            if verdict == VERDICT_COMPATIBLE:
                continue
            if (os.sep in rel_path or '/' in rel_path) and rel_path in shipped_by_target:
                # A subdirectory file the TARGET runtime also ships at this exact path.
                # _seed_draft laid the target's copy down and the source overlay wrote
                # over it, so deleting now leaves nothing where the seed put something.
                #
                # Root-level files have a way out of that: _strip_entry offers the
                # target's version and the operator ticks it. Subdirectory files never
                # get the offer -- isEnableablePluginPath() rejects any path with a
                # separator, so they cannot appear in the dialog at all -- which left
                # mydiscordbot.py landing with an empty discord_extensions/ beside it
                # and failing at load_extension().
                #
                # Restoring is not the same act as offering a replacement, and the
                # reason _strip_entry declines to offer does not apply here: that
                # concern is about relocating a subdirectory file into the plugin root,
                # a path change. This writes the target's own file back to the path it
                # already occupied, which is what the seed did before the overlay.
                try:
                    with open(full_path, 'w', encoding='utf-8') as handle:
                        handle.write(shipped_by_target[rel_path])
                    restored.append(rel_path)
                except OSError:
                    pass
                continue
            try:
                os.remove(full_path)
                removed.append(rel_path)
            except OSError:
                continue

    for name in accepted_replacements or []:
        # Client-supplied. Membership in `candidates` is what actually stops
        # '../x.py' or any other traversal -- replacement_scripts() only ever
        # returns bare filenames read from a flat preset scripts/ directory,
        # so nothing containing a separator can pass this check in the first
        # place. The separator/suffix checks below are defence in depth, not
        # the live guard.
        if name not in candidates:
            continue
        if '/' in name or os.sep in name or not name.endswith('.py'):
            continue
        try:
            with open(os.path.join(draft_scripts_path, name), 'w',
                      encoding='utf-8') as handle:
                handle.write(candidates[name])
        except OSError:
            continue

    return removed, restored
