"""Drift guard: ql-assets/data/minqlx-plugins/ (pool, source of truth for
plugin logic) must stay in sync with configs/presets/_builtin/default/scripts/
(the builtin "default" preset, physically copied onto every instance built
from it). See ui/plugin_pool_sync.py for what's in scope and why.

If this test fails after a plugin change, run:
    flask sync-plugin-pool
and commit the result alongside the plugin change.
"""

from ui.plugin_pool_sync import diff_pool_preset


def test_builtin_default_preset_matches_plugin_pool():
    diffs = diff_pool_preset()
    assert diffs == [], (
        "Builtin default preset has drifted from the plugin pool "
        "(run `flask sync-plugin-pool` and commit): " + repr(diffs)
    )
