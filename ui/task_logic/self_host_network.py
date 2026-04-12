import os
import socket
import subprocess
from pathlib import Path

GAME_UDP_PORTS = [27960, 27961, 27962, 27963]
RCON_TCP_PORTS = [28888, 28889, 28890, 28891, 29999, 30000, 30001, 30002]


def _detect_gateway_from_proc_route(route_path):
    try:
        lines = route_path.read_text().splitlines()
    except OSError:
        return None

    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 4:
            continue
        destination, gateway_hex, flags_hex = fields[1], fields[2], fields[3]
        try:
            flags = int(flags_hex, 16)
        except ValueError:
            continue
        if destination == "00000000" and flags & 0x3 == 0x3:
            octets = bytes.fromhex(gateway_hex)
            return ".".join(str(part) for part in reversed(octets))
    return None


def detect_docker_host_ip(route_path="/proc/net/route"):
    gateway = _detect_gateway_from_proc_route(Path(route_path))
    if gateway:
        return gateway

    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ValueError("Could not detect host machine IP. Ensure Docker bridge networking is active.") from exc

    tokens = result.stdout.split()
    if "via" in tokens:
        idx = tokens.index("via")
        if idx + 1 < len(tokens):
            return tokens[idx + 1]

    raise ValueError("Could not detect host machine IP. Ensure Docker bridge networking is active.")


def _can_resolve_hostname(name):
    try:
        socket.getaddrinfo(name, None)
        return True
    except socket.gaierror:
        return False


def resolve_self_host_management_target():
    override = os.environ.get("QLSM_SELF_HOST_SSH_TARGET", "").strip()
    if override:
        return override
    if _can_resolve_hostname("host.docker.internal"):
        return "host.docker.internal"
    return detect_docker_host_ip()


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
