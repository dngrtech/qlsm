#!/usr/bin/env python3
"""Add minqlxtended.demo_arm(match_id, map_name)/demo_disarm() bindings and
the demo_recording_started/demo_match_finalized events to minqlxtended-build.

patch-minqlxtended-demo-match.py leaves two inert `TASK5-HOOK` comment markers
in src/features/demo_match.c where the real dispatcher calls belong, because the
dispatcher functions do not exist yet:

    demo_match.c: DemoRecordingStartedDispatcher(...) in demo_seg_arm()
    demo_match.c: DemoMatchFinalizedDispatcher(...)   in demo_finalize_main()

This script wires up both ends: the Python-callable C functions
(demo_arm/demo_disarm, calling DemoMatch_Arm/DemoMatch_Disarm), the two
dispatcher functions that call from C into registered Python handlers, and the
Python-side event/handler plumbing that exposes them as minqlxtended events.

demo_seg_arm() runs only on the game thread (called from the G_RunFrame hook and
from DemoMatch_Arm), so its dispatcher call needs no special handling.
demo_finalize_main() is a dedicated pthread-created finalize thread;
PyGILState_Ensure()/DispatcherRelease() (used identically to every other
dispatcher in python_dispatchers.c) is CPython's own sanctioned mechanism for
calling into Python from any OS thread, so the call is safe as-is. The constraint
that creates lands on the *Python-side handler* for demo_match_finalized: it must
not read live game-thread state, since it can fire concurrently with game-thread
activity for a later, unrelated match. Cvar reads (get_cvar) are fine - a cvar is
a stable process-wide string, not per-frame game state, and the one real consumer
(addons/native-demo/minqlx/demo_native_autorecord.py) needs
qlx_nativeDemoRecordEnabled / fs_homepath / sv_demoDir to locate the demo
directory. What is off limits is anything that walks the game module: players(),
Player objects, Entity/GameClient, client_t. See the comment left on
DemoMatchFinalizedDispatcher itself.

demo_match.c is compiled into *both* the pygame build and the `nopy` build (it is
in COMMON_SOURCES), but python_embed.c/python_dispatchers.c are pygame-only. So
demo_match.c already carries its own `#ifndef NOPY` guard around the
`#include "python/pyminqlxtended.h"`, and the two markers this script replaces are
inside `#ifndef NOPY` blocks it inserts - or `make nopy` fails to link. That is
why, unlike the pre-v1.0.0 version of this script, there is no include patch here:
demo_match.c is our own file and ships with the guarded include already in place.

------------------------------------------------------------------------------
Resolved here (the design spec left it open): upstream v1.0.0 now has its own
`demo_finished(client_id, path, size, discarded, failed)` Python event, fired for
every segment its writer closes. It is NOT folded into, or replaced by, our
demo_recording_started/demo_match_finalized:

  * demo_finished reports a *capture* completing. Our events report a *match*
    being attributed and then packaged - a different lifecycle, at a different
    time, keyed by match_id rather than client id.
  * addons/native-demo/minqlx/demo_native_autorecord.py consumes both of ours and
    could not be simplified by consuming demo_finished instead: it needs the
    final, match-named path at arm time (demo_recording_started) and a single
    once-per-match signal after the two-stage cut and index have run
    (demo_match_finalized), neither of which demo_finished carries.
  * C-side, demo_match.c does consume the same completions demo_finished is built
    from - but through DemoMatch_OnFinished(), inside upstream's existing drain,
    not by re-entering Python.

So upstream's event stays exactly as it is, ours stay exactly as they were, and
the already-tested Python layer from the original plan is untouched.
------------------------------------------------------------------------------

All source paths below are v1.0.0's (src/python/..., src/features/...); the
anchors were re-verified against a pristine clone of tjone270/minqlxtended at
1e2f307. Where an anchor used to sit on something another patch in this chain
had added (the item_event handler/dispatcher entries), it has been moved onto
upstream's own demo_finished plumbing instead, so this script no longer depends
on patch-minqlxtended-item-events.py having run first.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "demo_recording_started_handler"

# ---------------------------------------------------------------------------
# src/python/pyminqlxtended.h
# ---------------------------------------------------------------------------

H_EXTERN_ANCHOR = "extern PyObject* kamikaze_explode_handler;\n"
H_EXTERN_INSERT = (
    "extern PyObject* demo_recording_started_handler;\n"
    "extern PyObject* demo_match_finalized_handler;\n"
)

H_ENDIF_ANCHOR = "#endif /* PYMINQLXTENDED_H */"
H_PROTO_INSERT = (
    "void DemoRecordingStartedDispatcher(int slot, const char* path, const char* name);\n"
    "\n"
    "// Fired from the dedicated demo finalize thread (demo_match.c), not the game\n"
    "// thread. Handlers must not read live game-thread state (players(), Player,\n"
    "// Entity/GameClient, client_t); cvar reads are fine.\n"
    "void DemoMatchFinalizedDispatcher(const char* match_id);\n"
    "\n"
)

# ---------------------------------------------------------------------------
# src/python/python_embed.c
# ---------------------------------------------------------------------------

# demo_arm/demo_disarm call into demo_match.c, not demos.c; python_embed.c
# already includes features/demos.h for upstream's own bindings.
E_INCLUDE_ANCHOR = '#include "common.h"\n'
E_INCLUDE_INSERT = '#include "features/demo_match.h"\n'

# Anchored on upstream's OWN demo_finished handler rather than on the
# item_event one another patch adds, so this script has no ordering dependency
# on patch-minqlxtended-item-events.py.
E_GLOBAL_ANCHOR = "PyObject* demo_finished_handler = NULL;\n"
E_GLOBAL_INSERT = (
    "PyObject* demo_recording_started_handler = NULL;\n"
    "PyObject* demo_match_finalized_handler = NULL;\n"
)

E_TABLE_ANCHOR = '    {"demo_finished", &demo_finished_handler},\n'
E_TABLE_INSERT = (
    '    {"demo_recording_started", &demo_recording_started_handler},\n'
    '    {"demo_match_finalized", &demo_match_finalized_handler},\n'
)

# v1.0.0 stripped the boxed banner comments this used to anchor on; what is left
# is a plain one-line comment above the function.
E_FUNC_ANCHOR = """// get_userinfo

static PyObject* PyMinqlxtended_GetUserinfo(PyObject* self, PyObject* args) {"""

E_FUNC_INSERT = """// demo_arm

static PyObject* PyMinqlxtended_DemoArm(PyObject* self, PyObject* args) {
    const char* match_id;
    const char* map_name;

    if (!PyArg_ParseTuple(args, "ss:demo_arm", &match_id, &map_name)) {
        return NULL;
    }

    DemoMatch_Arm(match_id, map_name);
    Py_RETURN_NONE;
}

// demo_disarm

static PyObject* PyMinqlxtended_DemoDisarm(PyObject* self, PyObject* args) {
    (void)self;
    (void)args;
    DemoMatch_Disarm();
    Py_RETURN_NONE;
}

"""

# Anchored on minqlxtendedMethods[]'s terminating sentinel, NOT on a neighbouring
# method entry. The obvious-looking anchor here used to be the
# {"client_pointer", ...} entry, which exists only because
# patch-minqlxtended-client-pointer.py had been run by hand against the local dev
# checkout - that script is not in patch-minqlxtended-qlhub.py's list, so on a
# fresh VPS build tree the anchor was simply absent and this whole patch aborted.
# The sentinel is upstream's own and is unique in the file; inserting before it
# keeps the new entries inside the table regardless of which other optional
# patches ran. Other scripts (e.g. the set_position patch) insert before the same
# sentinel; that is safe in any order, because each script's own MARKER check
# stops it re-inserting and none of them depend on being adjacent to the others.
E_METHOD_ANCHOR = "    {NULL, NULL, 0, NULL}};\n"
E_METHOD_INSERT = (
    '    {"demo_arm", PyMinqlxtended_DemoArm, METH_VARARGS,\n'
    '     "Arms native per-player demo recording for the current match (match_id, map_name)."},\n'
    '    {"demo_disarm", PyMinqlxtended_DemoDisarm, METH_NOARGS,\n'
    '     "Disarms native per-player demo recording, closing and finalising every open file."},\n'
)

# ---------------------------------------------------------------------------
# src/python/python_dispatchers.c
#
# Uses v1.0.0's own CallHandler()/DispatcherRelease() idiom rather than raw
# PyObject_CallFunction()/PyGILState_Release(): CallHandler takes its own
# reference to the handler slot under the GIL (register_handler can clear it from
# another thread) and consumes the argument references, and DispatcherRelease
# flushes a handler's exception before releasing the GIL - without which it would
# survive into the next PyGILState_Ensure and be raised against unrelated code.
# Both are defined near the top of the file, well above this insertion point.
#
# The PROF_* probes upstream's own dispatchers carry are deliberately not
# replicated: each needs its own entry in the profiler's enum, which is not this
# patch's to extend.
# ---------------------------------------------------------------------------

D_ANCHOR = "\nvoid KamikazeExplodeDispatcher(int client_id, int is_used_on_demand) {\n"
D_INSERT = """
void DemoRecordingStartedDispatcher(int slot, const char* path, const char* name) {
    if (!demo_recording_started_handler) {
        return; // No registered handler.
    }

    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject* argv[] = {
        PyLong_FromLong(slot),
        FromEngine(path),
        FromEngine(name),
    };
    PyObject* result = CallHandler(&demo_recording_started_handler, argv, 3);

    if (result == NULL) {
        DebugError("CallHandler() returned NULL.\\n", __FILE__, __LINE__, __func__);
    }
    Py_XDECREF(result);
    DispatcherRelease(gstate);
}

// Called from demo_finalize_main() (demo_match.c), a dedicated pthread-created
// finalize thread - not the game thread, not upstream's demo writer thread.
// PyGILState_Ensure()/DispatcherRelease() are CPython's own sanctioned mechanism
// for calling into Python from any OS thread Python didn't create itself, so this
// call is exactly as safe here as it is on the game thread; no frame-queue or
// marshaling back to the game thread is needed.
//
// The constraint that DOES exist lands on the Python-side handler: since this can
// fire concurrently with game-thread activity for a later, unrelated match,
// handlers of demo_match_finalized must not read live GAME-THREAD state - anything
// that walks the game module: minqlxtended.players(), Player objects,
// Entity/GameClient, client_t fields.
//
// The match_id argument and cvar reads (minqlxtended.get_cvar) ARE safe: a cvar is
// a stable process-wide string rather than per-frame game state, which is what lets
// the one real consumer (demo_native_autorecord.py) resolve fs_homepath/sv_demoDir
// from this handler.
void DemoMatchFinalizedDispatcher(const char* match_id) {
    if (!demo_match_finalized_handler) {
        return; // No registered handler.
    }

    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject* argv[] = {
        FromEngine(match_id),
    };
    PyObject* result = CallHandler(&demo_match_finalized_handler, argv, 1);

    if (result == NULL) {
        DebugError("CallHandler() returned NULL.\\n", __FILE__, __LINE__, __func__);
    }
    Py_XDECREF(result);
    DispatcherRelease(gstate);
}
"""

# ---------------------------------------------------------------------------
# src/features/demo_match.c
#
# Only the two TASK5-HOOK markers: unlike the pre-v1.0.0 version of this script,
# there is no include to add. demo_match.c is our own file and already carries
# the #ifndef NOPY-guarded #include "python/pyminqlxtended.h".
# ---------------------------------------------------------------------------

C_HOOK1_ANCHOR = "    // TASK5-HOOK: DemoRecordingStartedDispatcher(s->slot, s->final_path, name);\n"
C_HOOK1_INSERT = (
    "#ifndef NOPY\n"
    "    DemoRecordingStartedDispatcher(s->slot, s->final_path, name);\n"
    "#endif\n"
)

C_HOOK2_ANCHOR = "            // TASK5-HOOK: DemoMatchFinalizedDispatcher(job->match_id);\n"
C_HOOK2_INSERT = (
    "#ifndef NOPY\n"
    "            DemoMatchFinalizedDispatcher(job->match_id);\n"
    "#endif\n"
)

# ---------------------------------------------------------------------------
# python/minqlxtended/_events.py
# ---------------------------------------------------------------------------

EV_CLASS_ANCHOR = '''    @override
    def dispatch(self, client_id, path, size, discarded, failed):
        return super().dispatch(client_id, path, size, discarded, failed)
'''
EV_CLASS_INSERT = '''

class DemoRecordingStartedDispatcher(EventDispatcher):
    """Fires when native per-match demo capture binds a slot's open segment to a
    match. Carries the final, match-named path the file will be published under."""
    name = "demo_recording_started"

    @override
    def dispatch(self, slot, path, name):
        return super().dispatch(slot, path, name)


class DemoMatchFinalizedDispatcher(EventDispatcher):
    """Fires when the native demo finalize thread finishes the last segment for a
    match. Runs off the game thread (a dedicated finalize thread, see
    demo_match.c's demo_finalize_main()) - handlers must not read live game-thread
    state (minqlxtended.players(), Player objects, Entity/GameClient, client_t),
    since this can fire concurrently with game-thread activity for a later,
    unrelated match. The match_id argument and cvar reads are safe.
    """
    name = "demo_match_finalized"

    @override
    def dispatch(self, match_id):
        return super().dispatch(match_id)
'''

EV_REGISTER_ANCHOR = "EVENT_DISPATCHERS.add_dispatcher(DemoFinishedDispatcher)\n"
EV_REGISTER_INSERT = (
    "EVENT_DISPATCHERS.add_dispatcher(DemoRecordingStartedDispatcher)\n"
    "EVENT_DISPATCHERS.add_dispatcher(DemoMatchFinalizedDispatcher)\n"
)

# ---------------------------------------------------------------------------
# python/minqlxtended/_handlers.py
# ---------------------------------------------------------------------------

HD_FUNC_ANCHOR = '''    try:
        return minqlxtended.EVENT_DISPATCHERS["demo_finished"].dispatch(client_id, path, size, discarded, failed)
    except:
        minqlxtended.log_exception()
        return True
'''
HD_FUNC_INSERT = '''

def handle_demo_recording_started(slot, path, name):
    try:
        return minqlxtended.EVENT_DISPATCHERS["demo_recording_started"].dispatch(
            int(slot), path, name)
    except:
        minqlxtended.log_exception()
        return True

def handle_demo_match_finalized(match_id):
    # Runs off the game thread (dedicated finalize thread - see demo_match.c's
    # demo_finalize_main()). Do not add live game-thread state reads here
    # (players(), Player, Entity/GameClient, client_t); cvar reads are fine.
    try:
        return minqlxtended.EVENT_DISPATCHERS["demo_match_finalized"].dispatch(match_id)
    except:
        minqlxtended.log_exception()
        return True
'''

HD_REGISTER_ANCHOR = '    minqlxtended.register_handler("demo_finished", handle_demo_finished)\n'
HD_REGISTER_INSERT = (
    '    minqlxtended.register_handler("demo_recording_started", handle_demo_recording_started)\n'
    '    minqlxtended.register_handler("demo_match_finalized", handle_demo_match_finalized)\n'
)

# ---------------------------------------------------------------------------
# python/minqlxtended/__init__.py
#
# python_embed.c's minqlxtendedMethods[] table (patched above) is the actual
# Python-callable surface of the _minqlxtended C extension - but plugins never
# import _minqlxtended directly, they do `import minqlxtended as minqlx`. The
# minqlxtended package only re-exports a curated, generated allowlist from
# _minqlxtended (see __init__.py's own "Generated. Run tools/gen_stub.py..."
# comment; CI runs it with --check). That generated list predates
# demo_arm/demo_disarm's addition to the method table above, so on every VPS
# built from this patch chain minqlxtended.demo_arm silently does not exist as
# a plugin-visible attribute even though _minqlxtended.demo_arm does -
# reproduced live as an on_game_countdown AttributeError with the C side
# fully compiled in.
#
# Patched independently of the MARKER short-circuit above (own anchor, own
# idempotency check on "demo_arm" already being in __init__.py's import list)
# so a build tree that already ran the other six edits before this fix
# existed still picks this one up on the next patch run instead of being
# silently skipped as "already patched".
# ---------------------------------------------------------------------------

INIT_MARKER = "demo_arm"

INIT_ANCHOR = (
    "    cvar, cvars, demo_status, destroy_kamikaze_timers, dev_print_items, drop_holdable,\n"
)
INIT_INSERT = (
    "    cvar, cvars, demo_arm, demo_disarm, demo_status, destroy_kamikaze_timers,\n"
    "    dev_print_items, drop_holdable,\n"
)


def _patch_init(root: Path) -> bool:
    path = root / "python" / "minqlxtended" / "__init__.py"
    if not path.is_file():
        raise SystemExit(f"missing file: {path}")
    text = path.read_text(encoding="utf-8")
    if INIT_MARKER in text:
        return False
    if INIT_ANCHOR not in text:
        raise SystemExit(f"anchor missing in {path}: generated function import list")
    text = text.replace(INIT_ANCHOR, INIT_INSERT, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def _apply(text: str, anchor: str, insert: str, *, after: bool, label: str, path: Path) -> str:
    if anchor not in text:
        raise SystemExit(f"anchor missing in {path}: {label}")
    if after:
        return text.replace(anchor, anchor + insert, 1)
    return text.replace(anchor, insert + anchor, 1)


def _replace(text: str, anchor: str, replacement: str, *, label: str, path: Path) -> str:
    """Replace anchor with replacement outright (anchor is NOT kept)."""
    if anchor not in text:
        raise SystemExit(f"anchor missing in {path}: {label}")
    return text.replace(anchor, replacement, 1)


def _patch_header(text: str, path: Path) -> str:
    text = _apply(text, H_EXTERN_ANCHOR, H_EXTERN_INSERT, after=True, label="kamikaze_explode_handler extern", path=path)
    text = _apply(text, H_ENDIF_ANCHOR, H_PROTO_INSERT, after=False, label="header #endif guard", path=path)
    return text


def _patch_embed(text: str, path: Path) -> str:
    text = _apply(text, E_INCLUDE_ANCHOR, E_INCLUDE_INSERT, after=True, label="common.h include", path=path)
    text = _apply(text, E_GLOBAL_ANCHOR, E_GLOBAL_INSERT, after=True, label="demo_finished_handler global", path=path)
    text = _apply(text, E_TABLE_ANCHOR, E_TABLE_INSERT, after=True, label="demo_finished handlers[] entry", path=path)
    text = _apply(text, E_FUNC_ANCHOR, E_FUNC_INSERT, after=False, label="get_userinfo function anchor", path=path)
    text = _apply(text, E_METHOD_ANCHOR, E_METHOD_INSERT, after=False, label="minqlxtendedMethods[] sentinel", path=path)
    return text


def _patch_dispatchers(text: str, path: Path) -> str:
    return _apply(text, D_ANCHOR, D_INSERT, after=False, label="KamikazeExplodeDispatcher anchor", path=path)


def _patch_demo_match(text: str, path: Path) -> str:
    text = _replace(text, C_HOOK1_ANCHOR, C_HOOK1_INSERT, label="TASK5-HOOK DemoRecordingStartedDispatcher marker", path=path)
    text = _replace(text, C_HOOK2_ANCHOR, C_HOOK2_INSERT, label="TASK5-HOOK DemoMatchFinalizedDispatcher marker", path=path)
    return text


def _patch_events(text: str, path: Path) -> str:
    text = _apply(text, EV_CLASS_ANCHOR, EV_CLASS_INSERT, after=True, label="DemoFinishedDispatcher class", path=path)
    text = _apply(text, EV_REGISTER_ANCHOR, EV_REGISTER_INSERT, after=True, label="DemoFinishedDispatcher registration", path=path)
    return text


def _patch_handlers(text: str, path: Path) -> str:
    text = _apply(text, HD_FUNC_ANCHOR, HD_FUNC_INSERT, after=True, label="handle_demo_finished function", path=path)
    text = _apply(text, HD_REGISTER_ANCHOR, HD_REGISTER_INSERT, after=True, label="demo_finished register_handler call", path=path)
    return text


_FILES = [
    ("src/python/pyminqlxtended.h", _patch_header),
    ("src/python/python_embed.c", _patch_embed),
    ("src/python/python_dispatchers.c", _patch_dispatchers),
    ("src/features/demo_match.c", _patch_demo_match),
    ("python/minqlxtended/_events.py", _patch_events),
    ("python/minqlxtended/_handlers.py", _patch_handlers),
]


def patch_file(root: Path) -> bool:
    """Patch all six files under root. All-or-nothing: every anchor across every
    file is validated before any file is written, so a missing anchor in file 6
    can never leave files 1-5 half-patched."""
    marker_check = root / "src" / "python" / "python_embed.c"
    if marker_check.is_file() and MARKER in marker_check.read_text(encoding="utf-8"):
        return False

    paths = [(root / rel, fn) for rel, fn in _FILES]
    for path, _ in paths:
        if not path.is_file():
            raise SystemExit(f"missing file: {path}")

    # Compute every new text first (raises SystemExit naming file+anchor on any
    # mismatch) before writing anything.
    originals = [path.read_text(encoding="utf-8") for path, _ in paths]
    patched = [fn(text, path) for (path, fn), text in zip(paths, originals)]

    for (path, _), new_text in zip(paths, patched):
        path.write_text(new_text, encoding="utf-8", newline="\n")

    return True


def main() -> None:
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        root = Path.home() / "minqlxtended-build"

    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    if patch_file(root):
        print(f"patched demo bindings + demo_recording_started/demo_match_finalized events: {root}")
    else:
        print(f"already patched: {root}")

    if _patch_init(root):
        print(f"patched __init__.py generated import list (demo_arm/demo_disarm): {root}")
    else:
        print(f"__init__.py already exports demo_arm/demo_disarm: {root}")


if __name__ == "__main__":
    main()
