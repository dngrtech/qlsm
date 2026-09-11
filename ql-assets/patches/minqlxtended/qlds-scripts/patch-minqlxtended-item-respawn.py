#!/usr/bin/env python3
"""Lab: vanilla item touch + engine think/nextthink respawn on original map entity."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PATCH_C = REPO_ROOT / "minqlxtended-patches" / "qlhub_item_respawn.c"
PATCH_H = REPO_ROOT / "minqlxtended-patches" / "qlhub_item_respawn.h"
PATCH_EVENTS_C = REPO_ROOT / "minqlxtended-patches" / "qlhub_item_events.c"
MARKER = "qlhub_set_item_respawn_delay"

# qlhub_item_events.c is copied to the build-tree ROOT (not under src/) and
# patch-minqlxtended-item-events.py appends it as the last line of
# COMMON_SOURCES's backslash-continued list (v1.0.0's Makefile layout - see
# that script's own comment for why it always ends up last, regardless of
# whether patch-minqlxtended-demo-match.py has already run). qlhub_item_respawn.c
# is copied the same way, so it just gets chained on as one more continuation
# line after it.
MK_ITEM_EVENTS_LINE = "                 qlhub_item_events.c"
MK_ITEM_RESPAWN_SUFFIX = " \\\n                 qlhub_item_respawn.c"

# python_embed.c moved under src/python/ in v1.0.0 (patch_build_dir below), and
# the EMBED_BODY this script inserts into it still does
# `#include "qlhub_item_respawn.h"` - a build-tree-ROOT file (same convention
# as qlhub_item_events.c/.c - see that script's own comment on why). A quoted
# #include only searches the including file's own directory by default, so
# without -I. on the compile line that no longer resolves once python_embed.c
# is not itself at the build root. patch-minqlxtended-demo-match.py (Task 2)
# happens to add the same -I. for udt/bridge.h's sake, so in the real
# orchestrator order this is already present by the time this runs - but this
# script must not silently depend on another task's patch having run, so it
# adds -I. itself too (idempotent either way: checked by substring, not by
# which script put it there).
MK_CFLAGS_ANCHOR = "CFLAGS += $(EXTRA_CFLAGS)"
MK_CFLAGS_MARKER = "CFLAGS += -I."
MK_CFLAGS_NEW = (
    "CFLAGS += $(EXTRA_CFLAGS)\n"
    "# qlhub_item_respawn.c's EMBED_BODY (in python_embed.c, now under src/python/)\n"
    "# includes \"qlhub_item_respawn.h\", which lives at the build-tree root.\n"
    "CFLAGS += -I."
)


def _patch_makefile_cflags(makefile: Path) -> bool:
    text = makefile.read_text(encoding="utf-8")
    if MK_CFLAGS_MARKER in text:
        return False
    if MK_CFLAGS_ANCHOR not in text:
        raise SystemExit(f"CFLAGS += $(EXTRA_CFLAGS) anchor missing/changed in {makefile}")
    makefile.write_text(text.replace(MK_CFLAGS_ANCHOR, MK_CFLAGS_NEW, 1), encoding="utf-8")
    return True

EMBED_BODY = """
/*
 * ================================================================
 *              qlhub map item respawn (lab)
 * ================================================================
 */

#include "qlhub_item_respawn.h"

static PyObject* PyMinqlxtended_TouchMapItem(PyObject* self, PyObject* args) {
    int entity_id, client_id;
    char errbuf[256];
    if (!PyArg_ParseTuple(args, "ii:touch_map_item", &entity_id, &client_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    if (!qlhub_touch_map_item(entity_id, client_id, errbuf, (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "touch_map_item failed");
        return NULL;
    }
    Py_RETURN_TRUE;
}

static PyObject* PyMinqlxtended_SetItemRespawnDelay(PyObject* self, PyObject* args) {
    int entity_id, delay_ms;
    char errbuf[256];
    if (!PyArg_ParseTuple(args, "ii:set_item_respawn_delay", &entity_id, &delay_ms)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    if (!qlhub_set_item_respawn_delay(entity_id, delay_ms, errbuf, (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "set_item_respawn_delay failed");
        return NULL;
    }
    Py_RETURN_TRUE;
}

static PyObject* PyMinqlxtended_GetMapItemState(PyObject* self, PyObject* args) {
    int entity_id;
    int inuse = 0;
    int etype = 0;
    int eflags = 0;
    int contents = 0;
    int nextthink = 0;
    int has_think = 0;
    int level_time = 0;
    char classname[128];
    char errbuf[256];

    if (!PyArg_ParseTuple(args, "i:get_map_item_state", &entity_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    classname[0] = '\\0';
    if (!qlhub_get_map_item_state(
        entity_id,
        &inuse,
        &etype,
        &eflags,
        &contents,
        &nextthink,
        &has_think,
        &level_time,
        classname,
        (int)sizeof(classname),
        errbuf,
        (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "get_map_item_state failed");
        return NULL;
    }
    return Py_BuildValue(
        "(iiiiiiis)",
        inuse,
        etype,
        eflags,
        contents,
        nextthink,
        has_think,
        level_time,
        classname);
}

static PyObject* PyMinqlxtended_HideMapItem(PyObject* self, PyObject* args) {
    int entity_id;
    int item_id = 0;
    char errbuf[256];
    if (!PyArg_ParseTuple(args, "i|i:hide_map_item", &entity_id, &item_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    if (!qlhub_hide_map_item_for(entity_id, item_id, errbuf, (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "hide_map_item failed");
        return NULL;
    }
    Py_RETURN_TRUE;
}

static PyObject* PyMinqlxtended_ShowMapItem(PyObject* self, PyObject* args) {
    int entity_id;
    int item_id = 0;
    char errbuf[256];
    if (!PyArg_ParseTuple(args, "i|i:show_map_item", &entity_id, &item_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    if (!qlhub_show_map_item_for(entity_id, item_id, errbuf, (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "show_map_item failed");
        return NULL;
    }
    Py_RETURN_TRUE;
}

static PyObject* PyMinqlxtended_FindMapItemEntity(PyObject* self, PyObject* args) {
    float x;
    float y;
    float z;
    float radius = 96.0f;
    int want_item_id = 0;
    int exclude_entity_id = -1;
    int entity_id = -1;
    char errbuf[256];

    if (!PyArg_ParseTuple(args, "fff|fii:find_map_item_entity", &x, &y, &z, &radius, &want_item_id, &exclude_entity_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    if (!qlhub_find_map_item_entity(x, y, z, radius, want_item_id, exclude_entity_id, &entity_id, errbuf, (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "find_map_item_entity failed");
        return NULL;
    }
    return Py_BuildValue("i", entity_id);
}

static PyObject* PyMinqlxtended_SetPickupLock(PyObject* self, PyObject* args) {
    int active;
    if (!PyArg_ParseTuple(args, "i:set_pickup_lock", &active)) {
        return NULL;
    }
    qlhub_set_pickup_lock(active);
    Py_RETURN_TRUE;
}

"""

METHOD_INSERT = (
    '    {"touch_map_item", PyMinqlxtended_TouchMapItem, METH_VARARGS,\n'
    '     "Vanilla Touch_Item on map entity (real pickup)."},\n'
    '    {"hide_map_item", PyMinqlxtended_HideMapItem, METH_VARARGS,\n'
    '     "Hide map item (same entity, no think)."},\n'
    '    {"show_map_item", PyMinqlxtended_ShowMapItem, METH_VARARGS,\n'
    '     "Show map item hidden by hide_map_item / set_item_respawn_delay."},\n'
    '    {"find_map_item_entity", PyMinqlxtended_FindMapItemEntity, METH_VARARGS,\n'
    '     "Find ET_ITEM entity id near xyz (optional radius, want_item_id)."},\n'
    '    {"set_item_respawn_delay", PyMinqlxtended_SetItemRespawnDelay, METH_VARARGS,\n'
    '     "Hide map item; respawn same entity via think after delay_ms (level.time)."},\n'
    '    {"get_map_item_state", PyMinqlxtended_GetMapItemState, METH_VARARGS,\n'
    '     "Return (inuse,etype,eflags,contents,nextthink,has_think,level_time,classname) tuple."},\n'
    '    {"set_pickup_lock", PyMinqlxtended_SetPickupLock, METH_VARARGS,\n'
    '     "Block player map-item Touch_Item while match restore applies (1=lock)."},\n'
)

ANCHOR = "// force_weapon_respawn_time"


def patch_file(path: Path, old: str, new: str, *, required: bool = True) -> bool:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return False
    if old not in text:
        if required:
            raise SystemExit(f"marker missing in {path}: {old[:72]!r}...")
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def upgrade_embed_get_state_v2(text: str) -> tuple[str, bool]:
    old_fn = """static PyObject* PyMinqlxtended_GetMapItemState(PyObject* self, PyObject* args) {
    int entity_id;
    int inuse = 0;
    int etype = 0;
    int eflags = 0;
    int nextthink = 0;
    int has_think = 0;
    int level_time = 0;
    char classname[128];
    char errbuf[256];

    if (!PyArg_ParseTuple(args, "i:get_map_item_state", &entity_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    classname[0] = '\\0';
    if (!qlhub_get_map_item_state(
        entity_id,
        &inuse,
        &etype,
        &eflags,
        &nextthink,
        &has_think,
        &level_time,
        classname,
        (int)sizeof(classname),
        errbuf,
        (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "get_map_item_state failed");
        return NULL;
    }
    return Py_BuildValue(
        "(iiiiiis)",
        inuse,
        etype,
        eflags,
        nextthink,
        has_think,
        level_time,
        classname);
}"""
    new_fn = """static PyObject* PyMinqlxtended_GetMapItemState(PyObject* self, PyObject* args) {
    int entity_id;
    int inuse = 0;
    int etype = 0;
    int eflags = 0;
    int contents = 0;
    int nextthink = 0;
    int has_think = 0;
    int level_time = 0;
    char classname[128];
    char errbuf[256];

    if (!PyArg_ParseTuple(args, "i:get_map_item_state", &entity_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    classname[0] = '\\0';
    if (!qlhub_get_map_item_state(
        entity_id,
        &inuse,
        &etype,
        &eflags,
        &contents,
        &nextthink,
        &has_think,
        &level_time,
        classname,
        (int)sizeof(classname),
        errbuf,
        (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "get_map_item_state failed");
        return NULL;
    }
    return Py_BuildValue(
        "(iiiiiiis)",
        inuse,
        etype,
        eflags,
        contents,
        nextthink,
        has_think,
        level_time,
        classname);
}"""
    if old_fn in text:
        return text.replace(old_fn, new_fn, 1), True
    if "int contents = 0" in text and "(iiiiiiis)" in text:
        return text, False
    return text, False


def fix_buildvalue_format_v33(text: str) -> tuple[str, bool]:
    broken = """    return Py_BuildValue(
        "(iiiiiis)",
        inuse,
        etype,
        eflags,
        contents,
        nextthink,
        has_think,
        level_time,
        classname);"""
    fixed = """    return Py_BuildValue(
        "(iiiiiiis)",
        inuse,
        etype,
        eflags,
        contents,
        nextthink,
        has_think,
        level_time,
        classname);"""
    if broken in text:
        return text.replace(broken, fixed, 1), True
    return text, False


def upgrade_embed_hide_show_v35(text: str) -> tuple[str, bool]:
    if "PyMinqlxtended_HideMapItem" in text:
        return text, False
    anchor = "static PyObject* PyMinqlxtended_SetItemRespawnDelay"
    if anchor not in text:
        return text, False
    insert = """static PyObject* PyMinqlxtended_HideMapItem(PyObject* self, PyObject* args) {
    int entity_id;
    int item_id = 0;
    char errbuf[256];
    if (!PyArg_ParseTuple(args, "i|i:hide_map_item", &entity_id, &item_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    if (!qlhub_hide_map_item_for(entity_id, item_id, errbuf, (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "hide_map_item failed");
        return NULL;
    }
    Py_RETURN_TRUE;
}

static PyObject* PyMinqlxtended_ShowMapItem(PyObject* self, PyObject* args) {
    int entity_id;
    int item_id = 0;
    char errbuf[256];
    if (!PyArg_ParseTuple(args, "i|i:show_map_item", &entity_id, &item_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    if (!qlhub_show_map_item_for(entity_id, item_id, errbuf, (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "show_map_item failed");
        return NULL;
    }
    Py_RETURN_TRUE;
}

"""
    text = text.replace(anchor, insert + anchor, 1)
    method_anchor = '    {"set_item_respawn_delay", PyMinqlxtended_SetItemRespawnDelay, METH_VARARGS,'
    method_insert = (
        '    {"hide_map_item", PyMinqlxtended_HideMapItem, METH_VARARGS,\n'
        '     "Hide map item (same entity, no think)."},\n'
        '    {"show_map_item", PyMinqlxtended_ShowMapItem, METH_VARARGS,\n'
        '     "Show map item hidden by hide_map_item / set_item_respawn_delay."},\n'
    )
    if method_insert.strip() not in text and method_anchor in text:
        text = text.replace(method_anchor, method_insert + method_anchor, 1)
    return text, True


def upgrade_embed_find_v37(text: str) -> tuple[str, bool]:
    if "PyMinqlxtended_FindMapItemEntity" in text:
        return text, False
    anchor = '    {"set_item_respawn_delay", PyMinqlxtended_SetItemRespawnDelay, METH_VARARGS,'
    if anchor not in text:
        return text, False
    insert_fn = """
static PyObject* PyMinqlxtended_FindMapItemEntity(PyObject* self, PyObject* args) {
    float x;
    float y;
    float z;
    float radius = 96.0f;
    int want_item_id = 0;
    int exclude_entity_id = -1;
    int entity_id = -1;
    char errbuf[256];

    if (!PyArg_ParseTuple(args, "fff|fii:find_map_item_entity", &x, &y, &z, &radius, &want_item_id, &exclude_entity_id)) {
        return NULL;
    }
    errbuf[0] = '\\0';
    if (!qlhub_find_map_item_entity(x, y, z, radius, want_item_id, exclude_entity_id, &entity_id, errbuf, (int)sizeof(errbuf))) {
        PyErr_SetString(PyExc_ValueError, errbuf[0] ? errbuf : "find_map_item_entity failed");
        return NULL;
    }
    return Py_BuildValue("i", entity_id);
}

"""
    insert_method = (
        '    {"find_map_item_entity", PyMinqlxtended_FindMapItemEntity, METH_VARARGS,\n'
        '     "Find ET_ITEM entity id near xyz (optional radius, want_item_id)."},\n'
    )
    text = text.replace(
        "static PyObject* PyMinqlxtended_SetItemRespawnDelay",
        insert_fn + "static PyObject* PyMinqlxtended_SetItemRespawnDelay",
        1,
    )
    text = text.replace(anchor, insert_method + anchor, 1)
    return text, True


def upgrade_embed_find_exclude_v56(text: str) -> tuple[str, bool]:
    if "exclude_entity_id" in text and "fff|fii:find_map_item_entity" in text:
        return text, False
    old_parse = 'if (!PyArg_ParseTuple(args, "fff|fi:find_map_item_entity", &x, &y, &z, &radius, &want_item_id)) {'
    if old_parse not in text:
        return text, False
    text = text.replace(
        old_parse,
        'if (!PyArg_ParseTuple(args, "fff|fii:find_map_item_entity", &x, &y, &z, &radius, &want_item_id, &exclude_entity_id)) {',
        1,
    )
    text = text.replace(
        "    int want_item_id = 0;\n    int entity_id = -1;",
        "    int want_item_id = 0;\n    int exclude_entity_id = -1;\n    int entity_id = -1;",
        1,
    )
    text = text.replace(
        "qlhub_find_map_item_entity(x, y, z, radius, want_item_id, &entity_id, errbuf, (int)sizeof(errbuf))",
        "qlhub_find_map_item_entity(x, y, z, radius, want_item_id, exclude_entity_id, &entity_id, errbuf, (int)sizeof(errbuf))",
        1,
    )
    return text, True


def upgrade_embed_pickup_lock_v49(text: str) -> tuple[str, bool]:
    if "PyMinqlxtended_SetPickupLock" in text:
        return text, False
    anchor = '    {"get_map_item_state", PyMinqlxtended_GetMapItemState, METH_VARARGS,'
    if anchor not in text:
        return text, False
    fn = """
static PyObject* PyMinqlxtended_SetPickupLock(PyObject* self, PyObject* args) {
    int active;
    if (!PyArg_ParseTuple(args, "i:set_pickup_lock", &active)) {
        return NULL;
    }
    qlhub_set_pickup_lock(active);
    Py_RETURN_TRUE;
}

"""
    insert_anchor = "static PyObject* PyMinqlxtended_FindMapItemEntity"
    if insert_anchor in text:
        text = text.replace(insert_anchor, fn + insert_anchor, 1)
    method_insert = (
        '    {"set_pickup_lock", PyMinqlxtended_SetPickupLock, METH_VARARGS,\n'
        '     "Block player map-item Touch_Item while match restore applies (1=lock)."},\n'
    )
    text = text.replace(anchor, method_insert + anchor, 1)
    return text, True


def patch_embed(embed: Path) -> bool:
    text = embed.read_text(encoding="utf-8")
    changed = False
    text, upgraded = upgrade_embed_get_state_v2(text)
    if upgraded:
        changed = True
    text, fixed_fmt = fix_buildvalue_format_v33(text)
    if fixed_fmt:
        changed = True
    text, hide_show = upgrade_embed_hide_show_v35(text)
    if hide_show:
        changed = True
    text, find_fn = upgrade_embed_find_v37(text)
    if find_fn:
        changed = True
    text, find_ex = upgrade_embed_find_exclude_v56(text)
    if find_ex:
        changed = True
    text, pickup_lock = upgrade_embed_pickup_lock_v49(text)
    if pickup_lock:
        changed = True
    if "(int)sizeof(errbuf),\n    ))" in text:
        text = text.replace(
            "(int)sizeof(errbuf),\n    ))",
            "(int)sizeof(errbuf)))",
            1,
        )
        changed = True
    if "level_time,\n        classname,\n    );" in text:
        text = text.replace(
            "level_time,\n        classname,\n    );",
            "level_time,\n        classname);",
            1,
        )
        changed = True
    if MARKER in text:
        if changed:
            embed.write_text(text, encoding="utf-8")
        return changed
    if ANCHOR not in text:
        raise SystemExit(f"force_weapon_respawn_time anchor missing in {embed}")
    text = text.replace(ANCHOR, EMBED_BODY + ANCHOR, 1)
    method_anchor = '    {"force_weapon_respawn_time", PyMinqlxtended_ForceWeaponRespawnTime, METH_VARARGS,'
    if METHOD_INSERT.strip() in text:
        embed.write_text(text, encoding="utf-8")
        return False
    if method_anchor not in text:
        raise SystemExit(f"method table anchor missing in {embed}")
    text = text.replace(method_anchor, METHOD_INSERT + method_anchor, 1)
    embed.write_text(text, encoding="utf-8")
    return True


def _patch_makefile_sources(makefile: Path) -> bool:
    """Append qlhub_item_respawn.c to COMMON_SOURCES, right after
    qlhub_item_events.c (patch-minqlxtended-item-events.py must run first -
    it is the one that materialises that anchor line)."""
    text = makefile.read_text(encoding="utf-8")
    if "qlhub_item_respawn.c" in text:
        return False
    if MK_ITEM_EVENTS_LINE not in text:
        raise SystemExit(
            f"COMMON_SOURCES qlhub_item_events.c line missing in {makefile} — "
            "run patch-minqlxtended-item-events.py first"
        )
    makefile.write_text(
        text.replace(MK_ITEM_EVENTS_LINE, MK_ITEM_EVENTS_LINE + MK_ITEM_RESPAWN_SUFFIX, 1),
        encoding="utf-8",
    )
    return True


def _assert_makefile_sources(makefile: Path) -> None:
    text = makefile.read_text(encoding="utf-8")
    missing = [
        name
        for name in ("qlhub_item_events.c", "qlhub_item_respawn.c")
        if name not in text
    ]
    if missing:
        raise SystemExit(
            "Makefile missing {} — run patch-minqlxtended-qlhub.py (item-events before item-respawn)".format(
                ", ".join(missing)
            )
        )


def patch_build_dir(build_dir: Path) -> None:
    if not build_dir.is_dir():
        raise SystemExit(f"build dir not found: {build_dir}")

    events_dest = build_dir / PATCH_EVENTS_C.name
    if not events_dest.is_file() and PATCH_EVENTS_C.is_file():
        shutil.copy2(PATCH_EVENTS_C, events_dest)
        print(f"copied missing: {PATCH_EVENTS_C.name}")

    shutil.copy2(PATCH_C, build_dir / PATCH_C.name)
    shutil.copy2(PATCH_H, build_dir / PATCH_H.name)
    print(f"copied: {PATCH_C.name}, {PATCH_H.name}")

    makefile = build_dir / "Makefile"
    if _patch_makefile_sources(makefile):
        print("patched Makefile COMMON_SOURCES")
    else:
        print("Makefile already has qlhub_item_respawn.c")
    if _patch_makefile_cflags(makefile):
        print("patched Makefile CFLAGS (-I.)")

    _assert_makefile_sources(makefile)
    if not events_dest.is_file():
        raise SystemExit(f"missing {events_dest} — item-events sources not in build tree")

    embed = build_dir / "src" / "python" / "python_embed.c"
    if patch_embed(embed):
        print(f"patched python_embed: {embed}")


def main() -> None:
    build_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "minqlxtended-build"
    patch_build_dir(build_dir)
    print("item-respawn patch done")


if __name__ == "__main__":
    main()
