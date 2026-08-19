"""Wipe and reload every backed-up DB table from a parsed export dict.

Never commits — the caller (ui/task_logic/backup_import.py) only commits
after the matching filesystem swap has also succeeded, so the database and
on-disk state can never diverge from a partial restore.
"""
import datetime

from ui import db
from ui.models import (
    ApiKey, AppSetting, BinaryMetadata, ConfigPreset, Host, HostStatus,
    InstanceStatus, QLFilterStatus, QLInstance, User,
)
from ui.runtime import normalize_runtime
from ui.task_logic.backup_db_export import DB_EXPORT_FORMAT_VERSION

_REQUIRED_KEYS = ('hosts', 'instances', 'users', 'presets', 'api_keys', 'app_settings', 'binary_metadata')


class BackupImportError(ValueError):
    """Raised for a malformed db_export.json — always a 400, never a 500."""


def _parse_dt(value):
    return datetime.datetime.fromisoformat(value) if value else None


def _host_from_row(row):
    """Build a Host from a backup row.

    Optional columns use row.get(name, default) so a backup taken by an older
    QLSM restores cleanly -- a backup with no 'runtime' key lands every host on
    minqlx, which is correct.
    """
    return Host(
        id=row['id'], name=row['name'], ip_address=row.get('ip_address'),
        region=row.get('region'), machine_size=row.get('machine_size'),
        provider=row['provider'], workspace_name=row.get('workspace_name'),
        ssh_user=row.get('ssh_user'), ssh_key_path=row.get('ssh_key_path'),
        ssh_port=row.get('ssh_port', 22), os_type=row.get('os_type'),
        is_standalone=row.get('is_standalone', False), timezone=row.get('timezone'),
        cpu_count=row.get('cpu_count'),
        redis_unix_socket=row.get('redis_unix_socket', False),
        lan_rate_uses_hook=row.get('lan_rate_uses_hook', False),
        firewall_pool_v2=row.get('firewall_pool_v2', False),
        runtime=normalize_runtime(row.get('runtime')),
        status=HostStatus(row['status']) if row.get('status') else HostStatus.UNKNOWN,
        qlfilter_status=QLFilterStatus(row['qlfilter_status']) if row.get('qlfilter_status') else QLFilterStatus.UNKNOWN,
        auto_restart_schedule=row.get('auto_restart_schedule'), logs=row.get('logs'),
        last_updated=_parse_dt(row.get('last_updated')), created_at=_parse_dt(row.get('created_at')),
    )


def replace_database(data):
    if not isinstance(data, dict) or data.get('format_version') != DB_EXPORT_FORMAT_VERSION:
        raise BackupImportError('Unsupported or missing db_export format_version.')
    for key in _REQUIRED_KEYS:
        if not isinstance(data.get(key), list):
            raise BackupImportError(f"db_export.json is missing or has an invalid '{key}' list.")

    # Children before parents so no foreign key is ever left dangling
    # mid-wipe (QLInstance.host_id -> Host.id).
    BinaryMetadata.query.delete()
    QLInstance.query.delete()
    Host.query.delete()
    ConfigPreset.query.delete()
    User.query.delete()
    ApiKey.query.delete()
    AppSetting.query.delete()
    db.session.flush()

    for row in data['hosts']:
        db.session.add(_host_from_row(row))
    db.session.flush()

    for row in data['instances']:
        db.session.add(QLInstance(
            id=row['id'], name=row['name'], port=row['port'], hostname=row['hostname'],
            lan_rate_enabled=row.get('lan_rate_enabled', False), config=row.get('config'),
            qlx_plugins=row.get('qlx_plugins'), ld_preload_hooks=row.get('ld_preload_hooks'),
            cpu_affinity=row.get('cpu_affinity'), redis_db=row.get('redis_db'),
            status=InstanceStatus(row['status']) if row.get('status') else InstanceStatus.UNKNOWN,
            logs=row.get('logs'), zmq_rcon_port=row.get('zmq_rcon_port'),
            zmq_rcon_password=row.get('zmq_rcon_password'), zmq_stats_port=row.get('zmq_stats_port'),
            zmq_stats_password=row.get('zmq_stats_password'),
            last_updated=_parse_dt(row.get('last_updated')), created_at=_parse_dt(row.get('created_at')),
            host_id=row['host_id'],
        ))

    for row in data['users']:
        db.session.add(User(
            id=row['id'], username=row['username'], password_hash=row['password_hash'],
            created_at=_parse_dt(row.get('created_at')), last_login_at=_parse_dt(row.get('last_login_at')),
            password_change_required=row.get('password_change_required', False),
        ))

    for row in data['presets']:
        db.session.add(ConfigPreset(
            id=row['id'], name=row['name'], description=row.get('description'),
            path=row['path'], is_builtin=row.get('is_builtin', False),
            last_updated=_parse_dt(row.get('last_updated')), created_at=_parse_dt(row.get('created_at')),
        ))

    for row in data['api_keys']:
        db.session.add(ApiKey(id=row['id'], key=row['key'], created_at=_parse_dt(row.get('created_at'))))

    for row in data['app_settings']:
        db.session.add(AppSetting(key=row['key'], value=row['value']))

    for row in data['binary_metadata']:
        db.session.add(BinaryMetadata(
            id=row['id'], context_type=row['context_type'], context_key=row['context_key'],
            file_path=row['file_path'], description=row.get('description', ''),
            created_at=_parse_dt(row.get('created_at')), updated_at=_parse_dt(row.get('updated_at')),
        ))
    db.session.flush()
