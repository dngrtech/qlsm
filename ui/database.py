import click
import datetime
from flask import current_app
from flask.cli import with_appcontext
from ui import db
# Import models and status enums
from ui.models import QLInstance, Host, HostStatus, ConfigPreset

def init_db():
    """Initialize the database."""
    db.drop_all()
    db.create_all()
    current_app.logger.info('Database initialized')

@click.command('init-db')
@with_appcontext
def init_db_command():
    """CLI command to initialize the database."""
    init_db()
    click.echo('Database initialized.')

def register_db_commands(app):
    """Register database CLI commands with the app."""
    from ui.preset_cli import register_preset_commands
    from ui.user_cli import register_user_commands

    app.cli.add_command(init_db_command)
    register_preset_commands(app)
    register_user_commands(app)

# --- Instance Database Helpers ---

def get_instances():
    """Get all QL instances."""
    # Eager load the host relationship to avoid N+1 queries in templates
    return QLInstance.query.options(db.joinedload(QLInstance.host)).all()

def get_instance(instance_id):
    """Get a specific QL instance by ID."""
    # Use the modern db.session.get() method. Host relationship will be lazy-loaded.
    return db.session.get(QLInstance, instance_id)

def get_instance_by_name(name):
    """Get a specific QL instance by name."""
    # Eager load the host relationship
    return QLInstance.query.options(db.joinedload(QLInstance.host)).filter_by(name=name).first()

# Update create_instance to accept host_id, hostname, and lan_rate_enabled
def create_instance(name, host_id, port, hostname, lan_rate_enabled=False, config=None, qlx_plugins=None):
    """Create a new QL instance."""
    # Ensure host_id is an integer
    host_id_int = int(host_id)
    instance = QLInstance(
        name=name,
        host_id=host_id_int,
        port=port,
        hostname=hostname,
        lan_rate_enabled=lan_rate_enabled,
        config=config,
        qlx_plugins=qlx_plugins
    )
    db.session.add(instance)
    db.session.commit()
    return instance

# Update update_instance to accept host_id and hostname (via kwargs)
def update_instance(instance_id, **kwargs):
    """Update an existing QL instance."""
    instance = get_instance(instance_id)
    if not instance:
        return None
    
    for key, value in kwargs.items():
        if hasattr(instance, key):
            # Handle host_id specifically if needed, ensure it's an int
            if key == 'host_id' and value is not None:
                 try:
                     value = int(value)
                 except ValueError:
                     current_app.logger.warning(f"Invalid host_id value '{value}' provided for instance {instance_id}")
                     continue # Skip updating host_id if invalid
            # Removed obsolete config handling, hostname is handled like other attributes
            setattr(instance, key, value)

    db.session.commit()
    return instance

def delete_instance(instance_id):
    """Delete a QL instance."""
    instance = get_instance(instance_id)
    if not instance:
        return False
    
    db.session.delete(instance)
    db.session.commit()
    return True

# --- Host Database Helpers ---

def get_hosts():
    """Get all Host records, ordered by name. Ensures fresh data from DB."""
    # Expire all Host instances from the session to force a refresh from the DB
    # This helps ensure that changes made by other processes (e.g., RQ workers) are reflected.
    db.session.expire_all() 
    return Host.query.order_by(Host.name).all()

def get_host(host_id):
    """Get a specific Host by ID."""
    return db.session.get(Host, host_id)

def get_host_by_name(name):
    """Get a specific Host by name (case-insensitive)."""
    return Host.query.filter(db.func.lower(Host.name) == name.lower()).first()

def create_host(**kwargs):
    """Create a new Host record."""
    # Ensure status is set if provided, otherwise default in model applies
    if 'status' in kwargs and not isinstance(kwargs['status'], HostStatus):
        # Attempt to convert string to enum if necessary
        try:
            kwargs['status'] = HostStatus(kwargs['status'])
        except ValueError:
            # Handle invalid status string if needed, maybe default or raise error
            kwargs['status'] = HostStatus.PENDING # Default fallback
            
    host = Host(**kwargs)
    db.session.add(host)
    db.session.commit()
    return host

def update_host(host_id, **kwargs):
    """Update an existing Host record."""
    host = get_host(host_id)
    if not host:
        return None
    
    for key, value in kwargs.items():
        if hasattr(host, key):
            # Handle status enum conversion if necessary
            if key == 'status' and value and not isinstance(value, HostStatus):
                 try:
                     value = HostStatus(value)
                 except ValueError:
                     # Log warning or handle invalid status string
                     current_app.logger.warning(f"Invalid status value '{value}' provided for host {host_id}")
                     continue # Skip updating status if invalid
            setattr(host, key, value)
            
    # Ensure last_updated is touched
    host.last_updated = datetime.datetime.utcnow() 
    
    db.session.commit()
    return host

def delete_host(host_id):
    """Delete a Host record."""
    host = get_host(host_id)
    if not host:
        return False
        
    # Optional: Add check here to prevent deletion if instances exist, 
    # although the route already checks this. Belt and suspenders.
    if host.instances:
        current_app.logger.warning(f"Attempted to delete host {host_id} which still has instances.")
        return False # Or raise an exception

    db.session.delete(host)
    db.session.commit()
    return True

# --- Config Preset Database Helpers ---

def get_presets():
    """Get all ConfigPreset records, ordered by name."""
    return ConfigPreset.query.order_by(ConfigPreset.name).all()

def get_preset(preset_id):
    """Get a specific ConfigPreset by ID."""
    return db.session.get(ConfigPreset, preset_id)

def get_preset_by_name(name):
    """Get a specific ConfigPreset by name."""
    return ConfigPreset.query.filter_by(name=name).first()

def create_preset(**kwargs):
    """Create a new ConfigPreset record."""
    preset = ConfigPreset(**kwargs)
    db.session.add(preset)
    db.session.commit()
    return preset

def update_preset(preset_id, **kwargs):
    """Update an existing ConfigPreset record."""
    preset = get_preset(preset_id)
    if not preset:
        return None
    
    for key, value in kwargs.items():
        if hasattr(preset, key):
            setattr(preset, key, value)
            
    # Ensure last_updated is touched
    preset.last_updated = datetime.datetime.utcnow() 
    
    db.session.commit()
    return preset

def delete_preset(preset_id):
    """Delete a ConfigPreset record."""
    preset = get_preset(preset_id)
    if not preset:
        return False
        
    db.session.delete(preset)
    db.session.commit()
    return True
