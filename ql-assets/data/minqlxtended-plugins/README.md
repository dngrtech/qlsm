# minqlxtended plugin baseline

Vendored from [tjone270/minqlxtended-plugins](https://github.com/tjone270/minqlxtended-plugins)
at commit `d93a3ce758bac650ad1b00ff4850f06873c914a9` ("plugins v1.0.0").

These files are synced to every minqlxtended host by `setup_host.yml` and
backfilled into each instance's plugin directory by `add_qlds_instance.yml`.
Anything here is available to an instance whether or not a preset ships it.

`serverchecker.py` is **not** upstream. It is QLSM's own plugin, ported to the
minqlxtended API, and it is a hard dependency of live status: it writes
`minqlx:server_status:<port>`, which `ui/task_logic/service_runtime.py` reads.
`manifest.json` marks it `"origin": "qlsm"` so a diff against upstream skips it.

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
