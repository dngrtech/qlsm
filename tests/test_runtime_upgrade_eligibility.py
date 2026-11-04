"""Eligibility rules for the minqlx -> minqlxtended host upgrade action."""
from types import SimpleNamespace

from ui import db
from ui.models import Host, HostStatus, InstanceStatus
from ui.runtime_upgrade import UPGRADE_TARGET_RUNTIME, upgrade_eligibility


def _inst(name="i1", status=InstanceStatus.RUNNING):
    return SimpleNamespace(name=name, status=status)


def _host(runtime="minqlx", status=HostStatus.ACTIVE, os_type="ubuntu",
          os_version="24.04", instances=None):
    return SimpleNamespace(runtime=runtime, status=status, os_type=os_type,
                           os_version=os_version,
                           instances=[_inst()] if instances is None else instances)


def test_target_runtime_constant():
    assert UPGRADE_TARGET_RUNTIME == "minqlxtended"


def test_minqlxtended_host_hidden():
    assert upgrade_eligibility(_host(runtime="minqlxtended")) == {
        "visible": False, "enabled": False, "reason": None}


def test_ubuntu_2404_active_all_running_enabled():
    result = upgrade_eligibility(_host(instances=[_inst("a"), _inst("b")]))
    assert result["visible"] is True
    assert result["enabled"] is True
    assert result["reason"] is None


def test_debian_12_disabled_with_reason():
    result = upgrade_eligibility(_host(os_type="debian", os_version="12"))
    assert result["visible"] and not result["enabled"]
    assert result["reason"] == (
        "minqlxtended requires Ubuntu 24.04 or newer; this host runs Debian 12")


def test_ubuntu_2204_disabled():
    assert not upgrade_eligibility(_host(os_version="22.04"))["enabled"]


def test_ubuntu_2604_enabled():
    assert upgrade_eligibility(_host(os_version="26.04"))["enabled"]


def test_unknown_os_version_disabled():
    result = upgrade_eligibility(_host(os_version=None))
    assert not result["enabled"]
    assert "OS version unknown" in result["reason"]


def test_host_not_active_disabled():
    result = upgrade_eligibility(_host(status=HostStatus.ERROR))
    assert not result["enabled"]
    assert "ACTIVE" in result["reason"]


def test_assume_status_overrides_host_status():
    host = _host(status=HostStatus.CONFIGURING)
    assert upgrade_eligibility(host, assume_status=HostStatus.ACTIVE)["enabled"]
    assert not upgrade_eligibility(host)["enabled"]


def test_instance_in_error_disabled():
    result = upgrade_eligibility(
        _host(instances=[_inst("good"), _inst("broken", InstanceStatus.ERROR)]))
    assert not result["enabled"]
    assert "broken" in result["reason"]
    assert "ERROR" in result["reason"]


def test_stopped_instance_allowed():
    assert upgrade_eligibility(
        _host(instances=[_inst("a"), _inst("b", InstanceStatus.STOPPED)]))["enabled"]


def test_host_to_dict_includes_runtime_upgrade(app):
    with app.app_context():
        host = Host(name="elig-host", ip_address="192.0.2.10", provider="vultr",
                    status=HostStatus.ACTIVE, runtime="minqlx",
                    os_type="ubuntu", os_version="24.04")
        db.session.add(host)
        db.session.commit()
        assert host.to_dict()["runtime_upgrade"] == {
            "visible": True, "enabled": True, "reason": None}
