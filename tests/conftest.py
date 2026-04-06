import os
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
    
    # Close and remove the temporary database
    os.close(db_fd)
    os.unlink(db_path)

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
