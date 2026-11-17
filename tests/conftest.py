import sys
import pytest
import redis as redis_lib
from redis import exceptions as redis_exceptions
from werkzeug.security import generate_password_hash
import ui.models
from ui import create_app, db

@pytest.fixture
def app(tmp_path):
    """Create and configure a Flask app for testing.

    The database is in-memory, not a temp file. Each test still gets its own,
    because each `app` gets its own engine and an in-memory SQLite database
    lives and dies with the connection behind it. Worth ~46s across the suite
    over `tempfile.mkstemp()` -- a file-backed database means creating the
    file, a WAL and an SHM sidecar per test, then unlinking all three, and on
    Windows that unlink sometimes loses to SQLite still holding the handle.

    The one thing it cannot do is be read from a second connection: a thread
    that opens its own would find an empty database rather than this one's
    tables. No test does that today; if one ever needs to, give that test a
    file-backed URI of its own rather than moving the whole suite back.
    """
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key', # Added for session/flash support in tests
        'JWT_SECRET_KEY': 'test-jwt-secret-key',  # Required for JWT token generation in tests
        'JWT_COOKIE_CSRF_PROTECT': False,  # Disable CSRF cookie protection in tests
        'JWT_TOKEN_LOCATION': ['headers', 'cookies'],  # Accept tokens from both locations
        'JWT_EXPIRATION_HOURS': 24,  # Matches ui.config.Config default
        'JWT_REMEMBER_ME_DAYS': 90,  # Matches ui.config.Config default
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'WTF_CSRF_ENABLED': False,  # Disable CSRF protection in tests
        'SERVER_NAME': 'test.server', # Added to allow url_for outside request context
        'RCON_ENABLED': False,  # Avoid background Redis listener threads in tests
        'DRAFTS_BASE': str(tmp_path / 'qlds-drafts'),  # Isolated per-test drafts dir
    })
    
    # Create the database and load test data
    with app.app_context():
        db.create_all()
    
    yield app

    with app.app_context():
        db.session.remove()
        db.engine.dispose()

@pytest.fixture
def app_with_builtin_presets(app):
    """`app`, plus the builtin preset rows `flask sync-builtin-presets` creates.

    The plain `app` fixture stops at db.create_all(), so ConfigPreset is empty
    and get_preset_by_name('default') answers None for every test in the repo.
    resolve_preset_subdir() then resolves the builtin defaults to
    configs/presets/<name>/scripts -- a path that does not exist, because
    builtins live under configs/presets/_builtin/. The consequence is that
    _seed_draft()'s "copy the runtime-matched default preset in first, then
    overlay the source" branch is DEAD under `app`, while production always
    takes it. Every draft test therefore exercises "copy source, filter it",
    and production exercises "copy target default, overlay source, filter
    both" -- a different file set, which is where the over-strip of the
    target's own shipped plugins lived unseen.

    Deliberately a separate fixture rather than a change to `app`: ~1500 tests
    depend on `app` starting from an empty database, and several assert on
    preset rows they create themselves.
    """
    from ui.builtin_presets import sync_builtin_presets
    with app.app_context():
        sync_builtin_presets()
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """A test CLI runner for the app."""
    return app.test_cli_runner()

@pytest.fixture
def app_context(app):
    """An application context for the app."""
    with app.app_context() as ctx:
        yield ctx


class _OfflineRedis:
    """Stands in for the shared Redis client create_app() installs.

    Every command raises ConnectionError, which is exactly what the real client
    does when no Redis is listening -- the blocklist check fails open, logout's
    setex is swallowed, the lockout counter never trips. What it does not do is
    spend two seconds per socket finding that out: on Windows a refused connect
    to localhost costs a flat 2.0s, redis-py tries twice, and every
    JWT-authenticated request in the suite runs one blocklist GET. That is
    ~1460 commands x ~4s -- about an hour and a half of the suite's wall clock,
    against roughly three minutes of actual work.

    Tests that want blocklist/lockout behaviour keep overriding
    app.extensions['redis'] with their own mock, as they already do.
    """

    def __getattr__(self, name):
        def _refused(*args, **kwargs):
            raise redis_exceptions.ConnectionError(
                'Error 10061 connecting to localhost:6379. '
                '(tests: no Redis, see _OfflineRedis in tests/conftest.py)')
        return _refused


@pytest.fixture(autouse=True)
def _offline_redis(monkeypatch):
    """Keep create_app() from handing out a client that dials a real Redis."""
    monkeypatch.setattr(redis_lib, 'from_url', lambda *a, **kw: _OfflineRedis())
    yield


@pytest.fixture(autouse=True)
def default_watchdog_deploy(monkeypatch):
    """First-time host setup turns ql-watchdog on, which runs a real playbook.

    No test may shell out to ansible for it. Setup modules import the function
    at call time, so replacing it on its home module covers every caller; tests
    of the function itself hold their own reference to the real one.
    """
    from unittest.mock import MagicMock
    from ui.task_logic import ansible_watchdog

    mock = MagicMock(return_value=True)
    monkeypatch.setattr(ansible_watchdog, 'enable_default_watchdog', mock)
    return mock


@pytest.fixture(autouse=True)
def _fast_password_hashing(monkeypatch):
    """Hash test passwords with a cheap KDF.

    werkzeug's default is scrypt, ~120ms per call by design. The suite calls
    set_password() a few hundred times to get a user it can log in as, which is
    a minute of wall clock spent proving that scrypt is slow. Nothing asserts on
    the stored algorithm, and check_password_hash reads the method out of the
    hash itself, so the round trip still works.
    """
    monkeypatch.setattr(
        ui.models, 'generate_password_hash',
        lambda password, **kwargs: generate_password_hash(
            password, method='pbkdf2:sha256:1'),
    )
    yield


@pytest.fixture(autouse=True)
def _reset_minqlxtended_stub_state():
    """Clear the minqlxtended stub's shared state between tests.

    GameClient caches one live-memory view per client id, the way the engine hands
    back the same gclient_t for the same slot. That cache is process-wide, so without
    this a test reading GameClient(2).accuracy_shots sees whatever an earlier test
    wrote there. Autouse rather than opt-in: the tests that would be misled are the
    ones that never thought to ask.

    No-op unless the stub has been installed, so it costs nothing for the rest of the
    suite.
    """
    yield
    stub = sys.modules.get('minqlxtended')
    if stub is not None and getattr(stub, '_qlsm_stub', False):
        stub.GameClient.reset_all()
        stub.cvars.clear()
        stub.configstrings.clear()
        stub.console_lines.clear()
        stub.console_commands.clear()
        stub.logged_exceptions.clear()
        stub.Plugin.game = None
        stub.Plugin.db = None


@pytest.fixture
def preserve_logging_config():
    """Undo what a migration run does to logging.

    migrations/env.py calls logging.config.fileConfig(), which by default
    disables every logger that already exists (ui.cli among them) and swaps the
    root handlers and level. A later test asserting on caplog text from such a
    logger then sees nothing. Use this in any test that runs flask_migrate.
    """
    import logging

    root = logging.getLogger()
    root_state = (root.level, list(root.handlers))
    disabled = {name: logger.disabled for name, logger in logging.root.manager.loggerDict.items()
                if isinstance(logger, logging.Logger)}
    try:
        yield
    finally:
        root.setLevel(root_state[0])
        root.handlers[:] = root_state[1]
        for name, logger in logging.root.manager.loggerDict.items():
            if isinstance(logger, logging.Logger):
                logger.disabled = disabled.get(name, False)
