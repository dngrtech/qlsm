import os
import sys
import tempfile
import pytest
from ui import create_app, db

@pytest.fixture
def app(tmp_path):
    """Create and configure a Flask app for testing."""
    # Create a temporary file to isolate the database for each test
    db_fd, db_path = tempfile.mkstemp()

    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key', # Added for session/flash support in tests
        'JWT_SECRET_KEY': 'test-jwt-secret-key',  # Required for JWT token generation in tests
        'JWT_COOKIE_CSRF_PROTECT': False,  # Disable CSRF cookie protection in tests
        'JWT_TOKEN_LOCATION': ['headers', 'cookies'],  # Accept tokens from both locations
        'JWT_EXPIRATION_HOURS': 24,  # Matches ui.config.Config default
        'JWT_REMEMBER_ME_DAYS': 90,  # Matches ui.config.Config default
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
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

    # Dispose the engine first so SQLite releases its WAL/SHM files before
    # we unlink anything — otherwise those sidecar files are orphaned in /tmp.
    with app.app_context():
        db.session.remove()
        db.engine.dispose()

    os.close(db_fd)
    for path in (db_path, f'{db_path}-wal', f'{db_path}-shm'):
        if os.path.exists(path):
            os.unlink(path)

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
