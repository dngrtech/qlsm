#!/usr/bin/env python3
"""Apply the full qlhub patch chain to a minqlxtended build tree before make."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# tools/gen_stub.py's SIGNATURES dict is hand-maintained (PyArg_ParseTuple format
# strings give arity but not argument names/types), so every native this repo's
# patches add to minqlxtendedMethods[] needs an entry here too, or gen_stub.py's
# own --check fails and the natives never get re-exported by the minqlxtended
# package (they still register fine on the low-level _minqlxtended C module, so
# calling them via gdb or ctypes "works" while `import minqlxtended as minqlx;
# minqlx.<native>` raises AttributeError - this exact split silently broke
# an item-restore code path in production: live gdb showed hasattr(minqlx,
# "find_map_item_entity") False despite the C function working when called
# directly. Keyed by native name so a repeat run stays a no-op.
GEN_STUB_SIGNATURES = {
    # patch-minqlxtended-item-respawn.py / patch-minqlxtended-item-events.py
    "touch_map_item": '"(entity_id: int, client_id: int, /) -> bool"',
    "hide_map_item": '"(entity_id: int, forced_item_id: int = ..., /) -> bool"',
    "show_map_item": '"(entity_id: int, forced_item_id: int = ..., /) -> bool"',
    "find_map_item_entity": (
        '("(x: float, y: float, z: float, radius: float = ..., "\n'
        '                             "want_item_id: int = ..., exclude_entity_id: int = ..., /) -> int")'
    ),
    "set_item_respawn_delay": '"(entity_id: int, delay_ms: int, /) -> bool"',
    "get_map_item_state": '"(entity_id: int, /) -> tuple[int, int, int, int, int, int, int, str]"',
    "set_pickup_lock": '"(active: int, /) -> bool"',
    # patch-minqlxtended-demo-match.py
    "demo_arm": '"(match_id: str, map_name: str, /) -> None"',
    "demo_disarm": '"() -> None"',
    # patch-minqlxtended-set-position.py
    "set_position": '"(client_id: int, position: Vector3, /) -> bool"',
    # Not one of this repo's patches - an upstream gap in gen_stub.py itself,
    # caught 2026-08-20 by the first real Woodpecker run of
    # verify-minqlxtended-natives.py (pipeline #27): get_configstring is
    # registered in minqlxtendedMethods[] but missing from upstream's own
    # SIGNATURES dict, so it never made it into minqlxtended/__init__.py
    # either. Same failure mode as the rest of this dict, just not our bug.
    "get_configstring": '"(index: int, /) -> str"',
}


def patch_gen_stub_signatures(build_dir: Path) -> bool:
    """Add this repo's natives to gen_stub.py's SIGNATURES dict, then regenerate
    _minqlxtended.pyi and minqlxtended/__init__.py so the package actually
    re-exports them. Safe to call every run: skips names already present."""
    gen_stub = build_dir / "tools" / "gen_stub.py"
    if not gen_stub.is_file():
        print("skip (missing): tools/gen_stub.py")
        return False

    text = gen_stub.read_text(encoding="utf-8")
    missing = {name: sig for name, sig in GEN_STUB_SIGNATURES.items() if f'"{name}":' not in text}
    if missing:
        anchor = '    "cvars": "() -> Iterator[Cvar]",\n}'
        if anchor not in text:
            raise SystemExit(f"gen_stub.py SIGNATURES anchor missing in {gen_stub}")
        insert = "".join(f'    "{name}": {sig},\n' for name, sig in missing.items())
        text = text.replace(anchor, '    "cvars": "() -> Iterator[Cvar]",\n' + insert + "}", 1)
        gen_stub.write_text(text, encoding="utf-8")
        print(f"patched gen_stub.py SIGNATURES: {', '.join(sorted(missing))}")

    subprocess.run([sys.executable, str(gen_stub)], check=True, cwd=str(build_dir))
    print("regenerated _minqlxtended.pyi + minqlxtended/__init__.py")
    return True


def main() -> None:
    build_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "minqlxtended-build"
    if not build_dir.is_dir():
        raise SystemExit(f"minqlxtended build dir not found: {build_dir}")

    patches: list[tuple[Path, list[str]]] = [
        (SCRIPT_DIR / "patch-minqlxtended-set-position.py", []),
        # QLHUB_ITEM_EVENTS_DISABLE / --disable is retired as of the v1.0.0
        # port: it existed to switch off the OLD per-entity touch-repointing
        # workaround, which had a real segfault history from binary-patching
        # Touch_Item ourselves. That workaround is gone - item pickup
        # telemetry now hooks a single call inside upstream's OWN already-
        # installed My_Touch_Item (HOOK_VM(Touch_Item)), an ordinary function
        # call, not a custom VM patch - so there is no longer a comparable
        # incident class for this lever to guard against. If a real problem
        # with the native hook itself ever surfaces, disabling it needs a new
        # mechanism designed for that; passing --disable here would now be
        # silently ignored (patch-minqlxtended-item-events.py's own main()
        # discards every "-"-prefixed argument), so this is not left in a
        # form that mimics the old behavior.
        (SCRIPT_DIR / "patch-minqlxtended-item-events.py", []),
        (SCRIPT_DIR / "patch-minqlxtended-item-respawn.py", []),
        (SCRIPT_DIR / "patch-minqlxtended-redis-pool.py", []),
        # Native multi-POV demo capture. Order is a hard dependency chain, not
        # a preference:
        #   demo-cutter copies the vendored udt/ tree in and adds UDT_CXX_OBJS
        #     + the g++ link/compile rules to the Makefile;
        #   demo-match copies src/features/demo_match.{c,h} in, hooks them into
        #     src/server/hooks.c, and refuses outright if UDT_CXX_OBJS is not
        #     already in the Makefile - demo_match.c calls demo_cut()/
        #     demo_scan()/demo_index() unconditionally;
        #   demo-bindings replaces the two `// TASK5-HOOK:` comment markers
        #     demo_match.c ships with, so it has nothing to anchor on until
        #     demo-match has run.
        (SCRIPT_DIR / "patch-minqlxtended-demo-cutter.py", []),
        (SCRIPT_DIR / "patch-minqlxtended-demo-match.py", []),
        (SCRIPT_DIR / "patch-minqlxtended-demo-bindings.py", []),
    ]
    for patch, extra_args in patches:
        if not patch.is_file():
            print(f"skip (missing): {patch.name}")
            continue
        print(f"=== {patch.name} ===")
        subprocess.run([sys.executable, str(patch), *extra_args, str(build_dir)], check=True)

    print("=== gen_stub.py (republish this repo's natives via minqlxtended/__init__.py) ===")
    patch_gen_stub_signatures(build_dir)


if __name__ == "__main__":
    main()
