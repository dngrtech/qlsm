#ifndef UDT_BRIDGE_H
#define UDT_BRIDGE_H

#ifdef __cplusplus
extern "C" {
#endif

// Cuts [start_ms, end_ms) out of in_path (a .dm_91) into a new file under
// out_folder. UDT picks the output filename itself (see api_helpers.cpp's
// GetCutFilePath, confirmed by Step 6/7 of the Task 1 spike). out_folder
// must be a directory demo_cut can treat as exclusively its own for this
// call -- the caller is responsible for passing a unique directory per
// invocation so there is never more than one candidate output file to find.
// (This is a deliberate constraint set by the plan's controller after a
// prior task found a race when globbing a shared output folder for "the
// newest .dm_91" -- see the plan doc's Task 1 note. It does not change
// anything about demo_cut()'s own behavior, only what its caller promises.)
//
// start_ms/end_ms are in the demo's *server time* clock (milliseconds since
// the map/level loaded on the server that recorded it) -- the same clock as
// UDT's ServerTimeMs fields (udtParseDataObituary::ServerTimeMs,
// udtParseDataChat::ServerTimeMs, udtCuSnapshotMessage::ServerTimeMs, etc)
// and udtParseDataGameState's FirstSnapshotTimeMs/LastSnapshotTimeMs bounds.
// This is NOT wall-clock/epoch time and NOT "seconds since this recording
// started" -- a real per-player capture from the current pipeline had
// FirstSnapshotTimeMs=176550, LastSnapshotTimeMs=703000 (i.e. the demo
// begins 176.55s of server uptime in, not at 0). Confirmed empirically:
// cutting [300000, 400000) out of that same demo (a 100s window comfortably
// inside its range) produced a 440917-byte file from a 2521067-byte input
// (~17.5%, consistent with ~100s/526s of the source's real span), while
// cutting [5000, ...) -- 5000ms being *before* FirstSnapshotTimeMs -- barely
// changed the file size at all, because there was nothing before the first
// snapshot to trim. Task 6 must source start_ms/end_ms from the same
// server-time clock (e.g. UDT_json's own duration/snapshot-time fields, or
// this bridge's own snapshot index from a later task), never from wall time.
//
// end_ms=-1 does NOT mean "cut to end of file" -- CONFIRMED BROKEN in
// Task 1's live test (Step 7). udtCutDemoFileByTime (api.cpp) only queues a
// cut when "cut.StartTimeMs < cut.EndTimeMs"; since start_ms is always a
// large positive server-time value in practice, -1 fails that comparison,
// so zero cuts get queued. Left unguarded, the call still returns success
// (udtErrorCode::None) with out_folder ending up empty, silently, with no
// warning logged -- this bit us on the first live test run. demo_cut() now
// guards against start_ms >= end_ms itself (returns non-zero with a message
// in err_buf) specifically so this can't happen silently again; it does NOT
// treat end_ms=-1 as special, it is simply rejected by that same guard. To
// cut to the end of the file, pass a large sentinel end_ms (e.g. INT32_MAX)
// instead -- UDT clamps an out-of-range EndTimeMs to the actual last
// snapshot internally, which DOES work (confirmed: cutting [5000, INT32_MAX)
// produced a valid file running to the source's actual end). Task 6 must
// NOT pass -1 for "to end of file."
//
// Returns 0 on success. On failure, returns non-zero and writes a
// human-readable message into err_buf (truncated to err_buf_len).
int demo_cut(const char* in_path, const char* out_folder,
             int start_ms, int end_ms,
             char* err_buf, int err_buf_len);

// ---------------------------------------------------------------------------
// Task 6a additions: reading a .dm_91's own server-time clock.
//
// demo_cut() needs start/end in the demo's server-time clock, but the capture
// side (demos.c) never decodes message content -- all it knows about a message
// is the netchan outgoingSequence it stamped into the file's own 8-byte
// per-block header (see writer_handle_block()). demo_scan() closes that gap:
// it walks the file's framing itself, hands every message to UDT's public
// streaming parser (udtCuCreateContext/udtCuStartParsing/udtCuParseMessage),
// and reports the server times UDT decodes back out, keyed by that same
// sequence number.
//
// The correlation is exact, not heuristic: udtCuMessageInput::MessageSequence
// is passed straight through to udtBaseParser::ParseNextMessage's
// inServerMessageSequence (api.cpp), which lands in _inServerMessageSequence,
// which parser.cpp's ParseSnapshot copies into newSnap.messageNum and then
// into udtSnapshotCallbackArg::MessageNumber -- i.e. the value the caller put
// in comes straight back out on udtCuSnapshotMessage::MessageNumber. There is
// no re-derivation anywhere in between that could disagree with the caller.
// ---------------------------------------------------------------------------

// Everything demo_scan reports is scoped to the demo's FIRST gamestate,
// because that is the only gamestate demo_cut() can address (its
// udtCut::GameStateIndex is pinned to 0 -- Task 1's own concern #1). This is
// not a theoretical distinction: two of the eight real per-POV captures used
// as Task 6a's test corpus contain two gamestates, and their server-time
// clock jumps backwards mid-file (1077875 -> 7625) when the level reloads.
// Treating such a file as one continuous clock silently produces a negative
// span. Callers must check gamestate_count and refuse to cut when it is not
// 1. Task 4's capture path can only ever produce 1 (Demo_Capture finalises
// the segment and re-seeds on every gamestate), so >1 means a stranded or
// hand-recovered file, not a normal one.
typedef struct demo_scan_s {
    // Server time (ms) of the first / last snapshot of gamestate 0. Same
    // clock and same values as udtParseDataGameState::FirstSnapshotTimeMs /
    // LastSnapshotTimeMs (cross-checked against demo_range() below on real
    // single-gamestate files). -1 when there is no snapshot at all.
    int first_ms;
    int last_ms;

    // Server time (ms) of the first snapshot carried by a message whose
    // sequence number is >= the arm_seq passed in -- i.e. "what the server
    // clock read at the instant this POV was armed". -1 if arm_seq was
    // negative or no message at/after it carried a snapshot.
    int arm_ms;

    // Server time (ms) of the first snapshot at/after config string
    // DEMO_CS_WARMUP_INDEX is set to "\time\0" (QL's "match in progress"),
    // considering only updates at/after arm_seq. In other words: the server
    // clock at the instant the countdown ended and the match went live.
    // -1 when no such update happens at/after arm_seq -- normal for a file
    // that was already in-progress when it started (cs 5 then only appears
    // in the gamestate, never as a command) and for a pure-warmup file.
    // Diagnostic only -- see demos.c for why the two-stage cut deliberately
    // does NOT move its window to this time.
    int live_ms;

    // Number of gamestate messages in the whole file. 1 for anything Task 4's
    // capture path produces; anything else means first_ms/last_ms/arm_ms only
    // describe the leading gamestate and demo_cut() must not be used.
    int gamestate_count;

    // How many times the server-time clock jumped BACKWARDS between two
    // consecutive snapshots inside gamestate 0, counted over the WHOLE file.
    // Non-zero here is common and often harmless on the current (v1.0.0,
    // upstream Demo_Request-based) capture path: a raw file stays open and
    // keeps accumulating across back-to-back matches on the same map with no
    // client reconnect (see the "known limitation" comment on
    // DemoMatch_Disarm in demo_match.c), and a soft server respawn between
    // those matches resets the server clock WITHOUT sending a new gamestate -
    // so a raw capture can legitimately hold a stale, already-consumed
    // match's tail followed by a clock reset followed by the current match's
    // own clean data. That leading, pre-arm portion is discarded by the cut
    // regardless, so a reset confined to it must not veto the cut. Kept for
    // diagnostics; callers must gate the cut on clock_resets_since_arm below,
    // not this field.
    int clock_resets;

    // Same count, but only for resets detected AT OR AFTER arm_ms was found
    // (i.e. within the region demo_cut() will actually be asked to select).
    // -1 when arm_seq was negative (arm_ms lookup skipped, so "since arm" is
    // undefined). THIS is the field callers must check being 0 before
    // trusting a cut of [arm_ms, last_ms]: demo_cut() selects messages by a
    // plain "start <= t <= end" comparison (parser.cpp) with no notion of
    // where in the file a message sits, so a reset still inside the window
    // the cut will scan (from arm_ms's own message onward) means two clock
    // epochs really do overlap the requested range and the cut would be
    // silently wrong rather than failing - see clock_resets' own comment for
    // where this was first measured (Task 6a corpus, message 267).
    int clock_resets_since_arm;

    // Diagnostics. snapshot_count covers gamestate 0 only; message_count is
    // the whole file.
    int snapshot_count;
    int message_count;

    // The client number of the player who recorded the demo, straight off the
    // FIRST gamestate message (udtCuGamestateMessage::ClientNumber). -1 when
    // the file has no gamestate at all. This is the demo's own idea of "whose
    // POV is this", which is not necessarily the server slot the capture side
    // named the file after - a cut file's gamestate is rewritten by UDT but
    // ClientNumber is carried through unchanged.
    int client_num;
} demo_scan_t;

// QL's warmup/in-progress config string (the spec's "cs 5"). Confirmed
// empirically against real per-POV captures in Task 6a: index 5 is the only
// config string carrying a "\time\" key, and it goes
// "\time\-1" (no match) -> "\time\<absolute start time>" (countdown running)
// -> "\time\0" (in progress). Do not change without re-running that dump.
#define DEMO_CS_WARMUP_INDEX 5

// Walks in_path once with the udtCu* streaming parser and fills *out.
// arm_seq may be negative to skip the arm_ms/live_ms lookups.
// Returns 0 on success, non-zero with a message in err_buf otherwise.
int demo_scan(const char* in_path, int arm_seq, demo_scan_t* out,
              char* err_buf, int err_buf_len);

// The independent, second route to the same first/last snapshot times:
// udtParseDemoFiles() + udtGetContextPlugInBuffers(GameState), the exact
// call Task 1 used for its StartTimeMs-unit evidence. Kept as the
// cross-check for demo_scan()'s own first_ms/last_ms (test_scan.c runs both
// and diffs them); the finalize thread uses demo_scan() instead, because it
// needs arm_ms from the same walk anyway and one pass beats two.
// Returns 0 on success.
int demo_range(const char* in_path, int* first_ms, int* last_ms,
               char* err_buf, int err_buf_len);

// ---------------------------------------------------------------------------
// Task 6b additions: the per-POV snapshot byte index (index/p{slot}.snaps.json).
//
// demo_index() is demo_scan()'s walk with the per-snapshot rows kept instead of
// thrown away. Both go through ONE internal walker (ScanWalk in bridge.cpp), so
// there is exactly one implementation of "feed this file's own framing to the
// udtCu* streaming parser" and demo_scan()/demo_index() can never disagree
// about what a file contains. (demo_range() stays a genuinely independent
// second route - that duplication is the deliberate cross-check Task 6a kept.)
// ---------------------------------------------------------------------------

typedef struct demo_snap_s {
    // Byte offset, from the start of the file, of this message's OWN 8-byte
    // (int32 seq, int32 len) header - not of the payload behind it. This is
    // the spec's "index_framing": "with_header" convention. The value comes
    // from the walker's own read loop, not from UDT: the caller of
    // udtCuParseMessage is the one holding the file position, which is exactly
    // why offset and server time can never desync (see the note at the top of
    // bridge.cpp).
    long long off;

    // Server time (ms) of the snapshot this message carries. Same clock as
    // demo_scan()'s first_ms/last_ms and demo_cut()'s start/end.
    int t;

    // The header's own len field: payload bytes following the 8-byte header.
    // So the next message's header starts at off + 8 + len.
    int len;

    // Quake 3 / QL svc_snapshot "deltaNum": how many messages BACK the
    // snapshot this one is delta-compressed against sits. 0 means this
    // snapshot is a full/keyframe one that can be decoded with no history -
    // the only rows a seeker can jump straight to. -1 means "could not be
    // determined" (see delta_unknown on demo_index_result_t); it is never
    // silently reported as 0.
    //
    // WHERE THIS COMES FROM (investigated for Task 6b, do not "simplify"):
    // udtCuSnapshotMessage - the whole public Cu-API snapshot struct - carries
    // AreaMask/PlayerState/Entities/EntityFlags/ChangedEntities/RemovedEntities/
    // Reserved1/ServerTimeMs/MessageNumber/CommandNumber/ChangedEntityCount/
    // RemovedEntityCount/EntityCount and NOTHING else (uberdemotools.h, the
    // struct is closed by UDT_ENFORCE_API_STRUCT_SIZE). There is no delta or
    // baseline field on it, and "delta" does not appear anywhere else in the
    // public header either. UDT does parse the value - parser.cpp's
    // ParseSnapshot reads the wire byte and stores idClientSnapshotBase::
    // deltaNum - but plug_in_custom_parser.cpp's ProcessSnapshotMessage, which
    // is what fills udtCuSnapshotMessage, simply does not copy it across.
    // The raw bytes are no help either: a .dm_91 message body is a Huffman
    // bitstream, so the walker cannot read the deltaNum byte without running
    // UDT's decoder anyway.
    // So bridge.cpp reaches the value UDT already decoded, through UDT's own
    // internal headers (custom_context.hpp -> udtCuContext_s::Context.Parser,
    // GetClientSnapshot(messageNum & PACKET_MASK), which parser.cpp fills by
    // Com_Memcpy of the finished snapshot immediately before it notifies the
    // plug-ins). Every read is validated against the public struct first: the
    // recovered snapshot's messageNum AND serverTime must both equal
    // udtCuSnapshotMessage::MessageNumber/ServerTimeMs, otherwise the row's
    // delta is reported as -1 rather than guessed.
    // NOTE the stored value is normalised: UDT keeps deltaNum as an ABSOLUTE
    // message number (messageNum - wireByte), with -1 standing for "the wire
    // byte was 0". What is reported here is the wire byte itself, i.e. the
    // relative distance, because that is what the .dm_91 actually contains and
    // what survives UDT rewriting the sequence numbers on a cut.
    int delta;
} demo_snap_t;

typedef struct demo_index_result_s {
    // Everything demo_scan() would have reported for the same file.
    demo_scan_t scan;

    // One row per snapshot of gamestate 0, in file order. NULL when count is
    // 0. Owned by the caller: release with demo_index_free().
    demo_snap_t* snaps;
    int count; // always equals scan.snapshot_count on success

    // How many rows got delta = -1. Expected to be 0; anything else means the
    // internal-header route above stopped agreeing with the public struct and
    // the index's delta column is not trustworthy.
    int delta_unknown;
} demo_index_result_t;

// Walks in_path once and fills *out, including a row per snapshot.
// Returns 0 on success, non-zero with a message in err_buf otherwise.
// On success the caller MUST call demo_index_free(out) exactly once.
int demo_index(const char* in_path, demo_index_result_t* out,
               char* err_buf, int err_buf_len);

// Releases out->snaps and zeroes the pointer/count. Safe on a zeroed struct
// and safe to call twice.
void demo_index_free(demo_index_result_t* out);

#ifdef __cplusplus
}
#endif

#endif /* UDT_BRIDGE_H */
