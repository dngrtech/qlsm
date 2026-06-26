#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <sys/mman.h>
#include <unistd.h>
#include <errno.h>
#include <limits.h>
#include <time.h>

/*
 * force_rate.so - LD_PRELOAD library for Quake Live Dedicated Server
 *
 * Patches Sys_IsLANAddress (FUN_004518d0) to always return 1,
 * causing the server to force rate=99999 for all clients.
 *
 * Usage:
 *   LD_PRELOAD=./force_rate.so ./qzeroded.x64 +set sv_lanForceRate 1 ...
 *
 * Build:
 *   gcc -shared -fPIC -o force_rate.so force_rate.c
 */

/* Address of Sys_IsLANAddress in qzeroded.x64 */
#define SYS_ISLANADDRESS_ADDR 0x004518d0
#define PATCH_RETRY_ATTEMPTS 50
#define PATCH_RETRY_DELAY_NS 20000000L

static int is_qzeroded_process(void)
{
    char exe_path[PATH_MAX];
    ssize_t len = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
    if (len < 0)
        return 0;
    exe_path[len] = '\0';
    return strstr(exe_path, "qzeroded") != NULL;
}

static int page_is_mapped(void *page_start, long page_size)
{
    unsigned char vec;
    return mincore(page_start, (size_t)page_size, &vec) == 0;
}

static void sleep_retry_delay(void)
{
    struct timespec delay = { .tv_sec = 0, .tv_nsec = PATCH_RETRY_DELAY_NS };
    struct timespec remaining;

    while (nanosleep(&delay, &remaining) != 0 && errno == EINTR)
        delay = remaining;
}

static int wait_for_target_page(void *page_start, long page_size)
{
    /* 50 attempts at 20ms each gives qzeroded up to ~1s to map its text page. */
    for (int attempt = 0; attempt < PATCH_RETRY_ATTEMPTS; attempt++) {
        if (page_is_mapped(page_start, page_size))
            return 1;
        sleep_retry_delay();
    }

    return 0;
}

/*
 * Patch Sys_IsLANAddress to always return 1.
 *
 * Original prologue bytes don't matter — we overwrite the start with:
 *   MOV EAX, 1   (B8 01 00 00 00)
 *   RET           (C3)
 *
 * This is 6 bytes, well within any function prologue.
 */
static void patch_sys_islanaddress(void)
{
    void *target = (void *)SYS_ISLANADDRESS_ADDR;
    long page_size = sysconf(_SC_PAGESIZE);

    if (page_size <= 0)
        return;

    void *page_start = (void *)((uintptr_t)target & ~(page_size - 1));

    /* Silently skip if the target page isn't mapped — this constructor runs in
     * every process that inherits LD_PRELOAD (e.g. the bash wrapper script and
     * any subshells it spawns). Only qzeroded.x64 maps this address. For the
     * real qzeroded process, retry briefly so constructor/load ordering does
     * not cause a false negative before the text page appears. */
    if (!page_is_mapped(page_start, page_size)) {
        if (!is_qzeroded_process())
            return;
        if (!wait_for_target_page(page_start, page_size)) {
            fprintf(stderr,
                    "[force_rate] target page %p not mapped after retry; patch skipped\n",
                    page_start);
            return;
        }
    }

    if (mprotect(page_start, page_size, PROT_READ | PROT_WRITE | PROT_EXEC) != 0) {
        perror("[force_rate] mprotect failed");
        return;
    }

    /* Write: MOV EAX, 1; RET */
    uint8_t patch[] = { 0xB8, 0x01, 0x00, 0x00, 0x00, 0xC3 };
    memcpy(target, patch, sizeof(patch));
    __builtin___clear_cache((char *)target, (char *)target + sizeof(patch));

    if (mprotect(page_start, page_size, PROT_READ | PROT_EXEC) != 0)
        perror("[force_rate] mprotect restore failed");

    printf("[force_rate] Patched Sys_IsLANAddress at %p to always return 1\n", target);
    printf("[force_rate] All clients will receive rate=99999\n");
}

__attribute__((constructor))
static void init(void)
{
    patch_sys_islanaddress();
}
