# System Hooks

Built-in LD_PRELOAD hooks shipped with QLSM. These are referenced from
`ui/task_logic/ansible_instance_mgmt.py:_SYSTEM_HOOKS` and synced to
each instance's `/home/ql/qlds-<port>/system-hooks/` directory by
`ansible/playbooks/update_instance_hooks.yml`.

Unlike user-uploaded hooks (which land in `minqlx-plugins/`), these
binaries are part of the platform itself and cannot be uploaded or
disabled via the Hooks UI. The filename of each entry is automatically
added to `RESERVED_HOOK_FILENAMES`.

## Files

- `force_rate.so` / `force_rate.c` — patches `Sys_IsLANAddress` to
  always return 1 so the engine treats every client as LAN. Combined
  with `+set sv_lanForceRate 1`, this forces `rate=99999` for all
  clients. Activated per-instance by the `lan_rate_enabled` toggle on
  hosts that have been migrated to the hook mechanism (`Host.lan_rate_uses_hook = True`).

## Rebuilding

```
gcc -shared -fPIC -Wall -Wextra -Werror -Wl,--build-id=none -o ql-assets/data/system-hooks/force_rate.so ql-assets/data/system-hooks/force_rate.c
```

or:

```
make force-rate.so
```

x86-64 Linux only. Commit the rebuilt `.so` alongside source changes.
