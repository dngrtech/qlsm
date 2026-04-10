from types import SimpleNamespace

from ui.task_logic.self_host_network import (
    build_self_host_network_rules,
    with_self_host_network_extravars,
)


def _instance(instance_id, port, lan):
    return SimpleNamespace(id=instance_id, port=port, lan_rate_enabled=lan)


def _host(provider='self'):
    return SimpleNamespace(
        provider=provider,
        instances=[
            _instance(1, 27960, True),
            _instance(2, 27961, False),
            _instance(3, 27962, True),
        ],
    )


def test_build_network_rules_includes_enabled_lan_ports():
    rules = build_self_host_network_rules(_host())

    assert rules['filter']['udp_accept'] == [27960, 27961, 27962, 27963]
    assert rules['filter']['tcp_accept'] == [28888, 28889, 28890, 28891, 29999, 30000, 30001, 30002]
    assert rules['lan_rate']['udp_ports'] == [27960, 27962]


def test_build_network_rules_excludes_deleted_instance():
    rules = build_self_host_network_rules(_host(), exclude_instance_id=1)

    assert rules['lan_rate']['udp_ports'] == [27962]


def test_with_self_host_network_extravars_adds_helper_mode():
    host = _host('self')
    inst = host.instances[0]
    inst.host = host

    extravars = with_self_host_network_extravars(inst, {'port': 27960})

    assert extravars['firewall_mode'] == 'helper'
    assert extravars['qlsm_network_rules']['lan_rate']['udp_ports'] == [27960, 27962]


def test_with_self_host_network_extravars_leaves_remote_default_full():
    host = _host('standalone')
    inst = host.instances[0]
    inst.host = host

    extravars = with_self_host_network_extravars(inst, {'port': 27960})

    assert extravars == {'port': 27960, 'firewall_mode': 'full'}
