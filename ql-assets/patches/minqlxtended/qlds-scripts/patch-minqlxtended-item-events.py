#!/usr/bin/env python3
"""Wire qlhub_item_events.c's item_event payload into upstream's own item-pickup hook.

v1.0.0 upstream ships its own function-level hook on Touch_Item
(`HOOK_VM(Touch_Item)` in src/server/hooks.c, wrapping it with `My_Touch_Item`)
and diffs `ent->pickupCount` itself to fire a native `item_pickup` event. That
retires the entire touch-repointing workaround this file used to install
(`My_QLHub_EntityTouch` + a periodic `ent->touch` rewrite of every map item,
because pre-v1.0.0 upstream never hooked Touch_Item on its own): there is now
exactly one call site for a pickup, upstream's own, and this patch just adds
one extra call there for the payload minqlxtended's Python side needs beyond
what upstream's own item_pickup carries (item_entity_id, gi_type, gi_tag,
gi_quantity, world position, game_time - `item_event` in
python/minqlxtended/_events.py, unchanged 11-arg signature and Python-visible
name from before this port).

Also carries over minqlxtended.set_pickup_lock() (used by
addons/match-restore/minqlx/match_restore.py to block real pickups while it
is mid-way through rewriting entity/player state): the old per-entity
wrapper could refuse to call the vanilla touch at all while locked, and the
same refusal now has to happen in the My_Touch_Item patch itself, before it
calls Touch_Item, since there is no wrapper left in this file to refuse from.
qlhub_set_pickup_lock/qlhub_pickup_lock_active are otherwise unrelated to the
touch-repointing workaround being retired here, so they are kept rather than
deleted (confirmed real caller via grep across qlds-scripts/ and addons/
before keeping them - see the task report).

Research finding, confirm before relying on it: this repo's `action`
parameter / "pickup"-vs-"drop" mapping in handle_item_event has never had a
real `action=1` (drop) call site anywhere in this repo, current build tree or
patch script - Drop_Item is only ever used by minqlx.drop_item()'s own
programmatic-drop Python API, never hooked to observe a real player drop.
Drop coverage was already non-functional before this port; this patch does
not add it.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PATCH_SRC = REPO_ROOT / "minqlxtended-patches" / "qlhub_item_events.c"

DISPATCHER_MARKER = '"iiisiiifffi"'


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


# ---------------------------------------------------------------------------
# Makefile: qlhub_item_events.c is copied to the build-tree ROOT (like
# qlhub_item_respawn.c / .h - see patch-minqlxtended-item-respawn.py), not
# under src/, so the bare filename is all COMMON_SOURCES needs; `make`
# resolves it relative to the working directory it runs from (the build
# root). COMMON_SOURCES feeds both SOURCES and SOURCES_NOPY, and it has to:
# hooks.c's My_Touch_Item patch below calls QLHub_ReportItemPickup /
# qlhub_pickup_lock_active unconditionally (no #ifndef NOPY around the call
# sites themselves - only around what they do), so both builds need the
# symbols to link.
#
# Two possible anchors, tried in order, because patch-minqlxtended-demo-match.py
# (Task 2, same COMMON_SOURCES block) may or may not have already run:
#   - if it has, COMMON_SOURCES' last line is "src/features/demo_match.c"
#   - if it has not, COMMON_SOURCES' last line is still upstream's pristine
#     "src/features/demos.c src/features/profile.c"
# Either way this always leaves "qlhub_item_events.c" as the new last line,
# so patch-minqlxtended-item-respawn.py has one fixed anchor to append after,
# regardless of which of the two cases fired here.
MK_ANCHOR_POST_DEMO_MATCH = "                 src/features/demo_match.c"
MK_ANCHOR_PRISTINE = "                 src/features/demos.c src/features/profile.c"
MK_NEW_SUFFIX = " \\\n                 qlhub_item_events.c"


def patch_makefile(makefile: Path) -> bool:
    text = makefile.read_text(encoding="utf-8")
    if "qlhub_item_events.c" in text:
        return False
    for anchor in (MK_ANCHOR_POST_DEMO_MATCH, MK_ANCHOR_PRISTINE):
        if anchor in text:
            makefile.write_text(text.replace(anchor, anchor + MK_NEW_SUFFIX, 1), encoding="utf-8")
            return True
    raise SystemExit(f"COMMON_SOURCES anchor missing/changed in {makefile}")


# ---------------------------------------------------------------------------
# src/server/hooks.c
# ---------------------------------------------------------------------------

HK_DECL_ANCHOR = "static void SetTag(void);"
HK_DECL_NEW = (
    "static void SetTag(void);\n\n"
    "void QLHub_ReportItemPickup(gentity_t* ent, gentity_t* other);\n"
    "int qlhub_pickup_lock_active(void);"
)

# Verified byte-for-byte against a fresh tjone270/minqlxtended clone (branch
# master, commit 1e2f307 at the time of writing) at src/server/hooks.c:510.
# Re-verify at implementation/verification time - this plan does not
# re-fetch it.
OLD_TOUCH_ITEM = """void __cdecl My_Touch_Item(gentity_t* ent, gentity_t* other, trace_t* trace) {
    if (!ent || !other || !other->client) {
        Touch_Item(ent, other, trace);
        return;
    }

    int picked_up_before = ent->pickupCount;

    Touch_Item(ent, other, trace);

    if (ent->pickupCount != picked_up_before && ent->item) {
        ItemPickupDispatcher((int)(other - g_entities), ent->item->classname);
    }
}"""

# Deviates from a straight "add one call after Touch_Item()" patch in two
# places, both deliberate:
#
# 1. QLHub_ReportItemPickup is called *inside* the
#    `ent->pickupCount != picked_up_before && ent->item` guard, not right
#    after Touch_Item() unconditionally. That guard is upstream's own
#    reliable, dedicated pickup signal (gentity_t.pickupCount, "Touch_Item
#    bumps pickupCount once per successful pickup" - src/engine/quake_common.h)
#    and ent->item is already proven non-NULL by it. Calling from here means
#    QLHub_ReportItemPickup can just build and dispatch the payload - it does
#    not need to redo its own before/after diff of ent/other, because
#    "before" and "after" would be the exact same, already-touched ent: the
#    old per-entity wrapper (My_QLHub_EntityTouch, deleted by this patch)
#    ran *before* calling Touch_Item itself, so its own before/after diff
#    (qlhub_save_touch_before + qlhub_pickup_succeeded, also deleted) made
#    sense there. Called from after upstream's own Touch_Item call instead,
#    that same diff would compare ent against itself and never fire - a
#    silent, always-false no-op. Piggybacking on upstream's own
#    already-correct guard sidesteps the whole problem instead of
#    reimplementing (and re-verifying) an equivalent diff at the new call
#    site.
# 2. A lock check is added at the top, gating the Touch_Item() call itself
#    (not just the telemetry) - see qlhub_pickup_lock_active()'s docstring
#    in qlhub_item_events.c for why: match_restore.py's set_pickup_lock(1)
#    has to block the *real* pickup (item removed from world, player stats
#    changed), not just suppress our event about it, to preserve the old
#    behaviour (the old wrapper returned before calling the vanilla touch at
#    all while locked).
NEW_TOUCH_ITEM = """void __cdecl My_Touch_Item(gentity_t* ent, gentity_t* other, trace_t* trace) {
    if (!ent || !other || !other->client) {
        Touch_Item(ent, other, trace);
        return;
    }

    if (qlhub_pickup_lock_active()) {
        return;
    }

    int picked_up_before = ent->pickupCount;

    Touch_Item(ent, other, trace);

    if (ent->pickupCount != picked_up_before && ent->item) {
        QLHub_ReportItemPickup(ent, other);
        ItemPickupDispatcher((int)(other - g_entities), ent->item->classname);
    }
}"""


def patch_hooks(hooks: Path) -> bool:
    changed = False
    if patch_file(hooks, HK_DECL_ANCHOR, HK_DECL_NEW, required=False):
        changed = True
    elif "void QLHub_ReportItemPickup(gentity_t* ent, gentity_t* other);" not in hooks.read_text(encoding="utf-8"):
        raise SystemExit(f"SetTag forward-decl anchor missing/changed in {hooks}")
    if patch_file(hooks, OLD_TOUCH_ITEM, NEW_TOUCH_ITEM, required=False):
        changed = True
    elif "QLHub_ReportItemPickup(ent, other);" not in hooks.read_text(encoding="utf-8"):
        raise SystemExit(f"My_Touch_Item anchor missing/changed in {hooks}")
    return changed


# ---------------------------------------------------------------------------
# src/python/python_dispatchers.c
# ---------------------------------------------------------------------------

PD_INCLUDE_ANCHOR = '#include "pyminqlxtended.h"'
PD_EXTERN_NEW = '#include "pyminqlxtended.h"\n\nextern PyObject* item_event_handler;'

PD_FUNC_ANCHOR = "void KamikazeExplodeDispatcher(int client_id, int is_used_on_demand) {"
PD_ITEM_EVENT_DISPATCHER = '''
void ItemEventDispatcher(
    int action,
    int item_entity_id,
    int client_id,
    const char* classname,
    int gi_type,
    int gi_tag,
    int gi_quantity,
    float x,
    float y,
    float z,
    int game_time) {
    if (!item_event_handler) {
        return;
    }

    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject* result = PyObject_CallFunction(
        item_event_handler,
        "iiisiiifffi",
        action,
        item_entity_id,
        client_id,
        classname ? classname : "",
        gi_type,
        gi_tag,
        gi_quantity,
        x,
        y,
        z,
        game_time);

    if (result == NULL) {
        DebugError("PyObject_CallFunction() returned NULL.\\n", __FILE__, __LINE__, __func__);
    }
    Py_XDECREF(result);
    PyGILState_Release(gstate);
}
'''


def patch_dispatchers(dispatchers: Path) -> bool:
    changed = False
    if patch_file(dispatchers, PD_INCLUDE_ANCHOR, PD_EXTERN_NEW, required=False):
        changed = True
    # Idempotency guard checked BEFORE attempting the insertion, not only via
    # patch_file()'s own "is `new` already present verbatim" check: `new` is
    # the whole dispatcher body immediately followed by PD_FUNC_ANCHOR as one
    # contiguous string, and another script (patch-minqlxtended-demo-bindings.py)
    # inserts its own dispatchers between this function and
    # KamikazeExplodeDispatcher. Once that has happened, the two are no longer
    # adjacent, `new in text` is false, `old` (PD_FUNC_ANCHOR alone) is still
    # found, and patch_file() would insert a second, duplicate
    # `ItemEventDispatcher` definition right before it - a real
    # duplicate-symbol bug, caught by re-running the full orchestrator twice
    # against one tree (not just this script twice in isolation).
    if "void ItemEventDispatcher(" in dispatchers.read_text(encoding="utf-8"):
        return changed
    if patch_file(dispatchers, PD_FUNC_ANCHOR, PD_ITEM_EVENT_DISPATCHER + "\n" + PD_FUNC_ANCHOR, required=False):
        changed = True
    elif "void ItemEventDispatcher(" not in dispatchers.read_text(encoding="utf-8"):
        raise SystemExit(f"KamikazeExplodeDispatcher anchor missing/changed in {dispatchers}")
    return changed


# ---------------------------------------------------------------------------
# src/python/pyminqlxtended.h
# ---------------------------------------------------------------------------

PH_HANDLER_ANCHOR = "extern PyObject* demo_finished_handler;\n\n// Events sourced from the game module."
PH_HANDLER_NEW = (
    "extern PyObject* demo_finished_handler;\n\n"
    "extern PyObject* item_event_handler;\n\n"
    "// Events sourced from the game module."
)

PH_DISPATCH_DECL_ANCHOR = (
    "void ItemPickupDispatcher(int client_id, const char* item_name);\n\n"
    "/*\n"
    " * A player calling a vote,"
)
PH_DISPATCH_DECL_NEW = (
    "void ItemPickupDispatcher(int client_id, const char* item_name);\n\n"
    "void ItemEventDispatcher(\n"
    "    int action,\n"
    "    int item_entity_id,\n"
    "    int client_id,\n"
    "    const char* classname,\n"
    "    int gi_type,\n"
    "    int gi_tag,\n"
    "    int gi_quantity,\n"
    "    float x,\n"
    "    float y,\n"
    "    float z,\n"
    "    int game_time);\n\n"
    "/*\n"
    " * A player calling a vote,"
)


def patch_header(header: Path) -> bool:
    changed = False
    if patch_file(header, PH_HANDLER_ANCHOR, PH_HANDLER_NEW, required=False):
        changed = True
    elif "extern PyObject* item_event_handler;" not in header.read_text(encoding="utf-8"):
        raise SystemExit(f"demo_finished_handler extern anchor missing/changed in {header}")
    if patch_file(header, PH_DISPATCH_DECL_ANCHOR, PH_DISPATCH_DECL_NEW, required=False):
        changed = True
    elif "void ItemEventDispatcher(" not in header.read_text(encoding="utf-8"):
        raise SystemExit(f"ItemPickupDispatcher decl anchor missing/changed in {header}")
    return changed


# ---------------------------------------------------------------------------
# src/python/python_embed.c
# ---------------------------------------------------------------------------

PE_VAR_ANCHOR = "PyObject* kamikaze_explode_handler = NULL;"
PE_VAR_NEW = "PyObject* kamikaze_explode_handler = NULL;\nPyObject* item_event_handler = NULL;"

PE_TABLE_ANCHOR = '    {"kamikaze_explode", &kamikaze_explode_handler},'
PE_TABLE_NEW = (
    '    {"kamikaze_explode", &kamikaze_explode_handler},\n'
    '    {"item_event", &item_event_handler},'
)


def patch_embed(embed: Path) -> bool:
    changed = False
    if patch_file(embed, PE_VAR_ANCHOR, PE_VAR_NEW, required=False):
        changed = True
    elif "PyObject* item_event_handler = NULL;" not in embed.read_text(encoding="utf-8"):
        raise SystemExit(f"kamikaze_explode_handler var anchor missing/changed in {embed}")
    if patch_file(embed, PE_TABLE_ANCHOR, PE_TABLE_NEW, required=False):
        changed = True
    elif '{"item_event", &item_event_handler}' not in embed.read_text(encoding="utf-8"):
        raise SystemExit(f"kamikaze_explode handler-table anchor missing/changed in {embed}")
    return changed


# ---------------------------------------------------------------------------
# python/minqlxtended/_events.py
# ---------------------------------------------------------------------------

EV_CLASS_ANCHOR = """        return super().dispatch(player, is_used_on_demand)


class ItemPickupDispatcher(EventDispatcher):"""
EV_CLASS_NEW = '''        return super().dispatch(player, is_used_on_demand)


class ItemEventDispatcher(EventDispatcher):
    """Fires on map item pickup (upstream's own Touch_Item hook). Carries more
    than upstream's own item_pickup event: item_entity_id, gi_type, gi_tag,
    gi_quantity, the item's world position and the server game time.
    ``action`` is always 0 (pickup) - a drop action never had a real call
    site anywhere in this codebase and this event does not add one."""
    name = "item_event"

    @override
    def dispatch(self, action, item_entity_id, player, classname, gi_type, gi_tag, gi_quantity, x, y, z, game_time):
        return super().dispatch(
            action, item_entity_id, player, classname, gi_type, gi_tag, gi_quantity, x, y, z, game_time
        )


class ItemPickupDispatcher(EventDispatcher):'''

EV_REGISTER_ANCHOR = "EVENT_DISPATCHERS.add_dispatcher(ItemPickupDispatcher)"
EV_REGISTER_NEW = (
    "EVENT_DISPATCHERS.add_dispatcher(ItemPickupDispatcher)\n"
    "EVENT_DISPATCHERS.add_dispatcher(ItemEventDispatcher)"
)


def patch_events_py(events_py: Path) -> bool:
    changed = False
    if patch_file(events_py, EV_CLASS_ANCHOR, EV_CLASS_NEW, required=False):
        changed = True
    elif "class ItemEventDispatcher(EventDispatcher):" not in events_py.read_text(encoding="utf-8"):
        raise SystemExit(f"KamikazeExplodeDispatcher/ItemPickupDispatcher anchor missing/changed in {events_py}")
    if patch_file(events_py, EV_REGISTER_ANCHOR, EV_REGISTER_NEW, required=False):
        changed = True
    elif "add_dispatcher(ItemEventDispatcher)" not in events_py.read_text(encoding="utf-8"):
        raise SystemExit(f"add_dispatcher(ItemPickupDispatcher) anchor missing/changed in {events_py}")
    return changed


# ---------------------------------------------------------------------------
# python/minqlxtended/_handlers.py
# ---------------------------------------------------------------------------

HD_FUNC_ANCHOR = "def handle_item_pickup(client_id, item_name):"
HD_FUNC_NEW = '''def handle_item_event(action, item_entity_id, client_id, classname, gi_type, gi_tag, gi_quantity, x, y, z, game_time):
    try:
        player = minqlxtended.Player(client_id)
        return minqlxtended.EVENT_DISPATCHERS["item_event"].dispatch(
            "pickup" if int(action) == 0 else "drop",
            int(item_entity_id),
            player,
            str(classname or ""),
            int(gi_type),
            int(gi_tag),
            int(gi_quantity),
            float(x),
            float(y),
            float(z),
            int(game_time),
        )
    except:
        minqlxtended.log_exception()
        return True

def handle_item_pickup(client_id, item_name):'''

HD_REGISTER_ANCHOR = '    minqlxtended.register_handler("item_pickup", handle_item_pickup)'
HD_REGISTER_NEW = (
    '    minqlxtended.register_handler("item_pickup", handle_item_pickup)\n'
    '    minqlxtended.register_handler("item_event", handle_item_event)'
)


def patch_handlers_py(handlers_py: Path) -> bool:
    changed = False
    # Same guard as patch_dispatchers() and the same reason: HD_FUNC_NEW is
    # [inserted function] + HD_FUNC_ANCHOR, a suffix pattern - if anything
    # else ever inserts a handler immediately before "def handle_item_pickup"
    # in this file, a re-run's "is `new` already present verbatim" check
    # would stop matching while the bare anchor line still would, producing
    # a duplicate `def handle_item_event`. Not currently reachable (no other
    # patch-minqlxtended-*.py script targets this anchor today), but Python
    # would not even fail the build on a duplicate def - it would just
    # silently shadow the first one - so this is checked defensively before
    # it can ever bite, not after.
    if "def handle_item_event(" in handlers_py.read_text(encoding="utf-8"):
        return changed
    if patch_file(handlers_py, HD_FUNC_ANCHOR, HD_FUNC_NEW, required=False):
        changed = True
    elif "def handle_item_event(" not in handlers_py.read_text(encoding="utf-8"):
        raise SystemExit(f"handle_item_pickup anchor missing/changed in {handlers_py}")
    if patch_file(handlers_py, HD_REGISTER_ANCHOR, HD_REGISTER_NEW, required=False):
        changed = True
    elif 'register_handler("item_event"' not in handlers_py.read_text(encoding="utf-8"):
        raise SystemExit(f'register_handler("item_pickup", ...) anchor missing/changed in {handlers_py}')
    return changed


def patch_build_dir(build_dir: Path) -> None:
    if not build_dir.is_dir():
        raise SystemExit(f"build dir not found: {build_dir}")

    dest_c = build_dir / "qlhub_item_events.c"
    if not dest_c.is_file() or dest_c.read_bytes() != PATCH_SRC.read_bytes():
        shutil.copy2(PATCH_SRC, dest_c)
        print(f"copied: {dest_c.name}")

    any_changed = False
    if patch_makefile(build_dir / "Makefile"):
        print("patched Makefile COMMON_SOURCES")
        any_changed = True
    if patch_hooks(build_dir / "src" / "server" / "hooks.c"):
        print("patched src/server/hooks.c (My_Touch_Item)")
        any_changed = True
    if patch_dispatchers(build_dir / "src" / "python" / "python_dispatchers.c"):
        print("patched src/python/python_dispatchers.c")
        any_changed = True
    if patch_header(build_dir / "src" / "python" / "pyminqlxtended.h"):
        print("patched src/python/pyminqlxtended.h")
        any_changed = True
    if patch_embed(build_dir / "src" / "python" / "python_embed.c"):
        print("patched src/python/python_embed.c")
        any_changed = True
    if patch_events_py(build_dir / "python" / "minqlxtended" / "_events.py"):
        print("patched python/minqlxtended/_events.py")
        any_changed = True
    if patch_handlers_py(build_dir / "python" / "minqlxtended" / "_handlers.py"):
        print("patched python/minqlxtended/_handlers.py")
        any_changed = True

    if any_changed:
        print(f"item-events patch applied under {build_dir}")
    else:
        print(f"already patched: {build_dir}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    build_dir = Path(args[0]) if args else Path.home() / "minqlxtended-build"
    patch_build_dir(build_dir)


if __name__ == "__main__":
    main()
