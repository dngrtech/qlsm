import path from 'node:path';
import { pathToFileURL } from 'node:url';
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// The tier-2 loader is the one part of the addon UI that nothing else covered,
// and it shipped broken: `modal` was read in three places but never declared
// as a prop, so every `renders: "modal"` addon died with "modal is not
// defined" the moment its menu entry was clicked. The unit tests all passed --
// none of them mounted this component. These do.
//
// The bundle is loaded at runtime by URL, so the URL builder is mocked to
// point at a fixture that looks like a real addon bundle (plain ESM, default
// export, React off window.__qlsm) instead of a component compiled into core.
//
// A file:// URL, built from the working directory rather than import.meta.url:
// under vitest this module's own URL is an http: one, and the `@vite-ignore`
// on the host's dynamic import means Node's loader -- which takes only file:
// and data: -- is what actually resolves it.
const fixture = (name) => pathToFileURL(
  path.resolve(globalThis.process.cwd(), 'src/components/addons/__tests__/fixtures', name),
).href;

const FIXTURE_URL = fixture('ownModalPanel.js');

const mocks = vi.hoisted(() => ({
  addonAssetUrl: vi.fn(),
  addonRequest: vi.fn(),
  addonDownload: vi.fn(),
  saveBlob: vi.fn(),
}));

vi.mock('../../../services/addons', () => ({
  addonAssetUrl: (...a) => mocks.addonAssetUrl(...a),
  addonRequest: (...a) => mocks.addonRequest(...a),
  addonDownload: (...a) => mocks.addonDownload(...a),
  saveBlob: (...a) => mocks.saveBlob(...a),
}));

import AddonComponentHost from '../AddonComponentHost';

const ADDON = { id: 'demo-management', name: 'Demos' };
const ENTRY = { component: 'ui/Panel.js' };

beforeEach(() => {
  vi.clearAllMocks();
  delete window.__lastAddonCtx;
  mocks.addonAssetUrl.mockReturnValue(FIXTURE_URL);
});

describe('AddonComponentHost', () => {
  it('mounts a component that renders its own dialog and hands it ctx.modal', async () => {
    const onClose = vi.fn();
    render(
      <AddonComponentHost
        addon={ADDON}
        entry={{ ...ENTRY, renders: 'modal' }}
        scope="instance"
        scopeId={7}
        modal={{ isOpen: true, onClose, entity: { id: 7, name: 'duel srv' } }}
      />,
    );

    expect(await screen.findByText('entity:duel srv')).toBeInTheDocument();
    expect(screen.getByText('open:true')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('gives every component the four pinned call handles', async () => {
    render(
      <AddonComponentHost addon={ADDON} entry={ENTRY} scope="instance" scopeId={7} />,
    );

    expect(await screen.findByText('handles:api,apiFor,download,saveBlob')).toBeInTheDocument();
  });

  it('hands an Add Instance tab its form state as ctx.addInstance', async () => {
    const onChange = vi.fn();
    render(
      <AddonComponentHost
        addon={ADDON}
        entry={ENTRY}
        scope="host"
        scopeId={3}
        addInstance={{ hostId: 3, values: { on: true }, onChange }}
      />,
    );
    await screen.findByText('entity:none');

    const ctx = window.__lastAddonCtx;
    expect(ctx.addInstance.hostId).toBe(3);
    expect(ctx.addInstance.values).toEqual({ on: true });
    ctx.addInstance.onChange({ on: false });
    expect(onChange).toHaveBeenCalledWith({ on: false });
  });

  it('leaves ctx.addInstance undefined everywhere else', async () => {
    render(
      <AddonComponentHost addon={ADDON} entry={ENTRY} scope="instance" scopeId={7} />,
    );
    await screen.findByText('entity:none');
    expect(window.__lastAddonCtx.addInstance).toBeUndefined();
  });

  it('leaves ctx.modal undefined for an ordinary panel mount', async () => {
    render(
      <AddonComponentHost addon={ADDON} entry={ENTRY} scope="instance" scopeId={7} />,
    );

    expect(await screen.findByText('entity:none')).toBeInTheDocument();
  });

  it('pins api to this addon and apiFor to whichever one it is given', async () => {
    render(
      <AddonComponentHost addon={ADDON} entry={ENTRY} scope="instance" scopeId={7} />,
    );
    await screen.findByText('entity:none');

    const ctx = window.__lastAddonCtx;
    ctx.api('GET', 'instances/7/demos');
    expect(mocks.addonRequest).toHaveBeenLastCalledWith(
      'demo-management', 'GET', 'instances/7/demos', undefined,
    );

    // The cross-addon handle: a contributed action names the addon that owns
    // the route, and it must reach that addon, not this one.
    ctx.apiFor('other-addon')('POST', 'matches/x/rebuild');
    expect(mocks.addonRequest).toHaveBeenLastCalledWith(
      'other-addon', 'POST', 'matches/x/rebuild', undefined,
    );

    ctx.download('GET', 'demos/download');
    expect(mocks.addonDownload).toHaveBeenLastCalledWith(
      'demo-management', 'GET', 'demos/download', undefined,
    );

    expect(mocks.addonAssetUrl).toHaveBeenLastCalledWith('demo-management', 'ui/Panel.js');
  });

  it('shows a loading placeholder for a panel mount but nothing for a modal one', () => {
    const { container, rerender } = render(
      <AddonComponentHost addon={ADDON} entry={ENTRY} scope="instance" scopeId={7} />,
    );
    expect(container.textContent).toContain('Loading component');

    rerender(
      <AddonComponentHost
        addon={ADDON}
        entry={{ ...ENTRY, renders: 'modal' }}
        scope="instance"
        scopeId={7}
        modal={{ isOpen: true, onClose: vi.fn(), entity: { id: 7, name: 'duel srv' } }}
      />,
    );
    expect(container.textContent).not.toContain('Loading component');
  });

  it('reports a bundle that fails to load without breaking the page', async () => {
    mocks.addonAssetUrl.mockReturnValue(fixture('does-not-exist.js'));
    render(
      <AddonComponentHost addon={ADDON} entry={ENTRY} scope="instance" scopeId={7} />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Could not load this addon's component/)).toBeInTheDocument();
    });
  });
});
