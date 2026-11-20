"""Run one operation-fenced Custom update step. Keep unit secrets out of Ansible arguments."""
import json
from contextlib import ExitStack
from tempfile import NamedTemporaryFile
from types import SimpleNamespace

from .ansible_runner import _run_host_ansible_playbook
from .instance_runtime_update import _check_identity, _terminal_operation_ids


def run_step(host, action, *, operation_id, fencing_token, endpoint, instance=None, unit=None,
             release=None, original=None, allow_unrecorded=False):
    _check_identity(operation_id, fencing_token)
    extra = {'custom_action': action, 'operation_id': operation_id, 'fencing_token': fencing_token,
             'terminal_operation_ids': _terminal_operation_ids(host.id), 'allow_unrecorded': allow_unrecorded}
    if instance is not None:
        extra.update(instance_id=instance.id, port=instance.port)
    if release is not None:
        extra.update(custom_bundle_path=str(release.bundle_path.resolve()), custom_release_digest=release.sha256,
                     custom_original_digest=original.sha256, custom_platform=release.metadata['platform'],
                     runtime_shared_dir=release.installed_path, custom_launch_script=release.metadata['launch_script'],
                     custom_requirements_file=release.metadata['requirements_file'],
                     custom_dependency_imports=release.metadata.get('dependency_imports', []))
    # Host names can be inventory patterns (including "all") and the shared
    # inventory can lag the DB. Every step addresses only this confirmed endpoint.
    target = SimpleNamespace(id=host.id, name='qlsm_custom_target', ip_address=endpoint['address'],
                             ssh_user=endpoint['ssh_user'], ssh_key_path=endpoint['ssh_key_path'])
    variables = {'ansible_connection': 'ssh', 'ansible_host': target.ip_address,
                 'ansible_port': endpoint['ssh_port'], 'ansible_user': target.ssh_user,
                 'ansible_ssh_private_key_file': target.ssh_key_path}
    with ExitStack() as files:
        inventory = files.enter_context(NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.yml'))
        json.dump({'all': {'hosts': {target.name: variables}}}, inventory)
        inventory.flush()
        if unit is not None:
            source = files.enter_context(NamedTemporaryFile(mode='w', encoding='utf-8', prefix='qlsm-unit-'))
            source.write(unit)
            source.flush()
            extra['unit_src'] = source.name
        result = _run_host_ansible_playbook(target, 'custom_runtime_operation.yml', extravars=extra,
                                            capture_output=True, inventory_path=inventory.name)
    # Ansible exits zero for an empty inventory match. Require evidence that
    # this particular host reached the last task as well as a successful exit.
    if len(result) != 3 or not result[0] or 'QLSM_CUSTOM_STEP_VERIFIED' not in result[1]:
        return False
    if action == 'receipt':
        for state in ('open', 'closed', 'unrecorded'):
            if 'QLSM_CUSTOM_RECEIPT_' + state in result[1]:
                return state
        return False
    return True
