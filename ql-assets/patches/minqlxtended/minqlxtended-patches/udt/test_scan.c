// Standalone harness for the Task 6a bridge additions (demo_scan/demo_range).
//
// Build (from udt/, same toolchain as test_bridge.c -- see bridge.cpp's header
// comment for the vendoring notes):
//     g++ -std=c++14 -Iinclude -Isrc -c src/*.cpp bridge.cpp
//     gcc -std=gnu11 -Iinclude -c test_scan.c -o test_scan.o
//     g++ *.o -o test_scan -lstdc++
//
// Usage:
//     ./test_scan <demo.dm_91> [arm_seq]
//
// Prints demo_scan()'s results and, as an independent cross-check on the same
// file, demo_range()'s FirstSnapshotTimeMs/LastSnapshotTimeMs read through the
// completely separate udtParseDemoFiles + GameState plug-in path. The two must
// agree; the exit code is non-zero if they do not.

#include <stdio.h>
#include <stdlib.h>

#include "bridge.h"

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <demo.dm_91> [arm_seq]\n", argv[0]);
        return 2;
    }
    const char *path = argv[1];
    int arm_seq      = (argc > 2) ? atoi(argv[2]) : -1;

    char err[512];
    demo_scan_t scan;
    if (demo_scan(path, arm_seq, &scan, err, (int)sizeof(err)) != 0) {
        fprintf(stderr, "demo_scan failed: %s\n", err);
        return 1;
    }

    printf("scan  messages=%d snapshots(gs0)=%d gamestates=%d clock_resets=%d\n",
           scan.message_count, scan.snapshot_count, scan.gamestate_count, scan.clock_resets);
    printf("scan  first_ms=%d last_ms=%d span_ms=%d\n", scan.first_ms, scan.last_ms,
           scan.last_ms - scan.first_ms);
    printf("scan  arm_seq=%d -> arm_ms=%d (offset from first: %d ms)\n", arm_seq, scan.arm_ms,
           (scan.arm_ms < 0) ? -1 : scan.arm_ms - scan.first_ms);
    printf("scan  live_ms=%d (cs %d warmup->live at/after arm)\n", scan.live_ms, DEMO_CS_WARMUP_INDEX);

    int first = -1, last = -1;
    if (demo_range(path, &first, &last, err, (int)sizeof(err)) != 0) {
        fprintf(stderr, "demo_range failed: %s\n", err);
        return 1;
    }
    printf("range first_ms=%d last_ms=%d  (udtParseDemoFiles + GameState plug-in)\n", first, last);

    if (scan.clock_resets != 0) {
        printf("NOTE: %d backwards server-time jump(s) in this file -- it holds more than one\n"
               "      clock epoch, so demo_cut() must not be used on it and the two routes'\n"
               "      first/last are not comparable.\n",
               scan.clock_resets);
        return 0;
    }
    if (scan.gamestate_count != 1) {
        // demo_range() reports min/max across ALL gamestates, demo_scan() only
        // gamestate 0, so the two legitimately differ here. Nothing to diff.
        printf("NOTE: %d gamestates in this file -- demo_scan reports gamestate 0 only,\n"
               "      demo_range spans them all, so the two are not comparable.\n",
               scan.gamestate_count);
        return 0;
    }
    if (first != scan.first_ms || last != scan.last_ms) {
        fprintf(stderr,
                "MISMATCH: demo_scan says [%d,%d], demo_range says [%d,%d]\n",
                scan.first_ms, scan.last_ms, first, last);
        return 1;
    }
    printf("OK: both routes agree on [%d,%d]\n", first, last);
    return 0;
}
