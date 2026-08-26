"""The runtime resolver is the single source of truth for the minqlx /
minqlxtended split. Every hardcoded path in the codebase reads through it."""
import re

import pytest

from ui.runtime import (
    DEFAULT_RUNTIME,
    MINQLX,
    MINQLXTENDED,
    VALID_RUNTIMES,
    host_runtime,
    is_valid_runtime,
    log_filename_pattern,
    normalize_runtime,
    runtime_extravars,
    runtime_paths,
)


def test_default_runtime_is_minqlx():
    """P1 must never change what an existing host resolves to."""
    assert DEFAULT_RUNTIME == MINQLX
    assert VALID_RUNTIMES == (MINQLX, MINQLXTENDED)


@pytest.mark.parametrize("value", [None, "", "  ", "nonsense", "MINQLX-2", 0, object()])
def test_unknown_runtime_falls_back_to_minqlx(value):
    """A NULL column, an old backup, or a typo must never resolve to the new
    runtime -- nothing but minqlx has ever existed."""
    assert normalize_runtime(value) == MINQLX


@pytest.mark.parametrize("value", ["minqlxtended", "MinQLXtended", "  minqlxtended  "])
def test_runtime_normalisation_is_case_and_space_insensitive(value):
    assert normalize_runtime(value) == MINQLXTENDED


def test_is_valid_runtime_rejects_non_strings_and_unknowns():
    assert is_valid_runtime("minqlx") is True
    assert is_valid_runtime("MINQLXTENDED") is True
    assert is_valid_runtime("minqlx2") is False
    assert is_valid_runtime(None) is False
    assert is_valid_runtime(3) is False


def test_every_path_key_differs_between_runtimes():
    """If a key ever matched across runtimes it would be a shared path, and the
    two runtimes would overwrite each other on the same host."""
    a = runtime_paths(MINQLX)
    b = runtime_paths(MINQLXTENDED)
    for key in ("plugins_dirname", "shared_dir", "engine_so", "launch_script",
                "log_filename", "git_repo", "git_version", "os_name"):
        assert a[key] != b[key], f"{key} is identical across runtimes"


def test_minqlx_paths_match_what_is_deployed_today():
    """These strings are what existing hosts already have on disk. Changing any
    of them silently re-deploys every minqlx host."""
    paths = runtime_paths(MINQLX)
    assert paths["plugins_dirname"] == "minqlx-plugins"
    assert paths["shared_dir"] == "/home/ql/minqlx-shared"
    assert paths["engine_so"] == "minqlx.x64.so"
    assert paths["launch_script"] == "run_server_x64_minqlx.sh"
    assert paths["log_filename"] == "minqlx.log"
    assert paths["git_version"] == "fbdd915185337791d8e209dc4b686a1ee60d3721"
    assert paths["os_name"] == "Debian 12 x64 (bookworm)"
    assert paths["os_type"] == "debian"
    assert paths["min_python"] is None
    assert paths["excluded_system_hooks"] == frozenset()


def test_minqlxtended_paths_match_the_p0_spike():
    paths = runtime_paths(MINQLXTENDED)
    assert paths["plugins_dirname"] == "minqlxtended-plugins"
    assert paths["shared_dir"] == "/home/ql/minqlxtended-shared"
    assert paths["engine_so"] == "minqlxtended.x64.so"
    assert paths["launch_script"] == "run_server_x64_minqlxtended.sh"
    assert paths["log_filename"] == "minqlxtended.log"
    assert paths["git_repo"] == "https://github.com/tjone270/minqlxtended.git"
    assert paths["git_version"] == "97fbe6715a4802545aa7eca741d11e2486a306a4"
    assert paths["os_name"] == "Ubuntu 24.04 LTS x64"
    assert paths["os_family"] == "ubuntu"
    assert paths["os_type"] == "ubuntu"
    assert paths["min_python"] == (3, 12)


def test_force_rate_is_excluded_only_on_minqlxtended():
    """minqlxtended hooks Sys_IsLANAddress itself (src/server/hooks.c:142) and a
    failed STATIC_SEARCH is fatal (dllmain.c:294-297), so loading force_rate.so
    alongside it is a startup-abort race."""
    assert "force_rate.so" in runtime_paths(MINQLXTENDED)["excluded_system_hooks"]
    assert "force_rate.so" not in runtime_paths(MINQLX)["excluded_system_hooks"]


def test_runtime_paths_returns_a_copy():
    """Callers must not be able to mutate the shared table."""
    paths = runtime_paths(MINQLX)
    paths["plugins_dirname"] = "tampered"
    assert runtime_paths(MINQLX)["plugins_dirname"] == "minqlx-plugins"


def test_log_patterns_do_not_cross_match():
    """'minqlxtended.log' must not satisfy the minqlx pattern, or the log
    fetcher would happily serve the wrong runtime's file."""
    minqlx_pattern = log_filename_pattern(MINQLX)
    tended_pattern = log_filename_pattern(MINQLXTENDED)

    assert re.fullmatch(minqlx_pattern, "minqlx.log")
    assert re.fullmatch(minqlx_pattern, "minqlx.log.3")
    assert re.fullmatch(minqlx_pattern, "minqlxtended.log") is None

    assert re.fullmatch(tended_pattern, "minqlxtended.log")
    assert re.fullmatch(tended_pattern, "minqlxtended.log.12")
    assert re.fullmatch(tended_pattern, "minqlx.log") is None
    assert re.fullmatch(tended_pattern, "minqlxtended.log.x") is None


def test_host_runtime_handles_none_and_missing_attribute():
    class Bare:
        pass

    assert host_runtime(None) == MINQLX
    assert host_runtime(Bare()) == MINQLX


def test_host_runtime_reads_the_column():
    class FakeHost:
        runtime = MINQLXTENDED

    assert host_runtime(FakeHost()) == MINQLXTENDED


def test_runtime_extravars_shape():
    """These four keys are what every instance-level playbook consumes."""
    class FakeHost:
        runtime = MINQLXTENDED

    assert runtime_extravars(FakeHost()) == {
        "runtime": "minqlxtended",
        "runtime_plugins_dirname": "minqlxtended-plugins",
        "runtime_shared_dir": "/home/ql/minqlxtended-shared",
        "launch_script": "run_server_x64_minqlxtended.sh",
    }


def test_runtime_extravars_defaults_for_a_legacy_host():
    class LegacyHost:
        runtime = None

    assert runtime_extravars(LegacyHost())["runtime"] == "minqlx"
