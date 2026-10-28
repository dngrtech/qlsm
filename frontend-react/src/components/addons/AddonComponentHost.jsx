import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import * as addonUi from './uiKit';
import {
  addonAssetUrl, addonDownload, addonRequest, saveBlob,
} from '../../services/addons';
import { ensureAddonCss } from './addonCss';
import { publishAddonRuntime } from './publishAddonRuntime';

/**
 * Tier-2: mounts an addon's own pre-built component.
 *
 * The bundle is built by the addon's author, shipped inside the addon
 * package, and served by core from /api/addons/<id>/ui/. It is loaded with a
 * dynamic import() at the moment the mount point is rendered -- never at app
 * start, so an addon nobody opens costs nothing.
 *
 * The bundle must NOT contain its own React. Core publishes React and the
 * shared UI kit on window.__qlsm so an addon's build can mark them external;
 * two React copies on one page break hooks in ways that are miserable to
 * debug. Publishing happens here rather than in main.jsx so the globals only
 * exist once an addon actually needs them.
 *
 * `modal` is set when the entry declared `renders: "modal"` and the component
 * therefore *is* the whole dialog -- core's modal shell is skipped and the
 * open/close state reaches the addon through `ctx.modal` instead. That is what
 * lets an addon replace a purpose-built screen without losing its chrome
 * (title, width, header actions), which the generic shell cannot express.
 * Undefined for every other mount point.
 *
 * `addInstance` is the same idea for a tab in the Add Instance form (see
 * AddonAddInstanceTab.jsx): the form, not the component, holds the values.
 */
function AddonComponentHost({ addon, entry, scope, scopeId, modal, addInstance }) {
  const [Component, setComponent] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    publishAddonRuntime();
    ensureAddonCss(addon.id, entry.component);
    const url = addonAssetUrl(addon.id, entry.component);
    if (!url) {
      setError('The component path must stay inside the addon’s ui/ directory.');
      return undefined;
    }

    import(/* @vite-ignore */ url)
      .then((module) => {
        if (cancelled) return;
        const exported = module?.default || module?.[entry.export || 'Panel'];
        if (typeof exported !== 'function') {
          setError('The component bundle has no default export.');
          return;
        }
        // Wrapped in an object so React treats it as a value, not an updater.
        setComponent(() => exported);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Failed to load component');
      });

    return () => { cancelled = true; };
  }, [addon.id, entry.component, entry.export]);

  // An own-modal mount has no panel body to put a message in -- whatever it
  // renders lands loose on the page behind the (absent) dialog. So it reports
  // a failed load to the console and shows nothing.
  if (error) {
    if (modal) {
      console.error(`Addon ${addon.id}: could not load ${entry.component}: ${error}`);
      return null;
    }
    return (
      <p className="py-4 text-sm" style={{ color: 'var(--accent-danger)' }}>
        Could not load this addon's component: {error}
      </p>
    );
  }

  if (!Component) {
    if (modal) return null;
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-theme-muted">
        <Loader2 size={15} className="animate-spin" /> Loading component...
      </div>
    );
  }

  // The context an addon component receives. Every call handle here is
  // pinned to an addon prefix, so the component cannot reach a core endpoint
  // through anything it is given.
  const ctx = {
    addonId: addon.id,
    scope: { kind: scope, id: scopeId },
    api: (method, path, options) => addonRequest(addon.id, method, path, options),
    // A handle on *another* addon's endpoints. The one legitimate use is a
    // cross-addon UI contribution (see addons/README.md): a contributed
    // action names the addon that owns it and a route relative to that
    // addon's prefix, so the consuming component needs a call it cannot make
    // through its own pinned `api`. Still an addon prefix -- core endpoints
    // stay unreachable either way.
    apiFor: (otherAddonId) => (method, path, options) => (
      addonRequest(otherAddonId, method, path, options)
    ),
    // File downloads go through the same blob round-trip the declarative
    // table panel uses, so an addon keeps the CSRF header and the 401
    // interceptor instead of pointing a bare <a href> at the endpoint.
    download: (method, path, options) => addonDownload(addon.id, method, path, options),
    saveBlob,
    ui: addonUi,
    manifest: addon,
    // Only for `renders: "modal"` entries; undefined everywhere else.
    modal,
    // Only for an `add_instance_tabs` entry: { hostId, values, onChange }.
    // The tab has no instance to save to yet, so its values ride along with
    // the create request instead; undefined everywhere else.
    addInstance,
  };

  return <Component ctx={ctx} />;
}

export default AddonComponentHost;
