"""Wipe and reload every backed-up DB table from a parsed export dict.

Never commits — the caller (ui/task_logic/backup_import.py) only commits
after the matching filesystem swap has also succeeded, so the database and
on-disk state can never diverge from a partial restore.
"""
import datetime
import json

from sqlalchemy import null

from ui import db
from ui.addons.manifest import ADDON_ID_MAX, ADDON_ID_RE
from ui.models import (
    AddonScope, AddonState, ApiKey, AppSetting, BinaryMetadata, ConfigPreset, Host, HostStatus,
    InstanceStatus, Notification, Operator, PendingInstanceChange, QLFilterStatus, QLInstance, User,
)
from ui.runtime import CUSTOM, normalize_runtime
from ui.task_logic.backup_db_export import DB_EXPORT_FORMAT_VERSION

_REQUIRED_KEYS = ('hosts', 'instances', 'users', 'presets', 'api_keys', 'app_settings', 'binary_metadata')
_SQLITE_MAX_ROW_ID = 2 ** 63 - 1


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
        ssh_port=row.get('ssh_port', 22), os_type=row.get('os_type'), os_version=row.get('os_version'),
        is_standalone=row.get('is_standalone', False), timezone=row.get('timezone'),
        cpu_count=row.get('cpu_count'),
        redis_unix_socket=row.get('redis_unix_socket', False),
        lan_rate_uses_hook=row.get('lan_rate_uses_hook', False),
        firewall_pool_v2=row.get('firewall_pool_v2', False),
        runtime=CUSTOM if row.get('runtime') == CUSTOM else normalize_runtime(row.get('runtime')),
        runtime_provider_id=row.get('runtime_provider_id'),
        runtime_release_sha256=row.get('runtime_release_sha256'),
        runtime_plugin_api=row.get('runtime_plugin_api'),
        status=HostStatus(row['status']) if row.get('status') else HostStatus.UNKNOWN,
        qlfilter_status=QLFilterStatus(row['qlfilter_status']) if row.get('qlfilter_status') else QLFilterStatus.UNKNOWN,
        auto_restart_schedule=row.get('auto_restart_schedule'), logs=row.get('logs'),
        last_updated=_parse_dt(row.get('last_updated')), created_at=_parse_dt(row.get('created_at')),
    )


def _addon_states_from_export(data):
    rows = data.get('addon_states', [])
    if not isinstance(rows, list):
        raise BackupImportError("db_export.json has an invalid 'addon_states' list.")
    if not rows:
        return []

    scope_ids = {AddonScope.GLOBAL.value: {0}}
    for scope, table in ((AddonScope.HOST, 'hosts'), (AddonScope.INSTANCE, 'instances')):
        scope_ids[scope.value] = {
            row['id'] for row in data[table]
            if isinstance(row, dict) and type(row.get('id')) is int and 0 < row['id'] <= _SQLITE_MAX_ROW_ID
        }

    row_ids = set()
    state_keys = set()
    states = []
    for index, row in enumerate(rows, start=1):
        label = f'Invalid addon_states row {index}'
        if not isinstance(row, dict):
            raise BackupImportError(f'{label}: expected an object.')

        row_id = row.get('id')
        if type(row_id) is not int or not 0 < row_id <= _SQLITE_MAX_ROW_ID:
            raise BackupImportError(f'{label}: invalid row ID.')
        addon_id = row.get('addon_id')
        if not isinstance(addon_id, str) or len(addon_id) > ADDON_ID_MAX or not ADDON_ID_RE.fullmatch(addon_id):
            raise BackupImportError(f'{label}: invalid add-on ID.')

        scope, scope_id = row.get('scope'), row.get('scope_id')
        if not isinstance(scope, str) or scope not in scope_ids:
            raise BackupImportError(f'{label}: unknown scope.')
        if type(scope_id) is not int or scope_id not in scope_ids[scope]:
            raise BackupImportError(f'{label}: invalid scope ID or missing scope target in the backup.')

        state_key = (addon_id, scope, scope_id)
        if row_id in row_ids or state_key in state_keys:
            raise BackupImportError(f'{label}: duplicate row ID or add-on scope.')
        row_ids.add(row_id)
        state_keys.add(state_key)

        enabled, settings = row.get('enabled'), row.get('settings')
        if type(enabled) is not bool:
            raise BackupImportError(f'{label}: enabled must be a boolean.')
        if not isinstance(settings, dict):
            raise BackupImportError(f'{label}: settings must be an object.')
        try:
            settings_json = json.dumps(settings)
        except (TypeError, ValueError, RecursionError):
            raise BackupImportError(f'{label}: invalid settings object.') from None

        try:
            timestamps = {
                # Preserve explicit SQL NULL instead of invoking the model's default.
                field: datetime.datetime.fromisoformat(row[field]) if row.get(field) is not None else null()
                for field in ('created_at', 'updated_at')
            }
        except (TypeError, ValueError):
            raise BackupImportError(f'{label}: invalid timestamp.') from None

        states.append(AddonState(
            id=row_id, addon_id=addon_id, scope=scope, scope_id=scope_id,
            enabled=enabled, settings_json=settings_json, **timestamps,
        ))
    return states


def replace_database(data):
    if not isinstance(data, dict) or data.get('format_version') != DB_EXPORT_FORMAT_VERSION:
        raise BackupImportError('Unsupported or missing db_export format_version.')
    for key in _REQUIRED_KEYS:
        if not isinstance(data.get(key), list):
            raise BackupImportError(f"db_export.json is missing or has an invalid '{key}' list.")
    addon_states = _addon_states_from_export(data)

    # Children before parents so no foreign key is ever left dangling
    # mid-wipe (QLInstance.host_id -> Host.id).
    AddonState.query.delete()
    BinaryMetadata.query.delete()
    # Not backed up: pending-restart records describe the old install's
    # running servers and point at instance ids about to be replaced.
    PendingInstanceChange.query.delete()
    QLInstance.query.delete()
    Host.query.delete()
    ConfigPreset.query.delete()
    User.query.delete()
    ApiKey.query.delete()
    AppSetting.query.delete()
    Operator.query.delete()
    Notification.query.delete()
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
            runtime=normalize_runtime(row.get('runtime')),
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

    # 'operators' is intentionally not in _REQUIRED_KEYS: older backups predate
    # this table and simply have none to restore.
    for row in data.get('operators') or []:
        db.session.add(Operator(
            id=row['id'], name=row['name'], steam_id64=row['steam_id64'],
            default_level=row.get('default_level', 5),
            created_at=_parse_dt(row.get('created_at')), updated_at=_parse_dt(row.get('updated_at')),
        ))

    # Same for 'notifications'.
    for row in data.get('notifications') or []:
        db.session.add(Notification(
            id=row['id'], source=row['source'], severity=row['severity'],
            title=row['title'], body=row.get('body') or '', link=row.get('link'), key=row.get('key'),
            created_at=_parse_dt(row.get('created_at')), updated_at=_parse_dt(row.get('updated_at')),
            resolved_at=_parse_dt(row.get('resolved_at')), read_at=_parse_dt(row.get('read_at')),
        ))

    db.session.add_all(addon_states)
    db.session.flush()
