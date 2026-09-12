# Compat shim — not a real plugin, never appears in qlx_plugins.
#
# minqlxtended is a fork of minqlx that keeps the same Plugin/API surface but
# ships under its own module name. A pool plugin with no native
# minqlxtended-plugins equivalent may still do a bare `import minqlx` rather
# than `import minqlxtended as minqlx`. Since minqlx's own loader adds the
# plugins directory to sys.path, dropping this file there lets Python
# resolve `import minqlx` to the real minqlxtended module instead of failing
# with ModuleNotFoundError — no need to touch those plugins' source.
#
# Only takes effect when this host is actually running minqlxtended (see
# Host.runtime / ui/runtime.py). On a plain minqlx host, minqlxtended isn't
# installed and this shim is never imported (nothing here imports it
# eagerly).
import sys as _sys

import minqlxtended as _minqlxtended

_sys.modules[__name__] = _minqlxtended
