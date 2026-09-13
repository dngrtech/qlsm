#include <stdio.h>
#include <string.h>

#include "common.h"
#include "engine/patterns.h"
#include "server/maps_parser.h"
#include "qlhub_item_respawn.h"

extern Touch_Item_ptr Touch_Item;
extern G_AddEvent_ptr G_AddEvent;
extern SV_GetConfigstring_ptr SV_GetConfigstring;

/* My_SV_SetConfigstring (src/server/hooks.c) only exists in a Python build -
 * its whole definition sits inside an #ifndef NOPY block there, since all it
 * adds over the vanilla call is running SetConfigstringDispatcher. A nopy
 * build has no dispatcher to run, so it can call the vanilla SV_SetConfigstring
 * (already extern'd via quake_common.h) directly - see qlhub_replace_item_visible. */
#ifndef NOPY
extern void __cdecl My_SV_SetConfigstring(int index, char* value);
#endif

/*
 * Real signature is __cdecl(gentity_t*, gentity_t*, trace_t*) - see
 * src/server/hooks.c. gentity_t.touch's local type only declares two params
 * (quake_common.h); nothing in this codebase ever calls through ent->touch
 * itself, only assigns/compares it, so the type mismatch is cosmetic and the
 * cast at the one assignment site below (qlhub_show_map_item_for) is enough.
 *
 * My_Touch_Item's whole definition sits inside hooks.c's own #ifndef NOPY
 * block (it exists purely to raise Python events), same as HOOK_VM(Touch_Item)
 * itself - a nopy build never hooks Touch_Item at all, so this only exists
 * to extern the Python-build symbol; qlhub_show_map_item_for falls back to
 * the plain Touch_Item pointer under NOPY instead.
 */
#ifndef NOPY
extern void __cdecl My_Touch_Item(gentity_t* ent, gentity_t* other, trace_t* trace);
#endif

static int qlhub_pending_bg_index[MAX_GENTITIES];
static int qlhub_saved_contents[MAX_GENTITIES];
static int qlhub_last_item_id[MAX_GENTITIES];
static SV_LinkEntity_ptr qlhub_sv_link_entity = NULL;
static int qlhub_sv_link_entity_attempts = 0;

#define QLHUB_SV_LINK_RESOLVE_MAX_ATTEMPTS 8

#if defined(__x86_64__) || defined(_M_X64)
#define QLHUB_PTRN_SV_LINKENTITY_X64 \
    "\x48\x89\xe6\xbf\x02\x00\x00\x00\x48\xc7\x04\x24"
#define QLHUB_MASK_SV_LINKENTITY_X64 "XXXXXXXXXXXX"
#endif

static qboolean qlhub_window_has_contents_trigger(const unsigned char* start, int win_len) {
    int i;
    static const unsigned char trigger_le[] = {0x00, 0x00, 0x00, 0x20};

    if (win_len < 4) {
        return qfalse;
    }
    for (i = 0; i <= win_len - 4; i++) {
        if (memcmp(start + i, trigger_le, 4) == 0) {
            return qtrue;
        }
    }
    return qfalse;
}

static qboolean qlhub_module_range_for(
    const module_info_t* module,
    const unsigned char* addr,
    const unsigned char** out_start,
    const unsigned char** out_end) {
    int i;
    int entries;

    if (!module || !addr) {
        return qfalse;
    }
    entries = module->entries;
    if (entries > 128) {
        entries = 128;
    }
    for (i = 0; i < entries; i++) {
        const unsigned char* s = (const unsigned char*)module->address_start[i];
        const unsigned char* e = (const unsigned char*)module->address_end[i];
        if (addr >= s && addr < e) {
            *out_start = s;
            *out_end = e;
            return qtrue;
        }
    }
    return qfalse;
}

/* Trigger window clamped to the mapped segment so we never read past mmap end. */
static qboolean qlhub_candidate_prologue_ok(
    const unsigned char* start,
    const unsigned char* seg_start,
    const unsigned char* seg_end) {
    int win;

    if (start < seg_start || start >= seg_end) {
        return qfalse;
    }
    if (start[0] != 0x55) {
        return qfalse;
    }
    win = 0x280;
    if (start + win > seg_end) {
        win = (int)(seg_end - start);
    }
    return qlhub_window_has_contents_trigger(start, win);
}

static SV_LinkEntity_ptr qlhub_adjust_link_entity_hit(void* hit, const module_info_t* module) {
    const unsigned char* seg_start;
    const unsigned char* seg_end;
    unsigned char* anchor;
    unsigned char* start;
    int back;

    if (!hit) {
        return NULL;
    }
    anchor = (unsigned char*)hit;
    if (!qlhub_module_range_for(module, anchor, &seg_start, &seg_end)) {
        return NULL;
    }

    /* Body sig is +0x70 from SV_LinkEntity prologue on qzeroded.x64 (see ql-local/disasm-linkentity.py). */
    start = anchor - 0x70;
    if (qlhub_candidate_prologue_ok(start, seg_start, seg_end)) {
        return (SV_LinkEntity_ptr)start;
    }

    for (back = 0; back <= 0x280; back++) {
        start = anchor - back;
        if (start < seg_start) {
            break;
        }
        if (!qlhub_candidate_prologue_ok(start, seg_start, seg_end)) {
            continue;
        }
        return (SV_LinkEntity_ptr)start;
    }
    return NULL;
}

static SV_LinkEntity_ptr qlhub_resolve_sv_link_entity(void) {
    module_info_t module;

    /* Cache success only; failures (e.g. called before /proc maps are usable)
     * are retried a bounded number of times so one early miss is not fatal. */
    if (qlhub_sv_link_entity) {
        return qlhub_sv_link_entity;
    }
    if (qlhub_sv_link_entity_attempts >= QLHUB_SV_LINK_RESOLVE_MAX_ATTEMPTS) {
        return NULL;
    }
    qlhub_sv_link_entity_attempts++;
    strcpy(module.name, "qzeroded.x64");
    if (GetModuleInfo(&module) <= 0) {
        strcpy(module.name, "qzeroded.x86");
        if (GetModuleInfo(&module) <= 0) {
            return NULL;
        }
    }
#if defined(__x86_64__) || defined(_M_X64)
    {
        void* hit = PatternSearchModule(
            &module, QLHUB_PTRN_SV_LINKENTITY_X64, QLHUB_MASK_SV_LINKENTITY_X64);
        qlhub_sv_link_entity = qlhub_adjust_link_entity_hit(hit, &module);
    }
#endif
#if defined(PTRN_SV_LINKENTITY) && defined(MASK_SV_LINKENTITY)
    if (!qlhub_sv_link_entity) {
        qlhub_sv_link_entity = (SV_LinkEntity_ptr)PatternSearchModule(
            &module, PTRN_SV_LINKENTITY, MASK_SV_LINKENTITY);
    }
#endif
    return qlhub_sv_link_entity;
}

static void qlhub_try_link_map_item(gentity_t* ent) {
    SV_LinkEntity_ptr link_fn;

    if (!ent || ent->r.linked) {
        return;
    }
    link_fn = qlhub_resolve_sv_link_entity();
    if (!link_fn) {
        Com_Printf(
            "qlhub_item_respawn: link skipped entity=%d (SV_LinkEntity unresolved)\n",
            (int)(ent - g_entities));
        return;
    }
    link_fn((sharedEntity_t*)ent);
}

static void qlhub_relink_map_item_after_pickup(gentity_t* ent, int prior_contents) {
    int entity_id;

    if (!ent) {
        return;
    }
    qlhub_try_link_map_item(ent);
    if (!ent->r.linked) {
        entity_id = (int)(ent - g_entities);
        Com_Printf(
            "qlhub_item_respawn: link failed entity=%d prior_contents=%d\n",
            entity_id,
            prior_contents);
    }
}

void qlhub_item_respawn_reset_map(void) {
    memset(qlhub_pending_bg_index, 0, sizeof(qlhub_pending_bg_index));
    memset(qlhub_saved_contents, 0, sizeof(qlhub_saved_contents));
    memset(qlhub_last_item_id, 0, sizeof(qlhub_last_item_id));
}

void qlhub_reset_entity_item_state(int entity_id) {
    if (entity_id < 0 || entity_id >= MAX_GENTITIES) {
        return;
    }
    qlhub_pending_bg_index[entity_id] = 0;
    qlhub_saved_contents[entity_id] = 0;
    /* Entity slots are reused within a map; a stale id here could make
     * qlhub_find_map_item_entity match an unrelated item in a reused slot. */
    qlhub_last_item_id[entity_id] = 0;
}

static void qlhub_update_entity_abs(gentity_t* ent) {
    int i;

    if (!ent) {
        return;
    }
    for (i = 0; i < 3; i++) {
        ent->r.absmin[i] = ent->r.currentOrigin[i] + ent->r.mins[i];
        ent->r.absmax[i] = ent->r.currentOrigin[i] + ent->r.maxs[i];
    }
}

static void qlhub_ensure_item_bbox(gentity_t* ent) {
    float dx;
    float dy;
    float dz;

    if (!ent) {
        return;
    }
    dx = ent->r.maxs[0] - ent->r.mins[0];
    dy = ent->r.maxs[1] - ent->r.mins[1];
    dz = ent->r.maxs[2] - ent->r.mins[2];
    if (dx > 1.0f && dy > 1.0f && dz > 1.0f) {
        return;
    }
    ent->r.mins[0] = -15.0f;
    ent->r.mins[1] = -15.0f;
    ent->r.mins[2] = -15.0f;
    ent->r.maxs[0] = 15.0f;
    ent->r.maxs[1] = 15.0f;
    ent->r.maxs[2] = 15.0f;
}

static void qlhub_write_err(char* errbuf, int errbuf_len, const char* msg) {
    if (!errbuf || errbuf_len <= 0) {
        return;
    }
    snprintf(errbuf, (size_t)errbuf_len, "%s", msg ? msg : "");
}

static int qlhub_resolve_item_id(gentity_t* ent, int entity_id) {
    int item_id;
    int from_item;

    if (entity_id >= 0 && entity_id < MAX_GENTITIES) {
        item_id = qlhub_pending_bg_index[entity_id];
        if (item_id > 0 && item_id < bg_numItems) {
            return item_id;
        }
        item_id = qlhub_last_item_id[entity_id];
        if (item_id > 0 && item_id < bg_numItems) {
            return item_id;
        }
    }

    if (ent) {
        item_id = ent->s.modelindex;
        if (item_id > 0 && item_id < bg_numItems) {
            return item_id;
        }
        if (ent->item) {
            from_item = (int)(ent->item - bg_itemlist);
            if (from_item > 0 && from_item < bg_numItems) {
                return from_item;
            }
        }
    }

    return 0;
}

static void qlhub_remember_item_id(int entity_id, int item_id) {
    if (entity_id < 0 || entity_id >= MAX_GENTITIES) {
        return;
    }
    if (item_id > 0 && item_id < bg_numItems) {
        qlhub_last_item_id[entity_id] = item_id;
    }
}

static void qlhub_ensure_item_pointer(gentity_t* ent, int item_id) {
    if (!ent || item_id <= 0 || item_id >= bg_numItems) {
        return;
    }
    ent->s.modelindex = item_id;
    ent->classname = bg_itemlist[item_id].classname;
    ent->item = &bg_itemlist[item_id];
    ent->s.eType = ET_ITEM;
}

/* Validates the slot AND repairs the entity<->bg_itemlist links in place
 * (modelindex/classname/item may have been zeroed by the engine on pickup). */
static qboolean qlhub_valid_item_entity(int entity_id, gentity_t** out_ent, char* errbuf, int errbuf_len) {
    gentity_t* ent;
    int item_id;

    if (entity_id < 0 || entity_id >= MAX_GENTITIES) {
        qlhub_write_err(errbuf, errbuf_len, "entity_id out of range");
        return qfalse;
    }
    ent = &g_entities[entity_id];
    if (!ent->inuse) {
        qlhub_write_err(errbuf, errbuf_len, "entity not in use");
        return qfalse;
    }
    if (ent->s.eType != ET_ITEM) {
        qlhub_write_err(errbuf, errbuf_len, "entity is not ET_ITEM");
        return qfalse;
    }

    item_id = qlhub_resolve_item_id(ent, entity_id);
    if (item_id <= 0) {
        qlhub_write_err(errbuf, errbuf_len, "entity has no item id");
        return qfalse;
    }
    qlhub_ensure_item_pointer(ent, item_id);

    if (out_ent) {
        *out_ent = ent;
    }
    return qtrue;
}

static void qlhub_replace_item_visible(gentity_t* ent, int item_id, int contents) {
    char csbuffer[4096];
    int prior_contents;
    int cs_len;

    if (!ent || item_id <= 0 || item_id >= bg_numItems) {
        return;
    }

    prior_contents = ent->r.contents;
    qlhub_ensure_item_pointer(ent, item_id);
    ent->s.eFlags &= ~EF_NODRAW;
    ent->r.svFlags &= ~SVF_NOCLIENT;
    ent->r.contents = contents ? contents : CONTENTS_TRIGGER;
    qlhub_ensure_item_bbox(ent);
    qlhub_update_entity_abs(ent);
    qlhub_relink_map_item_after_pickup(ent, prior_contents);

    if (item_id >= (int)sizeof(csbuffer) - 2) {
        return;
    }
    SV_GetConfigstring(CS_ITEMS, csbuffer, sizeof(csbuffer));
    /* CS_ITEMS may be shorter than item_id (e.g. early in map load); pad with
     * '0' so the '1' lands inside the string instead of past the terminator. */
    cs_len = (int)strlen(csbuffer);
    if (cs_len <= item_id) {
        while (cs_len <= item_id) {
            csbuffer[cs_len++] = '0';
        }
        csbuffer[cs_len] = '\0';
    }
    csbuffer[item_id] = '1';
#ifndef NOPY
    My_SV_SetConfigstring(CS_ITEMS, csbuffer);
#else
    SV_SetConfigstring(CS_ITEMS, csbuffer);
#endif
}

static void qlhub_hide_item_for_respawn(gentity_t* ent, int entity_id, int item_id) {
    if (!ent || entity_id < 0 || entity_id >= MAX_GENTITIES) {
        return;
    }

    /* contents is intentionally left as-is (no unlink): with touch/think
     * cleared the engine never fires pickup on it, and keeping the link
     * avoids an unlink/relink round-trip through SV_LinkEntity. */
    if (ent->r.contents != 0) {
        qlhub_saved_contents[entity_id] = ent->r.contents;
    } else if (qlhub_saved_contents[entity_id] == 0) {
        qlhub_saved_contents[entity_id] = CONTENTS_TRIGGER;
    }

    qlhub_pending_bg_index[entity_id] = item_id;
    qlhub_ensure_item_pointer(ent, item_id);
    ent->s.eFlags |= EF_NODRAW;
    ent->r.svFlags |= SVF_NOCLIENT;
    ent->touch = NULL;
    ent->think = NULL;
    ent->nextthink = 0;
}

static void qlhub_item_respawn_think(gentity_t* ent) {
    int entity_id;
    char errbuf[256];

    if (!ent) {
        return;
    }

    entity_id = (int)(ent - g_entities);
    errbuf[0] = '\0';
    if (!qlhub_show_map_item(entity_id, errbuf, (int)sizeof(errbuf))) {
        Com_Printf(
            "qlhub_item_respawn: think show failed entity=%d (%s)\n",
            entity_id,
            errbuf[0] ? errbuf : "unknown");
    }
}

qboolean qlhub_touch_map_item(int entity_id, int client_id, char* errbuf, int errbuf_len) {
    gentity_t* ent;
    gentity_t* other;

    if (!Touch_Item) {
        qlhub_write_err(errbuf, errbuf_len, "Touch_Item unresolved");
        return qfalse;
    }
    if (!qlhub_valid_item_entity(entity_id, &ent, errbuf, errbuf_len)) {
        return qfalse;
    }
    if (client_id < 0 || client_id >= sv_maxclients->integer) {
        qlhub_write_err(errbuf, errbuf_len, "client_id out of range");
        return qfalse;
    }
    other = &g_entities[client_id];
    if (!other->client) {
        qlhub_write_err(errbuf, errbuf_len, "client slot empty");
        return qfalse;
    }

    Touch_Item(ent, other, NULL);
    return qtrue;
}

qboolean qlhub_hide_map_item_for(int entity_id, int forced_item_id, char* errbuf, int errbuf_len) {
    gentity_t* ent;
    int item_id;

    if (!qlhub_valid_item_entity(entity_id, &ent, errbuf, errbuf_len)) {
        return qfalse;
    }

    qlhub_reset_entity_item_state(entity_id);

    if (forced_item_id > 0 && forced_item_id < bg_numItems) {
        item_id = forced_item_id;
    } else {
        item_id = qlhub_resolve_item_id(ent, entity_id);
    }
    if (item_id <= 0 || item_id >= bg_numItems) {
        qlhub_write_err(errbuf, errbuf_len, "invalid bg item index");
        return qfalse;
    }

    qlhub_remember_item_id(entity_id, item_id);
    qlhub_hide_item_for_respawn(ent, entity_id, item_id);
    Com_Printf(
        "qlhub_item_respawn: hide entity=%d item=%d saved_contents=%d\n",
        entity_id,
        item_id,
        qlhub_saved_contents[entity_id]);
    return qtrue;
}

qboolean qlhub_hide_map_item(int entity_id, char* errbuf, int errbuf_len) {
    return qlhub_hide_map_item_for(entity_id, 0, errbuf, errbuf_len);
}

qboolean qlhub_show_map_item_for(int entity_id, int forced_item_id, char* errbuf, int errbuf_len) {
    gentity_t* ent;
    int item_id;

    if (!qlhub_valid_item_entity(entity_id, &ent, errbuf, errbuf_len)) {
        return qfalse;
    }

    if (forced_item_id > 0 && forced_item_id < bg_numItems) {
        item_id = forced_item_id;
    } else {
        item_id = qlhub_pending_bg_index[entity_id];
        qlhub_pending_bg_index[entity_id] = 0;
        if (item_id <= 0 || item_id >= bg_numItems) {
            item_id = qlhub_resolve_item_id(ent, entity_id);
        }
    }
    if (item_id <= 0 || item_id >= bg_numItems) {
        qlhub_write_err(errbuf, errbuf_len, "invalid bg item index");
        return qfalse;
    }

    qlhub_remember_item_id(entity_id, item_id);
    qlhub_pending_bg_index[entity_id] = 0;
    {
        int restore_contents = CONTENTS_TRIGGER;
        if (qlhub_saved_contents[entity_id] != 0) {
            restore_contents = qlhub_saved_contents[entity_id];
        }
        qlhub_saved_contents[entity_id] = 0;
        ent->think = NULL;
        ent->nextthink = 0;
        qlhub_replace_item_visible(ent, item_id, restore_contents);
    }
    if (G_AddEvent) {
        G_AddEvent(ent, EV_ITEM_RESPAWN, 0);
    }
    if (Touch_Item) {
#ifndef NOPY
        /* Route back through upstream's own Touch_Item hook (My_Touch_Item in
         * src/server/hooks.c) rather than a dedicated wrapper of our own - it
         * already does everything a respawned item needs: the real pickup
         * plus both upstream's item_pickup and our own item_event. */
        ent->touch = (void (*)(gentity_t*, gentity_t*))My_Touch_Item;
#else
        /* Touch_Item is never hooked in a nopy build (no Python events to
         * raise), so the plain resolved pointer is the vanilla touch. */
        ent->touch = (void (*)(gentity_t*, gentity_t*))Touch_Item;
#endif
    } else {
        Com_Printf(
            "qlhub_item_respawn: show entity=%d without touch (Touch_Item unresolved)\n",
            entity_id);
    }
    Com_Printf(
        "qlhub_item_respawn: show entity=%d item=%d contents=%d linked=%d\n",
        entity_id,
        item_id,
        ent->r.contents,
        ent->r.linked ? 1 : 0);
    return qtrue;
}

qboolean qlhub_show_map_item(int entity_id, char* errbuf, int errbuf_len) {
    return qlhub_show_map_item_for(entity_id, 0, errbuf, errbuf_len);
}

qboolean qlhub_find_map_item_entity(
    float x,
    float y,
    float z,
    float radius,
    int want_item_id,
    int exclude_entity_id,
    int* out_entity_id,
    char* errbuf,
    int errbuf_len) {
    int i;
    int limit;
    int best_id = -1;
    float best_dist = 0.0f;
    float radius_sq;
    int pass;

    if (out_entity_id) {
        *out_entity_id = -1;
    }
    if (!g_entities || !level) {
        qlhub_write_err(errbuf, errbuf_len, "level missing");
        return qfalse;
    }
    if (radius <= 0.0f) {
        radius = 64.0f;
    }
    radius_sq = radius * radius;

    limit = level->num_entities;
    if (limit <= 0) {
        qlhub_write_err(errbuf, errbuf_len, "no entities");
        return qfalse;
    }
    if (limit > MAX_GENTITIES) {
        limit = MAX_GENTITIES;
    }

    for (pass = 0; pass < 2; pass++) {
        best_id = -1;
        best_dist = 0.0f;
        for (i = 0; i < limit; i++) {
            gentity_t* ent = &g_entities[i];
            int item_id;
            float dx;
            float dy;
            float dz;
            float dist_sq;

            if (!ent->inuse || ent->s.eType != ET_ITEM) {
                continue;
            }
            if (exclude_entity_id >= 0 && i == exclude_entity_id) {
                continue;
            }

            item_id = qlhub_resolve_item_id(ent, i);
            if (want_item_id > 0) {
                if (item_id > 0 && item_id != want_item_id) {
                    if (qlhub_last_item_id[i] == want_item_id) {
                        item_id = want_item_id;
                    } else {
                        continue;
                    }
                }
            }

            if (pass == 0 && ent->r.contents == 0) {
                continue;
            }

            dx = ent->r.currentOrigin[0] - x;
            dy = ent->r.currentOrigin[1] - y;
            dz = ent->r.currentOrigin[2] - z;
            dist_sq = (dx * dx) + (dy * dy) + (dz * dz);
            if (dist_sq > radius_sq) {
                continue;
            }

            if (best_id < 0 || dist_sq < best_dist) {
                best_id = i;
                best_dist = dist_sq;
            }
        }
        if (best_id >= 0) {
            break;
        }
    }

    if (best_id < 0) {
        qlhub_write_err(errbuf, errbuf_len, "no item entity at slot");
        return qfalse;
    }

    if (out_entity_id) {
        *out_entity_id = best_id;
    }
    return qtrue;
}

qboolean qlhub_set_item_respawn_delay(int entity_id, int delay_ms, char* errbuf, int errbuf_len) {
    gentity_t* ent;
    int when;
    qboolean qlhub_think = qfalse;

    if (!level) {
        qlhub_write_err(errbuf, errbuf_len, "level missing");
        return qfalse;
    }
    if (delay_ms < 0) {
        qlhub_write_err(errbuf, errbuf_len, "delay_ms must be >= 0");
        return qfalse;
    }
    if (!qlhub_valid_item_entity(entity_id, &ent, errbuf, errbuf_len)) {
        return qfalse;
    }

    when = level->time + delay_ms;

    if (ent->think == (void*)qlhub_item_respawn_think) {
        ent->nextthink = when;
        qlhub_think = qtrue;
    } else if (!ent->think) {
        if ((ent->s.eFlags & EF_NODRAW) || qlhub_pending_bg_index[entity_id] > 0) {
            ent->think = qlhub_item_respawn_think;
            ent->nextthink = when;
            qlhub_think = qtrue;
        } else {
            qlhub_write_err(errbuf, errbuf_len, "no vanilla respawn think; touch reset first");
            return qfalse;
        }
    } else {
        ent->nextthink = when;
    }

    Com_Printf(
        "qlhub_item_respawn: %s nextthink entity=%d respawn_at=%d (delay=%dms)\n",
        qlhub_think ? "qlhub" : "vanilla",
        entity_id,
        when,
        delay_ms);
    return qtrue;
}

qboolean qlhub_get_map_item_state(
    int entity_id,
    int* out_inuse,
    int* out_etype,
    int* out_eflags,
    int* out_contents,
    int* out_nextthink,
    int* out_has_think,
    int* out_level_time,
    char* out_classname,
    int classname_len,
    char* errbuf,
    int errbuf_len) {
    gentity_t* ent;

    if (entity_id < 0 || entity_id >= MAX_GENTITIES) {
        qlhub_write_err(errbuf, errbuf_len, "entity_id out of range");
        return qfalse;
    }

    ent = &g_entities[entity_id];
    if (out_inuse) {
        *out_inuse = ent->inuse ? 1 : 0;
    }
    if (out_etype) {
        *out_etype = ent->s.eType;
    }
    if (out_eflags) {
        *out_eflags = ent->s.eFlags;
    }
    if (out_contents) {
        *out_contents = ent->r.contents;
    }
    if (out_nextthink) {
        *out_nextthink = ent->nextthink;
    }
    if (out_has_think) {
        *out_has_think = ent->think ? 1 : 0;
    }
    if (out_level_time) {
        *out_level_time = level ? level->time : 0;
    }
    if (out_classname && classname_len > 0) {
        if (ent->classname) {
            snprintf(out_classname, (size_t)classname_len, "%s", ent->classname);
        } else {
            out_classname[0] = '\0';
        }
    }
    return qtrue;
}
