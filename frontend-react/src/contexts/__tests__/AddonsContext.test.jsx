import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../services/addons', () => ({ listAddons: vi.fn() }));
vi.mock('../AuthContext', () => ({ useAuth: () => ({ isAuthenticated: true }) }));

import { listAddons } from '../../services/addons';
import { AddonsProvider, useAddonMounts, useAddons } from '../AddonsContext';

const HEALTHY = {
  id: 'good', name: 'Good', version: '1.0.0', loaded: true, ui_mountable: true, enabled: true,
  ui: {
    panels: { p: { kind: 'form' } },
    host_menu: [{ id: 'h', label: 'Good host panel', panel: 'p' }],
    settings_section: { label: 'Good settings', panel: 'p' },
  },
};

function MountList({ point }) {
  const mounts = useAddonMounts(point);
  return <ul>{mounts.map(m => <li key={m.key}>{m.label}</li>)}</ul>;
}

function Catalog() {
  const { addons, error } = useAddons();
  return <div><span data-testid="count">{addons.length}</span><span>{error}</span></div>;
}

const renderWith = (ui) => render(<AddonsProvider>{ui}</AddonsProvider>);

beforeEach(() => vi.clearAllMocks());

describe('AddonsContext', () => {
  it('exposes entries mounted at a point', async () => {
    listAddons.mockResolvedValue([HEALTHY]);
    renderWith(<MountList point="host_menu" />);
    expect(await screen.findByText('Good host panel')).toBeInTheDocument();
  });

  it('accepts a single object for settings_section, not just an array', async () => {
    listAddons.mockResolvedValue([HEALTHY]);
    renderWith(<MountList point="settings_section" />);
    expect(await screen.findByText('Good settings')).toBeInTheDocument();
  });

  it('falls back to the addon id when a label is not a non-empty string', async () => {
    listAddons.mockResolvedValue([{
      ...HEALTHY,
      name: { bad: true },
      ui: { ...HEALTHY.ui, host_menu: [{ id: 'h', label: { bad: true }, panel: 'p' }] },
    }]);
    renderWith(<MountList point="host_menu" />);
    expect(await screen.findByText('good')).toBeInTheDocument();
  });

  it('omits an addon that failed to load', async () => {
    listAddons.mockResolvedValue([{ ...HEALTHY, loaded: false }]);
    renderWith(<MountList point="host_menu" />);
    await waitFor(() => expect(listAddons).toHaveBeenCalled());
    expect(screen.queryByText('Good host panel')).not.toBeInTheDocument();
  });

  it('omits an addon whose UI needs a newer core', async () => {
    listAddons.mockResolvedValue([{ ...HEALTHY, ui_mountable: false }]);
    renderWith(<MountList point="host_menu" />);
    await waitFor(() => expect(listAddons).toHaveBeenCalled());
    expect(screen.queryByText('Good host panel')).not.toBeInTheDocument();
  });

  it('omits an entry whose panel is not declared', async () => {
    listAddons.mockResolvedValue([{
      ...HEALTHY,
      ui: { panels: {}, host_menu: [{ id: 'h', label: 'Dangling', panel: 'missing' }] },
    }]);
    renderWith(<MountList point="host_menu" />);
    await waitFor(() => expect(listAddons).toHaveBeenCalled());
    expect(screen.queryByText('Dangling')).not.toBeInTheDocument();
  });

  it('keeps a component entry that declares no panel', async () => {
    listAddons.mockResolvedValue([{
      ...HEALTHY,
      ui: { host_menu: [{ id: 'h', label: 'Custom', component: 'ui/panel.js' }] },
    }]);
    renderWith(<MountList point="host_menu" />);
    expect(await screen.findByText('Custom')).toBeInTheDocument();
  });

  it('survives a catalog failure without breaking the page', async () => {
    listAddons.mockRejectedValue(new Error('boom'));
    renderWith(<Catalog />);
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('0'));
    expect(screen.getByText(/Failed to load addons/)).toBeInTheDocument();
  });

  it('returns nothing for a point no addon declares', async () => {
    listAddons.mockResolvedValue([HEALTHY]);
    const { container } = renderWith(<MountList point="instance_tabs" />);
    await waitFor(() => expect(listAddons).toHaveBeenCalled());
    expect(container.querySelectorAll('li')).toHaveLength(0);
  });

  it('hides a disabled bundled addon from operator-facing mount points', async () => {
    listAddons.mockResolvedValue([{ ...HEALTHY, source: 'bundled', enabled: false }]);
    const { container } = renderWith(<MountList point="host_menu" />);
    await waitFor(() => expect(listAddons).toHaveBeenCalled());
    expect(container.querySelectorAll('li')).toHaveLength(0);
  });

  it('still shows settings_section for a disabled bundled addon', async () => {
    listAddons.mockResolvedValue([{ ...HEALTHY, source: 'bundled', enabled: false }]);
    renderWith(<MountList point="settings_section" />);
    expect(await screen.findByText('Good settings')).toBeInTheDocument();
  });

  it('shows an enabled bundled addon at its mount points', async () => {
    listAddons.mockResolvedValue([{ ...HEALTHY, source: 'bundled', enabled: true }]);
    renderWith(<MountList point="host_menu" />);
    expect(await screen.findByText('Good host panel')).toBeInTheDocument();
  });

  it('also hides a disabled installed addon from operator-facing mount points', async () => {
    listAddons.mockResolvedValue([{ ...HEALTHY, source: 'installed', enabled: false }]);
    const { container } = renderWith(<MountList point="host_menu" />);
    await waitFor(() => expect(listAddons).toHaveBeenCalled());
    expect(container.querySelectorAll('li')).toHaveLength(0);
  });

  it('shows an enabled installed addon at its mount points', async () => {
    listAddons.mockResolvedValue([{ ...HEALTHY, source: 'installed', enabled: true }]);
    renderWith(<MountList point="host_menu" />);
    expect(await screen.findByText('Good host panel')).toBeInTheDocument();
  });
});
