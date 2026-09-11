#include "bridge.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char** argv) {
    if (argc != 4 && argc != 5) {
        fprintf(stderr, "usage: %s <in.dm_91> <out_folder> <start_ms> [end_ms]\n", argv[0]);
        return 2;
    }
    // NOTE (Task 1 spike finding): end_ms=-1 does NOT mean "cut to end of
    // file" -- see bridge.h/bridge.cpp comments. udtCutDemoFileByTime only
    // registers a cut when StartTimeMs < EndTimeMs, so EndTimeMs=-1 is
    // silently a no-op (0 cuts queued, still returns success, writes
    // nothing). Default here to INT32_MAX so plain 3-arg invocations still
    // demonstrate a real "cut to end of file" instead of reproducing the
    // no-op. Pass an explicit 4th arg to test a specific end_ms.
    int end_ms = (argc == 5) ? atoi(argv[4]) : 2147483647;
    char err[256];
    int rc = demo_cut(argv[1], argv[2], atoi(argv[3]), end_ms, err, sizeof(err));
    if (rc != 0) {
        fprintf(stderr, "demo_cut failed: %s\n", err);
        return 1;
    }
    printf("demo_cut OK\n");
    return 0;
}
