"""The minqlxtended build lives in one task file shared by host setup, the
runtime rebuild and the upgrade installer, so all three install the same
patched engine."""
import ast
import os
import re
import subprocess
import sys

import pytest
import yaml

BUILD_TASKS = "ansible/playbooks/tasks/build_minqlxtended.yml"
PATCH = "ql-assets/patches/minqlxtended/qlsm-python-deps.patch"


def _load(path):
    with open(path) as handle:
        return yaml.safe_load(handle)


def _imports(path, target):
    return [t for t in _load(path)[0]["tasks"]
            if t.get("ansible.builtin.import_tasks") == target]


def test_build_tasks_clone_the_pinned_minqlxtended_and_apply_the_qlsm_patch():
    tasks = _load(BUILD_TASKS)
    text = yaml.safe_dump(tasks)
    assert len([t for t in tasks if "ansible.builtin.git" in t]) == 1
    assert "{{ minqlxtended_git_repo }}" in text
    assert "{{ minqlxtended_git_version }}" in text
    assert "patches/minqlxtended/" in text
    assert "--forward" in text
    for name in ("minqlxtended.x64.so", "minqlxtended.zip", "run_server_x64_minqlxtended.sh"):
        assert name in text


def test_build_tasks_never_touch_the_minqlx_shared_dir():
    text = open(BUILD_TASKS).read()
    assert "minqlx_shared_dir" not in text
    assert "/home/ql/minqlx-shared" not in text


@pytest.mark.parametrize("playbook", [
    "ansible/playbooks/setup_host.yml",
    "ansible/playbooks/rebuild_minqlx.yml",
])
def test_setup_and_rebuild_import_the_build_only_for_minqlxtended(playbook):
    imports = _imports(playbook, "tasks/build_minqlxtended.yml")
    assert len(imports) == 1
    assert imports[0]["when"] == "runtime == 'minqlxtended'"
    # No second, unpatched inline build left behind.
    inline = [t for t in _load(playbook)[0]["tasks"]
              if "minqlxtended" in t.get("name", "").lower() and "git" in t]
    assert inline == []


def test_minqlx_patch_loop_cannot_pick_up_the_minqlxtended_patch():
    """The minqlx loop globs /tmp/minqlx-patches/*.patch non-recursively; the
    minqlxtended patch lives one directory down."""
    assert os.path.isfile(PATCH)
    assert os.path.dirname(PATCH) != "ql-assets/patches"
    for playbook in ("ansible/playbooks/setup_host.yml", "ansible/playbooks/rebuild_minqlx.yml"):
        text = open(playbook).read()
        assert "/tmp/minqlx-patches/*.patch" in text
        assert "/tmp/minqlx-patches/**" not in text


def test_patch_only_edits_the_embedded_loader():
    text = open(PATCH).read()
    files = re.findall(r"^\+\+\+ b/(\S+)", text, re.M)
    assert files == ["src/python/python_embed.c"]
    added = [line for line in text.splitlines() if line.startswith("+") and not line.startswith("+++")]
    removed = [line for line in text.splitlines() if line.startswith("-") and not line.startswith("---")]
    assert removed == []
    assert all(line.lstrip("+").lstrip().startswith('"') for line in added)


def _patched_loader_source():
    """The Python the patch adds, decoded from its C string literals."""
    body = []
    for line in open(PATCH).read().splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            literal = line[1:].strip()
            body.append(ast.literal_eval(literal))  # C and Python agree on \n, \\ and \"
    return "".join(body)


def _run_loader(tmp_path, env_value, venv=None):
    """Run the patched loader fragment under this interpreter."""
    code = "import sys\n" + "\n".join(
        line[2:] for line in _patched_loader_source().splitlines()) + "\n"
    env = {k: v for k, v in os.environ.items() if k != "QLSM_PYTHON_DEPS"}
    if env_value is not None:
        env["QLSM_PYTHON_DEPS"] = env_value
    probe = code + "print('PATH=' + repr(sys.path))\n"
    return subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True)


def test_patched_loader_is_a_no_op_without_the_env_var(tmp_path):
    result = _run_loader(tmp_path, None)
    assert result.returncode == 0, result.stderr
    assert "QLSM_PYTHON_DEPS" not in result.stdout
    baseline = subprocess.run([sys.executable, "-c", "import sys; print('PATH=' + repr(sys.path))"],
                              env={k: v for k, v in os.environ.items() if k != "QLSM_PYTHON_DEPS"},
                              capture_output=True, text=True)
    assert result.stdout.strip().splitlines()[-1] == baseline.stdout.strip()


@pytest.mark.parametrize("value", ["relative/venv", "/tmp/not-runtime-deps", "/home/ql/runtime-deps/../evil"])
def test_patched_loader_refuses_paths_outside_runtime_deps(tmp_path, value):
    result = _run_loader(tmp_path, value)
    assert result.returncode == 0, result.stderr
    assert "QLSM_PYTHON_DEPS refused" in result.stdout


def test_patches_are_staged_privately_and_applied_by_explicit_name():
    """No shared, predictable /tmp path and no glob: another local user must
    not be able to plant a patch the ql build applies."""
    tasks = _load(BUILD_TASKS)
    raw = open(BUILD_TASKS).read()
    assert "/tmp/minqlxtended-patches" not in raw
    assert "*.patch" not in raw.split("\n- name:", 1)[1]
    stage = next(t for t in tasks if "ansible.builtin.tempfile" in t)
    assert stage["ansible.builtin.tempfile"]["state"] == "directory"
    restrict = next(t for t in tasks if t["name"] == "Restrict the patch staging directory to the ql user")
    assert restrict["ansible.builtin.file"]["mode"] == "0700"
    assert restrict["ansible.builtin.file"]["owner"] == "ql"
    apply = next(t for t in tasks if t["name"] == "Apply local minqlxtended patches")
    assert "ansible.builtin.command" in apply and "shell" not in apply
    assert "qlsm-python-deps.patch" in apply["loop"]
    assert "qlsm-demo-capture.patch" in apply["loop"]
    assert apply["loop"].index("qlsm-demo-capture.patch") < apply["loop"].index("qlsm-player-info-null-guard.patch")
    for name in ("qlsm-python-deps.patch", "qlsm-demo-capture.patch", "qlsm-player-info-null-guard.patch"):
        assert os.path.isfile(os.path.join("ql-assets/patches/minqlxtended", name))
