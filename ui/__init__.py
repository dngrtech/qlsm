import os
import sys
import logging
import redis as redis_lib
from flask import Flask, Blueprint, current_app
from flask_rq2 import RQ
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

# Initialize extensions
db = SQLAlchemy()
rq = RQ()
jwt = JWTManager()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"]
)
migrate = Migrate()

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    """Reject tokens that were explicitly revoked at logout."""
    redis = current_app.extensions.get('redis')
    if redis is None:
        return False
    try:
        return redis.get(f"jwt_blocklist:{jwt_payload['jti']}") is not None
    except Exception as e:
        current_app.logger.warning(f"Redis blocklist check failed: {e}")
        return False  # fail open if Redis is unavailable

# SocketIO - import from socketio_events module
from ui.socketio_events import socketio

# Redis listener for RCON - initialized after app creation
redis_listener = None

# Install global exception hooks to catch unhandled exceptions in threads
# Without this, daemon thread crashes are silently swallowed and can
# propagate as exit code 255 in gunicorn workers.
_orig_threading_excepthook = None

def _thread_excepthook(args):
    """Log unhandled exceptions in threads instead of crashing silently."""
    logging.getLogger(__name__).error(
        "Unhandled exception in thread %s: %s",
        args.thread.name if args.thread else "unknown",
        args.exc_value,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
    )

import threading
threading.excepthook = _thread_excepthook


def create_app(test_config=None):
    """Create and configure the Flask application using the factory pattern."""
    global redis_listener
    
    # NEW and SIMPLIFIED: Flask only needs its instance path.
    # Static file serving is now handled by the reverse proxy (Nginx).
    app = Flask(__name__, instance_relative_config=True)
    
    # Apply ProxyFix in production so REMOTE_ADDR reflects the real client IP (not Nginx's).
    # Skipped in debug mode to avoid conflicts with the Werkzeug reloader.
    if not app.debug:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)
    
    # Load config
    if test_config is None:
        app.config.from_object('ui.config.Config')
    else:
        app.config.from_mapping(test_config)

    # Configure logging early so all startup logs honor LOG_LEVEL/LOG_FORMAT.
    configure_logging(app)
    
    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    # Initialize extensions with app
    db.init_app(app)

    # Enable WAL mode for SQLite to support concurrent writes from multiple workers.
    # Also set busy_timeout so brief write contention retries instead of failing.
    from sqlalchemy import event

    with app.app_context():
        @event.listens_for(db.engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, connection_record):
            if 'sqlite' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

    migrate.init_app(app, db)
    rq.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)

    # Shared Redis client (used for JWT blocklist and login lockout)
    try:
        app.extensions['redis'] = redis_lib.from_url(
            app.config['RQ_REDIS_URL'], decode_responses=True
        )
    except Exception as e:
        app.logger.warning(f"Redis client init failed — JWT blocklist and lockout disabled: {e}")
    cors_origins = app.config.get('CORS_ORIGINS', [])
    if cors_origins:
        CORS(app, resources={r"/api/*": {"origins": cors_origins, "allow_headers": ["Content-Type", "X-CSRF-TOKEN"], "supports_credentials": True}})
    # When CORS_ORIGINS is empty, no CORS headers are added — browser enforces same-origin policy
    
    # Initialize Flask-SocketIO with Redis message queue (optional for RCON feature)
    redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379/0')
    redis_password = os.environ.get('REDIS_PASSWORD')
    rcon_enabled = app.config.get('RCON_ENABLED', True)
    
    # Build Redis URL with password if provided
    if redis_password:
        # URL-encode the password to handle special characters
        from urllib.parse import quote
        encoded_password = quote(redis_password, safe='')
        # Parse the URL and insert password
        # Format: redis://[:password@]host:port/db
        if '://' in redis_url:
            scheme, rest = redis_url.split('://', 1)
            redis_url_with_auth = f"{scheme}://:{encoded_password}@{rest}"
        else:
            redis_url_with_auth = redis_url
    else:
        redis_url_with_auth = redis_url
    
    # Only web-serving runtimes should initialize SocketIO + Redis listener.
    # Skip for Flask CLI commands like rq worker / run-status-poller / init-db.
    is_flask_cli = os.path.basename(sys.argv[0]) == 'flask'
    flask_cli_cmd = sys.argv[1] if is_flask_cli and len(sys.argv) > 1 else None
    is_web_runtime = (not is_flask_cli) or flask_cli_cmd == 'run'

    # Gunicorn pre-fork safety: the master process calls create_app() to
    # validate the WSGI app, then forks workers.  Background threads started
    # in the master (SocketIO Redis pubsub, RCON listener) don't survive the
    # fork, and any locks they hold become permanently locked in the child —
    # causing an intermittent deadlock.
    #
    # Solution: in the gunicorn master, init SocketIO *without* a message
    # queue (no threads).  The post_fork hook in gunicorn.conf.py re-inits
    # SocketIO with the message queue and starts the Redis listener in each
    # worker after the fork.
    is_gunicorn = 'gunicorn' in os.path.basename(sys.argv[0])
    is_gunicorn_worker = os.environ.get('_GUNICORN_WORKER') == '1'
    is_gunicorn_master = is_gunicorn and not is_gunicorn_worker

    # Restrict WebSocket origins to the same list used for HTTP CORS.
    # Defaults to same-origin (empty list) when CORS_ORIGINS is not configured.
    socketio_cors = app.config.get('CORS_ORIGINS') or []

    if is_gunicorn_master:
        # Master: init SocketIO without message_queue (no background threads)
        socketio.init_app(app, cors_allowed_origins=socketio_cors, async_mode='threading')
        app.logger.info('SocketIO initialized (master, no message queue)')
    elif rcon_enabled and is_web_runtime:
        try:
            async_mode = 'threading'

            socketio.init_app(
                app,
                message_queue=redis_url_with_auth,
                cors_allowed_origins=socketio_cors,
                async_mode=async_mode
            )

            # Start Redis listener for RCON responses
            # Skip in reloader spawner process (avoids duplicate listeners)
            is_reloader_spawner = app.debug and os.environ.get('WERKZEUG_RUN_MAIN') == 'false'
            if not is_reloader_spawner:
                try:
                    from ui.redis_listener import RedisListener
                    redis_listener = RedisListener(socketio, redis_url_with_auth)
                    redis_listener.start()
                    app.logger.info('RCON Redis listener started')
                except Exception as e:
                    app.logger.warning(f'Failed to start RCON Redis listener: {e}')

            app.logger.info(f'Flask-SocketIO initialized (async_mode={async_mode})')
        except Exception as e:
            app.logger.warning(f'Failed to initialize SocketIO for RCON: {e}')
            socketio.init_app(app, cors_allowed_origins=socketio_cors, async_mode='threading')
    elif is_web_runtime:
        socketio.init_app(app, cors_allowed_origins=socketio_cors, async_mode='threading')

    # Register blueprints from the new routes package
    from ui.routes.instance_routes import instance_api_bp
    from ui.routes.host_routes import host_api_bp
    from ui.routes.auth_api_routes import auth_api_bp
    from ui.routes.preset_api_routes import preset_api_bp
    from ui.routes.user_routes import user_api_bp
    from ui.routes.script_routes import script_api_bp
    from ui.routes.index_routes import index_bp
    
    # Create and register the main API blueprint
    api_bp = Blueprint('api', __name__, url_prefix='/api')
    
    # Register resource-specific API blueprints
    api_bp.register_blueprint(host_api_bp, url_prefix='/hosts')
    api_bp.register_blueprint(instance_api_bp, url_prefix='/instances')
    api_bp.register_blueprint(auth_api_bp, url_prefix='/auth')
    api_bp.register_blueprint(preset_api_bp, url_prefix='/presets')
    api_bp.register_blueprint(user_api_bp, url_prefix='/users')
    api_bp.register_blueprint(script_api_bp, url_prefix='/scripts')

    from ui.routes.draft_routes import draft_api_bp
    api_bp.register_blueprint(draft_api_bp, url_prefix='/drafts')

    from ui.routes.factory_routes import factory_api_bp
    api_bp.register_blueprint(factory_api_bp, url_prefix='/factories')

    from ui.routes.settings_routes import settings_api_bp
    api_bp.register_blueprint(settings_api_bp, url_prefix='/settings')

    from ui.routes.server_status_routes import server_status_bp
    api_bp.register_blueprint(server_status_bp, url_prefix='/server-status')

    app.register_blueprint(api_bp)
    app.register_blueprint(index_bp) # Register index_bp

    # External API (versioned, separate from internal UI API)
    from ui.routes.external_api_routes import external_api_bp
    app.register_blueprint(external_api_bp, url_prefix='/api/v1')


    # Register database commands
    from ui import database
    database.register_db_commands(app)

    from ui.cli import register_cli_commands
    register_cli_commands(app)

    # Register context processors
    from .models import HostStatus, InstanceStatus # Use relative import for models here too for consistency
    @app.context_processor
    def inject_enums():
        return dict(HostStatus=HostStatus, InstanceStatus=InstanceStatus)

    # Register utility filters
    from .general_utils import format_vultr_region, format_vultr_plan # Use relative import
    app.jinja_env.filters['format_vultr_region'] = format_vultr_region
    app.jinja_env.filters['format_vultr_plan'] = format_vultr_plan

    return app

def configure_logging(app):
    """Configure logging for the application."""
    log_level = app.config.get('LOG_LEVEL', logging.INFO)
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)
    log_format = app.config.get('LOG_FORMAT', 'text')

    # Configure root logger
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    app.logger.handlers.clear()
    root_logger.setLevel(log_level)
    app.logger.setLevel(log_level)
    logging.getLogger(app.import_name).setLevel(log_level)

    # Create formatter based on LOG_FORMAT
    if log_format == 'json':
        from pythonjsonlogger.json import JsonFormatter
        formatter = JsonFormatter(
            fmt='%(asctime)s %(levelname)s %(name)s %(module)s %(message)s',
            rename_fields={
                'levelname': 'level',
                'name': 'logger',
                'asctime': 'timestamp',
            },
        )
    else:
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if configured)
    log_file = app.config.get('LOG_FILE')
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Reduce verbosity of third-party libraries
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    app.logger.info('Logging configured')
