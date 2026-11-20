import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import AddonComponentHost from './AddonComponentHost';
import AddonErrorBoundary from './AddonErrorBoundary';
import AddonField from './AddonField';
import { addonRequest } from '../../services/addons';
import { initialValues, normalizeFields, resolveRoute } from './panelRoute';

/**
 * One addon's tab in the Add Instance form (`ui.add_instance_tabs`).
 *
 * Unlike every other mount point there is no instance to save to yet, so
 * the tab owns no save button: its values live in the form (`values` /
 * `onChange`) and go out with the create request as
 * `addon_options[<addon_id>]`, where the addon's `instance.created` handler
 * picks them up. The scope is the host picked in the form, so a `load`
 * route can say `{host_id}` and prefill per host (an addon-wide default, or
 * what that host can do). It reloads whenever the host changes.
 *
 * A tier-2 component gets the same three things as `ctx.addInstance =
 * { hostId, values, onChange }`.
 */
function AddonAddInstanceTab({ mount, hostId, values, errors, onChange }) {
  const { addon, entry, panel, scope } = mount;
  const fields = useMemo(() => normalizeFields(panel?.fields), [panel?.fields]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (entry?.component) return undefined;
    let cancelled = false;
    if (!panel?.load || !hostId) {
      onChange(initialValues(fields, null));
      return undefined;
    }
    setLoading(true);
    setLoadError(null);
    const route = resolveRoute(panel.load, { scope, scopeId: hostId, addonId: addon.id });
    addonRequest(addon.id, route.method, route.path)
      .then((data) => { if (!cancelled) onChange(initialValues(fields, data)); })
      .catch((err) => {
        if (cancelled) return;
        // The tab still works on the manifest defaults; say why they are
        // not this host's own.
        onChange(initialValues(fields, null));
        setLoadError(err?.response?.data?.error?.message || 'Failed to load defaults');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // onChange is a fresh closure on every parent render; the load depends
    // only on which addon, which route and which host.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addon.id, entry?.component, panel?.load, hostId, fields, scope, reloadToken]);

  let body;
  if (entry?.component) {
    body = (
      <AddonComponentHost
        addon={addon}
        entry={entry}
        scope={scope}
        scopeId={hostId || null}
        addInstance={{ hostId: hostId || null, values: values || {}, onChange }}
      />
    );
  } else if (loading) {
    body = (
      <div className="flex items-center gap-2 py-6 text-sm text-theme-muted">
        <Loader2 size={15} className="animate-spin" /> Loading...
      </div>
    );
  } else {
    const current = values || {};
    body = (
      <div className="flex flex-col gap-1">
        {panel?.description && (
          <p className="pb-2 text-sm text-theme-secondary">{panel.description}</p>
        )}
        {loadError && (
          <p className="pb-2 text-sm" style={{ color: 'var(--accent-warning, #d97706)' }}>
            {loadError}{' '}
            <button type="button" onClick={() => setReloadToken((n) => n + 1)}
                    className="inline-flex items-center gap-1 text-xs text-theme-secondary hover:text-theme-primary">
              <RefreshCw size={12} /> Retry
            </button>
          </p>
        )}
        {fields.map((field) => (
          <AddonField
            key={field.key}
            field={field}
            value={current[field.key]}
            error={errors?.[field.key]}
            disabled={false}
            onChange={(key, value) => onChange({ ...current, [key]: value })}
          />
        ))}
      </div>
    );
  }

  return <AddonErrorBoundary addonId={addon?.id}>{body}</AddonErrorBoundary>;
}

export default AddonAddInstanceTab;
