import pytest
from unittest.mock import MagicMock, call, patch
from ui.task_lock import acquire_lock, acquire_locks, release_lock, release_locks

@pytest.fixture
def mock_redis():
    """Provide a mock Redis client via the app extension."""
    mock = MagicMock()
    with patch('ui.task_lock._get_redis') as get_redis:
        get_redis.return_value = mock
        yield mock

class TestAcquireLock:
    def test_acquire_succeeds(self, mock_redis):
        mock_redis.set.return_value = True
        result = acquire_lock('host', 1, 'token-abc', ttl=300)
        assert result is True
        mock_redis.set.assert_called_once_with(
            'task_lock:host:1', 'token-abc', nx=True, ex=300
        )

    def test_acquire_fails_when_locked(self, mock_redis):
        mock_redis.set.return_value = False
        result = acquire_lock('host', 1, 'token-abc', ttl=300)
        assert result is False

    def test_acquire_uses_correct_key_format(self, mock_redis):
        mock_redis.set.return_value = True
        acquire_lock('instance', 42, 'tok', ttl=120)
        mock_redis.set.assert_called_once_with(
            'task_lock:instance:42', 'tok', nx=True, ex=120
        )

class TestReleaseLock:
    def test_release_own_lock(self, mock_redis):
        mock_redis.execute_command.return_value = 1
        result = release_lock('host', 1, 'token-abc')
        assert result is True

    def test_release_someone_elses_lock(self, mock_redis):
        mock_redis.execute_command.return_value = 0
        result = release_lock('host', 1, 'wrong-token')
        assert result is False

    def test_release_nonexistent_lock(self, mock_redis):
        mock_redis.execute_command.return_value = 0
        result = release_lock('host', 999, 'any-token')
        assert result is False


class TestAcquireLocks:
    @patch('ui.task_lock.acquire_lock', return_value=True)
    def test_deduplicates_and_acquires_ids_in_ascending_order(self, mock_acquire):
        result = acquire_locks('instance', [9, 2, 9, 4], 'batch-token', ttl=3660)

        assert result is True
        assert mock_acquire.call_args_list == [
            call('instance', 2, 'batch-token', 3660),
            call('instance', 4, 'batch-token', 3660),
            call('instance', 9, 'batch-token', 3660),
        ]

    @patch('ui.task_lock.release_lock', return_value=True)
    @patch('ui.task_lock.acquire_lock', side_effect=[True, True, False])
    def test_failed_acquisition_releases_every_owned_partial_lock(
        self, mock_acquire, mock_release
    ):
        result = acquire_locks('instance', [3, 1, 2], 'batch-token', ttl=1260)

        assert result is False
        assert mock_acquire.call_args_list == [
            call('instance', 1, 'batch-token', 1260),
            call('instance', 2, 'batch-token', 1260),
            call('instance', 3, 'batch-token', 1260),
        ]
        assert mock_release.call_args_list == [
            call('instance', 1, 'batch-token'),
            call('instance', 2, 'batch-token'),
        ]


class TestReleaseLocks:
    @patch('ui.task_lock.release_lock', side_effect=[RuntimeError('redis down'), True, True])
    def test_attempts_every_unique_id_when_one_release_raises(self, mock_release):
        release_locks('instance', [4, 2, 4, 3], 'batch-token')

        assert mock_release.call_args_list == [
            call('instance', 2, 'batch-token'),
            call('instance', 3, 'batch-token'),
            call('instance', 4, 'batch-token'),
        ]
