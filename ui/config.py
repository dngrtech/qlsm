import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration."""
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-for-development-only')
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///qlds_ui.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Redis / RQ
    # Keep a plain Redis URL for app components (e.g. socket listener), and
    # derive the RQ URL from it so workers share the same endpoint.
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    RQ_REDIS_URL = REDIS_URL
    if os.environ.get('REDIS_PASSWORD'):
        RQ_REDIS_URL = RQ_REDIS_URL.replace('redis://', f'redis://:{os.environ.get("REDIS_PASSWORD")}@')
    RQ_QUEUES = ['default']
    RQ_DEFAULT_RESULT_TTL = int(os.environ.get('RQ_DEFAULT_RESULT_TTL', 86400))
    
    # Ansible Runner
    ANSIBLE_RUNNER_PRIVATE_DATA_DIR = os.environ.get('ANSIBLE_RUNNER_PRIVATE_DATA_DIR', './ansible_runner_data')
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', None)
    LOG_FORMAT = os.environ.get('LOG_FORMAT', 'text')  # 'text' or 'json'

    # JWT Settings
    JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', 24)) # Default to 24 hours

    # CORS Settings
    # Comma-separated list of allowed origins, e.g. "https://app.example.com,https://admin.example.com"
    # Defaults to empty (same-origin only; Vite proxy in dev / Nginx in prod handle this)
    CORS_ORIGINS = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()]

    # Session Cookie Settings (for HttpOnly JWT)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true' # Default False
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax') # Default 'Lax'
    SESSION_COOKIE_PATH = os.environ.get('SESSION_COOKIE_PATH', '/') # Default '/'

    # Flask-JWT-Extended Settings
    JWT_TOKEN_LOCATION = ['cookies']  # Look for JWTs in cookies
    JWT_COOKIE_SECURE = os.environ.get('JWT_COOKIE_SECURE', str(SESSION_COOKIE_SECURE)).lower() == 'true' # Align with SESSION_COOKIE_SECURE
    JWT_COOKIE_SAMESITE = os.environ.get('JWT_COOKIE_SAMESITE', SESSION_COOKIE_SAMESITE) # Align with SESSION_COOKIE_SAMESITE
    JWT_COOKIE_HTTPONLY = True # Ensure HttpOnly is True
    JWT_COOKIE_CSRF_PROTECT = True
    # JWT_SECRET_KEY will default to app.config['SECRET_KEY']
    # JWT_ACCESS_TOKEN_EXPIRES can be set here if needed, e.g., using JWT_EXPIRATION_HOURS
    # For example: from datetime import timedelta; JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=JWT_EXPIRATION_HOURS)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    JWT_COOKIE_SECURE = True  # Must be explicit — base class evaluates this before subclass overrides SESSION_COOKIE_SECURE

    # In production, ensure these are properly set
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for production environment")

class DockerProductionConfig(Config):
    """Docker production configuration.

    Identical to ProductionConfig but with auto-detected cookie/JWT security
    based on SITE_ADDRESS so HTTP-only installs (home servers without a domain)
    work out of the box alongside HTTPS installs.

    Security logic:
      - FORCE_HTTPS=true  → always set Secure flag (external TLS proxy)
      - SITE_ADDRESS starts with ':'  → HTTP-only, Secure flag off
      - SITE_ADDRESS is a domain name → HTTPS via Caddy, Secure flag on
    """
    DEBUG = False
    TESTING = False

    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for Docker production environment")

    _force_https = os.environ.get('FORCE_HTTPS', '').lower() == 'true'
    _site_address = os.environ.get('SITE_ADDRESS', ':80')
    _is_https = _force_https or not _site_address.startswith(':')

    SESSION_COOKIE_SECURE = _is_https
    JWT_COOKIE_SECURE = _is_https


class TestingConfig(Config):
    """Testing configuration."""
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

# Select the appropriate configuration based on FLASK_ENV
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'docker-production': DockerProductionConfig,
    'testing': TestingConfig
}

Config = config_map.get(os.environ.get('FLASK_ENV', 'development'), DevelopmentConfig)
