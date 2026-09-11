#include <stddef.h>
#include <string.h>

#include "common.h"
#include "engine/patterns.h"
#include "engine/quake_common.h"
#include "qlhub_item_respawn.h"

/*
 * Blocks real map-item pickups while match_restore.py is mid-way through
 * rewriting entity/player state (a "restore session"): the Python side calls
 * minqlx.set_pickup_lock(1) before touching state and (0) once it is done.
 * Upstream's My_Touch_Item is now the only place a pickup is ever observed
 * (see the hooks.c patch in patch-minqlxtended-item-events.py), so the lock
 * has to gate that call directly, before Touch_Item runs there - unlike the
 * old per-entity touch wrapper this file used to install, there is no
 * wrapper left here to gate the pickup from.
 */
static int qlhub_pickup_lock = 0;

void qlhub_set_pickup_lock(int active) {
    qlhub_pickup_lock = active ? 1 : 0;
}

int qlhub_pickup_lock_active(void) {
    return qlhub_pickup_lock ? 1 : 0;
}

/* itemType_t from quake_common.h (IT_BAD=0). Only the two variants that share
 * giTag=0 and need quantity to disambiguate; qlhub_item_classname() falls
 * back to ent->item->classname (or ent->classname) for everything else. */
#define QL_IT_ARMOR 3
#define QL_IT_HEALTH 4

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
    int game_time);

static qboolean qlhub_is_map_item_classname(const char* name) {
    if (!name || !name[0]) {
        return qfalse;
    }
    return !strncmp(name, "item_", 5) || !strncmp(name, "weapon_", 7) || !strncmp(name, "ammo_", 5);
}

/*
 * Q3/QL gitem_t: armor and health variants share giTag=0; quantity holds pickup value
 * (pak00/bg_misc.c: shard/5hp=5, GA/25hp=25, YA/50hp=50, RA/MH=100). giTag is 0 for these.
 */
static const char* qlhub_classname_from_quantity(int gi_type, int quantity) {
    switch (gi_type) {
        case QL_IT_ARMOR:
            switch (quantity) {
                case 5:
                    return "item_armor_shard";
                case 25:
                    return "item_armor_jacket";
                case 50:
                    return "item_armor_combat";
                case 100:
                    return "item_armor_body";
                default:
                    return NULL;
            }
        case QL_IT_HEALTH:
            switch (quantity) {
                case 5:
                    return "item_health_small";
                case 25:
                    return "item_health";
                case 50:
                    return "item_health_large";
                case 100:
                    return "item_health_mega";
                default:
                    return NULL;
            }
        default:
            return NULL;
    }
}

static const char* qlhub_item_classname(const gentity_t* ent) {
    const char* ent_class;
    const char* item_class;
    const char* by_quantity;

    if (!ent) {
        return "";
    }
    ent_class = ent->classname;
    item_class = (ent->item && ent->item->classname) ? ent->item->classname : NULL;

    if (ent->item) {
        by_quantity = qlhub_classname_from_quantity(ent->item->giType, ent->item->quantity);
        if (by_quantity) {
            return by_quantity;
        }
    }

    if (ent_class && qlhub_is_map_item_classname(ent_class)) {
        return ent_class;
    }

    if (item_class && item_class[0]) {
        return item_class;
    }

    if (ent_class) {
        return ent_class;
    }
    return "";
}

static void qlhub_dispatch_item_event(int action, const gentity_t* ent, const gentity_t* client_ent) {
    const char* classname = qlhub_item_classname(ent);
    ItemEventDispatcher(
        action,
        (int)(ent - g_entities),
        (int)(client_ent - g_entities),
        classname,
        ent->item ? ent->item->giType : 0,
        ent->item ? ent->item->giTag : 0,
        ent->item ? ent->item->quantity : 0,
        ent->r.currentOrigin[0],
        ent->r.currentOrigin[1],
        ent->r.currentOrigin[2],
        level ? level->time : 0);
}

/*
 * Called from inside upstream's own My_Touch_Item, from within the
 * `ent->pickupCount != picked_up_before && ent->item` guard that also gates
 * upstream's own ItemPickupDispatcher call right next to this one - so by
 * the time this runs, a pickup is already confirmed by upstream's own
 * (reliable, dedicated) pickupCount diff and ent->item is already known
 * non-NULL. The pre-v1.0.0 version of this file saved a snapshot of ent/other
 * right here and compared it against the post-touch state to work out
 * whether a pickup had happened, because the old wrapper had no such
 * upstream-verified signal to gate on; reusing upstream's removes the need
 * for that snapshot-and-compare step entirely - see
 * patch-minqlxtended-item-events.py for the fuller explanation of why (the
 * old approach, called from this new position, would just compare `ent`
 * against itself and never fire).
 */
void QLHub_ReportItemPickup(gentity_t* ent, gentity_t* other) {
#ifndef NOPY
    if (!other->client || other->client->sess.sessionTeam == TEAM_SPECTATOR) {
        return;
    }
    qlhub_dispatch_item_event(0, ent, other);
#endif
}
