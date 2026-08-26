# minqlxtended plugin baseline

Vendored from [tjone270/minqlxtended-plugins](https://github.com/tjone270/minqlxtended-plugins)
at commit `d93a3ce758bac650ad1b00ff4850f06873c914a9` ("plugins v1.0.0").

These files are synced to every minqlxtended host by `setup_host.yml` and
backfilled into each instance's plugin directory by `add_qlds_instance.yml`.
Anything here is available to an instance whether or not a preset ships it.

## QLSM's own plugins

Seven files here are **not** upstream. They are QLSM's own plugins, ported to the
minqlxtended API, and `manifest.json` marks each `"origin": "qlsm"` so a diff against
upstream skips them. Their minqlx originals live in `ql-assets/data/minqlx-plugins/`.

| File | Notes |
|---|---|
| `serverchecker.py` | Hard dependency of live status: writes `minqlx:server_status:<port>`, which `ui/task_logic/service_runtime.py` reads. Never pickable — a `SYSTEM_PLUGIN`, backfilled into every instance. |
| `myFun.py` | Sound-trigger plugin. Keeps its `minqlx:myFun:*` Redis keys and its Steam Workshop item titles verbatim; both are matched by exact string. |
| `specqueue.py` | Spectator queue. Ported from the `minqlx-plugins/` copy, **not** the default preset's copy — see the warning below. |
| `player_info.py` | Does **not** carry the iouonegirl abstract base across. That base installs itself at import by downloading from a minqlx plugin repository; the one helper this plugin used from it is inlined. |
| `commands.py` | `!plugins` / `!lc`. Unrelated to upstream's `votecommands.py`, which adds `/pass` and `/veto`. |
| `reset_acc.py` | Needs no engine patch here — `gclient_t` is writable memory. On minqlxtended v1.0.2+ that includes the per-weapon WEAPONS arrays too (`shots_fired`/`shots_hit` gained a real setter), so the end-of-match weapon breakdown resets along with the aggregate accuracy. |
| `suppress_join_msg.py` | Suppresses the "joined the battle" centre-print. |

`serverchecker.py`, `reset_acc.py` and `suppress_join_msg.py` are baseline-only: present
in every instance's plugin directory, but not in `default-minqlxtended`'s `scripts/`, so
the picker does not offer them. The other four mirror the minqlx default preset, which
ships exactly those four.

> ⚠️ **Port from `ql-assets/data/minqlx-plugins/`, never from a preset's `scripts/`.**
> The two copies of `specqueue.py` on the minqlx side have diverged, and the preset copy
> is the broken one: its AFK sweep is dedented out of its `elif`, so it moves every
> player to spectator on every pass. `tests/test_default_minqlxtended_preset.py` pins
> the minqlxtended preset copies to the baseline so this cannot recur here.

## Re-vendoring against a newer upstream

    git clone https://github.com/tjone270/minqlxtended-plugins.git
    cd minqlxtended-plugins && git checkout <new-commit>
    cp *.py LICENSE <this-directory>/

Then bump `UPSTREAM_COMMIT` in `tests/test_minqlxtended_plugin_baseline.py`,
re-port `serverchecker.py` if the engine API moved, and regenerate the manifest.

## Regenerating manifest.json

Run from the repository root:

    python3 scripts/gen_plugin_manifest.py

It preserves each file's existing `origin`, defaulting new files to `upstream`.
