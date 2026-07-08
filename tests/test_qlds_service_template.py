from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def _render_service(**kwargs):
    template_dir = Path("ansible/templates").resolve()
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("qlds@.service.j2")
    return template.render(**kwargs)


def test_qlds_service_omits_cpu_affinity_when_unset():
    rendered = _render_service(qlds_args="+set net_port 27960")

    assert "CPUAffinity=" not in rendered


def test_qlds_service_renders_cpu_affinity_when_set():
    rendered = _render_service(qlds_args="+set net_port 27960", cpu_affinity=1)

    assert "CPUAffinity=1" in rendered


def test_qlds_service_uses_fast_intentional_hard_kill_restart_policy():
    rendered = _render_service(qlds_args="+set net_port 27960")

    assert "KillSignal=SIGKILL" in rendered
    assert "SuccessExitStatus=SIGKILL" not in rendered
    assert "TimeoutStopSec=2" in rendered
    assert "TimeoutStopSec=10" not in rendered
