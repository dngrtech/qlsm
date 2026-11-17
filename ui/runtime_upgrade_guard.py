"""The persistent host reservation a runtime upgrade holds.

A nonterminal HostRuntimeUpgradeOperation row blocks every host and instance
mutation until the operation finishes or its rollback is verified. Redis
execution locks only serialize the worker; they can expire, the reservation
cannot. Terminal rows never block anything, including a new host that reuses
an id. Read-only/status endpoints are not guarded.
"""
from flask import jsonify

from ui import db
from ui.models_runtime_upgrade import TERMINAL_STATES, HostRuntimeUpgradeOperation

BLOCKED_MESSAGE = ('Host {name} is being upgraded to minqlxtended; '
                   'changes are blocked until it finishes.')


class RuntimeUpgradeReserved(RuntimeError):
    """A mutation was attempted on a host with a nonterminal upgrade."""


def active_runtime_upgrade(host_id):
    """The host's nonterminal upgrade operation, or None."""
    if host_id is None:
        return None
    return (HostRuntimeUpgradeOperation.query
            .filter(HostRuntimeUpgradeOperation.host_id == host_id,
                    HostRuntimeUpgradeOperation.state.notin_(TERMINAL_STATES))
            .first())


def reserved_host_ids():
    """Ids of every host holding a nonterminal upgrade reservation."""
    rows = (db.session.query(HostRuntimeUpgradeOperation.host_id)
            .filter(HostRuntimeUpgradeOperation.state.notin_(TERMINAL_STATES))
            .all())
    return {row[0] for row in rows}


def blocked_message(host_name):
    return BLOCKED_MESSAGE.format(name=host_name)


def _host_name(host_id):
    from ui.models import Host

    host = db.session.get(Host, host_id)
    return host.name if host is not None else str(host_id)


def upgrade_block_response(host_id, host_name=None):
    """(response, 409) when the host is reserved by an upgrade, else None."""
    if active_runtime_upgrade(host_id) is None:
        return None
    name = host_name or _host_name(host_id)
    return jsonify({'error': {'message': blocked_message(name)}}), 409


def instance_upgrade_block_response(instance):
    """upgrade_block_response for an instance's host (None for a missing instance)."""
    if instance is None:
        return None
    host = getattr(instance, 'host', None)
    return upgrade_block_response(instance.host_id, host.name if host is not None else None)


def host_name_block_response(host_name):
    """upgrade_block_response for routes that address a host by name
    (instance config/script endpoints under configs/<host>/<id>/)."""
    from ui.models import Host

    if not host_name:
        return None
    host = Host.query.filter_by(name=host_name).first()
    if host is None:
        return None
    return upgrade_block_response(host.id, host.name)


def ensure_no_runtime_upgrade(host_id):
    """Raise RuntimeUpgradeReserved when the host is reserved (non-route callers)."""
    if active_runtime_upgrade(host_id) is not None:
        raise RuntimeUpgradeReserved(blocked_message(_host_name(host_id)))
