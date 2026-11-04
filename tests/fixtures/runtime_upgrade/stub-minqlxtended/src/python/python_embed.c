/*
 * Stub of minqlxtended's src/python/python_embed.c for the runtime-upgrade
 * integration fixture: only the `loader` literal QLSM patches, with the same
 * surrounding lines, so ql-assets/patches/minqlxtended/qlsm-python-deps.patch
 * applies exactly as it does to the pinned upstream commit.
 */
#define CORE_MODULE "minqlxtended.zip"

static int initialized = 0;

/*
 * Without this, PyRun_File*() and PyRun_String*() return a bare NULL for a module with an
 * error in it and the traceback is unreachable.
 */
static const char loader[] = "import traceback\n"
                             "try:\n"
                             "  import sys\n"
                             "  sys.path.append('" CORE_MODULE "')\n"
                             "  sys.path.append('.')\n"
                             "  import minqlxtended\n"
                             "  minqlxtended.initialize()\n"
                             "  ret = True\n"
                             "except Exception as e:\n"
                             "  e = traceback.format_exc().rstrip('\\n')\n"
                             "  for line in e.split('\\n'): print(line)\n"
                             "  ret = False\n";
