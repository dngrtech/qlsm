#ifndef QLHUB_ITEM_RESPAWN_H
#define QLHUB_ITEM_RESPAWN_H

#include "engine/quake_common.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Q3/QL item trigger contents (not always in headers). */
#ifndef CONTENTS_TRIGGER
#define CONTENTS_TRIGGER 0x20000000
#endif

qboolean qlhub_touch_map_item(int entity_id, int client_id, char* errbuf, int errbuf_len);

qboolean qlhub_hide_map_item(int entity_id, char* errbuf, int errbuf_len);

qboolean qlhub_hide_map_item_for(int entity_id, int item_id, char* errbuf, int errbuf_len);

qboolean qlhub_show_map_item(int entity_id, char* errbuf, int errbuf_len);

qboolean qlhub_show_map_item_for(int entity_id, int item_id, char* errbuf, int errbuf_len);

qboolean qlhub_find_map_item_entity(
    float x,
    float y,
    float z,
    float radius,
    int want_item_id,
    int exclude_entity_id,
    int* out_entity_id,
    char* errbuf,
    int errbuf_len);

qboolean qlhub_set_item_respawn_delay(int entity_id, int delay_ms, char* errbuf, int errbuf_len);

void qlhub_item_respawn_reset_map(void);

void qlhub_set_pickup_lock(int active);

int qlhub_pickup_lock_active(void);

void qlhub_reset_entity_item_state(int entity_id);

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
    int errbuf_len);

#ifdef __cplusplus
}
#endif

#endif
