#!/usr/bin/env python3
"""Add minqlxtended.set_position(client_id, Vector3) to python_embed.c (match restore lab).

v1.0.0 replaced most per-client setter functions with typed attribute objects
(Entity.health, GameClient.ps.viewangles, level.time, ...), but set_position has
no single-attribute equivalent: a real teleport has to write four different
struct mirrors atomically (ps.origin, r.currentOrigin, s.origin, s.pos.trBase),
zero velocity and flip the teleport bit, all in one call - exactly the kind of
setter the upstream module table's own comment carves out an exception for:

    /* No per-client setters here. Writable fields are accessors on Entity,
     * GameClient and level; what follows is what those views cannot express. */

So this script still exists post-port, just re-anchored onto v1.0.0's
restructured src/python/python_embed.c (moved from the build-tree root; see
patch-minqlxtended-item-respawn.py's header comment for why). The function body
itself is unchanged from the pre-port patch - vector3_type, sv_maxclients,
g_entities and PyStructSequence_GetItem are all engine/CPython-level names the
typed-attribute refactor didn't touch.

Anchored on the module method table's `{NULL, NULL, 0, NULL}};` sentinel for the
method-table row, the same anchor patch-minqlxtended-demo-bindings.py (Task 2)
inserts its own `demo_arm`/`demo_disarm` entries before. That is safe in any
run order: each script's own MARKER check (below) is verified BEFORE any
anchor-based text replacement is attempted, so neither script ever re-derives
its idempotency from being textually adjacent to the sentinel or to the other
script's insertion - only from whether its own function name is already in the
file. (A different insertion in this same repo's patch-minqlxtended-item-events.py
originally got this wrong - checked adjacency to a shared anchor instead of a
stable marker - and silently duplicated a function definition on a second
full-orchestrator run; fixed in ffdc60d/c40eaa6. This script was written the
safe way from the start: MARKER is checked first, and the function-body +
method-table edits only ever happen together in the same write.)
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PyMinqlxtended_SetPosition"

# Unique in the file; not touched by any other patch-minqlxtended-*.py script
# (verified via grep across qlds-scripts/ at implementation time).
FUNC_ANCHOR = "// drop_holdable\n"

FUNC_BODY = """// set_position

static PyObject* PyMinqlxtended_SetPosition(PyObject* self, PyObject* args) {
    int client_id;
    PyObject* new_position;
    gentity_t* ent;
    vec3_t origin;
    int i;

    if (!PyArg_ParseTuple(args, "iO:set_position", &client_id, &new_position)) {
        return NULL;
    } else if (client_id < 0 || client_id >= sv_maxclients->integer) {
        PyErr_Format(PyExc_ValueError,
                     "client_id needs to be a number from 0 to %d.",
                     sv_maxclients->integer);
        return NULL;
    } else if (!g_entities[client_id].client) {
        Py_RETURN_FALSE;
    } else if (!PyObject_TypeCheck(new_position, &vector3_type)) {
        PyErr_Format(PyExc_ValueError, "Argument must be of type minqlxtended.Vector3.");
        return NULL;
    }

    origin[0] = (float)PyFloat_AsDouble(PyStructSequence_GetItem(new_position, 0));
    origin[1] = (float)PyFloat_AsDouble(PyStructSequence_GetItem(new_position, 1));
    origin[2] = (float)PyFloat_AsDouble(PyStructSequence_GetItem(new_position, 2));

    ent = &g_entities[client_id];
    for (i = 0; i < 3; i++) {
        ent->client->ps.origin[i] = origin[i];
        ent->r.currentOrigin[i] = origin[i];
        ent->s.origin[i] = origin[i];
        ent->s.pos.trBase[i] = origin[i];
    }
    ent->s.pos.trType = TR_STATIONARY;
    ent->client->ps.velocity[0] = 0.0f;
    ent->client->ps.velocity[1] = 0.0f;
    ent->client->ps.velocity[2] = 0.0f;
    ent->client->ps.eFlags ^= EF_TELEPORT_BIT;

    Py_RETURN_TRUE;
}

"""

# Shared with patch-minqlxtended-demo-bindings.py (Task 2's demo_arm/demo_disarm
# entries also insert before this same sentinel) - safe because both scripts
# gate on their own MARKER first, see module docstring above.
METHOD_ANCHOR = "    {NULL, NULL, 0, NULL}};\n"
METHOD_INSERT = (
    '    {"set_position", PyMinqlxtended_SetPosition, METH_VARARGS,\n'
    '     "set_position(client_id, position) -- atomically writes ps.origin, "\n'
    '     "r.currentOrigin, s.origin and s.pos.trBase together with a teleport "\n'
    '     "flag flip; a four-field write no single typed attribute can express."},\n'
)


def _resolve_target(path: Path) -> Path:
    if path.is_dir():
        return path / "src" / "python" / "python_embed.c"
    return path


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    if FUNC_ANCHOR not in text:
        raise SystemExit(f"drop_holdable anchor missing in {path}")
    if METHOD_ANCHOR not in text:
        raise SystemExit(f"minqlxtendedMethods[] sentinel missing in {path}")
    text = text.replace(FUNC_ANCHOR, FUNC_BODY + FUNC_ANCHOR, 1)
    text = text.replace(METHOD_ANCHOR, METHOD_INSERT + METHOD_ANCHOR, 1)
    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    if len(sys.argv) > 1:
        targets = [_resolve_target(Path(p)) for p in sys.argv[1:]]
    else:
        targets = [Path.home() / "minqlxtended-build/src/python/python_embed.c"]
    for path in targets:
        if not path.is_file():
            print(f"skip (missing): {path}")
            continue
        if patch_file(path):
            print(f"patched set_position: {path}")
        else:
            print(f"already patched set_position: {path}")


if __name__ == "__main__":
    main()
