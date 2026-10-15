import React from 'react';
import { Link, useParams } from 'react-router-dom';
import { ChevronLeft, Loader2 } from 'lucide-react';
import AddonPanel from '../components/addons/AddonPanel';
import { resolveAddonIcon } from '../components/addons/addonIcons';
import { useAddons } from '../contexts/AddonsContext';

/**
 * A whole page an addon fills in.
 *
 * The page is core's: the route, the nav entry, the auth guard, the layout,
 * the loading and not-found states. The addon contributes only the body --
 * exactly what it contributes to an instance tab or a menu panel. One
 * contract, four mount points, so there is no separate "page API".
 */
function AddonPage() {
  const { addonId } = useParams();
  const { addons, loading } = useAddons();
  const addon = addons.find(a => a.id === addonId);

  if (loading && !addon) {
    return (
      <div className="mx-auto flex w-full max-w-5xl items-center gap-2 px-4 py-12 text-sm text-theme-muted">
        <Loader2 size={15} className="animate-spin" /> Loading...
      </div>
    );
  }

  const entry = addon?.ui?.page;
  const panel = entry?.panel ? addon.ui?.panels?.[entry.panel] : null;
  // Same rule as mountEntriesForAddon: a disabled addon's operator-facing
  // page stays hidden until it is switched on from the Addons list.
  const disabledAddon = Boolean(addon) && !addon.enabled;

  if (!addon || !entry || disabledAddon) {
    return (
      <div className="mx-auto w-full max-w-5xl px-4 py-12">
        <p className="text-sm text-theme-secondary">
          {disabledAddon
            ? `"${addon.name}" is disabled. Enable it from the Addons page first.`
            : addon ? 'This addon does not provide a page.' : `No addon named "${addonId}" is installed.`}
        </p>
        <Link to="/addons" className="mt-3 inline-flex items-center gap-1 text-sm"
              style={{ color: 'var(--accent-primary)' }}>
          <ChevronLeft size={15} /> Back to addons
        </Link>
      </div>
    );
  }

  const Icon = resolveAddonIcon(entry.icon || addon.ui?.icon);
  // A page with a navbar entry is a destination of its own, not a child of
  // the Addons list: it draws its own title and actions.
  const mounted = Boolean(addon.loaded && addon.ui_mountable);
  const ownsHeader = Boolean(entry.nav) && mounted;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8">
      {!ownsHeader && (
        <>
          <Link to="/addons" className="mb-4 inline-flex items-center gap-1 text-xs text-theme-muted hover:text-theme-primary">
            <ChevronLeft size={14} /> Addons
          </Link>

          <div className="mb-6 flex items-center gap-3">
            <Icon size={22} className="text-theme-muted" />
            <div>
              <h1 className="text-xl font-semibold text-theme-primary">
                {entry.label || addon.name}
              </h1>
              {addon.description && (
                <p className="mt-0.5 text-sm text-theme-secondary">{addon.description}</p>
              )}
            </div>
          </div>
        </>
      )}

      {mounted ? (
        <AddonPanel addon={addon} entry={entry} panel={panel} scope="global" scopeId={0} />
      ) : (
        <p className="text-sm" style={{ color: 'var(--accent-danger)' }}>
          This addon is installed but its interface cannot be shown
          {addon.loaded ? ' (it needs a newer QLSM).' : ' because it failed to load.'}
        </p>
      )}
    </div>
  );
}

export default AddonPage;
