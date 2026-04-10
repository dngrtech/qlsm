GAME_UDP_PORTS = [27960, 27961, 27962, 27963]
RCON_TCP_PORTS = [28888, 28889, 28890, 28891, 29999, 30000, 30001, 30002]


def is_self_host(host):
    return bool(host and host.provider == "self")


def build_self_host_network_rules(host, exclude_instance_id=None):
    lan_ports = []
    for instance in getattr(host, "instances", []) or []:
        if exclude_instance_id is not None and instance.id == exclude_instance_id:
            continue
        if getattr(instance, "lan_rate_enabled", False):
            lan_ports.append(int(instance.port))

    return {
        "filter": {
            "udp_accept": GAME_UDP_PORTS,
            "tcp_accept": RCON_TCP_PORTS,
        },
        "lan_rate": {
            "udp_ports": sorted(set(lan_ports)),
        },
    }


def with_self_host_network_extravars(instance, extravars, exclude_instance_id=None):
    host = getattr(instance, "host", None)
    merged = dict(extravars)
    if not is_self_host(host):
        merged.setdefault("firewall_mode", "full")
        return merged

    merged["firewall_mode"] = "helper"
    merged["qlsm_network_rules"] = build_self_host_network_rules(
        host,
        exclude_instance_id=exclude_instance_id,
    )
    return merged
