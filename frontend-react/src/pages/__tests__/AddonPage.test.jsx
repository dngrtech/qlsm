import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AddonPage from '../AddonPage';

const mocks = vi.hoisted(() => ({ useAddons: vi.fn() }));

vi.mock('../../contexts/AddonsContext', () => ({
  useAddons: mocks.useAddons,
}));

vi.mock('../../components/addons/AddonPanel', () => ({
  default: () => <div data-testid="addon-body">body</div>,
}));

const makeAddon = (page) => ({
  id: 'demo',
  name: 'Demo addon',
  description: 'Demo description',
  enabled: true,
  loaded: true,
  ui_mountable: true,
  ui: { page },
});

const renderPage = (addon) => {
  mocks.useAddons.mockReturnValue({ addons: addon ? [addon] : [], loading: false });
  return render(
    <MemoryRouter initialEntries={['/addons/demo']}>
      <Routes>
        <Route path="/addons/:addonId" element={<AddonPage />} />
      </Routes>
    </MemoryRouter>,
  );
};

describe('AddonPage header', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders no back link and no core title when the page has a nav entry', () => {
    renderPage(makeAddon({ component: 'ui/Page.js', label: 'Demo page', nav: { label: 'Demo' } }));

    expect(screen.getByTestId('addon-body')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /addons/i })).toBeNull();
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
  });

  it('keeps the back link and title when the page has no nav entry', () => {
    renderPage(makeAddon({ component: 'ui/Page.js', label: 'Demo page' }));

    expect(screen.getByTestId('addon-body')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /addons/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Demo page' })).toBeInTheDocument();
  });

  it('keeps core header and shows the error when a nav page cannot be mounted', () => {
    renderPage({
      ...makeAddon({ component: 'ui/Page.js', label: 'Demo page', nav: { label: 'Demo' } }),
      loaded: false,
    });

    expect(screen.queryByTestId('addon-body')).toBeNull();
    expect(screen.getByRole('link', { name: /addons/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Demo page' })).toBeInTheDocument();
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });

  it('keeps the back link on the not-found branch', () => {
    renderPage(null);

    expect(screen.getByRole('link', { name: /back to addons/i })).toBeInTheDocument();
  });
});
