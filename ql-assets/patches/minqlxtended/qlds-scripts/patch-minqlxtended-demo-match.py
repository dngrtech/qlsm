#!/usr/bin/env python3
"""Layer per-match native demo capture on top of upstream's own demos.c.

Replaces patch-minqlxtended-demo-slots.py, which whole-body-replaced demos.c
before minqlxtended v1.0.0. That rewrite existed because the old demos.c could
only record "every connected client while sv_demoRecord is 1" - there was no way
to say "record THIS slot, from ITS OWN connect-time gamestate", which is what a
match archive needs (a .dm_91 is a delta chain whose first message must be a
gamestate, so capture has to start at connect even though the shipped file must
start at the countdown). demo_slot.c's prebuffer was that missing mechanism,
hand-built.

v1.0.0 ships the mechanism itself - Demo_Request(slot, mode), read by
Demo_CaptureBody through demo_slot_wanted() - plus a completion queue
(Demo_PendingFinished/Demo_PollFinished) that hands each finished segment back
to the game thread. So demos.c is now left COMPLETELY UNTOUCHED by this patch,
and everything that is genuinely ours moves into one new file,
src/features/demo_match.c: match arm/disarm, match-named output paths, the
two-stage UDT cut, the per-POV snapshot index, and the finalize thread they run
on. demo_slot.c/.h are gone.

The insertions below are the five points where upstream's code has to call into
that file. Note two of them in particular:

  * DemoMatch_OnFinished() goes INSIDE upstream's existing completion drains
    (DispatchFinishedDemos in the pygame build, DrainFinishedDemos in nopy) -
    NOT into a second `while (Demo_PollFinished(&done))` loop of our own. That
    queue is single-consumer and Demo_PollFinished() pops destructively, so two
    independent drainers would each see an arbitrary subset of the completions
    and neither would work.

  * DemoMatch_OnClientConnect() is called after qagame's own ClientConnect has
    accepted the client and before the engine sends its gamestate, which is what
    makes upstream open that client's segment at exactly that gamestate.

demo_match.c/.h do not exist in pristine upstream and the real VPS build
re-clones upstream from scratch, so their canonical copies live in this repo
under minqlxtended-patches/ and are placed into the build tree here, exactly as
patch-minqlxtended-item-events.py does for qlhub_item_events.c.

The two `// TASK5-HOOK:` marker comments in demo_match.c are deliberate: the
Python dispatchers they name do not exist until patch-minqlxtended-demo-bindings.py
runs, and demo_match.c must keep compiling and linking with zero unresolved
symbols until then. Same convention the pre-v1.0.0 chain used.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PATCH_SRC_DIR = REPO_ROOT / "minqlxtended-patches"

# Copied into <build>/src/features/, next to the demos.c they sit on top of.
NEW_FILES = ("demo_match.c", "demo_match.h")
NEW_FILES_SUBDIR = Path("src") / "features"

MK_MARKER = "src/features/demo_match.c"
HOOKS_MARKER = "DemoMatch_OnClientConnect"

# ---------------------------------------------------------------------------
# Makefile
# ---------------------------------------------------------------------------

# COMMON_SOURCES feeds BOTH SOURCES and SOURCES_NOPY (see the two "+=" lines
# right under it), so this single insertion covers both builds - which is what
# is wanted: demo_match.c compiles in nopy too, with its Python call sites
# behind #ifndef NOPY, so a nopy build still type-checks the whole file.
MK_SOURCES_ANCHOR = "                 src/features/demos.c src/features/profile.c"
MK_SOURCES_NEW = (
    "                 src/features/demos.c src/features/profile.c \\\n"
    "                 src/features/demo_match.c"
)

# demo_match.c does #include "udt/bridge.h", and udt/ is materialised at the
# build-tree ROOT by patch-minqlxtended-demo-cutter.py - not under src/, which is
# the only -I the stock Makefile has. GCC does not put the working directory on
# the quoted-include path by itself, so without this the include does not resolve.
#
# patch-minqlxtended-item-respawn.py needs the same -I. for its own build-tree-root
# header and runs BEFORE this script in the orchestrator's list, so in the real
# order the line is usually already there. Guard on the line itself rather than on
# who wrote it (same check item-respawn.py uses): a duplicate -I. is harmless to
# the compiler but makes the composed Makefile look like a patch ran twice.
MK_CFLAGS_ANCHOR = "CFLAGS += $(EXTRA_CFLAGS)"
MK_CFLAGS_MARKER = "CFLAGS += -I."
MK_CFLAGS_NEW = (
    "CFLAGS += $(EXTRA_CFLAGS)\n"
    "# src/features/demo_match.c includes \"udt/bridge.h\", which the demo-cutter\n"
    "# patch places at the build-tree root rather than under src/.\n"
    "CFLAGS += -I."
)

# ---------------------------------------------------------------------------
# src/server/hooks.c
# ---------------------------------------------------------------------------

HK_INCLUDE_ANCHOR = '#include "features/demos.h"\n'
HK_INCLUDE_NEW = '#include "features/demo_match.h"\n#include "features/demos.h"\n'

# nopy build: upstream's own drain, called from the outgoing-message path
# because a nopy build has no G_RunFrame hook. Matched in full so it cannot be
# confused with the pygame drain below, which is textually similar.
HK_NOPY_DRAIN_ANCHOR = """    demo_finished_t done;
    while (Demo_PollFinished(&done)) {
        if (done.failed) {
            Demo_AbandonSlot(done.slot, done.gen);
        }
    }

    unsigned dropped = Demo_TakeDroppedCount();
    if (dropped) {
        DebugPrint("demo: %u completion(s) dropped\\n", dropped);
    }"""
HK_NOPY_DRAIN_NEW = """    demo_finished_t done;
    while (Demo_PollFinished(&done)) {
        if (done.failed) {
            Demo_AbandonSlot(done.slot, done.gen);
        }
        // Inert in a nopy build - nothing can arm a match without the Python
        // bindings - but kept symmetrical with the pygame drain so the two
        // never have to be reasoned about separately.
        DemoMatch_OnFinished(&done);
    }

    unsigned dropped = Demo_TakeDroppedCount();
    if (dropped) {
        DebugPrint("demo: %u completion(s) dropped\\n", dropped);
    }"""

# pygame build: the real one. Ours runs BEFORE the Python dispatch so a handler
# of upstream's own demo_finished event cannot observe a state where the segment
# has been reported to Python but not yet queued for cutting.
HK_PY_DRAIN_ANCHOR = (
    "        DemoFinishedDispatcher(done.slot, done.path, done.bytes, done.discarded, done.failed);\n"
)
HK_PY_DRAIN_NEW = (
    "        DemoMatch_OnFinished(&done);\n"
    "        DemoFinishedDispatcher(done.slot, done.path, done.bytes, done.discarded, done.failed);\n"
)

# Inside the existing demo probe, so its cost is attributed to the demo subsystem
# rather than silently added to PROF_FRAME_TOTAL. Before the drain: a segment
# opened during the last frame has to be noticed while its client is still
# connected and its netchan sequence still readable.
HK_FRAME_ANCHOR = "        PROF_BEGIN(t_demos);\n        DispatchFinishedDemos();"
HK_FRAME_NEW = (
    "        PROF_BEGIN(t_demos);\n"
    "        DemoMatch_Frame();\n"
    "        DispatchFinishedDemos();"
)

# After qagame has accepted the client (a non-NULL return is a rejection) and
# well before SV_SendClientGameState - which is the whole point: Demo_Request has
# to be set before that gamestate goes out, because it is the only message a
# valid .dm_91 for this connection can begin at.
HK_CONNECT_ANCHOR = """    return ClientConnect(clientNum, firstTime, isBot);
}"""
HK_CONNECT_NEW = """    char* rejected = ClientConnect(clientNum, firstTime, isBot);
    if (!rejected) {
        // Before the engine sends this client's gamestate, so upstream's capture
        // opens their segment at it. Also fires with firstTime false, i.e. for
        // every client carried across a map change, which is where they each get
        // their next fresh gamestate.
        DemoMatch_OnClientConnect(clientNum);
    }
    return rejected;
}"""

# Before upstream's own close, so the match still sees which segments are open
# and can count what it is waiting for.
HK_CLOSEALL_ANCHOR = (
    "    Demo_CloseAll(); // map change: finalise open demos; each client re-primes with a fresh gamestate\n"
)
HK_CLOSEALL_NEW = (
    "    DemoMatch_OnCloseAll(); // ...and close the match out, so its files still get cut and indexed\n"
    + HK_CLOSEALL_ANCHOR
)


def _replace(text: str, anchor: str, replacement: str, *, label: str, path: Path) -> str:
    if anchor not in text:
        raise SystemExit(f"anchor missing/changed in {path}: {label}")
    return text.replace(anchor, replacement, 1)


def patch_makefile(text: str, path: Path) -> str:
    # demo_match.c calls demo_cut()/demo_scan()/demo_index() unconditionally, so
    # without the vendored UDT tree this fails at LINK time with an unhelpful
    # wall of undefined references. Check for the demo-cutter patch's own marker
    # first, so the failure is loud and points at the fix.
    if "UDT_CXX_OBJS" not in text:
        raise SystemExit(
            f"{path}: no UDT_CXX_OBJS - run patch-minqlxtended-demo-cutter.py "
            "against this build tree first (it wires in the vendored UDT cutter "
            "demo_match.c depends on unconditionally)"
        )
    text = _replace(text, MK_SOURCES_ANCHOR, MK_SOURCES_NEW, label="COMMON_SOURCES", path=path)
    if MK_CFLAGS_MARKER not in text:
        text = _replace(text, MK_CFLAGS_ANCHOR, MK_CFLAGS_NEW, label="CFLAGS += $(EXTRA_CFLAGS)", path=path)
    return text


def patch_hooks(text: str, path: Path) -> str:
    text = _replace(text, HK_INCLUDE_ANCHOR, HK_INCLUDE_NEW, label="demos.h include", path=path)
    text = _replace(text, HK_NOPY_DRAIN_ANCHOR, HK_NOPY_DRAIN_NEW, label="DrainFinishedDemos (nopy)", path=path)
    text = _replace(text, HK_PY_DRAIN_ANCHOR, HK_PY_DRAIN_NEW, label="DispatchFinishedDemos loop body", path=path)
    text = _replace(text, HK_FRAME_ANCHOR, HK_FRAME_NEW, label="My_G_RunFrame demo probe", path=path)
    text = _replace(text, HK_CONNECT_ANCHOR, HK_CONNECT_NEW, label="My_ClientConnect tail", path=path)
    text = _replace(text, HK_CLOSEALL_ANCHOR, HK_CLOSEALL_NEW, label="My_SV_SpawnServer Demo_CloseAll", path=path)
    return text


def copy_new_files(root: Path) -> int:
    """Place demo_match.c/.h into the build tree before the Makefile names them.

    Content-compared rather than copied unconditionally so a re-run does not bump
    mtime and force a needless rebuild - same reasoning as the vendored udt/ copy
    in patch-minqlxtended-demo-cutter.py.

    Only ever called on a tree this script has NOT already patched. On an
    already-patched tree the copy would be actively harmful, not merely
    redundant: patch-minqlxtended-demo-bindings.py edits the build tree's copy of
    demo_match.c (it replaces the two TASK5-HOOK markers), so the destination
    legitimately differs from the canonical source, and re-copying would silently
    revert the dispatcher calls - while demo-bindings, seeing its own marker still
    present in python_embed.c, would report "already patched" and not put them
    back. The real installer re-clones the build tree from scratch anyway, so
    "refresh the sources in place" is not a case that has to work.
    """
    dest_dir = root / NEW_FILES_SUBDIR
    if not dest_dir.is_dir():
        raise SystemExit(f"not a v1.0.0 minqlxtended build tree (no {dest_dir}): {root}")
    copied = 0
    for name in NEW_FILES:
        src = PATCH_SRC_DIR / name
        if not src.is_file():
            raise SystemExit(f"canonical source missing: {src}")
        dest = dest_dir / name
        if dest.is_file() and dest.read_bytes() == src.read_bytes():
            continue
        shutil.copy2(src, dest)
        copied += 1
    return copied


_FILES = (
    (Path("Makefile"), MK_MARKER, patch_makefile),
    (Path("src") / "server" / "hooks.c", HOOKS_MARKER, patch_hooks),
)


def already_patched(root: Path) -> bool:
    for rel, marker, _ in _FILES:
        path = root / rel
        if not path.is_file() or marker not in path.read_text(encoding="utf-8"):
            return False
    return True


def patch_tree(root: Path) -> bool:
    """All-or-nothing: every anchor in every file is validated before anything is
    written, so a missing anchor in the last file cannot leave the first one
    half-patched."""
    targets = [(root / rel, marker, fn) for rel, marker, fn in _FILES]
    for path, _, _ in targets:
        if not path.is_file():
            raise SystemExit(f"missing file: {path}")

    originals = [path.read_text(encoding="utf-8") for path, _, _ in targets]
    patched = [fn(text, path) for (path, _, fn), text in zip(targets, originals)]
    for (path, _, _), new_text in zip(targets, patched):
        # newline="\n": these files are LF in the build tree and the Makefile in
        # particular breaks outright if a Windows-side run rewrites it with CRLF.
        path.write_text(new_text, encoding="utf-8", newline="\n")
    return True


def main() -> None:
    # Arguments are minqlxtended-build *directories*: this patch spans several
    # files, so pointing it at a single file would be meaningless.
    roots = [Path(p) for p in sys.argv[1:]] or [Path.home() / "minqlxtended-build"]
    for root in roots:
        if not root.is_dir():
            raise SystemExit(f"not a minqlxtended-build directory: {root}")
        if already_patched(root):
            # Nothing is copied and nothing is written - see copy_new_files' own
            # docstring for why re-copying an already-patched tree is worse than
            # doing nothing.
            print(f"already patched demo match: {root}")
            continue
        copied = copy_new_files(root)
        print(
            f"demo_match.c/.h up to date: {root / NEW_FILES_SUBDIR}"
            if copied == 0
            else f"copied {copied} new file(s) -> {root / NEW_FILES_SUBDIR}"
        )
        patch_tree(root)
        print(f"patched demo match: {root}")


if __name__ == "__main__":
    main()
