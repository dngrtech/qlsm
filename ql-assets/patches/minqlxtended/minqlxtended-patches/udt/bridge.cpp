// Vendored from github.com/mightycow/uberdemotools (UDT_DLL), GPLv2.
// Upstream commit: f9eddde501e494ec25797663282f9f36b22c9f52 (develop, 2024-01-08).
// See COPYING.txt in this directory for the license text.
//
// StartTimeMs/EndTimeMs unit (Task 1 spike finding): confirmed by reading
// UDT_DLL/include/uberdemotools.h byte-for-byte (not AI-summarized) that
// udtCut::StartTimeMs/EndTimeMs are "server time" milliseconds -- the same
// clock as ServerTimeMs on udtParseDataObituary, udtParseDataChat and
// udtCuSnapshotMessage, and the same clock udtParseDataGameState's
// FirstSnapshotTimeMs/LastSnapshotTimeMs report the demo's total range in.
// This is NOT wall-clock time and NOT seconds since the recording started
// (a real capture's own range started at FirstSnapshotTimeMs=176550, not 0).
// See bridge.h for the full write-up and real numbers from Task 1's live
// test against a real .dm_91.
//
// EndTimeMs=-1 pitfall (Task 1 spike finding, see bridge.h for detail):
// api.cpp's udtCutDemoFileByTime only queues a cut when
// "cut.StartTimeMs < cut.EndTimeMs" -- passing -1 fails that check for any
// realistic (positive) start_ms, so the cut is silently dropped: the call
// still returns success and demo_cut() still returns 0, but out_folder gets
// no file and nothing is logged. Use a large sentinel (e.g. INT32_MAX) to
// mean "cut to end of file" -- UDT clamps it to the real last snapshot.
//
// Snapshot serverTime + file byte offset finding (Task 1 spike, for Task 6's
// index/pN.snaps.json): the public udtCu* streaming API
// (udtCuCreateContext/udtCuStartParsing/udtCuParseMessage, declared near the
// bottom of uberdemotools.h) hands back udtCuSnapshotMessage::ServerTimeMs
// per snapshot, but the CALLER supplies each raw message's bytes to
// udtCuParseMessage -- so the caller already knows that message's file byte
// offset from its own read loop (the 8-byte seq+len .dm_91 framing), no
// extra plumbing needed. There is no separate "FileOffset" field on
// udtCuSnapshotMessage because the API's shape makes it redundant: offset
// and serverTime are produced by the same per-message step, so they cannot
// disagree/desync. (There is also a lower-level route: a custom
// udtBaseParserPlugIn::ProcessSnapshotMessage(arg, parser) override gets
// arg.ServerTime plus the parser's own _inFileOffset public field, which is
// set to the start-of-message file offset before that message's commands
// are parsed -- same information, different (heavier, non-Cu) entry point.
// This bridge does not implement either path; it only documents that the
// vendored code CAN report both, per Task 1's brief.

#include "bridge.h"
#include "include/uberdemotools.h"

// UDT's own INTERNAL headers, deliberately. The Makefile already compiles this
// file with -Iudt/src (it has to: the vendored .cpp files under udt/src need
// it), so this costs no build-system change. It buys exactly one thing: the
// snapshot's deltaNum, which UDT decodes but does not put on the public
// udtCuSnapshotMessage struct. See the long note on demo_snap_t::delta in
// bridge.h for the full investigation, and ReadSnapshotDelta() below for the
// validation that keeps this from silently rotting if the vendored UDT is ever
// updated.
#include "custom_context.hpp"

#include <cstdarg>
#include <cstring>
#include <cstdio>
#include <cstdlib>

static void LogToStderr(s32 logLevel, const char* message) {
    // Route UDT's own info/warning/error messages to stderr instead of
    // discarding them (a NULL MessageCb, as in the brief's original stub,
    // hid the real reason a "successful" cut produced no output file during
    // Task 1's Step 7 live test -- see the EndTimeMs=-1 pitfall above).
    fprintf(stderr, "[udt log %d] %s\n", (int)logLevel, message);
}

// udtInitLibrary() sets up the thread-local temp allocator and builds the
// protocol magic-number lookup tables. UDT's own thread_local_allocators.cpp
// asserts ("You forgot to call udtInitLibrary.") if the former is missing,
// and the Cu plug-in's ProcessSnapshotMessage calls GetIdNumber(), which
// reads the latter. Task 1's demo_cut() happened not to trip either, but
// relying on that is luck, so every entry point in this file goes through
// here first. The C++11 function-local static guarantees exactly-once,
// thread-safe initialisation; udtShutDownLibrary() is deliberately never
// called - these tables live for the process, like the finalize thread.
static void EnsureUdtInit() {
    static const int once = (udtInitLibrary(), 1);
    (void)once;
}

static void SetErr(char* err_buf, int err_buf_len, const char* fmt, ...) {
    if(!err_buf || err_buf_len <= 0) {
        return;
    }
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(err_buf, (size_t)err_buf_len, fmt, ap);
    va_end(ap);
}

extern "C" int demo_cut(const char* in_path, const char* out_folder,
                         int start_ms, int end_ms,
                         char* err_buf, int err_buf_len) {
    if (err_buf && err_buf_len > 0) {
        err_buf[0] = '\0';
    }

    // Guard against the EndTimeMs pitfall documented above: UDT itself
    // silently queues zero cuts (and still returns success) when
    // start_ms >= end_ms, which previously produced an empty out_folder
    // with no diagnostic at all. Fail loudly here instead.
    if (start_ms >= end_ms) {
        if (err_buf && err_buf_len > 0) {
            snprintf(err_buf, err_buf_len,
                     "invalid range: start_ms (%d) must be < end_ms (%d); "
                     "note end_ms=-1 does NOT mean \"to end of file\" -- "
                     "pass a real end server-time (e.g. INT32_MAX)",
                     start_ms, end_ms);
        }
        return 1;
    }

    EnsureUdtInit();

    udtParseArg info;
    memset(&info, 0, sizeof(info));
    info.OutputFolderPath = out_folder;
    info.MessageCb = LogToStderr;

    udtCut cut;
    memset(&cut, 0, sizeof(cut));
    cut.StartTimeMs = start_ms;
    cut.EndTimeMs = end_ms;
    cut.GameStateIndex = 0;

    udtCutByTimeArg cutInfo;
    memset(&cutInfo, 0, sizeof(cutInfo));
    cutInfo.CutCount = 1;
    cutInfo.Cuts = &cut;

    udtParserContext* context = udtCreateContext();
    if (!context) {
        if (err_buf && err_buf_len > 0) {
            snprintf(err_buf, err_buf_len, "udtCreateContext failed");
        }
        return 1;
    }

    s32 result = udtCutDemoFileByTime(context, &info, &cutInfo, in_path);
    udtDestroyContext(context);

    if (result != (s32)udtErrorCode::None) {
        if (err_buf && err_buf_len > 0) {
            snprintf(err_buf, err_buf_len, "udtCutDemoFileByTime error %d: %s",
                     (int)result, udtGetErrorCodeString(result));
        }
        return 1;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// demo_scan: one streaming pass over a .dm_91's own framing.
// ---------------------------------------------------------------------------

// Returns 1 when a raw config string value carries "\time\0" exactly -- QL's
// "the match is in progress" marker. Returns 0 for any other "\time\" value
// and for a value with no "\time\" key at all.
//
// The three values this key actually takes, observed in a real QL duel
// capture (Task 6a evidence dump, see that report):
//   "\time\-1"      no match scheduled (plain warmup)
//   "\time\211725"  countdown running; the value is the ABSOLUTE server time
//                   the match will start at (here 10s after the update)
//   "\time\0"       match in progress
// So "not -1" is NOT the same as "live" -- the countdown value is a large
// positive number. Only an exact 0 means the match is running.
static int CsTimeIsMatchLive(const char* cs) {
    if(cs == NULL) {
        return 0;
    }
    static const char key[] = "\\time\\";
    const char* p = strstr(cs, key);
    if(p == NULL) {
        return 0;
    }
    p += sizeof(key) - 1;
    // Values are backslash-delimited in a Quake info string.
    return (p[0] == '0' && (p[1] == '\0' || p[1] == '\\')) ? 1 : 0;
}

// Recovers the wire deltaNum of the snapshot the Cu API just handed back.
// Returns the number of messages back the baseline sits (0 = full/keyframe),
// or -1 when the value could not be established. See demo_snap_t::delta in
// bridge.h for why this has to reach into UDT's internals at all.
//
// The validation is the load-bearing part: GetClientSnapshot() indexes a ring
// of PACKET_BACKUP entries by (messageNum & PACKET_MASK), and parser.cpp's
// ParseSnapshot Com_Memcpy's the finished snapshot into that slot immediately
// BEFORE it calls the plug-ins - so for the snapshot we were just given, that
// slot must hold a snapshot whose messageNum and serverTime both match the
// public struct. If either disagrees we are looking at a stale ring entry (or
// at a vendored UDT that changed shape) and report -1 instead of a number.
static int ReadSnapshotDelta(udtCuContext* context, const udtCuSnapshotMessage* snap) {
    if(context == NULL || snap == NULL) {
        return -1;
    }
    udtCuContext_s* const cu = (udtCuContext_s*)context;
    const idClientSnapshotBase* const cs =
        cu->Context.Parser.GetClientSnapshot(snap->MessageNumber & PACKET_MASK);
    if(cs == NULL) {
        return -1;
    }
    if(cs->messageNum != snap->MessageNumber || cs->serverTime != snap->ServerTimeMs) {
        return -1;
    }
    // UDT stores the ABSOLUTE baseline message number (messageNum - wireByte),
    // using -1 for "the wire byte was 0, this is a full snapshot". Turn it back
    // into the relative wire value, which is what the file actually holds and
    // what stays meaningful after UDT renumbers messages on a cut.
    if(cs->deltaNum < 0) {
        return 0;
    }
    const s32 relative = cs->messageNum - cs->deltaNum;
    if(relative < 0 || relative > 255) {
        return -1; // Not a byte: something is wrong, do not report it as data.
    }
    return (int)relative;
}

// Growable demo_snap_t array. Only ever used by demo_index(); demo_scan()
// passes NULL and pays nothing.
struct SnapCollector {
    demo_snap_t* items;
    int count;
    int cap;
    int oom;
    int delta_unknown;
};

static int SnapCollectorAdd(SnapCollector* c, long long off, int t, int len, int delta) {
    if(c->oom) {
        return 0;
    }
    if(c->count == c->cap) {
        // ~40 Hz snapshots, so 4096 rows is roughly the first 100 seconds; a
        // long match doubles a handful of times and stops there.
        const int newCap = (c->cap == 0) ? 4096 : (c->cap * 2);
        demo_snap_t* const grown =
            (demo_snap_t*)realloc(c->items, (size_t)newCap * sizeof(demo_snap_t));
        if(grown == NULL) {
            c->oom = 1;
            return 0;
        }
        c->items = grown;
        c->cap   = newCap;
    }
    demo_snap_t* const s = &c->items[c->count++];
    s->off   = off;
    s->t     = t;
    s->len   = len;
    s->delta = delta;
    if(delta < 0) {
        c->delta_unknown++;
    }
    return 1;
}

// THE single walk. demo_scan() and demo_index() are both thin wrappers around
// it; coll may be NULL, in which case nothing per-snapshot is retained. `who`
// is only used to prefix error messages with the caller's name.
static int ScanWalk(const char* who, const char* in_path, int arm_seq, demo_scan_t* out,
                    SnapCollector* coll, char* err_buf, int err_buf_len) {
    if(err_buf && err_buf_len > 0) {
        err_buf[0] = '\0';
    }
    if(in_path == NULL || out == NULL) {
        SetErr(err_buf, err_buf_len, "%s: NULL argument", who);
        return 1;
    }

    memset(out, 0, sizeof(*out));
    out->first_ms               = -1;
    out->last_ms                = -1;
    out->arm_ms                 = -1;
    out->live_ms                = -1;
    out->client_num             = -1;
    out->clock_resets_since_arm = (arm_seq >= 0) ? 0 : -1;

    EnsureUdtInit();

    const u32 protocol = udtGetProtocolByFilePath(in_path);
    if(udtIsValidProtocol(protocol) == 0) {
        SetErr(err_buf, err_buf_len, "%s: unrecognised protocol for %s", who, in_path);
        return 1;
    }

    FILE* const fp = fopen(in_path, "rb");
    if(fp == NULL) {
        SetErr(err_buf, err_buf_len, "%s: cannot open %s", who, in_path);
        return 1;
    }

    // ID_MAX_MSG_LENGTH is what udtCuParseMessage itself passes as the
    // message's maxsize, so a longer block could not be parsed anyway.
    unsigned char* const buffer = (unsigned char*)malloc(ID_MAX_MSG_LENGTH);
    if(buffer == NULL) {
        fclose(fp);
        SetErr(err_buf, err_buf_len, "%s: out of memory", who);
        return 1;
    }

    udtCuContext* const context = udtCuCreateContext();
    if(context == NULL) {
        free(buffer);
        fclose(fp);
        SetErr(err_buf, err_buf_len, "%s: udtCuCreateContext failed", who);
        return 1;
    }
    udtCuSetMessageCallback(context, LogToStderr);

    int rc = 0;
    const s32 startResult = udtCuStartParsing(context, protocol);
    if(startResult != (s32)udtErrorCode::None) {
        SetErr(err_buf, err_buf_len, "%s: udtCuStartParsing error %d: %s",
               who, (int)startResult, udtGetErrorCodeString(startResult));
        rc = 1;
    }

    int pendingLive = 0;
    // 0 while we are inside the leading gamestate, which is the only one
    // demo_cut() can address. Snapshots past the second gamestate message are
    // counted for gamestate_count but contribute no times.
    int gsIndex = 0;
    // Byte offset of the header we are about to read. A .dm_91 has no file
    // header of its own: message 0's (seq,len) pair sits at offset 0.
    long long filePos = 0;

    while(rc == 0) {
        const long long msgOff = filePos;
        s32 header[2];
        if(fread(header, sizeof(s32), 2, fp) != 2) {
            break; // Clean end of file, or a capture truncated by a crash.
        }
        if(header[0] == -1 && header[1] == -1) {
            break; // The writer's explicit end-of-demo marker.
        }
        const s32 seq = header[0];
        const s32 len = header[1];
        if(len <= 0 || len > ID_MAX_MSG_LENGTH) {
            SetErr(err_buf, err_buf_len,
                   "%s: bad block length %d at message %d in %s",
                   who, (int)len, out->message_count, in_path);
            rc = 1;
            break;
        }
        if(fread(buffer, 1, (size_t)len, fp) != (size_t)len) {
            break; // Truncated tail: keep whatever we parsed up to here.
        }
        filePos = msgOff + 8 + (long long)len;

        udtCuMessageInput input;
        memset(&input, 0, sizeof(input));
        input.Buffer          = buffer;
        input.BufferByteCount = (u32)len;
        input.MessageSequence = seq;

        udtCuMessageOutput output;
        memset(&output, 0, sizeof(output));
        u32 continueParsing = 0;
        const s32 parseResult = udtCuParseMessage(context, &output, &continueParsing, &input);
        if(parseResult != (s32)udtErrorCode::None) {
            SetErr(err_buf, err_buf_len, "%s: udtCuParseMessage error %d: %s (message %d of %s)",
                   who, (int)parseResult, udtGetErrorCodeString(parseResult), out->message_count,
                   in_path);
            rc = 1;
            break;
        }
        out->message_count++;

        if(output.IsGameState != 0) {
            out->gamestate_count++;
            if(out->gamestate_count == 1 && output.GameStateOrSnapshot.GameState != NULL) {
                out->client_num = (int)output.GameStateOrSnapshot.GameState->ClientNumber;
            }
            if(out->gamestate_count > 1) {
                gsIndex++;
            }
        }
        // gsIndex != 0 means we are past the leading gamestate: a different
        // server-time clock that demo_cut() cannot address, so nothing from
        // there may contribute to the times reported here.
        if(gsIndex == 0) {
            // Commands are parsed before the snapshot inside one server
            // message (parser.cpp's ParseServerMessage loop), so a config
            // string update seen here is already in effect for this message's
            // own snapshot.
            for(u32 i = 0; i < output.CommandCount; ++i) {
                const udtCuCommandMessage& cmd = output.Commands[i];
                if(cmd.IsConfigString == 0 || cmd.ConfigStringIndex != DEMO_CS_WARMUP_INDEX) {
                    continue;
                }
                const char* value = NULL;
                if(cmd.CommandTokens != NULL && cmd.TokenCount >= 3) {
                    value = cmd.CommandTokens[2];
                }
                if(CsTimeIsMatchLive(value) && arm_seq >= 0 && seq >= arm_seq && out->live_ms < 0) {
                    pendingLive = 1;
                }
            }

            if(output.IsGameState == 0 && output.GameStateOrSnapshot.Snapshot != NULL) {
                const udtCuSnapshotMessage* const snap = output.GameStateOrSnapshot.Snapshot;
                const s32 t = snap->ServerTimeMs;
                if(out->first_ms < 0) {
                    out->first_ms = (int)t;
                } else if((int)t < out->last_ms) {
                    out->clock_resets++;
                    // arm_ms already set (in an earlier iteration) means this
                    // backward jump sits inside [arm_ms, ...] - the exact
                    // region demo_cut() will be asked to select from. A jump
                    // still ahead of arm_ms is stale, pre-arm data the cut
                    // discards regardless (see the field's own comment in
                    // bridge.h) and must not veto it.
                    if(out->arm_ms >= 0) {
                        out->clock_resets_since_arm++;
                    }
                }
                out->last_ms = (int)t;
                out->snapshot_count++;
                if(out->arm_ms < 0 && arm_seq >= 0 && seq >= arm_seq) {
                    out->arm_ms = (int)t;
                }
                if(pendingLive && out->live_ms < 0) {
                    out->live_ms = (int)t;
                    pendingLive  = 0;
                }
                if(coll != NULL &&
                   !SnapCollectorAdd(coll, msgOff, (int)t, (int)len,
                                     ReadSnapshotDelta(context, snap))) {
                    SetErr(err_buf, err_buf_len, "%s: out of memory collecting snapshot %d of %s",
                           who, out->snapshot_count, in_path);
                    rc = 1;
                    break;
                }
            }
        }

        if(continueParsing == 0) {
            break;
        }
    }

    udtCuDestroyContext(context);
    free(buffer);
    fclose(fp);

    if(rc == 0 && out->snapshot_count == 0) {
        SetErr(err_buf, err_buf_len, "%s: no snapshot found in %s (%d messages)",
               who, in_path, out->message_count);
        rc = 1;
    }
    return rc;
}

extern "C" int demo_scan(const char* in_path, int arm_seq, demo_scan_t* out,
                         char* err_buf, int err_buf_len) {
    return ScanWalk("demo_scan", in_path, arm_seq, out, NULL, err_buf, err_buf_len);
}

extern "C" int demo_index(const char* in_path, demo_index_result_t* out,
                          char* err_buf, int err_buf_len) {
    if(err_buf && err_buf_len > 0) {
        err_buf[0] = '\0';
    }
    if(out == NULL) {
        SetErr(err_buf, err_buf_len, "demo_index: NULL argument");
        return 1;
    }
    memset(out, 0, sizeof(*out));

    SnapCollector coll;
    memset(&coll, 0, sizeof(coll));

    // arm_seq is -1: arm_ms/live_ms are a property of the RAW capture (the
    // sequence number the capture side stamped), not of a finalised file, and
    // the index is only ever built for finalised files.
    const int rc = ScanWalk("demo_index", in_path, -1, &out->scan, &coll, err_buf, err_buf_len);
    if(rc != 0) {
        free(coll.items);
        memset(out, 0, sizeof(*out));
        return rc;
    }

    out->snaps         = coll.items;
    out->count         = coll.count;
    out->delta_unknown = coll.delta_unknown;

    // Belt and braces: the rows come off the same counter as snapshot_count in
    // the same loop, so a mismatch is impossible without a code change - which
    // is exactly when a caller most wants to be told rather than to ship a
    // silently short index. The spec's rule is "if snapshot counts from UDT vs
    // framing disagree, fail that file's index".
    if(out->count != out->scan.snapshot_count) {
        SetErr(err_buf, err_buf_len,
               "demo_index: collected %d row(s) but counted %d snapshot(s) in %s",
               out->count, out->scan.snapshot_count, in_path);
        demo_index_free(out);
        return 1;
    }
    return 0;
}

extern "C" void demo_index_free(demo_index_result_t* out) {
    if(out == NULL) {
        return;
    }
    free(out->snaps);
    out->snaps = NULL;
    out->count = 0;
}

// ---------------------------------------------------------------------------
// demo_range: the independent cross-check for demo_scan's first/last times.
// ---------------------------------------------------------------------------

extern "C" int demo_range(const char* in_path, int* first_ms, int* last_ms,
                          char* err_buf, int err_buf_len) {
    if(err_buf && err_buf_len > 0) {
        err_buf[0] = '\0';
    }
    if(in_path == NULL || first_ms == NULL || last_ms == NULL) {
        SetErr(err_buf, err_buf_len, "demo_range: NULL argument");
        return 1;
    }
    *first_ms = -1;
    *last_ms  = -1;

    EnsureUdtInit();

    const u32 plugIns[1] = { (u32)udtParserPlugIn::GameState };

    udtParseArg info;
    memset(&info, 0, sizeof(info));
    info.PlugIns     = plugIns;
    info.PlugInCount = 1;
    info.MessageCb   = LogToStderr;

    s32 errorCode            = (s32)udtErrorCode::None;
    const char* filePaths[1] = { in_path };

    udtMultiParseArg extraInfo;
    memset(&extraInfo, 0, sizeof(extraInfo));
    extraInfo.FilePaths        = filePaths;
    extraInfo.OutputErrorCodes = &errorCode;
    extraInfo.FileCount        = 1;
    extraInfo.MaxThreadCount   = 1;

    udtParserContextGroup* group = NULL;
    const s32 result = udtParseDemoFiles(&group, &info, &extraInfo);
    if(result != (s32)udtErrorCode::None) {
        if(group != NULL) {
            udtDestroyContextGroup(group);
        }
        SetErr(err_buf, err_buf_len, "demo_range: udtParseDemoFiles error %d: %s",
               (int)result, udtGetErrorCodeString(result));
        return 1;
    }

    u32 contextCount = 0;
    if(group == NULL || udtGetContextCountFromGroup(group, &contextCount) != (s32)udtErrorCode::None ||
       contextCount == 0) {
        if(group != NULL) {
            udtDestroyContextGroup(group);
        }
        SetErr(err_buf, err_buf_len, "demo_range: no parser context for %s", in_path);
        return 1;
    }

    udtParserContext* context = NULL;
    if(udtGetContextFromGroup(group, 0, &context) != (s32)udtErrorCode::None || context == NULL) {
        udtDestroyContextGroup(group);
        SetErr(err_buf, err_buf_len, "demo_range: cannot get parser context for %s", in_path);
        return 1;
    }

    udtParseDataGameStateBuffers buffers;
    memset(&buffers, 0, sizeof(buffers));
    if(udtGetContextPlugInBuffers(context, (u32)udtParserPlugIn::GameState, &buffers) !=
           (s32)udtErrorCode::None ||
       buffers.GameStates == NULL || buffers.GameStateCount == 0) {
        udtDestroyContextGroup(group);
        SetErr(err_buf, err_buf_len, "demo_range: no gamestate data for %s", in_path);
        return 1;
    }

    // Span the whole file, not just gamestate 0: a capture that survived a
    // mid-demo map change would have more than one.
    int lo = buffers.GameStates[0].FirstSnapshotTimeMs;
    int hi = buffers.GameStates[0].LastSnapshotTimeMs;
    for(u32 i = 1; i < buffers.GameStateCount; ++i) {
        if(buffers.GameStates[i].FirstSnapshotTimeMs < lo) {
            lo = buffers.GameStates[i].FirstSnapshotTimeMs;
        }
        if(buffers.GameStates[i].LastSnapshotTimeMs > hi) {
            hi = buffers.GameStates[i].LastSnapshotTimeMs;
        }
    }
    *first_ms = lo;
    *last_ms  = hi;

    udtDestroyContextGroup(group);
    return 0;
}
