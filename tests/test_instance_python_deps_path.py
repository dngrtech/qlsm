"""QLInstance.python_deps_path: an upgraded instance's isolated dependency
venv. When set, every service render passes QLSM_PYTHON_DEPS and per-instance
pip goes through the venv's interpreter. When NULL, nothing changes at all."""
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

from ui import db
from ui.models import Host, InstanceStatus, QLInstance
from ui.runtime import MINQLXTENDED, instance_runtime_extravars, runtime_extravars
from ui.task_logic import ansible_instance_mgmt as mod

VENV = "/home/ql/runtime-deps/minqlxtended/" + "a" * 32 + "/7"


def _render(template_text, **kwargs):
    # Ansible's template module renders with trim_blocks=True.
    env = Environment(trim_blocks=True)
    return env.from_string(template_text).render(**kwargs)


# qlds@.service.j2 exactly as it was before python_deps_path existed (630a82a8),
# inlined so the comparison works in a shallow or squashed checkout.
PRE_DEPS_PATH_TEMPLATE = "[Unit]\nDescription=Quake Live Dedicated Server Port %i\nAfter=network.target\n\n[Service]\nUser=ql\nGroup=ql\nWorkingDirectory=/home/ql/qlds-%i\n{% if cpu_affinity is defined and cpu_affinity is not none %}\nCPUAffinity={{ cpu_affinity }}\n{% endif %}\n{% if ld_preload_paths | default('') %}\nEnvironment=LD_PRELOAD={{ ld_preload_paths }}\n{% endif %}\n# The ExecStart line will include the script and the dynamic arguments passed from Ansible\n# Wrap the entire command in quotes to handle spaces/quotes in qlds_args\nExecStart=/home/ql/qlds-%i/{{ launch_script | default('run_server_x64_minqlx.sh') }} {{ qlds_args | default('') }} \nRestart=on-failure\nRestartSec=5\n# qzeroded/minqlx does not exit cleanly on SIGTERM. Treat fast hard-kill\n# restarts as intentional for QLDS config/hook applies instead of burning a\n# 10s stop timeout. Do not mark SIGKILL as a clean exit globally: external\n# kill -9/OOM exits should still be failures under Restart=on-failure.\nKillSignal=SIGKILL\nTimeoutStopSec=2\n\n# Standard output and error logging (optional, defaults to journald)\nStandardOutput=journal\nStandardError=journal\n\n[Install]\nWantedBy=multi-user.target\n"


SERVICE_INPUTS = [
    dict(qlds_args="+set net_port 27960"),
    dict(qlds_args="+set net_port 27961", cpu_affinity=2, ld_preload_paths="/a.so:/b.so",
         launch_script="run_server_x64_minqlxtended.sh"),
]


@pytest.mark.parametrize("inputs", SERVICE_INPUTS)
def test_service_unit_is_byte_identical_without_a_deps_path(inputs):
    before = PRE_DEPS_PATH_TEMPLATE
    after = Path("ansible/templates/qlds@.service.j2").read_text()
    assert _render(after, **inputs) == _render(before, **inputs)
    assert _render(after, python_deps_path="", **inputs) == _render(before, **inputs)


def test_service_unit_exports_the_deps_path_when_set():
    text = Path("ansible/templates/qlds@.service.j2").read_text()
    rendered = _render(text, python_deps_path=VENV, qlds_args="+set net_port 27960")
    assert f"Environment=QLSM_PYTHON_DEPS={VENV}\n" in rendered
    assert rendered.index("QLSM_PYTHON_DEPS") < rendered.index("ExecStart=")


@pytest.fixture
def instance(app, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "CONFIGS_BASE", str(tmp_path / "configs"), raising=False)
    with app.app_context():
        host = Host(name="deps-host", provider="vultr", ip_address="10.0.0.1", runtime=MINQLXTENDED)
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(name="di", port=27960, hostname="hn", host_id=host.id, qlx_plugins="",
                          status=InstanceStatus.RUNNING, zmq_rcon_port=28888, zmq_rcon_password="x",
                          zmq_stats_port=29999, zmq_stats_password="y")
        db.session.add(inst)
        db.session.commit()
        yield inst


def test_column_defaults_to_null(app, instance):
    with app.app_context():
        assert db.session.get(QLInstance, instance.id).python_deps_path is None


def test_instance_extravars_equal_host_extravars_when_null(app, instance):
    with app.app_context():
        inst = db.session.get(QLInstance, instance.id)
        assert instance_runtime_extravars(inst) == runtime_extravars(inst.host)
        assert "python_deps_path" not in instance_runtime_extravars(inst)


def test_instance_extravars_add_the_deps_path_when_set(app, instance):
    with app.app_context():
        inst = db.session.get(QLInstance, instance.id)
        inst.python_deps_path = VENV
        assert instance_runtime_extravars(inst) == {**runtime_extravars(inst.host),
                                                    "python_deps_path": VENV}


def _capture_logic(monkeypatch, module):
    captured = {}

    def fake_run(instance, playbook, extravars=None):
        captured["extravars"] = extravars
        return SimpleNamespace(rc=0, status="successful", stdout=lambda: ""), None

    monkeypatch.setattr(module, "_run_ansible_playbook", fake_run)
    for name in ("_prepare_instance_zmq", "ensure_instance_cpu_affinity"):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, lambda inst: None)
    if hasattr(module, "with_self_host_network_extravars"):
        monkeypatch.setattr(module, "with_self_host_network_extravars", lambda inst, e: e)
    if hasattr(module, "get_current_job"):
        monkeypatch.setattr(module, "get_current_job", lambda: SimpleNamespace(id="job"))
    return captured


def _call_sites():
    from ui.task_logic import ansible_instance_hooks, instance_reconciliation
    return [
        (mod, lambda i: mod.restart_instance_logic(i)),
        (mod, lambda i: mod.apply_instance_config_logic(i)),
        (mod, lambda i: mod.reconfigure_instance_lan_rate_logic(i)),
        (ansible_instance_hooks, lambda i: ansible_instance_hooks.apply_instance_hooks_logic(i)),
        (instance_reconciliation, lambda i: instance_reconciliation.reconcile_instance_after_host_setup(
            i, restart_service=True, target_status=InstanceStatus.RUNNING)),
    ]


@pytest.mark.parametrize("index", range(5))
@pytest.mark.parametrize("deps", [None, VENV])
def test_every_service_rendering_call_site_honours_the_deps_path(app, instance, monkeypatch, index, deps):
    module, call = _call_sites()[index]
    captured = _capture_logic(monkeypatch, module)
    with app.app_context():
        inst = db.session.get(QLInstance, instance.id)
        inst.python_deps_path = deps
        db.session.commit()
        try:
            call(inst.id)
        except Exception:
            pass
    assert captured.get("extravars"), "never reached the playbook call"
    if deps is None:
        assert "python_deps_path" not in captured["extravars"]
    else:
        assert captured["extravars"]["python_deps_path"] == VENV


@pytest.mark.parametrize("playbook", [
    "ansible/playbooks/add_qlds_instance.yml",
    "ansible/playbooks/sync_instance_configs_and_restart.yml",
    "ansible/playbooks/update_instance_lan_rate.yml",
    "ansible/playbooks/update_instance_hooks.yml",
    "ansible/playbooks/update_instance_runtime.yml",
])
def test_service_rendering_playbooks_default_the_deps_path_to_empty(playbook):
    with open(playbook) as handle:
        play = yaml.safe_load(handle)[0]
    assert play["vars"]["python_deps_path"] == ""


def _deps_tasks():
    with open("ansible/playbooks/tasks/install_minqlx_deps.yml") as handle:
        return yaml.safe_load(handle)


def test_deps_install_routes_pip_through_the_venv_when_set():
    tasks = _deps_tasks()
    venv = [t for t in tasks if "python_deps_path" in str(t.get("when", ""))
            and "length > 0" in str(t.get("when", ""))]
    assert venv, "no venv branch"
    text = " ".join(str(t.get("ansible.builtin.shell", "")) for t in venv) + yaml.safe_dump(venv)
    assert "(python_deps_path ~ '/bin/python') | quote }} -m pip install" in text
    assert "pip check" in text
    assert "break-system-packages" not in text
    assert "pip3" not in text


def test_deps_install_global_branch_only_runs_without_a_deps_path():
    tasks = _deps_tasks()
    for task in tasks:
        if task.get("ansible.builtin.pip") or "pip3" in str(task.get("command", "")):
            assert "python_deps_path | default('') | length == 0" in str(task.get("when", "")), task["name"]


def test_migration_adds_and_removes_the_column(tmp_path):
    """Applies only this migration on top of its parent revision."""
    import os
    import sqlite3

    from flask_migrate import downgrade, stamp, upgrade

    from ui import create_app

    db_path = tmp_path / 'migrated.db'
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
                      'SQLALCHEMY_TRACK_MODIFICATIONS': False, 'RCON_ENABLED': False})
    migrations = os.path.join(os.path.dirname(__file__), '..', 'migrations')

    def columns():
        conn = sqlite3.connect(db_path)
        try:
            return {row[1] for row in conn.execute('PRAGMA table_info(ql_instance)')}
        finally:
            conn.close()

    try:
        with app.app_context():
            db.create_all()
            db.session.execute(db.text('ALTER TABLE ql_instance DROP COLUMN python_deps_path'))
            db.session.commit()
            assert 'python_deps_path' not in columns()
            stamp(directory=migrations, revision='20261104120000')
            upgrade(directory=migrations, revision='20261104130000')
            assert 'python_deps_path' in columns()
            downgrade(directory=migrations, revision='20261104120000')
            assert 'python_deps_path' not in columns()
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
