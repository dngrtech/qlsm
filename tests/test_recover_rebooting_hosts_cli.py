from ui import db
from ui.models import Host, HostStatus


def _make_host(name, status, logs=None):
    host = Host(name=name, provider='self', status=status, logs=logs)
    db.session.add(host)
    db.session.commit()
    return host


def test_recover_transitions_rebooting_host_to_active(runner, app):
    with app.app_context():
        _make_host('ovh-3', HostStatus.REBOOTING)

    result = runner.invoke(args=['recover-rebooting-hosts'])

    assert result.exit_code == 0
    with app.app_context():
        host = Host.query.filter_by(name='ovh-3').one()
        assert host.status == HostStatus.ACTIVE
        assert 'Recovered from interrupted reboot on startup.' in host.logs


def test_recover_appends_to_existing_logs(runner, app):
    with app.app_context():
        _make_host('ovh-3', HostStatus.REBOOTING, logs='Previous log entry.\n')

    result = runner.invoke(args=['recover-rebooting-hosts'])

    assert result.exit_code == 0
    with app.app_context():
        host = Host.query.filter_by(name='ovh-3').one()
        assert 'Recovered from interrupted reboot on startup.' in host.logs
        assert 'Previous log entry.' in host.logs
        assert host.logs.index('Previous log entry.') < host.logs.index('Recovered from interrupted reboot on startup.')


def test_recover_no_op_when_no_rebooting_hosts(runner, app):
    with app.app_context():
        _make_host('ovh-3', HostStatus.ACTIVE)

    result = runner.invoke(args=['recover-rebooting-hosts'])

    assert result.exit_code == 0
    with app.app_context():
        host = Host.query.filter_by(name='ovh-3').one()
        assert host.status == HostStatus.ACTIVE


def test_recover_only_affects_rebooting_hosts(runner, app):
    with app.app_context():
        _make_host('ovh-3', HostStatus.REBOOTING)
        _make_host('ovh-4', HostStatus.ERROR)
        _make_host('ovh-5', HostStatus.ACTIVE)

    result = runner.invoke(args=['recover-rebooting-hosts'])

    assert result.exit_code == 0
    with app.app_context():
        assert Host.query.filter_by(name='ovh-3').one().status == HostStatus.ACTIVE
        assert Host.query.filter_by(name='ovh-4').one().status == HostStatus.ERROR
        assert Host.query.filter_by(name='ovh-5').one().status == HostStatus.ACTIVE


def test_recover_host_with_null_logs(runner, app):
    with app.app_context():
        _make_host('ovh-6', HostStatus.REBOOTING, logs=None)

    result = runner.invoke(args=['recover-rebooting-hosts'])

    assert result.exit_code == 0
    with app.app_context():
        host = Host.query.filter_by(name='ovh-6').one()
        assert host.status == HostStatus.ACTIVE
        assert host.logs is not None
        assert 'Recovered from interrupted reboot on startup.' in host.logs
