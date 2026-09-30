import datetime
import enum
import json
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from ui.runtime import DEFAULT_RUNTIME, normalize_runtime

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
    os_type = db.Column(db.String(50), nullable=True) # Detected OS type when known (e.g. 'debian', 'ubuntu')
    is_standalone = db.Column(db.Boolean, default=False, nullable=False) # True for user-provided servers
    timezone = db.Column(db.String(50), nullable=True) # IANA timezone name (e.g., 'America/New_York')
    cpu_count = db.Column(db.Integer, nullable=True) # Detected/inferred Linux CPU count for affinity assignment
    redis_unix_socket = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    lan_rate_uses_hook = db.Column(db.Boolean, default=False, nullable=False, server_default='0') # True = LD_PRELOAD hook mechanism; False = legacy iptables/sysctl path
    firewall_pool_v2 = db.Column(db.Boolean, default=False, nullable=False, server_default='0') # True = firewall rendered with the current game/RCON port pool; False = narrower legacy allow-list
    # Which minqlx runtime this host builds and runs. Chosen at creation and
    # immutable thereafter -- migrating a live host is destructive, and a locked
    # column can never drift from what is actually installed on the box.
    runtime = db.Column(db.String(20), nullable=False, default=DEFAULT_RUNTIME,
                        server_default=DEFAULT_RUNTIME)
    status = db.Column(db.Enum(HostStatus), default=HostStatus.PENDING, nullable=False)
    qlfilter_status = db.Column(db.Enum(QLFilterStatus), default=QLFilterStatus.UNKNOWN, nullable=True) # New field for QLFilter
    auto_restart_schedule = db.Column(db.String(100), nullable=True) # Cron expression for auto-restart
    watchdog_enabled = db.Column(db.Boolean, default=False, nullable=False, server_default='0') # ql-watchdog addon: detect+restart hung QLDS instances
    watchdog_config = db.Column(db.Text, nullable=True) # JSON overrides: recvq_threshold, strikes, interval, grace, rate_max, rate_window, forensics, dryrun
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
            'cpu_count': self.cpu_count,
            'redis_unix_socket': bool(self.redis_unix_socket),
            'lan_rate_uses_hook': bool(self.lan_rate_uses_hook),
            'firewall_pool_v2': bool(self.firewall_pool_v2),
            'runtime': normalize_runtime(self.runtime),
            'status': self.status.value if self.status else None,
            'qlfilter_status': self.qlfilter_status.value if self.qlfilter_status else QLFilterStatus.UNKNOWN.value, # Include QLFilter status
            'auto_restart_schedule': self.auto_restart_schedule,
            'watchdog_enabled': bool(self.watchdog_enabled),
            'watchdog_config': self.watchdog_config,
            'logs': self.logs, # Include logs
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            # 'instance_count': len(self.instances), # Replaced by full instance list below
            'instances': [
                {
                    'id': instance.id,
                    'name': instance.name,
                    'port': instance.port,
                    'redis_db': instance.redis_db,
                }
                for instance in self.instances
            ]
        }


class QLInstance(db.Model):
    """Model representing a Quake Live server instance."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    # host = db.Column(db.String(100), nullable=False) # Removed - Replaced by host_id FK
    port = db.Column(db.Integer, nullable=False)
    hostname = db.Column(db.String(64), nullable=False) # Added: Hostname for the QL server (sv_hostname)
    lan_rate_enabled = db.Column(db.Boolean, default=False, nullable=False) # 99k LAN rate mode
    config = db.Column(db.Text, nullable=True)  # JSON stored as text
    qlx_plugins = db.Column(db.String(1000), nullable=True) # Selected plugins as comma-separated string
    ld_preload_hooks = db.Column(db.Text, nullable=True) # Comma-separated .so filenames in preload order
    cpu_affinity = db.Column(db.Integer, nullable=True) # Optional Linux CPU index assigned to this service
    redis_db = db.Column(db.Integer, nullable=True)  # Chosen Redis logical DB; NULL = derive from port
    runtime_invocation_id = db.Column(db.String(64), nullable=True)
    status = db.Column(db.Enum(InstanceStatus), default=InstanceStatus.IDLE, nullable=False) # Status of the QL instance itself
    logs = db.Column(db.Text, nullable=True) # Stores logs from background tasks (e.g., Ansible)
    
    # ZMQ RCON and stats settings (for remote console access and remote stats)
    zmq_rcon_port = db.Column(db.Integer, nullable=True)  # Port for ZMQ RCON (28888 + (port - 27960))
    zmq_rcon_password = db.Column(db.String(64), nullable=True)  # Password for ZMQ RCON
    zmq_stats_port = db.Column(db.Integer, nullable=True) # Port for ZMQ Stats (29999 + (port - 27960))
    zmq_stats_password = db.Column(db.String(64), nullable=True)  # Password for ZMQ stats socket
    
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Foreign Key to Host
    host_id = db.Column(db.Integer, db.ForeignKey('host.id'), nullable=False)

    rank_provider_config = db.relationship(
        'RankProviderConfig', uselist=False,
        # No passive_deletes: SQLite does not enforce FK ON DELETE CASCADE by
        # default, so the ORM itself must delete the child row.
        cascade='all, delete-orphan',
        backref='instance',
    )

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
            'host_os_type': self.host.os_type if self.host else None,
            'host_lan_rate_uses_hook': bool(self.host.lan_rate_uses_hook) if self.host else False,
            'host_runtime': normalize_runtime(self.host.runtime) if self.host else DEFAULT_RUNTIME,
            'port': self.port,
            'hostname': self.hostname, # Added hostname
            'lan_rate_enabled': self.lan_rate_enabled, # 99k LAN rate mode
            'config': self.config,
            'qlx_plugins': self.qlx_plugins,
            'ld_preload_hooks': self.ld_preload_hooks,
            'cpu_affinity': self.cpu_affinity,
            'redis_db': self.redis_db,
            'status': self.status.value if self.status else None,
            'logs': self.logs, # Include logs
            'zmq_rcon_port': self.zmq_rcon_port,
            'zmq_rcon_password': self.zmq_rcon_password,
            'zmq_stats_port': self.zmq_stats_port,
            'zmq_stats_password': self.zmq_stats_password,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class RankProviderConfig(db.Model):
    """Which external rank service one QLDS instance reads ratings from.

    One row per configured instance; an instance with no row has no rank
    provider. api_key is a plaintext column, exactly as zmq_stats_password
    already is on QLInstance — see ApiKey's docstring for the project's
    position on masking.
    """
    __tablename__ = 'rank_provider_config'

    id = db.Column(db.Integer, primary_key=True)
    instance_id = db.Column(
        db.Integer,
        db.ForeignKey('ql_instance.id', ondelete='CASCADE'),
        nullable=False, unique=True,
    )
    provider_type = db.Column(db.String(32), nullable=False)
    base_url = db.Column(db.String(255), nullable=True)
    api_key = db.Column(db.String(255), nullable=True)
    # Optional override. Blank means "derive from the live gametype" — the
    # normal case for qlstats and Slipgate. Set for providers with their own
    # pool names, e.g. elo-service's "ffa_auto".
    game_type = db.Column(db.String(16), nullable=True)
    extra = db.Column(db.Text, nullable=True)  # JSON; qlstats' elo|elo_b selector
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_updated = db.Column(
        db.DateTime, default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    def extra_dict(self):
        """The extra blob as a dict; {} when unset or malformed."""
        if not self.extra:
            return {}
        try:
            parsed = json.loads(self.extra)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def to_dict(self):
        return {
            'provider_type': self.provider_type,
            'base_url': self.base_url,
            'api_key': self.api_key,
            'game_type': self.game_type,
            'extra': self.extra_dict(),
            'enabled': self.enabled,
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
    is_builtin = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    # The runtime of the instance this preset was saved from. Presets are not
    # portable across runtimes -- plugins written for one do not run on the
    # other -- so this is provenance the load path checks before applying.
    runtime = db.Column(db.String(20), nullable=False, default=DEFAULT_RUNTIME,
                        server_default=DEFAULT_RUNTIME)
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
            'is_builtin': self.is_builtin,
            'runtime': normalize_runtime(self.runtime),
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


class Operator(db.Model):
    """Directory of named operators (SteamID64) assignable as owner/admin in server configs."""
    __tablename__ = 'operator'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    steam_id64 = db.Column(db.String(20), nullable=False, unique=True)
    default_level = db.Column(db.Integer, nullable=False, default=5, server_default='5')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'steam_id64': self.steam_id64,
            'default_level': self.default_level,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class PluginRepository(db.Model):
    """An external source of minqlx plugins and qlsm addons the operator can
    browse and install from -- plugin files into the local pool
    (data/shared-plugins/<runtime>/), addon .zip packages into
    ADDON_PACKAGES_DIR.

    The manifest is fetched over plain HTTP from `<url>/qlsm-repository.json`
    (falling back to the original `<url>/qlsm-plugins.json`, see
    ui/plugin_repositories.py) and cached here as-fetched, so browsing
    doesn't need a live request every time -- only "Sync" does. This is a
    source list, not the pool itself: nothing here is ever read at
    instance-deploy time.
    """
    __tablename__ = 'plugin_repository'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    url = db.Column(db.String(500), nullable=False)  # what qlsm fetches from
    # What the operator typed, when it differs from `url` -- a github.com repo
    # URL is stored resolved to its raw.githubusercontent.com form, but the
    # card should still show the address they recognize. NULL means they are
    # the same.
    display_url = db.Column(db.String(500), nullable=True)
    manifest_json = db.Column(db.Text, nullable=True)  # last-fetched qlsm-plugins.json, verbatim
    last_synced_at = db.Column(db.DateTime, nullable=True)
    last_sync_error = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        # manifest_json is either the original bare plugin list (rows synced
        # before addons existed) or {'plugins': [...], 'addons': [...]} --
        # normalized here so no reader ever sees the difference.
        plugins, addons = [], []
        if self.manifest_json:
            try:
                cached = json.loads(self.manifest_json)
            except ValueError:
                cached = []
            if isinstance(cached, dict):
                plugins = cached.get('plugins') or []
                addons = cached.get('addons') or []
            elif isinstance(cached, list):
                plugins = cached
        return {
            'id': self.id,
            'name': self.name,
            'url': self.display_url or self.url,
            'fetch_url': self.url,
            'plugins': plugins,
            'addons': addons,
            'last_synced_at': self.last_synced_at.isoformat() if self.last_synced_at else None,
            'last_sync_error': self.last_sync_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BinaryMetadata(db.Model):
    """Stores user-provided description labels for .so binary plugin files."""
    __tablename__ = 'binary_metadata'

    id = db.Column(db.Integer, primary_key=True)
    context_type = db.Column(db.String(20), nullable=False)
    context_key = db.Column(db.String(150), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    description = db.Column(db.String(1000), nullable=False, default='')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            'context_type',
            'context_key',
            'file_path',
            name='uq_bm_context_path',
        ),
    )


class AddonScope(enum.Enum):
    """The three layers an addon can be configured at.

    An addon is active globally, installed on a host, and switched on per
    instance, with each layer requiring the one above it.
    """
    GLOBAL = 'global'
    HOST = 'host'
    INSTANCE = 'instance'


class AddonState(db.Model):
    """Per-(addon, scope, scope_id) enable flag + settings blob.

    One row per place an addon is configured. `scope_id` is the Host.id or
    QLInstance.id the row belongs to, and is 0 for GLOBAL rows (SQLite treats
    NULL as distinct in unique constraints, so a sentinel keeps the uniqueness
    guarantee real for the global row).

    `settings_json` holds the addon's own settings as a JSON object string.
    It is deliberately opaque to core: the shape is declared by the addon's
    manifest, validated by ui/addons/settings.py against that manifest, and
    never interpreted here -- core must not grow knowledge of any specific
    addon's fields.

    No ForeignKey to host/instance on purpose: one column has to point at two
    different tables depending on `scope`, which a FK cannot express. Cleanup
    is therefore explicit, in ui/addons/registry.py's host/instance delete
    handling, and covered by its own test so it cannot silently rot.
    """
    __tablename__ = 'addon_state'

    id = db.Column(db.Integer, primary_key=True)
    addon_id = db.Column(db.String(64), nullable=False, index=True)
    scope = db.Column(db.String(16), nullable=False)
    scope_id = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    enabled = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    settings_json = db.Column(db.Text, nullable=False, default='{}', server_default='{}')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            'addon_id',
            'scope',
            'scope_id',
            name='uq_addon_state_scope',
        ),
    )

    @property
    def settings(self):
        """Parsed settings dict. A corrupt blob reads as {} rather than raising --
        one unreadable row must not break the whole addon catalog."""
        try:
            value = json.loads(self.settings_json or '{}')
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def to_dict(self):
        return {
            'id': self.id,
            'addon_id': self.addon_id,
            'scope': self.scope,
            'scope_id': self.scope_id,
            'enabled': bool(self.enabled),
            'settings': self.settings,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
