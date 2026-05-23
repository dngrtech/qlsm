import os

from jinja2 import Environment, FileSystemLoader


TEMPLATES = os.path.join(os.path.dirname(__file__), "..", "ansible", "templates")


def _render(vars_dict):
    env = Environment(loader=FileSystemLoader(TEMPLATES), keep_trailing_newline=True)
    return env.get_template("qlds@.service.j2").render(**vars_dict)


def test_no_env_line_when_ld_preload_empty():
    out = _render({"qlds_args": "+set foo bar", "ld_preload_paths": ""})
    assert "Environment=LD_PRELOAD" not in out


def test_no_env_line_when_ld_preload_missing():
    out = _render({"qlds_args": "+set foo bar"})
    assert "Environment=LD_PRELOAD" not in out


def test_env_line_present_when_ld_preload_set():
    out = _render({"qlds_args": "+set foo bar", "ld_preload_paths": "/a.so:/b.so"})
    assert "Environment=LD_PRELOAD=/a.so:/b.so" in out
