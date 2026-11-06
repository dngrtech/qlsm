import React, { useEffect, useState } from 'react';
import { Menu } from '@headlessui/react';
import AddonComponentHost from './AddonComponentHost';
import AddonErrorBoundary from './AddonErrorBoundary';
import AddonModal from './AddonModal';
import { resolveAddonIcon } from './addonIcons';
import { rendersOwnModal } from './addonEntry';
import { resolveRoute } from './panelRoute';
import { addonRequest } from '../../services/addons';
import { useAddonMounts } from '../../contexts/AddonsContext';

/**
 * The optional status shown after a menu entry's label: a dot (green when
 * `ok`, grey otherwise) and a short label, from the entry's `status` route
 * (`{ok: bool, label: str}`, the same shape as a panel's status badge).
 *
 * It is rendered inside `Menu.Items`, which unmounts when the menu closes, so
 * mounting is what fetches: every open asks again, nothing polls while open.
 * A failed or malformed answer renders nothing -- no spinner, no error -- and
 * never gets in the way of the entry being clicked.
 */
function MenuEntryStatus({ mount, scopeId }) {
  const route = mount.entry?.status;
  const [status, setStatus] = useState(null);

  useEffect(() => {
    // Drop the previous entity's answer right away: a stale dot next to a
    // different host's name is worse than no dot.
    setStatus(null);
    if (typeof route !== 'string' || !route) return undefined;
    const resolved = resolveRoute(route, { scope: mount.scope, scopeId, addonId: mount.addon?.id });
    // Opening a menu must never mutate anything; the manifest validator
    // enforces GET and so does this.
    if (!resolved || resolved.method !== 'GET') return undefined;
    let cancelled = false;
    addonRequest(mount.addon?.id, resolved.method, resolved.path)
      .then((data) => {
        if (cancelled) return;
        const valid = data && typeof data.ok === 'boolean'
          && typeof data.label === 'string' && data.label.trim();
        setStatus(valid ? { ok: data.ok, label: data.label.trim() } : null);
      })
      .catch(() => { if (!cancelled) setStatus(null); });
    return () => { cancelled = true; };
  }, [route, mount.scope, mount.addon?.id, scopeId]);

  if (!status) return null;
  return (
    // min-w-0 lets the label truncate instead of squeezing the entry's own
    // name onto several lines in a narrow menu.
    <span className="ml-auto flex min-w-0 items-center gap-1.5 pl-3">
      <span
        data-testid="addon-menu-status-dot"
        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${status.ok ? 'bg-emerald-400' : 'bg-gray-400'}`}
      />
      <span className="text-xs text-theme-muted truncate max-w-[10rem]" title={status.label}>
        {status.label}
      </span>
    </span>
  );
}

/**
 * Addon entries for a host or instance action menu.
 *
 * Split into a hook plus two pieces because of a Headless UI constraint:
 * `Menu.Items` unmounts its children when the menu closes, and clicking an
 * entry closes the menu -- so a dialog rendered inside the menu would be torn
 * down the instant it opened. The items go inside the menu, the modal goes
 * outside it. HostActionsMenu already keeps its own confirmation modals
 * outside `<Menu>` for the same reason.
 *
 * `entity` is the whole host/instance object, not just its id: an addon that
 * supplies its own dialog gets it through `ctx.modal.entity`, because a
 * purpose-built screen usually shows the thing's name, port and so on -- not
 * only its id.
 *
 * Usage in a menu component:
 *
 *   const addonMenu = useAddonMenu('host_menu', host);
 *   return (<>
 *     {addonMenu.modal}
 *     <Menu>... <Menu.Items>... {addonMenu.items(closeMenu)} </Menu.Items></Menu>
 *   </>);
 */
export function useAddonMenu(point, entity, subtitle) {
  const mounts = useAddonMounts(point);
  const [openMount, setOpenMount] = useState(null);
  const scopeId = entity?.id;

  const items = (closeMenu) => {
    if (mounts.length === 0) return null;
    return (
      <div className="px-1 py-1" style={{ borderTop: '1px solid var(--surface-border)' }}>
        {mounts.map((mount) => {
          const Icon = resolveAddonIcon(mount.icon);
          return (
            <Menu.Item key={mount.key}>
              {({ active }) => (
                <button
                  type="button"
                  onClick={() => {
                    setOpenMount(mount);
                    if (typeof closeMenu === 'function') closeMenu();
                  }}
                  className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors ${
                    active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'
                  }`}
                >
                  <Icon size={15} className="mr-3 flex-shrink-0 text-theme-muted" />
                  <span className="whitespace-nowrap flex-shrink-0">{mount.label}</span>
                  <MenuEntryStatus mount={mount} scopeId={scopeId} />
                </button>
              )}
            </Menu.Item>
          );
        })}
      </div>
    );
  };

  // An addon may supply the whole dialog (`renders: "modal"` on a tier-2
  // component). Then core's modal shell is skipped entirely -- that is what
  // lets a feature keep its purpose-built screen on the way into an addon
  // instead of being flattened into the generic panel shell.
  const ownModal = openMount && rendersOwnModal(openMount.entry) && openMount.entry?.component;

  // Nothing is shown while the bundle loads: the operator clicked a menu
  // entry, and a flash of placeholder before the real dialog is worse than
  // the dialog simply appearing.
  const modal = ownModal ? (
    <AddonErrorBoundary addonId={openMount.addon?.id}>
      <AddonComponentHost
        addon={openMount.addon}
        entry={openMount.entry}
        scope={openMount.scope}
        scopeId={scopeId}
        modal={{
          isOpen: Boolean(openMount),
          onClose: () => setOpenMount(null),
          entity,
          subtitle,
        }}
      />
    </AddonErrorBoundary>
  ) : (
    <AddonModal
      isOpen={Boolean(openMount)}
      onClose={() => setOpenMount(null)}
      mount={openMount}
      scopeId={scopeId}
      subtitle={subtitle}
    />
  );

  return { mounts, items, modal };
}

export default useAddonMenu;
