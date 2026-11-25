"""Confirmation capture and public release choices for Custom Standalone hosts."""
import hashlib
import json
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ui.custom_runtime import RuntimeUnavailable, approved_release, pinned_release, release_for_host
from ui.models import HostStatus, InstanceStatus
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.runtime_upgrade_guard import active_runtime_upgrade
from ui.task_logic.ansible_instance_mgmt import _build_ld_preload_paths, _build_qlds_args_string

_UNIT_TEMPLATES = Path(__file__).resolve().parents[1] / 'ansible' / 'templates'
_UNIT_ENV = Environment(loader=FileSystemLoader(_UNIT_TEMPLATES), undefined=StrictUndefined,
                        trim_blocks=True, keep_trailing_newline=True)


class _ReleaseView:
    """Let the normal renderer see a prospective pin without dirtying any ORM rows."""

    def __init__(self, source, **overrides):
        self._source = source
        self.__dict__.update(overrides)

    def __getattr__(self, name):
        return getattr(self._source, name)


def _unit(instance, release):
    host = _ReleaseView(instance.host, runtime_release_sha256=release.sha256)
    view = _ReleaseView(instance, host=host)
    return _UNIT_ENV.get_template('qlds@.service.j2').render(
        runtime_launch_path=f"{release.installed_path}/{release.metadata['launch_script']}",
        qlds_args=_build_qlds_args_string(view), ld_preload_paths=_build_ld_preload_paths(view),
        cpu_affinity=instance.cpu_affinity)


def fingerprint(inputs):
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _created(row):
    return row.created_at.isoformat() if row.created_at else None


def _summary(release):
    return {'provider_id': release.provider_id, 'label': release.label, 'build': release.version,
            'sha256': release.sha256, 'plugin_api': release.metadata['plugin_api'],
            'platform': release.metadata['platform']}


def _compatible(current, candidate):
    return (candidate.sha256 != current.sha256 and candidate.provider_id == current.provider_id
            and candidate.metadata['plugin_api'] == current.metadata['plugin_api']
            and candidate.metadata['platform'] == current.metadata['platform'])


def _previous(host, current):
    operation = (HostRuntimeUpgradeOperation.query.filter_by(
        host_id=host.id, state='succeeded', original_runtime='custom')
        .order_by(HostRuntimeUpgradeOperation.created_at.desc(), HostRuntimeUpgradeOperation.id.desc()).first())
    if operation is None or not host.created_at:
        return None
    capture = json.loads(operation.inputs_json)
    if (capture['host_created_at'] != _created(host)
            or capture['current']['provider_id'] != current.provider_id
            or json.loads(operation.answers_json)['target_sha256'] != current.sha256):
        return None
    try:
        candidate = pinned_release(current.provider_id, capture['current']['sha256'])
    except RuntimeUnavailable:
        return None
    return candidate if _compatible(current, candidate) else None


def ssh_endpoint(host):
    return {'address': host.ip_address, 'ssh_port': host.ssh_port, 'ssh_user': host.ssh_user,
            'ssh_key_path': os.path.abspath(host.ssh_key_path) if host.ssh_key_path else None}


def capture_inputs(host, current, choices):
    """Private. Render every offered unit from the existing instance settings."""
    rows = []
    for instance in sorted(host.instances, key=lambda inst: inst.id):
        rows.append({'instance_id': instance.id, 'name': instance.name, 'port': instance.port,
                     'created_at': _created(instance), 'status': instance.status.value,
                     'units': {release.sha256: _unit(instance, release) for release in choices.values()
                               if release is not None}})
    return {'host_id': host.id, 'host_created_at': _created(host), 'host_name': host.name,
            **ssh_endpoint(host), 'current': _summary(current),
            'choices': {action: _summary(release) if release else None for action, release in choices.items()},
            'instances': rows}


def preview(host):
    """Return the public dialog data and the separate, server-side capture."""
    instances = sorted(host.instances, key=lambda inst: inst.id)
    result = {'eligibility': {'enabled': False, 'reason': None},
              'current': None, 'target': None, 'rollback': None, 'fingerprint': None, 'reason': None,
              'instances': [{'id': i.id, 'name': i.name, 'status': getattr(i.status, 'value', None)} for i in instances]}
    try:
        if host.runtime != 'custom' or host.provider != 'standalone':
            raise RuntimeUnavailable('Only Standalone Custom hosts can update a Custom release.')
        current = release_for_host(host)
        result['current'] = _summary(current)
        if host.status != HostStatus.ACTIVE or active_runtime_upgrade(host.id):
            raise RuntimeUnavailable('The host must be ACTIVE and available for runtime maintenance.')
        if any(i.status not in (InstanceStatus.RUNNING, InstanceStatus.STOPPED) for i in instances):
            raise RuntimeUnavailable('All instances must be RUNNING or STOPPED.')
        try:
            approved = approved_release(current.provider_id)
            target = approved if _compatible(current, approved) else None
            if target is None:
                result['reason'] = ('The approved release is already installed.' if current.sha256 == approved.sha256
                                    else 'The approved release uses a different plugin API or platform.')
        except RuntimeUnavailable as exc:
            target = None
            result['reason'] = str(exc)
        rollback = _previous(host, current)
        inputs = capture_inputs(host, current, {'update': target, 'rollback': rollback})
    except RuntimeUnavailable as exc:
        result['eligibility']['reason'] = str(exc)
        return result, None
    except (ValueError, TypeError, KeyError):
        # The field validator's errors can include ZMQ passwords.
        result['eligibility']['reason'] = 'Could not validate the Custom release history or instance settings.'
        return result, None

    result.update(eligibility={'enabled': True, 'reason': None}, target=inputs['choices']['update'],
                  rollback=inputs['choices']['rollback'], fingerprint=fingerprint(inputs))
    return result, inputs
