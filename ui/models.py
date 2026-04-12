import datetime
import enum
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from . import db

class HostStatus(enum.Enum):
    """Enum for Host status."""
    PENDING = 'pending'
    PROVISIONING = 'provisioning'
    PROVISIONED_PENDING_SETUP = 'provisioned_pending_setup' # Added for two-step provisioning
    ACTIVE = 'active'
    DELETING = 'deleting'
    ERROR = 'error'
    UNKNOWN = 'unknown'
    REBOOTING = 'rebooting'
    CONFIGURING = 'configuring'

class QLFilterStatus(enum.Enum):
    """Enum for Host QLFilter status."""
    NOT_INSTALLED = 'not_installed'
    INSTALLING = 'installing'
    ACTIVE = 'active' # Installed and service is active
    INACTIVE = 'inactive' # Installed but service is not active
    UNINSTALLING = 'uninstalling'
    ERROR = 'error'
    UNKNOWN = 'unknown'

class InstanceStatus(enum.Enum):
    """Enum for QLInstance status."""
    IDLE = 'idle'
    DEPLOYING = 'deploying'
    DELETING = 'deleting' # Deletion initiated
    RUNNING = 'running'
    STOPPING = 'stopping'
    STOPPED = 'stopped'
    STARTING = 'starting'
    RESTARTING = 'restarting'
    CONFIGURING = 'configuring'
    UPDATED = 'updated'  # Config synced but instance not restarted
    ERROR = 'error'
    UNKNOWN = 'unknown'

class Host(db.Model):
    """Model representing a target host server."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    ip_address = db.Column(db.String(50), nullable=True) # Populated after Terraform provisioning
    region = db.Column(db.String(50), nullable=True) # User selected, passed to Terraform
    machine_size = db.Column(db.String(50), nullable=True) # User selected, passed to Terraform
    provider = db.Column(db.String(50), nullable=False) # Cloud provider (e.g., 'vultr', 'gcp')
    workspace_name = db.Column(db.String(150), nullable=True, unique=True) # Terraform workspace name
    ssh_user = db.Column(db.String(50), default='ansible') # Default user for Ansible
    ssh_key_path = db.Column(db.String(255), nullable=True) # Path to private key generated/used by Terraform
    ssh_port = db.Column(db.Integer, default=22, nullable=False) # SSH port for connections
    os_type = db.Column(db.String(50), default='debian', nullable=True) # OS type: 'debian', 'ubuntu'
    is_standalone = db.Column(db.Boolean, default=False, nullable=False) # True for user-provided servers
    timezone = db.Column(db.String(50), nullable=True) # IANA timezone name (e.g., 'America/New_York')
    status = db.Column(db.Enum(HostStatus), default=HostStatus.PENDING, nullable=False)
    qlfilter_status = db.Column(db.Enum(QLFilterStatus), default=QLFilterStatus.UNKNOWN, nullable=True) # New field for QLFilter
    auto_restart_schedule = db.Column(db.String(100), nullable=True) # Cron expression for auto-restart
    logs = db.Column(db.Text, nullable=True) # Stores logs from background tasks (e.g., Terraform)
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Relationship to QLInstances (one-to-many)
    # cascade="all, delete-orphan": If a Host is deleted, its associated QLInstances are also deleted.
    instances = db.relationship('QLInstance', backref='host', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Host {self.name} ({self.ip_address or "No IP"})>'

    def to_dict(self):
        """Convert host to dictionary."""
        # Ensure the instance is refreshed from the database session
        # to get the most up-to-date state, especially for enum fields.
        db.session.refresh(self)
        return {
            'id': self.id,
            'name': self.name,
            'ip_address': self.ip_address,
            'region': self.region,
            'machine_size': self.machine_size,
            'provider': self.provider,
            'workspace_name': self.workspace_name,
            'ssh_user': self.ssh_user,
            'ssh_key_path': self.ssh_key_path,
            'ssh_port': self.ssh_port,
            'os_type': self.os_type,
            'is_standalone': self.is_standalone,
            'timezone': self.timezone,
            'status': self.status.value if self.status else None,
            'qlfilter_status': self.qlfilter_status.value if self.qlfilter_status else QLFilterStatus.UNKNOWN.value, # Include QLFilter status
            'auto_restart_schedule': self.auto_restart_schedule,
            'logs': self.logs, # Include logs
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            # 'instance_count': len(self.instances), # Replaced by full instance list below
            'instances': [{'id': instance.id, 'name': instance.name, 'port': instance.port} for instance in self.instances]
        }


class QLInstance(db.Model):
    """Model representing a Quake Live server instance."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    # host = db.Column(db.String(100), nullable=False) # Removed - Replaced by host_id FK
    port = db.Column(db.Integer, nullable=False)
    hostname = db.Column(db.String(255), nullable=False) # Added: Hostname for the QL server (sv_hostname)
    lan_rate_enabled = db.Column(db.Boolean, default=False, nullable=False) # 99k LAN rate mode
    config = db.Column(db.Text, nullable=True)  # JSON stored as text
    qlx_plugins = db.Column(db.String(1000), nullable=True) # Selected plugins as comma-separated string
    status = db.Column(db.Enum(InstanceStatus), default=InstanceStatus.IDLE, nullable=False) # Status of the QL instance itself
    logs = db.Column(db.Text, nullable=True) # Stores logs from background tasks (e.g., Ansible)
    
    # ZMQ RCON and stats settings (for remote console access and remote stats)
    zmq_rcon_port = db.Column(db.Integer, nullable=True)  # Port for ZMQ RCON (28960 + id - 1)
    zmq_rcon_password = db.Column(db.String(64), nullable=True)  # Password for ZMQ RCON
    zmq_stats_port = db.Column(db.Integer, nullable=True) # Port for ZMQ Stats (29999 + id - 1)
    zmq_stats_password = db.Column(db.String(64), nullable=True)  # Password for ZMQ stats socket
    
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Foreign Key to Host
    host_id = db.Column(db.Integer, db.ForeignKey('host.id'), nullable=False)
    
    def __repr__(self):
        # Access host name via the backref relationship
        host_name = self.host.name if self.host else "No Host"
        return f'<QLInstance {self.name} ({host_name}:{self.port})>'
    
    def to_dict(self):
        """Convert instance to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'host_id': self.host_id,
            'host_name': self.host.name if self.host else None, # Include host name for convenience
            'host_ip_address': self.host.ip_address if self.host else None, # Include host IP address
            'port': self.port,
            'hostname': self.hostname, # Added hostname
            'lan_rate_enabled': self.lan_rate_enabled, # 99k LAN rate mode
            'config': self.config,
            'qlx_plugins': self.qlx_plugins,
            'status': self.status.value if self.status else None,
            'logs': self.logs, # Include logs
            'zmq_rcon_port': self.zmq_rcon_port,
            'zmq_rcon_password': self.zmq_rcon_password,
            'zmq_stats_port': self.zmq_stats_port,
            'zmq_stats_password': self.zmq_stats_password,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class User(db.Model):
    """Model representing an application user."""
    __tablename__ = 'user' # Explicit table name

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False) # Increased length for modern hashes
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)
    password_change_required = db.Column(
        db.Boolean,
        default=False,
        nullable=False,
        server_default='0'
    )

    def set_password(self, password):
        """Hashes and sets the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Checks if the provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self):
        """Convert user to dictionary (excluding password hash)."""
        return {
            'id': self.id,
            'username': self.username,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'password_change_required': self.password_change_required
        }


# Configuration Preset Model
class ConfigPreset(db.Model):
    """Model representing a reusable configuration preset.

    Config content is stored on the filesystem at the path specified.
    The path column stores the folder path (e.g., 'configs/presets/mypreset').
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    path = db.Column(db.String(255), nullable=False)  # Filesystem path to preset folder
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f'<ConfigPreset {self.name}>'

    def to_dict(self):
        """Convert preset to dictionary (metadata only, no config content)."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'path': self.path,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ApiKey(db.Model):
    """Single active external API key for service-to-service auth.

    Plaintext storage by design: single-user app where the key is
    always viewable in the Settings UI. No hash column to avoid
    misleading security theater.
    """
    __tablename__ = 'api_key'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    @staticmethod
    def generate():
        """Create a new ApiKey instance (not yet added to session)."""
        return ApiKey(key=secrets.token_urlsafe(32))


class AppSetting(db.Model):
    """Generic key-value settings table."""
    __tablename__ = 'app_setting'

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)

    def to_dict(self):
        return {'key': self.key, 'value': self.value}
