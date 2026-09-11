#!/usr/bin/env python3
"""Wire udt/bridge.cpp + vendored UDT cutter sources into the Makefile.

minqlxtended-build is pure C (gcc, -std=gnu11) today - this adds a g++
compile step for the vendored C++ subset under udt/ (Task 1, see
udt/COPYING.txt for the GPLv2 vendoring) and links libstdc++, so demos.c
(Task 3) can call the extern "C" demo_cut() bridge from udt/bridge.h.

Both `make all` (the Python-embedding build) and `make nopy` get the vendored
objects and a C++-capable link step. `make debug`/`make nopy_debug` are
intentionally left untouched - each links from its own object list
(OBJS_DEBUG/OBJS_NOPY_DEBUG, separate build/{dbg,nopydbg}/ trees since
upstream's v1.0.0 restructure), and neither is patched to include the udt/
objects (matches the brief's scope: only all/nopy were asked for - the VPS
build only ever runs `make clean all`).

The vendored udt/ tree does NOT exist in pristine upstream tjone270/minqlxtended,
and the real VPS build (autoconfig-server/install-minqlx.sh) re-clones upstream
from scratch into $MINQLX_BUILD_DIR. A pure text patcher therefore cannot be the
whole story here: the canonical copy of udt/ lives in this repo, under
minqlxtended-patches/udt/, and is materialised into the build tree by this
script before the Makefile edits below reference it (same "copy the new file in,
then patch the Makefile that names it" pattern as
patch-minqlxtended-item-events.py).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
UDT_SRC = REPO_ROOT / "minqlxtended-patches" / "udt"

MARKER = "udt/bridge.cpp"

OLD_OBJS_BLOCK = (
    "OBJS = $(SOURCES:%.c=$(BUILDDIR)/rel/%.o)\n"
    "OBJS_DEBUG = $(SOURCES:%.c=$(BUILDDIR)/dbg/%.o)\n"
    "OBJS_NOPY = $(SOURCES_NOPY:%.c=$(BUILDDIR)/nopy/%.o)\n"
    "OBJS_NOPY_DEBUG = $(SOURCES_NOPY:%.c=$(BUILDDIR)/nopydbg/%.o)"
)
NEW_OBJS_BLOCK = (
    OLD_OBJS_BLOCK
    + "\nOBJS += $(UDT_CXX_OBJS_REL)  # udt/bridge.cpp\n"
    + "OBJS_NOPY += $(UDT_CXX_OBJS_NOPY)  # udt/bridge.cpp"
)

# Link recipes for the two targets this task covers. Note these are two
# textually distinct lines (different OUTPUT*/OBJS*/LDFLAGS* variable names),
# not one line reused twice - both must be patched independently, or the
# nopy link (which also gets the C++ objects appended to OBJS_NOPY below)
# would still try to link C++ translation units with plain `gcc`, producing
# undefined references to libstdc++ symbols (operator new/delete, exception
# machinery, etc.) at link time.
OLD_LINK_ALL = "$(CC) $(CFLAGS) -D$(VERSION) -o $(OUTPUT) $(OBJS) $(LDFLAGS)"
NEW_LINK_ALL = "$(CXX_LINK) $(CFLAGS) -D$(VERSION) -o $(OUTPUT) $(OBJS) $(LDFLAGS)"

OLD_LINK_NOPY = (
    "$(CC) $(CFLAGS) -D$(VERSION) -o $(OUTPUT_NOPY) $(OBJS_NOPY) $(LDFLAGS_NOPY)"
)
NEW_LINK_NOPY = (
    "$(CXX_LINK) $(CFLAGS) -D$(VERSION) -o $(OUTPUT_NOPY) $(OBJS_NOPY) $(LDFLAGS_NOPY)"
)

# Anchor for the new .cpp pattern rules: the last of the four existing .c pattern
# rules, right before "-include $(DEPS)". Ordering hazard note (still applies,
# unchanged from the pre-v1.0.0 patch): UDT_CXX_OBJS_REL/NOPY must already be
# defined by the time OBJS/OBJS_NOPY are appended to (done in NEW_OBJS_BLOCK,
# which sits before this pattern-rule anchor in the file) - see the docstring-level
# comment in UDT_CXX_DEFS below for the full explanation.
OLD_NOPYDBG_RULE = (
    "$(BUILDDIR)/nopydbg/%.o: %.c\n"
    "\t@mkdir -p $(dir $@)\n"
    "\t$(CC) $(CFLAGS) -MMD -MP -D$(VERSION) -c $< -o $@"
)
NEW_CPP_PATTERN_RULES = (
    OLD_NOPYDBG_RULE
    + "\n\n"
    "$(BUILDDIR)/rel/%.o: %.cpp\n"
    "\t@mkdir -p $(dir $@)\n"
    "\t$(CXX) $(CXXFLAGS) -MMD -MP -c $< -o $@\n\n"
    "$(BUILDDIR)/nopy/%.o: %.cpp\n"
    "\t@mkdir -p $(dir $@)\n"
    "\t$(CXX) $(CXXFLAGS) -MMD -MP -c $< -o $@"
)

# IMPORTANT (the one non-obvious gotcha, unchanged from the pre-v1.0.0 Makefile):
# GNU Make expands a rule's target/prerequisite text IMMEDIATELY when that rule
# line is parsed - top to bottom, in file order - even though OBJS is an ordinary
# recursively-expanded (`=`) variable. Only *recipe* (command) lines are expanded
# later, at execution time. So UDT_CXX_SOURCES/UDT_CXX_OBJS_REL/UDT_CXX_OBJS_NOPY/
# CXX/CXXFLAGS must be defined BEFORE the "$(OUTPUT): $(OBJS)" / "$(OUTPUT_NOPY):
# $(OBJS_NOPY)" rule lines further down. Defining this block right after CC/
# CXX_LINK, ahead of the OBJS block, sidesteps the trap entirely - same fix as
# before, just re-verified against the new file layout.
UDT_CXX_DEFS = (
    "\n\n# UDT cutter (vendored, GPLv2 - see udt/COPYING.txt), C++ built separately.\n"
    "# Two object lists (rel/nopy only - matches which two outputs get $(CXX_LINK)\n"
    "# below; debug/nopy_debug are not patched, same scope as before v1.0.0).\n"
    "UDT_CXX_SOURCES = $(wildcard udt/src/*.cpp) udt/bridge.cpp\n"
    "UDT_CXX_OBJS_REL = $(UDT_CXX_SOURCES:%.cpp=$(BUILDDIR)/rel/%.o)\n"
    "UDT_CXX_OBJS_NOPY = $(UDT_CXX_SOURCES:%.cpp=$(BUILDDIR)/nopy/%.o)\n"
    "CXX = g++\n"
    "CXXFLAGS = -std=c++14 -fPIC -Iudt/include -Iudt/src -O2\n"
)


def copy_udt(build_dir: Path) -> int:
    """Materialise minqlxtended-patches/udt/ into <build_dir>/udt/.

    Content-compare per file rather than shutil.copytree()/copy2() over the
    whole tree unconditionally: copy2 rewrites mtime, and every rewritten
    .cpp/.hpp would force `make` to rebuild ~132 C++ translation units on
    every single install run even when nothing changed. Only genuinely
    differing (or missing) files are written, so a re-run of the installer is
    a no-op for the vendored tree - the same "already patched" idempotency the
    Makefile edits below get from MARKER.

    Nothing is ever deleted from <build_dir>/udt/: the stale .o files left by
    a previous build live there too (now under build/{rel,nopy}/udt/... in
    v1.0.0's per-target object trees), and `make clean`'s `$(RM) -r
    $(BUILDDIR)` already removes them for free - unlike the old flat
    Makefile, this script no longer needs to patch `clean` itself.
    """
    if not UDT_SRC.is_dir():
        raise SystemExit(f"vendored UDT sources missing: {UDT_SRC}")
    dest_root = build_dir / "udt"
    copied = 0
    for src in sorted(UDT_SRC.rglob("*")):
        rel = src.relative_to(UDT_SRC)
        dest = dest_root / rel
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        if dest.is_file() and dest.read_bytes() == src.read_bytes():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    return copied


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    if OLD_OBJS_BLOCK not in text:
        raise SystemExit(f"OBJS block anchor missing/changed in {path}")
    if OLD_LINK_ALL not in text or OLD_LINK_NOPY not in text:
        raise SystemExit(f"link-recipe anchor(s) missing/changed in {path}")
    if OLD_NOPYDBG_RULE not in text:
        raise SystemExit(f"nopydbg pattern-rule anchor missing/changed in {path}")

    text = text.replace(OLD_OBJS_BLOCK, NEW_OBJS_BLOCK, 1)
    # Link both `all` and `nopy` outputs with g++ instead of gcc so
    # libstdc++ resolves automatically - simpler and more portable across
    # distros than hand-picking -lstdc++ on each LDFLAGS* variable. The
    # UDT_CXX_DEFS block goes right here too (see the ordering note above) -
    # this is before OBJS/OBJS_NOPY are defined, well before the
    # $(OUTPUT)/$(OUTPUT_NOPY) rules that expand them.
    text = text.replace("CC = gcc", "CC = gcc\nCXX_LINK = g++" + UDT_CXX_DEFS, 1)
    text = text.replace(OLD_LINK_ALL, NEW_LINK_ALL, 1)
    text = text.replace(OLD_LINK_NOPY, NEW_LINK_NOPY, 1)
    text = text.replace(OLD_NOPYDBG_RULE, NEW_CPP_PATTERN_RULES, 1)
    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    # Arguments may be either a minqlxtended-build *directory* (what
    # patch-minqlxtended-qlhub.py passes every patch script, and what this one
    # now needs anyway - it has a udt/ tree to place, not just a Makefile to
    # edit) or, for backwards compatibility with how this script was invoked
    # by hand during Task 2, a path to the Makefile itself.
    targets = [Path(p) for p in sys.argv[1:]] or [Path.home() / "minqlxtended-build"]
    for target in targets:
        if target.is_dir():
            build_dir, makefile = target, target / "Makefile"
        else:
            build_dir, makefile = target.parent, target
        if not makefile.is_file():
            print(f"skip (missing): {makefile}")
            continue
        copied = copy_udt(build_dir)
        print(
            f"vendored udt/ up to date: {build_dir / 'udt'}"
            if copied == 0
            else f"copied {copied} vendored udt/ file(s) -> {build_dir / 'udt'}"
        )
        if patch_file(makefile):
            print(f"patched demo-cutter build: {makefile}")
        else:
            print(f"already patched demo-cutter build: {makefile}")


if __name__ == "__main__":
    main()
