"""Scoped settings + enable state for one addon, backed by the AddonState table.

The three scopes (global / host / instance) are a layered switch, not three
independent ones: an instance is only really enabled if its host is, and its
host only if the addon is enabled globally. `is_enabled()` is the single place
that rule is implemented, so no addon and no call site can reimplement it
slightly differently.

Values are validated + coerced against the addon's own manifest before they
are written. Core never interprets what a setting *means* -- only that a field
the manifest declared as "number" is stored as a number.
"""
import json

from ui import db
from ui.models import AddonState, AddonScope, QLInstance
from ui.addons.runtime_protection import (
    check_provider_dependencies, lock_provider_state, lock_scoped_state_cleanup,
)

GLOBAL_SCOPE_ID = 0  # sentinel: SQLite treats NULLs as distinct in UNIQUE


class AddonSettingsError(ValueError):
    """Rejected input -- always surfaces as a 400, never a 500."""


def _scope_value(scope):
    if isinstance(scope, AddonScope):
        return scope.value
    scope = (scope or '').strip().lower()
    if scope not in [s.value for s in AddonScope]:
        raise AddonSettingsError(f'unknown scope "{scope}"')
    return scope


def _coerce(field, value):
    """Coerce one manifest-declared field, or raise AddonSettingsError."""
    key, ftype = field['key'], field['type']
    if ftype == 'bool':
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ('true', 'false', '1', '0'):
            return value.strip().lower() in ('true', '1')
        raise AddonSettingsError(f'"{key}" must be a boolean')
    if ftype == 'number':
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise AddonSettingsError(f'"{key}" must be a number')
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise AddonSettingsError(f'"{key}" must be a number')
        if 'min' in field and number < field['min']:
            raise AddonSettingsError(f'"{key}" must be at least {field["min"]}')
        if 'max' in field and number > field['max']:
            raise AddonSettingsError(f'"{key}" must be at most {field["max"]}')
        return int(number) if float(number).is_integer() else number
    if ftype == 'select':
        if not isinstance(value, str):
            raise AddonSettingsError(f'"{key}" must be a string')
        allowed = {
            (opt['value'] if isinstance(opt, dict) else opt)
            for opt in field.get('options', [])
        }
        if value not in allowed:
            raise AddonSettingsError(f'"{key}" must be one of {", ".join(sorted(allowed))}')
        return value
    # string / secret
    if value is None:
        return ''
    if not isinstance(value, str):
        raise AddonSettingsError(f'"{key}" must be a string')
    return value.strip()


class AddonSettings:
    """Settings accessor handed to an addon as `ctx.settings`."""

    def __init__(self, addon_id, manifest):
        self.addon_id = addon_id
        self._manifest = manifest or {}

    # ---- schema -------------------------------------------------------

    def fields(self, scope):
        return (self._manifest.get('settings') or {}).get(_scope_value(scope)) or []

    def defaults(self, scope):
        out = {}
        for field in self.fields(scope):
            if 'default' in field:
                out[field['key']] = field['default']
            elif field['type'] == 'bool':
                out[field['key']] = False
            elif field['type'] == 'number':
                out[field['key']] = 0
            else:
                out[field['key']] = ''
        return out

    # ---- rows ---------------------------------------------------------

    def _row(self, scope, scope_id, create=False):
        scope = _scope_value(scope)
        scope_id = GLOBAL_SCOPE_ID if scope == AddonScope.GLOBAL.value else int(scope_id)
        row = AddonState.query.filter_by(
            addon_id=self.addon_id, scope=scope, scope_id=scope_id
        ).first()
        if row is None and create:
            row = AddonState(
                addon_id=self.addon_id, scope=scope, scope_id=scope_id,
                enabled=False, settings_json='{}',
            )
            db.session.add(row)
        return row

    # ---- read ---------------------------------------------------------

    def get(self, scope='global', scope_id=0):
        """Stored values merged over the manifest defaults.

        Unknown keys left over from an older manifest version are dropped, so
        an addon never sees a field it no longer declares.
        """
        values = self.defaults(scope)
        row = self._row(scope, scope_id)
        if row is not None:
            for key, value in row.settings.items():
                if key in values:
                    values[key] = value
        return values

    def is_layer_enabled(self, scope='global', scope_id=0):
        """This one layer's own switch, ignoring the layers above it.

        The UI needs this next to is_enabled() to distinguish "off" from
        "on, but blocked by the host" -- showing only the effective value
        would make the toggle appear to reject the operator's own click.
        """
        row = self._row(scope, scope_id)
        return bool(row and row.enabled)

    def is_enabled(self, scope='global', scope_id=0):
        """Effective enable state, walking every layer above `scope`."""
        scope = _scope_value(scope)

        _flag = self.is_layer_enabled

        if not _flag(AddonScope.GLOBAL.value, GLOBAL_SCOPE_ID):
            return False
        if scope == AddonScope.GLOBAL.value:
            return True

        if scope == AddonScope.HOST.value:
            return _flag(AddonScope.HOST.value, scope_id)

        instance = QLInstance.query.get(int(scope_id))
        if instance is None or instance.host_id is None:
            return False
        if not _flag(AddonScope.HOST.value, instance.host_id):
            return False
        return _flag(AddonScope.INSTANCE.value, scope_id)

    # ---- write --------------------------------------------------------

    def set(self, scope='global', scope_id=0, values=None, commit=True):
        """Validate `values` against the manifest and store them.

        Only declared keys are accepted -- an undeclared key is an error, not
        a silent no-op, because it is nearly always a typo in the addon or a
        stale UI field.
        """
        values = values or {}
        if not isinstance(values, dict):
            raise AddonSettingsError('settings must be an object')
        by_key = {f['key']: f for f in self.fields(scope)}
        unknown = [k for k in values if k not in by_key]
        if unknown:
            raise AddonSettingsError(
                f'unknown setting(s) for scope "{_scope_value(scope)}": {", ".join(sorted(unknown))}'
            )

        lock_provider_state(self.addon_id)
        row = self._row(scope, scope_id, create=True)
        stored = dict(row.settings)
        for key, value in values.items():
            stored[key] = _coerce(by_key[key], value)
        row.settings_json = json.dumps(stored, ensure_ascii=False, sort_keys=True)
        if commit:
            db.session.commit()
        return self.get(scope, scope_id)

    def set_enabled(self, scope='global', scope_id=0, enabled=True, commit=True):
        """Flip this layer's own switch.

        Does not touch the layers above it: turning an instance on while its
        host is off stores the intent but leaves `is_enabled()` False, which is
        what lets the UI show "on, blocked by host" instead of silently lying.
        """
        scope = _scope_value(scope)
        lock_provider_state(self.addon_id)
        if scope == AddonScope.GLOBAL.value and not enabled:
            check_provider_dependencies(self.addon_id, 'disable')
        row = self._row(scope, scope_id, create=True)
        row.enabled = bool(enabled)
        if commit:
            db.session.commit()
        return row.enabled


def delete_scope_rows(scope, scope_id, commit=False):
    """Drop every addon's rows for a scope that is going away.

    Called from the registry when a host or instance is deleted. Not a FK
    cascade because `scope_id` points at two different tables depending on
    `scope` -- see the AddonState docstring.
    """
    scope = _scope_value(scope)
    if scope not in (AddonScope.HOST.value, AddonScope.INSTANCE.value):
        raise AddonSettingsError('Only host or instance settings can be removed by scope cleanup.')
    lock_scoped_state_cleanup()
    deleted = AddonState.query.filter_by(scope=scope, scope_id=int(scope_id)).delete()
    if commit:
        db.session.commit()
    return deleted
