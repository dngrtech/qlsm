"""Serialize every backed-up DB table to a JSON-safe snapshot."""
from ui.models import ApiKey, AppSetting, BinaryMetadata, ConfigPreset, Host, QLInstance, User
from ui.runtime import normalize_runtime

DB_EXPORT_FORMAT_VERSION = 1


def _iso(value):
    return value.isoformat() if value else None


def _host_row(host):
    return {
        'id': host.id, 'name': host.name, 'ip_address': host.ip_address,
        'region': host.region, 'machine_size': host.machine_size,
        'provider': host.provider, 'workspace_name': host.workspace_name,
        'ssh_user': host.ssh_user, 'ssh_key_path': host.ssh_key_path,
        'ssh_port': host.ssh_port, 'os_type': host.os_type,
        'is_standalone': host.is_standalone, 'timezone': host.timezone,
        'cpu_count': host.cpu_count,
        'redis_unix_socket': bool(host.redis_unix_socket),
        'lan_rate_uses_hook': bool(host.lan_rate_uses_hook),
        'firewall_pool_v2': bool(host.firewall_pool_v2),
        'runtime': normalize_runtime(host.runtime),
        'status': host.status.value if host.status else None,
        'qlfilter_status': host.qlfilter_status.value if host.qlfilter_status else None,
        'auto_restart_schedule': host.auto_restart_schedule,
        'logs': host.logs,
        'last_updated': _iso(host.last_updated),
        'created_at': _iso(host.created_at),
    }


def _instance_row(instance):
    return {
        'id': instance.id, 'name': instance.name, 'port': instance.port,
        'hostname': instance.hostname, 'lan_rate_enabled': instance.lan_rate_enabled,
        'config': instance.config, 'qlx_plugins': instance.qlx_plugins,
        'ld_preload_hooks': instance.ld_preload_hooks, 'cpu_affinity': instance.cpu_affinity,
        'redis_db': instance.redis_db,
        'status': instance.status.value if instance.status else None,
        'logs': instance.logs,
        'zmq_rcon_port': instance.zmq_rcon_port, 'zmq_rcon_password': instance.zmq_rcon_password,
        'zmq_stats_port': instance.zmq_stats_port, 'zmq_stats_password': instance.zmq_stats_password,
        'last_updated': _iso(instance.last_updated), 'created_at': _iso(instance.created_at),
        'host_id': instance.host_id,
    }


def _user_row(user):
    return {
        'id': user.id, 'username': user.username, 'password_hash': user.password_hash,
        'created_at': _iso(user.created_at), 'last_login_at': _iso(user.last_login_at),
        'password_change_required': user.password_change_required,
    }


def _preset_row(preset):
    return {
        'id': preset.id, 'name': preset.name, 'description': preset.description,
        'path': preset.path, 'is_builtin': bool(preset.is_builtin),
        'last_updated': _iso(preset.last_updated), 'created_at': _iso(preset.created_at),
    }


def _api_key_row(key):
    return {'id': key.id, 'key': key.key, 'created_at': _iso(key.created_at)}


def _app_setting_row(setting):
    return {'key': setting.key, 'value': setting.value}


def _binary_meta_row(row):
    return {
        'id': row.id, 'context_type': row.context_type, 'context_key': row.context_key,
        'file_path': row.file_path, 'description': row.description,
        'created_at': _iso(row.created_at), 'updated_at': _iso(row.updated_at),
    }


def serialize_database():
    """Return a JSON-serializable snapshot of every backed-up table."""
    return {
        'format_version': DB_EXPORT_FORMAT_VERSION,
        'hosts': [_host_row(h) for h in Host.query.order_by(Host.id).all()],
        'instances': [_instance_row(i) for i in QLInstance.query.order_by(QLInstance.id).all()],
        'users': [_user_row(u) for u in User.query.order_by(User.id).all()],
        'presets': [_preset_row(p) for p in ConfigPreset.query.order_by(ConfigPreset.id).all()],
        'api_keys': [_api_key_row(k) for k in ApiKey.query.order_by(ApiKey.id).all()],
        'app_settings': [_app_setting_row(s) for s in AppSetting.query.order_by(AppSetting.key).all()],
        'binary_metadata': [_binary_meta_row(r) for r in BinaryMetadata.query.order_by(BinaryMetadata.id).all()],
    }
