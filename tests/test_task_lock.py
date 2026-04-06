import pytest
from unittest.mock import MagicMock, patch
from ui.task_lock import acquire_lock, release_lock

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
