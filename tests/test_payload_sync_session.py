"""host.payload_sync must not run inside an open write transaction."""
from unittest.mock import MagicMock, patch

from ui.task_logic import ansible_host_setup as setup


def _fake_db(is_active=True):
    fake = MagicMock()
    fake.session.is_active = is_active
    return fake


def test_pending_setup_log_is_committed_before_handlers_run():
    order = []
    fake = _fake_db()
    fake.session.commit.side_effect = lambda: order.append('commit')

    with patch.object(setup, 'db', fake), \
            patch('ui.addons.dispatch', side_effect=lambda *a, **k: order.append('dispatch')):
        setup._dispatch_addon_payload_sync(MagicMock(id=7))

    assert order == ['commit', 'dispatch']
    fake.session.rollback.assert_not_called()


def test_session_poisoned_by_a_handler_is_rolled_back():
    fake = _fake_db(is_active=False)

    with patch.object(setup, 'db', fake), patch('ui.addons.dispatch'):
        setup._dispatch_addon_payload_sync(MagicMock(id=7))

    fake.session.rollback.assert_called_once()


def test_a_failing_dispatch_does_not_fail_setup():
    fake = _fake_db()

    with patch.object(setup, 'db', fake), \
            patch('ui.addons.dispatch', side_effect=RuntimeError('boom')):
        setup._dispatch_addon_payload_sync(MagicMock(id=7))  # must not raise
