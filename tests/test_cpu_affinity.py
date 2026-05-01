from unittest.mock import patch
from types import SimpleNamespace

from ui import db
from ui.database import create_host, create_instance
from ui.models import HostStatus
from ui.task_logic.cpu_affinity import (
    _detect_cpu_count_with_ansible,
    ensure_instance_cpu_affinity,
    resolve_host_cpu_count,
)


def test_resolve_vultr_cpu_count_from_plan(app_context):
    host = create_host(
        name='vultr-cpu-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )

    assert resolve_host_cpu_count(host) == 2
    assert host.cpu_count == 2


def test_resolve_vultr_cpu_count_refreshes_stale_saved_value(app_context):
    host = create_host(
        name='stale-vultr-cpu-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
        cpu_count=1,
    )

    assert resolve_host_cpu_count(host) == 2
    assert host.cpu_count == 2


def test_detect_cpu_count_with_ansible_parses_nproc_output(app_context):
    host = create_host(
        name='standalone-cpu-host',
        provider='standalone',
        region=None,
        machine_size=None,
        status=HostStatus.ACTIVE,
    )

    with patch('ui.task_logic.cpu_affinity.subprocess.run') as mock_run:
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout='standalone-cpu-host | CHANGED | rc=0 >>\n4\n',
            stderr='',
        )

        assert _detect_cpu_count_with_ansible(host) == 4

    cmd = mock_run.call_args.args[0]
    assert cmd[-3:] == ['command', '-a', 'nproc']


def test_unknown_cpu_count_leaves_affinity_unset(app_context):
    host = create_host(
        name='unknown-cpu-host',
        provider='vultr',
        region='ewr',
        machine_size='unknown-plan',
        status=HostStatus.ACTIVE,
    )
    inst = create_instance('unknown-cpu-inst', host.id, 27960, 'Unknown CPU')

    with patch('ui.task_logic.cpu_affinity._detect_cpu_count_with_ansible', return_value=None):
        assert ensure_instance_cpu_affinity(inst) is None

    assert inst.cpu_affinity is None


def test_one_cpu_host_leaves_affinity_unset(app_context):
    host = create_host(
        name='one-cpu-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-1c-1gb',
        status=HostStatus.ACTIVE,
    )
    inst = create_instance('one-cpu-inst', host.id, 27960, 'One CPU')

    assert ensure_instance_cpu_affinity(inst) is None
    assert inst.cpu_affinity is None


def test_skipped_ports_still_spread_by_existing_instances(app_context):
    host = create_host(
        name='skip-port-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )
    first = create_instance('inst-27960', host.id, 27960, 'First')
    second = create_instance('inst-27962', host.id, 27962, 'Second')

    assert ensure_instance_cpu_affinity(first) == 0
    db.session.commit()
    assert ensure_instance_cpu_affinity(second) == 1


def test_existing_valid_affinity_is_stable(app_context):
    host = create_host(
        name='stable-affinity-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )
    inst = create_instance('stable-inst', host.id, 27960, 'Stable')
    inst.cpu_affinity = 1
    db.session.commit()

    assert ensure_instance_cpu_affinity(inst) == 1
    assert inst.cpu_affinity == 1


def test_zero_cpu_affinity_is_stable(app_context):
    host = create_host(
        name='zero-stable-affinity-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )
    inst = create_instance('zero-stable-inst', host.id, 27960, 'Stable Zero')
    inst.cpu_affinity = 0
    db.session.commit()

    assert ensure_instance_cpu_affinity(inst) == 0
    assert inst.cpu_affinity == 0


def test_out_of_range_affinity_is_repaired(app_context):
    host = create_host(
        name='repair-affinity-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )
    inst = create_instance('repair-inst', host.id, 27960, 'Repair')
    inst.cpu_affinity = 9
    db.session.commit()

    assert ensure_instance_cpu_affinity(inst) == 0
    assert inst.cpu_affinity == 0
