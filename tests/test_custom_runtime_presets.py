from types import SimpleNamespace

from ui.preset_compat import apply_compatibility
from ui.runtime import plugin_api_for_host


def custom(api="minqlx"):
    return SimpleNamespace(runtime="custom", runtime_plugin_api=api)


def test_minqlx_preset_round_trip_on_custom_preserves_files_and_checks(monkeypatch):
    from ui.routes import draft_routes

    host = custom()
    monkeypatch.setattr(draft_routes, "get_host_by_name", lambda _name: host)
    runtime = draft_routes._resolve_source_runtime({"source": "instance", "host": "fixture"})
    source = {"scripts": {"legacy.py": "import minqlx\r\n"}, "checked_plugins": ["legacy.py"]}
    assert runtime == "minqlx"
    assert apply_compatibility(source, runtime, plugin_api_for_host(host)) is source


def test_custom_same_api_uses_minqlx_pool_for_pool_only_plugin():
    from ui.task_logic.plugin_update_check import _pool_hashes, _common_pool_remote_dir

    assert _pool_hashes(custom()) == _pool_hashes(SimpleNamespace(runtime="minqlx"))
    assert _common_pool_remote_dir(custom()).endswith("/minqlx-plugins")


def test_custom_cross_api_uses_existing_compatibility_verdict():
    source = {"scripts": {"legacy.py": "import minqlx\n"}, "checked_plugins": ["legacy.py"]}
    expected = apply_compatibility(source, "minqlx", "minqlxtended")
    assert expected["compatibility"]["stripped"]
    assert apply_compatibility(source, "minqlx", plugin_api_for_host(custom("minqlxtended"))) == expected
